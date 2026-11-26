# Meaning-based search

A search for a subject (in the app, *Topic*) also finds the passages that are *about* it, even when they use none of its words:
‘why do good people suffer’ finds 1 Peter's passages on suffering for doing good, and Psalm 73.
It follows the [embedding trial](Embeddings.md): each passage is turned into a list of 384 numbers (a *vector*) when the modules are built,
the query is turned into one on the device by the same model, and the passages whose vectors are closest are the results.
Nothing is generated: the results are passages, as they are.

## The pieces

| | What it is | Made by | Size |
| --- | --- | --- | --- |
| `bge-small-en-v1.5.model.blm` | The model for English works ([BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5), MIT licence): a 12-layer BERT encoder, its weights stored as one byte each, with its word pieces | `biblelastic model FOLDER` | 31 MB |
| `multilingual-e5-small.model.blm` | The model for Spanish works ([intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small), MIT licence): the same size of encoder, with SentencePiece's tokenizer, cut down to English and Spanish (see *Spanish* below) | `biblelastic model FOLDER` | 35 MB |
| `EDITION.vectors.blm` | For one work: its passages (where each is, its heading or title, and its text) and their vectors, one byte for each dimension | `biblelastic embed [EDITION…]` | e.g., 4.1 MB for the OET-RV |

All are ordinary modules (kinds `model` and `vectors`), installed like the others. Each work's vectors are made by the model for its language, and say which model that was,
so a query is embedded by that model when the work is searched. Meaning-based search needs a model and at least one work's vectors; without them, everything else works as before.

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

## Spanish

The Spanish works (the two Bibles, the Aquifer's study notes and dictionary, and the three Spanish books: 47,826 passages, 25 MB of vectors) are embedded with
`multilingual-e5-small`, which the trial found to be the best small model for Spanish. It averages all its tokens' states (rather than taking the first),
and its queries and passages start with `query: ` and `passage: `. Its tokenizer is SentencePiece's unigram one, which the engine now has too
(`Unigram` in `meaning.rs`: the most probable pieces for each word, after Unicode's compatibility forms, e.g., `…` → `...`, from a table of the 704 that Latin-script text can meet).

**Cut down.** The model has 250,002 word pieces for about a hundred languages, which are most of its 113 MB. `biblelastic model` keeps only the pieces that the installed
English and Spanish works use (and every single character of the scripts before Chinese, Japanese, and Korean, so that a query never meets an unknown letter): 41,095 pieces,
and 35 MB. A word is cut into the same pieces whichever other pieces there are, so the works' texts give exactly the same vectors as with the whole model.
Its vectors agree with the full model's (sentence-transformers) to a cosine similarity of 0.9998 on samples of the English and Spanish works.

**How good it is**, on the trial's fifty questions in Spanish, against each Spanish Bible's passages (nDCG@10):

| | The questions in Spanish |
| --- | --- |
| Against the Aquifer Spanish Bible Reference Text (`ASBRT`) | **0.32** |
| Against the Reina-Valera 1909 | 0.27 |
| (The trial: against the English OET-RV, with the same model) | 0.24 |
| (For comparison: the questions in English, against the OET-RV, with bge) | 0.37 |

The RV1909's archaic Spanish is harder. (At first it scored 0.23, because each of its chapters is one paragraph: such long paragraphs are now cut between verses.)

**How long it takes** is the same as for English (the models are the same size): on the phone, 47 ms a query natively for the ASBRT (58 ms for all the Spanish works),
and 178 ms in the phone's Chrome, after 0.6–0.8 s (1.3 s in Chrome) the first time.

**In the app**, a search uses the works in the language of the Bible that's being read, so reading a Spanish Bible searches the Spanish works.

**The source's titles.** Two of the Aquifer's Spanish titles are mistranslated: the introduction to Job is titled ‘Work’, and the dictionary's article on sin (*pecado*) ‘Without’.
`pipeline/biblelastic_ingest/aquifer.py` corrects those two. The dictionary's titles and its articles' own headings disagree in 346 places, mostly as spelling variants
(e.g., ‘Abiathar’ and ‘ABIATAR’), some with English left in a title (‘Aaron’s Rod’ for *Vara de Aarón*), so they're left as they are.

## In the app

The *Topic* search shows its other results first, then ‘Looking for passages about this…’, then the passages of Scripture that are about it,
and the notes, articles, and book chapters that are, each of which can be opened. It's only offered when a model and some vectors are installed.
Only the best passage of each entry is shown, and a passage that's the same in another edition (e.g., a book's modernised edition) is left out.

## Not done yet

- **One language at a time.** A search only uses the works in the Bible's language (the two models' scores aren't comparable), so a Spanish reader doesn't get the English books.
    `multilingual-e5-small` could search English works with a Spanish query, but less well (0.14 for the English questions against the ASBRT).
- **Not combined with word matching.** The trial found that combining the two rankings helps with names of people and themes; here they're shown side by side.
- **Measured on one phone only**, and not in Safari or Firefox. The phone's own memory use wasn't measured (the browser reported 55 MB with the OET-RV's vectors, 79 MB with all of them).
- **All of an edition's vectors are kept in memory** once they've been read (4 MB for the OET-RV; 37 MB for all the English works).
    On a phone with little memory, the bytes could be read a page at a time instead.

## Building them

    target/release/biblelastic model ~/.cache/huggingface/hub/models--BAAI--bge-small-en-v1.5/snapshots/*/   # → build/modules/bge-small-en-v1.5.model.blm
    target/release/biblelastic model ~/.cache/huggingface/hub/models--intfloat--multilingual-e5-small/snapshots/*/   # After the works are compiled (it's cut down to them)
    target/release/biblelastic embed                    # Every installed English and Spanish work (or name some editions)
    target/release/biblelastic meaning why do good people suffer
    target/release/biblelastic meaning --edition spa ¿Por qué sufren las personas buenas?
    python3 bench/meaning/evaluate.py                   # The trial's questions (needs build/embeddings/data/queries.jsonl)
    python3 bench/meaning/evaluate.py --sets questions-es --edition ASBRT
    node bench/meaning/web.mjs                          # Timing in headless Chrome

For a quicker build, compile the CLI for the build machine's processor: `RUSTFLAGS="-C target-cpu=native" cargo build --release`.
The model's folder is a Hugging Face download of the model (`config.json`, `model.safetensors`, `1_Pooling/config.json`, and `vocab.txt` or `tokenizer.json`).
Only the two models above are known to `biblelastic model` (it needs each one's prefixes and language).
Their rights (copyright, licence, and `licence_verified`) are under `[[model]]` in `pipeline/sources.toml`, which the ingest writes to `build/intermediate/models/`,
so the ingest must have run first.
