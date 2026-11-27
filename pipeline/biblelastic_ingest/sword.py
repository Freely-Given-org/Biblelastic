"""
Reference works from CrossWire's SWORD library (https://crosswire.org/sword), read straight from a module's zip file:
dictionaries and topical indexes (zLD, e.g., Easton's Bible Dictionary and Nave's Topical Bible), and commentaries (zCom, e.g., the Treasury of Scripture Knowledge).

A zLD dictionary's keys and entries become one document (e.g., `Articles`), with an entry for each key.
A zCom commentary becomes a document for each Bible book, with an entry for each verse that has something (named like `1:1`, and about that verse),
and, for the Treasury of Scripture Knowledge, an entry for each chapter's outline (named like `1`, and about the whole chapter), which SWORD keeps at its first verse.

References in the text become `cites` anchors. They're read from the text that's shown, not from the module's own osisRef attributes,
because some modules' converters gave every reference that's only numbers (e.g., the ‘11’ and ‘21:6’ in ‘Rev. 1:8, 11; 21:6’) to Genesis.
Such a reference takes its book (and chapter, if it hasn't one) from the reference before it, or, in a commentary, from the verse that the entry is about.
"""
import re
import struct
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path

from . import book_codes, items, references, usfm

# The KJV versification's books, in SWORD's order (its commentaries are indexed by verse in this order)
BOOKS = ['GEN','EXO','LEV','NUM','DEU','JOS','JDG','RUT','SA1','SA2','KI1','KI2','CH1','CH2','EZR','NEH','EST','JOB','PSA','PRO','ECC','SNG',
         'ISA','JER','LAM','EZE','DAN','HOS','JOL','AMO','OBA','JNA','MIC','NAH','HAB','ZEP','HAG','ZEC','MAL',
         'MAT','MRK','LUK','JHN','ACT','ROM','CO1','CO2','GAL','EPH','PHP','COL','TH1','TH2','TI1','TI2','TIT','PHM','HEB','JAM',
         'PE1','PE2','JN1','JN2','JN3','JDE','REV']
OLD_TESTAMENT = 39
# The abbreviations that SWORD's older modules use (e.g., the TSK's and Nave's ‘Ge’, ‘Jud’ for Judges, ‘Mr’, ‘Joh’, ‘Re’), as a module's text shows them
ABBREVIATIONS = dict( zip( ['Ge','Ex','Le','Nu','De','Jos','Jud','Ru','1Sa','2Sa','1Ki','2Ki','1Ch','2Ch','Ezr','Ne','Es','Job','Ps','Pr','Ec','So',
                            'Isa','Jer','La','Eze','Da','Ho','Joe','Am','Ob','Jon','Mic','Na','Hab','Zep','Hag','Zec','Mal',
                            'Mt','Mr','Lu','Joh','Ac','Ro','1Co','2Co','Ga','Eph','Php','Col','1Th','2Th','1Ti','2Ti','Tit','Phm','Heb','Jas',
                            '1Pe','2Pe','1Jo','2Jo','3Jo','Jude','Re'], BOOKS ) )
_RANGES = r'\d{1,3}(?::\d{1,3})?(?:\s*[-–]\s*\d{1,3}(?::\d{1,3})?)?'
PART_RE = re.compile( rf'(?:(?P<book>(?:[1-3]\s?)?[A-Z][a-z]+)\.?\s+)?(?P<ranges>{_RANGES}(?:\s*,\s*{_RANGES}(?![A-Za-z]))*)' )
SMALL_WORDS = {'a','an','and','as','at','by','for','from','in','of','on','or','the','to','with'}


def book_code( name:str ) -> str|None:
    """ A book's name or abbreviation as a module's text shows it (e.g., Ge, Joh, 1Ch, Rev., 1 Chr.) → its BOS code, or None """
    name = name.strip().rstrip( '.' )
    return ABBREVIATIONS.get( name.replace( ' ', '' ) ) or references.book_code( name )


def osis_passages( osisRef:str ) -> list:
    """ Bible:Exod.6.16-Exod.6.20 or 1Chr.24 → ['EXO 6:16-6:20'] or ['CH1 24']; [] for anything else (e.g., a range from one book into another) """
    ends = [ end.split( '.' ) for end in osisRef.removeprefix( 'Bible:' ).split( '-' ) ]
    if len(ends) > 2 or any( len(end) not in (2,3) or not all( part.isdigit() for part in end[1:] ) for end in ends ): return []
    BBB = book_codes.osis( ends[0][0] )
    if not BBB or book_codes.osis( ends[-1][0] ) != BBB: return []
    first, last = ends[0][1:], ends[-1][1:]
    if len(first) == 1: return [ f'{BBB} {first[0]}' + ('' if last == first else f'-{last[0]}') ] if int(last[0]) >= int(first[0]) else []
    if len(last) == 1 or tuple( map( int, last ) ) < tuple( map( int, first ) ): return []
    return [ f'{BBB} {first[0]}:{first[1]}' + ('' if last == first else f'-{last[0]}:{last[1]}') ]


class Context:
    """ The book, chapter, and verse that the last reference was in (for references that are only numbers), and the KJV's chapters (to check them) """
    def __init__( self, chapters:dict, BBB:str|None=None, chapter:int|None=None, verse:int|None=None ) -> None:
        self.chapters, self.BBB, self.chapter, self.verse = chapters, BBB, chapter, verse

    def exists( self, passage:str ) -> bool:
        """ Whether a passage's chapters and verses are in the KJV (for one of its books: others aren't checked) """
        BBB, numbers = passage.split( ' ', 1 )
        if BBB not in self.chapters: return True
        counts = self.chapters[BBB]
        for end in numbers.split( '-' ):
            chapter, _colon, verse = end.partition( ':' )
            if not 0 < int(chapter) <= len(counts) or (verse and not 0 < int(verse) <= counts[int(chapter)-1]): return False
        return True

    def passages( self, book:str|None, ranges:str, separator:str='' ) -> list:
        """
        The passages for a reference (a book's name, if it has one, and its numbers), and remember where it ended.
        A reference that's only numbers is in the last one's book: after a comma (or at the start, in a commentary), it's verses, unless it has a chapter,
        and after a semicolon it's chapters (e.g., the 11 in ‘Rev. 1:8, 11’, the ‘27-30’ in ‘Ex. 4:14, 27-30’, and the 24 in ‘1Ch 6:3; 24’).
        """
        if book:
            BBB = book_code( book )
            if not BBB: return []
            passages = references._passages( BBB, ranges )
        elif self.BBB is None: return []
        elif self.verse and (separator != ';' or ':' in ranges):
            BBB = self.BBB
            passages = references._passages( BBB, f'{self.chapter}:{self.verse}, {ranges}' )[1:]
        else:
            BBB = self.BBB
            passages = references._passages( BBB, ranges )
        if not all( self.exists( passage ) for passage in passages ): return []
        if passages:
            numbers = re.findall( r'\d+', passages[-1].split( ' ', 1 )[1].split( '-' )[-1] )
            self.BBB, self.chapter = BBB, int(numbers[0])
            self.verse = int(numbers[1]) if len(numbers) > 1 else None
        return passages


def read_dictionary( archive:zipfile.ZipFile, dataPath:str, encoding:str ) -> list:
    """ A zLD module's entries: [ (key, text), … ] in the module's order (a key that's only a link to another, e.g., @LINK AARON, is left out) """
    read = lambda suffix: archive.read( dataPath + suffix )
    index, keys, blockIndex, blocks = read( '.idx' ), read( '.dat' ), read( '.zdx' ), read( '.zdt' )
    unpacked, entries = {}, []
    for number in range( len(index) // 8 ):
        offset, size = struct.unpack_from( '<II', index, number * 8 )
        record = keys[offset:offset+size]
        key, _newline, rest = record.partition( b'\n' )
        if rest.startswith( b'@LINK' ) or len(rest) < 8: continue
        block, entry = struct.unpack_from( '<II', rest )
        if block not in unpacked:
            blockOffset, blockSize = struct.unpack_from( '<II', blockIndex, block * 8 )
            unpacked[block] = zlib.decompress( blocks[blockOffset:blockOffset+blockSize] )
        entryOffset, entrySize = struct.unpack_from( '<II', unpacked[block], 4 + entry * 8 )
        entries.append( (key.rstrip( b'\r' ).decode( encoding ), unpacked[block][entryOffset:entryOffset+entrySize].rstrip( b'\0' ).decode( encoding )) )
    return entries


def kjv_chapters( versificationPath:Path ) -> dict:
    """ { BBB: [verses in chapter 1, verses in chapter 2, …] } for the KJV, from BibleOrgSys's versification table """
    chapters = {}
    for book in ET.parse( versificationPath ).getroot().iter( 'BibleBookVersification' ):
        chapters[book.findtext( 'referenceAbbreviation' )] = [ int(count.text) for count in book.iter( 'numVerses' ) ]
    return chapters


def read_commentary( archive:zipfile.ZipFile, dataPath:str, encoding:str, chapters:dict ) -> list:
    """
    A zCom module's entries: [ (BBB, chapter, verse, text), … ] for the ones that have text.
    Each testament's index has a slot for the module's heading, the testament's, each book's, each chapter's (verse 0), and each verse, in order.
    """
    entries = []
    for testament, books in (('ot', BOOKS[:OLD_TESTAMENT]), ('nt', BOOKS[OLD_TESTAMENT:])):
        blockIndex, verseIndex, blocks = ( archive.read( f'{dataPath}{testament}.{suffix}' ) for suffix in ('bzs', 'bzv', 'bzz') )
        slots = [ (None, 0, 0), (None, 0, 0) ] + [ slot for BBB in books for slot in
                    [ (BBB, 0, 0) ] + [ (BBB, chapter, verse) for chapter, count in enumerate( chapters[BBB], start=1 ) for verse in range( count + 1 ) ] ]
        if len(slots) * 10 != len(verseIndex): raise ValueError( f'{testament}: {len(verseIndex) // 10} slots in the module, but the KJV has {len(slots)}' )
        unpacked = {}
        for number, (BBB, chapter, verse) in enumerate( slots ):
            block, offset, size = struct.unpack_from( '<IIH', verseIndex, number * 10 )
            if not size: continue
            if block not in unpacked:
                blockOffset, blockSize, _unpackedSize = struct.unpack_from( '<III', blockIndex, block * 12 )
                unpacked[block] = zlib.decompress( blocks[blockOffset:blockOffset+blockSize] )
            text = unpacked[block][offset:offset+size].decode( encoding )
            if text.strip() and BBB: entries.append( (BBB, chapter, verse, text) )
    return entries


def as_xml( text:str ) -> ET.Element:
    """ A module's entry as an element (with any stray ‘<’ and ‘&’ escaped, and the control characters left by an old conversion from DOS removed,
        except the TSK's section signs, which were DOS's character 21) """
    text = re.sub( r'[\x00-\x08\x0b\x0c\x0e-\x14\x16-\x1f\x80-\x9f]', '', text.replace( '\x15', '§' ) )
    text = re.sub( r'&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)', '&amp;', text )
    text = re.sub( r'<(?![/?!]?[A-Za-z])|<(?=[A-Z][a-z]+ )', '&lt;', text ) # e.g., ‘<See’, which isn't a tag
    return ET.fromstring( f'<entry>{text}</entry>' )


def topic_title( key:str ) -> str:
    """ AARON → Aaron, and GOD, LOVE OF → God, Love of (Nave's keys are in capitals) """
    words = re.split( r'(\s+|-)', key.lower() )
    return ''.join( word if (word in SMALL_WORDS and ix) else word[:1].upper() + word[1:] for ix, word in enumerate( words ) )


def entry_name( title:str ) -> str:
    """ An entry's name, from its title (as for Tyndale's: the letters and digits only), e.g., Aaron's Rod → AaronsRod """
    return re.sub( r'\W', '', title ) or 'Untitled'


class SwordParser( items._Parser ):
    def __init__( self, edition:dict, chapters:dict ) -> None:
        super().__init__( {}, edition.get( 'script', 'Latn' ) )
        self.document = edition['sword'].get( 'document', 'Articles' )
        self.chapters = chapters
        self.home = (None, None, None) # The book, chapter, and verse that an entry is about (in a commentary)
        self.context = Context( chapters )
        self.separator = ''
        self.line_style = 'li' if edition['sword'].get( 'topics' ) else 'p' # What a line break (<lb/> or <br/>) starts
        self.lastWasReference = False

    def add_reference( self, text:str, osisRef:str|None, passage:str|None=None ) -> None:
        """ A reference element's text (e.g., ‘Ex 6:16-20’, ‘10’, or ‘Job 26:7; Isa 45:18’): each reference in it is a cites anchor
            (or, where the element says what it is, e.g., passage="Ge 1:3" for the 3 in a TSK chapter's outline, that) """
        if passage and (match := PART_RE.fullmatch( passage.strip() )):
            start = len(self.doc.tokens)
            self.add_text( text )
            passages = Context( self.chapters ).passages( match.group( 'book' ), match.group( 'ranges' ) )
            if not passages: self.parsed.bad_references.append( passage )
            self.parsed.anchors.extend( (start, len(self.doc.tokens), 'cites', found) for found in passages )
            return
        position = 0
        for match in PART_RE.finditer( text ):
            before = text[position:match.start()]
            self.add_text( before )
            separator = before.strip()[-1:] or self.separator
            start = len(self.doc.tokens)
            self.add_text( match.group() )
            passages = self.context.passages( match.group( 'book' ), match.group( 'ranges' ), separator )
            if not passages and osisRef and len(text.strip()) == len(match.group()): # e.g., ‘1 Macc. 1:23’, whose book the text's names don't include
                passages = [ passage for passage in osis_passages( osisRef ) if self.context.exists( passage ) ]
            if not passages: self.parsed.bad_references.append( match.group() )
            self.parsed.anchors.extend( (start, len(self.doc.tokens), 'cites', passage) for passage in passages )
            position, self.separator = match.end(), ''
        self.add_text( text[position:] )

    def add_text( self, text:str|None ) -> None:
        """ (Remembering the last punctuation, which says what a reference that's only numbers is: see Context.passages) """
        super().add_text( text )
        if text and text.strip(): self.separator = text.strip()[-1]

    def walk( self, element, following=None ) -> None:
        """ An element of an entry. A line break starts a paragraph, unless a reference element comes straight after it (in the TSK,
            a word of the verse is on one line, and its references on the next): then they're kept together, with ‘; ’ between references. """
        tag, tokens = element.tag, self.doc.tokens
        if tag in ('lb', 'br'):
            tail = (element.tail or '').lstrip().removeprefix( '→' ) if self.line_style == 'li' else element.tail
            if following is not None and following.tag == 'scripRef' and not (element.tail or '').strip() and len(tokens) > self.paraStart:
                self.add_text( '; ' if self.lastWasReference else ' ' )
            else: self.start_paragraph( self.line_style, {} )
            self.add_text( tail ); self.lastWasReference = False
            return
        if tag in ('p', 'item'): self.start_paragraph( 'li' if tag == 'item' else 'p', {} )
        elif tag == 'title': self.add_text( element.tail ); return # (The entry's title is its first paragraph)
        start = len(tokens)
        if tag in ('ref', 'scripRef') and element.get( 'target' ) is None:
            if tag == 'scripRef': # (In the TSK, each line of references starts again from the verse that the entry is about)
                self.context = Context( self.chapters, *self.home )
            self.add_reference( ''.join( element.itertext() ), element.get( 'osisRef' ), element.get( 'passage' ) )
        else:
            if tag not in ('entry', 'entryFree', 'def', 'p', 'list', 'item', 'ref', 'hi', 'sync', 'orth', 'sense', 'foreign'): self.doc.warn( f'unknown element <{tag}>' )
            self.add_text( element.text )
            for ix, child in enumerate( element ): self.walk( child, element[ix+1] if ix + 1 < len(element) else None )
        end = len(tokens)
        if tag == 'ref' and element.get( 'target', '' ).count( ':' ) == 1 and end > start: # e.g., target="Nave:CHILDREN"
            self.parsed.links.append( (start, end, 'see', f"{self.document} {entry_name( topic_title( element.get( 'target' ).split( ':' )[1] ) )}") )
        elif tag == 'hi' and end > start: self.doc.nodes.append( ('span', start, end, element.get( 'type', 'hi' ), {}) )
        if tag in ('p', 'item'): self.end_paragraph()
        self.lastWasReference = tag == 'scripRef'
        self.add_text( element.tail )
        if (element.tail or '').strip(): self.lastWasReference = False

    def add_entry( self, name:str, entryType:str, title:str, root:ET.Element, about:list, heading:str='' ) -> None:
        """ One entry (with its heading, if it has one, as an h1 paragraph), and check that tokenising didn't lose or reorder any of its text """
        tokens, start, firstParagraph = self.doc.tokens, len(self.doc.tokens), len(self.doc.paragraphs)
        if heading:
            self.start_paragraph( 'h1', {} ); self.add_text( heading ); self.end_paragraph()
        self.start_paragraph( self.line_style, {} )
        self.lastWasReference, self.separator = False, ''
        self.walk( root )
        self.end_paragraph()
        self.gap = ''
        self.parsed.entries.append( (start, len(tokens), name, entryType, title) )
        self.parsed.anchors.extend( (start, len(tokens), 'about', passage) for passage in about )
        # (Whitespace, the arrows that start Nave's lines, and the semicolons put between the TSK's lines of references, aside)
        ours = ''.join( tokenlessText + ''.join( before+text+after for before,text,after,_features in tokens[paraStart:paraEnd] )
                        for _name, _kind, paraStart, paraEnd, tokenlessText in self.doc.paragraphs[firstParagraph:] )
        theirs = heading + ''.join( _shown_text( root ) )
        reduce = lambda text: re.sub( r'[\s→;]', '', text )
        ours, theirs = reduce( ours ), reduce( theirs )
        if ours != theirs:
            ix = next( (ix for ix,(a,b) in enumerate( zip( ours, theirs ) ) if a != b), min( len(ours), len(theirs) ) )
            self.parsed.text_differences.append( { 'entry':name, 'offset':ix, 'ours':ours[max(0,ix-30):ix+30], 'source':theirs[max(0,ix-30):ix+30] } )


def _shown_text( element:ET.Element, top:bool=True ) -> list:
    """ The text of an entry as it's shown: all of it but its <title> (whose text is the entry's heading instead) """
    parts = [] if element.tag == 'title' else [ element.text or '' ]
    for child in element: parts += _shown_text( child, False )
    if not top: parts.append( element.tail or '' )
    return parts


def parse( edition:dict, path:Path, versificationPath:Path ) -> dict:
    """ { document: (parsed items, [source name]) } for a SWORD module's zip file """
    settings = edition['sword']
    with zipfile.ZipFile( path ) as archive:
        confName = next( name for name in archive.namelist() if name.startswith( 'mods.d/' ) and name.endswith( '.conf' ) )
        conf = dict( line.split( '=', 1 ) for line in archive.read( confName ).decode( 'utf-8', 'replace' ).replace( '\r', '' ).splitlines() if '=' in line and not line.startswith( '#' ) )
        encoding = 'utf-8' if conf.get( 'Encoding', '' ).upper() == 'UTF-8' else 'latin-1'
        dataPath = conf['DataPath'].removeprefix( './' )
        driver = conf['ModDrv'].lower()
        chapters = { BBB:counts for BBB, counts in kjv_chapters( versificationPath ).items() if BBB in BOOKS }
        if driver == 'zld': return { settings['document']: parse_dictionary( edition, read_dictionary( archive, dataPath, encoding ), chapters, path.name ) }
        if driver == 'zcom':
            return parse_commentary( edition, read_commentary( archive, dataPath, encoding, chapters ), chapters, path.name )
        raise ValueError( f"{edition['id']}: SWORD's {conf['ModDrv']} modules can't be read yet" )


def parse_dictionary( edition:dict, entries:list, chapters:dict, sourceName:str ) -> tuple:
    parser = SwordParser( edition, chapters )
    names = set()
    for key, text in entries:
        root = as_xml( text )
        title = usfm.WHITESPACE_RE.sub( ' ', root.findtext( './/title' ) or '' ).strip() or (topic_title( key ) if edition['sword'].get( 'topics' ) else key.title())
        name = entry_name( title )
        while name in names: name += '_'
        names.add( name )
        parser.context = Context( chapters )
        parser.add_entry( name, 'Topic' if edition['sword'].get( 'topics' ) else 'Article', title, root, [], heading=title )
    # A link to a name that isn't an entry's goes to the nearest that is: its singular or plural, or else the first entry whose name starts with it
    # (e.g., Nave's ‘See ANGEL’, which is ‘Angel (a Spirit)’, and Easton's ‘Pilate’, which is ‘Pilate, Pontius’)
    document, ordered = edition['sword']['document'], [ entry[2] for entry in parser.parsed.entries ]
    known = { name.casefold():name for name in ordered }
    def nearest( name:str ) -> str|None:
        folded = name.casefold()
        forms = [ folded, folded + 's', folded + 'es', folded[:-1], folded[:-2], folded[:-3] + 'y' if folded.endswith( 'ies' ) else '', folded[:-1] + 'ies' if folded.endswith( 'y' ) else '' ]
        for form in forms:
            if form and form in known: return known[form]
        for form in forms:
            if len(form) > 2 and (found := next( (other for other in ordered if other.casefold().startswith( form )), None )): return found
        return None
    for ix, (start, end, kind, target) in enumerate( parser.parsed.links ):
        name = target.split( ' ', 1 )[1]
        if name.casefold() not in known and (found := nearest( name )): parser.parsed.links[ix] = (start, end, kind, f'{document} {found}')
    return parser.finish(), [sourceName]


def parse_commentary( edition:dict, entries:list, chapters:dict, sourceName:str ) -> dict:
    """ One document for each book. The TSK keeps a chapter's outline at its first verse, before a blank line: that becomes an entry of its own. """
    parsers = {}
    for BBB, chapter, verse, text in entries:
        if BBB not in parsers: parsers[BBB] = SwordParser( edition, chapters )
        parser = parsers[BBB]
        parts = [ (f'{chapter}', 'Outline', [f'{BBB} {chapter}:1-{chapter}:{chapters[BBB][chapter-1]}'], outline) for outline in [text.split( '\n<br />\n<br />', 1 )[0]]
                    if verse == 1 and '\n<br />\n<br />' in text and text.lstrip().startswith( '<br /><scripRef passage=' ) ]
        rest = text.split( '\n<br />\n<br />', 1 )[1] if parts else text
        if verse: parts.append( (f'{chapter}:{verse}', 'CrossReferences', [f'{BBB} {chapter}:{verse}'], rest) )
        else: parts.append( (f'{chapter}:0' if chapter else 'Intro', 'Introduction', [f'{BBB} {chapter}' if chapter else f'{BBB} 1-{len(chapters[BBB])}'], rest) )
        for name, entryType, about, part in parts:
            if not re.sub( r'<[^>]*>', '', part ).strip(): continue
            root = as_xml( part )
            parser.home = (BBB, chapter or None, verse or None)
            parser.context = Context( chapters, *parser.home )
            parser.add_entry( name, entryType, '', root, about )
    return { BBB: (parser.finish(), [sourceName]) for BBB, parser in parsers.items() }
