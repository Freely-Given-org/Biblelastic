
import { spawn } from 'node:child_process';
import { createReadStream, existsSync, mkdtempSync, rmSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../..', import.meta.url));
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


// Meaning-based search in the browser: how long the model takes to load, and each query (the model, then comparing with every passage)
// (With `all` on the command line: every work's vectors, not only the OET-RV's)
const measure = async (queries, all) => {
    const { Biblelastic } = await import('/web/biblelastic.js');
    const engine = await Biblelastic.start({});
    const { modules } = await (await fetch('/build/modules/index.json')).json();
    const names = all ? modules.map(module => module.name).filter(name => /\.(model|vectors)$/.test(name)) : ['bge-small-en-v1.5.model', 'OET-RV.vectors'];
    for (const name of names) await engine.install(name, `/build/modules/${name}.blm`);
    const report = [];
    for (const words of queries) {
        const { response, milliseconds, memoryBytes } = await engine.request({ command: 'meaning', words, editions: all ? '' : 'OET-RV', limit: 3, length: 60 });
        report.push({ words, ok: response.ok, error: response.error, milliseconds: Math.round(milliseconds), memoryMB: Math.round(memoryBytes / 1048576), first: response.scripture?.[0]?.locator });
    }
    engine.stop();
    return report;
};

let failed = false;
try {
    const queries = ['why do good people suffer', 'once saved, always saved', 'a prophet swallowed by a huge fish', 'What does the Bible say about worry and anxiety?', 'forgiveness'];
    const report = await inPage('/blank', `() => (${measure})(${JSON.stringify(queries)}, ${process.argv[2] === 'all'})`);
    for (const line of report) console.log(`${String(line.milliseconds).padStart(6)} ms  ${String(line.memoryMB).padStart(4)} MB  ${line.ok ? line.first : line.error}  (${line.words})`);
} catch (error) { console.log(`FAILED: ${error.message}`); failed = true; }
finally { socket.close(); chrome.kill(); server.close(); await new Promise(resolve => chrome.on('exit', resolve)); rmSync(profile, { recursive: true, force: true }); }
process.exit(failed ? 1 : 0);
