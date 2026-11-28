"""
Reference works from CrossWire's SWORD library (https://crosswire.org/sword), read straight from a module's zip file:
dictionaries and topical indexes (zLD and RawLD, e.g., Easton's Bible Dictionary and Nave's Topical Bible), commentaries (zCom and zCom4,
e.g., the Treasury of Scripture Knowledge and Matthew Henry's Concise Commentary), and general books (RawGenBook, e.g., Josephus's works and Owen's: see parse_genbook).

A dictionary's keys and entries become one document (e.g., `Articles`), with an entry for each key.
A commentary becomes a document for each Bible book, with an entry for each note (named like `1:1`, or `3:1-8` for a note on several verses, and about those verses),
an entry for each chapter's outline (named like `1`, and about the whole chapter), which SWORD keeps at the chapter's first verse,
and one for the book's introduction (`Intro`), which SWORD keeps at its first verse.

References in the text become `cites` anchors. They're read from the text that's shown, not from the module's own osisRef attributes,
because some modules' converters gave every reference that's only numbers (e.g., the ‘11’ and ‘21:6’ in ‘Rev. 1:8, 11; 21:6’) to Genesis.
Such a reference takes its book (and chapter, if it hasn't one) from the reference before it, or, in a commentary, from the verse that the entry is about.
"""
import collections
import fnmatch
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
# Other abbreviations, in Adam Clarke's (‘Sol’, ‘Zac’, ‘Phi’ for Philippians, ‘Plm’ for Philemon), Jamieson, Fausset, and Brown's (‘Jr’), Daily Light's (‘He’, ‘Ph’),
# Wesley's (‘Numb’, ‘Psal’), Spurgeon's (the ‘Solomon’ of ‘Song of Solomon 1:4’), and Barnes's, whose converter doubled some letters (‘1Timm’, ‘Romm’, ‘Gall’, ‘Hoss’)
ABBREVIATIONS |= { 'Sol':'SNG', 'Zac':'ZEC', 'Phi':'PHP', 'Plm':'PHM', 'Amo':'AMO', 'Jde':'JDE', 'Rut':'RUT', 'Oba':'OBA', 'Jr':'JER',
                   'He':'HEB', 'Ph':'PHP', 'Je':'JER', 'Mi':'MIC', '1Joh':'JN1', '2Joh':'JN2', '3Joh':'JN3', 'Mk':'MRK', 'Lk':'LUK', 'Jn':'JHN', '1Jn':'JN1', '2Jn':'JN2', '3Jn':'JN3', 'Ep':'EPH',
                   'Numb':'NUM', 'Psal':'PSA', 'Levit':'LEV', 'Isai':'ISA', '1Kin':'KI1', '2Kin':'KI2', 'Solomon':'SNG',
                   '1Timm':'TI1', '2Timm':'TI2', 'Romm':'ROM', 'Gall':'GAL', 'Hoss':'HOS', 'Lkke':'LUK', 'Jnn':'JHN', 'Nehh':'NEH', 'Revv':'REV', 'Levv':'LEV', 'Genn':'GEN',
                   'Nahh':'NAH', 'Provo':'PRO', 'Actst':'ACT', 'Actsts':'ACT' }
_RANGES = r'\d{1,3}(?::\d{1,3})?(?:\s*[-–]\s*\d{1,3}(?::\d{1,3})?)?'
PART_RE = re.compile( rf'(?:(?P<book>(?:[1-3]\s?)?[A-Z][a-z]+)\.?\s+)?(?P<ranges>{_RANGES}(?:\s*,\s*{_RANGES}(?![A-Za-z]))*)' )
SMALL_WORDS = {'a','an','and','as','at','by','for','from','in','of','on','or','the','to','with'}
# What starts a line of a topic, and isn't kept: Nave's arrows, and Torrey's ‘- ’ (and ‘. ’ for a line under another)
LINE_MARK_RE = re.compile( r'^\s*(?:→|[-.](?=\s))\s*' )
# What an OSIS commentary (e.g., Matthew Henry's) has before a verse's note: the book's introduction, the chapter's outline, or a section's title
PREVERSE_RE = re.compile( r'<div type="x-milestone" subType="x-preverse" sID="[^"]*"/>(.*?)<div type="x-milestone" subType="x-preverse" eID="[^"]*"/>', re.S )
# How each of Matthew Henry's and Adam Clarke's notes starts (what's before it in a chapter's first verse is the chapter's title and outline), and their chapters' titles
NOTE_START_RE = re.compile( r'<hi type="bold">Verses? \d' )
CHAPTER_TITLE_RE = re.compile( r'<title type="x-s2">(?!PREFACE<)|<title type="x-s">Introduction</title>' ) # (Not the preface to Matthew Henry's volumes, at Genesis, Joshua, and Acts)
PREFACE_RE = re.compile( r'<title type="x-s">Preface' ) # (Adam Clarke's book's preface, at its first note, which runs on into its first chapter's outline)
# Where a book's introduction is in its first note (`sword.intros = "first-note"`, e.g., Keil and Delitzsch's): its titles, a title that names a passage
#   (‘The Creation of the World - Genesis 1:1-2:3’, ‘SUPERSCRIPTION AND MOTTO, 1. 1-7.’, ‘FIRST BOOK OF THE PSALTER Ps. I.-XLI.’), and a paragraph that starts with a verse's reference (‘Jdg 1:1-2’)
TITLE_RE = re.compile( r'<title\b[^>]*>(.*?)</title>', re.S )
PASSAGE_TITLE_RE = re.compile( r'\d+\s*[-–:.]\s*\d+|\s[-–]\s+(?:[1-3]\s?)?[A-Z][a-z]+\.?\s+\d|\b[IVXL]+\.\s*[-–]\s*[IVXL]+\.' )
VERSE_HEADING_RE = re.compile( r'<div sID="[^"]*" type="x-p"/>\s*(?:<reference osisRef="[^"]*">[^<]*</reference>\s*<div eID="[^"]*" type="x-p"/>|(?:[1-3] ?)?[A-Z][a-z]{1,4}\.? \d+:\d+\b)' )
SPANS = { 'hi':None, 'i':'italic', 'b':'bold', 'em':'italic', 'strong':'bold' }
# What starts a paragraph (of this kind), and the other elements that are known (whose text is kept), in OSIS, ThML (whose HTML elements, e.g., Finney's <h2>), and TEI
BLOCKS = { 'p':'p', 'item':'li', 'li':'li', 'row':'li', 'tr':'li', 'title':'h2', 'h1':'h2', 'h2':'h2', 'h3':'h3', 'h4':'h4', 'h5':'h4', 'h6':'h4', 'l':'p', 'note':'note' }
INLINE = { 'entry', 'entryFree', 'def', 'list', 'ref', 'sync', 'orth', 'sense', 'foreign', 'table', 'cell', 'td', 'th', 'div', 'term', 'ol', 'ul', 'w', 'seg',
           'blockquote', 'lg', 'verse', 'font', 'small', 'sup', 'sub', 'a', 'span', 'label', 'inscription', 'hr' }
OSIS_PASSAGE_RE = re.compile( r'(?:[1-3]?[A-Z][A-Za-z]+\.\d+(?:\.\d+)?(?:-[1-3]?[A-Z][A-Za-z]+\.\d+(?:\.\d+)?)?\s*)+' )


def book_code( name:str ) -> str|None:
    """ A book's name or abbreviation as a module's text shows it (e.g., Ge, Joh, 1Ch, Rev., 1 Chr.) → its BOS code, or None """
    name = name.replace( '\xa0', ' ' ).strip().rstrip( '.' ) # (Smith's has ‘1\xa0Chronicles’)
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


def read_raw_dictionary( archive:zipfile.ZipFile, dataPath:str, encoding:str ) -> list:
    """ A RawLD module's entries: [ (key, text), … ] (Its index has a 4-byte offset and a 2-byte size for each entry, and each entry is its key, a line break, and its text) """
    index, records = archive.read( dataPath + '.idx' ), archive.read( dataPath + '.dat' )
    entries = []
    for number in range( len(index) // 6 ):
        offset, size = struct.unpack_from( '<IH', index, number * 6 )
        key, _newline, text = records[offset:offset+size].partition( b'\n' )
        if text.startswith( b'@LINK' ) or not text.strip(): continue
        entries.append( (key.rstrip( b'\r' ).decode( encoding ), text.rstrip( b'\0' ).decode( encoding )) )
    return entries


def read_genbook( archive:zipfile.ZipFile, dataPath:str, encoding:str ) -> tuple:
    """
    A RawGenBook module's tree of keys: (name, text, [children]) for its root.
    Its .idx has a 4-byte offset in .dat for each node; a node there is its parent's, next sibling's, and first child's numbers (each × 4, or -1),
    its name (ending with a 0), and its data's size (2 bytes) and data: the offset and size of its text in .bdt.
    """
    index, nodes, texts = ( archive.read( dataPath + suffix ) for suffix in ('.idx', '.dat', '.bdt') )
    def node( number:int ) -> tuple:
        offset, = struct.unpack_from( '<I', index, number * 4 )
        _parent, _next, child = struct.unpack_from( '<iii', nodes, offset )
        end = nodes.index( b'\0', offset + 12 )
        size, = struct.unpack_from( '<H', nodes, end + 1 )
        textOffset, textSize = struct.unpack_from( '<II', nodes, end + 3 ) if size >= 8 else (0, 0)
        children = []
        while child >= 0:
            children.append( node( child // 4 ) )
            child = struct.unpack_from( '<iii', nodes, struct.unpack_from( '<I', index, child )[0] )[1]
        return nodes[offset+12:end].decode( encoding ), texts[textOffset:textOffset+textSize].decode( encoding, 'replace' ), children
    return node( 0 )


def kjv_chapters( versificationPath:Path ) -> dict:
    """ { BBB: [verses in chapter 1, verses in chapter 2, …] } for the KJV, from BibleOrgSys's versification table """
    chapters = {}
    for book in ET.parse( versificationPath ).getroot().iter( 'BibleBookVersification' ):
        chapters[book.findtext( 'referenceAbbreviation' )] = [ int(count.text) for count in book.iter( 'numVerses' ) ]
    return chapters


def read_commentary( archive:zipfile.ZipFile, dataPath:str, encoding:str, chapters:dict, width:int=10, blockType:str='b' ) -> list:
    """
    A zCom module's entries: [ (BBB, chapter, verse, last verse, text), … ] for the ones that have text.
    Each testament's index has a slot for the module's heading, the testament's, each book's, each chapter's (verse 0), and each verse, in order:
    each slot is a block number, an offset in that block, and a size (of 2 bytes, or of 4 in a zCom4 module, whose slots are 12 bytes wide).
    A note on several verses is linked to each of them (their slots are the same), so it's one entry, from its first verse to its last.
    The files' names start with the module's block type (e.g., nt.bzv for blocks of a book, nt.czv for blocks of a chapter), and a module of one testament has only its files.
    """
    entries, last = [], None
    for testament, books in (('ot', BOOKS[:OLD_TESTAMENT]), ('nt', BOOKS[OLD_TESTAMENT:])):
        if f'{dataPath}{testament}.{blockType}zv' not in archive.namelist(): continue
        blockIndex, verseIndex, blocks = ( archive.read( f'{dataPath}{testament}.{blockType}{suffix}' ) for suffix in ('zs', 'zv', 'zz') )
        slots = [ (None, 0, 0), (None, 0, 0) ] + [ slot for BBB in books for slot in
                    [ (BBB, 0, 0) ] + [ (BBB, chapter, verse) for chapter, count in enumerate( chapters[BBB], start=1 ) for verse in range( count + 1 ) ] ]
        if len(slots) * width != len(verseIndex): raise ValueError( f'{testament}: {len(verseIndex) // width} slots in the module, but the KJV has {len(slots)}' )
        unpacked = {}
        for number, (BBB, chapter, verse) in enumerate( slots ):
            block, offset, size = struct.unpack_from( '<IIH' if width == 10 else '<III', verseIndex, number * width )
            if not size: continue
            if (block, offset, size) == last and verse and entries and entries[-1][:2] == (BBB, chapter) and entries[-1][3] == verse - 1:
                entries[-1] = entries[-1][:3] + (verse, entries[-1][4]); continue # (The same note as the verse before's)
            last = (block, offset, size)
            if block not in unpacked:
                blockOffset, blockSize, _unpackedSize = struct.unpack_from( '<III', blockIndex, block * 12 )
                unpacked[block] = zlib.decompress( blocks[blockOffset:blockOffset+blockSize] )
            text = unpacked[block][offset:offset+size].decode( encoding, 'replace' ) # (Barnes's has a few bytes that aren't UTF-8, e.g., a degree sign)
            if text.strip() and BBB: entries.append( (BBB, chapter, verse, verse, text) )
    return entries


def as_xml( text:str ) -> ET.Element:
    """ A module's entry as an element (with any stray ‘<’ and ‘&’ escaped, and the control characters left by an old conversion from DOS removed,
        except the TSK's section signs, which were DOS's character 21, and with a tag's name that's broken by a new line joined, e.g., the Westminster catechism's ‘<referen⏎ce’) """
    text = re.sub( r'[\x00-\x08\x0b\x0c\x0e-\x14\x16-\x1f\x80-\x9f]', '', text.replace( '\x15', '§' ) )
    text = re.sub( r'(<[A-Za-z]+)\r?\n([A-Za-z]+[\s>])', r'\1\2', text )
    text = re.sub( r'&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)', '&amp;', text )
    text = re.sub( r'<(?![/?!]?[A-Za-z])|<(?=[A-Z][a-z]+ )', '&lt;', text ) # e.g., ‘<See’, which isn't a tag
    try: return ET.fromstring( f'<entry>{text}</entry>' )
    except ET.ParseError: return ET.fromstring( f'<entry>{balanced( text )}</entry>' )


def balanced( text:str ) -> str:
    """ An entry's markup with an end tag that has no start tag left out, and a start tag that has no end tag ended at the end
        (e.g., Scofield's list that starts in the note on Genesis 4:1 and ends in the note on 4:2) """
    parts, stack = [], []
    for piece in re.split( r'(<[^>]+>)', text ):
        if (match := re.fullmatch( r'<(/?)([A-Za-z][\w:.-]*)[^>]*?(/?)>', piece )):
            closing, tag, empty = match.groups()
            if empty: pass
            elif not closing: stack.append( tag )
            elif tag in stack:
                while stack[-1] != tag: parts.append( f'</{stack.pop()}>' )
                stack.pop()
            else: continue
        parts.append( piece )
    return ''.join( parts ) + ''.join( f'</{tag}>' for tag in reversed( stack ) )


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
        self.show_titles = False # Whether a <title> is a heading in the entry (in a commentary), rather than the entry's own title (in a dictionary)
        self.lastWasReference = False
        self.inNote = False # (A paragraph in a note, e.g., each proof in the Westminster Confession's, is a note's paragraph)

    def add_reference( self, text:str, osisRef:str|None, passage:str|None=None ) -> None:
        """ A reference element's text (e.g., ‘Ex 6:16-20’, ‘10’, or ‘Job 26:7; Isa 45:18’): each reference in it is a cites anchor
            (or, where the element says what it is, e.g., passage="Ge 1:3" for the 3 in a TSK chapter's outline, that) """
        if passage and OSIS_PASSAGE_RE.fullmatch( passage.strip() ): # (Walther's ‘<scripRef passage="Matt.15.13">Matt. 15, 13</scripRef>’)
            start = len(self.doc.tokens)
            self.add_text( text )
            passages = [ found for part in passage.split() for found in osis_passages( part ) if self.context.exists( found ) ]
            if not passages: self.parsed.bad_references.append( passage )
            self.parsed.anchors.extend( (start, len(self.doc.tokens), 'cites', found) for found in passages )
            return
        if passage: passage = re.sub( r'^([1-3]?\s?)([a-z])', lambda match: match.group( 1 ) + match.group( 2 ).upper(), passage.strip() ) # (Smith's ‘1ch 12:27’)
        if passage and (match := PART_RE.fullmatch( passage )):
            start = len(self.doc.tokens)
            self.add_text( text )
            passages = Context( self.chapters ).passages( match.group( 'book' ), match.group( 'ranges' ) )
            if not passages: self.parsed.bad_references.append( passage )
            self.parsed.anchors.extend( (start, len(self.doc.tokens), 'cites', found) for found in passages )
            return
        position, elementStart, anchorCount, badCount = 0, len(self.doc.tokens), len(self.parsed.anchors), len(self.parsed.bad_references)
        for match in PART_RE.finditer( text ):
            before = text[position:match.start()]
            self.add_text( before )
            separator = before.strip()[-1:] or self.separator
            start = len(self.doc.tokens)
            self.add_text( match.group() )
            book = 'Revelation' if match.group( 'book' ) == 'John' and before.endswith( 'Revelation of ' ) else match.group( 'book' ) # (CCEL's ‘Revelation of John 22:16’)
            passages = self.context.passages( book, match.group( 'ranges' ), separator )
            if not passages and osisRef and len(text.strip()) == len(match.group()): # e.g., ‘1 Macc. 1:23’, whose book the text's names don't include
                passages = [ passage for passage in osis_passages( osisRef ) if self.context.exists( passage ) ]
            if not passages: self.parsed.bad_references.append( match.group() )
            self.parsed.anchors.extend( (start, len(self.doc.tokens), 'cites', passage) for passage in passages )
            position, self.separator = match.end(), ''
        self.add_text( text[position:] )
        if osisRef and len(self.parsed.bad_references) > badCount and len(self.parsed.anchors) == anchorCount and re.match( r'\W*[1-3]?[A-Z]{2,3}\s+\d', text ):
            # A reference that starts with a book's code (e.g., the Westminster Confession's ‘ROM 2:14’): what the element says it is
            # (only then, because some modules' osisRef attributes are wrong: see above)
            if (passages := [ passage for part in osisRef.split() for passage in osis_passages( part ) if self.context.exists( passage ) ]):
                del self.parsed.bad_references[badCount:]
                self.parsed.anchors.extend( (elementStart, len(self.doc.tokens), 'cites', passage) for passage in passages )

    def add_text( self, text:str|None ) -> None:
        """ (Remembering the last punctuation, which says what a reference that's only numbers is: see Context.passages) """
        super().add_text( text )
        if text and text.strip(): self.separator = text.strip()[-1]

    def walk( self, element, following=None ) -> None:
        """ An element of an entry. A line break starts a paragraph, unless a reference element comes straight after it (in the TSK,
            a word of the verse is on one line, and its references on the next): then they're kept together, with ‘; ’ between references. """
        tag, tokens = element.tag, self.doc.tokens
        if tag in ('lb', 'br'):
            tail = LINE_MARK_RE.sub( '', element.tail or '' ) if self.line_style == 'li' else element.tail
            if following is not None and following.tag == 'scripRef' and not (element.tail or '').strip() and len(tokens) > self.paraStart:
                self.add_text( '; ' if self.lastWasReference else ' ' )
            else: self.start_paragraph( 'note' if self.inNote else self.line_style, {} )
            self.add_text( tail ); self.lastWasReference = False
            return
        if tag in ('chapter', 'milestone') or (tag == 'div' and len(element) == 0 and not (element.text or '').strip()): # (OSIS's milestones)
            if tag == 'div' and element.get( 'sID' ) and element.get( 'type' ) == 'x-p': self.start_paragraph( 'note' if self.inNote else 'p', {} )
            self.add_text( element.tail ); self.lastWasReference = False
            return
        if tag == 'title' and not self.show_titles: self.add_text( element.tail ); return # (The entry's title is its first paragraph)
        if tag in BLOCKS: self.start_paragraph( 'note' if self.inNote and BLOCKS[tag] == 'p' else BLOCKS[tag], {} )
        wasInNote, self.inNote = self.inNote, self.inNote or tag == 'note'
        start = len(tokens)
        if tag in ('ref', 'scripRef', 'reference') and element.get( 'target' ) is None:
            if tag == 'scripRef': # (In the TSK, each line of references starts again from the verse that the entry is about)
                self.context = Context( self.chapters, *self.home )
            self.add_reference( ''.join( element.itertext() ), element.get( 'osisRef' ), element.get( 'passage' ) )
        else:
            if tag not in BLOCKS and tag not in SPANS and tag not in INLINE: self.doc.warn( f'unknown element <{tag}>' )
            text = element.text
            if tag == 'entry' and self.line_style == 'li': text = LINE_MARK_RE.sub( '', text or '' ) # (A topic's first line)
            self.add_text( text )
            for ix, child in enumerate( element ):
                if child.tag in ('cell', 'td', 'th') and ix: self.add_text( ' ' ) # (Between a table's cells, e.g., the topic and its verses in Matthew Henry's outlines)
                self.walk( child, element[ix+1] if ix + 1 < len(element) else None )
        end, self.inNote = len(tokens), wasInNote
        if tag == 'ref' and element.get( 'target', '' ).count( ':' ) == 1 and end > start: # e.g., target="Nave:CHILDREN"
            self.parsed.links.append( (start, end, 'see', f"{self.document} {entry_name( topic_title( element.get( 'target' ).split( ':' )[1] ) )}") )
        elif tag == 'term' and end > start: # e.g., Smith's ‘See <term>MONTH</term>’
            self.parsed.links.append( (start, end, 'see', f"{self.document} {entry_name( topic_title( ''.join( element.itertext() ).strip() ) )}") )
        elif tag in SPANS and end > start: self.doc.nodes.append( ('span', start, end, SPANS[tag] or element.get( 'type', 'hi' ), {}) )
        if tag in BLOCKS:
            self.end_paragraph()
            if tag not in ('p', 'item', 'li'): self.start_paragraph( 'note' if wasInNote else 'p', {} ) # (For what follows it, which isn't in a paragraph of its own)
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
        theirs = heading + ''.join( _shown_text( root, self.show_titles, self.line_style == 'li' ) )
        reduce = lambda text: re.sub( r'[\s→;]', '', text )
        ours, theirs = reduce( ours ), reduce( theirs )
        if ours != theirs:
            ix = next( (ix for ix,(a,b) in enumerate( zip( ours, theirs ) ) if a != b), min( len(ours), len(theirs) ) )
            self.parsed.text_differences.append( { 'entry':name, 'offset':ix, 'ours':ours[max(0,ix-30):ix+30], 'source':theirs[max(0,ix-30):ix+30] } )


def _shown_text( element:ET.Element, titles:bool=False, topics:bool=False, top:bool=True ) -> list:
    """ The text of an entry as it's shown: all of it but its <title> in a dictionary (whose text is the entry's heading instead),
        and the marks that start a topic's lines """
    text = element.text or ''
    if topics and (top or element.tag in ('lb', 'br')): text = LINE_MARK_RE.sub( '', text )
    parts = [] if element.tag == 'title' and not titles else [ text ]
    for child in element: parts += _shown_text( child, titles, topics, False )
    if not top: parts.append( LINE_MARK_RE.sub( '', element.tail or '' ) if topics and element.tag in ('lb', 'br') else element.tail or '' )
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
        if driver in ('zld', 'rawld'):
            read = read_dictionary if driver == 'zld' else read_raw_dictionary
            return { settings['document']: parse_dictionary( edition, read( archive, dataPath, encoding ), chapters, path.name ) }
        if driver == 'rawgenbook': return parse_genbook( edition, read_genbook( archive, dataPath, encoding ), chapters, path.name )
        if driver in ('zcom', 'zcom4'):
            blockType = conf.get( 'BlockType', 'BOOK' )[:1].lower()
            return parse_commentary( edition, read_commentary( archive, dataPath, encoding, chapters, 10 if driver == 'zcom' else 12, blockType ), chapters, path.name,
                                     conf.get( 'SourceType', '' ).upper() == 'OSIS' )
        raise ValueError( f"{edition['id']}: SWORD's {conf['ModDrv']} modules can't be read yet" )


MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December']


def dictionary_pieces( key:str, text:str, settings:dict ) -> list:
    """
    An entry's pieces: [ (title or None, root) ]. A devotional's readings for a day are each an entry: Spurgeon's Morning and Evening's sections
    (each with its title, e.g., ‘Evening, January 1’), and, where the registry's `sword.parts` names them (e.g., Daily Light's ‘Morning’ and ‘Evening’), the parts
    that start with those words in italics, titled with the date (from a key like 01.31, where `sword.dates` says so).
    Where `sword.wrapped` says so, a single line break is only where the text was wrapped (e.g., Daily Light's), and two start a paragraph.
    """
    if settings.get( 'wrapped' ):
        text = re.sub( r'\s*<br\s*/>\s*', ' ', re.sub( r'<br\s*/>\s*<br\s*/>', '\x1d', text ) ).replace( '\x1d', '<br /><br />' )
    date = None
    if settings.get( 'dates' ) and (match := re.fullmatch( r'(\d\d)\.(\d\d)', key.strip() )): date = f'{MONTHS[int(match.group( 1 ))-1]} {int(match.group( 2 ))}'
    if (parts := settings.get( 'parts' )):
        pattern = '|'.join( re.escape( f'<i>{part}</i>:' ) for part in parts )
        pieces = re.split( f'({pattern})', text )
        return [ (f'{re.sub( r"<[^>]*>|:", "", label )}, {date or key}', as_xml( piece )) for label, piece in zip( pieces[1::2], pieces[2::2] ) ]
    root = as_xml( text )
    sections = [ section for section in root.iter( 'div' ) if section.get( 'type' ) == 'section' and section.find( 'title' ) is not None ]
    if len(sections) > 1: return [ (None, section) for section in sections ]
    return [ (date, root) ]


def parse_dictionary( edition:dict, entries:list, chapters:dict, sourceName:str ) -> tuple:
    parser = SwordParser( edition, chapters )
    names = set()
    for key, text in entries:
        for pieceTitle, root in dictionary_pieces( key, text, edition['sword'] ):
            title = pieceTitle or usfm.WHITESPACE_RE.sub( ' ', root.findtext( './/title' ) or '' ).strip() or (topic_title( key ) if edition['sword'].get( 'topics' ) else key.title())
            name = entry_name( title )
            while name in names: name += '_'
            names.add( name )
            parser.context = Context( chapters )
            parser.add_entry( name, edition['sword'].get( 'entries', 'Topic' if edition['sword'].get( 'topics' ) else 'Article' ), title, root, [], heading=title )
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


def intro_end( text:str ) -> int|None:
    """
    Where the introduction ends in a book's first note that starts with it (e.g., Keil and Delitzsch's), or None if it has no introduction (no title that says ‘Introduction’):
    at the first title after the introduction's (last) title that names a passage, or else at the first paragraph that starts with a verse's reference,
    with any titles just before it (less than 1,500 characters apart), or else at the end (the whole note is the introduction).
    """
    plain = lambda part: len(re.sub( r'\s+', ' ', re.sub( r'<[^>]*>', '', part ) ).strip())
    titles = [ (match.start(), match.end(), re.sub( r'<[^>]*>', '', match.group( 1 ) )) for match in TITLE_RE.finditer( text ) ]
    introductions = [ number for number, (_start, _end, title) in enumerate( titles ) if 'introduction' in title.lower() ]
    if not introductions: return None
    later = titles[introductions[-1]+1:]
    found = next( (number for number, (_start, _end, title) in enumerate( later ) if PASSAGE_TITLE_RE.search( title )), None )
    if found is None:
        heading = VERSE_HEADING_RE.search( text, titles[introductions[-1]][1] )
        if not heading: return len(text)
        found = sum( 1 for start, _end, _title in later if start < heading.start() )
        later = later[:found] + [(heading.start(), heading.start(), '')]
    while found and plain( text[later[found-1][1]:later[found][0]] ) < 1500: found -= 1
    return later[found][0]


# Spurgeon's *Treasury of David* (`sword.sections = "verses"`): a psalm's sections (by their titles), and where each verse's part of a section starts
#   (‘Verse 1.’, ‘Ver. 3.’, ‘Ver 43.’, ‘Verses 4, 5.’, ‘Verses 1-4.’, ‘Ver. 42-43, 47.’, ‘Verse 2 (second clause).’, in bold or not)
SECTIONS = { 'EXPOSITION':('Exposition', ''), 'EXPLANATORY NOTES AND QUAINT SAYINGS':('Notes', 'Explanatory Notes and Quaint Sayings'),
             'NOTES RELATING TO THE PSALM AS A WHOLE':('Notes', 'Explanatory Notes and Quaint Sayings'),
             'HINTS TO THE VILLAGE PREACHER':('Hints', 'Hints to the Village Preacher'), 'HINTS TO PREACHERS':('Hints', 'Hints to Preachers'), 'WORKS UPON':('Works', 'Works upon the Psalm') }
VERSE_PART_RE = re.compile( r'<div sID="[^"]*" type="x-p"/>\s*(?:<hi type="bold">)?\s*(?:Verses?|Ver\.?)\s*(\d+(?:\s*[-–,]\s*\d+)*)(?=\s*[.(<:]|\s+[A-Z])' )
# Psalm 119's pages' leftovers (‘Psalms 119:2*’ and ‘Continued...See Psalms’), which are left out, and its sections' titles that are only paragraphs (‘HINTS TO PREACHERS.’)
PAGE_MARK_RE = re.compile( r'<div sID="[^"]*" type="x-p"/>\s*(?:Continued\.\.\.[^<]*|Psalms \d+:\d+\*)\s*<div eID="[^"]*" type="x-p"/>' )
SECTION_PARAGRAPH_RE = re.compile( r'<div sID="[^"]*" type="x-p"/>\s*((?:EXPOSITION|EXPLANATORY NOTES AND QUAINT SAYINGS|HINTS TO (?:THE VILLAGE )?PREACHERS?)\.?)\s*<div eID="[^"]*" type="x-p"/>' )


def verse_sections( BBB:str, chapter:int, text:str, chapters:dict ) -> list:
    """
    A psalm's note in Spurgeon's *Treasury of David* (which SWORD keeps at its first verse) as entries: its overview (with its title and division) up to its first section,
    then each section's part on each verse (its exposition, explanatory notes, and hints to preachers), named like `23:1`, `23:1Notes`, and `23:4-5Hints`,
    with what comes before a section's first verse in an entry on the whole psalm (`23Notes`), or, in a later section of the same kind (as in Psalm 119's stanzas), with that first verse.
    A section's title is the entry's title (with the psalm and verses), so it's left out of its text; the books on the psalm (‘WORKS UPON THE FIRST PSALM’) keep theirs.
    """
    whole, count = [f'{BBB} {chapter}:1-{chapter}:{chapters[BBB][chapter-1]}'], chapters[BBB][chapter-1]
    text = SECTION_PARAGRAPH_RE.sub( r'<title type="x-s">\1</title>', PAGE_MARK_RE.sub( '', text ) )
    titles = [ (match.start(), match.end(), re.sub( r'<[^>]*>', '', match.group( 1 ) ).strip().rstrip( '.' ).upper()) for match in TITLE_RE.finditer( text ) ]
    sections = [] # (Kind, title, start, end of its text)
    for start, end, title in titles:
        kind = next( (value for key, value in SECTIONS.items() if title.startswith( key )), None )
        if not kind: continue
        sections.append( (*kind, start if kind[0] == 'Works' else end) )
        if len(sections) == 1: overview = text[:start]
        else: sections[-2] = (*sections[-2], start)
    if not sections: return [ (f'{chapter}', 'Overview', whole, text, f'Psalm {chapter}') ]
    sections[-1] = (*sections[-1], len(text))
    parts, names, seen = [ (f'{chapter}', 'Overview', whole, overview, f'Psalm {chapter}: Overview') ], set(), set()
    for kind, sectionTitle, start, end in sections:
        suffix = '' if kind == 'Exposition' else kind
        label = lambda verses: f'Psalm {chapter}:{verses}' + (f': {sectionTitle}' if sectionTitle else '')
        marks = list( VERSE_PART_RE.finditer( text, start, end ) )
        if kind == 'Works' or not marks: marks = []
        pieces, carried = [], ''
        lead = text[start:marks[0].start()] if marks else text[start:end]
        if kind in seen and marks: carried = lead
        elif re.sub( r'<[^>]*>', '', lead ).strip(): pieces.append( (None, lead) )
        seen.add( kind )
        for number, match in enumerate( marks ):
            verses = [] # (Each range of verses that it's on)
            for separator, digits in re.findall( r'([-–,]?)\s*(\d+)', match.group( 1 ) ):
                if separator in '-–' and verses: verses[-1] = (verses[-1][0], int(digits))
                else: verses.append( (int(digits), int(digits)) )
            verses = tuple( (first, min( last, count )) for first, last in verses if first <= count ) or ((1, count),)
            piece = carried + text[match.start():marks[number+1].start() if number+1 < len(marks) else end]
            carried = ''
            if pieces and pieces[-1][0] == verses: pieces[-1] = (verses, pieces[-1][1] + piece) # (The same verses again)
            else: pieces.append( (verses, piece) )
        for verses, piece in pieces:
            if verses is None: name, about, title = f'{chapter}{suffix or kind}', whole, f'Psalm {chapter}: {sectionTitle or "Exposition"}'
            else:
                shown = ', '.join( f'{first}' if last == first else f'{first}-{last}' for first, last in verses )
                about = [ f'{BBB} {chapter}:{first}' + ('' if last == first else f'-{chapter}:{last}') for first, last in verses ]
                name, title = f'{chapter}:{shown.replace( ", ", "," )}{suffix}', label( shown ) if sectionTitle else ''
            base, copy = name, 1
            while name in names: copy += 1; name = f'{base}{copy}'
            names.add( name )
            parts.append( (name, kind if kind != 'Exposition' else 'Commentary', about, piece, title) )
    return parts


# Calvin's commentaries (`sword.sections = "milestones"`): each note is between OSIS milestones, and what comes after a note's (its next note's heading and text,
#   or a printed volume's back matter, or the next book's preface) is moved or left out. A paragraph (or title) starts where these are, and its text says what it is.
COMMENTARY_START_RE = re.compile( r'<div [^>]*annotateType="commentary"[^>]*sID="[^"]*"[^>]*/>' )
COMMENTARY_END_RE = re.compile( r'<div [^>]*annotateType="commentary"[^>]*eID="[^"]*"[^>]*/>' )
PARAGRAPH_START_RE = re.compile( r'<div sID="[^"]*"(?: type="x-p")?/>|<title\b[^>]*>' )
BACK_MATTER_RE = re.compile( r'(?:Indexes|A TRANSLATION OF|APPENDIX|A LIST OF THE CHIEF INTERPRETERS|Dissertation \d|NOTES AND COMMENTS|The addenda to)\b', re.I )
FRONT_MATTER_RE = re.compile( r'(?:Calvin.s Preface|THE ARGUMENT|THE AUTHOR.S DEDICATORY|PREFACE\b|Lecture (?:First|Forty))', re.I )
PRAYER_RE = re.compile( r'(?:PRAYER|End of the Commentaries|Praise be to God|PRAISE TO GOD)\b', re.I )
HEADING_RE = re.compile( r'((?:[1-3] )?[A-Z][a-z]+) (?:Chapter )?(\d+)(?:[:.]\d+)?(?:\s*[-–,]\s*\d+(?::\d+)?)*$' ) # (A paragraph that's a passage's heading: ‘1 John 1:1-2’, ‘Jude 1-2’, ‘Hebrews Chapter 2:16-18’)
PUBLISHER_RE = re.compile( r'CHRISTIAN CLASSICS ETHEREAL LIBRARY|http://www\.ccel\.org' )


def regroup_milestones( entries:list, chapters:dict ) -> list:
    """
    Calvin's notes (whose module has each between OSIS milestones, with what comes after it in the printed volumes kept with it) regrouped:
    what's after a note (its next note's heading, the Bible's text, and a lecture's title) goes with its next note in the book, except a lecture's closing prayer
    (‘PRAYER’, and ‘End of the Commentaries on Joel’), which stays; a volume's back matter (its indexes, translation of Calvin's version, dissertations, and appendices)
    is left out, from where it starts to where the note ends; and at a book's end, a preface or argument (which is the next book's, in the printed volume's order)
    goes to the book that its last heading is in (e.g., 1 Peter's ends with 1 John's argument, and ‘1 John 1:1-2’), or else the next book, as its introduction.
    What's before the book's first note (Genesis's title page, preface, and argument) is its introduction too, without the publisher's lines (CCEL's).
    """
    plain = lambda part: re.sub( r'\s+', ' ', re.sub( r'<[^>]*>?', ' ', part ) ).strip()
    def paragraphs( text:str ) -> list: # (Where each paragraph starts and ends, and its text)
        starts = [ match.start() for match in PARAGRAPH_START_RE.finditer( text ) ]
        return [ (start, end, plain( text[start:end] )) for start, end in zip( starts, starts[1:] + [len(text)] ) ]
    def first( text:str, pattern:re.Pattern ) -> int|None:
        return next( (start for start, _end, words in paragraphs( text ) if pattern.match( words )), None )
    notes = [ number for number, entry in enumerate( entries ) if entry[2] ]
    books = list( dict.fromkeys( entries[number][0] for number in notes ) )
    intros, regrouped, carried = {}, {}, ''
    for position, number in enumerate( notes ):
        BBB, chapter, verse, lastVerse, text = entries[number]
        following = entries[notes[position+1]] if position+1 < len(notes) else None
        if not carried and (position == 0 or entries[notes[position-1]][0] != BBB): # (The book's first note)
            if (start := COMMENTARY_START_RE.search( text )): intros[BBB] = intros.get( BBB, '' ) + text[:start.start()]; text = text[start.start():]
            elif not COMMENTARY_END_RE.search( text ): intros[BBB] = intros.get( BBB, '' ) + text; text = '' # (Genesis's, which is all its translator's preface, the dedications, and the argument)
        text, carried = carried + text, ''
        ends = list( COMMENTARY_END_RE.finditer( text ) )
        if ends:
            after, text = text[ends[-1].end():], text[:ends[-1].end()]
            if (back := first( after, BACK_MATTER_RE )) is not None: after = after[:back]
            kept = 0 # (How much of what's after it stays with the note: its closing prayer)
            for _start, end, words in paragraphs( after ):
                if not words: continue
                if PRAYER_RE.match( words ) or (kept and words.startswith( 'Grant' )): kept = end
                else: break
            text, after = text + after[:kept], after[kept:]
            heading = next( (match for _start, _end, words in paragraphs( after ) if (match := HEADING_RE.match( words ))), None )
            if following and following[0] == BBB and not (heading and book_code( heading.group( 1 ) ) == BBB and int(heading.group( 2 )) == chapter != following[1]):
                carried = after # (Unless it's more of this chapter, though the next note is on another: e.g., Psalm 119:121-128's text, whose commentary the module doesn't have)
            elif plain( after ):
                front = first( after, FRONT_MATTER_RE )
                if front is None: text += after
                else:
                    text += after[:front]
                    headings = [ book_code( match.group( 1 ) ) for _start, _end, words in paragraphs( after[front:] ) if (match := HEADING_RE.match( words )) ]
                    target = next( (code for code in reversed( headings ) if code in books and code != BBB), None )
                    if not target: target = books[books.index( BBB )+1] if books.index( BBB )+1 < len(books) else None
                    if target: intros[target] = after[front:] + intros.get( target, '' )
        regrouped[number] = (BBB, chapter, verse, lastVerse, text)
    result, introduced = [], set()
    for number, entry in enumerate( entries ):
        BBB = entry[0]
        if BBB not in introduced and re.sub( r'<[^>]*>', '', intros.get( BBB, '' ) ).strip():
            introduced.add( BBB )
            intro, pieces = intros[BBB], paragraphs( intros[BBB] )
            intro = intro[:pieces[0][0] if pieces else len(intro)] + ''.join( intro[start:end] for start, end, words in pieces if not PUBLISHER_RE.search( words ) )
            result.append( (BBB, 0, 0, 0, intro) )
        result.append( regrouped.get( number, entry ) )
    return result


def parse_commentary( edition:dict, entries:list, chapters:dict, sourceName:str, osis:bool=False ) -> dict:
    """
    One document for each book, with an entry for each note (of the type that the registry's `sword.notes` says: `CrossReferences` by default, as for the TSK).
    The TSK keeps a chapter's outline at its first verse, before a blank line: that becomes an entry of its own.
    An OSIS commentary (e.g., Matthew Henry's) keeps what comes before a verse's note between ‘pre-verse’ milestones: at the book's first note,
    that's the book's introduction (an entry of its own, up to the chapter's title, if it has one), and at a chapter's first note,
    its title and outline in Matthew Henry's (an entry of its own, if it has more than titles); titles alone (e.g., a section's title) stay with the note.
    The book's own slot (chapter 0) goes with its introduction (e.g., Jamieson, Fausset, and Brown's ‘Commentary by David Brown’), as does,
    in an OSIS commentary, its first chapter's (where Matthew Henry's keeps a book of one chapter's introduction).
    A chapter's own slot (verse 0) that has only a title or nothing is left out.
    Adam Clarke's has no milestones, but the same: a book's preface, and each chapter's ‘Introduction’, before the chapter's first note.
    In ThML commentaries (e.g., the TSK, Barnes's, and the People's New Testament), a chapter's own slot repeats a note from elsewhere (e.g., Acts 27:44's, before Romans):
    it's left out. Barnes's keeps a book's preface and introduction at its first verses, with those verses' notes after them: they're `BookIntro`s, about the whole book too.
    In Matthew Henry's and Adam Clarke's, a note starts with the verses it's about (‘Verses 1-8’), except where a chapter has only one note, which is about the whole chapter
    (e.g., Psalm 23's), though SWORD has it only at the chapter's first verse.
    """
    noteType = edition['sword'].get( 'notes', 'CrossReferences' )
    if edition['sword'].get( 'sections' ) == 'milestones': entries = regroup_milestones( entries, chapters ) # (Calvin's)
    hasText = lambda text: bool( re.sub( r'<[^>]*>', '', re.sub( r'<title\b.*?</title>', '', text, flags=re.S ) ).strip() ) # (Outside its titles)
    parsers, bookSlots, introduced = {}, {}, set()
    notes = {}
    for BBB, chapter, verse, _lastVerse, _text in entries:
        if verse: notes[(BBB, chapter)] = notes.get( (BBB, chapter), 0 ) + 1
    headed = any( NOTE_START_RE.search( text ) for *_slot, text in entries )
    repeated = { text for text, count in collections.Counter( text for *_slot, text in entries ).items() if count > 1 }
    for BBB, chapter, verse, lastVerse, text in entries:
        if BBB not in parsers:
            parsers[BBB] = SwordParser( edition, chapters )
            parsers[BBB].show_titles = True
        parser = parsers[BBB]
        if not verse and not osis and text in repeated: continue # (A copy of another slot's note)
        if not chapter or (osis and chapter == 1 and not verse and BBB not in introduced): bookSlots[BBB] = bookSlots.get( BBB, '' ) + text; continue
        first = bool( verse ) and BBB not in introduced # (The book's first note)
        if first: introduced.add( BBB )
        bookSlot = bookSlots.pop( BBB, '' ) if first else ''
        bookCount = len(chapters[BBB])
        wholeBook = f'{BBB} 1' if bookCount == 1 else f'{BBB} 1-{bookCount}'
        wholeChapter = f'{BBB} {chapter}:1-{chapter}:{chapters[BBB][chapter-1]}' if chapter else ''
        parts, opening = [], None # (Where what comes before the note starts and ends, and where the note starts, if it says)
        if first and edition['sword'].get( 'intros' ) == 'first-note' and (split := intro_end( text )) is not None:
            verses = [f'{BBB} {chapter}:{verse}' + ('' if lastVerse == verse else f'-{chapter}:{lastVerse}')] if split == len(text) else [] # (A whole note that's the introduction is about its verses too)
            parts.append( ('Intro', 'BookIntro', [wholeBook] + verses, bookSlot + text[:split]) )
            text, bookSlot = text[split:], ''
        if verse and edition['sword'].get( 'sections' ) == 'verses': # (Spurgeon's psalms: nothing's left for the note)
            if first and hasText( bookSlot ): parts.append( ('Intro', 'BookIntro', [wholeBook], bookSlot) )
            parts += verse_sections( BBB, chapter, text, chapters )
            text, bookSlot = '', ''
        elif verse and (match := PREVERSE_RE.search( text )):
            start, end = match.span( 1 )
            noteStart = NOTE_START_RE.search( text, match.start() )
            if noteStart and CHAPTER_TITLE_RE.search( text, start, noteStart.start() ): end = noteStart.start()
            opening = (start, end, noteStart)
        elif verse and headed and (noteStart := NOTE_START_RE.search( text )) and (CHAPTER_TITLE_RE.search( text, 0, noteStart.start() )
                                                                              or (first and PREFACE_RE.search( text, 0, noteStart.start() ))):
            opening = (0, noteStart.start(), noteStart) # (Adam Clarke's, which has no pre-verse milestones: a book's preface, and a chapter's ‘Introduction’)
        if first and not opening and hasText( bookSlot ):
            parts.append( ('Intro', 'Introduction', [wholeBook], bookSlot) )
        if verse == 1 and '\n<br />\n<br />' in text and text.lstrip().startswith( '<br /><scripRef passage=' ):
            outline, text = text.split( '\n<br />\n<br />', 1 )
            parts.append( (f'{chapter}', 'Outline', [wholeChapter], outline) )
        elif opening:
            start, end, noteStart = opening
            before, kept = text[start:end], ''
            ix = chapterTitle.start() if (chapterTitle := CHAPTER_TITLE_RE.search( before )) else -1
            if first:
                titles = set( re.findall( r'<title[^>]*>(.*?)</title>', before, re.S ) ) # (Without a title that the book's slot and its introduction both have)
                bookSlot = re.sub( r'<title[^>]*>(.*?)</title>', lambda match: '' if match.group( 1 ) in titles else match.group(), bookSlot, flags=re.S )
                intro = bookSlot + (before[:ix] if ix >= 0 else before)
                if hasText( intro ): # (Otherwise, e.g., only a section's title, it stays with the note)
                    parts.append( ('Intro', 'BookIntro', [wholeBook], intro) )
                    before = before[ix:] if ix >= 0 else ''
            if CHAPTER_TITLE_RE.search( before ) and hasText( before ):
                parts.append( (f'{chapter}', 'Outline' if noteStart or '<table>' in before else 'Introduction', [wholeChapter], before) )
            else: kept = before
            text = text[:start] + kept + text[end:]
        if verse:
            if headed and notes[(BBB, chapter)] == 1 and verse == 1 and not NOTE_START_RE.search( text ): lastVerse = chapters[BBB][chapter-1]
            verses = f'{verse}' if lastVerse == verse else f'{verse}-{lastVerse}'
            about = [f'{BBB} {chapter}:{verse}' + ('' if lastVerse == verse else f'-{chapter}:{lastVerse}')]
            if not osis and chapter == 1 and verse <= 2 and re.match( r'\W*(?:\w+\W+){0,12}?(?:PREFACE|INTRODUCTION|Introduction to)\b', re.sub( r'<[^>]*>', ' ', text ) ):
                parts.append( (f'{chapter}:{verses}', 'BookIntro', [wholeBook] + about, text) ) # (Barnes's)
            else: parts.append( (f'{chapter}:{verses}', noteType, about, text) )
        elif hasText( text ): parts.append( (f'{chapter}:0', 'Introduction', [f'{BBB} {chapter}'], text) )
        for name, entryType, about, part, *title in parts:
            if not re.sub( r'<[^>]*>', '', part ).strip(): continue
            root = as_xml( part )
            parser.home = (BBB, chapter or None, verse or None)
            parser.context = Context( chapters, *parser.home )
            parser.add_entry( name, entryType, title[0] if title else '', root, about )
    return { BBB: (parser.finish(), [sourceName]) for BBB, parser in parsers.items() }


def lift_notes( root:ET.Element ) -> ET.Element:
    """ Each <note> in a paragraph moved to just after it (e.g., Whiston's notes in Josephus), so that the paragraph isn't broken by it """
    for paragraph in list( root.iter( 'p' ) ):
        notes = [ child for child in paragraph if child.tag == 'note' ]
        if not notes: continue
        parent = next( element for element in root.iter() if paragraph in list( element ) )
        position = list( parent ).index( paragraph )
        for note in notes:
            previous = next( (child for child, following in zip( paragraph, list( paragraph )[1:] ) if following is note), None )
            if previous is None: paragraph.text = (paragraph.text or '') + (note.tail or '')
            else: previous.tail = (previous.tail or '') + (note.tail or '')
            paragraph.remove( note )
            note.tail = None
        for offset, note in enumerate( notes, start=1 ): parent.insert( position + offset, note )
        notes[-1].tail, paragraph.tail = paragraph.tail, None
    return root


# The note that CCEL's modernizing left after each word it changed (e.g., in Owen's works: ‘you<note n="thou">Auto-modernized</note>’), which isn't kept
AUTO_MODERNIZED_RE = re.compile( r'<note n="[^"]*">Auto-modernized</note>' )
# The printed edition's page numbers, as links (e.g., in Walther's Law and Gospel: ‘<small><sup><a href="#29">29</a></sup></small><a name="29"/>’), which aren't kept
PAGE_MARKER_RE = re.compile( r'<small><sup><a href="#[^"]*">[^<]*</a></sup></small><a name="[^"]*"/>\s*' )
GENBOOK_LIMIT = 100_000 # (characters of a module's markup: more than this in one entry is split, where it can be)
HEADINGS = {'title', 'h1', 'h2', 'h3', 'h4'}


ROMAN_RE = re.compile( r'(?=[IVXLC])C{0,3}(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})[.,:]?' )


def key_name( name:str ) -> str:
    """ A general book's key as it's shown: Lecture_01_Thesis_I → Lecture 1 Thesis I, Section 2_1 → Section 2.1,
        BOOK FIRST. - OF THE KNOWLEDGE OF GOD → Book First: Of the Knowledge of God, II. THE WAGES OF SIN. → II. The Wages of Sin, and its spacing tidied """
    name = re.sub( r'(?<=\d)_(?=\d)', '.', name ).replace( '_', ' ' )
    name = re.sub( r'\.\s+-\s+', ': ', ' '.join( re.sub( r'\b0+(?=\d)', '', name ).split() ) ).rstrip( '.,;:' )
    if name.upper() != name: return name
    name, words = name.replace( '—', '— ' ), []
    for word in name.split( ' ' ):
        if ROMAN_RE.fullmatch( word ): words.append( word )
        elif words and word.lower() in SMALL_WORDS and not words[-1].endswith( (':', '.', '-') ): words.append( word.lower() )
        else: words.append( word[:1] + word[1:].lower() )
    return ' '.join( words ).replace( '— ', '—' )


def heading_text( element:ET.Element ) -> str|None:
    """ The text of the heading that an element is, or starts with (e.g., the Westminster catechisms' ‘<p><title>Q. 1. …</title>’), if it's one """
    if element.tag not in HEADINGS:
        if element.tag != 'p' or (element.text or '').strip() or not len( element ) or element[0].tag not in HEADINGS: return None
        element = element[0]
    return ' '.join( ''.join( element.itertext() ).split() )


def has_text( element:ET.Element, top:bool=True ) -> bool:
    """ Whether an entry has any text but its headings """
    if not top and element.tag in HEADINGS: return bool( (element.tail or '').strip() )
    return bool( (element.text or '').strip() ) or any( has_text( child, False ) for child in element ) or (not top and bool( (element.tail or '').strip() ))


def parse_genbook( edition:dict, tree:tuple, chapters:dict, sourceName:str ) -> dict:
    """
    A general book (e.g., Josephus's works) as one document, `Chapter`, like an EPUB book's: an entry (named 1, 2, …, and titled with its keys,
    e.g., ‘The Antiquities of the Jews, Book 1, Chapter 1’) for each key whose keys under it have none under them (e.g., a chapter and its sections),
    unless it has more than 20 (e.g., the sections of Josephus's Life) or they're long, when each of those is an entry.
    A key's own text goes with the next entry, as does an entry that has nothing but headings.
    A long entry that has headings (e.g., each question of a catechism) is split at them. The notes that CCEL's modernizing left, and links for a printed edition's pages, aren't kept.
    When the book has only one key at the top, its name isn't in the titles, and a key named for the module (e.g., Owen's `JOChrist`) is named for the book.
    The `sword` settings can name keys (`names`, e.g., `WSC` → ‘The Westminster Shorter Catechism’, or ‘’ to leave a key's name out of the titles), and leave keys out (`skip`, with any `*` in a key matching anything, e.g., ‘Index of *’).
    """
    settings = edition.get( 'sword', {} )
    names, skip, moduleName = settings.get( 'names', {} ), settings.get( 'skip', [] ), Path( sourceName ).stem.lower()
    def skipped( name:str ) -> bool: return any( fnmatch.fnmatchcase( name, pattern ) for pattern in skip )
    def label( name:str ) -> str: return names[name] if name in names else edition['name'] if name.lower() == moduleName else key_name( name )
    def size( node:tuple ) -> int: return len( node[1] ) + sum( size( child ) for child in node[2] )
    entries, pending = [], ''
    def visit( node:tuple, path:list ) -> None:
        nonlocal pending
        name, text, children = node
        children = [ child for child in children if not skipped( child[0] ) ]
        path = path + [label( name )] if label( name ) else path
        if not children or (len(children) <= 20 and all( not child[2] for child in children ) and size( (name, text, children) ) <= GENBOOK_LIMIT):
            entries.append( (', '.join( path ) or edition['name'], pending + text + ''.join( child[1] for child in children )) ); pending = ''
        else:
            pending += text
            for child in children: visit( child, path )
    works = [ work for work in tree[2] if not skipped( work[0] ) ]
    if len(works) == 1 and works[0][2]: pending, works = works[0][1], [ work for work in works[0][2] if not skipped( work[0] ) ]
    for work in works: visit( work, [] )
    roots = []
    for title, text in entries:
        root = lift_notes( as_xml( PAGE_MARKER_RE.sub( '', AUTO_MODERNIZED_RE.sub( '', text ) ) ) )
        pieces = [(None, [])]
        if len(text) > GENBOOK_LIMIT:
            for child in root:
                if (heading := heading_text( child )): pieces.append( (heading, []) )
                pieces[-1][1].append( child )
        if sum( 1 for heading, _elements in pieces if heading ) < 2: roots.append( (title, root) ); continue
        for heading, elements in pieces:
            if not elements: continue
            piece = ET.Element( 'entry' ); piece.extend( elements )
            if heading is None: piece.text = root.text
            roots.append( (f'{title}, {heading}' if heading else title, piece) )
    merged, carried = [], []
    for title, root in roots:
        if not has_text( root ): carried.append( root ); continue
        inserted = [ child for earlier in carried for child in earlier ]
        if inserted:
            for position, child in enumerate( inserted ): root.insert( position, child )
            inserted[-1].tail, root.text = (inserted[-1].tail or '') + (root.text or ''), None
        merged.append( (title, root) ); carried = []
    for earlier in carried: merged[-1][1].extend( list( earlier ) )
    parser = SwordParser( edition, chapters )
    parser.show_titles = True
    for number, (title, root) in enumerate( merged, start=1 ):
        parser.context = Context( chapters )
        parser.add_entry( str(number), 'Chapter', title, root, [] )
    return { 'Chapter': (parser.finish(), [sourceName]) }
