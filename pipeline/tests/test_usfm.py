"""
Tests for the USFM/ESFM tokeniser. Run from the pipeline/ folder with: python3 -m unittest discover tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert( 0, str( Path( __file__ ).resolve().parent.parent ) )
from biblelastic_ingest import normalise, usfm

ESFM = r'''\id MRK
\rem WORDTABLE OET-LV_NT_word_table.tsv
\h Markos
\mt1 Markos
\c 1
\s1 A heading
\p
\v 1 \add +The¦21569\add*_beginning¦21569 of¦21572_\nd Yaʸsous/(Yəhōshūˊa)¦21572\nd*, son¦21575.\f + \fr 1:1 \ft A note¦9.\f*
\rem /s1 Another heading
\v 2 As¦21580 plant[s]¦149 Aʸsaias/(Yəshaˊ\sup yāh\sup*)¦21585 said, “Go.” He didn't.
'''

MARKS = r'''\id PSA
\c 1
\q1
\v 1 Yahweh is \add ≈my hope\add*.
\q1 ≈He gives \add ?@Dawid\add* \add !(David)\add* comfort,
\q1 ^but \add ?maybe\add* not \add (always)\add*.
\v 2 ⇔Then →he left.
\q1
\v 3 →And 5 ^ 2 is 25.
'''

USFM = r'''\id GEN unfoldingWord® Hebrew Bible
\mt Genesis
\c 32
\ca 31\ca*
\p
\v 1 \va 31:55\va*
\w עַל|lemma="עַל" strong="H5921a" x-morph="He,R"\w*־\w פְּנֵ֣י|lemma="פָּנִים" strong="H6440" x-morph="He,Ncbpc"\w*
\w הָ⁠אָֽרֶץ|lemma="אֶרֶץ" strong="d:H0776" x-morph="He,Td:Ncbsa"\w*׃
'''

def words( doc ): return [ token[1] for token in doc.tokens ]
def nodes( doc, nodeType ): return [ node for node in doc.nodes if node[0] == nodeType ]


class ESFMTests( unittest.TestCase ):
    def setUp( self ): self.doc = usfm.parse( ESFM, 'Latn', True )

    def test_text_is_not_lost( self ):
        self.assertEqual( usfm.WHITESPACE_RE.sub( '', self.doc.plain_text() ), usfm.reference_text( ESFM, True ) )

    def test_word_numbers( self ):
        rows = { token[1]:token[3].get( 'row' ) for token in self.doc.tokens }
        self.assertEqual( rows['The'], 21569 )
        self.assertEqual( rows['Yaʸsous'], 21572 ) # Shares the number that follows the bracketed alternative
        self.assertEqual( rows['Yəhōshūˊa'], 21572 )
        self.assertEqual( (rows['plant'], rows['s']), (149, 149) )
        self.assertEqual( (rows['Aʸsaias'], rows['Yəshaˊ'], rows['yāh']), (21585, 21585, 21585) ) # Across a character marker
        self.assertIsNone( rows['said'] )
        self.assertEqual( self.doc.row_marks, 8 ) # The one inside the footnote isn't counted
        self.assertFalse( self.doc.warnings )

    def test_before_and_after( self ):
        tokens = { token[1]:token for token in self.doc.tokens }
        self.assertEqual( tokens['The'][0], '' ) # The + mark isn't text
        self.assertEqual( tokens['The'][2], '_' )
        self.assertEqual( tokens['Yaʸsous'][2], '/(' )
        self.assertEqual( tokens['said'][2], ', ' )
        self.assertEqual( tokens['Go'][0], '“' )
        self.assertEqual( tokens['Go'][2], '.” ' )
        self.assertIn( "didn't", tokens )

    def test_nodes( self ):
        self.assertEqual( [ (node[3], words( self.doc )[node[1]:node[2]][0]) for node in nodes( self.doc, 'verse' ) ], [('1:1','The'), ('1:2','As')] )
        self.assertEqual( [ node[3] for node in nodes( self.doc, 'para' ) ], ['mt1','s1','p'] )
        self.assertEqual( { node[3] for node in nodes( self.doc, 'span' ) }, {'add','nd','sup'} )
        self.assertEqual( [ node[4] for node in nodes( self.doc, 'span' ) if node[3] == 'add' ], [{'reason':'article'}] )
        self.assertEqual( [ node[3] for node in nodes( self.doc, 'section' ) ], ['A heading'] )
        self.assertEqual( len( nodes( self.doc, 'sentence' ) ), 3 )

    def test_notes_and_headers( self ):
        self.assertEqual( [ note[1] for note in self.doc.notes ], ['f','rem'] )
        self.assertEqual( self.doc.headers['h'], 'Markos' )
        self.assertEqual( self.doc.header_remarks, ['WORDTABLE OET-LV_NT_word_table.tsv'] )


class OETMarkTests( unittest.TestCase ):
    def setUp( self ): self.doc = usfm.parse( MARKS, 'Latn', True )

    def test_marks_are_not_text( self ):
        self.assertEqual( usfm.WHITESPACE_RE.sub( '', self.doc.plain_text() ), usfm.reference_text( MARKS, True ) )
        self.assertEqual( self.doc.plain_text(), 'Yahweh is my hope.He gives Dawid (David) comfort,but maybe not (always). Then →he left.And 5 ^ 2 is 25.' )
        self.assertEqual( self.doc.marks, 8 )

    def test_add_reasons( self ):
        spans = [ (' '.join( words( self.doc )[node[1]:node[2]] ), node[4]) for node in nodes( self.doc, 'span' ) ]
        self.assertEqual( spans, [ ('my hope', {'reason':'reworded'}), ('Dawid', {'reason':'pronoun_to_name', 'uncertain':True}),
                                   ('David', {'reason':'traditional_name'}), ('maybe', {'reason':'unclear'}), ('always', {}) ] )

    def test_line_marks( self ):
        paragraphs = [ node[4].get( 'parallelism' ) for node in nodes( self.doc, 'para' ) ]
        self.assertEqual( paragraphs, [None, 'synonymous', 'antithetic', 'synthetic'] )
        verses = { node[3]:{ key:value for key,value in node[4].items() if key not in 'cv' } for node in nodes( self.doc, 'verse' ) }
        self.assertEqual( verses, { '1:1':{}, '1:2':{'reordered':True}, '1:3':{} } ) # A mark that's not at the start stays as text

    def test_marks_are_only_for_esfm( self ):
        self.assertIn( '≈my', usfm.parse( MARKS, 'Latn' ).plain_text() )


class USFMTests( unittest.TestCase ):
    def setUp( self ): self.doc = usfm.parse( USFM, 'Hebr' )

    def test_words_and_attributes( self ):
        self.assertEqual( len( self.doc.tokens ), 4 ) # Including the title
        before, text, after, features = self.doc.tokens[1]
        self.assertEqual( (text, after, features['strong'], features['x-morph']), ('עַל', '־', 'H5921a', 'He,R') )
        self.assertEqual( self.doc.tokens[3][2], '׃' )
        self.assertEqual( usfm.WHITESPACE_RE.sub( '', self.doc.plain_text() ), usfm.reference_text( USFM ) )

    def test_alternative_numbers( self ):
        self.assertEqual( nodes( self.doc, 'verse' )[0][4], {'c':'32', 'v':'1', 'alt':'31:55'} )
        self.assertEqual( nodes( self.doc, 'chapter' )[0][4], {'alt':'31'} )


class NormaliseTests( unittest.TestCase ):
    def test_normalisers( self ):
        self.assertEqual( normalise.greek( 'Ἀρχὴ' ), 'αρχη' )
        self.assertEqual( normalise.greek( 'Χριστός' ), 'χριστοσ' )
        self.assertEqual( normalise.hebrew_consonants( 'הָ⁠אָֽרֶץ' ), 'הארץ' )
        self.assertEqual( normalise.latin( 'Yəhōshūˊa' ), 'yəhoshua' )

    def test_match_sequences( self ):
        self.assertEqual( normalise.match_sequences( list('abcdef'), list('abXdef') ), [(0,0),(1,1),(2,2),(3,3),(4,4),(5,5)] ) # Substitution
        self.assertEqual( normalise.match_sequences( list('abcdef'), list('abdef') ), [(0,0),(1,1),(3,2),(4,3),(5,4)] ) # Deletion
        self.assertEqual( normalise.match_sequences( list('abdef'), list('abcdef') ), [(0,0),(1,1),(2,3),(3,4),(4,5)] ) # Insertion


if __name__ == '__main__':
    unittest.main()
