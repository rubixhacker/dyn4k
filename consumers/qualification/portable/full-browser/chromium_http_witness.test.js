const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {Cdp, endpoint, waitForControl, validateControl} =
    require('./chromium_http_witness.js');
const {observedUrlMatches} = require('./chromium_observer_run.js');

class FakeSocket {
    constructor() { this.sent = []; }
    open() { this.onopen(); }
    send(message) { this.sent.push(JSON.parse(message)); }
    reply(id, result) { this.onmessage({data: JSON.stringify({id, result})}); }
    drop() { this.onclose({code: 1006}); }
    error() { this.onerror(new Error('socket error')); }
    close() { this.drop(); }
}

test('close rejects a pending command and clears its entry', async () => {
    const cdp = new Cdp('ws://fake', FakeSocket, 1000);
    cdp.socket.open();
    const result = cdp.send('Network.getResponseBody', {requestId: 'one'});
    const second = cdp.send('Page.enable');
    await Promise.resolve();
    assert.equal(cdp.pending.size, 2);
    cdp.socket.drop();
    await Promise.all([assert.rejects(result, /closed/i),
        assert.rejects(second, /closed/i)]);
    assert.equal(cdp.pending.size, 0);
    await assert.rejects(cdp.send('Page.navigate'), /closed/i);
});

test('error rejects a pending command and clears its entry', async () => {
    const cdp = new Cdp('ws://fake', FakeSocket, 1000);
    cdp.socket.open();
    const result = cdp.send('Network.enable');
    await Promise.resolve();
    cdp.socket.error();
    await assert.rejects(result, /socket error/i);
    assert.equal(cdp.pending.size, 0);
});

test('silence rejects at the command deadline and ignores a late reply', async () => {
    const cdp = new Cdp('ws://fake', FakeSocket, 20);
    cdp.socket.open();
    await assert.rejects(cdp.send('Page.enable'), /timed out/i);
    assert.equal(cdp.pending.size, 0);
    cdp.socket.reply(1, {});
    const next = cdp.send('Page.navigate');
    await Promise.resolve();
    cdp.socket.reply(2, {frameId: 'page'});
    assert.deepEqual(await next, {frameId: 'page'});
    cdp.close();
});

test('connection without open has a finite deadline', async () => {
    const cdp = new Cdp('ws://fake', FakeSocket, 20);
    await assert.rejects(cdp.send('SystemInfo.getProcessInfo'), /timed out/i);
    assert.equal(cdp.pending.size, 0);
});

test('silent discovery fetch is aborted at the remaining deadline', async () => {
    let signal;
    const silent = (url, options) => {
        assert.equal(url, 'http://127.0.0.1:41234/json/version');
        signal = options.signal;
        return new Promise(() => {});
    };
    await assert.rejects(endpoint(41234, '/json/version', silent, 30), /did not appear/);
    assert.equal(signal.aborted, true);
});

test('discovery deadline also covers an unfinished JSON body', async () => {
    let signal;
    const unfinished = (url, options) => {
        signal = options.signal;
        return Promise.resolve({ok: true, json: () => new Promise(() => {})});
    };
    await assert.rejects(endpoint(41234, '/json/list', unfinished, 30), /did not appear/);
    assert.equal(signal.aborted, true);
});

test('normal discovery retries and clears request timers', async () => {
    const requests = [];
    const fetcher = (url, options) => {
        requests.push({url, signal: options.signal});
        if (requests.length === 1) return Promise.resolve({ok: false});
        return Promise.resolve({ok: true, json: async () => ({id: 'page'})});
    };
    assert.deepEqual(await endpoint(41234, '/json/list', fetcher, 100), {id: 'page'});
    assert.equal(requests.length, 2);
    assert.deepEqual(requests.map(item => item.url),
        ['http://127.0.0.1:41234/json/list', 'http://127.0.0.1:41234/json/list']);
    await new Promise(resolve => setTimeout(resolve, 110));
    assert.equal(requests[0].signal.aborted, false);
    assert.equal(requests[1].signal.aborted, false);
});

test('missing observer readiness times out without navigation permission', async () => {
    const root = fs.mkdtempSync(path.join(process.env.TMPDIR || os.tmpdir(), 'cdp-handshake-'));
    try {
        await assert.rejects(waitForControl(path.join(root, 'allow.json'),
            {offer_sha256: 'fresh', browser_pid: 41}, 0, 30), /timed out/);
    } finally { fs.rmSync(root, {recursive: true}); }
});

test('wrong process and stale readiness fail closed', () => {
    assert.throws(() => validateControl({offer_sha256: 'fresh', browser_pid: 42,
        ready_ns: 201}, {offer_sha256: 'fresh', browser_pid: 41}, 200), /differs/);
    assert.throws(() => validateControl({offer_sha256: 'fresh', browser_pid: 41,
        ready_ns: 199}, {offer_sha256: 'fresh', browser_pid: 41}, 200), /stale/);
});

test('current epoch nanoseconds are valid control times', () => {
    const offered = Date.now() * 1000000;
    assert.deepEqual(validateControl({offer_sha256: 'fresh', browser_pid: 41,
        ready_ns: offered + 1000000},
    {offer_sha256: 'fresh', browser_pid: 41}, offered),
    {offer_sha256: 'fresh', browser_pid: 41, ready_ns: offered + 1000000});
});

test('premature stop fails before observer release', async () => {
    const root = fs.mkdtempSync(path.join(process.env.TMPDIR || os.tmpdir(), 'cdp-handshake-'));
    try {
        fs.writeFileSync(path.join(root, 'stop'), '');
        await assert.rejects(waitForControl(path.join(root, 'allow.json'),
            {offer_sha256: 'fresh', browser_pid: 41}, 0, 50,
            [path.join(root, 'stop')]), /premature/);
    } finally { fs.rmSync(root, {recursive: true}); }
});

test('both generated JS and Wasm module handoffs preserve distinct offers', () => {
    for (const target of ['js', 'wasmJs']) {
        for (const module of ['core', 'facade']) {
            const offer = `${target}:${module}:fresh`;
            assert.deepEqual(validateControl({offer_sha256: offer, browser_pid: 41,
                ready_ns: 201}, {offer_sha256: offer, browser_pid: 41}, 200),
            {offer_sha256: offer, browser_pid: 41, ready_ns: 201});
            assert.throws(() => validateControl({offer_sha256: `${target}:other:fresh`,
                browser_pid: 41, ready_ns: 201},
            {offer_sha256: offer, browser_pid: 41}, 200), /differs/);
        }
    }
});

test('observer response URLs are exact Karma-relative paths', () => {
    const capture = new URL('http://localhost:44281/?id=one');
    assert.equal(observedUrlMatches('/absolute/tmp/_karma_webpack_/runtime.js?one',
        capture), true);
    assert.equal(observedUrlMatches('http://elsewhere:44281/runtime.js', capture), false);
    assert.equal(observedUrlMatches('//elsewhere:44281/runtime.js', capture), false);
});
