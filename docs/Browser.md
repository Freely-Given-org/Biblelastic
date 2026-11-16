# Biblelastic in the browser

The same Rust engine that the command-line tool uses is compiled to WebAssembly, and runs in a web worker.
It reads the same module files, which are downloaded once into the browser's private storage
(the Origin Private File System, OPFS), so searching then works offline. The server only provides static files.

This is a first trial, to check that the [module format](ModuleFormat.md) suits browsers. There's no app yet—only a test page.

    rustup target add wasm32-unknown-unknown     # Once
    web/build.sh                                 # Builds web/biblelastic.wasm
    target/release/biblelastic compile           # If the modules aren't built yet
    python3 -m http.server 8377                  # Then open http://localhost:8377/web/
    node web/test.mjs                            # Or run the test in headless Chrome

## The pieces

| File | What it is |
| --- | --- |
| `crates/biblelastic-engine/src/api.rs` | The interface for every kind of app: a text request in, JSON out |
| `crates/biblelastic-wasm` | The engine as a WebAssembly module (225 kB, or 77 kB gzipped) |
| `web/engine-worker.js` | The worker: loads the engine, installs modules into OPFS, and reads byte ranges for the engine |
| `web/biblelastic.js` | What a web page uses: `Biblelastic.start()`, then `install`, `list`, `remove`, `request` |
| `web/index.html` | The test page |
| `web/test.mjs` | The same test, automated |
| `build/modules/index.json` | The catalogue of modules, written by `biblelastic compile` |

No extra tools (such as wasm-bindgen) are needed: the WebAssembly module has five plain functions,
and needs only one from the browser (`storage_read`: copy these bytes of that file to here).

## Requests

A request is lines of `key=value`, and the response is JSON:

    command=terms
    edition=OET-RV
    words=love loves loved loving
    limit=3

The commands are `info`, `terms`, `find` (with `within`), and `marked`, with the same meanings and defaults as on the command line.
`target/release/biblelastic request command=find 'words=grace truth'` shows the same JSON that a browser gets.

## What the trial found

Measured in headless Chrome on a desktop computer, with all twelve modules (64 MB) installed:

| Request | First time | Read from storage | Again |
| --- | --- | --- | --- |
| `terms love loves loved loving` | 43 ms | 11.3 MB | 1.5 ms |
| `find grace truth` | 3 ms | 0.2 MB | 0.4 ms |
| `marked pronoun_to_name` | 6 ms | 0.5 MB | 1.7 ms |

The engine used 13 MB of memory after all three. Starting it (with the modules already installed) took about 10 ms.

- **The format needed no changes.** Reading only byte ranges, through one small interface, works the same in the browser as natively.
- **Reading must be synchronous, so the engine must be in a worker.** That's the only place browsers allow it.
- **There are two ways to read, and the slower one is the default.** A *sync access handle* is fastest (27 ms for the first request above),
    but it locks the file, so a second tab can't open the modules at all. Reading slices with `FileReaderSync` takes about half as long again,
    but works in several tabs at once, and in every current browser. `Biblelastic.start({ reader: 'handle' })` chooses the faster one.
- **Installing streams straight into storage**, so a module is never held whole in memory.

## Not done yet

- Only tried in Chrome on a desktop: not in Firefox or Safari, and not on a low-end phone (which is the real target).
- Not tried from Flutter's web build.
- An interrupted download leaves a broken module (which the engine refuses to open). Downloads should be resumed and checked, then renamed into place.
- If one tab reinstalls a module while another tab has it open, the other tab must restart its engine.
- The browser may delete the stored modules when it's short of space, unless the app asks for persistent storage.
- Nothing is cached for offline use except the modules: the page, worker, and engine need a service worker.
