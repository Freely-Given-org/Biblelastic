# Biblelastic module format (v0)

A module is one file (`.blm`) that the engine reads directly. Modules are what users will download.
They're compiled from the [intermediate format](IntermediateFormat.md) by `biblelastic compile`.

This is version 0: it proves the design end to end, and it will change (see *Known gaps* below).
The engine refuses any module whose format version it doesn't know.

    cargo build --release
    target/release/biblelastic compile                         # build/intermediate → build/modules
    target/release/biblelastic info                            # List the modules
    target/release/biblelastic info OET-RV.text                # List the sections of one module
    target/release/biblelastic terms love loves loved loving   # The original-language terms behind these words
    target/release/biblelastic find grace truth --within sentence
    target/release/biblelastic marked pronoun_to_name          # Where the translators marked an addition or change
    cargo test

## Design rules

- **Read-only.** A module is written once by the compiler and never changed.
- **Range reads only.** The engine asks its storage for `(offset, length)` byte ranges and nothing else,
    so the same code works on a local file, on browser storage, or on bytes in memory. Nothing depends on memory-mapping.
- **Column-based.** Each feature of a word is a separate section, so a query only reads the columns it uses,
    and an edition simply doesn't have the columns it has no data for.
- **Layered.** An edition is split across several modules that all number its words the same way,
    so that users can download only what they need, and so that data with a different licence stays separate.
- **No dependencies.** The engine uses only the Rust standard library, to keep it small and easy to build for WebAssembly.

## Slots

Every word of an edition has a *slot* number: the documents are put in order (currently alphabetical by book code),
and the words are numbered consecutively from zero right through them.
A slot is also a position, so an index of slots is automatically a positional index.
All the modules of one edition use the same slot numbers.

## Modules

| File | Kind | Contains |
| --- | --- | --- |
| `<EDITION>.text.blm` | `text` | The words (`before`, `text`, `after`), the `norm` search form and its index, the documents, and all the nodes |
| `<EDITION>.morph.blm` | `features` | The edition's other word columns, e.g., `lemma`, `strong`, `morph`, `translit` |
| `<EDITION>.<LAYER>.blm` | `features` | The columns of one intermediate-format layer, e.g., `SR-GNT.OET.blm` has the OET glosses and tags |
| `<FROM>--<TO>.align.blm` | `alignment` | Word-to-word links between two editions |

The first four editions compile to twelve modules totalling about 64 MB (from 140 MB of intermediate files).
The smallest useful download, `OET-RV.text.blm`, is under 9 MB without any general-purpose compression yet.

## File layout

All integers are little-endian.

| Offset | Size | Content |
| --- | --- | --- |
| 0 | 8 | `BLMODULE` |
| 8 | 2 | Format version (0) |
| 10 | 2 | Reserved |
| 12 | 4 | Length of the table of contents |
| 16 | 8 | Offset of the table of contents |
| 24 | 4 | CRC-32 of the table of contents |
| 28 | 4 | Reserved |
| 32 | | The sections, one after another |
| | | The table of contents |

The table of contents is a 4-byte count, then for each section:
a 2-byte name length and the UTF-8 name, a 1-byte encoding, a 1-byte bit width, 2 reserved bytes,
then an 8-byte offset, an 8-byte length, an 8-byte item count, and a 4-byte CRC-32 of the section.

So opening a module takes two small reads (the header, then the table of contents), whatever the module's size.

## Section encodings

| Number | Name | Content |
| --- | --- | --- |
| 0 | Raw | Uninterpreted bytes, usually UTF-8 text |
| 1 | Packed | An array of unsigned integers, each using the same number of bits (the fewest that will hold the largest value), packed from the least-significant bit, followed by 8 bytes of padding |
| 2 | Strings | An array of strings: one 4-byte offset for each string plus one more for the end, then all the UTF-8 bytes |
| 3 | Varints | Lists of ascending integers, each list stored as the differences between its values, in LEB128 form |

A *dictionary* is a Strings section sorted by bytes, so a string can be found by binary search, and so can everything with a given prefix.

A *postings* index is a pair of sections: `….post.data` (Varints) holds one list of slots for each dictionary entry,
and `….post.offsets` (Packed) says where each list starts. Looking a word up reads only that word's list.

## Sections

In every module:

| Section | Encoding | Content |
| --- | --- | --- |
| `module.kind` | Raw | `text`, `features`, or `alignment` |
| `module.edition`, `module.layer` | Raw | For text and features modules |
| `module.from`, `module.to` | Raw | For alignment modules |
| `manifest` | Raw | The edition's intermediate-format manifest (JSON), including its copyright and licence details |
| `documents.names` | Strings | The book codes, in slot order |
| `documents.starts` | Packed | The first slot of each document, plus the total number of slots |

For each feature column `X` (e.g., `col.text`, `col.lemma`):

| Section | Encoding | Content |
| --- | --- | --- |
| `col.X.dict` | Strings | Dictionary of the distinct values |
| `col.X.ids` | Packed | For every slot, the number of its value in the dictionary |
| `col.X.post.offsets`, `col.X.post.data` | | Postings (only for indexed columns): the slots that have each value |
| `idx.X.dict`, `idx.X.post.…` | | For multi-valued columns (currently only `tags`): a dictionary and postings for each separate value |

For each node type `T` (e.g., `verse`, `para`, `sentence`), in the text module, in order of where the nodes start:

| Section | Encoding | Content |
| --- | --- | --- |
| `node.T.starts`, `node.T.ends` | Packed | The slot range of each node (end exclusive) |
| `node.T.name.dict`, `node.T.name.ids` | | Each node's name, e.g., `3:16` for a verse or `q1` for a paragraph |
| `node.T.attributes.dict`, `node.T.attributes.ids` | | Each node's attributes (JSON, or empty) |

Finding the verse or sentence that contains a slot is a binary search of `starts`—there's no join.

In an alignment module:

| Section | Encoding | Content |
| --- | --- | --- |
| `links.from`, `links.to` | Packed | Every link as a pair of slots, sorted by the `from` slot |
| `rlinks.to`, `rlinks.from` | Packed | The same links sorted by the `to` slot, for looking up in the other direction |
| `module.slots` | Packed | The number of slots in the two editions |

One-to-many, many-to-one, and many-to-many alignments are just several links that share a slot.

## How the first two queries work

`terms love loves loved loving` (which original-language terms do these words translate?):

1. look each word up in the OET-RV `col.norm` dictionary, and read its postings to get the slots
1. for each alignment module from the OET-RV, binary-search `links.from` for each slot to get the original-language slots
1. read `col.lemma.ids` at those slots (from the original edition's `morph` module), and group and count by lemma
1. add the transliteration, Strong's number, and most common gloss from whichever installed modules have those columns
1. resynthesise an example verse for each term from the OET-RV `before`, `text`, and `after` columns.

`find grace truth --within sentence`: get the slots of each word as above, binary-search the sentence nodes to see which sentence each is in,
and keep the sentences that have them all.

On the full data each of these takes 10–30 ms on a desktop computer.

## Known gaps

- **Whole columns are loaded.** Apart from postings lists, a section is read whole the first time it's used
    (about 11 MB for the `terms` query). The Packed and Strings encodings allow reading just the parts needed, but the engine doesn't do that yet.
- **No general-purpose compression** (e.g., zstd) of dictionaries or long text.
- **Dictionaries are sorted string arrays**, not finite-state transducers, so there's prefix matching but no fuzzy matching yet.
- **Queries are separate functions.** There's no general query tree yet, and query words are only lower-cased
    (so they must be typed without accents to match).
- **OET-LV word joiners** (`_` and `=`) and a few other unexplained source characters are displayed as they are in the source.
- **Node attributes aren't indexed.** They're stored as JSON text, so `marked` scans all the spans (which is still only about 10 ms).
- **Not compiled yet:** notes (footnotes and cross-references), variant readings, and versification mappings between editions.
- **Which columns are indexed** is fixed in the compiler, rather than being set in the source registry.
- The WebAssembly build hasn't been tried.
