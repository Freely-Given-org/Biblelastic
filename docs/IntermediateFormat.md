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

`<BBB>` is the three-character BibleOrgSys book code (GEN, SA1, MRK, etc.).
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

A third, `UBSH`, is the United Bible Societies' handbooks *Animals in the Bible*, *Plants and Trees in the Bible*, and *Objects in the Bible* (a `dictionary`,
with the documents `Fauna`, `Flora`, and `Realia`: 762 articles). It comes from a different XML format, but becomes the same files: see the next section.

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

The alignments so far are derived by joining OET `row` numbers to SR-GNT and UHB `oet_row` numbers.
(Those `oet_row` numbers are themselves found by matching each original-language word against the OET word tables, in order.)

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
- Commentaries and dictionaries can only be read from Tyndale's XML format, and the UBS handbooks from theirs, so far.
- The UBS dictionaries are only used for the meaning of each word (and their domains): there's no browsable dictionary of their own entries yet,
    and Hebrew prefixes and suffixes (which UBS counts as words of their own) don't get meanings.
- The UBS handbooks' pictures, the MARBLE index's picture and map links, the Bible routes, HOTTP, and the parallel passages aren't used yet.
- A few source references can't be understood and are left out (16 of about 120,000 in the two Tyndale works: they're listed in `report.json`).
    Most are mistakes in the source, e.g., `Gen.1.3-2` where the text says 1:3–2:3. Parts of verses (e.g., 16b) are treated as the whole verse.
- References are only found where the source marks them as links: plain text like ‘v 13’ isn't recognised.
- Links to a heading within an article, tables (their cells are just paragraphs), and images aren't kept.
- Commentaries and dictionaries don't have section nodes for their headings yet.
