"""
Embedding trial, part 2: the query side as a device would run it.

    build/embeddings/venv/bin/python bench/embeddings/quantised.py

Downloads the 8-bit ONNX versions of the small models (from the Xenova conversions on Hugging Face), embeds the test queries
with them on one processor thread, and scores them against passage vectors made by the full-precision model
(as the build would make them), stored as int8 with each passage's section heading in front of it.
"""
import json
import time
from pathlib import Path

import numpy as np
import onnxruntime
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

from evaluate import MODELS, WORK, as_int8, fuse, bm25_scores, load, measure, rankings

# name: (repository of the ONNX conversion, how the token vectors are combined)
QUANTISED = { 'all-MiniLM-L6-v2':('Xenova/all-MiniLM-L6-v2', 'mean'), 'bge-small-en-v1.5':('Xenova/bge-small-en-v1.5', 'first'),
              'multilingual-e5-small':('Xenova/multilingual-e5-small', 'mean') }


def main() -> None:
    chunks, queries = load( 'chunks.jsonl' ), load( 'queries.jsonl' )
    for chunk in chunks: chunk['text'] = (chunk['heading'] + '. ' if chunk['heading'] else '') + chunk['text']
    wordRanked = rankings( bm25_scores( queries, chunks ) )
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    results = {}
    print( f"{'':<24}{'file':>9}{'tokenizer':>11}{'one query':>11}   nDCG@10: questions, in Spanish, themes, people   (and with word matching)" )
    for name, (repository, pooling) in QUANTISED.items():
        modelPath = Path( hf_hub_download( repository, 'onnx/model_quantized.onnx' ) )
        tokenizerPath = Path( hf_hub_download( repository, 'tokenizer.json' ) )
        tokenizer = Tokenizer.from_file( str( tokenizerPath ) )
        tokenizer.enable_truncation( 512 )
        session = onnxruntime.InferenceSession( str( modelPath ), options, providers=['CPUExecutionProvider'] )
        inputNames = { modelInput.name for modelInput in session.get_inputs() }
        def embed( text:str ) -> np.ndarray:
            encoding = tokenizer.encode( MODELS[name][2] + text )
            feeds = { 'input_ids':np.array( [encoding.ids], dtype=np.int64 ), 'attention_mask':np.array( [encoding.attention_mask], dtype=np.int64 ),
                      'token_type_ids':np.zeros( (1, len(encoding.ids)), dtype=np.int64 ) }
            states = session.run( None, { key:value for key,value in feeds.items() if key in inputNames } )[0][0]
            vector = states[0] if pooling == 'first' else states.mean( axis=0 )
            return vector / np.linalg.norm( vector )
        embed( 'warm up' )
        started = time.perf_counter()
        vectors = np.array( [ embed( query['text'] ) for query in queries ], dtype=np.float32 )
        milliseconds = (time.perf_counter() - started) * 1000 / len(queries)
        passages = np.load( WORK / 'vectors' / f'{name}.passages-headed.npy' )
        fullQueries = np.load( WORK / 'vectors' / f'{name}.queries.npy' )
        agreement = float( np.mean( np.sum( vectors * fullQueries, axis=1 ) ) ) # Cosine similarity with the full-precision model's query vectors
        ranked = rankings( as_int8( vectors, passages )[0] )
        scores, withWords = measure( ranked, queries ), measure( fuse( ranked, wordRanked ), queries )
        results[name] = { 'model_bytes':modelPath.stat().st_size, 'tokenizer_bytes':tokenizerPath.stat().st_size, 'query_ms':round( milliseconds, 2 ),
                          'agreement':round( agreement, 4 ), 'scores':scores, 'with words':withWords }
        show = lambda measured: ', '.join( f"{measured[setName]['ndcg10']:.3f}" for setName in ('questions','questions-es','themes','people') )
        print( f"{name:<24}{modelPath.stat().st_size/1048576:>6.1f} MB{tokenizerPath.stat().st_size/1048576:>8.1f} MB{milliseconds:>8.1f} ms   {show( scores )}   ({show( withWords )})   agreement {agreement:.3f}" )
    (WORK / 'results-quantised.json').write_text( json.dumps( results, indent=1 ) + '\n', encoding='utf-8' )


if __name__ == '__main__':
    main()
