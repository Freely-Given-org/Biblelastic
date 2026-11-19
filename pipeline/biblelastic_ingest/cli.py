"""
Convert the registered source editions into the Biblelastic intermediate format.

Usage (from the pipeline/ folder):
    python3 -m biblelastic_ingest [--editions OET-RV,SR-GNT] [--books MRK,GEN] [--jobs N]

Each source file (or each document of a commentary or dictionary) is handled in its own process,
then word alignments are derived in a second pass.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import contextlib
import csv
from datetime import date
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import shutil
import sys
import time
import tomllib

from . import items, normalise, ubs, usfm

PIPELINE_FOLDER = Path( __file__ ).resolve().parent.parent
REPOSITORY_FOLDER = PIPELINE_FOLDER.parent

# USFM book codes that differ from the BibleOrgSys ones that we use
USFM_TO_BBB = { '1SA':'SA1','2SA':'SA2', '1KI':'KI1','2KI':'KI2', '1CH':'CH1','2CH':'CH2', 'EZK':'EZE', 'JON':'JNA', 'NAM':'NAH',
                '1CO':'CO1','2CO':'CO2', '1TH':'TH1','2TH':'TH2', '1TI':'TI1','2TI':'TI2', 'JAS':'JAM',
                '1PE':'PE1','2PE':'PE2', '1JN':'JN1','2JN':'JN2','3JN':'JN3', 'JUD':'JDE' }
FEATURE_ATTRIBUTES = { 'lemma':'lemma', 'strong':'strong', 'x-strong':'strong', 'x-morph':'morph', 'x-koine':'koine' }
MORPH_LANGUAGES = { 'He':'hbo', 'Ar':'arc', 'Gr':'grc' }
TABLE_KEY_FUNCTIONS = { 'Grek':normalise.greek, 'Hebr':normalise.hebrew_consonants }
NOTES_RE = re.compile( r'\\(fe|fig|f|x)\b.*?\\\1\*', re.DOTALL )


def book_code( path:Path ) -> str:
    """ OET-RV_MRK.ESFM → MRK and 42-MRK.usfm → MRK and 09-1SA.usfm → SA1 """
    code = re.split( '[-_]', path.stem )[-1].upper()
    return USFM_TO_BBB.get( code, code )


def load_row_table( edition:dict, sourceRoot:Path ) -> tuple:
    """
    Load an OET word table.

    Returns the header and { BBB: [(rowNumber, row), …] } for every row (ESFM word numbers are one-based row numbers).
    """
    rowsByBook = {}
    with open( sourceRoot / edition['row_table'], encoding='utf-8-sig', newline='' ) as tableFile:
        reader = csv.reader( tableFile, delimiter='\t', quoting=csv.QUOTE_NONE )
        header = next( reader )
        refIndex = header.index( 'Ref' )
        for rowNumber, row in enumerate( reader, start=1 ):
            rowsByBook.setdefault( row[refIndex][:3], [] ).append( (rowNumber, row) )
    return header, rowsByBook


_transliterators = {} # Per-process cache: language → (function, {word: transliteration})
def transliterator( language:str, libraryFolder:str ):
    """ Returns a caching transliteration function from the (optional) BibleTransliterations library, or None if it's not available. """
    if language not in _transliterators:
        function = None
        try:
            if libraryFolder not in sys.path: sys.path.insert( 0, libraryFolder )
            import BibleTransliterations
            with contextlib.redirect_stdout( io.StringIO() ): BibleTransliterations.load_transliteration_table( language )
            function = getattr( BibleTransliterations, f'transliterate_{language}' )
        except Exception: pass
        cache = {}
        def transliterate( word:str ) -> str:
            if word not in cache:
                logging.disable( logging.CRITICAL ) # It logs every word that has anything unexpected in it
                try: cache[word] = function( word ).replace( '\u2060', '' )
                except Exception: cache[word] = ''
                finally: logging.disable( logging.NOTSET )
            return cache[word]
        _transliterators[language] = transliterate if function else None
    return _transliterators[language]


def write_tsv( path:Path, header:list, rows ) -> None:
    with open( path, 'w', encoding='utf-8', newline='' ) as tsvFile:
        tsvFile.write( '\t'.join( header ) + '\n' )
        for row in rows:
            fields = [ str( field ) for field in row ]
            assert not any( '\t' in field or '\n' in field for field in fields ), f'{path.name} {fields}'
            tsvFile.write( '\t'.join( fields ) + '\n' )


def ingest_file( edition:dict, sourcePath:str, BBB:str, table:tuple|None, outputFolder:str, transliterationsFolder:str ) -> dict:
    """ Worker: parse one file, add derived features, check it, and write its intermediate files. """
    script = edition['script']
    source = Path( sourcePath ).read_bytes()
    text = source.decode( 'utf-8' )
    isESFM = edition.get( 'format' ) == 'ESFM'
    doc = usfm.parse( text, script, isESFM )
    tokens = doc.tokens

    normaliser = normalise.NORMALISERS[script]
    for token in tokens:
        features = token[3]
        for attributeName in [ name for name in features if name != 'row' ]:
            value = features.pop( attributeName )
            if attributeName in FEATURE_ATTRIBUTES: features[FEATURE_ATTRIBUTES[attributeName]] = value
        features['norm'] = normaliser( token[1] )
        if script == 'Hebr':
            features['cons'] = normalise.hebrew_consonants( token[1] )
            features['lang'] = MORPH_LANGUAGES.get( features.get( 'morph', '' )[:2], '' )
    transliterate = transliterator( edition['transliterate'], transliterationsFolder ) if 'transliterate' in edition else None
    if transliterate:
        for token in tokens:
            if 'morph' in token[3]: # Only the original-language words
                token[3]['translit'] = transliterate( token[1] )
                token[3]['lemma_translit'] = transliterate( token[3].get( 'lemma', '' ) ) if token[3].get( 'lemma' ) else ''

    stats = { 'BBB':BBB, 'source':Path( sourcePath ).name, 'sha256':hashlib.sha256( source ).hexdigest(), 'tokens':len(tokens) }
    stats['transliterated'] = bool(transliterate)
    layerRows = variantRows = None
    if table is not None: # Link our words to the OET word-table rows
        tableHeader, allTableRows = table
        keyFunction = TABLE_KEY_FUNCTIONS[script]
        wordColumn, filterColumn = tableHeader.index( edition['row_table_word_column'] ), tableHeader.index( edition['row_table_filter_column'] )
        wantedValues = set( edition['row_table_filter_values'] )
        tableRows = [ (rowNumber, keyFunction( row[wordColumn] )) for rowNumber,row in allTableRows if row[filterColumn] in wantedValues ]
        wordIndexes = [ ix for ix,token in enumerate( tokens ) if 'morph' in token[3] ] # Only the \w words -- not titles, etc.
        ourKeys, tableKeys = [ keyFunction( tokens[ix][1] ) for ix in wordIndexes ], [ key for _rowNumber,key in tableRows ]
        pairs = [ (n,n) for n in range( len(ourKeys) ) ] if len(ourKeys) == len(tableKeys) else []
        if sum( 1 for n,_n in pairs if ourKeys[n] != tableKeys[n] ) > len(pairs) // 100 or not pairs:
            pairs = normalise.match_sequences( ourKeys, tableKeys ) # Not simply the same words in the same order
        for n, rowIndex in pairs: tokens[wordIndexes[n]][3]['oet_row'] = tableRows[rowIndex][0]
        stats.update( source_words=len(wordIndexes), table_rows=len(tableRows), linked_to_table=len(pairs),
                      linked_with_different_form=sum( 1 for n,rowIndex in pairs if ourKeys[n] != tableKeys[rowIndex] ) )

        # A layer of extra features from the table, with one row for each of our tokens
        rowsByNumber = dict( allTableRows )
        layer = edition.get( 'layer' )
        if layer:
            columnIndexes = [ tableHeader.index( tableColumn ) for tableColumn in layer['columns'].values() ]
            layerRows = [ [ rowsByNumber[token[3]['oet_row']][columnIndex] for columnIndex in columnIndexes ] if 'oet_row' in token[3] else ['']*len(columnIndexes)
                            for token in tokens ]
            stats['layer_values'] = sum( 1 for layerRow in layerRows for value in layerRow if value )
        # Table rows for words that aren't in our text (variant readings), each anchored before the next word that is
        variants = edition.get( 'variants' )
        if variants:
            columnIndexes = [ tableHeader.index( tableColumn ) for tableColumn in variants['columns'].values() ]
            wantedValues = set( variants['filter_values'] )
            tokenIndexByRow = { token[3]['oet_row']:ix for ix,token in enumerate( tokens ) if 'oet_row' in token[3] }
            variantRows, anchor = [], len(tokens)
            for rowNumber, row in reversed( allTableRows ):
                if rowNumber in tokenIndexByRow: anchor = tokenIndexByRow[rowNumber]
                elif row[filterColumn] in wantedValues: variantRows.append( [anchor, rowNumber] + [ row[columnIndex] for columnIndex in columnIndexes ] )
            variantRows.reverse()
            stats['variants'] = len(variantRows)

    # Checks
    ours, theirs = usfm.WHITESPACE_RE.sub( '', doc.plain_text() ), usfm.reference_text( text, isESFM )
    stats['text_ok'] = ours == theirs
    if not stats['text_ok']:
        ix = next( (ix for ix,(a,b) in enumerate( zip( ours, theirs ) ) if a != b), min( len(ours), len(theirs) ) )
        stats['text_difference'] = { 'offset':ix, 'ours':ours[max(0,ix-30):ix+30], 'source':theirs[max(0,ix-30):ix+30] }
    stats['row_marks'], stats['marks'] = doc.row_marks, doc.marks
    stats['row_marks_ok'] = doc.row_marks == len( re.findall( r'¦\d+', NOTES_RE.sub( '', text ) ) )
    stats['with_row'] = sum( 1 for token in tokens if 'row' in token[3] )
    nodeCounts = {}
    for node in doc.nodes: nodeCounts[node[0]] = nodeCounts.get( node[0], 0 ) + 1
    stats.update( nodes=nodeCounts, notes=len(doc.notes), warnings=doc.warnings, unknown_markers=doc.unknown_markers )

    # Output
    folder = Path( outputFolder )
    columns = ['norm'] + edition['features']
    write_tsv( folder / f'{BBB}.tokens.tsv', ['before','text','after'] + columns,
                ( [before, word, after] + [ features.get( column, '' ) for column in columns ] for before,word,after,features in tokens ) )
    if layerRows is not None:
        layerFolder = folder.parent / 'layers' / edition['layer']['id']
        write_tsv( layerFolder / f'{BBB}.features.tsv', list( edition['layer']['columns'] ), layerRows )
    if variantRows is not None:
        layerFolder = folder.parent / 'layers' / edition['variants']['id']
        write_tsv( layerFolder / f'{BBB}.variants.tsv', ['anchor','row'] + list( edition['variants']['columns'] ), variantRows )
    with open( folder / f'{BBB}.nodes.tsv', 'w', encoding='utf-8', newline='' ) as nodesFile:
        nodesFile.write( 'type\tstart\tend\tname\tattributes\n' )
        for nodeType, start, end, name, attributes in doc.nodes:
            nodesFile.write( f'{nodeType}\t{start}\t{end}\t{name}\t{json.dumps( attributes, ensure_ascii=False ) if attributes else ""}\n' )
    with open( folder / f'{BBB}.notes.tsv', 'w', encoding='utf-8', newline='' ) as notesFile:
        notesFile.write( 'anchor\ttype\tcontent\n' )
        for anchor, noteType, content in doc.notes:
            notesFile.write( f'{anchor}\t{noteType}\t{content.replace( "\t", " " )}\n' )
    metadata = { 'BBB':BBB, 'headers':doc.headers, 'remarks':doc.header_remarks }
    metadata.update( stats )
    (folder / f'{BBB}.meta.json').write_text( json.dumps( metadata, ensure_ascii=False, indent=1 ) + '\n', encoding='utf-8' )
    return stats


def ingest_items( edition:dict, document:str, sourceNames:list, itemSources:list, outputFolder:str ) -> dict:
    """ Worker: parse the items (study notes, articles, etc.) of one document of a commentary or dictionary, check them, and write the files. """
    parsed = items.parse( itemSources, edition['item_documents'], edition['script'] )
    return write_items( parsed, document, sourceNames, hashlib.sha256( ''.join( itemSources ).encode( 'utf-8' ) ).hexdigest(), outputFolder, edition['script'] )


def write_items( parsed, document:str, sourceNames:list, digest:str, outputFolder:str, script:str ) -> dict:
    """ Write the files of one document of a commentary or dictionary, and return its statistics """
    doc, tokens = parsed.doc, parsed.doc.tokens
    normaliser = normalise.NORMALISERS[script]
    nodeCounts, anchorCounts = {}, {}
    for node in doc.nodes: nodeCounts[node[0]] = nodeCounts.get( node[0], 0 ) + 1
    for anchor in parsed.anchors: anchorCounts[anchor[2]] = anchorCounts.get( anchor[2], 0 ) + 1
    stats = { 'BBB':document, 'source':', '.join( sourceNames ), 'sha256':digest,
              'tokens':len(tokens), 'entries':len(parsed.entries), 'anchors':anchorCounts, 'links':len(parsed.links), 'nodes':nodeCounts,
              'text_ok':not parsed.text_differences, 'row_marks_ok':True, 'bad_references':parsed.bad_references,
              'warnings':doc.warnings, 'unknown_markers':{} }
    if parsed.text_differences: stats['text_difference'] = parsed.text_differences[0]

    folder = Path( outputFolder )
    write_tsv( folder / f'{document}.tokens.tsv', ['before','text','after','norm'], ( [before, word, after, normaliser( word )] for before,word,after,_features in tokens ) )
    write_tsv( folder / f'{document}.nodes.tsv', ['type','start','end','name','attributes'],
                ( [nodeType, start, end, name, json.dumps( attributes, ensure_ascii=False ) if attributes else ''] for nodeType,start,end,name,attributes in doc.nodes ) )
    write_tsv( folder / f'{document}.entries.tsv', ['start','end','name','type','title'], parsed.entries )
    write_tsv( folder / f'{document}.anchors.tsv', ['start','end','kind','reference'], parsed.anchors )
    write_tsv( folder / f'{document}.links.tsv', ['start','end','kind','target'], parsed.links )
    (folder / f'{document}.meta.json').write_text( json.dumps( stats, ensure_ascii=False, indent=1 ) + '\n', encoding='utf-8' )
    # Only for the cross-document check of the links (not kept in the report)
    stats['entry_locations'] = [ f'{document} {entry[2]}' for entry in parsed.entries ]
    stats['link_targets'] = [ link[3] for link in parsed.links ]
    return stats


def ingest_ubs( entry:dict, output:Path, sourceRoot:Path ) -> dict:
    """
    The UBS dictionaries and handbooks (see ubs.py): a layer with the meaning of each word of the original-language editions,
    and the handbooks as a work of their own. Needs those editions' token files (from this run or an earlier one).
    """
    folder = sourceRoot / entry['folder']
    stats, places, references = {}, {}, {} # places: reference → (edition, BBB, token index)
    meanings, books, verses = {}, {}, {} # (edition, BBB) → (header, tokens) and token index → (chapter, verse)
    for language in ('hebrew', 'greek'):
        if language not in entry: continue
        edition = entry[language]['edition']
        documents = output / edition / 'documents'
        if not documents.is_dir(): print( f"ERROR: {edition} must be ingested before the UBS {language} dictionary" ); return {'failed':True}
        editionMeanings, editionReferences = ubs.load_dictionary( str(folder / entry[language]['file']), language == 'greek' )
        meanings.update( editionMeanings )
        linked = total = 0
        for BBB, bookReferences in editionReferences.items():
            tokensPath = documents / f'{BBB}.tokens.tsv'
            if not tokensPath.exists(): continue
            with open( tokensPath, encoding='utf-8', newline='' ) as tokensFile:
                rows = list( csv.reader( tokensFile, delimiter='\t', quoting=csv.QUOTE_NONE ) )
            books[(edition, BBB)] = (rows[0], rows[1:])
            verseOf = verses[(edition, BBB)] = {}
            for nodeType, start, end, name, _attributes in list( csv.reader( open( documents / f'{BBB}.nodes.tsv', encoding='utf-8', newline='' ), delimiter='\t', quoting=csv.QUOTE_NONE ) )[1:]:
                if nodeType == 'verse' and ':' in name:
                    chapter, verse = name.split( ':', 1 )
                    for ix in range( int(start), int(end) ): verseOf[ix] = (int(chapter), int(re.match( r'\d*', verse ).group() or 0))
            for reference, ix in ubs.link_book( rows[1:], rows[0], bookReferences, language == 'greek' ).items():
                places[reference] = (edition, BBB, ix)
            byReference = { reference[3]:reference[5] for reference in bookReferences }
            references.update( { reference:byReference[reference] for reference in byReference if reference in places } )
            linked += sum( 1 for reference in byReference if reference in places ); total += len(byReference)
        stats[edition] = { 'references':total, 'linked':linked }

    def place_of( reference:str ):
        edition, BBB, ix = places.get( reference[-14:], (None, None, None) )
        verse = verses.get( (edition, BBB), {} ).get( ix )
        return (BBB,) + verse if verse else None

    # The handbooks: a work of their own, and links from the words that each article is about
    handbooks = entry.get( 'handbooks' )
    wordLinks = {} # (edition, BBB, token index) → [locator, …]
    if handbooks:
        handbookFolder = output / handbooks['id'] / 'documents'
        if handbookFolder.parent.is_dir(): shutil.rmtree( handbookFolder.parent )
        handbookFolder.mkdir( parents=True )
        documents = []
        for document, file in handbooks['files'].items():
            parsed, links = ubs.parse_handbook( str(folder / file), document, place_of )
            documents.append( write_items( parsed, document, [Path( file ).name], hashlib.sha256( (folder / file).read_bytes() ).hexdigest(), str(handbookFolder), 'Latn' ) )
            for reference, name in links:
                if reference[-14:] in places: wordLinks.setdefault( places[reference[-14:]], [] ).append( f'{document} {name}' )
            stats[handbooks['id']] = stats.get( handbooks['id'], 0 ) + len(links)
        stats['handbook_word_links'] = sum( len(links) for links in wordLinks.values() )
        locations = { location for document in documents for location in document.pop( 'entry_locations' ) }
        brokenLinks = sorted( { target for document in documents for target in document.pop( 'link_targets' ) if target not in locations } )
        manifest = { 'format_version':usfm.FORMAT_VERSION, 'generated':date.today().isoformat(), 'kind':'dictionary' }
        manifest.update( { key:value for key,value in handbooks.items() if key != 'files' } )
        manifest.update( { 'token_columns':['before','text','after','norm'], 'layers':[], 'broken_links':brokenLinks,
                           'documents':[ { key:document[key] for key in ('BBB','source','sha256','tokens') } for document in documents ] } )
        (handbookFolder.parent / 'manifest.json').write_text( json.dumps( manifest, ensure_ascii=False, indent=1 ) + '\n', encoding='utf-8' )
        stats['handbook_entries'] = sum( document['entries'] for document in documents )

    # The layer: for every word of each edition, its meaning there, and the handbook articles about it
    byToken = { place:references[reference] for reference, place in places.items() if reference in references }
    for (edition, BBB), (header, tokens) in books.items():
        layerFolder = output / edition / 'layers' / entry['id']
        layerFolder.mkdir( parents=True, exist_ok=True )
        rows = []
        for ix in range( len(tokens) ):
            meaning = meanings.get( byToken.get( (edition, BBB, ix) ), ['', '', '', '', ''] )
            rows.append( meaning + [ ';'.join( dict.fromkeys( wordLinks.get( (edition, BBB, ix), [] ) ) ) ] )
        write_tsv( layerFolder / f'{BBB}.features.tsv', ubs.LAYER_COLUMNS, rows )
    for language in ('hebrew', 'greek'):
        if language not in entry: continue
        manifestPath = output / entry[language]['edition'] / 'manifest.json'
        manifest = json.loads( manifestPath.read_text( encoding='utf-8' ) )
        manifest['layers'] = [ layer for layer in manifest.get( 'layers', [] ) if layer.get( 'id' ) != entry['id'] ] + [
            { 'id':entry['id'], 'kind':'features', 'columns':ubs.LAYER_COLUMNS } | { key:entry[key] for key in ('name','copyright','licence','attribution','changes','licence_verified') if key in entry } ]
        manifestPath.write_text( json.dumps( manifest, ensure_ascii=False, indent=1 ) + '\n', encoding='utf-8' )
    return stats


def read_column( path:Path, columnName:str ) -> list:
    with open( path, encoding='utf-8', newline='' ) as tsvFile:
        columnIndex = tsvFile.readline().rstrip( '\n' ).split( '\t' ).index( columnName )
        return [ line.rstrip( '\n' ).split( '\t' )[columnIndex] for line in tsvFile ]


def align_book( fromFolder:str, toFolder:str, BBB:str, outputPath:str ) -> dict:
    """ Worker: join a translation's word numbers to an original's table-row numbers, giving token-to-token links. """
    fromRows = read_column( Path( fromFolder ) / f'{BBB}.tokens.tsv', 'row' )
    toIndexes = { row:ix for ix,row in enumerate( read_column( Path( toFolder ) / f'{BBB}.tokens.tsv', 'oet_row' ) ) if row }
    links = [ (ix, toIndexes[row]) for ix,row in enumerate( fromRows ) if row in toIndexes ]
    with open( outputPath, 'w', encoding='utf-8', newline='' ) as linksFile:
        linksFile.write( 'from\tto\n' )
        linksFile.writelines( f'{a}\t{b}\n' for a,b in links )
    return { 'BBB':BBB, 'from_tokens':len(fromRows), 'from_numbered':sum( 1 for row in fromRows if row ), 'links':len(links),
             'to_tokens':len(toIndexes), 'to_linked':len( { b for _a,b in links } ) }


def main() -> int:
    parser = argparse.ArgumentParser( prog='biblelastic_ingest', description=__doc__.split( '\n' )[1] )
    parser.add_argument( '--registry', type=Path, default=PIPELINE_FOLDER / 'sources.toml' )
    parser.add_argument( '--source-root', type=Path, default=Path( os.environ.get( 'BIBLELASTIC_SOURCE_ROOT', REPOSITORY_FOLDER.parent ) ) )
    parser.add_argument( '--output', type=Path, default=REPOSITORY_FOLDER / 'build' / 'intermediate' )
    parser.add_argument( '--editions', help='Comma-separated edition ids (default: all)' )
    parser.add_argument( '--books', help='Comma-separated book codes (default: all)' )
    parser.add_argument( '--jobs', type=int, default=os.cpu_count() )
    parser.add_argument( '--clean', action='store_true', help='Delete the output of the selected editions first' )
    arguments = parser.parse_args()

    startTime = time.time()
    registry = tomllib.loads( arguments.registry.read_text( encoding='utf-8' ) )
    wantedEditions = set( arguments.editions.split( ',' ) ) if arguments.editions else None
    wantedBooks = set( arguments.books.upper().split( ',' ) ) if arguments.books else None
    editions = [ edition for edition in registry['edition'] if not wantedEditions or edition['id'] in wantedEditions ]

    transliterationsFolder = str( arguments.source_root / registry.get( 'tools', {} ).get( 'transliterations', 'BibleTransliterations/Python' ) )
    failures = 0
    report = { 'format_version':usfm.FORMAT_VERSION, 'generated':date.today().isoformat(), 'editions':{}, 'alignments':{} }
    with ProcessPoolExecutor( max_workers=arguments.jobs ) as pool:
        futures = {}
        for edition in editions:
            folder = arguments.output / edition['id'] / 'documents'
            if arguments.clean and (arguments.output / edition['id']).is_dir(): shutil.rmtree( arguments.output / edition['id'] )
            folder.mkdir( parents=True, exist_ok=True )
            for layerKey in ('layer','variants'):
                if layerKey in edition: (arguments.output / edition['id'] / 'layers' / edition[layerKey]['id']).mkdir( parents=True, exist_ok=True )
            tableHeader, rowTable = load_row_table( edition, arguments.source_root ) if 'row_table' in edition else (None, None)
            paths = sorted( path for pattern in edition['files'] for path in arguments.source_root.glob( pattern ) )
            if not paths: print( f"ERROR: no source files found for {edition['id']} under {arguments.source_root}" ); failures += 1
            if 'item_documents' in edition: # A commentary or dictionary: split the files into items, and handle each document's items together
                groups = {}
                for path in paths:
                    for document, itemSource in items.split_items( path.read_text( encoding='utf-8' ), edition['item_documents'] ):
                        group = groups.setdefault( document, ([], []) )
                        if path.name not in group[0]: group[0].append( path.name )
                        group[1].append( itemSource )
                futures[edition['id']] = [ pool.submit( ingest_items, edition, document, sourceNames, itemSources, str(folder) )
                                            for document, (sourceNames, itemSources) in groups.items() if not wantedBooks or document.upper() in wantedBooks ]
                continue
            futures[edition['id']] = [ pool.submit( ingest_file, edition, str(path), book_code( path ), (tableHeader, rowTable.get( book_code( path ), [] )) if rowTable else None, str(folder), transliterationsFolder )
                                        for path in paths if not wantedBooks or book_code( path ) in wantedBooks ]

        for edition in editions:
            documents = [ future.result() for future in futures[edition['id']] ]
            manifest = { 'format_version':usfm.FORMAT_VERSION, 'generated':date.today().isoformat() }
            manifest['kind'] = 'scripture' # Unless the registry says that it's a commentary or dictionary
            manifest.update( { key:value for key,value in edition.items() if not key.startswith( 'row_table' ) and key not in ('files','layer','variants') } )
            manifest['layers'] = [ { key:(list( value ) if key == 'columns' else value) for key,value in edition[layerKey].items() if key != 'filter_values' }
                                    | { 'kind':'features' if layerKey == 'layer' else 'variants' } for layerKey in ('layer','variants') if layerKey in edition ]
            manifest['token_columns'] = ['before','text','after','norm'] + edition['features']
            if 'item_documents' in edition: # Check that every link between items leads somewhere
                # (ignoring case, because the sources aren't consistent about it, e.g., AbrahamSBosom for AbrahamsBosom)
                locations = { location.casefold() for document in documents for location in document.pop( 'entry_locations' ) }
                targets = [ target.casefold() for document in documents for target in document.pop( 'link_targets' ) ]
                brokenLinks = sorted( { target for target in targets if target not in locations } )
                manifest['broken_links'] = brokenLinks
            manifest['documents'] = [ { key:document[key] for key in ('BBB','source','sha256','tokens') } for document in documents ]
            (arguments.output / edition['id'] / 'manifest.json').write_text( json.dumps( manifest, ensure_ascii=False, indent=1 ) + '\n', encoding='utf-8' )
            report['editions'][edition['id']] = documents

            bad = [ document for document in documents if not document['text_ok'] or not document['row_marks_ok'] ]
            failures += len(bad)
            warnings, unknownMarkers = {}, {}
            for document in documents:
                for name, count in document['warnings'].items(): warnings[name] = warnings.get( name, 0 ) + count
                for name, count in document['unknown_markers'].items(): unknownMarkers[name] = unknownMarkers.get( name, 0 ) + count
            totalTokens = sum( document['tokens'] for document in documents )
            print( f"{edition['id']}: {len(documents)} documents, {totalTokens:,} tokens, {len(documents)-len(bad)}/{len(documents)} passed the text checks" )
            if 'item_documents' in edition:
                anchorCounts = {}
                for document in documents:
                    for kind, count in document['anchors'].items(): anchorCounts[kind] = anchorCounts.get( kind, 0 ) + count
                badReferences = [ reference for document in documents for reference in document['bad_references'] ]
                print( f"    {sum( document['entries'] for document in documents ):,} entries; Scripture anchors: {anchorCounts};"
                       f" {len(targets):,} links between entries ({sum( 1 for target in targets if target not in locations ):,} to {len(brokenLinks):,} missing entries)" )
                if badReferences: print( f"    {len(badReferences):,} references couldn't be understood, e.g., {badReferences[:6]}" )
            if edition['format'] == 'ESFM':
                print( f"    {sum( document['with_row'] for document in documents ):,} tokens have word numbers; {sum( document['marks'] for document in documents ):,} OET marks became attributes" )
            if 'row_table' in edition:
                print( f"    {sum( document['linked_to_table'] for document in documents ):,} of {sum( document['source_words'] for document in documents ):,} words linked to"
                       f" {sum( document['table_rows'] for document in documents ):,} word-table rows ({sum( document['linked_with_different_form'] for document in documents ):,} with a different form)" )
            if 'layer' in edition: print( f"    {sum( document['layer_values'] for document in documents ):,} values in the {edition['layer']['id']} feature layer" )
            if 'variants' in edition: print( f"    {sum( document['variants'] for document in documents ):,} variant words" )
            if 'transliterate' in edition and not all( document['transliterated'] for document in documents ):
                print( f'    WARNING: no transliterations (BibleTransliterations not found at {transliterationsFolder})' )
            if warnings: print( f'    warnings: {warnings}' )
            if unknownMarkers: print( f'    unknown paragraph markers: {unknownMarkers}' )
            for document in bad:
                print( f"    FAILED {document['BBB']}: text_ok={document['text_ok']} row_marks_ok={document['row_marks_ok']} {document.get( 'text_difference', '' )}" )

        # Second pass: derive alignments (needs both editions' token files to be complete)
        ingested = { edition['id'] for edition in editions }
        for alignment in registry.get( 'alignment', [] ):
            fromId = alignment['from']
            for toId in alignment['to']:
                if fromId not in ingested or toId not in ingested: continue
                fromFolder, toFolder = arguments.output / fromId / 'documents', arguments.output / toId / 'documents'
                books = sorted( { path.name[:3] for path in fromFolder.glob( '*.tokens.tsv' ) } & { path.name[:3] for path in toFolder.glob( '*.tokens.tsv' ) } )
                if wantedBooks: books = [ BBB for BBB in books if BBB in wantedBooks ]
                outputFolder = arguments.output / 'alignments' / f'{fromId}--{toId}'
                outputFolder.mkdir( parents=True, exist_ok=True )
                results = list( pool.map( align_book, [str(fromFolder)]*len(books), [str(toFolder)]*len(books), books, [ str(outputFolder / f'{BBB}.links.tsv') for BBB in books ] ) )
                report['alignments'][f'{fromId}--{toId}'] = results
                total = { key:sum( result[key] for result in results ) for key in ('from_tokens','from_numbered','links','to_tokens','to_linked') }
                if results: print( f"{fromId} → {toId}: {len(books)} books, {total['links']:,} links from {total['from_numbered']:,} numbered words;"
                                   f" {total['to_linked']:,} of {total['to_tokens']:,} linkable original words are translated" )

    # Thesauruses: checked, then copied as they are (the compiler works out how each term is looked up)
    report['thesauruses'] = {}
    for thesaurus in registry.get( 'thesaurus', [] ) if not wantedEditions else []:
        rows = [ line.split( '\t' ) for line in (PIPELINE_FOLDER / thesaurus['file']).read_text( encoding='utf-8' ).split( '\n' ) if line ]
        problems = [ row[0] for row in rows if len(row) != 4 or not row[0].strip() or not (row[1].strip() or row[2].strip()) ]
        problems += sorted( { row[0] for row in rows if sum( 1 for other in rows if other[0].casefold() == row[0].casefold() ) > 1 } )
        if rows[0] != ['term','see','contrast','note'] or problems:
            print( f"ERROR: thesaurus {thesaurus['file']} has bad or repeated rows: {problems[:5]}" ); failures += 1; continue
        (arguments.output / 'thesaurus').mkdir( parents=True, exist_ok=True )
        write_tsv( arguments.output / 'thesaurus' / f"{thesaurus['language']}.tsv", rows[0], rows[1:] )
        report['thesauruses'][thesaurus['language']] = { 'terms':len(rows)-1, 'licence':thesaurus.get( 'licence', '' ) }
        print( f"Thesaurus ({thesaurus['language']}): {len(rows)-1} terms" )

    # The UBS dictionaries and handbooks (after the editions that they're joined to)
    report['ubs'] = {}
    for entry in registry.get( 'ubs', [] ):
        wanted = { entry[language]['edition'] for language in ('hebrew','greek') if language in entry } | ({ entry['handbooks']['id'] } if 'handbooks' in entry else set())
        if wantedEditions and not wanted & wantedEditions: continue
        stats = ingest_ubs( entry, arguments.output, arguments.source_root )
        if stats.get( 'failed' ): failures += 1; continue
        report['ubs'][entry['id']] = stats
        for edition, counts in stats.items():
            if isinstance( counts, dict ): print( f"UBS {edition}: {counts['linked']:,} of {counts['references']:,} dictionary references joined to words" )
        if 'handbook_entries' in stats: print( f"UBS handbooks: {stats['handbook_entries']:,} entries; {stats['handbook_word_links']:,} of their word references joined to words" )

    (arguments.output / 'report.json').write_text( json.dumps( report, ensure_ascii=False, indent=1 ) + '\n', encoding='utf-8' )
    print( f"{'FAILED' if failures else 'Done'} in {time.time()-startTime:.1f}s -- output in {arguments.output}" )
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit( main() )
