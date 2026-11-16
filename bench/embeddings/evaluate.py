"""
Embedding trial: which model, and how small can the vectors be made?

    build/embeddings/venv/bin/python bench/embeddings/evaluate.py [MODEL...]

Embeds the passages and test queries from passages.py with each model (downloading it from Hugging Face the first time),
then measures how well the right passages are ranked, with the vectors stored in several ways.
Results go to build/embeddings/results.json, and the embeddings are cached in build/embeddings/vectors/.
"""
import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

REPOSITORY = Path( __file__ ).resolve().parent.parent.parent
WORK = REPOSITORY / 'build' / 'embeddings'

# name: (Hugging Face id, kind, query prefix, passage prefix)
MODELS = {
    'potion-base-8M': ('minishlab/potion-base-8M', 'static', '', ''),
    'potion-retrieval-32M': ('minishlab/potion-retrieval-32M', 'static', '', ''),
    'potion-multilingual-128M': ('minishlab/potion-multilingual-128M', 'static', '', ''),
    'all-MiniLM-L6-v2': ('sentence-transformers/all-MiniLM-L6-v2', 'transformer', '', ''),
    'bge-small-en-v1.5': ('BAAI/bge-small-en-v1.5', 'transformer', 'Represent this sentence for searching relevant passages: ', ''),
    'multilingual-e5-small': ('intfloat/multilingual-e5-small', 'transformer', 'query: ', 'passage: '),
    'bge-m3': ('BAAI/bge-m3', 'transformer', '', ''),
}
MULTILINGUAL = { 'potion-multilingual-128M', 'multilingual-e5-small', 'bge-m3' }


def load( name:str ) -> list:
    with open( WORK / 'data' / name, encoding='utf-8' ) as jsonFile: return [ json.loads( line ) for line in jsonFile ]


def encode( modelName:str, texts:list, isQuery:bool ) -> tuple:
    """ Returns unit-length float32 vectors, and how long one text took on one CPU thread (for queries only). """
    huggingFaceId, kind, queryPrefix, passagePrefix = MODELS[modelName]
    texts = [ (queryPrefix if isQuery else passagePrefix) + text for text in texts ]
    if kind == 'static':
        from model2vec import StaticModel
        model = StaticModel.from_pretrained( huggingFaceId )
        vectors = model.encode( texts )
        started = time.perf_counter()
        if isQuery:
            for text in texts[:200]: model.encode( [text] )
        seconds = (time.perf_counter() - started) / min( 200, len(texts) )
    else:
        import torch
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer( huggingFaceId, device='cuda' if torch.cuda.is_available() else 'cpu' )
        vectors = model.encode( texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False )
        seconds = 0.0
        if isQuery: # What a device would do: one short text at a time, on one thread of the processor
            torch.set_num_threads( 1 )
            cpuModel = SentenceTransformer( huggingFaceId, device='cpu' )
            cpuModel.encode( texts[:3] )
            started = time.perf_counter()
            for text in texts[:50]: cpuModel.encode( [text] )
            seconds = (time.perf_counter() - started) / 50
    vectors = np.asarray( vectors, dtype=np.float32 )
    return vectors / np.maximum( np.linalg.norm( vectors, axis=1, keepdims=True ), 1e-9 ), seconds


def cached( modelName:str, what:str, texts:list, isQuery:bool ) -> tuple:
    path = WORK / 'vectors' / f'{modelName}.{what}.npy'
    timingPath = path.with_suffix( '.seconds' )
    if path.exists() and timingPath.exists(): return np.load( path ), float( timingPath.read_text() )
    path.parent.mkdir( parents=True, exist_ok=True )
    vectors, seconds = encode( modelName, texts, isQuery )
    np.save( path, vectors ); timingPath.write_text( str( seconds ) )
    return vectors, seconds


# Ways of storing the passage vectors. Each returns (scores for every query and passage, bytes for each passage).
def as_float32( queries, passages ): return queries @ passages.T, passages.shape[1] * 4

def as_int8( queries, passages ):
    scale = 127 / np.abs( passages ).max()
    return queries @ np.round( passages * scale ).astype( np.int8 ).astype( np.float32 ).T, passages.shape[1]

def centred( queries, passages ):
    """ Take the passages' average vector away from everything first: some models' vectors all lean the same way, which wastes the bits """
    mean = passages.mean( axis=0, keepdims=True )
    return queries - mean, passages - mean

def as_bits( queries, passages ): # One bit for each dimension; the query is still compared as numbers
    queries, passages = centred( queries, passages )
    return queries @ np.where( passages > 0, 1.0, -1.0 ).astype( np.float32 ).T, math.ceil( passages.shape[1] / 8 )

def as_bits_both( queries, passages ): # … or the query is one bit for each dimension too (so comparing is counting bits)
    queries, passages = centred( queries, passages )
    return np.where( queries > 0, 1.0, -1.0 ).astype( np.float32 ) @ np.where( passages > 0, 1.0, -1.0 ).astype( np.float32 ).T, math.ceil( passages.shape[1] / 8 )

def as_bits_then_int8( queries, passages, shortlist=100 ): # Bits to find the best hundred, then int8 to put those in order
    coarse, bitBytes = as_bits( queries, passages )
    fine, int8Bytes = as_int8( queries, passages )
    keep = np.argpartition( -coarse, shortlist, axis=1 )[:, :shortlist]
    scores = np.full_like( coarse, -np.inf )
    np.put_along_axis( scores, keep, np.take_along_axis( fine, keep, axis=1 ), axis=1 )
    return scores, bitBytes + int8Bytes

def half( method ):
    def halved( queries, passages ):
        size = passages.shape[1] // 2
        normalise = lambda vectors: vectors[:, :size] / np.maximum( np.linalg.norm( vectors[:, :size], axis=1, keepdims=True ), 1e-9 )
        return method( normalise( queries ), normalise( passages ) )
    return halved

STORAGE = { 'float32':as_float32, 'int8':as_int8, 'bits':as_bits, 'bits (query too)':as_bits_both, 'bits then int8':as_bits_then_int8,
            'half, int8':half( as_int8 ), 'half, bits':half( as_bits ) }


def rankings( scores:np.ndarray, depth:int=100 ) -> np.ndarray:
    top = np.argpartition( -scores, depth, axis=1 )[:, :depth]
    return np.take_along_axis( top, np.argsort( -np.take_along_axis( scores, top, axis=1 ), axis=1 ), axis=1 )


def measure( ranked:np.ndarray, queries:list ) -> dict:
    """ nDCG@10 (how well the right passages are placed in the first ten) and how often any right passage is in the first ten, for each set of queries """
    sums = {}
    for row, query in zip( ranked, queries ):
        relevant = set( query['relevant'] )
        gain = sum( 1 / math.log2( position + 2 ) for position, chunk in enumerate( row[:10] ) if chunk in relevant )
        ideal = sum( 1 / math.log2( position + 2 ) for position in range( min( 10, len(relevant) ) ) )
        entry = sums.setdefault( query['set'], [0, 0.0, 0] )
        entry[0] += 1; entry[1] += gain / ideal; entry[2] += any( chunk in relevant for chunk in row[:10] )
    return { setName:{ 'ndcg10':round( total / count, 4 ), 'any10':round( hits / count, 4 ) } for setName, (count, total, hits) in sums.items() }


WORD_RE = re.compile( r"\w+", re.UNICODE )
def bm25_scores( queries:list, chunks:list, k1:float=1.2, b:float=0.75 ) -> np.ndarray:
    """ The usual word-matching score, for comparison (lower-cased words, no stemming) """
    documents = [ Counter( WORD_RE.findall( chunk['text'].lower() ) ) for chunk in chunks ]
    lengths = np.array( [ sum( document.values() ) for document in documents ], dtype=np.float32 )
    documentFrequency = Counter( word for document in documents for word in document )
    postings = {}
    for number, document in enumerate( documents ):
        for word, count in document.items(): postings.setdefault( word, [] ).append( (number, count) )
    scores = np.zeros( (len(queries), len(chunks)), dtype=np.float32 )
    for row, query in enumerate( queries ):
        for word in set( WORD_RE.findall( query['text'].lower() ) ):
            if word not in postings: continue
            numbers, counts = map( np.array, zip( *postings[word] ) )
            idf = math.log( 1 + (len(chunks) - documentFrequency[word] + 0.5) / (documentFrequency[word] + 0.5) )
            scores[row, numbers] += idf * counts * (k1 + 1) / (counts + k1 * (1 - b + b * lengths[numbers] / lengths.mean()))
    return scores


def fuse( *rankedLists, k:int=60 ) -> np.ndarray:
    """ Reciprocal rank fusion of several rankings of the same queries """
    fused = []
    for rows in zip( *rankedLists ):
        totals = Counter()
        for row in rows:
            for position, chunk in enumerate( row ): totals[int(chunk)] += 1 / (k + position + 1)
        fused.append( [ chunk for chunk,_score in totals.most_common( 100 ) ] + [-1] * 100 )
    return np.array( [ row[:100] for row in fused ] )


HEADED = '--headed' in sys.argv # Put each passage's section heading in front of it (the ‘headings’ queries then prove nothing)

def main() -> None:
    chunks, queries = load( 'chunks.jsonl' ), load( 'queries.jsonl' )
    if HEADED: sys.argv.remove( '--headed' )
    results = { 'chunks':len(chunks), 'queries':Counter( query['set'] for query in queries ), 'models':{} }
    if HEADED:
        for chunk in chunks: chunk['text'] = (chunk['heading'] + '. ' if chunk['heading'] else '') + chunk['text']
    wordRanked = rankings( bm25_scores( queries, chunks ) )
    results['words only'] = measure( wordRanked, queries )
    for modelName in sys.argv[1:] or MODELS:
        started = time.perf_counter()
        passages, _seconds = cached( modelName, 'passages' + ('-headed' if HEADED else ''), [ (chunk['heading'] + '. ' if HEADED and chunk['heading'] else '') + chunk['text'] for chunk in chunks ], False )
        queryVectors, querySeconds = cached( modelName, 'queries', [ query['text'] for query in queries ], True )
        entry = { 'dimensions':passages.shape[1], 'query_ms':round( querySeconds * 1000, 3 ), 'storage':{} }
        for storageName, method in STORAGE.items():
            scores, bytesEach = method( queryVectors, passages )
            ranked = rankings( scores )
            entry['storage'][storageName] = { 'bytes_each':bytesEach, 'scores':measure( ranked, queries ) }
            if storageName in ('float32','bits then int8'): entry['storage'][storageName]['with words'] = measure( fuse( ranked, wordRanked ), queries )
        results['models'][modelName] = entry
        print( f'{modelName}: {passages.shape[1]} dimensions, {entry["query_ms"]} ms for a query, done in {time.perf_counter()-started:.0f}s', flush=True )
        (WORK / ('results-headed.json' if HEADED else 'results.json')).write_text( json.dumps( results, indent=1 ) + '\n', encoding='utf-8' )

    sets = list( results['queries'] )
    print( f"\nnDCG@10 for {len(chunks):,} passages" + ''.join( f'{setName:>14}' for setName in sets ) + '   bytes each' )
    line = lambda label, scores, size='': print( f'{label:<44}' + ''.join( f"{scores.get( setName, {} ).get( 'ndcg10', 0 ):>14.3f}" for setName in sets ) + f'   {size}' )
    line( 'words only (BM25)', results['words only'] )
    for modelName, entry in results['models'].items():
        for storageName, stored in entry['storage'].items():
            if modelName not in MULTILINGUAL: stored['scores'].pop( 'questions-es', None )
            line( f'{modelName}, {storageName}', stored['scores'], stored['bytes_each'] )
            if 'with words' in stored: line( f'{modelName}, {storageName} + words', stored['with words'], stored['bytes_each'] )


if __name__ == '__main__':
    main()
