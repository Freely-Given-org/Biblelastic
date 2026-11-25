# Biblelastic

Fant**astic** open-source **Bible** study software!

A completely free, cross-platform, Bible study app

## Introduction

*Biblelastic* is a free and open, extensible, multi-lingual, cross-platform, Bible-study application that is intended to be
available on a range of devices from desktop computers to tablets to low-end phones.

It will allow Bible reading in a range of versions and format,
plus include complex modern-language searches (including theological terms, etc.)
combined with Hebrew, Aramaic, Greek restrictions. Example searches include:
    Find all the different Heb/Grk terms for 'love' in the Bible
    What do the scriptures and commentators say about 'once saved, always saved'
    What is Solomon's name in the original Hebrew (Note: a transliteration would also be expected in the answer here)
    Give all the sentences in the Bible where 'grace' and 'truth' are both mentioned in the same sentence.
    etc, etc.

Initially it will start with only open-licenced materials,
and it will be the first major Bible-study app to be based on *The Open English Translation of the Bible* (OET)
with its side-by-side *Readers’ Version* and *Literal Version* --
both with their marked formatting segments and their linked word numbers.

Although generally aimed at Western, protestant Christians who pretty much stick to 39 ‘Old Testament’
and 27 ‘New Testament’ ‘books’, it's designed from the start to also handle deuterocanonical/apocryphal
‘books’, along with other writings all the way from ‘church fathers’ and rabbinical commentators
to modern books.
(Note: some of those words are in ‘scare quotes’ because the *OET* uses different terminology for them.)

The database will include Hebrew, Aramaic, and Greek dictionaries, along with other ancient translations
and able to be accessed by a range of modern langages.

## Intended audience

*Biblelastic* is not aimed at full-time Christian professionals (incl. ministers and academics)
who can probably afford to spend thousands of dollars on expensive software.
It's aimed at the serious Christian student who wishes to make use of the power of modern computers
to assist them in getting the most out of their Bible study,
including showing them what is written in the Scriptures (including how it's translated from the originals)
as well as giving them ideas from commentaries that have been written over the centuries,
with the aim of helping the user to form their own ideas.

If asked to find Scriptures promoting a certain doctrinal viewpoint,
*Biblelastic* should automatically also append a segment showing
scriptural texts that support other viewpoints.

## Engine

It will need an offline way to load, index, and compress source materials with overlapping hierarchies,
and for the users' database copies (used for offline operated) to be added to.

Since natural language translations are involved, one-to-many, many-to-one,
and many-to-many relationships all need to be able to be handled.

The advanced indexing and compression, and then searching and resynthesis, of source materials will be the most vital part of Biblelastic.

## Frontends

Frontends will eventually need to be available on mobile phones,
tablets (including OSes capable of display multiple windows), desktops, and browsers,
and should all be able to work in either online or offline ways.

Offline working will require the user to manually request downloads of compressed, indexed materials.

## Source materials

Only materials that we are allowed to redistribute will be published as downloadable modules.
Each module will carry its own copyright, licence, and acknowledgement details,
and the build process will refuse to publish anything that isn't marked as redistributable.
(This means that most modern commercial translations, which only permit a limited number of verses to be quoted,
can't be included as full texts.)

The starting point will be the materials already collected for https://Freely-Given.org/OBD/ (Open Bible Data).
The licence of each one will be checked again before it's included. The planned categories are:

- **The OET**: the *Open English Translation* Readers’ Version and Literal Version,
    including their word-level links back to the original languages.
- **Original-language texts**: Hebrew and Aramaic (e.g., the unfoldingWord Hebrew Bible)
    and Greek New Testaments (e.g., the CNTR Statistical Restoration, Robinson-Pierpont Byzantine, SBL),
    with lemmas and morphology where available.
- **Ancient translations**: the Greek Septuagint (Brenton), the Latin Vulgate, and others as they become available.
- **Open-licenced and public-domain translations**: modern ones (e.g., the Berean Bibles, World English Bible, unfoldingWord ULT and UST)
    and historical ones (e.g., KJB 1611 and 1769, Geneva, Tyndale, Wycliffe, Luther),
    with Spanish and other languages to follow.
- **Dictionaries and lexicons**: Hebrew, Aramaic, and Greek dictionaries (e.g., the United Bible Societies open-licenced dictionaries),
    Bible dictionaries, and original-language grammars.
- **Translation and study notes**: e.g., unfoldingWord Translation Notes and SIL Open Translator’s Notes.
- **Cross-references and topics**: cross-reference collections, topical indexes,
    and people/places data (e.g., Theographic Bible Metadata).
- **Other writings**: commentaries, ‘church fathers’, rabbinical commentators, and other books,
    starting with public-domain works.

Lists such as https://github.com/jcuenod/awesome-bible-data will be used to find more open materials.
Suggestions of other open-licenced resources are very welcome.

Downloaded source files will be cached (not fetched on every rebuild)
and checked periodically for updated versions.

## More technical details

*This is the planned design. Only the first pieces are implemented (see ‘Current status’ below), and details will change as it's tested.*

### Current status

There's the start of the build pipeline and engine, and a minimal app (for Android and browsers) that reads, searches, and shows notes (see [docs/App.md](docs/App.md)).
Four Bible editions (OET-RV, OET-LV, SR-GNT, and UHB), one commentary (Tyndale Open Study Notes), one dictionary (Tyndale Open Bible Dictionary),
the UBS Hebrew and Greek dictionaries (as the meaning of each original-language word), the UBS handbooks on animals, plants, and objects,
sixty-two free books from books.freely.giving (every English or Spanish one there that's CC0 or in the public domain and has an EPUB: from Puritan classics to a study of Mark and a commentary on Jude),
and in Spanish two Bibles (the Aquifer Spanish Bible Reference Text and the Reina-Valera 1909) with the Aquifer's Spanish study notes and Bible dictionary
can be converted and compiled, and three of the example searches above already work (the third only as a first sketch):

    cd pipeline && python3 -m biblelastic_ingest && cd ..      # Source texts → build/intermediate/
    cargo build --release
    target/release/biblelastic compile                         # build/intermediate/ → build/modules/
    target/release/biblelastic terms love loves loved loving   # The Hebrew and Greek terms behind these words
    target/release/biblelastic find grace truth --within sentence
    target/release/biblelastic marked pronoun_to_name          # Where the OET-RV has a name in place of a pronoun
    target/release/biblelastic about JHN 3:16                  # What the commentary and dictionary say about a passage
    target/release/biblelastic entry aaron                     # Look up a dictionary entry
    target/release/biblelastic topic once saved, always saved  # What the Scriptures and the commentators say about a subject
    target/release/biblelastic model ~/.cache/huggingface/hub/models--BAAI--bge-small-en-v1.5/snapshots/*/ && target/release/biblelastic embed
    target/release/biblelastic meaning why do good people suffer   # Passages about a subject, by meaning (see docs/Meaning.md)
    target/release/biblelastic meaning --edition spa ¿Por qué sufren las personas buenas?   # … in the Spanish works

(The ingest expects the source texts to be in folders alongside this one, as listed in `pipeline/sources.toml`.)
See [docs/IntermediateFormat.md](docs/IntermediateFormat.md) and [docs/ModuleFormat.md](docs/ModuleFormat.md) for the details.

The same engine also runs in a browser, reading the same modules from the browser's own storage (see [docs/Browser.md](docs/Browser.md)):

    web/build.sh                                               # Compiles the engine to WebAssembly
    python3 -m http.server 8377                                # Then open http://localhost:8377/web/

### One engine everywhere

The engine is a single Rust library. It's linked directly into the Android app (and will be into the other phone, tablet, and desktop apps),
and it's compiled to WebAssembly for browsers, so that searching works the same way everywhere, including offline.
The server will only need to host static files: a catalogue and the downloadable modules.

### Data model

Rather than a relational database, the texts will be stored in a compact, read-only, column-based format
(similar in concept to [Text-Fabric](https://github.com/annotation/text-fabric)):

- Every word in an edition gets a consecutive number (its ‘slot’).
- **Features** are columns of information about each word: its displayed form, a normalised form for searching,
    lemma, Strong’s number, morphology, gloss, etc. An edition only includes the columns it has data for.
- **Nodes** are ranges of words: verses, chapters, paragraphs, sections, sentences, clauses, etc.
- **Alignments** link the words of a translation to the original-language words that they translate.
- Each edition declares its own versification, which is mapped to a common reference scheme when the module is built.
- Non-Bible works use the same model, with their own location schemes (e.g., volume/chapter/section, or dictionary headword),
    and a record of which Bible passages each entry is about and which ones it cites.

Nothing in the engine assumes a 66-‘book’ Bible—a ‘book’ is just a document in a collection.

### Indexes

All indexes will be created in advance as part of the build, so that devices only need to read them:

- **Word indexes** for each searchable feature (word, lemma, Strong’s number, morphology),
    with language-aware normalisation (e.g., Hebrew with or without vowels, Greek without accents).
- **Structure indexes** for searches like ‘in the same verse / clause / paragraph’.
- **Reference indexes** to find a passage in every edition, and to find everything that comments on or cites a passage.
- **Alignment indexes**, so a search for an English word can be followed through to the Hebrew/Greek words behind it
    (and back again), e.g., to list and count all the different original terms translated as ‘love’.
- **Topic and concept indexes**, linking topics and theological terms to their related terms and key passages.
- **Meaning-based (vector) indexes**, as an optional download, to find passages that are about a subject
    even when they don't use the same words.

The results from these are combined and ranked. Results are always the actual source passages with their locations—the
engine doesn't generate its own answers.

### Compression and resynthesis

The displayed text is rebuilt (‘resynthesised’) from the indexed word columns, so the text isn't stored twice.
Columns and indexes are stored in compressed forms that can be read in small pieces,
so that only the parts needed for a particular page or search are loaded.
This is what allows it to run on low-end phones and inside browsers.

### Modules

Each resource will be packaged as one or more versioned module files, with separate layers
(text, morphology, alignment, meaning-based index) so that users with limited storage or data
can download only what they need. The engine works with whichever modules are installed.

### Build pipeline

1. **Fetch**: download and cache the source materials, recording their versions and licences.
1. **Ingest**: Python scripts convert the many source formats into one common
    [intermediate format](docs/IntermediateFormat.md) of words, ranges of words, notes, and word alignments.
    (This is working for the OET-RV, OET-LV, SR-GNT, UHB, and the two Tyndale works, and more will be added.)
1. **Compile**: a Rust tool creates, indexes, and compresses the [modules](docs/ModuleFormat.md). (More checks will be added.)
1. **Publish**: copy the redistributable modules and the catalogue to the server.

### Frontends

The frontends are written in [Flutter](https://flutter.dev) (so far a minimal app in `app/`), starting with English and Spanish interfaces,
with allowance for more languages to be added later.