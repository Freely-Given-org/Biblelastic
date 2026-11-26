// Open the web build of the app in headless Chrome, install some modules, and save screenshots:  node app/test_web.mjs [FOLDER-FOR-SCREENSHOTS]
// Needs Node 22+ and Chrome or Chromium (set CHROME to its path if it isn't found).
// Run first: app/build-engine.sh web, then (in app/) flutter build web --base-href /app/build/web/, and `biblelastic compile`.

import { spawn } from 'node:child_process';
import { createReadStream, existsSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const shots = process.argv[2] ?? tmpdir();
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.wasm': 'application/wasm', '.png': 'image/png', '.otf': 'font/otf', '.ttf': 'font/ttf' };
// /flaky/NAME.blm is a module from build/modules, served with ranges, as a poor connection would: the first request for each is cut short after 1 MB,
// and, with ?corrupt, has a wrong byte (so that carrying on, and the SHA-256 check, are tested)
const flakyRequests = [];
const flakyServed = new Set();
function flaky(request, response, url) {
    const file = join(root, 'build/modules', normalize(url.pathname.slice('/flaky/'.length)));
    if (!existsSync(file)) return response.writeHead(404).end();
    const size = statSync(file).size;
    const range = request.headers.range ?? '';
    const start = range.startsWith('bytes=') ? Number(range.slice(6, -1)) : 0;
    const first = !flakyServed.has(url.pathname);
    flakyServed.add(url.pathname);
    flakyRequests.push(`${url.pathname.slice(7)} ${range || 'whole'}`);
    response.writeHead(start ? 206 : 200, { 'Content-Type': 'application/octet-stream', 'Content-Length': size - start, 'Accept-Ranges': 'bytes',
                                            ...(start ? { 'Content-Range': `bytes ${start}-${size - 1}/${size}` } : {}) });
    const data = readFileSync(file).subarray(start);
    if (first && url.searchParams.has('corrupt')) { data[0] ^= 1; return response.end(data); }
    if (first && data.length > 1000000) { response.write(data.subarray(0, 1000000)); return setTimeout(() => response.socket.destroy(), 100); }
    response.end(data);
}

const server = createServer((request, response) => {
    const url = new URL(request.url, 'http://localhost');
    if (url.pathname.startsWith('/flaky/')) return flaky(request, response, url);
    let path = decodeURIComponent(url.pathname);
    if (path.endsWith('/')) path += 'index.html';
    const file = join(root, normalize(path));
    if (!file.startsWith(root) || !existsSync(file) || !statSync(file).isFile()) return response.writeHead(404).end();
    response.writeHead(200, { 'Content-Type': TYPES[extname(file)] ?? 'application/octet-stream', 'Content-Length': statSync(file).size });
    createReadStream(file).pipe(response);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://localhost:${server.address().port}`;

const chromePath = process.env.CHROME ?? ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser'].find(existsSync);
const profile = mkdtempSync(join(tmpdir(), 'biblelastic-app-'));
const chrome = spawn(chromePath, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run', '--window-size=412,892', 'about:blank']);
const browserUrl = await new Promise((resolve, reject) => {
    let output = '';
    chrome.stderr.on('data', data => { output += data; const match = output.match(/DevTools listening on (ws:\S+)/); if (match) resolve(match[1]); });
    chrome.on('exit', () => reject(new Error(`Chrome didn't start:\n${output}`)));
});
const socket = new WebSocket(browserUrl);
await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
const waiting = new Map();
const errors = [];
let nextId = 1;
socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.exception?.description ?? message.params.exceptionDetails.text);
    waiting.get(message.id)?.(message); waiting.delete(message.id);
};
const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const id = nextId++;
    waiting.set(id, message => message.error ? reject(new Error(`${method}: ${message.error.message}`)) : resolve(message.result));
    socket.send(JSON.stringify({ id, method, params, sessionId }));
});
const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

let failed = false;
try {
    const { targetId } = await send('Target.createTarget', { url: `${origin}/app/build/web/` });
    const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
    await send('Runtime.enable', {}, sessionId);
    await send('Emulation.setDeviceMetricsOverride', { width: 412, height: 892, deviceScaleFactor: 2, mobile: true }, sessionId);
    const evaluate = async expression => {
        const { result, exceptionDetails } = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }, sessionId);
        if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text);
        return result.value;
    };
    const shoot = async name => {
        const { data } = await send('Page.captureScreenshot', { format: 'png' }, sessionId);
        writeFileSync(join(shots, `${name}.png`), Buffer.from(data, 'base64'));
        console.log(`Saved ${join(shots, `${name}.png`)}`);
    };
    const tap = async (x, y) => {
        for (const type of ['mousePressed', 'mouseReleased']) await send('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: 1 }, sessionId);
        await sleep(1500);
    };
    await sleep(6000);
    await shoot('1-nothing-installed');

    // A poor connection: a download that's cut short is carried on from where it stopped, and one that arrives wrong isn't installed
    const poor = await evaluate(`(async () => {
        const { Biblelastic } = await import('${origin}/app/build/web/engine/biblelastic.js');
        const engine = await Biblelastic.start();
        const index = await (await fetch('${origin}/build/modules/index.json')).json();
        const sha256 = name => index.modules.find(module => module.name === name).sha256;
        await engine.install('OET-RV.text', '${origin}/flaky/OET-RV.text.blm', null, sha256('OET-RV.text'));
        let corrupt = 'installed';
        try { await engine.install('UHB.text', '${origin}/flaky/UHB.text.blm?corrupt', null, sha256('UHB.text')); } catch (error) { corrupt = error.message; }
        const installed = (await engine.list()).map(module => module.name);
        await engine.remove();
        engine.stop();
        return { corrupt, installed };
    })()`);
    console.log(`Poor connection: ${flakyRequests.join('; ')}; the corrupted one: ${poor.corrupt}; installed: ${poor.installed.join(', ')}`);
    if (flakyRequests[1] !== 'OET-RV.text.blm bytes=1000000-' || !poor.corrupt.includes("didn't download correctly") || poor.installed.join() !== 'OET-RV.text') {
        console.log('FAILED: the poor connection wasn\'t handled as it should be');
        failed = true;
    }

    // Install modules into this browser's storage with the engine's own JavaScript (as the app's Modules page does), then start the app again
    const installed = await evaluate(`(async () => {
        const { Biblelastic } = await import('${origin}/app/build/web/engine/biblelastic.js');
        const engine = await Biblelastic.start();
        let modules = [];
        const index = await (await fetch('${origin}/build/modules/index.json')).json(); // Every module there is
        for (const { name } of index.modules)
            modules = await engine.install(name, '${origin}/build/modules/' + name + '.blm');
        engine.stop();
        return modules.length;
    })()`);
    console.log(`${installed} modules installed`);
    await send('Page.reload', {}, sessionId);
    await sleep(6000);
    await shoot('2-reading');
    await tap(206, 80); // ‘Both’: the Literal Version with the Readers' Version
    await shoot('2a-both');
    await tap(120, 162); // A word in the first verse (‘beginning’), for what it translates, and to mark the words linked to it
    await shoot('2b-word');
    await tap(66, 611); // The narrower domain of its meaning here: the words that share it
    await shoot('2c-domain');
    await tap(28, 27); // Back to the sheet
    await tap(108, 828); // ‘Every place it’s translated’
    await shoot('2c-places');
    await tap(28, 27); // Back to the sheet
    await tap(200, 60); // Outside the sheet, to close it
    await shoot('2d-linked'); // The words that translate the same Greek word are marked in both versions
    await tap(25, 636); // The number of John 1:6, for the notes on it (where it is depends on the text and the fonts: check the screenshot)
    await shoot('3-notes');
    await tap(200, 60); // Outside the sheet, to close it
    await tap(352, 27); // The search button
    await send('Input.insertText', { text: 'once saved, always saved' }, sessionId);
    for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, text: type === 'keyDown' ? '\r' : undefined }, sessionId);
    await sleep(2000);
    await shoot('4-topic');
    await send('Input.dispatchMouseEvent', { type: 'mouseWheel', x: 200, y: 500, deltaX: 0, deltaY: 520 }, sessionId);
    await sleep(1000);
    await shoot('4b-topic-further');
    await sleep(3000); // For the passages found by meaning (the model is loaded the first time)
    await send('Input.dispatchMouseEvent', { type: 'mouseWheel', x: 200, y: 500, deltaX: 0, deltaY: 5200 }, sessionId);
    await sleep(1000);
    await shoot('4c-meaning');
    await send('Input.dispatchMouseEvent', { type: 'mouseWheel', x: 200, y: 500, deltaX: 0, deltaY: -5200 }, sessionId);
    await sleep(1000);
    await tap(100, 700); // A passage in the results: it should open in its section, with the verse marked (check the screenshot before for what's there)
    await sleep(1500);
    await shoot('5-landed');
    await tap(392, 27); // The ‘More’ menu
    await shoot('7a-menu');
    await tap(300, 104); // Library (the second item, after Bible)
    await shoot('7-library');
    await tap(120, 80); // Licences and sources
    await shoot('7b-licences');
    await tap(28, 27); // Back to the Library
    await tap(120, 178); // The first book
    await shoot('8-contents');
    await tap(120, 290); // Its fourth entry
    await sleep(1000);
    await shoot('9-chapter');
    for (let n = 0; n < 60; n++) await send('Input.dispatchMouseEvent', { type: 'mouseWheel', x: 200, y: 500, deltaX: 0, deltaY: 3000 }, sessionId); // To the end
    await sleep(1000);
    await shoot('9b-chapter-end');
    for (let n = 0; n < 3; n++) await tap(28, 27); // Back to the reader
    // A Spanish Bible, chosen from the menu, with its notes (the Spanish ones first)
    await tap(392, 27); // The ‘More’ menu
    await tap(300, 50); // Bible (the first item)
    await shoot('10a-bibles');
    await tap(200, 780); // The Aquifer Spanish text (the second): the same passage, in Spanish
    await sleep(1000);
    await shoot('10b-spanish');
    await tap(185, 87); // ‘vid’ in John 15:1, for the Greek word that it translates (from the Aquifer's alignments)
    await shoot('10b2-spanish-word');
    await tap(200, 60); // Outside the sheet, to close it
    await tap(25, 280); // The number of John 15:4, for its notes: the Spanish ones should come first
    await shoot('10c-spanish-notes');
    await tap(200, 60); // Outside the sheet, to close it
    await tap(392, 27); // Back to the OET, for the rest
    await tap(300, 50);
    await tap(200, 715);
    await sleep(1000);
    await send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false }, sessionId);
    await sleep(1500);
    await shoot('6-wide'); // Side by side
    if (errors.length) { console.log(`Errors in the page:\n${errors.join('\n')}`); failed = true; }
} catch (error) { console.log(`FAILED: ${error.message}`); failed = true; }
finally {
    socket.close(); chrome.kill(); server.close();
    await new Promise(resolve => chrome.on('exit', resolve));
    rmSync(profile, { recursive: true, force: true });
}
console.log(failed ? '\nFAILED' : '\nDone');
process.exit(failed ? 1 : 0);
