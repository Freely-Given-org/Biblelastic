# The app

`app/` is a minimal [Flutter](https://flutter.dev) app. It exists to prove that one Rust engine can sit behind one Flutter interface on every platform,
not to be the finished design. It runs on Android and in browsers, and is set up for Linux desktops (which hasn't been tried).

It can:

- install and remove modules, from a list (`index.json`) at a web address
- read the OET-RV a section at a time (from one section heading to the next, whichever chapters that covers), with its poetry indents, words of Jesus, and translators' additions shown differently
- step to the next or previous section, right through from one book into the next, or choose a book and chapter
- show what the installed commentaries and dictionaries say about a verse (tap its number)
- search: words together in a sentence, the original-language terms behind English words, and dictionary entries. Choosing a result opens its section with that verse in view and marked.

Its own words are in English and Spanish (`app/lib/strings.dart`), chosen by the device's language.

## How it fits together

| Part | What it is |
| --- | --- |
| `crates/biblelastic-engine` | The engine: the same code everywhere |
| `crates/biblelastic-ffi` | The engine as a native library (`libbiblelastic.so`, about 0.8 MB) with two C functions: `biblelastic_request` and `biblelastic_free` |
| `crates/biblelastic-wasm` + `web/*.js` | The engine as WebAssembly in a web worker (see [Browser.md](Browser.md)) |
| `app/lib/engine/engine.dart` | What the app sees: `start`, `request`, `installed`, `install`, `removeAll` |
| `app/lib/engine/engine_native.dart` | … on phones and desktops: calls the native library (Dart FFI) from an isolate of its own, so a slow request can't freeze the display, and keeps modules as files in the app's own folder |
| `app/lib/engine/engine_web.dart` | … in browsers: calls `web/biblelastic.js`, which keeps modules in the browser's own storage |

Every request is the same text everywhere (`command=read`, `passage=JHN 3`, …) and every answer is the same JSON, so the app's screens don't know which platform they're on.
Two requests were added for the app:

- `contents` lists an edition's documents, with how many chapters each has, and whether there's anything before chapter 1.
- `read` gives a passage laid out for reading: paragraphs (each with the edition's own style, e.g., `q1`, and its kind, e.g., `heading`),
    made of chapter numbers, verse numbers, and pieces of text with their character styles. A whole chapter comes with its headings, and chapter 0 is whatever comes before chapter 1.
    With `unit=section` it gives the section that a passage starts in (or, with `document` and `section`, a section by its number), together with its heading, the verses it covers,
    and which sections come before and after it. Section 0 of a document is whatever comes before its first heading, and an edition without headings is read by chapter.

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

## Known gaps

- **Only the OET-RV can be read**, the reader doesn't remember where you were, and there's no chapter view to choose in place of the section view.
- **Sections aren't listed anywhere**: a book's section headings would make a better way in than chapter numbers.
- **Verse numbers are small targets** for a finger, and nothing else about a verse can be tapped yet (e.g., a word, to see what it translates).
- **Search results and notes are plain text**, and dictionary entries are cut short, not opened in full.
- **Modules are only fetched from a development address**, with no resuming of a broken download, no checking of what was downloaded, and no licence or attribution shown.
- **Only debug builds were made**: no release build, signing, app icon, or store listing. A debug build is 155 MB; a release build will be far smaller.
- **Linux desktop is set up but untried**, and there's nothing for iOS, macOS, or Windows yet.
- **The web build fetches its fonts from Google** when it starts, so it doesn't yet work offline, and there's no service worker for the engine and modules.
- **Spanish covers the app's own words only**: the Bible, notes, and passage codes in notes are still English.
