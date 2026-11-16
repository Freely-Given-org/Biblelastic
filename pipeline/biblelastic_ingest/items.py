"""
Tokenising parser for works that are made of separate items (study notes, dictionary articles, etc.),
as in Tyndale's XML format (https://tyndaleopenresources.com).

Each item becomes an *entry*: a range of tokens with a name that locates it within its document.
The Scripture passages that an item is about, and the ones that it cites, become *anchors*,
and its links to other items become *links*.
"""
import html
import re
import xml.etree.ElementTree as ET

from . import usfm

WORD_RE = re.compile( rf"{usfm._W}+(?:['’]{usfm._W}+)*" )
ITEM_RE = re.compile( r'<item\b([^>]*)>.*?</item>', re.DOTALL )
ITEM_ATTRIBUTE_RE = re.compile( r'(\w+)="([^"]*)"' )
BODY_RE = re.compile( r'<body>(.*)</body>', re.DOTALL )
TAG_RE = re.compile( r'<[^>]*>' )
HEADING_CLASS_RE = re.compile( r'(?:^|-)(?:h\d|title|head)(?:-|$)' )
ROMAN_RE = re.compile( r'(I{1,3})([A-Z][a-z]+)' )
STUDY_NOTE_NAME_RE = re.compile( r'(\d?[A-Za-z]+)\.(\d.*)' )
INCLUDED_TYPES = { 'Textboxes':'Textbox', 'Maps':'Map', 'Charts':'Chart', 'Pictures':'Picture' }
REFERENCE_SPAN = 'sn-ref' # The reference at the start of a study note: it repeats the item's own <refs>
PART_VERSE_RE = re.compile( r'(?<=\d)[a-d](?![A-Za-z])' )
BY_BOOK = '*' # In the registry: this type of item goes into one document for each Bible book
LAST = 999 # ‘To the end of the book’, for the first part of a range that crosses into another book

# Tyndale's book abbreviations → the BibleOrgSys codes that we use
BOOKS = { 'Gen':'GEN', 'Exod':'EXO', 'Lev':'LEV', 'Num':'NUM', 'Deut':'DEU', 'Josh':'JOS', 'Jos':'JOS', 'Judg':'JDG', 'Ruth':'RUT',
          '1Sam':'SA1', '2Sam':'SA2', '1Kgs':'KI1', '2Kgs':'KI2', '1Chr':'CH1', '2Chr':'CH2', 'Ezra':'EZR', 'Neh':'NEH', 'Esth':'EST', 'Esther':'EST',
          'Job':'JOB', 'Ps':'PSA', 'Pr':'PRO', 'Eccl':'ECC', 'Song':'SNG', 'Isa':'ISA', 'Jer':'JER', 'Lam':'LAM', 'Ezek':'EZE', 'Dan':'DAN',
          'Hos':'HOS', 'Joel':'JOL', 'Amos':'AMO', 'Obad':'OBA', 'Jon':'JNA', 'Mic':'MIC', 'Nah':'NAH', 'Hab':'HAB', 'Zeph':'ZEP', 'Hagg':'HAG',
          'Zech':'ZEC', 'Mal':'MAL',
          'Matt':'MAT', 'Mt':'MAT', 'Mark':'MRK', 'Luke':'LUK', 'John':'JHN', 'Acts':'ACT', 'Rom':'ROM', '1Cor':'CO1', '2Cor':'CO2', 'Gal':'GAL',
          'Eph':'EPH', 'Phil':'PHP', 'Col':'COL', '1Thes':'TH1', '2Thes':'TH2', '1Tim':'TI1', '2Tim':'TI2', 'Titus':'TIT', 'Phlm':'PHM',
          'Heb':'HEB', 'Jas':'JAM', '1Pet':'PE1', '2Pet':'PE2', '1Jn':'JN1', '2Jn':'JN2', '3Jn':'JN3', 'Jude':'JDE', 'Rev':'REV',
          'Tb':'TOB', 'Jdt':'JDT', 'AddEsth':'ESG', 'Wisd':'WIS', 'Ecclus':'SIR', 'Bar':'BAR', 'Bel':'BEL',
          '1Macc':'MA1', '2Macc':'MA2', '3Macc':'MA3', '4Macc':'MA4', '1Esd':'ES1', '2Esd':'ES2' }


def parse_references( text:str ) -> list:
    """
    Gen.1.1 or Gen.1.3-5 or Gen.1.1-2.3 or 1Chr.8.23,28 or Gen.50.1-Exod.1.7 → [ (BBB, chapter, verse, lastChapter, lastVerse), … ]

    A range that crosses into another book is given as two ranges (and any books in between are left out).
    Raises ValueError for anything else.
    """
    text = usfm.WHITESPACE_RE.sub( '', text ).replace( '–', '-' ).replace( '--', '-' ).replace( ':', '.' )
    text = PART_VERSE_RE.sub( '', text ) # Parts of verses aren't kept, e.g., 16b
    ranges, book, chapter = [], None, None
    def position( fields:list, isEnd:bool ) -> tuple:
        nonlocal book, chapter
        newBook = book
        if len(fields) == 3: newBook = BOOKS[fields.pop( 0 )]
        if newBook is None or len(fields) not in (1,2): raise ValueError( text )
        if len(fields) == 2: chapter = int(fields.pop( 0 ))
        elif newBook != book: raise ValueError( text )
        if newBook != book:
            if isEnd: ranges.append( (book, start[0], start[1], LAST, LAST) )
            book = newBook
        return chapter, int(fields[0])
    try:
        for part in text.split( ',' ):
            first, _hyphen, last = part.partition( '-' )
            start = position( first.split( '.' ), False )
            startBook = book
            end = position( last.split( '.' ), True ) if last else start
            if book != startBook: start = (1, 1)
            if end < start: raise ValueError( text )
            ranges.append( (book,) + start + end )
    except (KeyError, ValueError): raise ValueError( text ) from None
    return ranges


def show_reference( BBB:str, chapter:int, verse:int, lastChapter:int, lastVerse:int ) -> str:
    """ GEN 1:1 or GEN 1:1-2:3 (a range always has the chapter number on both sides) """
    return f'{BBB} {chapter}:{verse}' + ('' if (lastChapter,lastVerse) == (chapter,verse) else f'-{lastChapter}:{lastVerse}')


def book_code( abbreviation:str ) -> str|None:
    """ Gen → GEN and 2Cor or IICor → CO2 (item names have Roman numerals where references have digits) """
    if abbreviation in BOOKS: return BOOKS[abbreviation]
    match = ROMAN_RE.fullmatch( abbreviation )
    return BOOKS.get( str(len(match.group( 1 ))) + match.group( 2 ) ) if match else None


def locate( itemType:str, name:str, documents:dict ) -> tuple|None:
    """ The (document, entry name) for an item, or None if this type of item isn't wanted. """
    document = documents.get( itemType )
    if not document: return None
    if itemType == 'BookIntro': # Named GenIntro where it's defined, but Gen where it's linked to
        return document, book_code( name.removesuffix( 'Intro' ) ) or name
    if document != BY_BOOK: return document, name
    match = STUDY_NOTE_NAME_RE.fullmatch( name ) # e.g., Gen.1.1-2.3 → GEN and 1:1-2:3
    BBB = book_code( match.group( 1 ) ) if match else None
    return (BBB, re.sub( r'(\d+)\.(\d+)', r'\1:\2', match.group( 2 ) )) if BBB else ('Other', name)


def split_items( source:str, documents:dict ) -> list:
    """ [ (document, itemSource), … ] for the wanted items of one source file, in order. (Fast: no XML parsing yet.) """
    found = []
    for match in ITEM_RE.finditer( source ):
        attributes = dict( ITEM_ATTRIBUTE_RE.findall( match.group( 1 ) ) )
        location = locate( attributes.get( 'typename', '' ), attributes.get( 'name', '' ), documents )
        if location: found.append( (location[0], match.group( 0 )) )
    return found


class Parsed:
    """
    The parsed result for one document.

    doc: a usfm.Document (tokens, nodes, paragraphs, warnings)
    entries: list of (start, end, name, type, title)
    anchors: list of (start, end, kind, reference) where kind is ‘about’ or ‘cites’
    links: list of (start, end, kind, target) where kind is ‘see’ or ‘include’ and target is ‘DOCUMENT NAME’
    """
    def __init__( self ) -> None:
        self.doc = usfm.Document()
        self.entries, self.anchors, self.links = [], [], []
        self.bad_references = []
        self.text_differences = []


class _Parser:
    def __init__( self, documents:dict, script:str ) -> None:
        self.parsed = Parsed()
        self.doc = self.parsed.doc
        self.documents, self.script = documents, script
        self.gap = ''
        self.paraName, self.paraStart, self.paraAttributes = None, 0, {}
        self.bodyRanges = []

    def end_paragraph( self ) -> None:
        if self.paraName is None: return
        tokens = self.doc.tokens
        gap = usfm.WHITESPACE_RE.sub( ' ', self.gap ); self.gap = ''
        tokenlessText = ''
        if len(tokens) > self.paraStart: tokens[-1][2] += gap.rstrip()
        else: tokenlessText = gap.strip()
        kind = 'heading' if HEADING_CLASS_RE.search( self.paraName ) else 'body'
        self.doc.paragraphs.append( (self.paraName, kind, self.paraStart, len(tokens), tokenlessText) )
        if len(tokens) > self.paraStart or tokenlessText:
            attributes = {'kind':kind}; attributes.update( self.paraAttributes )
            if tokenlessText: attributes['text'] = tokenlessText
            self.doc.nodes.append( ('para', self.paraStart, len(tokens), self.paraName, attributes) )
            if kind == 'body': self.bodyRanges.append( (self.paraStart, len(tokens)) )
        self.paraName = None

    def start_paragraph( self, name:str, attributes:dict ) -> None:
        self.end_paragraph()
        self.paraName, self.paraStart, self.paraAttributes = name, len(self.doc.tokens), attributes

    def add_text( self, text:str|None ) -> None:
        if not text: return
        if self.paraName is None:
            if not text.strip(): return
            self.doc.warn( 'text outside a paragraph' )
            self.start_paragraph( 'p', {} )
        tokens = self.doc.tokens
        position = 0
        for match in WORD_RE.finditer( text ):
            gap = usfm.WHITESPACE_RE.sub( ' ', self.gap + text[position:match.start()] ); self.gap = ''
            position = match.end()
            if len(tokens) == self.paraStart: before = gap.lstrip()
            else: # The same rules as for USFM: up to the last space belongs to the previous word
                ix = gap.rfind( ' ' )
                if ix == -1: ix = len(gap) - 1
                tokens[-1][2] += gap[:ix+1]
                before = gap[ix+1:]
            tokens.append( [before, match.group(), '', {}] )
        self.gap += text[position:]

    def add_link( self, href:str, start:int, end:int, insideReference:bool ) -> None:
        parsed = self.parsed
        if href.startswith( '?bref=' ):
            if insideReference: return
            try:
                for reference in parse_references( href[6:] ): parsed.anchors.append( (start, end, 'cites', show_reference( *reference )) )
            except ValueError: parsed.bad_references.append( href[6:] )
        elif href.startswith( '?item=' ):
            fields = href[6:].rsplit( '_', 2 ) # NAME_TYPE_PRODUCT
            target = locate( fields[1], fields[0], self.documents ) if len(fields) == 3 else None
            if target: parsed.links.append( (start, end, 'see', ' '.join( target )) )
            else: self.doc.warn( 'link to an item that is not included' )
        elif href.startswith( '#' ): self.doc.warn( 'link within an item (not kept)' )
        else: self.doc.warn( 'unknown kind of link' )

    def walk( self, element, insideReference:bool=False ) -> None:
        tag, className, tokens = element.tag, element.get( 'class', '' ), self.doc.tokens
        if tag == 'p': self.start_paragraph( className or 'p', { 'id':element.get( 'id' ) } if element.get( 'id' ) else {} )
        elif tag == 'include_items': # Another item (e.g., a text box or a map) is displayed here
            folder = element.get( 'src', '' ).split( '/' )[-2:-1]
            target = locate( INCLUDED_TYPES.get( folder[0] if folder else '', '' ), element.get( 'name', '' ), self.documents )
            if target: self.parsed.links.append( (len(tokens), len(tokens), 'include', ' '.join( target )) )
            else: self.doc.warn( 'included item that is not included' )
        start = len(tokens)
        self.add_text( element.text )
        for child in element:
            self.walk( child, insideReference or (tag == 'span' and className.startswith( REFERENCE_SPAN )) )
            self.add_text( child.tail )
        end = len(tokens)
        if tag == 'span':
            if end > start: self.doc.nodes.append( ('span', start, end, className or 'span', {}) )
        elif tag == 'a': self.add_link( element.get( 'href', '' ), start, end, insideReference )
        elif tag == 'p': self.end_paragraph()

    def add_item( self, source:str ) -> None:
        parsed, tokens = self.parsed, self.doc.tokens
        item = ET.fromstring( source )
        _document, name = locate( item.get( 'typename' ), item.get( 'name' ), self.documents )
        start, firstParagraph = len(tokens), len(self.doc.paragraphs)
        body = item.find( 'body' )
        if body is not None: self.walk( body )
        self.end_paragraph()
        self.gap = ''
        title = usfm.WHITESPACE_RE.sub( ' ', item.findtext( 'title' ) or '' ).strip()
        parsed.entries.append( (start, len(tokens), name, item.get( 'typename' ), title) )
        for refs in item.findall( 'refs' ):
            try:
                for reference in parse_references( refs.text or '' ): parsed.anchors.append( (start, len(tokens), 'about', show_reference( *reference )) )
            except ValueError: parsed.bad_references.append( refs.text )

        # Check that tokenising didn't lose or reorder any text, against an independent reduction of the source
        ours = ''.join( tokenlessText + ''.join( before+text+after for before,text,after,_features in tokens[paraStart:paraEnd] )
                            for _name, _kind, paraStart, paraEnd, tokenlessText in self.doc.paragraphs[firstParagraph:] )
        bodyMatch = BODY_RE.search( source )
        theirs = html.unescape( TAG_RE.sub( '', bodyMatch.group( 1 ) ) ) if bodyMatch else ''
        ours, theirs = usfm.WHITESPACE_RE.sub( '', ours ), usfm.WHITESPACE_RE.sub( '', theirs )
        if ours != theirs:
            ix = next( (ix for ix,(a,b) in enumerate( zip( ours, theirs ) ) if a != b), min( len(ours), len(theirs) ) )
            parsed.text_differences.append( { 'entry':name, 'offset':ix, 'ours':ours[max(0,ix-30):ix+30], 'source':theirs[max(0,ix-30):ix+30] } )

    def finish( self ) -> Parsed:
        doc = self.doc
        doc.nodes.extend( usfm.sentence_nodes( doc.tokens, self.bodyRanges, self.script, crossParagraphs=False ) )
        doc.nodes.sort( key=lambda node: (node[1], -node[2], node[0]) )
        return self.parsed


def parse( itemSources:list, documents:dict, script:str='Latn' ) -> Parsed:
    """ Parse the items of one document. documents is the registry's { item type: document } table. """
    parser = _Parser( documents, script )
    for source in itemSources: parser.add_item( source )
    return parser.finish()
