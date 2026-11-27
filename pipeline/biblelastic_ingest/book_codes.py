""" Book codes: Biblelastic uses BibleOrgSys's (BOS) codes for books everywhere (e.g., SA1, CO1, MA4, GES, DNG: each starts with a letter),
    and converts any other (e.g., USFM's 1SA, 1CO, 4MA, 1ES, DAG) to one of those as soon as it comes in.

USFM_TO_BOS and BOS_CODES are written from BibleOrgSys's BibleBooksCodes table (where a USFM code could be several BOS books, the first is taken).
To write them again (e.g., when BibleOrgSys's table changes), from the pipeline folder:
    python3 -m biblelastic_ingest.book_codes ../../BibleOrgSys/BibleOrgSys/DataFiles/DerivedFiles/BibleBooksCodes_Tables.json
"""
import json
import re
import sys
from pathlib import Path

# The USFM codes that aren't BOS codes, and the BOS code for each
USFM_TO_BOS = {
    '1CH':'CH1', '1CL':'CL1', '1CO':'CO1', '1ES':'GES', '1JN':'JN1', '1KI':'KI1', '1MA':'MA1', '1MQ':'MQ1', '1PE':'PE1', '1SA':'SA1',
    '1TH':'TH1', '1TI':'TI1', '2BA':'BA2', '2CH':'CH2', '2CL':'CL2', '2CO':'CO2', '2ES':'LES', '2JN':'JN2', '2KI':'KI2', '2MA':'MA2',
    '2MQ':'MQ2', '2PE':'PE2', '2SA':'SA2', '2TH':'TH2', '2TI':'TI2', '3CO':'CO3', '3JN':'JN3', '3MA':'MA3', '3MQ':'MQ3', '4BA':'BA4',
    '4MA':'MA4', '5EZ':'EZ5', '6EZ':'EZ6', 'ADE':'ESA', 'DAG':'DNG', 'EZK':'EZE', 'GLO':'GLS', 'JAS':'JAM', 'JDA':'JGA', 'JDB':'JGB',
    'JON':'JNA', 'JUD':'JDE', 'NAM':'NAH', 'NDX':'IXN', 'ODA':'ODE', 'S3Y':'PAZ', 'TDX':'IXT' }

# Every BOS book code
BOS_CODES = {
    'A2J', 'A2Z', 'ABL', 'ACK', 'ACT', 'AEZ', 'AJA', 'AMO', 'APC', 'APS', 'ARI', 'ART', 'ASS', 'BA2', 'BA3', 'BA4', 'BAK', 'BAR', 'BEL', 'BLT',
    'CAT', 'CH1', 'CH2', 'CHR', 'CL1', 'CL2', 'CLM', 'CMP', 'CNC', 'CO1', 'CO2', 'CO3', 'COL', 'COP', 'DAN', 'DEU', 'DID', 'DIO', 'DNA', 'DNC',
    'DNG', 'DNT', 'DOJ', 'ECC', 'EHY', 'ELM', 'EN2', 'ENO', 'EPH', 'EPL', 'ESA', 'ESC', 'ESG', 'EST', 'EUP', 'EUT', 'EXO', 'EZ5', 'EZ6', 'EZA',
    'EZE', 'EZN', 'EZR', 'EZT', 'FOP', 'FOQ', 'FRT', 'GAL', 'GBA', 'GEN', 'GES', 'GHE', 'GJU', 'GLS', 'GMA', 'GMC', 'GPH', 'GTH', 'GTR', 'GTW',
    'H2C', 'HAB', 'HAG', 'HEB', 'HOS', 'HRE', 'HYP', 'IGC', 'IGE', 'IGM', 'IGP', 'IGR', 'IGS', 'IGT', 'INT', 'ISA', 'IXN', 'IXP', 'IXT', 'JAM',
    'JDE', 'JDG', 'JDT', 'JER', 'JGA', 'JGB', 'JHN', 'JJW', 'JN1', 'JN2', 'JN3', 'JNA', 'JOB', 'JOL', 'JOS', 'JRA', 'JSA', 'JSB', 'JUB', 'KGS',
    'KI1', 'KI2', 'LAE', 'LAM', 'LAO', 'LAR', 'LB2', 'LBA', 'LBB', 'LES', 'LEV', 'LJB', 'LJE', 'LKA', 'LPR', 'LUK', 'MA1', 'MA2', 'MA3', 'MA4',
    'MA5', 'MAC', 'MAI', 'MAL', 'MAN', 'MAP', 'MAT', 'MIC', 'MOS', 'MPC', 'MQ1', 'MQ2', 'MQ3', 'MRK', 'NAH', 'NEH', 'NUM', 'OBA', 'OBS', 'ODE',
    'OTH', 'P12', 'P1A', 'P1B', 'P4D', 'PAZ', 'PB1', 'PB2', 'PB3', 'PB4', 'PB5', 'PCP', 'PE1', 'PE2', 'PEU', 'PHM', 'PHP', 'PJE', 'PRF', 'PRO',
    'PS2', 'PS3', 'PSA', 'PSB', 'PSJ', 'PSO', 'PSS', 'REP', 'REV', 'ROE', 'ROM', 'RUT', 'RVE', 'SA1', 'SA2', 'SAM', 'SEM', 'SES', 'SHE', 'SHM',
    'SHS', 'SHV', 'SIP', 'SIR', 'SMC', 'SMK', 'SNG', 'SPR', 'SST', 'STR', 'SUS', 'TAD', 'TAT', 'TBS', 'TEO', 'TH1', 'TH2', 'TI1', 'TI2', 'TIT',
    'TJB', 'TOB', 'TOC', 'TPC', 'TSA', 'TSB', 'TSD', 'TSG', 'TSI', 'TSJ', 'TSL', 'TSN', 'TSO', 'TSR', 'TSS', 'TST', 'TSY', 'TSZ', 'TTP', 'UNK',
    'VAM', 'VSE', 'WDF', 'WIS', 'WJC', 'WOM', 'WRD', 'WSI', 'XXA', 'XXB', 'XXC', 'XXD', 'XXE', 'XXF', 'XXG', 'ZEC', 'ZEP' }


def bos( code:str ) -> str:
    """ The BOS code for a book code, whichever kind it is (e.g., 1Co, 1CO, or CO1 → CO1; 4MA → MA4; DAG → DNG). Raises ValueError for one that isn't a book's. """
    code = code.strip().upper()
    code = USFM_TO_BOS.get( code, code )
    if code not in BOS_CODES: raise ValueError( f"{code!r} isn't a USFM or BibleOrgSys book code" )
    return code


def write_tables( tablesPath:Path ) -> None:
    """ Write this file's tables again from BibleOrgSys's BibleBooksCodes_Tables.json """
    tables = json.loads( tablesPath.read_text( encoding='utf-8' ) )
    first = lambda value: value[0] if isinstance( value, list ) else value
    usfm = { code:first( entry[1] ) for code, entry in sorted( tables['USFMAbbreviationDict'].items() ) if code != first( entry[1] ) }
    codes = sorted( tables['referenceAbbreviationDict'] )
    def wrap( items:list, per:int ) -> str: return ',\n'.join( '    ' + ', '.join( items[ix:ix+per] ) for ix in range( 0, len(items), per ) )
    path = Path( __file__ )
    text = path.read_text( encoding='utf-8' )
    text = re.sub( r'USFM_TO_BOS = \{.*?\}', lambda _match: 'USFM_TO_BOS = {\n' + wrap( [ f"'{key}':'{value}'" for key, value in usfm.items() ], 10 ) + ' }', text, count=1, flags=re.DOTALL )
    text = re.sub( r'BOS_CODES = \{.*?\}', lambda _match: 'BOS_CODES = {\n' + wrap( [ f"'{code}'" for code in codes ], 20 ) + ' }', text, count=1, flags=re.DOTALL )
    path.write_text( text, encoding='utf-8' )
    # The engine's copy (for references that it's given, and modules built with USFM codes)
    rustPath = path.parent.parent.parent / 'crates' / 'biblelastic-engine' / 'src' / 'reference.rs'
    rows = [ f'("{key}", "{value}")' for key, value in usfm.items() ]
    rust = '\n'.join( '    ' + ', '.join( rows[ix:ix+10] ) + ',' for ix in range( 0, len(rows), 10 ) )
    rustText = re.sub( r'(pub const USFM_TO_BOS: &\[\(&str, &str\)\] = &\[\n).*?(\n\];)', lambda match: match.group( 1 ) + rust + match.group( 2 ),
                       rustPath.read_text( encoding='utf-8' ), count=1, flags=re.DOTALL )
    rustPath.write_text( rustText, encoding='utf-8' )
    print( f'Wrote {len(usfm)} USFM codes and {len(codes)} BOS codes into {path}, and the USFM codes into {rustPath}' )


if __name__ == '__main__':
    write_tables( Path( sys.argv[1] ) )
