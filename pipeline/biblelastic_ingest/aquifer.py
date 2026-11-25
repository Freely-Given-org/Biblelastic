"""
Resources from the Bible Aquifer (https://github.com/BibleAquifer), e.g., its Spanish study notes and Bible dictionary
(translations of the Tyndale Open Study Notes and Tyndale Open Bible Dictionary), from their JSON files.

Each file is a list of items: { reference_id, title, index_reference, content (HTML), associations: { passage, resource } }.
In the content, <data class="bible-ref" data-start-ref="01001003" data-end-ref="01002003"> is a reference (book 2 digits, chapter 3, verse 3),
and <data class="resource-ref" data-content-id="4188"> is a link to another item (by its reference_id).

They become the same files as the Tyndale works: study notes go into a document for each Bible book (named by the verses, e.g., `3:16` or `1:1-2:3`),
and book introductions, profiles, and dictionary articles into the documents `Intros`, `Profiles`, and `Articles`.
"""
import html
import html.parser
import json
import re
import unicodedata
from pathlib import Path

from . import items, ubs, usfm

# Which document each resource's items go into ("*": the Bible book that the item is about), and their entry type
RESOURCES = { 'AquiferOpenStudyNotes':('*', 'StudyNote'), 'AquiferOpenStudyNotesBookIntros':('Intros', 'BookIntro'),
              'AquiferOpenStudyNotesProfiles':('Profiles', 'Profile'), 'AquiferOpenBibleDictionary':('Articles', 'Article') }
# Titles that are mistranslated in the source (by resource and reference_id), as found so far
TITLE_CORRECTIONS = { ('AquiferOpenStudyNotesBookIntros', '26394'):'Job',      # The Spanish introduction to Job is titled ‘Work’
                      ('AquiferOpenBibleDictionary', '7691'):'Pecado' }          # The Spanish article on sin (its heading is ‘PECADO’) is titled ‘Without’
BLOCKS = { 'p':'p', 'h1':'h1', 'h2':'h2', 'h3':'h3', 'li':'li' }
STYLES = { 'em':'ital', 'i':'ital', 'strong':'bold', 'b':'bold', 'u':'underline', 'sup':'sup', 'sub':'sub' }


def place( reference:str ) -> tuple|None:
    """ 01001003 → ('GEN', 1, 3) (a verse or chapter of 0 means the whole chapter or book) """
    if not re.fullmatch( r'\d{8}', reference or '' ) or not 1 <= int(reference[:2]) <= len(ubs.BOOKS): return None
    return ubs.BOOKS[int(reference[:2]) - 1], int(reference[2:5]), int(reference[5:8])


def passage( start:str, end:str, extent ) -> str|None:
    """ A reference's passage, e.g., `GEN 1:3-2:3`. extent(BBB) is a book's last (chapter, verse), for references to whole books. """
    first, last = place( start ), place( end or start )
    if not first: return None
    if not last or last[0] != first[0]: last = first
    BBB, chapter, verse = first
    if chapter == 0: # The whole book
        lastChapter, lastVerse = extent( BBB ) or (0, 0)
        return f'{BBB} 1:1-{lastChapter}:{lastVerse}' if lastChapter else None
    if verse == 0: return f'{BBB} {chapter}' if last[1] in (0, chapter) else f'{BBB} {chapter}-{last[1]}'
    lastChapter, lastVerse = last[1:]
    if (lastChapter, lastVerse) <= (chapter, verse) or lastVerse == 0: return f'{BBB} {chapter}:{verse}'
    return f'{BBB} {chapter}:{verse}-{lastChapter}:{lastVerse}'


def entry_name( title:str ) -> str:
    """ `Elifelet #3` → `Elifelet3`, `Israel, Historia de` → `IsraelHistoriaDe` (letters without accents, and digits) """
    plain = ''.join( character for character in unicodedata.normalize( 'NFD', title ) if not unicodedata.combining( character ) )
    return ''.join( word[:1].upper() + word[1:] for word in re.findall( r'[A-Za-z0-9]+', plain ) ) or 'X'


class _ContentParser( html.parser.HTMLParser ):
    """ One item's HTML content, added to the parsed items """
    def __init__( self, parser:items._Parser, extent, target_of ) -> None:
        super().__init__( convert_charrefs=True )
        self.parser, self.extent, self.target_of = parser, extent, target_of
        self.open = [] # (tag, start token, attributes)

    def handle_starttag( self, tag:str, attributes:list ) -> None:
        attributes = dict( attributes )
        if tag == 'br': self.parser.add_text( ' ' ); return
        if tag in BLOCKS:
            self.parser.start_paragraph( BLOCKS[tag], {} )
        self.open.append( (tag, len(self.parser.doc.tokens), attributes) )

    def handle_endtag( self, tag:str ) -> None:
        while self.open:
            openTag, start, attributes = self.open.pop()
            end = len(self.parser.doc.tokens)
            if openTag in BLOCKS: self.parser.end_paragraph()
            elif openTag in STYLES and end > start: self.parser.doc.nodes.append( ('span', start, end, STYLES[openTag], {}) )
            elif openTag == 'data' and end > start:
                kind = attributes.get( 'class', '' )
                if kind == 'bible-ref':
                    found = passage( attributes.get( 'data-start-ref', '' ), attributes.get( 'data-end-ref', '' ), self.extent )
                    if found: self.parser.parsed.anchors.append( (start, end, 'cites', found) )
                    else: self.parser.parsed.bad_references.append( attributes.get( 'data-start-ref', '' ) )
                elif kind == 'resource-ref':
                    target = self.target_of( attributes.get( 'data-content-id', '' ) )
                    if target: self.parser.parsed.links.append( (start, end, 'see', target) )
                    else: self.parser.doc.warn( 'link to an item that is not included' )
            if openTag == tag: break

    def handle_data( self, data:str ) -> None:
        if self.parser.paraName is None:
            if not data.strip(): return
            self.parser.start_paragraph( 'p', {} ) # Text that isn't in a paragraph
        self.parser.add_text( data )


def parse( paths:list, extent ) -> dict:
    """
    The items of an Aquifer resource (or several, e.g., the study notes with their book introductions): { document: (parsed items, source file names) }.
    extent(BBB) is a book's last (chapter, verse).
    """
    loaded = [] # (document, entry type, item, path)
    for path in paths:
        resource = next( (part for part in Path( path ).parts if part in RESOURCES), None )
        if not resource: continue
        document, entryType = RESOURCES[resource]
        for item in json.loads( Path( path ).read_text( encoding='utf-8' ) ):
            item['title'] = TITLE_CORRECTIONS.get( (resource, str(item.get( 'reference_id' ))), item.get( 'title', '' ) )
            loaded.append( (document, entryType, item, Path( path ).name) )
    # Each item's document and entry name, so that links between items can be followed
    targets, names = {}, {}
    for ix, (document, entryType, item, _name) in enumerate( loaded ):
        associations = item.get( 'associations' ) or {}
        if document == '*':
            first = (associations.get( 'passage' ) or [{}])[0]
            where = passage( first.get( 'start_ref', '' ), first.get( 'end_ref', '' ), extent ) or ''
            document, name = (where.split( ' ', 1 ) + [''])[:2] if where else ('', '')
        elif document == 'Intros':
            name = (place( item.get( 'index_reference', '' )[:8] ) or ('',))[0]
        else: name = entry_name( item.get( 'title', '' ) )
        if not document or not name: continue
        used = names.setdefault( document, set() )
        unique, number = name, 1
        while unique in used: number += 1; unique = f'{name}~{number}'
        used.add( unique )
        targets[str(item.get( 'reference_id' ))] = (ix, document, unique)
    target_of = lambda contentId: ' '.join( targets[contentId][1:] ) if contentId in targets else None

    results = {}
    for ix, document, name in sorted( targets.values() ):
        _document, entryType, item, fileName = loaded[ix]
        parser, sources = results.setdefault( document, (items._Parser( {}, 'Latn' ), []) )
        if fileName not in sources: sources.append( fileName )
        tokens, firstParagraph = parser.doc.tokens, len(parser.doc.paragraphs)
        start = len(tokens)
        content = _ContentParser( parser, extent, target_of )
        content.feed( item.get( 'content', '' ) ); content.close()
        parser.end_paragraph()
        parser.gap = ''
        if len(tokens) == start: continue
        title = '' if entryType == 'StudyNote' else usfm.WHITESPACE_RE.sub( ' ', item.get( 'title', '' ) ).strip()
        parser.parsed.entries.append( (start, len(tokens), name, entryType, title) )
        # What a note or introduction is about. (A profile's or article's associations are every passage where its subject is named,
        # up to hundreds, so they aren't taken as what it's about: like the Tyndale dictionary's, its own references are what it cites.)
        for association in (item.get( 'associations' ) or {}).get( 'passage', [] ) if entryType in ('StudyNote', 'BookIntro') else []:
            found = passage( association.get( 'start_ref', '' ), association.get( 'end_ref', '' ), extent )
            if entryType == 'BookIntro': found = passage( item['index_reference'][:8], '', extent ) # (Its association is only the book's first verse)
            if found: parser.parsed.anchors.append( (start, len(tokens), 'about', found) )
            if entryType == 'BookIntro': break
        # Check that no text was lost or reordered, against an independent reduction of the source
        ours = ''.join( tokenlessText + ''.join( before+text+after for before,text,after,_features in tokens[paraStart:paraEnd] )
                            for _name, _kind, paraStart, paraEnd, tokenlessText in parser.doc.paragraphs[firstParagraph:] )
        theirs = html.unescape( re.sub( r'<[^>]+>', '', item.get( 'content', '' ) ) )
        ours, theirs = usfm.WHITESPACE_RE.sub( '', ours ), usfm.WHITESPACE_RE.sub( '', theirs )
        if ours != theirs:
            at = next( (at for at,(a,b) in enumerate( zip( ours, theirs ) ) if a != b), min( len(ours), len(theirs) ) )
            parser.parsed.text_differences.append( { 'entry':f'{document} {name}', 'offset':at, 'ours':ours[max(0,at-30):at+30], 'source':theirs[max(0,at-30):at+30] } )
    return { document:(parser.finish(), sources) for document, (parser, sources) in results.items() }
