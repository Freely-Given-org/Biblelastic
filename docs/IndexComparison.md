# Our own indexes or Tantivy's?

[Tantivy](https://github.com/quickwit-oss/tantivy) is the best-known search engine library written in Rust.
This compares Biblelastic's own simple index structures (see the [module format](ModuleFormat.md)) with Tantivy and its building blocks,
on the real compiled modules, to decide whether to switch. Measured on a desktop computer on 16 November 2026, with version 0 of the module format.
(Version 1 reads through a page cache, which makes our lookups below two to four times slower. That doesn't change the conclusion.)

    cargo run --release --manifest-path bench/Cargo.toml       # After `biblelastic compile`

The benchmark is a separate crate in `bench/`, so that its 150 dependencies stay out of the engine.

## Conclusion

**Keep our own structures for now.** At the size of this data they're as small as Tantivy's and fast enough everywhere,
and they keep the engine free of dependencies. The one clear gain on offer is matching misspelt words, and that can wait until it's needed.

## A. Term dictionaries

Ours is a sorted array of strings. The alternative is a finite-state transducer (the `fst` crate, which is what Tantivy uses).

| | OET-RV words (18,479) | | UHB words (53,502) | |
| --- | --- | --- | --- | --- |
| | **array** | **fst** | **array** | **fst** |
| Size | 201 kB | 92 kB | 1,160 kB | 501 kB |
| Size after zstd | 66 kB | 63 kB | 230 kB | 266 kB |
| Find one word | 0.26 µs | 0.11 µs | 0.35 µs | 0.20 µs |
| Find a three-letter prefix | 0.5 µs | 2.7 µs | 5.9 µs | 38 µs |
| Find words within one edit | 400 µs | 22 µs | 1.2 ms | 33 µs |
| Find words within two edits | 520 µs | 115 µs | 1.8 ms | 196 µs |

- A transducer is half the size, but only until general-purpose compression is added (which is already planned); then there's nothing in it.
- Exact and prefix lookups are far below anything a user could notice, either way.
- For misspellings the array has no index at all, so it checks every word. That's 4 to 37 times slower than the transducer—but still under 2 ms
    on the largest dictionary. Even at ten times slower on a low-end phone, that's acceptable.
- Adding `fst` and `levenshtein_automata` would add up to 100 kB (37 kB gzipped) to the 225 kB WebAssembly engine.
- The `fst` crate's own Levenshtein search returned nothing at all for Hebrew words with vowel points (not even the word itself),
    so the figures above use the `levenshtein_automata` crate, as Tantivy does.

## B. Postings lists

Ours store the differences between positions as variable-length bytes. Tantivy packs blocks of 128 positions into the fewest bits, using SIMD instructions.

| | OET-RV words | | UHB lemmas | |
| --- | --- | --- | --- | --- |
| | **bytes** | **blocks** | **bytes** | **blocks** |
| Size | 1,482 kB | 1,506 kB | 449 kB | 473 kB |
| Size after zstd | 1,327 kB | 1,396 kB | 401 kB | 431 kB |
| Decode every list | 2.5 ms | 1.0 ms | 0.84 ms | 0.41 ms |
| Decode the longest list | 45 µs (‘the’, 57,889) | 13 µs | 9.7 µs (‘אֵת’, 11,871) | 2.7 µs |

- Blocks aren't smaller here: most words are rare, so most lists are much shorter than one block.
- Blocks decode two to three times faster, but the longest list in the whole Bible already takes only 45 µs.
- General-purpose compression saves only about 10% on postings, so it isn't worth applying to them.

## C. A whole Tantivy index

The OET-RV indexed with Tantivy: one document for each verse, with word positions, and no stored text.

| | Tantivy | Ours |
| --- | --- | --- |
| Index size | 2,329 kB | 1,916 kB (and it also covers headings and introductions) |
| Verses with ‘love’ (362) | 17 µs | 14 µs |
| Verses with ‘the’ (25,200) | 0.7 ms | 2.0 ms |
| Verses with ‘grace’ and ‘truth’ (5) | 1.9 µs | 9.6 µs |
| Verses with ‘love’ and ‘god’ (56) | 5.2 µs | 226 µs |
| ‘the messiah’ as a phrase (279) | 13 µs | not written yet |

Both engines found the same verses.

- Tantivy combines lists better: it skips through the longer list, where ours decodes both whole lists. That's worth copying when queries get more complex,
    but 0.2 ms isn't a problem yet.
- Tantivy doesn't build for browsers (`wasm32-unknown-unknown`) as it comes: one of its dependencies needs extra configuration and JavaScript glue.
    It also expects memory-mapped files and threads.
- It has no place for what Biblelastic most needs: words numbered across a whole edition, overlapping structures (verse, sentence, paragraph),
    feature columns, and word alignment between editions. Those would still have to be built beside it.

## What this shows should be improved instead

- **Reading less.** The ‘love’ query read 11 MB because whole columns were loaded. That, not the index structures, is the cost that matters on a low-end phone.
    (Done in version 1 of the module format: it now reads 4.3 MB, and memory use is limited.)
- **Compressing dictionaries** with zstd, which cuts them to between a fifth and a third. (Done in version 1.)
- **Skipping** when lists are combined, and a phrase query.
- **Near matches by checking every word**, with no new dependency, when misspelling-tolerant search is wanted.
