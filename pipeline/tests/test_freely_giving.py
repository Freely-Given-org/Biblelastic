"""
Tests for adding the books of books.freely.giving (freely_giving.py), and for a book of untitled files, e.g., one prayer to a file (epub.py).
Run from the pipeline/ folder with: python3 -m unittest discover tests
"""
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert( 0, str( Path( __file__ ).resolve().parent.parent ) )
from biblelastic_ingest import epub, freely_giving

# The text of a book's page, as text_of() makes it (shortened)
PAGE = 'Freely Given Books Library People People Surprised by Hesed by Mark Feezell 2024 · 212 pages · CC0 Description “Hesed” is …'


class SurveyTests( unittest.TestCase ):
    def test_identifier( self ):
        self.assertEqual( freely_giving.identifier( 'the-dorean-principle' ), 'DoreanPrinciple' )
        self.assertEqual( freely_giving.identifier( 'a-divine-cordial' ), 'ADivineCordial' )
        self.assertEqual( freely_giving.identifier( 'the-1689-baptist-confession-of-faith' ), 'BaptistConfessionOfFaith1689' ) # Not starting with a number

    def test_licence( self ):
        self.assertEqual( freely_giving.licence_of( PAGE ), 'CC0' )
        self.assertEqual( freely_giving.licence_of( 'Cristina of Aspen Aisle 2018 · CC0 Description …' ), 'CC0' ) # No pages given
        self.assertEqual( freely_giving.licence_of( 'Institutes 1559 · 600 pages · Public Domain (translation 1845) Description …' ), 'Public Domain' )
        self.assertEqual( freely_giving.licence_of( 'Some Book 2020 · 100 pages · CC BY-SA 4.0 Description …' ), 'CC' )
        self.assertEqual( freely_giving.licence_of( 'No details' ), '' )

    def test_byline( self ):
        self.assertEqual( freely_giving.byline_of( PAGE, 'Surprised by Hesed' ), 'Mark Feezell' ) # Not ‘Hesed by Mark Feezell’
        page = 'People People The Anatomy of Simon Magus by Anonymous foreword by Conley Owens 1650 · 98 pages · CC0 Description'
        self.assertEqual( freely_giving.byline_of( page, 'The Anatomy of Simon Magus' ), 'Anonymous, foreword by Conley Owens' )
        page = 'People People A Book by Andrew Case with contributions by Conley Owens , Jonathan Melin 2026 · 272 pages · CC0 Description'
        self.assertEqual( freely_giving.byline_of( page, 'A Book' ), 'Andrew Case with contributions by Conley Owens, Jonathan Melin' )
        self.assertEqual( freely_giving.byline_of( 'People People Front · Spine · Back A Confession 1689 · 179 pages · CC0 Description', 'A Confession' ), '' )


CONTAINER = '<?xml version="1.0"?><container><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'
OPF = '''<package><manifest><item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/>{items}</manifest><spine toc="toc">{spine}</spine></package>'''
NCX = '<ncx><navMap><navPoint><navLabel><text>Prayers</text></navLabel><content src="p0.xhtml"/></navPoint></navMap></ncx>'
FILES = [ '<html><body><div>Prayers</div></body></html>',
          '<html><body><div>O Keeper of Your people,</div><div>Be our strength and our song (Psalm 118).</div></body></html>',
          '<html><body><div>God of Grace,</div><div>Thank You.</div></body></html>',
          '<html><body><div>for</div><div>A line that carries on from the last file.</div></body></html>' ]


class UntitledFilesTests( unittest.TestCase ):
    def test_file_titles( self ):
        """ A short line that starts a file (and isn't a sentence) is that file's title: each prayer is a section """
        with tempfile.TemporaryDirectory() as folder:
            path = Path( folder ) / 'prayers.epub'
            with zipfile.ZipFile( path, 'w' ) as book:
                book.writestr( 'META-INF/container.xml', CONTAINER )
                book.writestr( 'OEBPS/content.opf', OPF.format( items=''.join( f'<item id="p{n}" href="p{n}.xhtml" media-type="application/xhtml+xml"/>' for n in range( len(FILES) ) ),
                                                               spine=''.join( f'<itemref idref="p{n}"/>' for n in range( len(FILES) ) ) ) )
                book.writestr( 'OEBPS/toc.ncx', NCX )
                for n, text in enumerate( FILES ): book.writestr( f'OEBPS/p{n}.xhtml', text )
            parsed, _contents = epub.parse( str(path) )
        styles = [ (node[3], ''.join( before+word+after for before, word, after, _features in parsed.doc.tokens[node[1]:node[2]] ).strip() ) for node in parsed.doc.nodes if node[0] == 'para' ]
        self.assertEqual( [ text for style, text in styles if style == 'h3' ], ['O Keeper of Your people,', 'God of Grace,'] ) # Not ‘for’
