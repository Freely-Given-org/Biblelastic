"""
Books (EPUB files): each top-level item of the book's table of contents becomes an entry, e.g., a chapter.

- Paragraphs are the book's blocks (paragraphs, list items, table cells, notes). A heading is an h1-h6 element,
  a block that the table of contents points to below its top level, or a block whose text the book's stylesheet makes bold and large.
- Bible references in the text (see references.py) become ‘cites’ anchors. A heading that names a passage (e.g., ‘Mark 1:1-20’,
  or ‘1:21-28 Jesus heals’ in a chapter about Mark) makes the text under it, up to the next heading of the same or a higher level, ‘about’ that passage.
- Footnote markers in the text are left out; the notes themselves are kept, as paragraphs of their own.
"""
import html
import html.parser
import posixpath
import re
import zipfile

from . import items, references, usfm

# Chapters and headings with these words are lists of things, not text: references in them aren't citations
LISTING_RE = re.compile( r'(?i)\b(index|contents|bibliography|glossary|abbreviations|sigla)\b' )
BLOCKS = {'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'dt', 'dd', 'td', 'th', 'div', 'blockquote', 'figcaption', 'caption', 'pre'}
SKIPPED = {'head', 'script', 'style', 'svg', 'math'}
NOTE_CONTAINERS = {'aside', 'dl'} # Footnotes are in these (with epub:type="footnote", or a footnote class)


class Block:
    def __init__( self, tag:str, ids:list ) -> None:
        self.tag, self.ids = tag, ids
        self.parts = [] # (text, italic, heading-like)
        self.note = False
        self.first = False # The first block of its file (a book's files are often one per chapter, section, or e.g., prayer)

    @property
    def text( self ) -> str: return ''.join( text for text, _italic, _large in self.parts )


class _Reader( html.parser.HTMLParser ):
    """ Reads one XHTML file of a book into blocks """
    def __init__( self, styles:dict ) -> None:
        super().__init__( convert_charrefs=True )
        self.styles = styles # class → (bold, size in points, italic)
        self.blocks, self.stack, self.block, self.pendingIds = [], [], None, []

    def _inside( self, tags:set ) -> bool: return any( tag in tags for tag, _attributes in self.stack )

    def handle_starttag( self, tag:str, attributes:list ) -> None:
        attributes = dict( attributes )
        if tag in ('br', 'img', 'hr', 'link', 'meta'):
            if tag == 'br' and self.block is not None: self.block.parts.append( (' ', False, False) )
            if attributes.get( 'id' ): self.pendingIds.append( attributes['id'] )
            return
        self.stack.append( (tag, attributes) )
        if attributes.get( 'id' ): self.pendingIds.append( attributes['id'] )
        if tag in BLOCKS:
            self._finish()
            self.block = Block( tag, self.pendingIds ); self.pendingIds = []
            classes = ' '.join( attributes.get( 'class', '' ) for _tag, attributes in self.stack )
            self.block.note = self._inside( NOTE_CONTAINERS ) or 'footnote' in classes or any( 'footnote' in attributes.get( 'epub:type', '' ) for _tag, attributes in self.stack )

    def handle_endtag( self, tag:str ) -> None:
        if tag in ('br', 'img', 'hr', 'link', 'meta'): return
        while self.stack:
            open_tag, _attributes = self.stack.pop()
            if open_tag in BLOCKS: self._finish()
            if open_tag == tag: break

    def handle_data( self, data:str ) -> None:
        data = data.replace( '\u00ad', '' ).replace( '\u200b', '' ) # Soft hyphens and zero-width spaces are only hints for line breaking
        if self._inside( SKIPPED ) or not data: return
        # Footnote markers: a superscript link (the notes themselves are kept where they are)
        if any( tag == 'a' and ('noteref' in attributes.get( 'epub:type', '' ) or 'note' in attributes.get( 'href', '' )) for tag, attributes in self.stack ) and self._inside( {'sup'} ):
            return
        if self.block is None:
            if not data.strip(): return
            self.block = Block( 'div', self.pendingIds ); self.pendingIds = []
        bold = large = italic = False
        size = 0.0
        for tag, attributes in self.stack:
            if tag in ('b', 'strong'): bold = True
            if tag in ('i', 'em'): italic = True
            for cls in attributes.get( 'class', '' ).split():
                styleBold, styleSize, styleItalic = self.styles.get( cls, (False, 0.0, False) )
                bold, italic, size = bold or styleBold, italic or styleItalic, max( size, styleSize )
        large = bold and size >= 13.5
        self.block.parts.append( (data, italic, large) )

    def _finish( self ) -> None:
        if self.block is not None and self.block.text.strip(): self.blocks.append( self.block )
        elif self.block is not None and self.block.ids and self.blocks is not None: self.pendingIds = self.block.ids + self.pendingIds
        self.block = None

    def close( self ) -> None:
        super().close()
        self._finish()


def stylesheet_rules( css:str ) -> dict:
    """ class → (bold, size in points, italic), from a book's stylesheet (only simple ‘.class { … }’ rules are understood) """
    rules = {}
    for selector, body in re.findall( r'([^{}]+)\{([^}]*)\}', css ):
        for name in re.findall( r'\.([\w-]+)\s*$', selector.strip() ) or []:
            bold = bool( re.search( r'font-weight:\s*(bold|[6-9]00)', body ) )
            italic = bool( re.search( r'font-style:\s*italic', body ) )
            size = re.search( r'font-size:\s*([\d.]+)\s*(pt|px|em|rem)', body )
            points = 0.0
            if size: points = float(size.group( 1 )) * {'pt':1, 'px':0.75, 'em':12, 'rem':12}[size.group( 2 )]
            rules[name] = (bold, points, italic)
    return rules


def read_epub( path:str ) -> tuple:
    """ Returns (blocks in reading order, table of contents) where the table of contents is [(depth, label, block index), …] """
    with zipfile.ZipFile( path ) as book:
        container = book.read( 'META-INF/container.xml' ).decode( 'utf-8' )
        opfPath = re.search( r'full-path="([^"]+)"', container ).group( 1 )
        opf = book.read( opfPath ).decode( 'utf-8' )
        folder = posixpath.dirname( opfPath )
        within = lambda href: posixpath.normpath( posixpath.join( folder, html.unescape( href ) ) )
        manifest = { item_id:within( href ) for item_id, href in re.findall( r'<item\b[^>]*?\bid="([^"]+)"[^>]*?\bhref="([^"]+)"', opf ) }
        manifest.update( { item_id:within( href ) for href, item_id in re.findall( r'<item\b[^>]*?\bhref="([^"]+)"[^>]*?\bid="([^"]+)"', opf ) } )
        styles = {}
        for name in book.namelist():
            if name.endswith( '.css' ): styles.update( stylesheet_rules( book.read( name ).decode( 'utf-8', 'replace' ) ) )
        blocks, positions = [], {} # positions: 'file' or 'file#id' → block index
        for item_id in re.findall( r'<itemref\b[^>]*\bidref="([^"]+)"', opf ):
            name = manifest.get( item_id )
            if not name or not name.endswith( ('.html', '.xhtml', '.htm') ): continue
            positions[name] = len(blocks)
            reader = _Reader( styles )
            reader.feed( book.read( name ).decode( 'utf-8', 'replace' ) )
            reader.close()
            if reader.blocks: reader.blocks[0].first = True
            for block in reader.blocks:
                for block_id in block.ids: positions[f'{name}#{block_id}'] = len(blocks)
                blocks.append( block )
            for pending in reader.pendingIds: positions.setdefault( f'{name}#{pending}', len(blocks) )
        # The table of contents (EPUB 2's NCX, which EPUB 3 books usually include too)
        contents = []
        ncxName = next( (name for name in manifest.values() if name.endswith( '.ncx' )), None )
        if ncxName:
            ncx = book.read( ncxName ).decode( 'utf-8' )
            ncxFolder = posixpath.dirname( ncxName )
            depth = 0
            for match in re.finditer( r'<navPoint\b|</navPoint>|<navLabel>\s*<text>(.*?)</text>\s*</navLabel>\s*<content\s+src="([^"]*)"', ncx, re.DOTALL ):
                if match.group( 0 ).startswith( '<navPoint' ): depth += 1
                elif match.group( 0 ) == '</navPoint>': depth -= 1
                else:
                    target = posixpath.normpath( posixpath.join( ncxFolder, html.unescape( match.group( 2 ) ) ) )
                    index = positions.get( target, positions.get( target.split( '#' )[0] ) )
                    if index is not None: contents.append( (depth, usfm.WHITESPACE_RE.sub( ' ', html.unescape( match.group( 1 ) ) ).strip(), index) )
    return blocks, contents


class BookParser( items._Parser ):
    def __init__( self, context:str|None ) -> None:
        super().__init__( {}, 'Latn' )
        self.context = context # The Bible book that bare references are in (e.g., MRK for a study of Mark), if any
        self.openAbout = [] # Headings that name a passage: (level, start token, passages)
        self.listing = 0 # While above 0: the level of the heading of an index, contents, bibliography, etc., where references aren't citations

    def close_about( self, level:int ) -> None:
        while self.openAbout and self.openAbout[-1][0] >= level:
            _level, start, passages = self.openAbout.pop()
            for passage in passages: self.parsed.anchors.append( (start, len(self.doc.tokens), 'about', passage) )

    def add_block( self, block:Block, style:str, level:int ) -> None:
        tokens = self.doc.tokens
        if level > 1: self.close_about( level )
        if level and self.listing and level <= self.listing: self.listing = 0
        if level and LISTING_RE.search( block.text ): self.listing = level
        start = len(tokens)
        self.start_paragraph( style, {} )
        italicStart = None
        for text, italic, _large in block.parts:
            if italic and italicStart is None: italicStart = len(tokens)
            elif not italic and italicStart is not None:
                if len(tokens) > italicStart: self.doc.nodes.append( ('span', italicStart, len(tokens), 'ital', {}) )
                italicStart = None
            self.add_text( text )
        if italicStart is not None and len(tokens) > italicStart: self.doc.nodes.append( ('span', italicStart, len(tokens), 'ital', {}) )
        self.end_paragraph()
        # References in the text: matched against the paragraph's words by character position
        text, offsets = '', []
        for ix in range( start, len(tokens) ):
            before, word, after, _features = tokens[ix]
            offsets.append( (len(text) + len(before), ix) ); text += before + word + after
        word_at = lambda position: next( (ix for offset, ix in reversed( offsets ) if offset <= position), start )
        for first, last, passages in references.find( text, self.context ):
            if self.listing: break # e.g., a Scripture index: its references aren't the book citing those passages
            if level == 1: break # (A chapter's title is taken from its entry in the contents)
            if level: # A heading that names a passage: what's under it is about that passage
                self.openAbout.append( (level, start, passages) ); break
            for passage in passages: self.parsed.anchors.append( (word_at( first ), word_at( max( first, last - 1 ) ) + 1, 'cites', passage) )


def parse( path:str, context:str|None=None ) -> tuple:
    """ Returns (parsed items, table of contents) for a book, with one entry for each top-level item of its contents """
    blocks, contents = read_epub( path )
    parser = BookParser( context )
    tokens = parser.doc.tokens
    top = min( (depth for depth, _label, _index in contents), default=1 )
    starts = { index:label for depth, label, index in contents if depth == top }
    headings = { index:depth - top + 1 for depth, _label, index in contents if depth > top } # Lower levels of the contents are headings
    if 0 not in starts: starts[0] = 'Front matter'
    names, entry, entryStart, entryTitle = 0, None, 0, ''
    def finish_entry() -> None:
        parser.close_about( 0 )
        if len(tokens) > entryStart: parser.parsed.entries.append( (entryStart, len(tokens), str(names), 'Chapter', entryTitle) )
    for index, block in enumerate( blocks ):
        if index in starts:
            finish_entry()
            names += 1
            entryStart, entryTitle = len(tokens), starts[index]
            parser.listing = 1 if LISTING_RE.search( entryTitle ) else 0
            # A chapter whose title names a passage (e.g., ‘Mark 1:1-20’) is about that passage
            found = references.find( entryTitle, parser.context )
            if found: parser.openAbout.append( (1, entryStart, found[0][2]) )
        level = 0
        if block.tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'): level = int(block.tag[1])
        elif index in headings: level = headings[index]
        elif not block.note and all( large for text, _italic, large in block.parts if text.strip() ) and len(block.text) < 150: level = 3
        # A short line that starts a file, and isn't a sentence, is that file's title, e.g., ‘God of Grace,’ for a prayer in a book of them
        elif block.first and index not in starts and not block.note and len(block.text.strip()) <= 50 and not block.text.strip()[:1].islower() and not re.search( r'[.!?:;”"’)\]]$', block.text.strip() ): level = 3
        if index in starts and (level or block.text.strip() == entryTitle): level = 1 # The chapter's own title
        style = 'note' if block.note else f'h{level}' if level else 'li' if block.tag == 'li' else 'p'
        parser.add_block( block, style, level )
    finish_entry()
    return parser.finish(), contents
