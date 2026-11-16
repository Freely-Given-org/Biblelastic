#!/bin/sh
# Build the engine for browsers, and put it beside the test page.
# Needs: rustup target add wasm32-unknown-unknown
set -e
cd "$(dirname "$0")/.."
cargo build --release --target wasm32-unknown-unknown -p biblelastic-wasm
cp target/wasm32-unknown-unknown/release/biblelastic_wasm.wasm web/biblelastic.wasm
ls -l web/biblelastic.wasm
echo "Now run:  python3 -m http.server 8377   and open http://localhost:8377/web/"
