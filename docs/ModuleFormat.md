# Biblelastic module format (v1)

A module is one file (`.blm`) that the engine reads directly. Modules are what users will download.
They're compiled from the [intermediate format](IntermediateFormat.md) by `biblelastic compile`,
which also writes `index.json`: the catalogue of the modules and their sizes.

This is version 1, and it will change again (see *Known gaps* below).
The engine refuses any module whose format version it doesn't know, so modules must be compiled again when the version changes.
(Version 0 stored each section whole and uncompressed. Version 1 stores them as pages, compressed where that helps.)

    cargo build --release
    target/release/biblelastic compile                         # build/intermediate → build/modules
    target/release/biblelastic info                            # List the modules
    target/release/biblelastic info OET-RV.text                # List the sections of one module
    target/release/biblelastic terms love loves loved loving   # The original-language terms behind these words
    target/release/biblelastic find grace truth --within sentence
    target/release/biblelastic marked pronoun_to_name          # Where the translators marked an addition or change
    target/release/biblelastic request command=find 'words=grace truth'   # The same as JSON, as an app gets it
    cargo test

## Design rules

- **Read-only.** A module is written once by the compiler and never changed.
- **Range reads only.** The engine asks its storage for `(offset, length)` byte ranges and nothing else,
    so the same code works on a local file, on browser storage, or on bytes in memory. Nothing depends on memory-mapping.
- **Column-based.** Each feature of a word is a separate section, so a query only reads the columns it uses,
    and an edition simply doesn't have the columns it has no data for.
- **Layered.** An edition is split across several modules that all number its words the same way,
    so that users can download only what they need, and so that data with a different licence stays separate.
- **Paged.** Each section is stored as pages of 16 kB. A page is only read when something in it is wanted, and the pages that have been read
    are kept in one cache of limited size (16 MB unless it's set otherwise), shared by all the open modules.
    So the engine's memory use doesn't grow with the number or size of the modules installed.
- **Compressed where it helps.** Each page of a section is compressed separately with zstd, if that saves at least a tenth for the section as a whole.
    That suits dictionaries and text. Postings lists and most columns of word numbers are already compact, and are left as they are.
- **Almost no dependencies.** The engine uses only the Rust standard library and one small zstd decoder (`ruzstd`, which is pure Rust),
    to keep it small and easy to build for WebAssembly. The compiler uses the standard zstd library.

## Slots

Every word of an edition has a *slot* number: the documents are put in order (front matter, New Testament, Old Testament, then the deuterocanonical and other books),
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

The first four editions compile to twelve modules totalling about 42 MB (from 142 MB of intermediate files, and 63 MB before compression).
The smallest useful download, `OET-RV.text.blm`, is 6.4 MB.

## File layout

All integers are little-endian.

| Offset | Size | Content |
| --- | --- | --- |
| 0 | 8 | `BLMODULE` |
| 8 | 2 | Format version (1) |
| 10 | 2 | Reserved |
| 12 | 4 | Length of the table of contents |
| 16 | 8 | Offset of the table of contents |
| 24 | 4 | CRC-32 of the table of contents |
| 28 | 4 | Reserved |
| 32 | | The sections, one after another |
| | | The table of contents |

The table of contents is a 4-byte count, then for each section:

- a 2-byte name length and the UTF-8 name
- a 1-byte encoding, a 1-byte bit width, a 1-byte compression (0 for none, 1 for zstd), and a 1-byte page size (as a power of two: 14 means 16 kB)
- an 8-byte offset, an 8-byte length before compression, and an 8-byte item count
- for each page: its 4-byte length as stored, and a 4-byte CRC-32 of it as stored.

The number of pages is the length before compression divided by the page size, rounded up. The pages are stored one after another from the section's offset,
and every page except the last holds exactly one page size of data once it's decompressed. Each compressed page is a complete zstd frame.

So opening a module takes two reads (the header, then the table of contents), whatever the module's size,
and after that any page can be found, read, checked, and decompressed on its own. Values, strings, and lists can cross from one page to the next.

`biblelastic compile --page-bits N` sets the page size, and `--no-compress` turns compression off. `biblelastic info MODULE` shows what each section came to.

## Section encodings

| Number | Name | Content |
| --- | --- | --- |
| 0 | Raw | Uninterpreted bytes, usually UTF-8 text |
| 1 | Packed | An array of unsigned integers, each using the same number of bits (the fewest that will hold the largest value), packed from the least-significant bit, followed by 8 bytes of padding |
| 2 | Strings | An array of strings: one 4-byte offset for each string plus one more for the end, then all the UTF-8 bytes |
| 3 | Varints | Lists of ascending integers, each list stored as the differences between its values, in LEB128 form |

A *dictionary* is a Strings section sorted by bytes, so a string can be found by binary search, and so can everything with a given prefix.

A *postings* index is a pair of sections: `….post.data` (Varints) holds one list of slots for each dictionary entry,
and `….post.offsets` (Packed) says where each list starts. Looking a word up reads only the pages that its list is in.

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

On the full data, starting with nothing in memory, on a desktop computer:

| Query | Version 0 | Version 1 |
| --- | --- | --- |
| `terms love loves loved loving` | 21 ms, reading 11.2 MB | 21 ms, reading 4.3 MB |
| `find grace truth` | 8 ms, reading 4.4 MB | 4 ms, reading 0.7 MB |
| `find love God` | 9 ms, reading 4.4 MB | 5 ms, reading 0.8 MB |
| `marked pronoun_to_name` | 9 ms, reading 4.4 MB | 11 ms, reading 2.3 MB |

With pages of 4 kB the first query reads 2.8 MB, not 4.3 MB, and the modules are 2% bigger. But browsers that have to use the slower way of reading
(see [Browser.md](Browser.md)) then take half as long again, because they pay for each read, so 16 kB is the default.

## Known gaps

- **Scattered lookups still read a lot.** A word that's used all through the Bible has something on most pages of each column that it needs,
    so the `terms` query still reads 4.3 MB. Small indexes of what's on each page would cut the binary searches down; they aren't there yet.
- **A page that can't be read stops the engine**, rather than giving an error for that one query (which matters in a browser, where the engine must then be restarted).
- **Lookups are two to four times slower than in version 0 once everything is in memory**, because every value now goes through the page cache.
    They're still microseconds, but a query that touches every occurrence of a very common word could be made faster.
- **Dictionaries are sorted string arrays**, not finite-state transducers, so there's prefix matching but no fuzzy matching yet.
    (That's deliberate for now: see the [comparison with Tantivy](IndexComparison.md).)
- **Queries are separate functions.** There's no general query tree yet, and query words are only lower-cased
    (so they must be typed without accents to match).
- **OET-LV word joiners** (`_` and `=`) and a few other unexplained source characters are displayed as they are in the source.
- **Node attributes aren't indexed.** They're stored as JSON text, so `marked` scans all the spans (which is still only about 10 ms).
- **Not compiled yet:** notes (footnotes and cross-references), variant readings, and versification mappings between editions.
- **Which columns are indexed**, and the compression level, are fixed in the compiler, rather than being set in the source registry.
- The WebAssembly build works in Chrome (see [Browser.md](Browser.md)), but hasn't been tried in other browsers or on a phone.
