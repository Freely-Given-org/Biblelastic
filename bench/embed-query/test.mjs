// Run the embedding trial page in headless Chrome, at full speed and with the processor slowed down:  node bench/embed-query/test.mjs
// Needs Node 22+ and Chrome or Chromium (set CHROME to its path if it isn't found). Run build.sh first.

import { spawn } from 'node:child_process';
import { createReadStream, existsSync, mkdtempSync, rmSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../..', import.meta.url));
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript', '.wasm': 'application/wasm' };
const server = createServer((request, response) => {
    let path = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
    if (path.endsWith('/')) path += 'index.html';
    const file = join(root, normalize(path));
    if (!file.startsWith(root) || !existsSync(file) || !statSync(file).isFile()) return response.writeHead(404).end();
    response.writeHead(200, { 'Content-Type': TYPES[extname(file)] ?? 'application/octet-stream', 'Content-Length': statSync(file).size });
    createReadStream(file).pipe(response);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://localhost:${server.address().port}`;

const chromePath = process.env.CHROME ?? ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser'].find(existsSync);
const profile = mkdtempSync(join(tmpdir(), 'biblelastic-embed-'));
const chrome = spawn(chromePath, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run', 'about:blank']);
const browserUrl = await new Promise((resolve, reject) => {
    let output = '';
    chrome.stderr.on('data', data => { output += data; const match = output.match(/DevTools listening on (ws:\S+)/); if (match) resolve(match[1]); });
    chrome.on('exit', () => reject(new Error(`Chrome didn't start:\n${output}`)));
});
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

// Open a page, slow the processor down, run its trial, and return what it measured
async function trial(page, slowdown, ...parameters) {
    const { targetId } = await send('Target.createTarget', { url: `${origin}/bench/embed-query/web/${page}` });
    const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
    for (let n = 0; n < 100; n++) {
        const { result } = await send('Runtime.evaluate', { expression: `typeof window.runTrial === 'function'` }, sessionId);
        if (result.value) break;
        await new Promise(resolve => setTimeout(resolve, 50));
    }
    await send('Emulation.setCPUThrottlingRate', { rate: slowdown }, sessionId);
    const { result, exceptionDetails } = await send('Runtime.evaluate', { expression: `window.runTrial(${parameters.map(parameter => JSON.stringify(parameter)).join(', ')})`, awaitPromise: true, returnByValue: true }, sessionId);
    await send('Target.closeTarget', { targetId });
    if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text);
    return result.value;
}

let failed = false;
try {
    console.log('tract:');
    for (const [model, slowdown, tokens] of [['float32', 1, 32], ['int8', 1, 32], ['float32', 1, 16], ['float32', 6, 32], ['int8', 6, 32]]) {
        const measured = await trial('', slowdown, model, tokens);
        console.log(`${model.padEnd(8)} ${tokens} tokens, processor ${slowdown}× slower: model loads in ${measured.loadMs.toFixed(0).padStart(5)} ms, uses ${(measured.memoryBytes / 1048576).toFixed(0).padStart(4)} MB;` +
                    ` a query takes ${measured.queryMs.toFixed(0).padStart(4)} ms (slowest ${measured.slowestQueryMs.toFixed(0)}); agreement ${measured.agreement.toFixed(4)};` +
                    ` comparing with 8,725 passages ${measured.scanMs[8725].toFixed(0)} ms, with 100,000 ${measured.scanMs[100000].toFixed(0)} ms`);
        if (measured.agreement < 0.99) failed = true;
    }
    if (existsSync(join(root, 'build/embeddings/ort/package/dist/ort.wasm.min.mjs'))) {
        console.log('\nONNX Runtime (one thread):');
        for (const [model, slowdown] of [['int8', 1], ['float32', 1], ['int8', 6], ['float32', 6]]) {
            const measured = await trial('ort.html', slowdown, model);
            console.log(`${model.padEnd(8)} processor ${slowdown}× slower: runtime and model load in ${measured.loadMs.toFixed(0).padStart(5)} ms; a query takes ${measured.paddedMs.toFixed(1).padStart(6)} ms padded to 32 tokens,` +
                        ` ${measured.queryMs.toFixed(1).padStart(6)} ms at its own length (slowest ${measured.queryMsSlowest.toFixed(0)}); agreement ${measured.queryMsAgreement.toFixed(4)}`);
            if (measured.queryMsAgreement < 0.99) failed = true;
        }
    } else console.log('\n(ONNX Runtime not tried: unpack the onnxruntime-web package into build/embeddings/ort/ first)');
} catch (error) { console.log(`FAILED: ${error.message}`); failed = true; }
finally {
    socket.close(); chrome.kill(); server.close();
    await new Promise(resolve => chrome.on('exit', resolve));
    rmSync(profile, { recursive: true, force: true });
}
console.log(failed ? '\nFAILED' : '\nPassed');
process.exit(failed ? 1 : 0);
