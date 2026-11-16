#!/bin/sh
# Build the trial for browsers, and put it beside the models in build/embeddings/rust/.
set -e
cd "$(dirname "$0")"
# With SIMD (which every current browser has): the model runs about three times faster
RUSTFLAGS="-C target-feature=+simd128" cargo build --release --lib --target wasm32-unknown-unknown
cp target/wasm32-unknown-unknown/release/embed_query.wasm ../../build/embeddings/rust/
ls -l ../../build/embeddings/rust/embed_query.wasm
echo "Now run (in the repository's top folder):  python3 -m http.server 8377   and open http://localhost:8377/bench/embed-query/web/"
