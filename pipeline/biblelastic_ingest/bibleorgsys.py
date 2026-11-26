""" Convert the Bibles that aren't in USFM or ESFM (e.g., the BSB's word table, and Zefania XML) into USFM or ESFM, with BibleOrgSys,
    so that the ingest can read them like any other.

Each edition with a `convert` table in the registry is read with that BibleOrgSys reader, and written (with BibleOrgSys's USFM 3 writer)
into the folder that its `files` pattern names, as ID_BBB.usfm (or .ESFM, if its format is ESFM).
    convert = { reader = "CSVBible", from = "OpenBibleData/…/bsb_tables.tsv", remove = ["[", "]"] }

This needs BibleOrgSys and its Rust module, so it runs in OpenBibleData's environment, from the pipeline folder:
    ../../OpenBibleData/.venv/bin/python -m biblelastic_ingest.bibleorgsys [--editions BSB,Wycl]
"""
import argparse
import os
import re
import sys
import tempfile
import tomllib
from pathlib import Path

PIPELINE_FOLDER = Path( __file__ ).resolve().parent.parent
REPOSITORY_FOLDER = PIPELINE_FOLDER.parent


def convert( edition:dict, sourceRoot:Path ) -> int:
    """ Write an edition's books as USFM or ESFM, into the folder of its files pattern. Returns how many books were written. """
    from BibleOrgSys.Formats import CSVBible, ZefaniaXMLBible # (Only importable in BibleOrgSys's environment)
    settings = edition['convert']
    readers = { 'CSVBible':CSVBible.CSVBible, 'ZefaniaXMLBible':ZefaniaXMLBible.ZefaniaXMLBible }
    bible = readers[settings['reader']]( str( sourceRoot / settings['from'] ), givenName=edition['name'], givenAbbreviation=edition['id'], encoding='utf-8' )
    bible.loadBooks()
    pattern = sourceRoot / edition['files'][0]
    outputFolder = pattern.parent
    outputFolder.mkdir( parents=True, exist_ok=True )
    for old in outputFolder.glob( pattern.name ): old.unlink()
    suffix = 'ESFM' if edition.get( 'format' ) == 'ESFM' else 'usfm'
    count = 0
    with tempfile.TemporaryDirectory() as written:
        bible.toUSFM3( Path( written ) )
        for path in sorted( Path( written ).glob( '*.usfm' ) ):
            text = path.read_text( encoding='utf-8' )
            BBB = re.match( r'\\id (\w+)', text ).group( 1 ).upper()
            text = re.sub( r'^\\id \w+', f'\\\\id {BBB}', text )
            for unwanted in settings.get( 'remove', [] ): text = text.replace( unwanted, '' )
            if not re.search( r'^\\(p|m|q\d?|pi\d?|li\d?)\b', text, re.MULTILINE ): # No paragraphs at all (e.g., from Zefania XML): one for each chapter
                text = re.sub( r'^(\\c \d+)$', r'\1\n\\p', text, flags=re.MULTILINE )
            (outputFolder / f"{edition['id']}_{BBB}.{suffix}").write_text( text, encoding='utf-8' )
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser( prog='biblelastic_ingest.bibleorgsys', description=__doc__.split( '\n' )[0] )
    parser.add_argument( '--registry', type=Path, default=PIPELINE_FOLDER / 'sources.toml' )
    parser.add_argument( '--source-root', type=Path, default=Path( os.environ.get( 'BIBLELASTIC_SOURCE_ROOT', REPOSITORY_FOLDER.parent ) ) )
    parser.add_argument( '--editions', help='Comma-separated edition ids (default: every one with a convert table)' )
    parser.add_argument( '--bibleorgsys', type=Path, default=REPOSITORY_FOLDER.parent / 'BibleOrgSys', help='Where BibleOrgSys is' )
    arguments = parser.parse_args()
    sys.path.insert( 0, str( arguments.bibleorgsys ) )
    from BibleOrgSys import BibleOrgSysGlobals
    sys.argv = sys.argv[:1] # (BibleOrgSys reads the command line too)
    BibleOrgSysGlobals.addStandardOptionsAndProcess( argparse.ArgumentParser() )

    registry = tomllib.loads( arguments.registry.read_text( encoding='utf-8' ) )
    wanted = set( arguments.editions.split( ',' ) ) if arguments.editions else None
    for edition in registry['edition']:
        if 'convert' not in edition or wanted and edition['id'] not in wanted: continue
        print( f"{edition['id']}: {convert( edition, arguments.source_root )} books written" )
    return 0


if __name__ == '__main__':
    sys.exit( main() )
