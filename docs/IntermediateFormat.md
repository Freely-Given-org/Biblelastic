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
Each source file is processed in its own process, so a full run of the first four editions takes a few seconds.

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
            layers/
                <LAYER>/
                    <BBB>.features.tsv      Extra feature columns from another source: one row per word
                    <BBB>.variants.tsv      Words that aren't in this edition's text (variant readings)
        alignments/
            <FROM>--<TO>/
                <BBB>.links.tsv             Word-to-word links between two editions

`<BBB>` is the three-character BibleOrgSys book code (GEN, SA1, MRK, etc.).
One *document* is one ‘book’. Nothing assumes any particular set of documents.

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

## Alignments

`<BBB>.links.tsv` has the columns `from` and `to`, each a word index in the same `<BBB>` document of the two editions.
One-to-many, many-to-one, and many-to-many relationships are simply several rows that share a `from` or a `to`.

The alignments so far are derived by joining OET `row` numbers to SR-GNT and UHB `oet_row` numbers.
(Those `oet_row` numbers are themselves found by matching each original-language word against the OET word tables, in order.)

## Checks

A run fails (non-zero exit code) if, for any document:

- the text rebuilt from the tokens differs from the source text (ignoring white-space), or
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
- Non-Bible works (with their own location schemes and Scripture references) aren't covered yet.
