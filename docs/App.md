# The app

`app/` is a minimal [Flutter](https://flutter.dev) app. It exists to prove that one Rust engine can sit behind one Flutter interface on every platform,
not to be the finished design. It runs on Android and in browsers, and is set up for Linux desktops (which hasn't been tried).

It can:

- install, update, and remove modules, from a list (`index.json`) at a web address (Freely-Given.org for a release build: see [Publishing.md](Publishing.md)),
    showing each one's licence, and when one has changed. They're chosen as people think of them (`app/lib/catalogue.dart`):
    - **a starter set for a language** (*Start with*: English, 65 MB; Español, 58 MB; both, 102 MB): its Bibles, commentaries, and dictionaries,
        the Greek and Hebrew (for what each word translates), and its thesaurus, but not the books
    - **search by meaning in a language** (the model, about 31–35 MB, with the vectors of the works in that language that are installed;
        offered once something in that language is installed, and on the Search page when a subject is searched for without it)
    - **each work** (its text, layers, and alignments, and its vectors if search by meaning is installed in its language), on the Modules page
        and, for the books, commentaries, and dictionaries that aren't installed, under *To download* in the Library
    - every module one by one (*Each module*, at the end of the Modules page), with *Install all* (256 MB) and *Remove all*
- read the OET-RV a section at a time (from one section heading to the next, whichever chapters that covers), with its poetry indents, words of Jesus, and translators' additions shown differently
- read another installed Bible instead (Bible, in the ⋮ menu), at the same place: so far the two Spanish ones, in the OET-RV's sections. The choice is remembered;
    until one is chosen, a phone set to Spanish starts with a Spanish Bible. While reading one, the notes in its language come first
- step to the next or previous section, right through from one book into the next, or choose a book and chapter
- show what the installed commentaries and dictionaries say about a verse (tap its number). A verse with a note of its own has its number underlined;
    the others still show the notes on the passage around them. If there's nothing at all (e.g., in Judith, which the Tyndale notes don't cover),
    ‘No notes for v4’ appears for a couple of seconds instead, so that it's clear the tap worked
- show the OET-LV with the OET-RV: a switch above the text chooses the Readers' Version, the Literal Version, or both (remembered on the device).
    With both, the LV of the same verses goes under each run of RV paragraphs, or beside it on a wide screen, and a verse that's marked is marked in both.
    The LV has no headings of its own, so it's read in the RV's sections (and with only the LV, the RV's headings are still shown)
- show what a word translates (tap the word, in either version of the OET, or in either Spanish Bible), and mark the words of both versions that translate the same Hebrew or Greek word: the Hebrew or Greek word, its transliteration, dictionary form, gloss, Strong's number, and form,
    how else the OET-RV translates that dictionary form (with counts), and every verse where it's translated.
    Where the UBS dictionaries cover it, it also shows what the word means in this place (e.g., ἀρχή in John 1:1: ‘beginning, to begin: a point of time at the beginning of a duration’),
    with its semantic domains, each of which lists the other words with a meaning in it, and any UBS handbook article about the thing it refers to (e.g., ‘Camel, dromedary’)
- read a whole article of a dictionary or handbook (from a word, or from a search result), and follow its links to others
- browse the installed books, commentaries, and dictionaries (the Library, in the ⋮ menu), and read them entry by entry (e.g., a book chapter by chapter, with Previous and Next)
- show each work's copyright, licence, and attribution under its contents, and all of them together (*Licences and sources*, in the Library)
- show each book's and commentary's disclaimer wherever its words are shown: under the notes on a verse, at the end of an article or chapter, and with its contents
- search: a subject (the articles about it, the passages they refer to most, the other side of the question, where the words themselves are found,
    and, if the model is installed, the passages, notes, articles, and book chapters that are about it by meaning: see [Meaning.md](Meaning.md)), words together in a sentence, the original-language terms behind English words, and dictionary entries. Choosing a result opens its section with that verse in view and marked.

Its own words are in English and Spanish (`app/lib/strings.dart`), chosen by the device's language.

## How it fits together

| Part | What it is |
| --- | --- |
| `crates/biblelastic-engine` | The engine: the same code everywhere |
| `crates/biblelastic-ffi` | The engine as a native library (`libbiblelastic.so`, about 0.8 MB) with two C functions: `biblelastic_request` and `biblelastic_free` |
| `crates/biblelastic-wasm` + `web/*.js` | The engine as WebAssembly in a web worker (see [Browser.md](Browser.md)) |
| `app/lib/engine/engine.dart` | What the app sees: `start`, `request`, `installed`, `install`, `remove`, `removeAll` |
| `app/lib/engine/engine_native.dart` | … on phones and desktops: calls the native library (Dart FFI) from an isolate of its own, so a slow request can't freeze the display, and keeps modules as files in the app's own folder |
| `app/lib/engine/engine_web.dart` | … in browsers: calls `web/biblelastic.js`, which keeps modules in the browser's own storage |

Every request is the same text everywhere (`command=read`, `passage=JHN 3`, …) and every answer is the same JSON, so the app's screens don't know which platform they're on.
Four requests were added for the app:

- `contents` lists an edition's documents, with how many chapters each has, and whether there's anything before chapter 1.
- `read` gives a passage laid out for reading: paragraphs (each with the edition's own style, e.g., `q1`, and its kind, e.g., `heading`),
    made of chapter numbers, verse numbers, and pieces of text with their character styles. A whole chapter comes with its headings, and chapter 0 is whatever comes before chapter 1.
    With `unit=section` it gives the section that a passage starts in (or, with `document` and `section`, a section by its number), together with its heading, the verses it covers,
    and which sections come before and after it. Section 0 of a document is whatever comes before its first heading, and an edition without headings is read by chapter.
    With `detail=words`, each piece of text is one word (with its punctuation) and has the word's number, `w`.
- With `unit=section`, `read` also gives `noted`: the verses that an installed commentary has a note of its own on (one that starts at that verse).
- `word` (with `slot`, a word's number) follows a word of a translation through the alignment modules to the original-language word(s) it translates,
    with their details and how the translation renders the same dictionary form. For a very common word (e.g., καί, 8,957 times) only the first 4,000 places are counted.
    It also gives `linked`: for every installed translation that's aligned to the same originals (the OET-RV and the OET-LV so far), the numbers of the words that translate them.
- `lemma` (with `original` and `lemma`) lists the verses of a translation where an original-language dictionary form is translated.
- `word` also gives each original's `meaning` (gloss, definition, note, code, and domains) and `articles`, where a meanings layer is installed.
- `article` (with `locator`, e.g., `Fauna 2.8`) gives one whole entry of a dictionary, handbook, or commentary, as paragraphs, with the entries it links to.
- `toc` (with `edition`) lists a work's entries in order, and `article` also gives the `previous` and `next` ones; `info` gives each module's `title` and `disclaimer`.
- `domain` (with `original` and `domain`) lists the words of an original-language edition with a meaning in a semantic domain, the commonest first.

## Building and running

    app/build-engine.sh                 # Builds the engine for Android (three processor types), Linux, and browsers, and copies it into app/
    cd app
    flutter test                        # Includes a test of the native library against the real modules

Android (with a phone connected by USB, and the modules served from this computer):

    flutter build apk --debug
    adb install -r build/app/outputs/flutter-apk/app-debug.apk
    adb reverse tcp:8377 tcp:8377       # So that the phone's localhost:8377 is this computer's
    cd .. && python3 -m http.server 8377

Browser:

    flutter build web --base-href /app/build/web/
    cd .. && python3 -m http.server 8377       # Then open http://localhost:8377/app/build/web/
    node app/test_web.mjs /tmp                 # Or: open it in headless Chrome, and save screenshots

Modules come from `http://localhost:8377/build/modules/` unless the app is built with `--dart-define=MODULES=https://…/`.
The Android build needs a full Java development kit: if Gradle says that the Java it found has no compiler,
set `JAVA_HOME` to one that has (e.g., Android Studio's own, in its `jbr` folder).

## What's been tried

On 17 November 2026: in headless Chrome on a desktop, and on an OPPO CPH2579 phone (Android, debug build).
On both, the modules installed, John 1 displayed, the notes on a verse opened, and searches ran, including the Hebrew and Greek terms for ‘love’.
The section view (added later the same day) was checked in headless Chrome by screenshot, and on the phone by hand.
Tapping a word (17 November) was checked in headless Chrome by screenshot (including the list of places), and on the phone by screenshot.
The OET-LV with the OET-RV (19 November) was checked in headless Chrome by screenshot, on a phone-sized and a wide screen, and on the phone by screenshot.
Choosing a Spanish Bible, and its notes (25 November), were checked in headless Chrome by screenshot, and on the phone (26 November), with meaning-based search in Spanish
and tapping a Spanish word (e.g., *Verbo* in John 1:1 → λόγος).

## Known gaps

- **The reader doesn't remember where you were**, and there's no chapter view to choose in place of the section view.
- **A Spanish word's original is explained in English** (the OET's glosses and the UBS dictionaries' meanings), and the Library lists works in every language together.
- **The OET-LV's word joiners** (`_`) are shown as they are, as decided for the ingest. The OET website shows them more subtly.
- **Sections aren't listed anywhere**: a book's section headings would make a better way in than chapter numbers.
- **Verse numbers are still small targets**, though the area that can be tapped is wider than the number. A word and a verse number are told apart only by where the finger lands.
- **The counts of a word's renderings** group words by exactly how they're spelt (so ‘love’ and ‘loves’ are counted apart).
- **The marked words can be hidden** behind the word's sheet until it's closed, on a small screen.
- **The disclaimer's link isn't followed** when it's tapped (it's only shown underlined), and a book's references aren't links to the passages yet.
- **Search results and notes are plain text** (an article opened in full is too: its italics, tables, and pictures aren't shown). A passage that's opened from a search has only its first verse marked.
- **Modules aren't published yet**, and a broken download isn't resumed (see [Publishing.md](Publishing.md)).
- **Only debug builds were made**: no release build, signing, app icon, or store listing. A debug build is 155 MB; a release build will be far smaller.
- **Linux desktop is set up but untried**, and there's nothing for iOS, macOS, or Windows yet.
- **The web build fetches its fonts from Google** when it starts, so it doesn't yet work offline, and there's no service worker for the engine and modules.
- **Spanish covers the app's own words only**: the Bible, notes, and passage codes in notes are still English.
