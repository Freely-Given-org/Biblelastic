"""
Finding Bible references in plain English text, e.g., ‘John 3:16’, ‘2 Tim. 3:1–9’, ‘Mark 2-3:6’, ‘Rom 8:28, 31-39; 9:1’, or ‘Jude 5’.

Each reference found becomes passages in the form that the compiler reads: ‘JHN 3:16’, ‘TI2 3:1-3:9’, or ‘ROM 8’ for a whole chapter.
A book's name must be followed by a number, so ‘Mark’ the name (or ‘Job’ the word) isn't taken for a book on its own.
Where the context gives a book (e.g., a chapter of a book about Mark), bare ‘(1:21-28)’ is taken to be in that book too.
"""
import re

# Names and abbreviations → BibleOrgSys codes. Keys are in lower case without dots or spaces, e.g., ‘1cor’ or ‘songofsongs’.
_NAMES = {
    'GEN':'genesis gen gn ge', 'EXO':'exodus exod exo ex', 'LEV':'leviticus lev lv le', 'NUM':'numbers num nm nu', 'DEU':'deuteronomy deut deu dt',
    'JOS':'joshua josh jos', 'JDG':'judges judg jdg jgs', 'RUT':'ruth ru rth', 'SA1':'1samuel 1sam 1sa 1sm isamuel', 'SA2':'2samuel 2sam 2sa 2sm iisamuel',
    'KI1':'1kings 1kgs 1ki ikings', 'KI2':'2kings 2kgs 2ki iikings', 'CH1':'1chronicles 1chron 1chr 1ch ichronicles', 'CH2':'2chronicles 2chron 2chr 2ch iichronicles',
    'EZR':'ezra ezr', 'NEH':'nehemiah neh', 'EST':'esther esth est', 'JOB':'job jb', 'PSA':'psalm psalms ps psa pss', 'PRO':'proverbs prov pro prv pr',
    'ECC':'ecclesiastes eccl eccles ecc qoh', 'SNG':'songofsongs songofsolomon song sos canticles', 'ISA':'isaiah isa is', 'JER':'jeremiah jer',
    'LAM':'lamentations lam', 'EZE':'ezekiel ezek eze ezk', 'DAN':'daniel dan dn', 'HOS':'hosea hos', 'JOL':'joel joe jl', 'AMO':'amos am',
    'OBA':'obadiah obad ob', 'JNA':'jonah jon', 'MIC':'micah mic', 'NAH':'nahum nah', 'HAB':'habakkuk hab', 'ZEP':'zephaniah zeph zep',
    'HAG':'haggai hag', 'ZEC':'zechariah zech zec', 'MAL':'malachi mal',
    'MAT':'matthew matt mat mt', 'MRK':'mark mk mrk mar', 'LUK':'luke lk luk', 'JHN':'john jn jhn joh', 'ACT':'acts act ac', 'ROM':'romans rom ro rm',
    'CO1':'1corinthians 1cor 1co icorinthians', 'CO2':'2corinthians 2cor 2co iicorinthians', 'GAL':'galatians gal', 'EPH':'ephesians eph',
    'PHP':'philippians phil php', 'COL':'colossians col', 'TH1':'1thessalonians 1thess 1thes 1th ithessalonians', 'TH2':'2thessalonians 2thess 2thes 2th iithessalonians',
    'TI1':'1timothy 1tim 1ti itimothy', 'TI2':'2timothy 2tim 2ti iitimothy', 'TIT':'titus tit', 'PHM':'philemon philem phlm phm', 'HEB':'hebrews heb',
    'JAM':'james jas jam jms', 'PE1':'1peter 1pet 1pe 1pt ipeter', 'PE2':'2peter 2pet 2pe 2pt iipeter', 'JN1':'1john 1jn 1jo 1jhn ijohn', 'JN2':'2john 2jn 2jo 2jhn iijohn',
    'JN3':'3john 3jn 3jo 3jhn iiijohn', 'JDE':'jude jud jd', 'REV':'revelation rev rv apocalypse',
}
BOOKS = { name:BBB for BBB, names in _NAMES.items() for name in names.split() }
SINGLE_CHAPTER = {'OBA', 'PHM', 'JN2', 'JN3', 'JDE'}

_NUMBERED = r'(?:[1-3]|I{1,3})\s*'
_NAME = r'[A-Z][a-z]+(?:\s+of\s+(?:Songs|Solomon))?'
_RANGE = r'\d{1,3}(?::\d{1,3}[a-c]?)?(?:\s*[-–]\s*\d{1,3}(?::\d{1,3})?[a-c]?)?'
_NEXT_BOOK = r'(?!\s*[A-Z][a-z]+\.?\s+\d)' # A later number that starts another reference (e.g., the 2 in ‘1 Cor. 10:6; 2 Cor. 3:5’) isn't part of this one
REFERENCE_RE = re.compile( rf'\b(?P<book>(?:{_NUMBERED})?{_NAME})\.?\s+(?P<ranges>{_RANGE}(?:\s*[,;]\s*{_RANGE}{_NEXT_BOOK})*)' )
BARE_RE = re.compile( rf'(?<![\w:.])(?P<ranges>\d{{1,3}}:\d{{1,3}}[a-c]?(?:\s*[-–]\s*\d{{1,3}}(?::\d{{1,3}})?[a-c]?)?(?:\s*[,;]\s*{_RANGE}{_NEXT_BOOK})*)(?![\w:])' )
VERSES_RE = re.compile( r'\((?P<ranges>\d{1,2}(?:\s*[-–]\s*\d{1,2})?(?:\s*,\s*\d{1,2}(?:\s*[-–]\s*\d{1,2})?)*)\)' ) # e.g., (1-2), in a one-chapter book


def book_code( name:str ) -> str|None:
    return BOOKS.get( re.sub( r'[\s.]', '', name ).lower() )


def _passages( BBB:str, ranges:str ) -> list:
    """ ‘3:16–17, 20; 4:2’ in a book → ['JHN 3:16-3:17', 'JHN 3:20', 'JHN 4:2'] (a later number without a chapter is a verse, after one with a verse) """
    passages, chapter, verses = [], None, False
    for part in re.split( r'\s*[,;]\s*', ranges.strip() ):
        match = re.fullmatch( r'(\d+)(?::(\d+))?[a-c]?(?:\s*[-–]\s*(\d+)(?::(\d+))?[a-c]?)?', part )
        if not match: return []
        first, firstVerse, last, lastVerse = (int(group) if group else None for group in match.groups())
        if BBB in SINGLE_CHAPTER and firstVerse is None and lastVerse is None: # Jude 5 is verse 5, and Jude 1-4 is verses 1-4
            first, firstVerse, last, lastVerse = 1, first, (1 if last is not None else None), last
        elif firstVerse is None and verses: # The 20 in ‘3:16, 20’ is a verse of chapter 3
            first, firstVerse = chapter, first
            if last is not None and lastVerse is None: last, lastVerse = chapter, last
        if firstVerse is None: # Whole chapters: ‘Romans 8’, ‘Mark 2-3’, or ‘Mark 2-3:6’
            if last is None: passages.append( f'{BBB} {first}' ); chapter, verses = first, False; continue
            if lastVerse is None: passages.append( f'{BBB} {first}-{last}' ); chapter, verses = last, False; continue
            firstVerse = 1
        if last is None: last, lastVerse = first, firstVerse
        elif lastVerse is None: last, lastVerse = first, last # ‘3:16-18’
        if (last, lastVerse) < (first, firstVerse) or not 0 < first <= 150 or last > 150 or not 0 < firstVerse <= 176 or lastVerse > 176: return []
        if BBB in SINGLE_CHAPTER and (first, last) != (1, 1): return [] # e.g., ‘9:5’ can't be in Jude
        passages.append( f'{BBB} {first}:{firstVerse}' + ('' if (last, lastVerse) == (first, firstVerse) else f'-{last}:{lastVerse}') )
        chapter, verses = last, True
    return passages


def find( text:str, context:str|None=None ) -> list:
    """
    The Bible references in some text: [(start, end, [passage, …]), …] with character offsets.
    context is the book that bare references (e.g., ‘(1:21-28)’) are taken to be in, if any.
    """
    found, taken = [], []
    for match in REFERENCE_RE.finditer( text ):
        BBB = book_code( match.group( 'book' ) )
        if not BBB: continue
        passages = _passages( BBB, match.group( 'ranges' ) )
        if passages: found.append( (match.start(), match.end(), passages) ); taken.append( (match.start(), match.end()) )
    if context:
        outside = lambda match: not any( start <= match.start() < end for start, end in taken )
        for match in BARE_RE.finditer( text ):
            if outside( match ) and (passages := _passages( context, match.group( 'ranges' ) )): found.append( (match.start(), match.end(), passages) )
        if context in SINGLE_CHAPTER:
            for match in VERSES_RE.finditer( text ):
                if outside( match ) and (passages := _passages( context, match.group( 'ranges' ) )): found.append( (match.start( 'ranges' ), match.end( 'ranges' ), passages) )
    found.sort()
    return found
