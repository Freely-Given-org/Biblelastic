"""
Build the passages and test queries for the embedding trial, from build/intermediate (standard library only).

    python3 bench/embeddings/passages.py

Writes build/embeddings/data/chunks.jsonl and queries.jsonl.

A chunk is a run of body paragraphs of the OET-RV within one section, of about 80-200 words.
Each query has ‘gold’ passages; a chunk is a right answer if it overlaps any of them.
"""
import csv
import json
import random
import re
from pathlib import Path

REPOSITORY = Path( __file__ ).resolve().parent.parent.parent
INTERMEDIATE = REPOSITORY / 'build' / 'intermediate'
OUTPUT = REPOSITORY / 'build' / 'embeddings' / 'data'
MIN_WORDS, MAX_WORDS = 80, 200
HEADING_SAMPLE = 500


def rows( path:Path ) -> list:
    with open( path, encoding='utf-8', newline='' ) as tsvFile:
        reader = csv.reader( tsvFile, delimiter='\t', quoting=csv.QUOTE_NONE )
        next( reader )
        return list( reader )


def verse_number( name:str ) -> tuple:
    chapter, _colon, verse = name.partition( ':' )
    return int( re.match( r'\d+', chapter ).group() ), int( re.match( r'\d+', verse ).group() )


def parse_passage( text:str ) -> tuple:
    """ GEN 1:1 or GEN 1:1-2:3 or GEN 1:3-5 → (BBB, (c,v), (c,v)) """
    BBB, numbers = text.split()
    first, _hyphen, last = numbers.partition( '-' )
    start = verse_number( first )
    end = start if not last else verse_number( last ) if ':' in last else (start[0], int(last))
    return BBB, start, end


def build_chunks() -> tuple:
    chunks, headings = [], []
    for tokensPath in sorted( (INTERMEDIATE / 'OET-RV' / 'documents').glob( '*.tokens.tsv' ) ):
        BBB = tokensPath.name[:3]
        tokens = rows( tokensPath )
        nodes = rows( tokensPath.with_name( f'{BBB}.nodes.tsv' ) )
        verses = [ (int(start), int(end), verse_number( name )) for nodeType,start,end,name,_attributes in nodes if nodeType == 'verse' and int(end) > int(start) ]
        if not verses: continue
        sections = [ (int(start), int(end), name) for nodeType,start,end,name,_attributes in nodes if nodeType == 'section' ] or [ (0, len(tokens), '') ]
        paragraphs = [ (int(start), int(end)) for nodeType,start,end,_name,attributes in nodes if nodeType == 'para' and '"kind": "body"' in attributes and int(end) > int(start) ]
        def finish( parts:list, heading:str ) -> None:
            start, end = parts[0][0], parts[-1][1]
            inside = [ number for verseStart,verseEnd,number in verses if verseStart < end and verseEnd > start ]
            if not inside: return
            text = ' '.join( ''.join( before+word+after for before,word,after,*_features in tokens[partStart:partEnd] ).strip() for partStart,partEnd in parts )
            chunks.append( { 'id':len(chunks), 'book':BBB, 'from':min( inside ), 'to':max( inside ), 'heading':heading, 'words':sum( e-s for s,e in parts ), 'text':text } )
        for sectionStart, sectionEnd, heading in sections:
            firstChunk, parts, words = len(chunks), [], 0
            for start, end in paragraphs:
                if not sectionStart <= start < sectionEnd: continue
                if parts and words + (end-start) > MAX_WORDS: finish( parts, heading ); parts, words = [], 0
                parts.append( (start, end) ); words += end - start
                if words >= MIN_WORDS: finish( parts, heading ); parts, words = [], 0
            if parts: finish( parts, heading )
            if heading and len(chunks) > firstChunk:
                headings.append( (heading, BBB, min( chunk['from'] for chunk in chunks[firstChunk:] ), max( chunk['to'] for chunk in chunks[firstChunk:] )) )
    return chunks, headings


def entry_queries( edition:str, document:str, setName:str ) -> list:
    """ One query for each entry of a document: its title, with the passages that the entry is about or cites as the right answers. """
    folder = INTERMEDIATE / edition / 'documents'
    anchors = [ (int(start), reference) for start,_end,_kind,reference in rows( folder / f'{document}.anchors.tsv' ) ]
    queries = []
    for start, end, name, _type, title in rows( folder / f'{document}.entries.tsv' ):
        gold = sorted( { reference for anchorStart,reference in anchors if int(start) <= anchorStart < int(end) } )
        if title and gold: queries.append( { 'set':setName, 'language':'eng', 'text':title, 'gold':gold } )
    return queries


def main() -> None:
    OUTPUT.mkdir( parents=True, exist_ok=True )
    chunks, headings = build_chunks()
    with open( OUTPUT / 'chunks.jsonl', 'w', encoding='utf-8' ) as chunksFile:
        for chunk in chunks: chunksFile.write( json.dumps( chunk, ensure_ascii=False ) + '\n' )

    queries = []
    for english, spanish, passages in rows( Path( __file__ ).with_name( 'questions.tsv' ) ):
        gold = [ passage.strip() for passage in passages.split( ';' ) ]
        queries.append( { 'set':'questions', 'language':'eng', 'text':english, 'gold':gold } )
        queries.append( { 'set':'questions-es', 'language':'spa', 'text':spanish, 'gold':gold } )
    queries += entry_queries( 'TOSN', 'Themes', 'themes' ) + entry_queries( 'TOSN', 'Profiles', 'people' )
    random.seed( 6 )
    for heading, BBB, start, end in random.sample( headings, min( HEADING_SAMPLE, len(headings) ) ):
        queries.append( { 'set':'headings', 'language':'eng', 'text':heading, 'gold':[ f'{BBB} {start[0]}:{start[1]}-{end[0]}:{end[1]}' ] } )

    # Work out which chunks are right answers for each query
    byBook = {}
    for chunk in chunks: byBook.setdefault( chunk['book'], [] ).append( chunk )
    kept = []
    for query in queries:
        relevant = set()
        for passage in query['gold']:
            BBB, start, end = parse_passage( passage )
            relevant.update( chunk['id'] for chunk in byBook.get( BBB, [] ) if tuple(chunk['from']) <= end and tuple(chunk['to']) >= start )
        query['relevant'] = sorted( relevant )
        if relevant: kept.append( query )
    with open( OUTPUT / 'queries.jsonl', 'w', encoding='utf-8' ) as queriesFile:
        for query in kept: queriesFile.write( json.dumps( query, ensure_ascii=False ) + '\n' )

    words = sorted( chunk['words'] for chunk in chunks )
    print( f"{len(chunks):,} chunks of the OET-RV ({sum( words ):,} words; median {words[len(words)//2]}, longest {words[-1]})" )
    for setName in dict.fromkeys( query['set'] for query in kept ):
        inSet = [ query for query in kept if query['set'] == setName ]
        print( f"  {setName:<13}{len(inSet):>4} queries, with {sum( len(query['relevant']) for query in inSet ) / len(inSet):.1f} right chunks each on average" )


if __name__ == '__main__':
    main()
