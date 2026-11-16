// The Biblelastic engine for web pages. The engine runs in a worker (see engine-worker.js), so every call is asynchronous.
//
//     const engine = await Biblelastic.start();
//     await engine.install('OET-RV.text', '/modules/OET-RV.text.blm');
//     const { response, milliseconds, bytesRead } = await engine.request({ command: 'find', words: 'grace truth' });

export class Biblelastic {
    #worker; #pending = new Map(); #nextId = 1;

    /** Start the engine, opening whichever modules are already installed in this browser.
     *  reader: 'auto' (the default), 'blob' or 'handle': see engine-worker.js.
     *  cacheBytes: how much of the modules the engine may keep in memory (the default is 16 MB). */
    static async start({ worker = new URL('engine-worker.js', import.meta.url), wasm = new URL('biblelastic.wasm', import.meta.url), reader, cacheBytes } = {}) {
        const engine = new Biblelastic();
        engine.#worker = new Worker(worker);
        engine.#worker.onmessage = ({ data: { id, result, error, progress } }) => {
            const pending = engine.#pending.get(id);
            if (progress) return pending.onProgress?.(progress);
            engine.#pending.delete(id);
            if (error === undefined) pending.resolve(result); else pending.reject(new Error(error));
        };
        engine.#worker.onerror = event => { for (const pending of engine.#pending.values()) pending.reject(new Error(event.message)); engine.#pending.clear(); };
        await engine.#call('start', { wasm: String(wasm), reader, cacheBytes });
        return engine;
    }

    #call(action, parameters = {}, onProgress) {
        return new Promise((resolve, reject) => {
            const id = this.#nextId++;
            this.#pending.set(id, { resolve, reject, onProgress });
            this.#worker.postMessage({ id, action, ...parameters });
        });
    }

    /** The installed modules: [{ name, bytes }] */
    list() { return this.#call('list'); }

    /** Download a module into the browser's storage. onProgress gets { name, written }. */
    install(name, url, onProgress) { return this.#call('install', { name, url: String(new URL(url, location.href)) }, onProgress); }

    /** Remove the named modules, or all of them. */
    remove(names) { return this.#call('remove', { names }); }

    /** Ask the engine something, e.g. { command: 'terms', words: 'love loves' }.
     *  Resolves to { response, bytesRead, cachedBytes, milliseconds, memoryBytes }. */
    request(fields) { return this.#call('request', { text: Object.entries(fields).map(([key, value]) => `${key}=${value}`).join('\n') }); }

    /** Stop the engine, and let go of the module files. */
    stop() { this.#worker.terminate(); }

    /** Drop everything the engine has cached, as if it had just started. */
    forget() { return this.#call('request', { text: 'command=forget' }); }
}
