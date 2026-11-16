"""
Embedding trial, part 3: put what the Rust and browser trial (bench/embed-query) needs into build/embeddings/rust/.

    build/embeddings/venv/bin/python bench/embeddings/export_queries.py

Copies the 8-bit and full-precision ONNX files of bge-small-en-v1.5 there, and writes queries.tsv:
the fifty English questions as token numbers (padded to 32), their attention masks, and the vectors that ONNX Runtime gives for them.
"""
import json
import shutil

import numpy as np
import onnxruntime
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

from evaluate import MODELS, WORK

REPOSITORY, NAME, PADDED = 'Xenova/bge-small-en-v1.5', 'bge-small-en-v1.5', 32


def main() -> None:
    output = WORK / 'rust'
    output.mkdir( parents=True, exist_ok=True )
    quantised = hf_hub_download( REPOSITORY, 'onnx/model_quantized.onnx' )
    shutil.copy( quantised, output / f'{NAME}.int8.onnx' )
    shutil.copy( hf_hub_download( REPOSITORY, 'onnx/model.onnx' ), output / f'{NAME}.float32.onnx' )
    tokenizer = Tokenizer.from_file( hf_hub_download( REPOSITORY, 'tokenizer.json' ) )
    session = onnxruntime.InferenceSession( quantised, providers=['CPUExecutionProvider'] )
    with open( WORK / 'data' / 'queries.jsonl', encoding='utf-8' ) as queriesFile:
        questions = [ query['text'] for query in map( json.loads, queriesFile ) if query['set'] == 'questions' ]
    lines = []
    for question in questions:
        ids = tokenizer.encode( MODELS[NAME][2] + question ).ids[:PADDED]
        mask = [1] * len(ids) + [0] * (PADDED - len(ids))
        ids += [0] * (PADDED - len(ids))
        feeds = { 'input_ids':np.array( [ids] ), 'attention_mask':np.array( [mask] ), 'token_type_ids':np.zeros( (1, PADDED), dtype=np.int64 ) }
        vector = session.run( None, feeds )[0][0][0] # The first token's vector is the embedding
        vector /= np.linalg.norm( vector )
        lines.append( '\t'.join( ( ' '.join( map( str, ids ) ), ' '.join( map( str, mask ) ), ' '.join( f'{value:.6f}' for value in vector ) ) ) )
    (output / 'queries.tsv').write_text( '\n'.join( lines ) + '\n', encoding='utf-8' )
    print( f'{len(lines)} queries, and two model files, in {output}' )


if __name__ == '__main__':
    main()
