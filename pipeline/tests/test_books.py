"""
Tests for books (epub.py) and for finding Bible references in plain text (references.py).
Run from the pipeline/ folder with: python3 -m unittest discover tests
"""
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert( 0, str( Path( __file__ ).resolve().parent.parent ) )
from biblelastic_ingest import epub, references

CONTAINER = '<?xml version="1.0"?><container><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'
OPF = '''<package><manifest><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/><item id="two" href="two.xhtml" media-type="application/xhtml+xml"/>
<item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/><item id="css" href="style.css" media-type="text/css"/></manifest>
<spine toc="toc"><itemref idref="one"/><itemref idref="two"/></spine></package>'''
NCX = '''<ncx><docTitle><text>A Book</text></docTitle><navMap>
<navPoint><navLabel><text>Preface</text></navLabel><content src="one.xhtml"/></navPoint>
<navPoint><navLabel><text>Mark 1:1-20</text></navLabel><content src="two.xhtml"/>
  <navPoint><navLabel><text>1:9-11 Baptism</text></navLabel><content src="two.xhtml#b"/></navPoint></navPoint></navMap></ncx>'''
ONE = '<html><body><p>Why we <em>wrote</em> this.</p></body></html>'
TWO = '''<html><body><h1>Mark 1:1-20</h1><p>John appears (see Isa. 40:3; Mal 3:1).<sup><a epub:type="noteref" href="#n1">1</a></sup></p>
<p id="b">1:9-11 Baptism</p><p>Compare 1:14 and <span class="big">not a heading here</span>.</p><p><span class="big">Big Heading</span></p>
<aside epub:type="footnote" id="n1"><p>1 A note.</p></aside></body></html>'''
CSS = '.big { font-weight: bold; font-size: 22pt; }'


class ReferenceTests( unittest.TestCase ):
    def test_references( self ):
        cases = { 'John 3:16':['JHN 3:16'], '2 Tim. 3:1–9':['TI2 3:1-3:9'], 'Mark 2-3:6':['MRK 2:1-3:6'], 'Rom 8:28, 31-39; 9:1':['ROM 8:28', 'ROM 8:31-8:39', 'ROM 9:1'],
                  'Jude 5':['JDE 1:5'], 'Romans 8':['ROM 8'], 'Job 38–41':['JOB 38-41'], 'II Kings 2:11':['KI2 2:11'], 'Song of Songs 2:4':['SNG 2:4'] }
        for text, expected in cases.items(): self.assertEqual( [ passage for _start, _end, passages in references.find( text ) for passage in passages ], expected, text )
        for text in ('the Mark of a True Disciple', 'Enoch 1:9', 'I am 5:2 tall'): self.assertEqual( references.find( text ), [], text )

    def test_context( self ):
        self.assertEqual( references.find( 'Seeking service (1:21-28).', 'MRK' ), [ (17, 24, ['MRK 1:21-1:28']) ] )
        self.assertEqual( references.find( 'Never forget. (1-2) and (9:5)', 'JDE' ), [ (15, 18, ['JDE 1:1-1:2']) ] ) # Jude has no chapter 9
        self.assertEqual( references.find( 'Seeking service (1:21-28).' ), [] ) # No context: a bare reference isn't taken


class BookTests( unittest.TestCase ):
    def test_book( self ):
        with tempfile.TemporaryDirectory() as folderName:
            path = Path( folderName ) / 'book.epub'
            with zipfile.ZipFile( path, 'w' ) as book:
                for name, content in (('META-INF/container.xml', CONTAINER), ('OEBPS/content.opf', OPF), ('OEBPS/toc.ncx', NCX),
                                      ('OEBPS/one.xhtml', ONE), ('OEBPS/two.xhtml', TWO), ('OEBPS/style.css', CSS)):
                    book.writestr( name, content )
            parsed, contents = epub.parse( str(path), 'MRK' )
        self.assertEqual( [ (depth, label) for depth, label, _index in contents ], [ (1, 'Preface'), (1, 'Mark 1:1-20'), (2, '1:9-11 Baptism') ] )
        tokens = parsed.doc.tokens
        text = lambda start, end: ''.join( before+word+after for before,word,after,_features in tokens[start:end] )
        self.assertEqual( [ (entry[2], entry[4], text( entry[0], entry[1] )) for entry in parsed.entries ], [
            ('1', 'Preface', 'Why we wrote this.'),
            ('2', 'Mark 1:1-20', 'Mark 1:1-20John appears (see Isa. 40:3; Mal 3:1).1:9-11 BaptismCompare 1:14 and not a heading here.Big Heading1 A note.') ] )
        styles = [ (node[3], text( node[1], node[2] )) for node in parsed.doc.nodes if node[0] == 'para' ]
        self.assertEqual( styles, [ ('p', 'Why we wrote this.'), ('h1', 'Mark 1:1-20'), ('p', 'John appears (see Isa. 40:3; Mal 3:1).'), ('h2', '1:9-11 Baptism'),
                                    ('p', 'Compare 1:14 and not a heading here.'), ('h3', 'Big Heading'), ('note', '1 A note.') ] ) # The footnote marker is left out
        self.assertIn( ('span', 2, 3, 'ital', {}), parsed.doc.nodes ) # ‘wrote’
        anchors = sorted( (kind, passage, text( start, end )) for start, end, kind, passage in parsed.anchors )
        self.assertEqual( anchors, [ ('about', 'MRK 1:1-1:20', text( parsed.entries[1][0], parsed.entries[1][1] )), # The chapter, from its heading
                                     ('about', 'MRK 1:9-1:11', '1:9-11 BaptismCompare 1:14 and not a heading here.Big Heading1 A note.'), # Under the heading, to the next one as high (a lower one doesn't end it)
                                     ('cites', 'ISA 40:3', 'Isa. 40:3; '), ('cites', 'MAL 3:1', 'Mal 3:1).'), ('cites', 'MRK 1:14', '1:14 ') ] )


if __name__ == '__main__':
    unittest.main()
