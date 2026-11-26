"""
Tokenising parser for USFM and ESFM files.

Turns one source file into the Biblelastic intermediate model:
    tokens (with before/after text and features), nodes (ranges over tokens), and notes.

It's deliberately standalone (no BibleOrgSys import) so that tokenisation is fully under our control
and can be checked for losslessness against the source text (see reference_text() below).
"""
import re

FORMAT_VERSION = '0.1'

# Characters that can be part of a word: letters and digits, plus combining marks
#   (which Python's \w doesn't include), plus the word-joiner that UHB uses between morphemes.
_MARKS = '\u0300-\u036F\u0591-\u05BD\u05BF\u05C1\u05C2\u05C4\u05C5\u05C7\u1AB0-\u1AFF\u1DC0-\u1DFF\u20D0-\u20FF\u2060\uFE20-\uFE2F'
_W = rf'(?:[^\W_]|[{_MARKS}])'
TOKEN_RE = re.compile(rf"¦(\d+)|({_W}+(?:['’]{_W}+)*)")
MARKER_RE = re.compile(r'\\(\+?)([a-z][a-z0-9]*(?:-[se])?)(\*?)')
ATTRIBUTE_RE = re.compile(r'([\w-]+)="([^"]*)"')
WHITESPACE_RE = re.compile(r'\s+')
ROW_JOIN_RE = re.compile(r"[/()\[\]\-?'’]*") # What may separate words that share one ESFM word number

HEADER_MARKERS = {'id','usfm','ide','rem','h','toc1','toc2','toc3','toca1','toca2','toca3','sts','cp'}
NOTE_MARKERS = {'f','fe','x','fig'} # Captured raw (not tokenised yet)
CAPTURED_MARKERS = {'va','vp','ca'} # Alternative/published numbers -- stored as attributes
ATTRIBUTE_SPANS = {'w','jmp','rb','xt'} # Character markers whose content can end with |attributes

TITLE_MARKERS = {'mt','mt1','mt2','mt3','mt4','mte','mte1','mte2','ms','ms1','ms2','ms3','mr','imt','imt1','imt2','imt3','imte'}
HEADING_MARKERS = {'s','s1','s2','s3','s4','sr','r','sp','qa','cl','periph','sd','sd1','sd2', 'is','is1','is2','iot'}
INTRO_MARKERS = {'ip','ipi','im','imi','ipq','imq','ipr','iq','iq1','iq2','ib','ili','ili1','ili2','io','io1','io2','io3','iex','ie'}
BODY_MARKERS = {'p','m','po','pr','cls','pmo','pm','pmc','pmr','pi','pi1','pi2','pi3','mi','nb','pc','ph','ph1','ph2','b',
                'q','q1','q2','q3','q4','qr','qc','qm','qm1','qm2','qd','d','li','li1','li2','li3','lh','lf','lim','lim1'}

# OET marks (see https://OpenEnglishTranslation.Bible/Resources/Formats): these aren't displayed text, so they become attributes.
# At the start of an \add field: why the words were added or changed (optionally after a ? for considerable doubt)
ADD_REASONS = { '+':'article', '=':'copula', '<':'object', '>':'implied', '≡':'repeated', '&':'owner',
                '@':'pronoun_to_name', '*':'name_to_pronoun', '#':'number', '%':'person', '^':'opposite',
                '!':'traditional_name', '$':'measure', '≈':'reworded' }
ADD_MARK_RE = re.compile( rf'(\??)([{re.escape( "".join( ADD_REASONS ) )}])|(\?)' )
# At the start of a line of poetry: how it relates to the line before
PARALLELISMS = { '≈':'synonymous', '^':'antithetic', '→':'synthetic' }
REORDERED_MARK = '⇔' # At the start of a verse whose two halves were swapped in translation
LINE_MARK_RE = re.compile( rf'\s*([{re.escape( "".join( PARALLELISMS ) + REORDERED_MARK )}])' )

SENTENCE_ENDERS = { 'Latn': '.?!', 'Grek': '.;', 'Hebr': '׃' }


def paragraph_kind( marker:str ) -> str:
    if marker in BODY_MARKERS: return 'body'
    if marker in HEADING_MARKERS: return 'heading'
    if marker in TITLE_MARKERS: return 'title'
    if marker in INTRO_MARKERS: return 'intro'
    return 'other'


class Document:
    """
    The parsed result for one source file.

    tokens: list of [before, text, after, features-dict]
    nodes: list of (type, start, end, name, attributes-dict) with end exclusive (and start==end allowed)
    notes: list of (anchor, type, raw) where anchor is the number of tokens preceding the note
    """
    def __init__( self ) -> None:
        self.tokens, self.nodes, self.notes = [], [], []
        self.headers, self.header_remarks = {}, []
        self.paragraphs = [] # (marker, kind, start, end, tokenless_text)
        self.warnings = {} # name → count
        self.unknown_markers = {} # name → count
        self.row_marks = 0
        self.marks = 0 # OET marks that were turned into attributes

    def warn( self, name:str ) -> None:
        self.warnings[name] = self.warnings.get( name, 0 ) + 1

    def plain_text( self ) -> str:
        """ Resynthesise the text (without markers) from the tokens -- used for the losslessness check. """
        parts = []
        for _marker, _kind, start, end, tokenlessText in self.paragraphs:
            parts.append( tokenlessText )
            parts.extend( before+text+after for before,text,after,_features in self.tokens[start:end] )
        return ''.join( parts )


class _Parser:
    def __init__( self, script:str, esfm:bool ) -> None:
        self.doc = Document()
        self.script, self.esfm = script, esfm
        self.paraAttributes = {}
        self.atVerseStart = False # No words yet since the \v
        self.gap = '' # Non-word text since the last token (or paragraph start)
        self.paraMarker = None
        self.paraStart = 0
        self.paraTokenlessText = ''
        self.spans = [] # Open character markers: [name, start, attributes-string]
        self.chapter, self.chapterStart, self.chapterAttributes = None, 0, {}
        self.verse, self.verseStart, self.verseEnd, self.verseAttributes = None, None, None, {}
        self.started = False # Have we got past the header lines?

    # Paragraphs
    def end_paragraph( self ) -> None:
        if self.paraMarker is None: return
        doc, tokens = self.doc, self.doc.tokens
        while self.spans:
            doc.warn( f'unclosed \\{self.spans[-1][0]}' )
            self.close_span( self.spans[-1][0] )
        gap = WHITESPACE_RE.sub( ' ', self.gap ); self.gap = ''
        tokenlessText = ''
        if len(tokens) > self.paraStart: tokens[-1][2] += gap.rstrip()
        else: tokenlessText = gap.strip()
        kind = paragraph_kind( self.paraMarker )
        doc.paragraphs.append( (self.paraMarker, kind, self.paraStart, len(tokens), tokenlessText) )
        attributes = {'kind':kind}; attributes.update( self.paraAttributes )
        if tokenlessText: attributes['text'] = tokenlessText
        doc.nodes.append( ('para', self.paraStart, len(tokens), self.paraMarker, attributes) )
        self.paraMarker = None

    def start_paragraph( self, marker:str ) -> None:
        self.end_paragraph()
        self.paraMarker, self.paraStart, self.paraAttributes = marker, len(self.doc.tokens), {}
        self.started = True
        if paragraph_kind( marker ) == 'other':
            self.doc.unknown_markers[marker] = self.doc.unknown_markers.get( marker, 0 ) + 1

    # Chapters and verses
    def end_verse( self ) -> None:
        if self.verse is None: return
        start = self.verseStart if self.verseStart is not None else len(self.doc.tokens)
        end = self.verseEnd if self.verseEnd is not None else start
        attributes = {'c':self.chapter, 'v':self.verse}; attributes.update( self.verseAttributes )
        self.doc.nodes.append( ('verse', start, end, f'{self.chapter}:{self.verse}', attributes) )
        self.verse, self.verseStart, self.verseEnd, self.verseAttributes = None, None, None, {}

    def end_chapter( self ) -> None:
        self.end_verse()
        if self.chapter is not None:
            self.doc.nodes.append( ('chapter', self.chapterStart, len(self.doc.tokens), self.chapter, self.chapterAttributes) )

    # Character markers
    def close_span( self, name:str ) -> None:
        for ix in range( len(self.spans)-1, -1, -1 ):
            if self.spans[ix][0] == name:
                _name, start, attributeString, attributes = self.spans.pop( ix )
                if name == 'w': return # Words are tokens, not spans
                end = len(self.doc.tokens)
                attributes.update( ATTRIBUTE_RE.findall( attributeString ) )
                if end > start:
                    self.doc.nodes.append( ('span', start, end, name, attributes) )
                else: self.doc.warn( f'empty \\{name}' )
                return
        self.doc.warn( f'unopened \\{name}*' )

    # Tokens
    def add_token( self, text:str, features:dict ) -> None:
        tokens = self.doc.tokens
        if self.paraMarker is None: # Text outside of any paragraph
            self.doc.warn( 'implicit paragraph' ) # e.g., a chapter that starts without a paragraph marker
            self.start_paragraph( 'p' )
        gap = WHITESPACE_RE.sub( ' ', self.gap ); self.gap = ''
        if len(tokens) == self.paraStart: before = gap.lstrip()
        else:
            ix = gap.rfind( ' ' ) # Everything up to and including the last space belongs to the previous word
            if ix == -1: ix = len(gap) - 1 # … and so does all of it if the two words are joined, e.g., he/it or of_the
            tokens[-1][2] += gap[:ix+1]
            before = gap[ix+1:]
        tokens.append( [before, text, '', features] )
        self.atVerseStart = False
        if paragraph_kind( self.paraMarker ) == 'body' and self.verse is not None:
            if self.verseStart is None: self.verseStart = len(tokens) - 1
            self.verseEnd = len(tokens)

    def add_row_number( self, rowNumber:int ) -> None:
        """ Handle an ESFM ¦number, which belongs to the word(s) immediately before it. """
        doc, tokens = self.doc, self.doc.tokens
        doc.row_marks += 1
        ix = len(tokens) - 1
        if ix < self.paraStart or 'row' in tokens[ix][3] or not ROW_JOIN_RE.fullmatch( self.gap ):
            doc.warn( 'orphan word number' ); return
        tokens[ix][3]['row'] = rowNumber
        while ix > self.paraStart and 'row' not in tokens[ix-1][3] \
        and not tokens[ix][0] and ROW_JOIN_RE.fullmatch( tokens[ix-1][2] ): # e.g., Yaʸsous/(Yəhōshūˊa)¦21572
            ix -= 1
            tokens[ix][3]['row'] = rowNumber

    def add_text( self, segment:str ) -> None:
        if not segment: return
        if not self.started:
            if segment.strip(): self.doc.warn( 'text in header' )
            return
        if self.spans and self.spans[-1][0] in ATTRIBUTE_SPANS and '|' in segment:
            segment, attributeString = segment.split( '|', 1 )
            self.spans[-1][2] += attributeString
            if self.spans[-1][0] == 'w': # The whole content is one word, whatever characters it contains (except spaces)
                self.add_words( segment, dict(ATTRIBUTE_RE.findall(attributeString)) )
                return
        elif self.spans and self.spans[-1][0] == 'w':
            self.add_words( segment, {} )
            return
        if self.esfm: segment = self.take_marks( segment )
        position = 0
        for match in TOKEN_RE.finditer( segment ):
            self.gap += segment[position:match.start()]
            position = match.end()
            if match.group( 1 ): self.add_row_number( int(match.group( 1 )) )
            else: self.add_token( match.group( 2 ), {} )
        self.gap += segment[position:]

    def add_words( self, segment:str, features:dict ) -> None:
        """ The content of a \\w: one word, or several with the same attributes, e.g., Spanish ‘el principio’ for one Greek word in the RV1909 """
        for ix, word in enumerate( segment.split() ):
            if ix: self.gap += ' '
            self.add_token( word, dict(features) )

    def take_marks( self, segment:str ) -> str:
        """ Remove any OET marks from the start of this text, recording what they mean. """
        doc = self.doc
        if self.spans and self.spans[-1][0] == 'add' and self.spans[-1][3].get( 'fresh' ): # Directly after the \add
            del self.spans[-1][3]['fresh']
            match = ADD_MARK_RE.match( segment )
            if match:
                self.spans[-1][3]['reason'] = ADD_REASONS[match.group( 2 )] if match.group( 2 ) else 'unclear'
                if match.group( 1 ): self.spans[-1][3]['uncertain'] = True
                doc.marks += 1
                return segment[match.end():]
        elif not self.spans and self.paraMarker is not None:
            atParagraphStart = len(doc.tokens) == self.paraStart and not self.gap.strip()
            while (atParagraphStart or self.atVerseStart) and (match := LINE_MARK_RE.match( segment )):
                mark = match.group( 1 )
                if mark == REORDERED_MARK:
                    if self.verse is None: doc.warn( 'reordered mark outside a verse' )
                    self.verseAttributes['reordered'] = True
                elif atParagraphStart: self.paraAttributes['parallelism'] = PARALLELISMS[mark]
                else: self.verseAttributes['parallelism'] = PARALLELISMS[mark]
                doc.marks += 1
                segment = segment[match.end():]
        return segment

    def parse( self, source:str ) -> Document:
        doc = self.doc
        source = source.lstrip( '\ufeff' ).replace( '\r\n', '\n' )
        closers = { match.group( 2 ) for match in MARKER_RE.finditer( source ) if match.group( 3 ) }
        whitespaceRunRE, wordRE = re.compile( r'[ \t]*(\S+)[ \t]?' ), re.compile( r'[ \t]*(\S+)' )
        position = 0
        while True:
            match = MARKER_RE.search( source, position )
            self.add_text( source[position:match.start() if match else len(source)] )
            if not match: break
            position = match.end()
            name, isCloser = match.group( 2 ), bool(match.group( 3 ))
            if isCloser:
                self.close_span( name ); continue

            if name in NOTE_MARKERS or name in CAPTURED_MARKERS:
                closer = f'\\{name}*'
                end = source.find( closer, position )
                if end == -1:
                    doc.warn( f'unclosed \\{name}' ); continue
                content = source[position:end].strip()
                position = end + len(closer)
                if name in NOTE_MARKERS: doc.notes.append( (len(doc.tokens), name, WHITESPACE_RE.sub( ' ', content )) )
                elif name == 'ca': self.chapterAttributes['alt'] = content
                else: self.verseAttributes['alt' if name=='va' else 'published'] = content
                continue

            if name in HEADER_MARKERS:
                end = source.find( '\n', position )
                if end == -1: end = len(source)
                value = source[position:end].strip()
                position = end
                if name == 'cp': self.chapterAttributes['published'] = value
                elif name != 'rem': doc.headers[name] = value
                elif self.started: doc.notes.append( (len(doc.tokens), 'rem', value) )
                else: doc.header_remarks.append( value )
                continue

            if name == 'c':
                self.end_paragraph(); self.end_chapter()
                numberMatch = wordRE.match( source, position )
                self.chapter, position = numberMatch.group( 1 ), numberMatch.end()
                self.chapterStart, self.chapterAttributes = len(doc.tokens), {}
                self.started = True
                continue
            if name == 'v':
                self.end_verse()
                if self.chapter is not None and self.paraMarker is not None and paragraph_kind( self.paraMarker ) == 'intro':
                    # A verse after a chapter's summary (e.g., the KJB-1611's \iex) without a paragraph marker of its own: the text starts here
                    doc.warn( 'verse in an introduction' )
                    self.start_paragraph( 'p' )
                numberMatch = whitespaceRunRE.match( source, position )
                self.verse, position = numberMatch.group( 1 ), numberMatch.end()
                self.atVerseStart = True
                continue

            if position < len(source) and source[position] in ' \n': position += 1 # The marker's own terminator
            if name in closers: self.spans.append( [name, len(doc.tokens), '', {'fresh':True} if name == 'add' and self.esfm else {}] )
            elif name[0] == 'z': # A custom marker that's never closed, e.g., OET-RV \z1 -- kept as a zero-width milestone
                doc.nodes.append( ('milestone', len(doc.tokens), len(doc.tokens), name, {}) )
            else: self.start_paragraph( name )

        self.end_paragraph(); self.end_chapter()
        doc.nodes.append( ('book', 0, len(doc.tokens), '', {}) )
        self.add_sections()
        self.add_sentences()
        doc.nodes.sort( key=lambda node: (node[1], -node[2], node[0]) )
        return doc

    def add_sections( self ) -> None:
        """ A section runs from one \\s1 (or \\s) heading to the next. """
        doc = self.doc
        starts = [ (start, ' '.join( token[1] for token in doc.tokens[start:end] ))
                        for marker,_kind,start,end,_text in doc.paragraphs if marker in ('s','s1') ]
        for ix, (start,title) in enumerate( starts ):
            end = starts[ix+1][0] if ix+1 < len(starts) else len(doc.tokens)
            doc.nodes.append( ('section', start, end, title, {}) )

    def add_sentences( self ) -> None:
        """ Body sentences can continue across paragraphs (e.g., lines of poetry), but intro sentences can't. """
        doc = self.doc
        for wantedKind in ('intro','body'):
            ranges = [ (start,end) for _marker,kind,start,end,_text in doc.paragraphs if kind == wantedKind ]
            doc.nodes.extend( sentence_nodes( doc.tokens, ranges, self.script, crossParagraphs=wantedKind == 'body' ) )


def sentence_nodes( tokens:list, ranges:list, script:str, crossParagraphs:bool ) -> list:
    """
    Heuristic sentence boundaries from punctuation (marked as derived, so they can be replaced by better data).

    ranges are the (start, end) token ranges of the paragraphs to consider, in order. Words outside them are ignored,
    so a sentence that's interrupted by a heading spans that heading.
    A sentence doesn't end inside parentheses, e.g., at the abbreviation in ‘Yeshua (Jesus; Grk. Yaʸsous)’.
    """
    nodes = []
    enders = SENTENCE_ENDERS.get( script, '.?!' )
    isLatin = script == 'Latn'
    indexes = [ ix for start,end in ranges for ix in range( start, end ) ]
    forcedEnds = set() if crossParagraphs else { end-1 for _start,end in ranges }
    sentenceStart, depth = None, 0
    for n, ix in enumerate( indexes ):
        if sentenceStart is None: sentenceStart = ix
        isLast = n+1 == len(indexes) or ix in forcedEnds
        depth = max( 0, depth + tokens[ix][0].count( '(' ) - tokens[ix][2].count( ')' ) )
        insideParentheses = depth > 0
        depth += tokens[ix][2].count( '(' )
        if isLast: depth = 0
        elif insideParentheses: continue
        if not isLast and not any( character in tokens[ix][2] for character in enders ): continue
        if not isLast and isLatin:
            nextCharacter = tokens[indexes[n+1]][1][0]
            if nextCharacter.islower() or nextCharacter.isdigit(): continue # e.g., an abbreviation or reference
        nodes.append( ('sentence', sentenceStart, ix+1, '', {'derived':'punctuation'}) )
        sentenceStart = None
    return nodes


def parse( source:str, script:str='Latn', esfm:bool=False ) -> Document:
    """ Parse the text of one USFM or ESFM file. (OET marks are only looked for in ESFM.) """
    return _Parser( script, esfm ).parse( source )


def reference_text( source:str, esfm:bool=False ) -> str:
    """
    An independent (regex-only) reduction of a source file to its bare text with all whitespace removed.

    Comparing this to Document.plain_text() (also with whitespace removed) proves that tokenising didn't lose or reorder any text.
    """
    text = source.lstrip( '\ufeff' ).replace( '\r\n', '\n' )
    text = re.sub( r'(?m)^\\(?:id|usfm|ide|rem|h|toca?\d|sts|cp)\b.*$', '', text )
    text = re.sub( r'\\(fe|fig|f|x)\b.*?\\\1\*', '', text, flags=re.DOTALL )
    text = re.sub( r'\\(va|vp|ca)\b.*?\\\1\*', '', text, flags=re.DOTALL )
    text = re.sub( r'\\(\+?)(w|jmp|rb|xt)\s([^|\\]*)\|[^\\]*(?=\\\1\2\*)', r'\3', text ) # (also nested, e.g., \+w inside \add)
    if esfm: # Remove the OET marks: after \add, and at the start of a line (after any paragraph and verse markers)
        text = re.sub( r'(\\\+?add )(?:\?[+=<>≡&@*#%^!$≈]?|[+=<>≡&@*#%^!$≈])', r'\1', text )
        text = re.sub( r'(?m)^((?:\\[a-z]+\d?[ \n]+)?(?:\\v \S+[ \n]+)?)[≈^→⇔]+', r'\1', text )
    text = re.sub( r'\\[cv][ \t]+\S+', '', text )
    text = re.sub( r'\\\+?[A-Za-z0-9]+(?:-[se])?\*?', '', text ) # Deliberately not MARKER_RE, so the two can't share a mistake
    text = re.sub( r'¦\d+', '', text )
    return WHITESPACE_RE.sub( '', text )
