# Meaning-based search

A search for a subject (in the app, *Topic*) also finds the passages that are *about* it, even when they use none of its words:
‘why do good people suffer’ finds 1 Peter's passages on suffering for doing good, and Psalm 73.
It follows the [embedding trial](Embeddings.md): each passage is turned into a list of 384 numbers (a *vector*) when the modules are built,
the query is turned into one on the device by the same model, and the passages whose vectors are closest are the results.
Nothing is generated: the results are passages, as they are.

## The pieces

| | What it is | Made by | Size |
| --- | --- | --- | --- |
| `bge-small-en-v1.5.model.blm` | The model ([BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5), MIT licence): a 12-layer BERT encoder, its weights stored as one byte each, with its word pieces | `biblelastic model FOLDER` | 31 MB |
| `EDITION.vectors.blm` | For one work: its passages (where each is, its heading or title, and its text) and their vectors, one byte for each dimension | `biblelastic embed [EDITION…]` | e.g., 4.1 MB for the OET-RV |

Both are ordinary modules (kinds `model` and `vectors`), installed like the others. Meaning-based search needs the model and at least one work's vectors;
without them, everything else works as before.

**Passages.** For a Bible, runs of the body paragraphs within one section, of about 80–200 words, each with its section's heading in front of it
(the trial found that the heading helps more than any choice of model). For a commentary, dictionary, or book, runs of the paragraphs of one entry,
with the entry's title (and the heading that they're under) in front. A study note is usually one passage; a book's chapter is many.

**The model runs in the engine**, in plain Rust (`crates/biblelastic-engine/src/meaning.rs`): its tokenizer (BERT's WordPiece), and the encoder's arithmetic
(see *How long it takes* for the three ways that it's done). So it's the same natively and in WebAssembly, adds nothing to the engine's dependencies
(the engine grew by about 0.1 MB), and the same code embeds the passages when the modules are built, so the two sides always agree.
It's loaded the first time that it's needed (about a quarter of a second), and kept.

**Comparing** is with every passage, without an index: the vectors of the works being searched are read once and kept in memory.

## How good it is

On the trial's questions (`bench/meaning/evaluate.py`), against the OET-RV's passages, as nDCG@10:

| | Questions (50) | Themes (298) | People (125) |
| --- | --- | --- | --- |
| The trial (the model in Python, at full precision) | 0.39 | 0.17 | 0.33 |
| **The engine** | **0.37** | **0.18** | **0.32** |
| The engine, without the model's query prefix | 0.35 | 0.15 | 0.30 |

The differences from the trial are within its noise (its passages were cut slightly differently). The engine's vectors agree with the full-precision model's
(sentence-transformers) to a cosine similarity of 0.9997, closer than the 8-bit ONNX file that the trial measured (0.996).

The model's recommended query prefix (‘Represent this sentence for searching relevant passages: ’) is more than half of a typical query's work,
but leaving it out costs about 8%, so it's kept.

## How long it takes

A query, after the model's loaded, including comparing with all 8,672 passages of the OET-RV (or, where it says so, with all 73,693 passages of the 63 English works).
The phone is the OPPO CPH2579 (MediaTek Helio G85: two fast and six slow ARM cores, 4 GB), measured on 26 November 2026:

| | A query | The first query (loading the model and vectors) |
| --- | --- | --- |
| **The phone, natively** (as the app runs it) | **32–57 ms** (47 ms typical) | 0.49 s |
| … all 63 works | 79 ms | 1.0 s |
| **The phone's Chrome** (WebAssembly) | **135–231 ms** (180 ms typical) | 1.3 s |
| Desktop, natively | 25 ms | |
| Desktop, natively, with AVX2 (as the build machine compiles it for `biblelastic embed`) | about 10 ms | |
| Desktop Chrome | 11–18 ms | 0.16 s |
| … all 63 works | 31–52 ms (before the 16-bit path below) | 0.39 s (79 MB of memory in all) |

(The trial's ONNX Runtime, for comparison: 2 ms natively and 10 ms in desktop Chrome; 237 ms in the phone's Chrome.)

The arithmetic is done three ways, and the engine chooses whichever the processor can do:

- **ARM processors with the byte dot-product instruction** (`sdot`: most phones since about 2018, checked when the engine runs): each token's inputs are turned into bytes too
    (with a scale for each token), and sixteen products of bytes are done at once. On the phone this made a query four to five times faster than with floats (175–218 ms),
    and the vectors still agree with the full-precision model's to 0.999.
- **WebAssembly** (built with its vector instructions, `+simd128`, which every current browser has) has no dot product of bytes, but has one of 16-bit numbers:
    the same bytes, made 16-bit as they're loaded. That's about 1.6 times as fast as floats on the phone, and 2.5 times on the desktop.
- **Otherwise** (e.g., x86 computers, and building the vectors), floats, which agree with the full-precision model to 0.9997.

**Threads** were tried natively (sharing each layer's rows among them): four made the desktop a third faster, but made the phone *slower* (300–430 ms against 175–218 ms with one thread, with floats),
so a query uses one thread.

So on the phone a meaning-based search takes about a twentieth of a second in the app, and a fifth of a second in the browser, after a second or so the first time.
That's quick enough for a search that's asked for (and the app shows the other results first), though not yet for searching as one types in the browser.
Embedding all the passages at build time took 16 minutes on a 32-processor desktop (73,693 passages of 63 works, 37 MB of vectors; the OET-RV's took 89 s),
and is only redone for passages whose text has changed.

## In the app

The *Topic* search shows its other results first, then ‘Looking for passages about this…’, then the passages of Scripture that are about it,
and the notes, articles, and book chapters that are, each of which can be opened. It's only offered when a model and some vectors are installed.
Only the best passage of each entry is shown, and a passage that's the same in another edition (e.g., a book's modernised edition) is left out.

## Not done yet

- **Only English.** There's no small model that's good at Spanish yet (see the trial): the Spanish Bibles, notes, and books have no vectors.
- **Not combined with word matching.** The trial found that combining the two rankings helps with names of people and themes; here they're shown side by side.
- **Measured on one phone only**, and not in Safari or Firefox. The phone's own memory use wasn't measured (the browser reported 55 MB with the OET-RV's vectors, 79 MB with all of them).
- **All of an edition's vectors are kept in memory** once they've been read (4 MB for the OET-RV; 37 MB for all the English works).
    On a phone with little memory, the bytes could be read a page at a time instead.

## Building them

    target/release/biblelastic model ~/.cache/huggingface/hub/models--BAAI--bge-small-en-v1.5/snapshots/*/   # → build/modules/bge-small-en-v1.5.model.blm
    target/release/biblelastic embed                    # Every installed English work (or name some editions)
    target/release/biblelastic meaning why do good people suffer
    python3 bench/meaning/evaluate.py                   # The trial's questions (needs build/embeddings/data/queries.jsonl)
    node bench/meaning/web.mjs                          # Timing in headless Chrome

For a quicker build, compile the CLI for the build machine's processor: `RUSTFLAGS="-C target-cpu=native" cargo build --release`.
The model's folder is a Hugging Face download of the model (`config.json`, `vocab.txt`, `model.safetensors`, and `1_Pooling/config.json`).
