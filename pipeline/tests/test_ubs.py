"""
Tests for the UBS dictionaries and handbooks (ubs.py).
Run from the pipeline/ folder with: python3 -m unittest discover tests
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert( 0, str( Path( __file__ ).resolve().parent.parent ) )
from biblelastic_ingest import ubs

HANDBOOK = '''<Thematic_Lexicon><ThemLex_Entry Key="2.8">
    <Title>Camel, dromedary</Title>
    <Sections><Section Type="entry" Content="references"><Heading>References:</Heading><LanguageSets>
        <LanguageSet Language="Hebrew"><Lemma>גָּמָל</Lemma><Transliteration>gamal</Transliteration>
            <References><Reference>00101201600044</Reference></References></LanguageSet>
    </LanguageSets></Section>
    <Section Type="entry"><Heading><b>Discussion:</b></Heading><Paragraphs>
        <Paragraph>Camels in <s>00101201600044</s> and <s>00302400100000-00302400400000</s>; see <l target="FAUNA:2.10">Cattle</l>.</Paragraph>
    </Paragraphs><BibleImages><BibleImage><Caption>A camel</Caption><Copyright>© Someone</Copyright></BibleImage></BibleImages></Section></Sections>
</ThemLex_Entry></Thematic_Lexicon>'''


class UBSTests( unittest.TestCase ):
    def test_references( self ):
        self.assertEqual( ubs.reference_parts( '01905001300008' ), ('PSA', 50, 13, 8) )
        self.assertEqual( ubs.reference_parts( 'G05800901300020' ), ('HEB', 9, 13, 20) ) # A letter in front is ignored
        self.assertIsNone( ubs.reference_parts( '06700100100000' ) )
        self.assertEqual( ubs.show_references( '00301101301000-00301101901000 G05800901300020 02600100501000-02600201401000' ), 'Lev 11:13-19; Heb 9:13; Ezek 1:5–2:14' )

    def test_cleaning_and_numbers( self ):
        self.assertEqual( ubs.clean( 'like {L:Ahashverosh<SDBH:אֲחַשְׁוֵרֹושׁ>}[a] (see {S:01100401900002}, {D:93.32}){N:001}; {A:ABD}' ),
                          'like Ahashverosh (see 1Kgs 4:19, §93.32), ABD' )
        self.assertEqual( (ubs.strong_number( 'c:d:H0776' ), ubs.strong_number( 'H1254a' ), ubs.strong_number( 'G07460' ), ubs.strong_number( 'G0746' )), ('776', '1254', '746', '746') )

    def test_alignment( self ):
        # UBS counts the Hebrew prefix ב separately (it has no partner), and the dictionary leaves out the fourth word
        words = ['7225', '1254', '430', '853']
        references = [ {'1119'}, {'7225'}, {'1254'}, {'430'} ]
        self.assertEqual( ubs.align( words, references ), [ (0, 1), (1, 2), (2, 3) ] )
        header = ['before', 'text', 'after', 'norm', 'lemma', 'strong']
        tokens = [ ['', 'Genesis', '', 'genesis', '', ''], ['', 'בְּ⁠רֵאשִׁ֖ית', ' ', '', 'רֵאשִׁית', 'b:H7225'], ['', 'בָּרָ֣א', ' ', '', 'בָּרָא', 'H1254a'] ]
        bookReferences = [ (1, 1, 2, '00100100100002', {'1119'}, 'H1'), (1, 1, 4, '00100100100004', {'7225'}, 'H2'), (1, 1, 6, '00100100100006', {'1254'}, 'H3') ]
        self.assertEqual( ubs.link_book( tokens, header, bookReferences, False ), { '00100100100004':1, '00100100100006':2 } )

    def test_handbook( self ):
        with tempfile.TemporaryDirectory() as folderName:
            path = Path( folderName ) / 'FAUNA.xml'
            path.write_text( HANDBOOK, encoding='utf-8' )
            # The word that the first reference points to is in the edition's 12:16, but UBS's own numbering is used for the other
            parsed, links = ubs.parse_handbook( str(path), 'Fauna', lambda reference: ('GEN', 12, 16) if reference.endswith( '00101201600044' ) else None )
        tokens = parsed.doc.tokens
        text = ' | '.join( ''.join( before+word+after for before,word,after,_features in tokens[start:end] ) for _name,_kind,start,end,_text in parsed.doc.paragraphs )
        self.assertEqual( text, 'Camel, dromedary | Hebrew: גָּמָל (gamal) — 1 reference | Discussion: | Camels in Gen 12:16 and Lev 24:1-4; see Cattle. | Picture: A camel (© Someone)' )
        self.assertEqual( parsed.entries, [ (0, len(tokens), '2.8', 'Article', 'Camel, dromedary') ] )
        self.assertEqual( [ anchor[2:] for anchor in parsed.anchors ], [ ('cites', 'GEN 12:16'), ('cites', 'LEV 24:1-24:4') ] )
        self.assertEqual( [ link[2:] for link in parsed.links ], [ ('see', 'Fauna 2.10') ] )
        self.assertEqual( links, [ ('00101201600044', '2.8') ] )


if __name__ == '__main__':
    unittest.main()
