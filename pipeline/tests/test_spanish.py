"""
Tests for the Spanish sources: Spanish Bible references (references.py), the Bible Aquifer's JSON (aquifer.py),
USFM words with several words in them, numbered file names, and sections taken from another edition (cli.py).
Run from the pipeline/ folder with: python3 -m unittest discover tests
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert( 0, str( Path( __file__ ).resolve().parent.parent ) )
from biblelastic_ingest import aquifer, cli, references, usfm


class SpanishReferenceTests( unittest.TestCase ):
    def test_spanish( self ):
        found = lambda text: [ (text[start:end], passages) for start, end, passages in references.find( text, language='spa' ) ]
        self.assertEqual( found( 'Como dice Juan 3:16 y Sal 119:105; ver 1 Co 13:4-7.' ),
                          [('Juan 3:16', ['JHN 3:16']), ('Sal 119:105', ['PSA 119:105']), ('1 Co 13:4-7', ['CO1 13:4-13:7'])] )
        self.assertEqual( found( 'Éxodo 20:1-17, Mateo 5:3; 6:9' ), [('Éxodo 20:1-17', ['EXO 20:1-20:17']), ('Mateo 5:3; 6:9', ['MAT 5:3', 'MAT 6:9'])] )
        self.assertEqual( found( 'Él es Dios 3 veces' ), [] )
        self.assertEqual( references.find( 'Juan 3:16' ), [] ) # Not in English text ('Juan' isn't an English name for John)


class AquiferTests( unittest.TestCase ):
    def test_passage( self ):
        extent = lambda BBB: (21, 25) if BBB == 'JHN' else None
        self.assertEqual( aquifer.passage( '43003016', '43003021', extent ), 'JHN 3:16-3:21' )
        self.assertEqual( aquifer.passage( '43003016', '43003016', extent ), 'JHN 3:16' )
        self.assertEqual( aquifer.passage( '43000000', '', extent ), 'JHN 1:1-21:25' ) # The whole book
        self.assertEqual( aquifer.passage( '99001001', '', extent ), None )
        self.assertEqual( aquifer.entry_name( 'Israel, Historia de' ), 'IsraelHistoriaDe' )
        self.assertEqual( aquifer.entry_name( 'Aarón' ), 'Aaron' )

    def test_parse( self ):
        notes = [ { 'reference_id':1, 'title':'Juan 3:16', 'index_reference':'43003016',
                    'content':'<p>Dios amó al <em>mundo</em> (<data class="bible-ref" data-start-ref="62004009" data-end-ref="62004010">1 Jn 4.9–10</data>; '
                              'ver <data class="resource-ref" data-content-id="2" data-resource-code="AquiferOpenStudyNotes">nota</data>).</p>',
                    'associations':{ 'passage':[{ 'start_ref':'43003016', 'end_ref':'43003016' }] } },
                  { 'reference_id':2, 'title':'Juan 3:17', 'index_reference':'43003017', 'content':'<p>El Hijo vino a salvar.</p>',
                    'associations':{ 'passage':[{ 'start_ref':'43003017', 'end_ref':'43003017' }] } } ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path( folder ) / 'AquiferOpenStudyNotes' / 'spa' / 'json' / '43.content.json'
            path.parent.mkdir( parents=True )
            path.write_text( json.dumps( notes ), encoding='utf-8' )
            parsed = aquifer.parse( [str(path)], lambda BBB: None )
        self.assertEqual( list( parsed ), ['JHN'] )
        items, sources = parsed['JHN']
        self.assertEqual( sources, ['43.content.json'] )
        self.assertEqual( [ (entry[2], entry[3], entry[4]) for entry in items.entries ], [('3:16', 'StudyNote', ''), ('3:17', 'StudyNote', '')] )
        self.assertFalse( items.text_differences )
        anchors = sorted( (kind, passage) for _start, _end, kind, passage in items.anchors )
        self.assertEqual( anchors, [('about', 'JHN 3:16'), ('about', 'JHN 3:17'), ('cites', 'JN1 4:9-4:10')] )
        self.assertEqual( [ link[3] for link in items.links ], ['JHN 3:17'] )
        self.assertIn( 'ital', [ node[3] for node in items.doc.nodes if node[0] == 'span' ] )


class SpanishBibleTests( unittest.TestCase ):
    def test_file_names( self ):
        self.assertEqual( cli.book_code( Path( '43JHNASBRT.SFM' ) ), 'JHN' )
        self.assertEqual( cli.book_code( Path( '141CHRV09.SFM' ) ), 'CH1' ) # (14, then 1CH)
        self.assertEqual( cli.book_code( Path( 'OET-RV_MRK.ESFM' ) ), 'MRK' )

    def test_several_words_in_one( self ):
        """ The RV1909 has one \\w for the Spanish words that translate one original word: each is a token of its own """
        doc = usfm.parse( '\\id JHN\n\\c 1\n\\p\n\\v 1 \\w EN|strong="G1722"\\w* \\w el principio|strong="G0746"\\w* \\add \\+w era|strong="G2258"\\+w*\\add*.\n', 'Latn', False )
        self.assertEqual( [ (token[1], token[3].get( 'strong' )) for token in doc.tokens ], [('EN', 'G1722'), ('el', 'G0746'), ('principio', 'G0746'), ('era', 'G2258')] )
        self.assertEqual( usfm.reference_text( '\\v 1 \\w el principio|strong="G0746"\\w* \\add \\+w era|strong="G2258"\\+w*\\add*', False ), 'elprincipioera' )

    def test_borrowed_sections( self ):
        with tempfile.TemporaryDirectory() as folder:
            theirs, ours = Path( folder ) / 'theirs.nodes.tsv', Path( folder ) / 'ours.nodes.tsv'
            header = 'type\tstart\tend\tname\tattributes\n'
            theirs.write_text( header + 'section\t0\t30\tFirst\t\nverse\t2\t10\t1:1\t\nverse\t10\t20\t1:2\t\nsection\t20\t40\tSecond\t\nverse\t22\t40\t1:3\t\n' )
            ours.write_text( header + 'book\t0\t50\t\t\nverse\t1\t12\t1:1\t\nverse\t12\t30\t1:2-3\t\nverse\t30\t50\t1:4\t\n' )
            self.assertEqual( cli.borrow_sections( theirs, ours ), 2 )
            sections = [ line.split( '\t' )[:3] for line in ours.read_text().splitlines() if line.startswith( 'section' ) ]
        # The second section starts at verse 3, which is in our combined verse 2-3, so it starts at our next verse after it begins (verse 4)
        self.assertEqual( sections, [['section', '1', '30'], ['section', '30', '50']] )
