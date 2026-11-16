// The Biblelastic engine in a web worker. Use it through biblelastic.js.
//
// It has to be a worker: the engine reads module files synchronously, and browsers only allow
// synchronous file access (to the Origin Private File System, OPFS) inside workers.
// Each installed module is kept open, and the engine asks for byte ranges of it as it needs them.
//
// There are two ways to read, chosen when starting:
//   'blob'    FileReaderSync on slices of the file. Works in every browser, and in several tabs at once.
//   'handle'  A FileSystemSyncAccessHandle. Locks the file, so only one tab can have the modules open.

const FOLDER = 'modules';
const encoder = new TextEncoder(), decoder = new TextDecoder();
let engine = null;   // The WebAssembly module's exports
let files = [];      // { name, file } or { name, handle }; the index is the engine's file number
let reader = 'blob';
const fileReader = new FileReaderSync();

const imports = { biblelastic: {
    storage_read(file, offset, pointer, length) { // memory.buffer is fetched each time because it's replaced whenever the memory grows
        const source = files[file];
        if (source.handle) return source.handle.read(new Uint8Array(engine.memory.buffer, pointer, length), { at: offset });
        const data = new Uint8Array(fileReader.readAsArrayBuffer(source.file.slice(offset, offset + length)));
        new Uint8Array(engine.memory.buffer, pointer, data.length).set(data);
        return data.length;
    },
} };

function withText(text, call) {
    const bytes = encoder.encode(text);
    const pointer = engine.allocate(bytes.length);
    new Uint8Array(engine.memory.buffer, pointer, bytes.length).set(bytes);
    try { return call(pointer, bytes.length); } finally { engine.release(pointer, bytes.length); }
}

const folder = async () => (await navigator.storage.getDirectory()).getDirectoryHandle(FOLDER, { create: true });

function closeModules() {
    engine.clear_modules();
    for (const file of files) file.handle?.close();
    files = [];
}

async function openModules() {
    closeModules();
    const found = [];
    for await (const [name, handle] of (await folder()).entries())
        if (handle.kind === 'file' && name.endsWith('.blm')) found.push([name.slice(0, -4), handle]);
    found.sort((a, b) => a[0] < b[0] ? -1 : 1);
    for (const [name, fileHandle] of found) {
        files.push(reader === 'handle' ? { name, handle: await fileHandle.createSyncAccessHandle() } : { name, file: await fileHandle.getFile() });
        withText(name, (pointer, length) => engine.add_module(pointer, length, files.length - 1));
    }
}

const list = () => files.map(file => ({ name: file.name, bytes: file.handle ? file.handle.getSize() : file.file.size }));

const actions = {
    async start({ wasm, reader: wanted }) {
        reader = wanted ?? reader;
        const response = await fetch(wasm);
        if (!response.ok) throw new Error(`${wasm}: ${response.status}`);
        engine = (await WebAssembly.instantiate(await response.arrayBuffer(), imports)).instance.exports;
        await openModules();
        return list();
    },

    // Download one module straight into storage, without ever holding it all in memory
    async install({ name, url }, progress) {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`${url}: ${response.status}`);
        closeModules();
        try {
            const handle = await (await (await folder()).getFileHandle(`${name}.blm`, { create: true })).createSyncAccessHandle();
            try {
                handle.truncate(0);
                let written = 0;
                const reader = response.body.getReader();
                for (;;) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    written += handle.write(value, { at: written });
                    progress({ name, written });
                }
                handle.flush();
            } finally { handle.close(); }
        } finally { await openModules(); }
        return list();
    },

    async remove({ names }) { // No names: remove them all
        closeModules();
        const directory = await folder();
        const all = [];
        for await (const name of directory.keys()) all.push(name);
        for (const name of all) if (!names || names.includes(name.replace(/\.blm$/, ''))) await directory.removeEntry(name);
        await openModules();
        return list();
    },

    async list() { return list(); },

    // text: lines of key=value (see crates/biblelastic-engine/src/api.rs)
    async request({ text }) {
        const started = performance.now();
        const json = withText(text, (pointer, length) => {
            const result = engine.request(pointer, length);
            const size = new DataView(engine.memory.buffer).getUint32(result, true);
            return decoder.decode(new Uint8Array(engine.memory.buffer, result + 4, size));
        });
        const milliseconds = performance.now() - started;
        return { ...JSON.parse(json), milliseconds, memoryBytes: engine.memory.buffer.byteLength };
    },
};

// One at a time, in the order that they arrive
let queue = Promise.resolve();
onmessage = ({ data: { id, action, ...parameters } }) => {
    queue = queue.then(async () => {
        try {
            if (!engine && action !== 'start') throw new Error('the engine has not been started');
            postMessage({ id, result: await actions[action](parameters, progress => postMessage({ id, progress })) });
        } catch (error) { postMessage({ id, error: String(error.message ?? error) }); }
    });
};
