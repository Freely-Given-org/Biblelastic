// Run the engine in a real (headless) browser, and report what the queries cost:  node web/test.mjs
// Needs Node 22+ and Chrome or Chromium (set CHROME to its path if it isn't found). Run web/build.sh and `biblelastic compile` first.

import { spawn } from 'node:child_process';
import { createReadStream, existsSync, mkdtempSync, rmSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.json': 'application/json', '.wasm': 'application/wasm' };

const server = createServer((request, response) => {
    let path = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
    if (path === '/blank') return response.writeHead(200, { 'Content-Type': TYPES['.html'] }).end('<!doctype html><title>test</title>');
    if (path.endsWith('/')) path += 'index.html';
    const file = join(root, normalize(path));
    if (!file.startsWith(root) || !existsSync(file) || !statSync(file).isFile()) return response.writeHead(404).end();
    response.writeHead(200, { 'Content-Type': TYPES[extname(file)] ?? 'application/octet-stream', 'Content-Length': statSync(file).size });
    createReadStream(file).pipe(response);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://localhost:${server.address().port}`;

const chromePath = process.env.CHROME ?? ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser'].find(existsSync);
const profile = mkdtempSync(join(tmpdir(), 'biblelastic-test-'));
const chrome = spawn(chromePath, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run', 'about:blank']);
const browserUrl = await new Promise((resolve, reject) => {
    let output = '';
    chrome.stderr.on('data', data => { output += data; const match = output.match(/DevTools listening on (ws:\S+)/); if (match) resolve(match[1]); });
    chrome.on('exit', () => reject(new Error(`Chrome didn't start:\n${output}`)));
});

// Just enough of the DevTools protocol to open a page and run something in it
const socket = new WebSocket(browserUrl);
await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
const waiting = new Map();
let nextId = 1;
socket.onmessage = ({ data }) => { const message = JSON.parse(data); waiting.get(message.id)?.(message); waiting.delete(message.id); };
const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const id = nextId++;
    waiting.set(id, message => message.error ? reject(new Error(`${method}: ${message.error.message}`)) : resolve(message.result));
    socket.send(JSON.stringify({ id, method, params, sessionId }));
});
async function inPage(path, script) {
    const { targetId } = await send('Target.createTarget', { url: origin + path });
    const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
    for (let n = 0; n < 100; n++) { // Wait for the page to load
        const { result } = await send('Runtime.evaluate', { expression: `location.origin === ${JSON.stringify(origin)} && document.readyState === 'complete'` }, sessionId);
        if (result.value) break;
        await new Promise(resolve => setTimeout(resolve, 50));
    }
    const { result, exceptionDetails } = await send('Runtime.evaluate', { expression: `(${script})()`, awaitPromise: true, returnByValue: true }, sessionId);
    await send('Target.closeTarget', { targetId });
    if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text);
    return result.value;
}

const REQUESTS = [
    { command: 'terms', words: 'love loves loved loving', limit: 3 },
    { command: 'find', words: 'grace truth', within: 'sentence' },
    { command: 'marked', words: 'pronoun_to_name', limit: 2 },
];

// Runs in the page
const measure = async (reader, requests) => {
    const { Biblelastic } = await import('/web/biblelastic.js');
    const report = { reader, requests: [] };
    let started = performance.now();
    const engine = await Biblelastic.start({ reader });
    report.startMs = performance.now() - started;
    if (!(await engine.list()).length) {
        const { modules } = await (await fetch('/build/modules/index.json')).json();
        started = performance.now();
        for (const { name } of modules) await engine.install(name, `/build/modules/${name}.blm`);
        report.installMs = performance.now() - started;
    }
    report.modules = await engine.list();
    await engine.forget();
    for (const fields of [...requests, ...requests]) { // The second time round, everything needed is already cached
        const { response, bytesRead, milliseconds, memoryBytes } = await engine.request(fields);
        report.requests.push({ command: fields.command, ok: response.ok, error: response.error, total: response.total, bytesRead, milliseconds, memoryBytes,
                               first: response.terms?.[0]?.lemma ?? response.examples?.[0]?.reference });
    }
    report.storage = (await navigator.storage.estimate()).usage;
    engine.stop();
    return report;
};

// Runs in the page: can two engines (as in two tabs) have the same modules open at once?
const together = async reader => {
    const { Biblelastic } = await import('/web/biblelastic.js');
    const first = await Biblelastic.start({ reader });
    try {
        const second = await Biblelastic.start({ reader });
        const { response } = await second.request({ command: 'find', words: 'grace truth' });
        second.stop();
        return response.ok ? 'yes' : `no: ${response.error}`;
    } catch (error) { return `no: ${error.message}`; }
    finally { first.stop(); }
};

// Runs in the test page itself: wait for it to start, press Run, and read what it shows
const usePage = async () => {
    const until = async test => { for (let n = 0; n < 200 && !test(); n++) await new Promise(resolve => setTimeout(resolve, 50)); return test(); };
    const text = id => document.getElementById(id).textContent;
    if (!await until(() => text('status') !== 'Starting…')) return { status: 'never started' };
    document.querySelector('#request button').click();
    await until(() => text('cost') !== '');
    return { status: text('status'), cost: text('cost'), installed: document.querySelectorAll('#modules tr').length, results: document.querySelectorAll('#results p').length,
             first: document.querySelector('#results p:nth-child(2)')?.textContent };
};

let failed = false;
try {
    const megabytes = bytes => (bytes / 1048576).toFixed(2) + ' MB';
    for (const reader of ['handle', 'blob']) {
        const report = await inPage('/blank', `() => (${measure})(${JSON.stringify(reader)}, ${JSON.stringify(REQUESTS)})`);
        console.log(`\nReader '${reader}': started in ${report.startMs.toFixed(0)} ms; ${report.modules.length} modules installed` +
                    (report.installMs ? ` in ${(report.installMs / 1000).toFixed(1)} s` : ' already') + `, using ${megabytes(report.storage)} of storage`);
        report.requests.forEach((request, n) => {
            console.log(`  ${n < REQUESTS.length ? 'cold' : 'warm'} ${request.command.padEnd(7)}${request.milliseconds.toFixed(1).padStart(7)} ms  read ${megabytes(request.bytesRead).padStart(9)}` +
                        `  memory ${megabytes(request.memoryBytes).padStart(9)}  ${request.ok ? `${request.total} results, first: ${request.first}` : `FAILED: ${request.error}`}`);
            if (!request.ok || !request.total) failed = true;
        });
    }
    for (const reader of ['handle', 'blob']) console.log(`\nTwo engines at once with reader '${reader}': ${await inPage('/blank', `() => (${together})(${JSON.stringify(reader)})`)}`);
    const page = await inPage('/web/', usePage);
    console.log('\nTest page:', page);
    if (page.status !== 'The engine is running.' || !page.results) failed = true;
} catch (error) { console.error(error); failed = true; }
finally {
    socket.close(); chrome.kill(); server.close();
    await new Promise(resolve => chrome.on('exit', resolve));
    rmSync(profile, { recursive: true, force: true, maxRetries: 5 });
}
console.log(failed ? '\nFAILED' : '\nPassed');
process.exit(failed ? 1 : 0);
