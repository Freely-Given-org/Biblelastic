# Meaning-based search: the embedding trial

The plan is for an optional meaning-based index: each passage is turned into a list of numbers (a *vector*) when the modules are built,
and a small model on the device turns the user's query into a vector, so that passages can be found by what they're about even when they use different words.
This trial was to find out which model to use, how small the vectors can be stored, how big the download is, and how long a query takes.

It was run on 16 November 2026 on a desktop computer, with one measurement on an Android phone (see *On a phone* below).
The scripts are in `bench/embeddings/` and `bench/embed-query/`. What was built from this is described in [Meaning.md](Meaning.md).

## Summary

- **It's worth having, but it's a modest gain.** On fifty questions like ‘Why do good people suffer?’, the best small model put more of the right passages
    in the first ten results than word matching did (a score of 0.39 against 0.29). It doesn't replace word matching, and it's not magic.
- **Put each passage's section heading in front of it.** That one change did more than any choice among the small models: it raised every method's score, by a quarter to two thirds.
- **Model for English: `bge-small-en-v1.5`** (MIT licence). As an 8-bit file it's a 32 MB download, with no loss of quality.
- **There's no good small model for Spanish yet.** `multilingual-e5-small` works but is a 113 MB download (plus 16 MB for its tokenizer),
    and is a little worse than the English model on English.
- **Store one byte for each dimension** (384 bytes for each passage: 3.4 MB for the whole OET-RV). That loses nothing. One *bit* for each dimension loses about a sixth with this model.
- **The very small ‘static’ models aren't good enough.** They need no real computing on the device, which would have suited low-end phones, but they scored no better than word matching.
- **Comparing a query with every passage is quick enough without an index structure**: 100,000 passages took 21 ms here.
- **How to run the model on the device isn't settled.** A pure-Rust runtime (tract) works inside WebAssembly, but adds 14 MB to the engine and is much slower than ONNX Runtime
    (33 ms a query in a desktop browser, against about 2 ms natively). On an Android phone with 4 GB of memory, a query took 0.55 s with the 8-bit model and 0.64 s with the full-precision one, which is too slow.
    ONNX Runtime's WebAssembly build took 0.24 s on the same phone: better, but still slow, and much less of an improvement than on the desktop.

## What was tested

**Passages.** The OET-RV, cut into 8,725 pieces: runs of paragraphs within one section, mostly of 80 to 200 words (`bench/embeddings/passages.py`).

**Queries**, each with a list of the passages that are right answers (a piece counts if it overlaps any of them):

| Set | Queries | What they are |
| --- | --- | --- |
| questions | 50 | Written by hand for this trial (`bench/embeddings/questions.tsv`): subjects, doctrines, and stories described without their usual names, e.g., ‘once saved, always saved’ or ‘a prophet swallowed by a huge fish’ |
| questions in Spanish | 50 | The same in Spanish, still searching the English text |
| themes | 298 | The titles of the Tyndale Open Study Notes' theme articles; the right answers are the passages each article refers to |
| people | 125 | The titles of the same notes' profiles of people |
| headings | 500 | OET-RV section headings; the right answer is that section |

**Score.** nDCG@10: from 0 to 1, how well the right passages are placed in the first ten results.
The lists of right answers are far from complete, so the scores are low for every method and only comparisons mean anything.
With fifty questions, differences smaller than about 0.03 shouldn't be relied on.

**Models** (all with MIT or Apache-2.0 licences):

| Model | Kind | Languages | Dimensions |
| --- | --- | --- | --- |
| `potion-base-8M`, `potion-retrieval-32M` | Static (a table of word-piece vectors that are averaged) | English | 256, 512 |
| `potion-multilingual-128M` | Static | 101 languages | 256 |
| `all-MiniLM-L6-v2` | Small transformer | English | 384 |
| `bge-small-en-v1.5` | Small transformer | English | 384 |
| `multilingual-e5-small` | Small transformer | About 100 languages | 384 |
| `bge-m3` | Large transformer (2.3 GB), as a measure of what's possible | About 100 languages | 1024 |

## Results

With each passage's section heading in front of it, and one byte for each dimension:

| | Questions | In Spanish | Themes | People |
| --- | --- | --- | --- | --- |
| Word matching only (BM25) | 0.29 | 0.00 | 0.16 | 0.39 |
| `potion-base-8M` | 0.27 | | 0.15 | 0.30 |
| `potion-retrieval-32M` | 0.29 | | 0.17 | 0.39 |
| `potion-multilingual-128M` | 0.20 | 0.12 | 0.09 | 0.28 |
| `all-MiniLM-L6-v2` | 0.35 | | 0.16 | 0.32 |
| **`bge-small-en-v1.5`** | **0.39** | | 0.17 | 0.33 |
| `multilingual-e5-small` | 0.34 | 0.24 | 0.16 | 0.41 |
| `bge-m3` (too big for a phone) | 0.43 | 0.39 | 0.19 | 0.50 |
| `bge-small-en-v1.5` combined with word matching | 0.37 | | 0.19 | 0.42 |
| `multilingual-e5-small` combined with word matching | 0.38 | 0.15 | 0.19 | 0.42 |

- **Headings.** Without the headings the same table reads 0.23 for word matching, 0.26 for `bge-small-en-v1.5`, 0.21 for `multilingual-e5-small`, and 0.31 for `bge-m3`.
    (With the headings in, the ‘headings’ queries prove nothing, so they're left out above. Without them, `bge-small-en-v1.5` scored 0.27 against 0.22 for word matching.)
- **Combining** the two rankings (by reciprocal rank fusion) helps most for names of people and for the themes, and makes little difference to the questions.
    For Spanish queries against English text, word matching finds nothing, so combining only does harm: it should be left out when the languages differ.
- **Names.** Word matching does best on the people's names, even though the OET-RV spells many of them differently (Yitshak for Isaac), because it gives the familiar name once in each section.
- **Spanish** was only tested against English text, because no Spanish Bible has been ingested yet. Spanish queries against a Spanish text should do better than this.

### How the vectors are stored

For `bge-small-en-v1.5` (384 dimensions), with headings. The other models behave the same way, unless noted.

| Stored as | Bytes for each passage | The OET-RV (8,725 passages) | 100,000 passages | Questions |
| --- | --- | --- | --- | --- |
| 32-bit numbers | 1,536 | 13.4 MB | 154 MB | 0.39 |
| **One byte for each dimension** | **384** | **3.4 MB** | **38 MB** | **0.39** |
| One bit for each dimension | 48 | 0.4 MB | 4.8 MB | 0.33 |
| Bits to find the best hundred, then bytes to put them in order | 432 | 3.8 MB | 43 MB | 0.39 |
| Only the first half of the dimensions, as bytes | 192 | 1.7 MB | 19 MB | 0.34 |

- One byte for each dimension lost nothing for any model.
- Bits lose from 6% (`bge-m3`) to 26% (`multilingual-e5-small`). Each model's average vector has to be taken away first, or `multilingual-e5-small` loses nearly everything.
- Bits are only worth it as a first pass over far more passages than this. At 100,000 passages, comparing bytes is already fast enough (see below).
- Cutting off half the dimensions costs about as much as going to bits, for a smaller saving.

### The model on the device

The passages are embedded when the modules are built, so only queries are embedded on the device.
The 8-bit versions of the models (ONNX files, from the Xenova conversions) were run on one processor thread with ONNX Runtime:

| Model | Download | A query (desktop, one thread) | Questions | Same vectors as full precision? |
| --- | --- | --- | --- | --- |
| `bge-small-en-v1.5` | 32.4 MB + 0.7 MB tokenizer | 2.1 ms | 0.39 | Yes (0.996) |
| `multilingual-e5-small` | 112.8 MB + 16.3 MB tokenizer | 1.8 ms | 0.34 (0.25 in Spanish) | Yes (0.997) |
| `all-MiniLM-L6-v2` | 21.9 MB + 0.7 MB tokenizer | 5.3 ms | 0.22 | No (0.56): this conversion doesn't reproduce the model, and wasn't looked into further |

Most of `multilingual-e5-small` is its table of 250,000 word pieces for a hundred languages (about 96 MB of the 113 MB).
Cutting that down to the pieces that English and Spanish use should bring it to roughly 35 MB, but that hasn't been tried.

### Running it in Rust and in a browser

The engine is one Rust library that's also compiled to WebAssembly, so the model needs to run there too.
[tract](https://github.com/sonos/tract), an ONNX runtime written in Rust, was tried with `bge-small-en-v1.5` (`bench/embed-query/`), on queries of up to 32 word pieces:

| | Model file | A query | Memory used | Loading the model |
| --- | --- | --- | --- | --- |
| ONNX Runtime, native (for comparison) | 8-bit, 32 MB | about 2 ms | | |
| tract, native | full precision, 127 MB | 14 ms | | 0.2 s |
| tract, native | 8-bit, 32 MB | 65 ms | | 0.3 s |
| tract in Chrome (WebAssembly with SIMD) | full precision, 127 MB | 33 ms | 387 MB | 0.3 s |
| tract in Chrome (WebAssembly with SIMD) | 8-bit, 32 MB | 101 ms | 112 MB | 0.7 s |
| … with Chrome's processor slowed six times | full precision | 205 ms | 387 MB | 1.7 s |
| … with Chrome's processor slowed six times | 8-bit | 648 ms | 112 MB | 4.2 s |

- tract gives the same vectors as ONNX Runtime (agreement of at least 0.992), and compiles for the engine's WebAssembly target with one small workaround.
- It adds 14.1 MB to the engine (2.4 MB gzipped), which is now 0.4 MB.
- Its 8-bit arithmetic is slow: five times slower than its own full-precision arithmetic. But the full-precision model is four times the download and uses 387 MB of memory,
    which is too much for a phone with 2 GB.
- Without SIMD it's three times slower again (107 ms and 202 ms).
- Queries were tokenised in Python for this trial. The engine would need its own tokenizer (for this model, a table of 30,522 word pieces and a simple longest-match rule).

### On a phone

One Android phone (an OPPO, model code CPH2579, with 8 processors, and 4 GB of memory as Chrome reports it) ran the test page in Chrome:

| | Desktop Chrome | Slowed six times | The phone |
| --- | --- | --- | --- |
| Loading the 8-bit model | 0.7 s | 4.2 s | 5.9 s |
| A query (tract, 8-bit model) | 101 ms | 648 ms | 548 ms |
| Loading the full-precision model | 0.3 s | 1.7 s | 2.3 s |
| A query (tract, full-precision model) | 33 ms | 205 ms | 638 ms |
| Comparing with 100,000 passages | 21 ms | 128 ms | 231–234 ms |

So this phone is five to twenty times slower than the desktop, and its 4 GB is more than the target of 2–3 GB, where it's likely to be slower still.
More than half a second for each query is too slow, so tract is ruled out for now, with either model.

The full-precision model did load and run on the phone (it needs 387 MB), but it was no faster there than the 8-bit one, although it's three times faster on the desktop.
Why wasn't looked into: the phone's processor may simply be much slower at this arithmetic, or the model may be too big for its memory caches.
So desktop timings, even slowed down, don't predict a phone's well, and each candidate needs measuring on a real one.

Comparing with the passages is fine for one Bible (about 20 ms for 8,725 passages), but 100,000 passages would want the bits-first shortlist or compiled code instead of plain JavaScript.

### ONNX Runtime in the browser

ONNX Runtime's own WebAssembly build (the `onnxruntime-web` package, version 1.31.1, MIT licence) was then tried on the same queries, on one thread (`bench/embed-query/web/ort.html`).
It's 14.8 MB (3.8 MB gzipped) plus 0.4 MB of JavaScript, so about the same size as tract.

| A query with the 8-bit model | Desktop Chrome | Slowed six times | The phone |
| --- | --- | --- | --- |
| tract, padded to 32 word pieces | 101 ms | 648 ms | 548 ms |
| ONNX Runtime, padded to 32 word pieces | 17 ms | 100 ms | 344 ms |
| ONNX Runtime, at the query's own length (11 on average) | 10 ms | 61 ms | 237 ms |
| Loading the runtime and the model (ONNX Runtime) | 0.3 s | 1.4 s | 3.3 s |

On the desktop, ONNX Runtime is six times faster than tract. On the phone it's only 1.6 times faster, and a query still takes about a quarter of a second, after three seconds to load.
That's usable for a search that the user has asked for, but not for searching as they type.
With the full-precision model on the desktop it took 32 ms padded and 17 ms at the query's own length, the same as tract.

Not padding matters: the queries average 11 word pieces, and running them at their own length saved about a third on the phone.

**Comparing with every passage**, as bytes, in plain JavaScript: 5 ms for 8,725 passages and 21 ms for 100,000 (23 ms and 128 ms with the processor slowed six times).
So no approximate index (such as HNSW) is needed at this size.

## What this suggests

1. Build the vectors from each passage with its section heading, with `bge-small-en-v1.5` for English, stored as one byte for each dimension in an optional module.
1. Keep word matching as the main search, and add the meaning-based results to it (leaving word matching out only when the query's language isn't the text's).
1. The on-device runtime is still open. tract is too slow on a phone with either model. ONNX Runtime is the fastest that was tried (a quarter of a second for a query on the phone, in a browser),
    but it's a separate native library for each platform and a JavaScript package for browsers. Its native Android library, which can use more of the processor than WebAssembly can, is likely to be faster, and should be measured before deciding.
    The other choice is writing the model's arithmetic into the engine (about twelve layers of matrix multiplication: no dependency, but it must be made fast).
1. Whatever runs the model, give it each query at its own length, load it only when a meaning-based search is first asked for, and show the word-matching results first.
1. For Spanish, either cut `multilingual-e5-small` down to English and Spanish word pieces and test it again, or wait for a smaller multilingual model.
    Test it against a Spanish Bible, not just the English one.

## Not done

- **Only one phone was measured, and it has more memory than the target.** `bench/embed-query/web/` is the test page.
- **ONNX Runtime was only tried in a browser, on one thread.** Its native Android library, more threads, and WebGPU weren't tried.
- **The questions are few and were written by one person** (with the lists of right passages from memory), and the passages are from one translation.
- **Commentaries and dictionaries weren't embedded.** By size, the study notes (17,478 entries) would need about 7 MB of vectors, and the dictionary (about 31,000 paragraphs) about 12 MB.
- **Longer and shorter passages weren't compared**, nor other ways of dividing the text.
- **Only a few models were tried**, and newer small models keep appearing.

## Running it again

    python3 bench/embeddings/passages.py                                  # Needs build/intermediate (the ingest)
    uv venv --python 3.12 build/embeddings/venv
    uv pip install --python build/embeddings/venv/bin/python torch sentence-transformers model2vec onnxruntime
    build/embeddings/venv/bin/python bench/embeddings/evaluate.py         # Without the headings (downloads the models: about 6 GB)
    build/embeddings/venv/bin/python bench/embeddings/evaluate.py --headed
    cd bench/embeddings && ../../build/embeddings/venv/bin/python quantised.py && ../../build/embeddings/venv/bin/python export_queries.py && cd ../..
    bench/embed-query/build.sh
    mkdir -p build/embeddings/ort && cd build/embeddings/ort && npm pack onnxruntime-web && tar -xzf onnxruntime-web-*.tgz && cd ../../..
    node bench/embed-query/test.mjs                                       # tract, then ONNX Runtime, in headless Chrome
