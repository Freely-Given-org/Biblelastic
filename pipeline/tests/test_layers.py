"""
Integration test for word-table linking, the feature layer, and variant readings.
Run from the pipeline/ folder with: python3 -m unittest discover tests
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert( 0, str( Path( __file__ ).resolve().parent.parent ) )
from biblelastic_ingest import cli

USFM = r'''\id MRK
\mt1 Κατὰ Μᾶρκον
\c 1
\p
\v 1
\w Ἀρχὴ|lemma="ἀρχή" x-strong="G07460" x-morph="Gr,N,....NFS"\w*
\w τοῦ|lemma="ὁ" x-strong="G35880" x-morph="Gr,E,....GNS"\w*
\w Ἰησοῦ|lemma="Ἰησοῦς" x-strong="G24240" x-morph="Gr,N,....GMS"\w*.
'''
TABLE_HEADER = ['Ref','GreekWord','OETGlossWords','Probability','Tags']
TABLE_ROWS = [ (7, ['MRK_1:1w1','Ἀρχή','beginning','X','TStart']), # A different accent from the USFM
               (8, ['MRK_1:1w2','τοῦ','of the','X','']),
               (9, ['MRK_1:1w3','τοῦ','¬the','','']), # Not in the text
               (10, ['MRK_1:1w4','Ἰησοῦ','Yaʸsous','X','PJesus']),
               (11, ['MRK_1:1w5','Χριστοῦ','messiah','H','']) ] # Not in the text, and after the last word
EDITION = { 'id':'TEST', 'script':'Grek', 'features':['lemma','strong','morph','oet_row'],
            'row_table_word_column':'GreekWord', 'row_table_filter_column':'Probability', 'row_table_filter_values':['X'],
            'layer':{ 'id':'OET', 'columns':{'gloss':'OETGlossWords','tags':'Tags'} },
            'variants':{ 'id':'OET-variants', 'filter_values':['','H'], 'columns':{'ref':'Ref','status':'Probability','text':'GreekWord'} } }

def read( path ): return [ line.split( '\t' ) for line in path.read_text( encoding='utf-8' ).split( '\n' )[1:] if line ]


class LayerTests( unittest.TestCase ):
    def test_layers_and_variants( self ):
        with tempfile.TemporaryDirectory() as folderName:
            folder = Path( folderName )
            (folder / 'source.usfm').write_text( USFM, encoding='utf-8' )
            for subfolder in ('documents','layers/OET','layers/OET-variants'): (folder / subfolder).mkdir( parents=True )
            stats = cli.ingest_file( EDITION, str(folder / 'source.usfm'), 'MRK', (TABLE_HEADER, TABLE_ROWS), str(folder / 'documents'), str(folder / 'missing') )
            self.assertTrue( stats['text_ok'] )
            self.assertEqual( (stats['source_words'], stats['linked_to_table'], stats['linked_with_different_form']), (3, 3, 0) )
            tokens = read( folder / 'documents' / 'MRK.tokens.tsv' )
            self.assertEqual( [ token[-1] for token in tokens ], ['','','7','8','10'] ) # The two title words have no row
            features = (folder / 'layers' / 'OET' / 'MRK.features.tsv').read_text( encoding='utf-8' ).split( '\n' )[1:-1]
            self.assertEqual( features, ['\t', '\t', 'beginning\tTStart', 'of the\t', 'Yaʸsous\tPJesus'] ) # One row per token
            variants = read( folder / 'layers' / 'OET-variants' / 'MRK.variants.tsv' )
            self.assertEqual( variants, [ ['4','9','MRK_1:1w3','','τοῦ'], ['5','11','MRK_1:1w5','H','Χριστοῦ'] ] )


if __name__ == '__main__':
    unittest.main()
