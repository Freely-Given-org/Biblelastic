"""
Tests that Biblelastic uses BibleOrgSys's book codes everywhere (see biblelastic_ingest/book_codes.py). Run from the pipeline/ folder with:
python3 -m unittest discover tests
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert( 0, str( Path( __file__ ).resolve().parent.parent ) )
from biblelastic_ingest import book_codes, items, references, ubs, web_pages

REPOSITORY = Path( __file__ ).resolve().parent.parent.parent


class BookCodeTests( unittest.TestCase ):
    def test_conversion( self ):
        for given, expected in (('1Co', 'CO1'), ('1CO', 'CO1'), ('CO1', 'CO1'), ('4MA', 'MA4'), ('MA4', 'MA4'), ('1ES', 'GES'), ('2ES', 'LES'),
                                ('DAG', 'DNG'), ('ODA', 'ODE'), ('S3Y', 'PAZ'), ('ADE', 'ESA'), ('JUD', 'JDE'), ('jhn', 'JHN'), ('FRT', 'FRT')):
            self.assertEqual( book_codes.bos( given ), expected, given )
        with self.assertRaises( ValueError ): book_codes.bos( 'XYZ' )

    def test_bos_codes_start_with_a_letter( self ):
        self.assertFalse( [ code for code in book_codes.BOS_CODES if not code[0].isalpha() ] )

    def test_the_pipeline_tables( self ):
        """ Every book code that the pipeline's own tables give is a BOS one """
        for name, codes in (('items.BOOKS', items.BOOKS.values()), ('references.BOOKS', references.BOOKS.values()),
                            ('references.SPANISH_BOOKS', references.SPANISH_BOOKS.values()), ('ubs.BOOKS', ubs.BOOKS),
                            ('web_pages.OT_BOOKS', web_pages.OT_BOOKS), ('web_pages.NT_BOOKS', web_pages.NT_BOOKS)):
            self.assertFalse( sorted( set( codes ) - book_codes.BOS_CODES ), name )

    def test_the_compiler_and_the_app( self ):
        """ The compiler's book order and the app's book names use BOS codes """
        order = re.search( r'const BOOK_ORDER: &\[&str\] = &\[(.*?)\];', (REPOSITORY / 'crates/biblelastic-cli/src/compile.rs').read_text( encoding='utf-8' ), re.DOTALL )
        self.assertFalse( sorted( set( re.findall( r'"(\w+)"', order.group( 1 ) ) ) - book_codes.BOS_CODES ), 'compile.rs BOOK_ORDER' )
        names = re.search( r'const _books = <String, List<String>>\{(.*?)\n\};', (REPOSITORY / 'app/lib/strings.dart').read_text( encoding='utf-8' ), re.DOTALL )
        self.assertFalse( sorted( set( re.findall( r"'(\w+)':", names.group( 1 ) ) ) - book_codes.BOS_CODES ), 'strings.dart _books' )

    def test_the_engine_has_the_same_table( self ):
        rust = (REPOSITORY / 'crates/biblelastic-engine/src/reference.rs').read_text( encoding='utf-8' )
        table = re.search( r'pub const USFM_TO_BOS: &\[\(&str, &str\)\] = &\[(.*?)\n\];', rust, re.DOTALL ).group( 1 )
        self.assertEqual( dict( re.findall( r'\("(\w+)", "(\w+)"\)', table ) ), book_codes.USFM_TO_BOS )
