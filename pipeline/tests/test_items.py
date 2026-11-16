"""
Tests for commentaries and dictionaries (works made of items).
Run from the pipeline/ folder with: python3 -m unittest discover tests
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert( 0, str( Path( __file__ ).resolve().parent.parent ) )
from biblelastic_ingest import cli, items

DOCUMENTS = { 'StudyNote':'*', 'BookIntro':'Intros', 'Article':'Articles', 'Textbox':'Textboxes' }
NOTES = '''<items release="1">
<item name="IJn.4.8-9" typename="StudyNote" product="Test">
<refs>1Jn.4.8-9</refs>
<body>
<p class="sn-text"><span class="sn-ref"><a href="?bref=1Jn.4.8-9">4:8-9</a></span> <span class="sn-excerpt">God is love:</span> See <a href="?bref=Rom.5.8">Rom 5:8</a>;
<a href="?bref=John.3.16,18-4.2">John 3:16, 18–4:2</a> (and the <a href="?item=1Jn_BookIntro_Test">introduction</a>). It&#x2019;s true.</p>
</body>
</item>
<item name="IJnIntro" typename="BookIntro" product="Test">
<title>1 John</title>
<refs>1Jn.1.1-5.21</refs>
<body>
<p class="intro-h1">Setting</p>
<p class="intro-body">Written late. <a href="?bref=Gen.1.3-2">Bad</a></p>
</body>
</item>
<item name="A" typename="DictionaryLetter" product="Test"><body><p class="toc">Aaron</p></body></item>
</items>'''
ARTICLES = '''<items><item typename="Article" product="Test" name="AaronsRod">
  <title>Aaron’s Rod*</title>
  <body>
<p class="h1">AARON’S ROD*</p>
<p class="fl">A staff. <span class="ital">See</span> <a href="?item=Aaron_Article_Test">Aaron</a>.</p>
<include_items src="../Textboxes/Textboxes.xml" name="TheRod"/>
<table><tr><td><p class="td">Cell</p></td></tr></table>
  </body>
</item></items>'''


class ItemTests( unittest.TestCase ):
    def test_references( self ):
        for text, expected in ( ('Gen.1.1', ['GEN 1:1']), ('Gen.1.3-5', ['GEN 1:3-1:5']), ('Gen.1.1-2.3', ['GEN 1:1-2:3']), ('1Chr.8.23,28', ['CH1 8:23', 'CH1 8:28']),
                                ('Exod.3.1-4:17', ['EXO 3:1-4:17']), ('1Cor.10.16b-17', ['CO1 10:16-10:17']), ('John.3.16, 18-4.2', ['JHN 3:16', 'JHN 3:18-4:2']),
                                ('Gen.50.1-Exod.1.7', ['GEN 50:1-999:999', 'EXO 1:1-1:7']) ):
            self.assertEqual( [ items.show_reference( *reference ) for reference in items.parse_references( text ) ], expected, text )
        for text in ('', 'Gen.1.3-2', 'Nobody.1.1', 'Ecclus.49', '2Chr.28.12_StudyNote_Filament'):
            self.assertRaises( ValueError, items.parse_references, text )

    def test_locations( self ):
        self.assertEqual( items.locate( 'StudyNote', 'IICor.1.1-2.3', DOCUMENTS ), ('CO2', '1:1-2:3') )
        self.assertEqual( items.locate( 'StudyNote', 'Isa.1.1', DOCUMENTS ), ('ISA', '1:1') )
        self.assertEqual( (items.locate( 'BookIntro', 'IJnIntro', DOCUMENTS ), items.locate( 'BookIntro', '1Jn', DOCUMENTS )), (('Intros','JN1'), ('Intros','JN1')) )
        self.assertEqual( (items.locate( 'Article', 'Aaron', DOCUMENTS ), items.locate( 'DictionaryLetter', 'A', DOCUMENTS )), (('Articles','Aaron'), None) )
        self.assertEqual( [ document for document,_source in items.split_items( NOTES, DOCUMENTS ) ], ['JN1','Intros'] )

    def test_study_note( self ):
        parsed = items.parse( [ source for _document,source in items.split_items( NOTES, DOCUMENTS ) ][:1], DOCUMENTS )
        tokens = parsed.doc.tokens
        self.assertEqual( ''.join( before+text+after for before,text,after,_features in tokens ),
                          '4:8-9 God is love: See Rom 5:8; John 3:16, 18–4:2 (and the introduction). It’s true.' )
        self.assertEqual( parsed.entries, [ (0, len(tokens), '4:8-9', 'StudyNote', '') ] )
        # The reference at the start of the note isn't an anchor of its own, and a list of references gives several
        self.assertEqual( parsed.anchors, [ (7,10,'cites','ROM 5:8'), (10,16,'cites','JHN 3:16'), (10,16,'cites','JHN 3:18-4:2'), (0,21,'about','JN1 4:8-4:9') ] )
        self.assertEqual( parsed.links, [ (18,19,'see','Intros JN1') ] )
        self.assertEqual( [ node[:4] for node in parsed.doc.nodes if node[0] != 'sentence' ],
                          [ ('para',0,21,'sn-text'), ('span',0,3,'sn-ref'), ('span',3,6,'sn-excerpt') ] )
        self.assertEqual( [ node[1:3] for node in parsed.doc.nodes if node[0] == 'sentence' ], [ (0,19), (19,21) ] )
        self.assertEqual( (parsed.text_differences, parsed.bad_references), ([], []) )

    def test_documents( self ):
        with tempfile.TemporaryDirectory() as folderName:
            folder = Path( folderName )
            edition = { 'script':'Latn', 'item_documents':DOCUMENTS }
            stats = cli.ingest_items( edition, 'Intros', ['Notes.xml'], [ source for _document,source in items.split_items( NOTES, DOCUMENTS ) ][1:], str(folder) )
            self.assertEqual( (stats['text_ok'], stats['entries'], stats['anchors'], stats['bad_references'], stats['entry_locations']), (True, 1, {'about':1}, ['Gen.1.3-2'], ['Intros JN1']) )
            self.assertEqual( (folder / 'Intros.entries.tsv').read_text( encoding='utf-8' ), 'start\tend\tname\ttype\ttitle\n0\t4\tJN1\tBookIntro\t1 John\n' )
            self.assertEqual( (folder / 'Intros.nodes.tsv').read_text( encoding='utf-8' ).split( '\n' )[1:3],
                              ['para\t0\t1\tintro-h1\t{"kind": "heading"}', 'para\t1\t4\tintro-body\t{"kind": "body"}'] )
            stats = cli.ingest_items( edition, 'Articles', ['A.xml'], [ source for _document,source in items.split_items( ARTICLES, DOCUMENTS ) ], str(folder) )
            self.assertEqual( (stats['text_ok'], stats['tokens'], stats['link_targets']), (True, 7, ['Articles Aaron', 'Textboxes TheRod']) )
            self.assertEqual( (folder / 'Articles.links.tsv').read_text( encoding='utf-8' ).split( '\n' )[1:3], ['5\t6\tsee\tArticles Aaron', '6\t6\tinclude\tTextboxes TheRod'] )
            self.assertEqual( (folder / 'Articles.tokens.tsv').read_text( encoding='utf-8' ).split( '\n' )[1:3], ['\tAARON’S\t \taaron’s', '\tROD\t*\trod'] )


if __name__ == '__main__':
    unittest.main()
