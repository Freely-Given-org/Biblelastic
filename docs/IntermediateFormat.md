# Biblelastic intermediate format (v0.1)

The intermediate format sits between the many source formats (USFM, ESFM, TSV, etc.)
and the compiled, compressed modules that the engine reads.
It's plain UTF-8 text (TSV and JSON), so it's easy to inspect, compare, and create from any language.
It's not intended for distribution, and it will change as more kinds of sources are added.

It's created by the `pipeline/biblelastic_ingest` Python package (standard library only, Python 3.12+):

    cd pipeline
    python3 -m biblelastic_ingest                       # Everything in sources.toml
    python3 -m biblelastic_ingest --editions OET-RV,SR-GNT --books MRK
    python3 -m biblelastic_ingest --clean               # Delete the old output first
    python3 -m unittest discover tests

Output goes into `build/intermediate/` (which is not committed).
Each source file is processed in its own process, so a full run of the first six editions takes several seconds.
(For a commentary or dictionary, each document is processed in its own process.)

Transliterations need the (CC0) [BibleTransliterations](https://github.com/Freely-Given-org/BibleTransliterations) library
in a folder alongside this one. Without it, a warning is given and those columns are left empty.

## Layout

    build/intermediate/
        report.json                         Statistics and check results for the last run
        <EDITION>/
            manifest.json                   Edition details, licence, token columns, list of documents
            documents/
                <BBB>.tokens.tsv            One row per word
                <BBB>.nodes.tsv             Ranges of words (verses, paragraphs, sentences, etc.)
                <BBB>.notes.tsv             Footnotes, cross-references, figures, and remarks
                <BBB>.meta.json             Headers, counts, warnings, and check results
                <DOCUMENT>.entries.tsv      Only for commentaries, dictionaries, etc.: the entries (study notes, articles, etc.)
                <DOCUMENT>.anchors.tsv      … the Bible passages that they're about, and that they cite
                <DOCUMENT>.links.tsv        … and the links from one entry to another
            layers/
                <LAYER>/
                    <BBB>.features.tsv      Extra feature columns from another source: one row per word
                    <BBB>.variants.tsv      Words that aren't in this edition's text (variant readings)
        alignments/
            <FROM>--<TO>/
                <BBB>.links.tsv             Word-to-word links between two editions
        thesaurus/
            <LANGUAGE>.tsv                  What people search for → the titles of entries about it

`<BBB>` is the three-character BibleOrgSys (BOS) book code (GEN, SA1, MRK, MA4, GES, DNG, etc.), which always starts with a letter.
Biblelastic uses BOS codes everywhere: any other (e.g., USFM's 1SA, 4MA, 1ES, or DAG, as in a USFM or ESFM file's `\id` line) is converted to one
as soon as it comes in, by `pipeline/biblelastic_ingest/book_codes.py`, whose table is written from BibleOrgSys's BibleBooksCodes table.
The engine converts the same ones (`reference.rs`), both in the passages it's given (e.g., `1CO 13:4` is `CO1 13:4`) and in a module's document names
as the module is loaded; `book_codes.py` writes its table too, and a test checks that the two are the same.
One *document* is one ‘book’. Nothing assumes any particular set of documents,
and the documents of other kinds of work have other names (see *Commentaries and dictionaries* below).

The manifest's `kind` says what an edition is: `scripture`, `commentary`, or `dictionary`.

## Tokens

`<BBB>.tokens.tsv` has a header row, then one row per word. A word's *index* is its zero-based row number within the document.
(The compiler will later turn these into edition-wide slot numbers.)

| Column | Meaning |
| --- | --- |
| `before` | Punctuation directly attached to the start of the word, e.g., an opening quote mark |
| `text` | The word exactly as it appears in the source |
| `after` | Everything between this word and the next one: punctuation, then (usually) a space |
| `norm` | A normalised form for searching (see below) |
| others | Edition-specific feature columns, listed in `token_columns` in the manifest |

Joining `before + text + after` for every word in a paragraph gives the paragraph's text.
Every run checks this against an independent reduction of the source file, so no text can be silently lost or reordered.

A word is a run of letters, digits, and combining marks (with internal apostrophes allowed, e.g., *didn't*).
Hyphenated words are separate tokens joined by a `-` in `after`.
The content of a USFM `\w …\w*` is always exactly one token.

The rules for splitting the text between two words are:

- if there's a space, everything up to and including the last space goes into the first word's `after`, and the rest into the second word's `before`
- if there's no space (e.g., OET-LV `of_the`, `he/it`, or Hebrew words joined by maqqef), it all goes into the first word's `after`
- trailing space at the end of a paragraph is dropped.

### OET marks

The OET's ESFM files use some special characters that aren't part of the text (they're explained on the OET's
[formats page](https://OpenEnglishTranslation.Bible/Resources/Formats)).
These are removed from the text and recorded as node attributes instead, so they're never displayed but the information isn't lost:

| In the source | Becomes | Values |
| --- | --- | --- |
| A character straight after `\add` | a `reason` attribute on that `add` span | `+` `article`, `=` `copula`, `<` `object`, `>` `implied`, `≡` `repeated`, `&` `owner`, `@` `pronoun_to_name`, `*` `name_to_pronoun`, `#` `number`, `%` `person`, `^` `opposite`, `!` `traditional_name`, `$` `measure`, `≈` `reworded`, and `?` on its own `unclear` |
| `?` before one of those characters | an `uncertain` attribute (`true`) on the span | |
| `≈`, `^`, or `→` at the start of a line of poetry | a `parallelism` attribute on that `para` (or on the `verse`, if the verse starts part-way through a paragraph) | `synonymous`, `antithetic`, `synthetic` |
| `⇔` at the start of a verse | a `reordered` attribute (`true`) on that `verse` | |

So, for example, the `add` spans with the reason `pronoun_to_name` are the places where the OET-RV has a name where the original has a pronoun.
This is only done for ESFM files. A run reports how many marks were converted (about 55,700 in the OET-RV and 25,800 in the OET-LV).

Other characters are still kept in `before`/`after` exactly as they appear in the source, because they aren't covered by that page:
the OET-LV's word joiners (`_` and `=`), `/` between alternatives, `◘` (apparently for a verse that's not in the text),
and `⟦…⟧`, `˓…˒`, and `§` in the OET-LV.

### Feature columns so far

| Column | Editions | Meaning |
| --- | --- | --- |
| `row` | OET-RV, OET-LV | ESFM word number: the row in the OET word table for the original-language word being translated |
| `oet_row` | SR-GNT, UHB | The OET word-table row that this original-language word corresponds to |
| `lemma`, `strong`, `morph` | SR-GNT, UHB | As given in the source |
| `koine` | SR-GNT | The unaccented manuscript-style form given in the source (including nomina sacra like `=ιυ`) |
| `lang` | UHB | `hbo` (Hebrew) or `arc` (Aramaic), from the morphology code |
| `cons` | UHB | Consonants only |
| `translit`, `lemma_translit` | SR-GNT, UHB | Transliterations of the word and of its lemma, e.g., `shəlomoh` |

`norm` is currently: for English, lower-case without diacritics or modifier letters;
for Greek, lower-case without accents or breathings and with only one form of sigma;
for Hebrew, vowel points kept but cantillation marks removed. These rules are provisional.

A word in the OET can share its `row` with others: several English words often translate one original word,
and where one number follows joined alternatives (e.g., `Yaʸsous/(Yəhōshūˊa)¦21572`) each of those words gets the number.

## Nodes

`<BBB>.nodes.tsv` has the columns `type`, `start`, `end`, `name`, `attributes`.
`start` and `end` are word indexes, with `end` exclusive. `attributes` is either empty or a JSON object.
Nodes of different types overlap freely (e.g., a sentence can cross verse, paragraph, and chapter boundaries),
and a node may be empty (`start == end`).

| Type | Name | Notes |
| --- | --- | --- |
| `book` | | The whole document |
| `chapter` | chapter number | From one `\c` to the next. `alt` and `published` attributes come from `\ca` and `\cp` |
| `verse` | `chapter:verse` | The body text words only. `c` and `v` attributes; `alt` comes from `\va`; `reordered` and `parallelism` from OET marks |
| `para` | the USFM marker (`p`, `q1`, `s1`, `mt1`, etc.) | `kind` attribute is `body`, `heading`, `title`, `intro`, or `other`; `parallelism` from OET marks. A paragraph with no words can have a `text` attribute |
| `section` | the heading text | From one `\s1` heading to the next |
| `span` | the USFM character marker (`add`, `nd`, `wj`, etc.) | Any attributes from the source (e.g., `link-href`), and `reason` and `uncertain` from OET marks |
| `sentence` | | Derived from punctuation (see below) |
| `milestone` | the marker | Custom unclosed markers, e.g., OET-RV `\z1` |

Sentences are a first approximation: `derived` is set to `punctuation` so that they can be replaced later by better data.
Only body and introduction words are considered, so a sentence that's interrupted by a section heading includes that heading in its range.

Verse and chapter numbers are those of the source edition. The edition's versification scheme is named in the manifest,
and mapping between schemes is left to the compiler.

## Layers

A layer holds information about an edition's words that comes from a different source than the text itself,
and so can have a different copyright and licence (which are listed for each layer in the edition's manifest).
Layers will become separate, optional downloads.

`layers/<LAYER>/<BBB>.features.tsv` has exactly one row for each row of `<BBB>.tokens.tsv`, in the same order,
so it's just more feature columns. So far there's one feature layer, `OET`, which is taken from the OET word tables:

| Column | Editions | Meaning |
| --- | --- | --- |
| `gloss` | SR-GNT, UHB | The OET's English gloss for the word |
| `context_gloss` | UHB | A gloss for the word in this particular context (where there is one) |
| `morpheme_glosses`, `context_morpheme_glosses` | UHB | Comma-separated glosses for each morpheme of a multi-morpheme word |
| `gloss_caps` | SR-GNT | Capitalisation codes for the gloss |
| `role` | SR-GNT, UHB | Part of speech (Greek) or clause role such as `S`, `V`, `O` (Hebrew) |
| `nesting` | UHB | The word's position in the syntax tree, e.g., `PP-V-S-O/Np2S/N2NP` |
| `tags` | SR-GNT, UHB | Semicolon-separated tags (see below) |
| `row_type` | UHB | `K` for a ketiv (written) form, `A` for Aramaic, or `AK` |

Each tag starts with a letter that gives its kind. These meanings are inferred from the data and still need to be confirmed:
`P` person, `L` location, `G` group, `Y` year (negative for BC), `E` event, `T` topic or story,
and `F`/`R` followed by a word-table row number, which link a word to another word that it refers to.

`layers/<LAYER>/<BBB>.variants.tsv` lists words that are *not* in the edition's text. It has the columns `anchor`
(the index of the next word that is in the text, so the variant comes before that word), `row` (the word-table row), and then feature columns.
So far there's one, `OET-variants` for the SR-GNT, with the columns `ref`, `status`, `text`, `lemma`, `strong`, `morph`, `role`, and `gloss`.
It doesn't say which manuscripts have each reading.

## Notes

`<BBB>.notes.tsv` has the columns `anchor`, `type`, `content`.
`anchor` is the number of words that come before the note. `type` is `f` (footnote), `x` (cross-reference), `fig` (figure), or `rem` (a remark line in the body).
`content` is the raw source content—it's not yet tokenised, so it can't yet be searched like the main text.

## Commentaries and dictionaries

These have tokens and nodes just like a Bible ‘book’ (so their text is displayed and searched in the same way), plus three more files.
They're made of separate items (study notes, articles, etc.), and each item becomes an *entry*.
The registry says which document each type of item goes into: either a named document, or one document for each Bible book that the items are about.

`<DOCUMENT>.entries.tsv` has the columns `start`, `end`, `name`, `type`, `title`, in order of `start` (`end` is exclusive, as for nodes).
`name` identifies the entry within its document, so an entry's *locator* is the edition, then the document, then the name:
e.g., `TOSN GEN 1:1-2:3` is a study note, and `TOBD Articles AbdonPerson` is a dictionary article whose `title` is ‘Abdon (Person)’.
`type` is whatever the source calls that kind of item, e.g., `StudyNote` or `Article`.

`<DOCUMENT>.anchors.tsv` has the columns `start`, `end`, `kind`, `reference`. These are the *Scripture anchors*:

| Kind | Meaning | `start` and `end` |
| --- | --- | --- |
| `about` | The entry is about this passage | The whole entry |
| `cites` | The entry refers to this passage | The words that are the link in the source, e.g., *Rom 5:8* |

`reference` is one book code and a passage in it: `GEN 1:1`, or `GEN 1:1-2:3` for a range (always with the chapter number on both sides).
A source reference to several passages gives several rows, and a range that goes from one book into another gives two rows
(with `999:999` for ‘to the end of the book’, and any books in between left out).
The chapter and verse numbers are the source's own, in the versification that the manifest names.

`<DOCUMENT>.links.tsv` has the columns `start`, `end`, `kind`, `target`. `kind` is `see` (the words from `start` to `end` are a link to another entry)
or `include` (another entry, e.g., a text box or a map, is displayed at this point, so `start` equals `end`).
`target` is the document and name of an entry in the same edition. The manifest lists any `broken_links`: targets that don't exist.
(Case is ignored when matching them, because the sources aren't consistent about it.)

The paragraph and span nodes are named by the source's own classes, e.g., `sn-text`, `h2`, `sn-excerpt`, `hebrew`.
Paragraphs have a `kind` attribute of `heading` or `body`, and sentences are derived from the body paragraphs (never crossing from one to the next).

So far there are two, both from [Tyndale Open Resources](https://tyndaleopenresources.com) (CC BY-SA 4.0), in the form that's been
[adapted for the OET](https://github.com/Freely-Given-org/OET_TyndaleOpenResources): names and some other wording are changed to match the OET-RV
(e.g., ‘Yeshua (Jesus; Grk. Yesus)’, and ‘Yahweh’ for ‘the LORD’), but references, links, and titles are as Tyndale has them:

| Edition | Kind | Documents | Entries | Words | Anchors |
| --- | --- | --- | --- | --- | --- |
| `TOSN` Tyndale Open Study Notes | `commentary` | One for each of the 66 books (16,923 study notes), plus `Intros`, `Summaries`, `Profiles`, and `Themes` | 17,478 | 1.12 million | 17,478 `about` and 55,554 `cites` |
| `TOBD` Tyndale Open Bible Dictionary | `dictionary` | `Articles`, `Textboxes`, `Charts`, `Maps`, and `Pictures` (captions only) | 6,431 | 1.53 million | 47,393 `cites` |

Twenty-seven more are public-domain works from CrossWire's [SWORD](https://crosswire.org/sword) library, read from each module's zip file by `pipeline/biblelastic_ingest/sword.py`
(the registry's `format = "SWORD"`): a dictionary module (zLD or RawLD) becomes one document, with an entry for each key, a general book (RawGenBook) a `Chapter` document like an EPUB book's,
and a commentary module (zCom or zCom4, of the whole Bible or the New Testament, in blocks of a book or a chapter) a document for each book, with an entry for each note (named like `1:1`, or `3:1-8` for a note on several verses, which SWORD links to each of them, and `about` those verses).
A note's type is the registry's `sword.notes` (`CrossReferences` by default). Their references are to the KJV's chapters and verses, which are taken from
BibleOrgSys's versification table, and are checked against it.

The two OSIS commentaries (Matthew Henry's and Jamieson, Fausset, and Brown's) keep what comes before a verse's note between ‘pre-verse’ milestones.
At a book's first note, that's the book's introduction, which becomes an entry of its own (`Intro`, a `BookIntro` about the whole book), with the book's own slot
(e.g., ‘Commentary by David Brown’) and, for a book of one chapter, its chapter's slot. At a chapter's first note, Matthew Henry's has the chapter's title and outline
(up to the first note's ‘Verses 1-8’), which becomes an entry named like `3` (an `Outline` about the whole chapter); a chapter with only one note, and no ‘Verses’,
has it about the whole chapter (e.g., Psalm 23's). Titles alone (e.g., Jamieson, Fausset, and Brown's ‘CHAPTER 3’ and its sections' titles) stay with the note, as `h2` headings,
unless the chapter's opening has more, which becomes an `Introduction` about the chapter. Adam Clarke's has no milestones, but each book's first note starts with its preface
(a `BookIntro`, which runs on into the first chapter's summary), and each other chapter's with an ‘Introduction’ (an `Outline`), before the note's ‘Verse 1’.
In the ThML commentaries (the TSK, Barnes's, and the People's New Testament), a chapter's own slot is a copy of a note from elsewhere (e.g., Acts 27:44's, before Romans), so it's left out;
Barnes's keeps a book's preface and introduction in its first verses' notes, which are `BookIntro`s about the book as well as those verses.
Scofield's has two notes whose markup is cut between them (a list that starts in Genesis 4:1's note and ends in 4:2's): an end tag without its start tag is left out, and a start tag without its end is ended.

The two devotionals are `book`s, with a document `Readings` of `Reading`s: Spurgeon's *Morning and Evening* keeps a day's two readings under one key, as sections with titles, and *Daily Light*
keeps them as parts that start with ‘*Morning*:’ and ‘*Evening*:’, under a key like `01.31` (the registry's `sword.parts` and `sword.dates`); each reading is an entry, titled like ‘Morning, January 31’.
*Daily Light*'s lines are wrapped with line breaks, so a single one is a space (`sword.wrapped`), and two start a paragraph. Josephus's works are a tree of keys (each work, its books, their chapters,
and their sections): an entry is a key whose keys under it have none under them (a chapter, with its sections), unless there are more than 20 (the *Life*'s and *Against Apion*'s sections),
when each is an entry; a key's own text (e.g., a book's title and summary) goes with the next entry, and Whiston's notes follow the paragraphs they're in, as `note` paragraphs.
The other general books follow the same rule, with a few more. Keys under a key that together are longer than 100,000 characters of markup are entries of their own
(e.g., the 19 sermons that are all under one key in Edwards's), and a long entry with headings is split at them (e.g., the Westminster catechisms, whose questions are each a heading in one long key).
An entry with nothing but headings goes with the next. A book that has only one key at the top doesn't have it in its titles, and a key named for the module (e.g., Owen's `JOGlory`) is named for the book.
Keys' names are tidied: `Lecture_01_Thesis_I` is ‘Lecture 1 Thesis I’, `Section 2_1` ‘Section 2.1’, and a name in capitals (e.g., `II. THE WAGES OF SIN.`) ‘II. The Wages of Sin’.
The registry's `sword.names` names keys (or, with ‘’, leaves a key out of the titles, e.g., the Westminster Larger Catechism's `Q1-50`), and `sword.skip` leaves keys out
(e.g., an index, or a modern reprint's foreword: a `*` matches anything). CCEL modernized the archaic words in Owen's works, with a note after each (‘you<note n="thou">Auto-modernized</note>’),
which isn't kept; nor are the links for a printed edition's pages in Walther's (‘<small><sup><a href="#29">29</a></sup></small>’). A paragraph in a note (e.g., each proof in the Westminster Confession's)
is a `note` paragraph. A reference that starts with a book's code (the Westminster Confession's ‘ROM 2:14’) is what its `osisRef` says, as is a ThML reference whose `passage` is an OSIS reference
(Walther's ‘<scripRef passage="Matt.15.13">Matt. 15, 13</scripRef>’, where ‘15, 13’ would otherwise be two chapters); and CCEL's ‘Revelation of John 22:16’ is Revelation's.

| Edition | Kind | Documents | Entries | Words | Anchors |
| --- | --- | --- | --- | --- | --- |
| `Easton` Easton's Bible Dictionary (1897) | `dictionary` | `Articles` | 3,963 | 0.47 million | 24,067 `cites` |
| `Nave` Nave's Topical Bible | `dictionary` | `Topics`: each line of a topic is a paragraph (`li`), and the topics' names are in lower case (`Love`, not `LOVE`) | 5,322 | 0.32 million | 77,922 `cites` |
| `TSK` Treasury of Scripture Knowledge | `commentary` | One for each of the 66 books: each verse's note (each word of the verse on a line with its references), and each chapter's outline (named like `1`, and `about` the whole chapter) | 32,243 | 1.34 million | 32,243 `about` and 387,166 `cites` |
| `MHCC` Matthew Henry's Concise Commentary | `commentary` | One for each of the 66 books: each book's introduction (`Intro`), each chapter's outline (named like `1`), and each note (named like `3:1-8`) | 5,161 | 0.72 million | 5,161 `about` and 1,210 `cites` |
| `JFB` Jamieson, Fausset, and Brown's Commentary (1871) | `commentary` | One for each of the 66 books: each book's introduction, a few chapters' introductions, and each verse's note | 17,452 | 1.82 million | 17,452 `about` and 56,201 `cites` |
| `Clarke` Adam Clarke's Commentary on the Bible | `commentary` | One for each of the 66 books: each book's preface (`Intro`), each other chapter's introduction (named like `2`), and each note | 22,059 | 3.59 million | 22,059 `about` and 32,489 `cites` |
| `Wesley` John Wesley's Notes on the Bible | `commentary` | One for each of the 66 books: its introduction, each chapter's (named like `3:0`), and each note | 18,865 | 1.01 million | 18,865 `about` and 5,280 `cites` |
| `Scofield` Scofield Reference Notes (1917) | `commentary` | One for each of the 66 books: its introduction, and each note | 3,269 | 0.14 million | 3,269 `about` and 11,005 `cites` |
| `Barnes` Barnes' New Testament Notes | `commentary` | One for each of the 27 books of the New Testament | 7,431 | 2.74 million | 7,457 `about` and 45,038 `cites` |
| `PNT` The People's New Testament (1891) | `commentary` | One for each book of the New Testament but Philemon, which the module has no notes on | 6,068 | 0.39 million | 6,068 `about` and 6,613 `cites` |
| `Torrey` Torrey's New Topical Textbook (1897) | `dictionary` | `Topics`: like Nave's, without the ‘- ’ and ‘. ’ that start its lines | 628 | 0.20 million | 38,858 `cites` |
| `Smith` Smith's Bible Dictionary (1884) | `dictionary` | `Articles` | 4,639 | 0.49 million | 16,831 `cites` |
| `Hitchcock` Hitchcock's Bible Names | `dictionary` | `Names`: what each name means | 2,616 | 0.01 million | none |
| `MorningAndEvening` Spurgeon's *Morning and Evening* | `book` | `Readings`: two for each day | 732 | 0.26 million | 779 `cites` |
| `DailyLight` *Daily Light on the Daily Path* | `book` | `Readings`: two for each day | 732 | 0.15 million | 7,001 `cites` |
| `Josephus` *The Works of Josephus* (William Whiston's translation) | `book` | `Chapter`: the *Life*'s and *Against Apion*'s sections, and the *Antiquities*' and *War*'s chapters | 657 | 0.84 million | none |
| `Holiness` *Holiness* (J. C. Ryle, 1879) | `book` | `Chapter`: Ryle's introduction, and each of the 21 papers | 22 | 0.17 million | 803 `cites` |
| `EdwardsSermons` *Select Sermons of Jonathan Edwards* | `book` | `Chapter`: each sermon | 19 | 0.19 million | 629 `cites` |
| `Christologia` *Christologia* (John Owen, 1679) | `book` | `Chapter`: the preface, and each chapter | 23 | 0.14 million | 711 `cites` |
| `CommunionWithGod` *Communion with God* (John Owen, 1657) | `book` | `Chapter`: each chapter and digression, and the *Vindication* | 32 | 0.19 million | 2,028 `cites` |
| `GloryOfChrist` *The Glory of Christ* (John Owen, 1684) | `book` | `Chapter`: each chapter, and the application to unconverted sinners | 21 | 0.10 million | 528 `cites` |
| `GospelThemes` *Sermons on Gospel Themes* (Charles G. Finney, 1876) | `book` | `Chapter`: each sermon | 26 | 0.14 million | none |
| `LawAndGospel` *The Proper Distinction Between Law and Gospel* (C. F. W. Walther, translated by W. H. T. Dau, 1929) | `book` | `Chapter`: each of the 39 lectures, and the preface and theses | 42 | 0.20 million | 520 `cites` |
| `Westminster` The Westminster Confession of Faith and Catechisms (1646–1647) | `book` | `Chapter`: each of the Confession's 33 chapters, and each question of the Shorter and Larger Catechisms, with their proofs as notes | 338 | 0.24 million | 5,736 `cites` |
| `PracticeOfThePresence` *The Practice of the Presence of God* (Brother Lawrence) | `book` | `Chapter`: the conversations, and the letters | 3 | 0.01 million | none |
| `Enoch` *The Book of Enoch* (R. H. Charles's translation, 1913) | `book` | `Chapter`: each chapter (or, in sections IV and V, the whole section), with Charles's notes and the cross-references | 75 | 0.06 million | 717 `cites` |
| `Jubilees` *The Book of Jubilees* (R. H. Charles's translation, 1913) | `book` | `Chapter`: Charles's introduction, and each chapter | 51 | 0.06 million | none |

Their references are read from the text that's shown, not from the modules' own `osisRef` attributes, because Easton's module gives every reference that's only numbers
(e.g., the ‘11’ and ‘21:6’ in ‘Rev. 1:8, 11; 21:6’) to Genesis. Such a reference is in the book of the reference before it: after a comma it's verses (unless it has a chapter),
and after a semicolon it's chapters (e.g., Nave's ‘1Ch 6:3; 24’). In the TSK, each line of references starts again from the verse that the note is about,
so its ‘8,13’ in the note on Genesis 1:5 is Genesis 1:8 and 1:13. A link to an entry that doesn't exist goes to the nearest one that does: its singular or plural,
or else the first whose name starts with it (e.g., Nave's ‘See ANGEL’ goes to ‘Angel (a Spirit)’). Smith's links are its `<term>`s (‘See <term>MONTH</term>’), and its references' `passage` attributes (‘1ch 12:27’) are used where they can be read.
The abbreviations the modules use, besides the usual ones, include Adam Clarke's ‘Sol’ and ‘Zac’, Wesley's ‘Numb’ and ‘Psal’, and Barnes's, whose converter doubled letters (‘1Timm’, ‘Romm’).
About 400 references (mostly errors in the sources, such as ‘Phm 2:10’), and 90 links (mostly to a topic's sub-topics), are still left out.
The TSK has no vectors for meaning-based search (its registry entry says `meaning = false`), because it's mostly references.

A sixth, `UBSH`, is the United Bible Societies' handbooks *Animals in the Bible*, *Plants and Trees in the Bible*, and *Objects in the Bible* (a `dictionary`,
with the documents `Fauna`, `Flora`, and `Realia`: 762 articles). It comes from a different XML format, but becomes the same files: see the next section.

## Books

A book is read from an EPUB file by `pipeline/biblelastic_ingest/epub.py`, and becomes the same files as a commentary or dictionary,
with one document, `Chapter`: each top-level item of the book's table of contents is an entry (so locators are `Chapter 1`, `Chapter 2`, …, and each entry's title is its item in the contents).
An item whose own text is only its title (e.g., Standard Ebooks' half-title page, with the book's name before all its chapters, or a page that only says ‘Book I’)
isn't an entry: the items under it are, and its title page goes with the first of them. A title may be split across lines (‘Part I’ and ‘On the Creature Called Man’),
and a book's own half-title page may have a subtitle too (‘Lilith’ and ‘A Romance’). Where one item at a level is split like this, so is a sibling whose page is short (e.g., with an epigraph too),
so that all of a book's chapters are entries (as in *Ben-Hur*). A chapter whose title is only a number takes its book's too (e.g., ‘Book II, III’ in *The Imitation of Christ*).

- **Paragraphs** are the book's blocks (paragraphs, list items, table cells), styled `h1`–`h3` (headings), `p`, `li`, or `note` (footnotes and endnotes;
    the footnote markers in the text are left out). A heading is an h1–h6 element, a block that the contents points to below its top level,
    or a block whose text the book's stylesheet makes bold and large (that's how some word processors mark headings).
    A short line that starts one of the book's files, and isn't a sentence, is a heading too: e.g., each prayer in *Praying the Bible Together* is a file that starts ‘God of Grace,’.
- **Bible references** in the text are found by `references.py` and become `cites` anchors: e.g., ‘John 3:16’, ‘2 Tim. 3:1–9’, ‘Rom 8:28, 31-39; 9:1’, ‘Mark 2-3:6’, or ‘Jude 5’.
    A book's name only counts when a number follows it (so ‘the Mark of a True Disciple’ isn't a reference). The registry's `context_book` is the Bible book
    that bare references (e.g., ‘(1:21-28)’, or ‘(1-2)’ for a one-chapter book) are in.
    References in a chapter or under a heading that's a list (an index, contents, bibliography, glossary, or abbreviations) aren't counted as citations,
    so a book's Scripture index doesn't make it cite every passage. Soft hyphens and zero-width spaces (hints for breaking lines) are removed.
- **What it's about:** a chapter whose title names a passage (e.g., ‘Mark 1:1-20’ or ‘Pericope #1: Jude 1-4’) is `about` that passage, and so is the text under
    a heading that names one (e.g., ‘1:21-28 Jesus heals’), up to the next heading of the same or a higher level. So a book's chapters are found by the notes on a verse, like a commentary's.

The registry gives each book's `download` address: the file is fetched once into `files` (under `build/downloads/`) and kept there.
Sixty-two are from [books.freely.giving](https://books.freely.giving), and all CC0 (or in the public domain). Five of those are in `sources.toml` itself:

| Edition | Kind | Entries | Words | Anchors |
| --- | --- | --- | --- | --- |
| `PritchardMark` *The Mark of a True Disciple* (Shelby and Elisabeth Pritchard, 2024): a study of Mark | `book` | 32 | 85,000 | 122 `about` and 571 `cites` |
| `PritchardJude` *Jude: A Theological Commentary* (Shelby Pritchard, 2025) | `commentary` | 8 | 30,000 | 13 `about` and 143 `cites` |
| `DoreanPrinciple` *The Dorean Principle* (Conley Owens, 2021) | `book` | 22 | 47,000 | 402 `cites` |
| `DoctrineOfSimony` *The Doctrine of Simony: A Theological Retrieval and Appraisal* (Conley Owens, 2026; from [simony.info](https://simony.info)) | `book` | 27 | 100,000 | 6 `about` and 360 `cites` |
| `AbolishTheJesusTrade` *Abolish the Jesus Trade* (Andrew Case, Conley Owens, Jon Here, and others, 2025) | `book` | 40 | 129,000 | 21 `about` and 933 `cites` |

The Pritchard books quote several copyrighted Bible translations (CSB, ESV, NET, LEB, LSB, NLT, NASB), and *The Dorean Principle* the ESV and NASB, by those publishers' permission,
so their notices are part of each manifest's `copyright`. *The Doctrine of Simony*'s translations are the author's own, and *Abolish the Jesus Trade* doesn't say which version it quotes.

Thirty-seven more are public-domain classics from [Standard Ebooks](https://standardebooks.org), which dedicates its own work on its editions to the public domain (CC0 1.0):

| Edition | Kind | Entries | Words | Anchors |
| --- | --- | --- | --- | --- |
| `UnspokenSermons` *Unspoken Sermons* (George MacDonald, three series, 1867–1889) | `book` | 44 | 177,000 | 59 `cites` |
| `Orthodoxy` *Orthodoxy* (G. K. Chesterton, 1908) | `book` | 14 | 65,000 | none |
| `ImitationOfChrist` *The Imitation of Christ* (Thomas à Kempis (translated by William Benham), 1877) | `book` | 120 | 64,000 | 184 `cites` |
| `WayToGod` *The Way to God and How to Find It* (D. L. Moody, 1884) | `book` | 14 | 42,000 | 207 `cites` |
| `PracticalMysticism` *Practical Mysticism: A Little Book for Normal People* (Evelyn Underhill, 1914) | `book` | 16 | 34,000 | none |
| `ArtOfIllustration` *The Art of Illustration* (C. H. Spurgeon, 1894) | `book` | 10 | 48,000 | 3 `cites` |
| `NewmanVerses` *Verses on Various Occasions* (John Henry Newman, 1903) | `book` | 190 | 36,000 | 1 `about` and 4 `cites` |
| `Heretics` *Heretics* (G. K. Chesterton, 1905) | `book` | 24 | 65,000 | none |
| `EverlastingMan` *The Everlasting Man* (G. K. Chesterton, 1925) | `book` | 22 | 108,000 | none |
| `WhatsWrongWithTheWorld` *What’s Wrong with the World* (G. K. Chesterton, 1910) | `book` | 53 | 61,000 | none |
| `ManWhoWasThursday` *The Man Who Was Thursday: A Nightmare* (G. K. Chesterton, 1908) | `book` | 19 | 59,000 | none |
| `Phantastes` *Phantastes: A Faerie Romance for Men and Women* (George MacDonald, 1858) | `book` | 31 | 70,000 | none |
| `Lilith` *Lilith: A Romance* (George MacDonald, 1895) | `book` | 52 | 96,000 | none |
| `BackOfTheNorthWind` *At the Back of the North Wind* (George MacDonald, 1871) | `book` | 41 | 90,000 | none |
| `PrincessAndTheGoblin` *The Princess and the Goblin* (George MacDonald, 1872) | `book` | 35 | 52,000 | none |
| `PrincessAndCurdie` *The Princess and Curdie* (George MacDonald, 1883) | `book` | 38 | 57,000 | none |
| `DivineComedy` *The Divine Comedy* (Dante Alighieri (translated by Henry Wadsworth Longfellow), 1867) | `book` | 12 | 315,000 | 176 `cites` |
| `ParadiseLost` *Paradise Lost* (John Milton, 1667) | `book` | 15 | 83,000 | none |
| `BenHur` *Ben-Hur: A Tale of the Christ* (Lew Wallace, 1880) | `book` | 87 | 201,000 | none |
| `DonnePoetry` *Poetry* (John Donne, first collected in 1633) | `book` | 202 | 76,000 | none |
| `MacDonaldPoetry` *Poetry* (George MacDonald, 1855–1893, with *The Diary of an Old Soul* as one entry) | `book` | 416 | 161,000 | 2 `cites` |
| `KingdomOfGod` *The Kingdom of God Is Within You* (Leo Tolstoy (translated by Leo Wiener), 1894) | `book` | 23 | 126,000 | 32 `cites` |
| `TolstoyConfession` *A Confession* (Leo Tolstoy (translated by Aylmer Maude), 1882) | `book` | 21 | 27,000 | none |
| `InnocenceOfFatherBrown` *The Innocence of Father Brown* (G. K. Chesterton, 1911) | `book` | 16 | 80,000 | none |
| `WisdomOfFatherBrown` *The Wisdom of Father Brown* (G. K. Chesterton, 1914) | `book` | 16 | 73,000 | none |
| `IncredulityOfFatherBrown` *The Incredulity of Father Brown* (G. K. Chesterton, 1926) | `book` | 13 | 72,000 | none |
| `SecretOfFatherBrown` *The Secret of Father Brown* (G. K. Chesterton, 1927) | `book` | 14 | 64,000 | none |
| `ConsolationOfPhilosophy` *The Consolation of Philosophy* (Boethius (translated by H. R. James), 1897) | `book` | 13 | 43,000 | none |
| `BrothersKaramazov` *The Brothers Karamazov* (Fyodor Dostoevsky (translated by Constance Garnett), 1880) | `book` | 101 | 351,000 | 1 `cites` |
| `QuoVadis` *Quo Vadis: A Narrative of the Time of Nero* (Henryk Sienkiewicz (translated by Jeremiah Curtin), 1895) | `book` | 80 | 210,000 | none |
| `UncleTomsCabin` *Uncle Tom’s Cabin* (Harriet Beecher Stowe, 1852) | `book` | 49 | 183,000 | 4 `cites` |
| `ChristmasCarol` *A Christmas Carol* (Charles Dickens, 1843) | `book` | 9 | 29,000 | none |
| `LesMiserables` *Les Misérables* (Victor Hugo (translated by Isabel F. Hapgood), 1862) | `book` | 371 | 566,000 | 6 `cites` |
| `CrimeAndPunishment` *Crime and Punishment* (Fyodor Dostoevsky (translated by Constance Garnett), 1866) | `book` | 46 | 205,000 | none |
| `Resurrection` *Resurrection* (Leo Tolstoy (translated by Louise Maude), 1899) | `book` | 135 | 175,000 | 11 `cites` |
| `MacDonaldShortFiction` *Short Fiction* (George MacDonald, 1858–1891: its numbered chapters are titled with their story's name, e.g., ‘A Double Story, III’) | `book` | 92 | 224,000 | 1 `cites` |
| `VanDykePoetry` *Poetry* (Henry van Dyke, 1897–1927) | `book` | 231 | 69,000 | 7 `cites` |

The other fifty-seven are every English or Spanish book in that library that's CC0 or in the public domain and has an EPUB. They're in `pipeline/books-freely-giving.toml`
(which `sources.toml` includes), written by

    cd pipeline && python3 -m biblelastic_ingest.freely_giving

which surveys the library (one request at a time), fetches each EPUB once, and takes each book's copyright from its own notices in its front matter
(e.g., Common Weal Press's CC0 dedication of its editions of the Puritans, or the BSB's public-domain notice): run it again for books added since.
They range from a 2,800-word essay (*On the Election of Infants*) to Edwards's *Religious Affections* (179,000 words),
mostly older works (Owen, Bunyan, Brooks, Watson, Flavel, Gouge, Perkins, Sibbes, Edwards, Spurgeon, the 1689 Baptist Confession) newly edited,
many of them also in a modernised edition (e.g., `AllOfGraceModern`), and some recent ones. Three are in Spanish (`language = "spa"`):
*Meditaciones sobre el Salmo 119*, *Pronunciando y traduciendo el Nombre Divino* (`NombreDivino`), and *Sobre la elección de los infantes*,
whose references are found with the Bible's books' Spanish names (e.g., ‘Juan 3:16’, ‘Sal 119:105’, ‘1 Co 13:4-7’).
*Meditations on Psalm 119* and its Spanish edition have `context_book = "PSA"`, from their titles. Books there that are only PDFs, web pages, or print (e.g., Calvin's *Institutes*,
Spurgeon's *Morning and Evening*, Augustine's *Expositions on the Psalms*, and the two Spanish editions of *Our Sin, His Mercy*) aren't included yet.

## Disclaimers

The registry's `[disclaimers]` table gives text (a little HTML: `<em>` and `<a>`) for each kind of work, which is put in the manifest as `disclaimer`
and must be shown wherever such a work's words are shown. So far it's the same for books and commentaries: that the material is included in good faith,
but the views are its authors' and not necessarily the design decisions of the Open English Translation.
A table for a language (e.g., `[disclaimers.spa]`) gives it in that language, for the works in it: so far a Spanish translation, which is still to be checked.

## Spanish

Two Spanish Bibles and the Spanish study notes and Bible dictionary come from the [Bible Aquifer](https://github.com/BibleAquifer), in `/srv/Bibles/BibleAquifer`:

| Edition | Kind | From | Licence |
| --- | --- | --- | --- |
| `ASBRT` *Texto Bíblico de Referencia en Español de Aquifer* (Aquifer Spanish Bible Reference Text, 2026) | `scripture` | USFM | CC BY-SA 4.0 |
| `RV1909` *Reina-Valera 1909* (with Strong's numbers on its words) | `scripture` | USFM | Public domain |
| `AOSN-ES` *Notas de estudio abiertas de Aquifer*: 13,303 study notes (on 43 books so far), 66 book introductions, and 124 profiles | `commentary` | JSON | CC BY-SA 4.0 |
| `AOBD-ES` *Diccionario bíblico abierto de Aquifer*: 5,886 articles | `dictionary` | JSON | CC BY-SA 4.0 |

The notes and dictionary are the Aquifer's translations of the Tyndale Open Study Notes and Tyndale Open Bible Dictionary.

- **The Bibles** have no section headings, so the registry's `sections_from = "OET-RV"` gives each the OET-RV's sections, starting at the same verses
    (at the next verse, where a section would start inside a combined verse, e.g., ‘6-7’). Those sections have no titles: the reader shows the passage.
    Their files are named like `43JHNASBRT.SFM` (the book's code after its number). A `\w` of the RV1909 can hold several words that translate one Hebrew or Greek word
    (e.g., ‘el principio’ for ἀρχῇ): each becomes a token of its own, with the same Strong's number.
- **The notes and articles** (`format = "Aquifer"`, read by `pipeline/biblelastic_ingest/aquifer.py`) become the same documents as the Tyndale works:
    a study note goes into the document of the book that it's about (named by its verses, e.g., `3:16` or `1:1-2:3`), and introductions, profiles, and articles
    into `Intros`, `Profiles`, and `Articles`. A note or introduction is `about` its passage; the Bible references in the text (`<data class="bible-ref">`) are `cites`
    anchors, and the links to other items (`<data class="resource-ref">`) are `see` links (those to the other work, e.g., from a note to the dictionary, aren't kept yet).
    A profile's or article's list of passages (every place where its subject is named, up to hundreds) isn't taken as what it's about.

Searching folds accents, as the ingest does (so ‘corazón’ finds ‘corazon’ in `norm`).

**Their words are linked to the Hebrew and Greek**, from the Aquifer's own alignments (each Bible's `alignments/` folder, named by the registry's `aquifer_alignments`),
so that a Spanish word can be tapped like an OET one: see *Alignments* below.

## The UBS dictionaries and handbooks

The [UBS open-licensed resources](https://github.com/ubsicap/ubs-open-license) are read from the [copies adapted for the OET](https://github.com/Freely-Given-org/OET_ubs-open-license)
(CC BY-SA 4.0), by `pipeline/biblelastic_ingest/ubs.py`, after the editions that they're joined to. The registry's `[[ubs]]` entry says which.

The *UBS Dictionary of Biblical Hebrew* and the *UBS Dictionary of the Greek New Testament* list each meaning of each word, with every place where the word has that meaning.
Those places are joined to the words of the UHB and the SR-GNT, giving each a layer called `UBS` (`layers/UBS/<BBB>.features.tsv`, one row per word, as for other layers):

| Column | Meaning |
| --- | --- |
| `meaning_gloss` | Short English glosses for the word's meaning in this place, e.g., `beginning, to begin` |
| `meaning_definition` | The meaning's definition |
| `meaning_note` | Any comment on it |
| `meaning_code` | A Louw-Nida number for Greek, e.g., `67.65` |
| `domains` | The semantic domains that the meaning is in, separated by semicolons, e.g., `Time;Time > A Point of Time with Reference to Duration of Time: Beginning, End` |
| `handbook` | The handbook articles about the thing that the word refers to, as locators separated by semicolons, e.g., `Fauna 2.8` |

UBS places are given as 14 digits (book, chapter, verse, and position), but they can't be used as they are:
the positions count each part of a Hebrew word (e.g., a prefix) separately, and the Old Testament verse numbers are the Hebrew ones, while the UHB's are mostly the English ones.
So each book's words are aligned in order with the places, by Strong's number (Hebrew) or lemma (Greek). That joins 260,028 of 289,216 Hebrew places and 120,298 of 128,164 Greek ones,
which gives a meaning to 87% of the original-language words (about what the dictionaries cover: the Hebrew one is still about 90% complete).
Of the joined places, 99.9% of the Greek ones are in the same verse; for Hebrew it's 93%, and the rest are in the known blocks where the Hebrew and English verse numbers differ.

Definitions and comments are made plain: links to other words become just the words, references are shown as, e.g., `1Kgs 4:19`, and Louw-Nida numbers as `§93.32`.

The handbooks' articles list the Hebrew and Greek words that they're about, with their places. Those are joined to words in the same way (18,542 of about 22,000),
giving the `handbook` column. Their text has its own references (shown readably, and anchored as `cites`), links to other articles (`see`), and pictures (only the captions are kept).

## Thesauruses

A thesaurus connects the words that people search with to the entries of the dictionaries and commentaries, which are found by their titles.
`thesaurus/<LANGUAGE>.tsv` has the columns `term`, `see`, `contrast`, `note`:

| Column | Meaning |
| --- | --- |
| `term` | What someone might type, e.g., `once saved, always saved`. Capitals and punctuation don't matter |
| `see` | The titles of entries on the subject, separated by semicolons, e.g., `Perseverance; Assurance; Eternal Life` |
| `contrast` | The titles of entries for the other side of the question, e.g., `Apostasy; Backsliding`, so that both can be shown |
| `note` | A remark for whoever maintains it (not used) |

A title that no installed work has is simply not found, so one thesaurus can name titles from several works.

The source is `pipeline/thesaurus/eng.tsv`, which is written for Biblelastic (CC0). It's only a first sketch of 32 terms, to prove the idea:
**it needs writing properly, and reviewing by people who know the subjects**, because choosing what counts as ‘the other side’ is a theological judgement.
The ingest checks it (every row has a term and at least one title, and no term is repeated) and copies it.

## Alignments

`<BBB>.links.tsv` has the columns `from` and `to`, each a word index in the same `<BBB>` document of the two editions.
One-to-many, many-to-one, and many-to-many relationships are simply several rows that share a `from` or a `to`.

The OET's alignments are derived by joining OET `row` numbers to SR-GNT and UHB `oet_row` numbers.
(Those `oet_row` numbers are themselves found by matching each original-language word against the OET word tables, in order.)

The Spanish Bibles' (`ASBRT--SR-GNT`, `ASBRT--UHB`, `RV1909--SR-GNT`, and `RV1909--UHB`) come from the Bible Aquifer, by `pipeline/biblelastic_ingest/aquifer_alignment.py`.
The Aquifer joins its own numbering of each Bible's words to the words of the SBL Greek New Testament and the Westminster Leningrad Codex, chapter by chapter,
so both sides are first paired with our words: book by book, in order (so that differences of verse numbering don't matter), the Spanish by its letters,
the Greek without accents, and the Hebrew by its consonants (the Codex's pieces of a word, e.g., בְּ and רֵאשִׁית, put together as the UHB has them).
Where the texts differ by a long passage (e.g., John 7:53–8:11), the matching finds its place again by the next three words in a row that are the same.
Where a link joins the Greek article to other Greek words (e.g., ἡ ἀληθινή → *verdadera*), the article is left out of it.

| | Spanish words paired | Greek words paired | Hebrew words paired | Links | The Aquifer's links that couldn't be used |
| --- | --- | --- | --- | --- | --- |
| `ASBRT` | 668,014 of 668,820 | 136,377 of 137,741 | 303,615 of 305,649 | 660,220 | 3,190 of 432,979 |
| `RV1909` | 703,517 of 703,631 | (the same) | (the same) | 676,974 | 3,646 of 531,086 |

The Aquifer's alignments were made with the help of language models (their files name the models): what was checked by hand looked right, but they won't all be.
The glosses and meanings that a tapped word shows are still the English ones (the OET's and the UBS dictionaries').

## Checks

A run fails (non-zero exit code) if, for any document:

- the text rebuilt from the tokens differs from the source text (ignoring white-space)—for a commentary or dictionary, this is checked for each entry—or
- the number of ESFM word numbers handled differs from the number in the source.

Other oddities are counted as warnings in `<BBB>.meta.json` and `report.json`, e.g., word numbers that aren't attached to a word,
empty character markers, and unknown paragraph markers.

## Known gaps

- Footnote and cross-reference content isn't tokenised.
- The OET's Hebrew morpheme and lemma tables aren't carried through yet (only the word tables).
- Tags are still a single column, and aren't yet split into people, places, years, etc.
- Syntax (`nesting`) isn't yet turned into clause and phrase nodes.
- OET deuterocanonical books keep their `row` numbers, but there's no original-language edition for them to link to yet.
- No English lemmas or stems.
- Commentaries and dictionaries can only be read from Tyndale's XML format, the UBS handbooks from theirs, and books from EPUB, so far.
- References in a book are only found in its text as written: a chapter that says ‘verse 5’, or a printed table of contents that lists passages, isn't understood as such
    (the table of contents in *The Mark of a True Disciple*'s preface is taken as citing each passage). Tables, pictures, and links within a book aren't kept.
- The UBS dictionaries are only used for the meaning of each word (and their domains): there's no browsable dictionary of their own entries yet,
    and Hebrew prefixes and suffixes (which UBS counts as words of their own) don't get meanings.
- The UBS handbooks' pictures, the MARBLE index's picture and map links, the Bible routes, HOTTP, and the parallel passages aren't used yet.
- A few source references can't be understood and are left out (16 of about 120,000 in the two Tyndale works: they're listed in `report.json`).
    Most are mistakes in the source, e.g., `Gen.1.3-2` where the text says 1:3–2:3. Parts of verses (e.g., 16b) are treated as the whole verse.
- References are only found where the source marks them as links: plain text like ‘v 13’ isn't recognised.
- Links to a heading within an article, tables (their cells are just paragraphs), and images aren't kept.
- Commentaries and dictionaries don't have section nodes for their headings yet.
