"""
Score the engine's meaning-based search on the embedding trial's questions (see docs/Embeddings.md), as nDCG@10 against their lists of right passages.

    python3 bench/meaning/evaluate.py [--binary target/release/biblelastic] [--sets questions,themes,people] [--edition OET-RV]
    python3 bench/meaning/evaluate.py --sets questions-es --edition ASBRT      # The questions in Spanish, against a Spanish Bible

Needs build/embeddings/data/queries.jsonl (from bench/embeddings/passages.py), the model module, and OET-RV.vectors (biblelastic model, biblelastic embed OET-RV).
A passage found is right if it overlaps any of a question's right passages. (Standard library only.)
"""
import argparse
import json
import math
import re
import subprocess
from pathlib import Path

REPOSITORY = Path( __file__ ).resolve().parent.parent.parent


def span( passage:str ) -> tuple:
    """ ‘JHN 10:27-29’, ‘PE1 3:8-3:11’, ‘PSA 23’ → ('JHN', (10, 27), (10, 29)) """
    book, numbers = passage.split( ' ', 1 )
    first, _hyphen, last = numbers.partition( '-' )
    chapter, _colon, verse = first.partition( ':' )
    start = (int(chapter), int(verse) if verse else 1)
    if not last: end = (start[0], int(verse) if verse else 999)
    elif ':' in last: end = tuple( int(part) for part in last.split( ':' ) )
    else: end = (start[0], int(last)) if verse else (int(last), 999)
    return book, start, end


def overlaps( a:str, b:str ) -> bool:
    (bookA, startA, endA), (bookB, startB, endB) = span( a ), span( b )
    return bookA == bookB and startA <= endB and startB <= endA


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument( '--binary', default=str( REPOSITORY / 'target' / 'release' / 'biblelastic' ) )
    parser.add_argument( '--sets', default='questions,themes,people' )
    parser.add_argument( '--edition', default='OET-RV' )
    arguments = parser.parse_args()
    queries = [ json.loads( line ) for line in open( REPOSITORY / 'build' / 'embeddings' / 'data' / 'queries.jsonl', encoding='utf-8' ) ]
    sums = {}
    for query in queries:
        if query['set'] not in arguments.sets.split( ',' ): continue
        response = json.loads( subprocess.run( [arguments.binary, 'request', 'command=meaning', f"words={query['text']}", f'editions={arguments.edition}', 'limit=10', 'length=1'],
                                               capture_output=True, text=True, cwd=REPOSITORY, check=True ).stdout )
        found = [ result['locator'] for result in response['scripture'] ]
        gain = sum( 1 / math.log2( position + 2 ) for position, passage in enumerate( found ) if any( overlaps( passage, right ) for right in query['gold'] ) )
        ideal = sum( 1 / math.log2( position + 2 ) for position in range( min( 10, len(query['relevant']) ) ) )
        entry = sums.setdefault( query['set'], [0, 0.0] )
        entry[0] += 1; entry[1] += gain / ideal if ideal else 0
    for name, (count, total) in sums.items(): print( f'{name:<14} {count:>4} queries   nDCG@10 {total / count:.3f}' )


if __name__ == '__main__':
    main()
