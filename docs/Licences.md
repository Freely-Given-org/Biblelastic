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

## Public-domain reference works and books (added 27 November 2026)

None is in the English starter set. Each was checked at its source on 27 November 2026.

| Work | Registry | Where its source says so | What it says |
| --- | --- | --- | --- |
| `Easton` Easton's Bible Dictionary (M. G. Easton, third edition, 1897) | Public domain | The SWORD module's `mods.d/easton.conf` (in `build/downloads/crosswire/Easton.zip`, from https://crosswire.org/ftpmirror/pub/sword/packages/rawzip/Easton.zip) | `DistributionLicense=Public Domain`; ‘Public Domain -- Copy Freely’; `TextSource=CCEL` |
| `Nave` Nave's Topical Bible (Orville J. Nave, c. 1896) | Public domain | `mods.d/nave.conf` in `Nave.zip` (as above) | `DistributionLicense=Public Domain`; the text is from https://ccel.org/ccel/n/nave/bible.xml |
| `TSK` Treasury of Scripture Knowledge (c. 1880) | Public domain | `mods.d/tsk.conf` in `TSK.zip` (as above) | `DistributionLicense=Public Domain` |
| `UnspokenSermons` *Unspoken Sermons* (George MacDonald, 1867, 1885, and 1889) | Public domain (Standard Ebooks' edition: CC0 1.0) | The EPUB's `uncopyright.xhtml` (https://standardebooks.org/ebooks/george-macdonald/unspoken-sermons) | Believed to be in the US public domain; Standard Ebooks' own work on it is CC0 1.0. MacDonald died in 1905 |
| `Orthodoxy` *Orthodoxy* (G. K. Chesterton, 1908) | Public domain (Standard Ebooks' edition: CC0 1.0) | The EPUB's `uncopyright.xhtml` (https://standardebooks.org/ebooks/g-k-chesterton/orthodoxy) | As above. Chesterton died in 1936 |

All five were first published before 1931 by authors who died before 1956, so they're in the public domain in the United States and in countries where copyright lasts 70 years after the author's death.
CrossWire's modules are from the Christian Classics Ethereal Library's texts. CCEL claims copyright on its own formatting, but the modules are CrossWire's conversions, and CrossWire only hosts a module
whose text is in the public domain or whose holder has given it permission.

## More books from Standard Ebooks (added 27 November 2026)

Each EPUB's `uncopyright.xhtml` says that the text is believed to be in the United States public domain, and that Standard Ebooks' own work on it is CC0 1.0.
Each was first published (or translated) before 1931, by an author (and translator) who died before 1956. None is in the English starter set. Each was checked at its source on 27 November 2026.

| Work | First published | Author (and translator) | Source |
| --- | --- | --- | --- |
| `ImitationOfChrist` *The Imitation of Christ* | 1877 | Thomas à Kempis (died 1471), William Benham (died 1910) | https://standardebooks.org/ebooks/thomas-a-kempis/the-imitation-of-christ/william-benham |
| `WayToGod` *The Way to God and How to Find It* | 1884 | D. L. Moody (died 1899) | https://standardebooks.org/ebooks/d-l-moody/the-way-to-god-and-how-to-find-it |
| `PracticalMysticism` *Practical Mysticism: A Little Book for Normal People* | 1914 | Evelyn Underhill (died 1941) | https://standardebooks.org/ebooks/evelyn-underhill/practical-mysticism |
| `ArtOfIllustration` *The Art of Illustration* | 1894 | C. H. Spurgeon (died 1892) | https://standardebooks.org/ebooks/c-h-spurgeon/the-art-of-illustration |
| `NewmanVerses` *Verses on Various Occasions* | 1903 | John Henry Newman (died 1890) | https://standardebooks.org/ebooks/john-henry-newman/verses-on-various-occasions |
| `Heretics` *Heretics* | 1905 | G. K. Chesterton (died 1936) | https://standardebooks.org/ebooks/g-k-chesterton/heretics |
| `EverlastingMan` *The Everlasting Man* | 1925 | G. K. Chesterton (died 1936) | https://standardebooks.org/ebooks/g-k-chesterton/the-everlasting-man |
| `WhatsWrongWithTheWorld` *What’s Wrong with the World* | 1910 | G. K. Chesterton (died 1936) | https://standardebooks.org/ebooks/g-k-chesterton/whats-wrong-with-the-world |
| `ManWhoWasThursday` *The Man Who Was Thursday: A Nightmare* | 1908 | G. K. Chesterton (died 1936) | https://standardebooks.org/ebooks/g-k-chesterton/the-man-who-was-thursday |
| `Phantastes` *Phantastes: A Faerie Romance for Men and Women* | 1858 | George MacDonald (died 1905) | https://standardebooks.org/ebooks/george-macdonald/phantastes |
| `Lilith` *Lilith: A Romance* | 1895 | George MacDonald (died 1905) | https://standardebooks.org/ebooks/george-macdonald/lilith |
| `BackOfTheNorthWind` *At the Back of the North Wind* | 1871 | George MacDonald (died 1905) | https://standardebooks.org/ebooks/george-macdonald/at-the-back-of-the-north-wind |
| `PrincessAndTheGoblin` *The Princess and the Goblin* | 1872 | George MacDonald (died 1905) | https://standardebooks.org/ebooks/george-macdonald/the-princess-and-the-goblin |
| `PrincessAndCurdie` *The Princess and Curdie* | 1883 | George MacDonald (died 1905) | https://standardebooks.org/ebooks/george-macdonald/the-princess-and-curdie |
| `DivineComedy` *The Divine Comedy* | 1867 | Dante Alighieri (died 1321), Henry Wadsworth Longfellow (died 1882) | https://standardebooks.org/ebooks/dante-alighieri/the-divine-comedy/henry-wadsworth-longfellow |
| `ParadiseLost` *Paradise Lost* | 1667 | John Milton (died 1674) | https://standardebooks.org/ebooks/john-milton/paradise-lost |
| `BenHur` *Ben-Hur: A Tale of the Christ* | 1880 | Lew Wallace (died 1905) | https://standardebooks.org/ebooks/lew-wallace/ben-hur |

Left out: A. W. Tozer's *The Pursuit of God* (1948: Tozer died in 1963, so it's in copyright in the United Kingdom until 2034), and Archibald Alexander's *A Day at a Time* (1916),
because when its author died isn't known. Augustine's *Confessions*, *Introduction to the Devout Life*, and Hopkins's poems are only on Standard Ebooks' list of wanted books so far.

## More reference works from CrossWire, and a third batch of books (added 27 November 2026)

None is in the English starter set. Each was checked at its source on 27 November 2026. Each was first published (or translated) before 1931,
by an author (and translator) who died before 1956, except where it says otherwise below. The CrossWire modules are in `build/downloads/crosswire/`
(from https://crosswire.org/ftpmirror/pub/sword/packages/rawzip/), and the books in `build/downloads/standardebooks/`.

| Work | Registry | Where its source says so | What it says |
| --- | --- | --- | --- |
| `MHCC` Matthew Henry's Concise Commentary (Matthew Henry, died 1714) | Public domain | `mods.d/mhcc.conf` in `MHCC.zip` | `DistributionLicense=Public Domain`; ‘Public Domain--Copy Freely’; the text matches Moody Press's printing, which shows no copyright; `TextSource=https://ccel.org/ccel/h/henry/mhcc/cache/mhcc.txt` |
| `JFB` Commentary Critical and Explanatory on the Whole Bible (Robert Jamieson, died 1880; A. R. Fausset, died 1910; David Brown, died 1897; 1871) | Public domain | `mods.d/jfb.conf` in `JFB.zip` | `DistributionLicense=Public Domain`; `TextSource=https://ccel.org/ccel/j/jamieson/jfb/cache/jfb.txt` |
| `Torrey` The New Topical Text Book (R. A. Torrey, died 1928; 1897) | Public domain | `mods.d/torrey.conf` in `Torrey.zip` | `DistributionLicense=Public Domain`; from a reprint that has no copyright notice, ‘of the original edition which is out of copyright’ |
| `Smith` Smith's Bible Dictionary (William Smith, died 1893; 1884 edition) | Public domain | `mods.d/smith.conf` in `Smith.zip` | `DistributionLicense=Public Domain`; ‘(1884) Public domain.’ |
| `Hitchcock` Hitchcock's Bible Names (Roswell D. Hitchcock, died 1887; from *Hitchcock's New and Complete Analysis of the Holy Bible*, 1869) | Public domain | `mods.d/hitchcock.conf` in `Hitchcock.zip` | `DistributionLicense=Public Domain`; ‘It is out of copyright’; `TextSource=CCEL` |
| `DonnePoetry` *Poetry* (John Donne, died 1631) | Public domain (Standard Ebooks' edition: CC0 1.0) | The EPUB's `uncopyright.xhtml` (https://standardebooks.org/ebooks/john-donne/poetry) | Believed to be in the US public domain; Standard Ebooks' own work on it is CC0 1.0 |
| `MacDonaldPoetry` *Poetry* (George MacDonald, died 1905) | As above | https://standardebooks.org/ebooks/george-macdonald/poetry | As above |
| `KingdomOfGod` *The Kingdom of God Is Within You* (Leo Tolstoy, died 1910; translated by Leo Wiener, died 1939, in 1905) | As above | https://standardebooks.org/ebooks/leo-tolstoy/the-kingdom-of-god-is-within-you/leo-wiener | As above |
| `TolstoyConfession` *A Confession* (Leo Tolstoy; translated by Aylmer Maude, died 1938, in 1921) | As above | https://standardebooks.org/ebooks/leo-tolstoy/a-confession/aylmer-maude | As above |
| `InnocenceOfFatherBrown`, `WisdomOfFatherBrown`, `IncredulityOfFatherBrown`, `SecretOfFatherBrown` (G. K. Chesterton, died 1936; 1911, 1914, 1926, and 1927) | As above | https://standardebooks.org/ebooks/g-k-chesterton/the-innocence-of-father-brown (and `the-wisdom-of-father-brown`, `the-incredulity-of-father-brown`, `the-secret-of-father-brown`) | As above |
| `ConsolationOfPhilosophy` *The Consolation of Philosophy* (Boethius; translated by H. R. James, died 1931, in 1897) | As above | https://standardebooks.org/ebooks/boethius/the-consolation-of-philosophy/h-r-james | As above (James's dates are from https://viaf.org/viaf/45545240) |
| `BrothersKaramazov` *The Brothers Karamazov* (Fyodor Dostoevsky, died 1881; translated by Constance Garnett, died 1946, in 1912) | As above | https://standardebooks.org/ebooks/fyodor-dostoevsky/the-brothers-karamazov/constance-garnett | As above |
| `QuoVadis` *Quo Vadis* (Henryk Sienkiewicz, died 1916; translated by Jeremiah Curtin, died 1906, in 1896) | As above | https://standardebooks.org/ebooks/henryk-sienkiewicz/quo-vadis/jeremiah-curtin | As above |
| `UncleTomsCabin` *Uncle Tom's Cabin* (Harriet Beecher Stowe, died 1896; 1852) | As above | https://standardebooks.org/ebooks/harriet-beecher-stowe/uncle-toms-cabin | As above |

Two things that were weighed when they were checked: Matthew Henry's *Concise Commentary* is an abridgement whose abridger isn't named (in CrossWire's module, CCEL's text, or Moody Press's printing),
so it rests on CrossWire's and CCEL's word that it's in the public domain; and Smith's dictionary is the 1884 American edition, whose editors the module doesn't name.

Left out again: Augustine's *Confessions* and *On Christian Doctrine*, *Introduction to the Devout Life*, Hopkins's and Milton's shorter poems, *Samson Agonistes*, and Pascal's *Pensées*
have pages on Standard Ebooks, but they're only on its list of wanted books. *The Scandal of Father Brown* (1935) isn't in the US public domain until 2031.

## Still more works from CrossWire, and a fourth batch of books (added 27 November 2026)

None is in the English starter set. Each was checked at its source on 27 November 2026. Each was first published (or translated) before 1931,
by an author (and translator) who died before 1956. The CrossWire modules' settings files (`mods.d/*.conf`) are in the zip files in `build/downloads/crosswire/`.

| Work | Registry | Where its source says so | What it says |
| --- | --- | --- | --- |
| `MorningAndEvening` *Morning and Evening: Daily Readings* (C. H. Spurgeon, died 1892; 1865–1868) | Public domain | `mods.d/sme.conf` in `SME.zip` | `DistributionLicense=Public Domain`; from CCEL, ‘through a generous contribution by Logos Bible Software’ |
| `DailyLight` *Daily Light on the Daily Path* (Jonathan Bagster, died 1872, and his family; c. 1875) | Public domain | `mods.d/daily.conf` in `Daily.zip` | `DistributionLicense=Public Domain`; ‘Public Domain -- Copy Freely’ |
| `Wesley` *Explanatory Notes* (John Wesley, died 1791; 1755 and 1765) | Public domain | `mods.d/wesley.conf` in `Wesley.zip` | `DistributionLicense=Public Domain`; from Sulu Kelley and Bill Brown's electronic edition and CCEL's |
| `Scofield` the Scofield Reference Bible's notes (C. I. Scofield, died 1921; 1917 edition) | Public domain | `mods.d/scofield.conf` in `Scofield.zip` | `DistributionLicense=Public Domain`; `TextSource=https://en.wikisource.org/wiki/Scofield_Reference_Bible_Notes` |
| `Barnes` *Notes on the New Testament* (Albert Barnes, died 1870; 1832–1851) | Public domain | `mods.d/barnes.conf` in `Barnes.zip` | `DistributionLicense=Public Domain` |
| `PNT` *The People's New Testament* (B. W. Johnson, died 1894; 1889–1891) | Public domain | `mods.d/pnt.conf` in `PNT.zip` | `DistributionLicense=Public Domain` |
| `Clarke` *Commentary and Critical Notes* (Adam Clarke, died 1832; 1810–1826) | Public domain | `mods.d/clarke.conf` in `Clarke.zip` | `DistributionLicense=Public Domain`; `TextSource=https://en.wikisource.org/wiki/Commentary_and_critical_notes_on_the_Bible` |
| `Josephus` *The Works of Josephus* (translated by William Whiston, died 1752; 1737) | Public domain | `mods.d/josephus.conf` in `Josephus.zip` | `DistributionLicense=Public Domain`; `TextSource=CCEL` |
| `ChristmasCarol` *A Christmas Carol* (Charles Dickens, died 1870; 1843) | Public domain (Standard Ebooks' edition: CC0 1.0) | The EPUB's `uncopyright.xhtml` (https://standardebooks.org/ebooks/charles-dickens/a-christmas-carol) | Believed to be in the US public domain; Standard Ebooks' own work on it is CC0 1.0 |
| `LesMiserables` *Les Misérables* (Victor Hugo, died 1885; translated by Isabel F. Hapgood, died 1928, in 1888) | As above | https://standardebooks.org/ebooks/victor-hugo/les-miserables/isabel-f-hapgood | As above |
| `CrimeAndPunishment` *Crime and Punishment* (Fyodor Dostoevsky; translated by Constance Garnett, died 1946, in 1914) | As above | https://standardebooks.org/ebooks/fyodor-dostoevsky/crime-and-punishment/constance-garnett | As above |
| `Resurrection` *Resurrection* (Leo Tolstoy; translated by Louise Maude, died 1939, in 1900) | As above | https://standardebooks.org/ebooks/leo-tolstoy/resurrection/louise-maude | As above |
| `MacDonaldShortFiction` *Short Fiction* (George MacDonald, died 1905) | As above | https://standardebooks.org/ebooks/george-macdonald/short-fiction | As above |

Things that were weighed when they were checked: the Scofield notes' 1917 edition had consulting editors as well as Scofield (the last of them to die, Arno C. Gaebelein, died in 1945);
*Daily Light*'s compilers, besides Jonathan Bagster, aren't named; and Spurgeon's module came to CCEL from Logos Bible Software, though the module says it's in the public domain.

Left out: Robertson's *Word Pictures* (CrossWire's module says ‘Copyrighted; Free non-commercial distribution’), the *International Standard Bible Encyclopedia*
(1915, but by many contributors, some of whom may have died after 1956, which would need checking one by one), and, for now, the largest commentaries (Calvin's, Matthew Henry's complete commentary, and Keil and Delitzsch's,
whose translators would need checking). Manzoni's *The Betrothed* is only on Standard Ebooks' list of wanted books.

## General books from CrossWire, and a fifth batch of books (added 28 November 2026)

None is in the English starter set. Each was checked at its source on 28 November 2026. Each was first published (or translated) before 1931,
by an author (and translator) who died before 1956, except where it says otherwise below. The CrossWire modules' settings files (`mods.d/*.conf`) are in the zip files in `build/downloads/crosswire/`.

| Work | Registry | Where its source says so | What it says |
| --- | --- | --- | --- |
| `Holiness` *Holiness* (J. C. Ryle, died 1900; 1877, enlarged 1879) | Public domain | `mods.d/jcrholiness.conf` in `JCRHoliness.zip` | `DistributionLicense=Public Domain`; `TextSource=CCEL` |
| `EdwardsSermons` *Select Sermons* (Jonathan Edwards, died 1758) | Public domain | `mods.d/jesermons.conf` in `JESermons.zip` | `DistributionLicense=Public Domain`; `TextSource=CCEL` |
| `Christologia` *Christologia* (John Owen, died 1683; 1679), with William H. Goold's prefatory note (died 1897; 1850–1853) | Public domain | `mods.d/jochrist.conf` in `JOChrist.zip` | `DistributionLicense=Public Domain`; `TextSource=CCEL`; ‘Archaic words in the text have been automatically modernized’ |
| `CommunionWithGod` *Of Communion with God* (John Owen; 1657), with Goold's notes | Public domain | `mods.d/jocommgod.conf` in `JOCommGod.zip` | As above |
| `GloryOfChrist` *Meditations and Discourses on the Glory of Christ* (John Owen; 1684), with Goold's note | Public domain | `mods.d/joglory.conf` in `JOGlory.zip` | As above |
| `GospelThemes` *Sermons on Gospel Themes* (Charles G. Finney, died 1875; 1876) | Public domain | `mods.d/finney.conf` in `Finney.zip` | `DistributionLicense=Public Domain`; `TextSource=CCEL` |
| `LawAndGospel` *The Proper Distinction Between Law and Gospel* (C. F. W. Walther, died 1887; translated by W. H. T. Dau, died 1944, in 1929) | Public domain | `mods.d/lawgospel.conf` in `LawGospel.zip` | `DistributionLicense=Public Domain`; ‘As the 1929 edition was not copyrighted, it is in the public domain’ |
| `Westminster` The Westminster Confession of Faith (1646) and Shorter and Larger Catechisms (1647), with their proofs (the KJV) | Public domain | `mods.d/westminster.conf` in `Westminster.zip` | `DistributionLicense=Public Domain`; from reformed.org (the Center for Reformed Theology and Apologetics) in 2011 |
| `PracticeOfThePresence` *The Practice of the Presence of God* (Brother Lawrence, died 1691; c. 1692; the translator isn't named) | Public domain | `mods.d/practice.conf` in `Practice.zip` | `DistributionLicense=Public Domain`; John Harris's electronic edition (1994), which he calls ‘this Public Domain edition’ |
| `Enoch` *The Book of Enoch* (translated by R. H. Charles, died 1931; 1913) | Public domain | `mods.d/enoch.conf` in `Enoch.zip` | `DistributionLicense=Public Domain`; from *The Apocrypha and Pseudepigrapha of the Old Testament* (1913), https://archive.org/details/apocryphapseudep02charuoft |
| `Jubilees` *The Book of Jubilees* (translated, with an introduction, by R. H. Charles; 1913) | Public domain | `mods.d/jubilees.conf` in `Jubilees.zip` | `DistributionLicense=Public Domain`; from the same (1913) |
| `VanDykePoetry` *Poetry* (Henry van Dyke, died 1933; 1897–1927) | Public domain (Standard Ebooks' edition: CC0 1.0) | The EPUB's `uncopyright.xhtml` (https://standardebooks.org/ebooks/henry-van-dyke-jr/poetry) | Believed to be in the US public domain; Standard Ebooks' own work on it is CC0 1.0 |

Things that were weighed when they were checked: *The Practice of the Presence of God*'s translator isn't named; the text is from an Epworth Press printing (‘Authentic Edition’) that its transcriber dates
to between 1932 and 1948, though its title (‘The Best Rule of a Holy Life’) is the older translation's, so its unsigned preface is left out; Owen's works are CCEL's automatically modernized texts
(the modernizing isn't creative work, but it isn't Owen's wording either); Walther's and *Holiness*'s modules each had something modern in them, which is left out
(Walther's has twenty sermons whose translations are later: eight are Donald E. Heck's, of 1960, and twelve E. Myers's, for Hope Press, undated, and *Holiness* a foreword that seems to be D. Martyn Lloyd-Jones's, who died in 1981); and Enoch's text was edited by Marjan Šavli
and Barbara Hojkar Šavli in 2023, which, from what it says, was correcting the scan rather than adding to it.

Left out: Calvin's *Institutes* (CCEL's text, which CrossWire's module is, has John Murray's introduction of 1949, and Robert J. Dunzweiler's modern footnotes mixed into the text without markup),
*The Dark Night of the Soul* (CrossWire's text is E. Allison Peers's third revised edition, of 1959), and Spurgeon's *Treasury of David* (which needs more work: CrossWire's module keeps each
psalm's whole commentary at its first verse). *The Mortification of Sin*, *Religious Affections*, *The Pilgrim's Progress*, and the Baptist Confession of 1689 were left out because they're already here,
from books.freely.giving.

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
