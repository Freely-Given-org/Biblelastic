"""
The open-licensed United Bible Societies resources (https://github.com/ubsicap/ubs-open-license), as adapted for the OET.

- The UBS Hebrew and Greek dictionaries list each meaning of each word, and every place where the word has that meaning.
  Those places are joined to the words of an original-language edition, giving a layer with each word's meaning *there*.
- The handbooks on animals, plants, and objects (fauna, flora, realia) become a work of their own (like a dictionary),
  and each word that a handbook article is about gets a link to the article in the same layer.

A UBS reference is 14 digits: book (3, from 1 = Genesis to 66 = Revelation), chapter (3), verse (3), and position (5).
Positions count each part of a Hebrew word (e.g., a prefix) separately, in steps of two, and the verse numbers are the UBS text's own,
which for the Old Testament are the Hebrew ones (e.g., Malachi 3:19 for the English 4:1).
So references aren't joined to words by their numbers, but by aligning each book's words in order,
on Strong's number (Hebrew) or lemma (Greek).
"""
import json
import re
import unicodedata
import xml.etree.ElementTree as ET

from . import items, usfm

BOOKS = ['GEN','EXO','LEV','NUM','DEU','JOS','JDG','RUT','SA1','SA2','KI1','KI2','CH1','CH2','EZR','NEH','EST','JOB','PSA','PRO','ECC','SNG',
         'ISA','JER','LAM','EZE','DAN','HOS','JOL','AMO','OBA','JNA','MIC','NAH','HAB','ZEP','HAG','ZEC','MAL',
         'MAT','MRK','LUK','JHN','ACT','ROM','CO1','CO2','GAL','EPH','PHP','COL','TH1','TH2','TI1','TI2','TIT','PHM','HEB','JAM',
         'PE1','PE2','JN1','JN2','JN3','JDE','REV']
ABBREVIATIONS = {} # BBB → a short name for showing references in the handbooks' text, e.g., Lev
for _abbreviation, _BBB in items.BOOKS.items(): ABBREVIATIONS.setdefault( _BBB, _abbreviation )
LAYER_COLUMNS = ['meaning_gloss', 'meaning_definition', 'meaning_note', 'meaning_code', 'domains', 'handbook']
REFERENCE_RE = re.compile( r'[A-Z]?(\d{3})(\d{3})(\d{3})(\d{5})' )


def reference_parts( reference:str ) -> tuple|None:
    """ 01905001300008 → ('PSA', 50, 13, 8). (A letter in front, as in G05800901300020, is ignored.) None for anything else. """
    match = REFERENCE_RE.fullmatch( reference.strip() )
    if not match or not 1 <= int(match.group( 1 )) <= len(BOOKS): return None
    return BOOKS[int(match.group( 1 )) - 1], int(match.group( 2 )), int(match.group( 3 )), int(match.group( 4 ))


def show_references( text:str ) -> str:
    """ The text of a handbook's <s> element: references, ranges (a-b), and lists (separated by spaces) → e.g., ‘Lev 11:13-19; Heb 9:13’ """
    shown = []
    for part in text.split():
        ends = [ reference_parts( end ) for end in part.split( '-' ) ]
        if not ends or None in ends or len(ends) > 2: shown.append( part ); continue
        (BBB, chapter, verse, _), last = ends[0], ends[-1]
        place = f'{ABBREVIATIONS.get( BBB, BBB )} {chapter}' + (f':{verse}' if verse else '')
        if last != ends[0]:
            place += f'-{last[2]}' if last[1] == chapter else f'–{last[1]}:{last[2]}'
        shown.append( place )
    return '; '.join( shown )


def clean( text:str|None ) -> str:
    """ A definition or comment as plain text: links to other words become just the words, references are shown readably,
        and notes' markers are dropped. (Semicolons become commas, because the layer uses them between values.) """
    text = text or ''
    text = re.sub( r'\{L:([^<}]*)(?:<[^>]*>)?\}(?:\[[a-z]\])?', r'\1', text ) # A link to another word
    text = re.sub( r'\{S:([^}]*)\}', lambda match: show_references( match.group( 1 ) ), text ) # A reference
    text = re.sub( r'\{D:([^}]*)\}', r'§\1', text ) # A Louw-Nida domain number
    text = re.sub( r'\{A:([^}]*)\}', r'\1', text ) # An abbreviation for a source
    text = re.sub( r'\{N:[^}]*\}|\[[a-z]\]', '', text )
    return usfm.WHITESPACE_RE.sub( ' ', text.replace( ';', ',' ) ).strip()


def strong_number( code:str ) -> str:
    """ H1254a, b:H1254, G07460 → the number alone: 1254 or 746 (UHB and SR-GNT write them differently from the UBS dictionaries) """
    match = re.search( r'(\d+)', code.rsplit( ':', 1 )[-1] )
    if not match: return ''
    number = int(match.group( 1 ))
    return str( number // 10 if code.startswith( 'G' ) and len(match.group( 1 )) == 5 else number ) # SR-GNT adds a digit: G07460 is 746


def nfc( text:str ) -> str: return unicodedata.normalize( 'NFC', text )


def load_dictionary( path:str, greek:bool ) -> tuple:
    """
    Returns (meanings, references):
        meanings: { meaning id: [gloss, definition, note, code, domains] } (domains separated by semicolons).
            The ids start with H or G, because the two dictionaries number their meanings in the same way.
        references: { BBB: [ (chapter, verse, position, reference, keys, meaning id), … ] } in order, where keys is what a word must have to match:
            its lemma (Greek) or one of its Strong's numbers (Hebrew)
    """
    meanings, references = {}, {}
    with open( path, encoding='utf-8' ) as dictionaryFile: entries = json.load( dictionaryFile )
    for entry in entries:
        keys = { nfc( entry['Lemma'] ) } if greek else { strong_number( code ) for code in entry['StrongCodes'] } - {''}
        for baseForm in entry.get( 'BaseForms' ) or []:
            for meaning in baseForm.get( 'LEXMeanings' ) or []:
                senses = [ sense for sense in meaning.get( 'LEXSenses' ) or [] if sense.get( 'LanguageCode' ) == 'en' ]
                sense = senses[0] if senses else {}
                domains = [ (f"{domain['DomainSource']} > " if domain.get( 'DomainSource' ) else '') + domain['Domain'] for domain in meaning.get( 'LEXDomains' ) or [] if domain.get( 'Domain' ) ]
                main = (meaning.get( 'LEXDomains' ) or [{}])[0].get( 'Domain', '' )
                domains += [ f"{main} > {domain['Domain']}" if main else domain['Domain'] for domain in meaning.get( 'LEXSubDomains' ) or [] if domain.get( 'Domain' ) ]
                meaningId = ('G' if greek else 'H') + meaning['LEXID']
                meanings[meaningId] = [ clean( ', '.join( sense.get( 'Glosses' ) or [] ) ), clean( re.sub( r'^=\s*', '', sense.get( 'DefinitionShort' ) or '' ) ),
                                               clean( sense.get( 'Comments' ) ), meaning.get( 'LEXEntryCode' ) or '', ';'.join( dict.fromkeys( clean( domain ) for domain in domains ) ) ]
                for reference in meaning.get( 'LEXReferences' ) or []:
                    parts = reference_parts( reference[:14] )
                    if parts and keys: references.setdefault( parts[0], [] ).append( (parts[1], parts[2], parts[3], reference[:14], keys, meaningId) )
    for bookReferences in references.values(): bookReferences.sort( key=lambda reference: reference[:3] )
    return meanings, references


def align( words:list, references:list, window:int=20 ) -> list:
    """
    Pair up words (each a key) with references (each a set of keys) in order: [(word index, reference index), …].

    Greedy, resynchronising with a look-ahead after a word or reference that has no partner
    (e.g., a Hebrew prefix, which UBS counts as a word of its own, or a word that the dictionary doesn't cover yet).
    """
    pairs, i, j = [], 0, 0
    same = lambda i, j: words[i] in references[j]
    while i < len(words) and j < len(references):
        if same( i, j ): pairs.append( (i, j) ); i += 1; j += 1; continue
        found = None
        for distance in range( 1, window + 1 ):
            for di in range( distance + 1 ):
                dj = distance - di
                if i+di < len(words) and j+dj < len(references) and same( i+di, j+dj ) \
                and (i+di+1 >= len(words) or j+dj+1 >= len(references) or same( i+di+1, j+dj+1 )):
                    found = (di, dj); break
            if found: break
        if found: i += found[0]; j += found[1]
        else: i += 1; j += 1
    return pairs


def link_book( tokens:list, header:list, bookReferences:list, greek:bool ) -> dict:
    """ { reference: token index } for one book of an edition (tokens are its rows, with lemma and strong columns) """
    lemmaColumn, strongColumn = header.index( 'lemma' ), header.index( 'strong' )
    indexes = [ ix for ix, token in enumerate( tokens ) if token[lemmaColumn] ]
    words = [ nfc( tokens[ix][lemmaColumn] ) if greek else strong_number( tokens[ix][strongColumn] ) for ix in indexes ]
    return { bookReferences[j][3]:indexes[i] for i, j in align( words, [ reference[4] for reference in bookReferences ] ) }


class HandbookParser( items._Parser ):
    """ The UBS ‘thematic lexicon’ XML of a handbook: each ThemLex_Entry becomes an entry """
    def __init__( self, document:str, place_of ) -> None:
        super().__init__( {}, 'Latn' )
        self.document = document
        self.place_of = place_of # reference → (BBB, chapter, verse) in the edition's own numbering, or None
        self.word_links = [] # (reference, entry name): the words that an entry is about
        self.current = None # The paragraph being read (its tail isn't part of it)

    def place( self, reference:str ) -> tuple|None:
        """ Where a reference is: (BBB, chapter, verse) in the edition's own numbering if its word is known, else as UBS numbers it """
        parts = reference_parts( reference )
        return (self.place_of( reference ) or parts[:3]) if parts else None

    def inline( self, element ) -> None:
        """ The contents of a paragraph (or heading): text, styles, references, and links to other entries """
        tokens = self.doc.tokens
        start = len(tokens)
        if element.tag == 's': # References: shown readably, and anchored
            self.add_text( show_references( element.text or '' ) )
            for part in (element.text or '').split():
                ends = [ self.place( end ) for end in part.split( '-' ) ]
                if None in ends or len(ends) > 2: continue
                (BBB, chapter, verse), (lastBBB, lastChapter, lastVerse) = ends[0], ends[-1]
                if lastBBB != BBB or not verse: continue
                if not lastVerse or (lastChapter, lastVerse) < (chapter, verse): lastChapter, lastVerse = chapter, verse
                passage = f'{BBB} {chapter}:{verse}' + ('' if (lastChapter, lastVerse) == (chapter, verse) else f'-{lastChapter}:{lastVerse}')
                self.parsed.anchors.append( (start, len(tokens), 'cites', passage) )
            self.add_text( element.tail )
            return
        self.add_text( element.text )
        for child in element: self.inline( child )
        end = len(tokens)
        style = { 'i':'ital', 'b':'bold', 'u':'underline', 'sup':'sup' }.get( element.tag )
        if style and end > start: self.doc.nodes.append( ('span', start, end, style, {}) )
        elif element.tag == 'l':
            target = element.get( 'target', '' )
            if ':' in target:
                book, name = target.split( ':', 1 )
                self.parsed.links.append( (start, end, 'see', f'{book.capitalize()} {name}') )
        if element is not self.current: self.add_text( element.tail )

    def paragraph( self, style:str, element ) -> None:
        if element is None: return
        self.start_paragraph( style, {} )
        self.current = element
        self.inline( element )
        self.end_paragraph()

    def add_entry( self, entry ) -> None:
        tokens = self.doc.tokens
        start, name = len(tokens), entry.get( 'Key' )
        title = usfm.WHITESPACE_RE.sub( ' ', entry.findtext( 'Title' ) or '' ).strip()
        self.paragraph( 'h1', entry.find( 'Title' ) )
        for item in entry.iter( 'IndexItem' ): # Contents
            link = item.find( 'l' )
            if link is not None: self.paragraph( 'toc', link )
        for section in entry.iter( 'Section' ):
            heading = section.find( 'Heading' )
            if heading is not None and ''.join( heading.itertext() ).strip() and section.get( 'Content' ) != 'references': self.paragraph( 'h2', heading )
            subheading = section.find( 'SubHeading' )
            if subheading is not None and ''.join( subheading.itertext() ).strip(): self.paragraph( 'h3', subheading )
            for languageSet in section.iter( 'LanguageSet' ): # The words that the entry is about, in Hebrew or Greek
                lemma, transliteration = (languageSet.findtext( 'Lemma' ) or '').strip(), (languageSet.findtext( 'Transliteration' ) or '').strip()
                references = [ reference.text.strip() for reference in languageSet.iter( 'Reference' ) if reference.text ]
                self.word_links.extend( (reference, name) for reference in references )
                if lemma:
                    self.start_paragraph( 'lemma', {} )
                    self.add_text( f"{languageSet.get( 'Language', '' )}: {lemma}" + (f' ({transliteration})' if transliteration else '') + f" — {len(references)} reference{'' if len(references) == 1 else 's'}" )
                    self.end_paragraph()
            for paragraph in section.iter( 'Paragraph' ): self.paragraph( 'p', paragraph )
            for image in section.iter( 'BibleImage' ): # Only the captions: the pictures themselves aren't included yet
                caption, copyright = (image.findtext( 'Caption' ) or '').strip(), (image.findtext( 'Copyright' ) or '').strip()
                if caption:
                    self.start_paragraph( 'caption', {} )
                    self.add_text( f'Picture: {caption}' + (f' ({copyright})' if copyright else '') )
                    self.end_paragraph()
        self.gap = ''
        if len(tokens) > start: self.parsed.entries.append( (start, len(tokens), name, 'Article', title) )


def parse_handbook( path:str, document:str, place_of ) -> tuple:
    """ Returns (parsed items, word links) for one handbook file """
    parser = HandbookParser( document, place_of )
    for entry in ET.parse( path ).getroot().iter( 'ThemLex_Entry' ): parser.add_entry( entry )
    return parser.finish(), parser.word_links
