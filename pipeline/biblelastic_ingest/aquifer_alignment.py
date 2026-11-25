"""
The Bible Aquifer's word alignments of a translation (e.g., the Aquifer Spanish Bible Reference Text, or the Reina-Valera 1909) with the original languages,
made into our alignments of that translation with the SR-GNT and the UHB, so that a word can be tapped for what it translates, as in the OET.

In an Aquifer Bible's `alignments/` folder:
- `tsv/nt_X.tsv` and `tsv/ot_X.tsv`: the translation's words, each with an id of book (2 digits), chapter (3), verse (3), and word (3), and its text
    (punctuation is there too, marked `exclude`)
- `tsv/SBLGNT.tsv` and `tsv/WLCM.tsv`: the Greek (SBL Greek New Testament) and Hebrew (Westminster Leningrad Codex) words, with ids like `n40001001001`
    and, for the Hebrew, a fifth part for each piece of a word, e.g., `o010010010011` for the בְּ of בְּרֵאשִׁית
- `json/BB-CCC.alignment.json`: for each chapter, records that join some original words (`source`) to some translation words (`target`), by id

Neither side's words are numbered as ours are, and the SBLGNT isn't the SR-GNT, so each side's words are paired with ours by matching them in order,
book by book (so that differences in verse numbering don't matter): the translation's by their letters, the Greek without accents, and the Hebrew by its consonants.
"""
import csv
import json
from pathlib import Path

from . import normalise, ubs

# The Aquifer's original-language texts → ours, with how to compare their words
ORIGINALS = { 'SBLGNT':('SR-GNT', normalise.greek), 'WLCM':('UHB', normalise.hebrew_consonants) }


def _rows( path:Path ) -> list:
    with open( path, encoding='utf-8', newline='' ) as tsvFile:
        reader = csv.reader( tsvFile, delimiter='\t', quoting=csv.QUOTE_NONE )
        header = next( reader )
        return [ dict( zip( header, row ) ) for row in reader ]


def _book( number:str ) -> str|None:
    return ubs.BOOKS[int(number) - 1] if number.isdigit() and 1 <= int(number) <= len(ubs.BOOKS) else None


def match( a:list, b:list, reach:int=500 ) -> list:
    """
    Pair up the equal items of two sequences in order, as normalise.match_sequences does, but able to find its place again after a long
    difference (e.g., a passage that only one edition of the Greek has): where the next items aren't equal, it looks up to `reach` items ahead in each
    for the nearest place where three in a row are the same.
    """
    pairs, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]: pairs.append( (i, j) ); i += 1; j += 1; continue
        if pairs and pairs[-1] == (i-1, j-1) and a[i+1:i+2] == b[j+1:j+2] and i+1 < len(a): # One word that's different (e.g., spelt differently)
            pairs.append( (i, j) ); i += 1; j += 1; continue
        ahead = {}
        for dj in range( min( reach, len(b) - j - 2 ) ): ahead.setdefault( tuple( b[j+dj:j+dj+3] ), dj )
        best = None
        for di in range( min( reach, len(a) - i - 2 ) ):
            dj = ahead.get( tuple( a[i+di:i+di+3] ) )
            if dj is not None and (best is None or di + dj < sum( best )): best = (di, dj)
            if best and di > sum( best ): break
        if best is None: break # Nothing more in common within reach
        i, j = i + best[0], j + best[1]
    return pairs


def _pair( theirs:dict, ourFolder:Path, key, wordsOnly:bool ) -> tuple:
    """
    theirs: BBB → [(their id, text), …] in order. Returns ({ their id: (BBB, our token index) }, how many of theirs there were).
    wordsOnly: only our tokens that have a morphology (an original's words, not its titles) are matched.
    """
    paired, total = {}, 0
    for BBB, words in theirs.items():
        total += len(words)
        path = ourFolder / f'{BBB}.tokens.tsv'
        if not path.exists(): continue
        ours = [ (ix, row['text']) for ix, row in enumerate( _rows( path ) ) if not wordsOnly or row.get( 'morph' ) ]
        pairs = match( [ key( text ) for _id, text in words ], [ key( text ) for _ix, text in ours ] )
        for a, b in pairs: paired[words[a][0]] = (BBB, ours[b][0])
    return paired, total


def align( edition:dict, sourceRoot:Path, output:Path ) -> dict:
    """ Writes output/alignments/EDITION--SR-GNT and EDITION--UHB, and returns statistics """
    folder = sourceRoot / edition['aquifer_alignments']
    stats = { 'edition':edition['id'] }
    # The translation's words, paired with ours
    translated = {}
    for path in sorted( (folder / 'tsv').glob( '*.tsv' ) ):
        if path.stem in ORIGINALS: continue
        for row in _rows( path ):
            if row.get( 'exclude' ) == 'y': continue # Punctuation
            if (BBB := _book( row['id'][:2] )): translated.setdefault( BBB, [] ).append( (row['id'], row['text']) )
    for words in translated.values(): words.sort()
    ours, total = _pair( translated, output / edition['id'] / 'documents', normalise.latin, False )
    stats['translation_words'], stats['translation_paired'] = total, len(ours)
    # The original-language words, paired with the SR-GNT's and the UHB's (each Hebrew word is the pieces with the same first 11 digits)
    originals = {}
    articles = set() # The Greek article's words: left out of a link that has other Greek words in it (e.g., ἡ ἀληθινή → ‘verdadera’ is ἀληθινή)
    for document, (ourId, key) in ORIGINALS.items():
        if not (output / ourId / 'documents').is_dir(): continue
        words = {}
        for row in _rows( folder / 'tsv' / f'{document}.tsv' ):
            wordId = row['id'][1:12]
            if row.get( 'lemma' ) == 'ὁ': articles.add( wordId )
            if not (BBB := _book( wordId[:2] )): continue
            book = words.setdefault( BBB, [] )
            if book and book[-1][0] == wordId: book[-1] = (wordId, book[-1][1] + row['text'])
            else: book.append( (wordId, row['text']) )
        paired, total = _pair( words, output / ourId / 'documents', key, True )
        originals[document] = (ourId, paired)
        stats[f'{ourId}_words'], stats[f'{ourId}_paired'] = total, len(paired)
    # The links, from the chapters' records
    links = {} # (our original edition, BBB) → {(translation token, original token)}
    records = unlinked = 0
    for path in sorted( (folder / 'json').glob( '*.alignment.json' ) ):
        for group in json.loads( path.read_text( encoding='utf-8' ) ).get( 'groups', [] ):
            document = group.get( 'documents', [{}] )[0].get( 'docid' )
            if document not in originals: continue
            ourId, paired = originals[document]
            for record in group.get( 'records', [] ):
                records += 1
                sourceIds = [ source.split( '|' )[0][:11] for source in record.get( 'source', [] ) ]
                if any( sourceId not in articles for sourceId in sourceIds ): sourceIds = [ sourceId for sourceId in sourceIds if sourceId not in articles ]
                sources = [ paired[sourceId] for sourceId in sourceIds if sourceId in paired ]
                targets = [ ours[target.split( '|' )[0]] for target in record.get( 'target', [] ) if target.split( '|' )[0] in ours ]
                if not sources or not targets: unlinked += 1; continue
                for BBB, to in sources:
                    for targetBBB, fromIx in targets:
                        if targetBBB == BBB: links.setdefault( (ourId, BBB), set() ).add( (fromIx, to) )
    for (ourId, BBB), pairs in links.items():
        outputFolder = output / 'alignments' / f"{edition['id']}--{ourId}"
        outputFolder.mkdir( parents=True, exist_ok=True )
        with open( outputFolder / f'{BBB}.links.tsv', 'w', encoding='utf-8', newline='' ) as linksFile:
            linksFile.write( 'from\tto\n' )
            linksFile.writelines( f'{a}\t{b}\n' for a, b in sorted( pairs ) )
    stats['records'], stats['records_unlinked'] = records, unlinked
    stats['links'] = sum( len(pairs) for pairs in links.values() )
    return stats
