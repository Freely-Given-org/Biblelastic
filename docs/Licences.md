# Licences: what each source says

Before the modules are published, a person should check each work's licence at its source and set `licence_verified = true` for it
in `pipeline/sources.toml` (or, for the books from books.freely.giving, in `pipeline/books-freely-giving.toml`, where the survey tool keeps it when it runs again;
and for the models, under `[[model]]` in `sources.toml`). This page gathers what the sources say, as found on 26 November 2026, so that checking is quick.
Every work's was marked as checked on 26 November 2026, except the thesaurus's and the models'.

## The Bibles, notes, dictionaries, and handbooks

| Work | Registry | Where its source says so | What it says | |
| --- | --- | --- | --- | --- |
| OET-RV | CC BY-SA 4.0 | `OpenEnglishTranslation--OET/translatedTexts/ReadersVersion/README.md` and `LICENSE` | ‘Copyright (c) 2010-2026 Robert Hunt’; CC BY-SA 4.0 | Corrected: the registry had ‘Freely-Given.org’ |
| OET-LV | CC BY-SA 4.0 | `…/derivedTexts/auto_edited_*_ESFM/README.md` and `LICENSE` | ‘Copyright © 2010-2026 Robert Hunt (Freely-Given.org)’; CC BY-SA 4.0 | Corrected (as above) |
| The OET word tables (the `OET` layers of the SR-GNT and UHB) | CC BY-SA 4.0 | In the OET-RV's folder (its licence); the VLT README credits the CNTR data, CC BY 4.0 | | Corrected the holder (as above) |
| SR-GNT | CC BY 4.0 | `Forked/CNTR-SR/README.md` and `LICENSE.md` | ‘Copyright © 2022-2023 by Alan Bunning … CC BY 4.0’ | Corrected: the registry had 2022–2024 |
| UHB | CC BY-SA 4.0 | https://git.door43.org/unfoldingWord/hbo_uhb (LICENSE.md; there's no licence in the local copy) | ‘Copyright © 2022 by unfoldingWord’; CC BY-SA 4.0; see the question below | Corrected the year, and added the attribution that its licence asks of a derivative |
| TOSN | CC BY-SA 4.0 | `OET_TyndaleOpenResources/Tyndale Open Study Notes/_README.txt`, `LICENSE` | ‘Copyright (C) 2022 by Tyndale House Publishers’; CC BY-SA 4.0; the attribution wording | Matches |
| TOBD | CC BY-SA 4.0 | `OET_TyndaleOpenResources/TyndaleOpenBibleDictionary/_README.txt`, `LICENSE` | ‘Copyright (C) 2023 by Tyndale House Publishers’; CC BY-SA 4.0; the attribution wording | Matches |
| UBS dictionaries (the `UBS` meanings) | CC BY-SA 4.0 | `Forked/ubs-open-license/OET_ubs-open-license/UBS_README.md`, `UBS_LICENSE.md`, `LICENSE` | The copyright lines as the registry has them; CC BY-SA 4.0 | Matches |
| UBSH (the handbooks) | CC BY-SA 4.0 | `…/OET_ubs-open-license/flora-fauna-realia/README.md` | Three copyright lines, each with the book it's adapted from | Corrected: the registry gave the original of only the first, and called the third ‘Objects in the Bible’ (it's ‘Human-made Things in the Bible’) |
| ASBRT | CC BY-SA 4.0 | `/srv/Bibles/BibleAquifer/AquiferSpanishBibleReferenceText/README.md` | ‘© 2026 Mission Mutual’; CC BY-SA 4.0; revised from Biblica's Open Nueva Biblia Viva (CC BY-SA 4.0) | Matches; added what was changed |
| RV1909 | Public domain | `…/ReinaValera1909/README.md` | ‘© 1909 Public Domain’; CC0 | Matches |
| AOSN-ES | CC BY-SA 4.0 | `…/AquiferOpenStudyNotes/README.md` (and its BookIntros and Profiles) | ‘© 2026 Mission Mutual’; an adaptation of Tyndale Open Study Notes ‘© 2023 Tyndale House Publishers’; CC BY-SA 4.0 | Corrected: the registry gave the Tyndale notes as 2022; added what was changed |
| AOBD-ES | CC BY-SA 4.0 | `…/AquiferOpenBibleDictionary/README.md` | ‘© 2026 Mission Mutual’; an adaptation of Tyndale Open Bible Dictionary ‘© 2023 Tyndale House Publishers’; CC BY-SA 4.0 | Corrected (the year); added what was changed |
| The Spanish Bibles' alignments | As each Bible | In each Bible's Aquifer repository (whose README gives its licence) | | |
| Thesaurus (English) | CC0 1.0 | Written for Biblelastic (`pipeline/thesaurus/eng.tsv`) | ‘Freely-Given.org’ | Confirmed by you (26 November 2026) |

## More English Bibles (added 26 November 2026)

All are in the public domain, as their sources say, and aren't in the English starter set. Each was checked at its source on 26 November 2026.

| Work | Registry | Where its source says so | What it says |
| --- | --- | --- | --- |
| BSB | Public domain | https://berean.bible/terms.htm (the local copy is `OpenBibleData/copiedBibles/English/Berean.Bible/BSB/bsb_tables.tsv`) | ‘This text of God’s Word has been dedicated to the public domain’ (as quoted in the Jude commentary’s notices; to be checked on the site) |
| KJB-1769 | Public domain | `OpenBibleData/copiedBibles/English/eBible.org/KJB/copr.htm` | Public domain, except that letters patent restrict printing it in the United Kingdom (see the question below) |
| KJB-1611 | Public domain | `OpenBibleData/Bibles/EnglishTranslations/KJB-1611/README.md` | The 1611 text is out of copyright (except, it says, in England); Open Bible Data’s USFM is in the public domain |
| ASV, RV, YLT, Drby, Wbstr, DRA, JPS, Gnva, TNT | Public domain | Each one’s `copr.htm` in `OpenBibleData/copiedBibles/English/eBible.org/` | ‘Public Domain’ |
| WEBBE | Public domain | `…/eBible.org/WEBBE/copr.htm` | Public domain; ‘World English Bible’ is a trademark, which mayn't be used for a changed text (it isn't changed) |
| Wymth | Public domain | `OpenBibleData/Bibles/EnglishTranslations/Weymouth_NT-1903/README.md` | Out of copyright (1903) |
| Wycl | Public domain | `OpenBibleData/copiedBibles/English/eBible.org/Wycliffe/copr.htm` (for the Pentateuch and Gospels); the whole Bible is from the Zefania XML, whose `<rights>` is empty | Public domain (c. 1395) |

Left out: the Bible in Basic English, which eBible.org says is in the public domain only in the United States (it was printed in 1965 without a copyright notice);
and those whose licences need reading first (the LSV, FBV, T4T, and TCNT, all on eBible.org) or that mayn't be passed on (the NET Bible).

Question: the King James Bible (1611 and 1769) is under letters patent in the United Kingdom, which restrict printing it there.
Electronic copies are widely given away (eBible.org, Crosswire), and the registry says so in its copyright notice. Is that enough?

## The books (62)

Every book's page on books.freely.giving gives CC0 (that's how the survey chose them; the five in `sources.toml` were checked by hand when they were added),
and every book's own notice, which is its `copyright` in the registry, dedicates it to the public domain (CC0, ‘public domain’, or ‘waived all copyright’).
Where a book quotes Bibles, its notice says which: most quote the BSB or the Reina-Valera 1909, which are public domain.

Three quote copyrighted translations by their publishers' permission: *The Mark of a True Disciple* and *Jude: A Theological Commentary* (CSB, ESV, NET, LEB, LSB, NLT, NASB)
and *The Dorean Principle* (ESV, NASB). Their notices are kept with them (‘Used by permission. All rights reserved.’), so those quotations are covered by
the publishers' own terms for quoting, not by CC0. See the question below.

## The models

| Model | Licence | Where | Copyright line used |
| --- | --- | --- | --- |
| bge-small-en-v1.5 | MIT | Its model card (`license: mit`); the code's LICENSE (https://github.com/FlagOpen/FlagEmbedding) | ‘Copyright (c) 2022 staoxiao’ |
| multilingual-e5-small | MIT | Its model card (`license: mit`); the code's LICENSE (https://github.com/microsoft/unilm) | ‘Copyright (c) Microsoft Corporation’ |

MIT requires its notice to go with every copy, so each model module now has the licence's full text (`module.licence_text`).
The model cards don't give a copyright line of their own, so the one from the code's repository is used.

## Questions, and what was decided

1. **The unfoldingWord® trademark.** *Decided (26 November 2026): the title stays ‘unfoldingWord® Hebrew Bible’.* The UHB's licence says that a modified copy
    mustn't use the unfoldingWord® name, but the words of the UHB are unchanged in its modules: they're only in another format, and the word tables, transliterations,
    and meanings that go with them are in modules of their own. Its attribution still says what was changed.
1. **Quoted copyrighted Bibles.** *Decided (26 November 2026): included.* The two Pritchard books and *The Dorean Principle* are passed on as their authors published them,
    with their notices, so their quotations stay under the publishers' terms for quoting.
1. **The thesaurus.** *Decided (26 November 2026): CC0, by Freely-Given.org.* It was written for Biblelastic (by Claude, in the session that added topic search),
    and copies nothing from elsewhere: it names entries' titles, but has none of their text.
1. **The OET's request** (its README): that the OET-RV or OET-LV used alone shouldn't be called the *Open English Translation*.
    *Decided (26 November 2026): fine as it is.* The app offers both together, and shows the Readers' Version alone at first, by its own name.
