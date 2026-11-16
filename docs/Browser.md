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
| `crates/biblelastic-wasm` | The engine as a WebAssembly module (389 kB, or 126 kB gzipped; about 95 kB of that is the zstd decoder) |
| `web/engine-worker.js` | The worker: loads the engine, installs modules into OPFS, and reads byte ranges for the engine |
| `web/biblelastic.js` | What a web page uses: `Biblelastic.start()`, then `install`, `list`, `remove`, `request` |
| `web/index.html` | The test page |
| `web/test.mjs` | The same test, automated |
| `build/modules/index.json` | The catalogue of modules, written by `biblelastic compile` |

No extra tools (such as wasm-bindgen) are needed: the WebAssembly module has six plain functions,
and needs only one from the browser (`storage_read`: copy these bytes of that file to here).

## Requests

A request is lines of `key=value`, and the response is JSON:

    command=terms
    edition=OET-RV
    words=love loves loved loving
    limit=3

The commands are `info`, `contents`, `read` (with `passage`), `terms`, `find` (with `within`), `marked`, `about` (with `passage`), and `entry`, with the same meanings and defaults as on the command line.
`target/release/biblelastic request command=find 'words=grace truth'` shows the same JSON that a browser gets.

## What the trial found

Measured in headless Chrome on a desktop computer, with all fourteen modules (58 MB) installed, running these one after another from a fresh start:

| Request | First time | Read from storage | Again |
| --- | --- | --- | --- |
| `terms love loves loved loving` | 30 ms | 4.3 MB | 1 ms |
| `find grace truth` | 2 ms | 0.4 MB | 0.1 ms |
| `find love God` | 2 ms | 0.1 MB | 1 ms |
| `marked pronoun_to_name` | 10 ms | 1.6 MB | 2 ms |
| `about JHN 3:16` | 6 ms | 1.0 MB | 0.2 ms |
| `entry aaron` | 6 ms | 0.5 MB | 0.1 ms |

The engine used 12.5 MB of memory after all six. Starting it (with the modules already installed) took about 10 ms.
When it was only allowed 2 MB for pages of the modules (`Biblelastic.start({ cacheBytes: 2 << 20 })`), it used 3.7 MB in all,
gave the same answers, and took about the same time, because it then reads everything again for each request.

- **The format works the same in the browser as natively.** Reading only byte ranges, through one small interface, was enough.
- **Reading must be synchronous, so the engine must be in a worker.** That's the only place browsers allow it.
- **There are three ways to read**, and `Biblelastic.start({ reader })` can choose one:
    - `'auto'` (the default) uses *read-only access handles* if the browser has them (Chrome does). They're fast, and several tabs can share the modules.
        Otherwise it falls back to `'blob'`.
    - `'blob'` reads slices with `FileReaderSync`. It works in every current browser and in several tabs, but each read costs much more:
        the first request above takes 87 ms rather than 30 ms.
    - `'handle'` uses an exclusive access handle. It's as fast as the first, but a second tab can't open the modules at all.
- **Installing streams straight into storage**, so a module is never held whole in memory.

## Not done yet

- Only tried in Chrome on a desktop: not in Firefox or Safari, and not on a low-end phone (which is the real target).
- Not tried from Flutter's web build.
- An interrupted download leaves a broken module (which the engine refuses to open). Downloads should be resumed and checked, then renamed into place.
- If one tab reinstalls a module while another tab has it open, the other tab must restart its engine.
- The browser may delete the stored modules when it's short of space, unless the app asks for persistent storage.
- Nothing is cached for offline use except the modules: the page, worker, and engine need a service worker.
