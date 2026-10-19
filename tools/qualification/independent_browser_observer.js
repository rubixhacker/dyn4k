#!/usr/bin/env node
const fs = require('node:fs');
const crypto = require('node:crypto');
const path = require('node:path');

function fail(message) { throw new Error(message); }
function now() { return Date.now() * 1000000; }
function hash(bytes) { return crypto.createHash('sha256').update(bytes).digest('hex'); }
function options(argv) {
    const result = {};
    for (let index = 0; index < argv.length; index += 2) {
        if (!argv[index]?.startsWith('--') || !argv[index + 1]) fail('observer argument differs');
        const key = argv[index].slice(2);
        if (key in result) fail('duplicate observer argument');
        result[key] = argv[index + 1];
    }
    if (Object.keys(result).sort().join(',') !==
            'browser,cdp-port,karma-port,module,output,pid,ready-file,stop-file,target,timeout-ms') {
        fail('observer arguments are incomplete');
    }
    if (!['core', 'facade'].includes(result.module) ||
            !['js', 'wasmJs'].includes(result.target) ||
            !Number.isSafeInteger(+result.pid) || +result.pid <= 0 ||
            !Number.isSafeInteger(+result['cdp-port']) || +result['cdp-port'] <= 0 ||
            !Number.isSafeInteger(+result['karma-port']) || +result['karma-port'] <= 0 ||
            !Number.isSafeInteger(+result['timeout-ms']) || +result['timeout-ms'] <= 0 ||
            !path.isAbsolute(result.output) || !path.isAbsolute(result['ready-file']) ||
            !path.isAbsolute(result['stop-file']) ||
            !path.isAbsolute(result.browser)) fail('observer identity or path differs');
    return result;
}
function processIdentity(pid, executable, port) {
    const startTicks = fs.readFileSync(`/proc/${pid}/stat`, 'utf8')
        .split(') ').pop().trim().split(/\s+/)[19];
    const actual = fs.realpathSync(`/proc/${pid}/exe`);
    if (actual !== fs.realpathSync(executable)) fail('live browser executable differs');
    const executableHash = hash(fs.readFileSync(`/proc/${pid}/exe`));
    const sockets = fs.readdirSync(`/proc/${pid}/fd`).map(fd => {
        try { return fs.readlinkSync(`/proc/${pid}/fd/${fd}`); }
        catch (_) { return ''; }
    });
    const hex = port.toString(16).toUpperCase().padStart(4, '0');
    let owned = false;
    for (const table of ['/proc/net/tcp', '/proc/net/tcp6']) {
        for (const line of fs.readFileSync(table, 'utf8').split('\n').slice(1)) {
            const fields = line.trim().split(/\s+/);
            if (fields.length >= 10 && fields[1].endsWith(`:${hex}`) && fields[3] === '0A' &&
                    sockets.includes(`socket:[${fields[9]}]`)) owned = true;
        }
    }
    if (!owned) fail('CDP listening socket does not belong to live browser PID');
    return {sha256: executableHash, startTicks};
}
class Cdp {
    constructor(url) {
        this.socket = new WebSocket(url);
        this.sequence = 0;
        this.pending = new Map();
        this.onEvent = () => {};
        this.ready = new Promise((resolve, reject) => {
            const timer = setTimeout(() => reject(new Error('CDP connection timed out')), 10000);
            this.socket.onopen = () => { clearTimeout(timer); resolve(); };
            this.socket.onerror = () => {
                clearTimeout(timer);
                reject(new Error('CDP connection failed'));
            };
        });
        this.socket.onmessage = event => {
            let message;
            try { message = JSON.parse(event.data); }
            catch (_) { return; }
            if (message.id !== undefined) {
                const waiting = this.pending.get(message.id);
                if (waiting) {
                    this.pending.delete(message.id);
                    message.error ? waiting.reject(new Error(JSON.stringify(message.error))) :
                        waiting.resolve(message.result);
                }
            } else this.onEvent(message);
        };
        this.socket.onclose = () => {
            for (const waiting of this.pending.values()) {
                clearTimeout(waiting.timer);
                waiting.reject(new Error('CDP closed'));
            }
            this.pending.clear();
        };
    }
    async send(method, params = {}) {
        await this.ready;
        const id = ++this.sequence;
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => {
                this.pending.delete(id);
                reject(new Error(`CDP ${method} timed out`));
            }, 10000);
            this.pending.set(id, {resolve: value => { clearTimeout(timer); resolve(value); },
                reject: error => { clearTimeout(timer); reject(error); }, timer});
            this.socket.send(JSON.stringify({id, method, params}));
        });
    }
    close() { this.socket.close(); }
}
function selected(url, port, moduleName, target) {
    const address = new URL(url);
    if (address.protocol !== 'http:' || !['localhost', '127.0.0.1'].includes(address.hostname) ||
            +address.port !== port) return null;
    const name = path.posix.basename(address.pathname);
    const packageName = `dyn4k-full-staged-browser-consumer-${moduleName}-test`;
    const asset = new Set([`${packageName}.mjs`, `${packageName}.wasm`,
        `${packageName}.import-object.mjs`, `${packageName}.js-builtins.mjs`,
        'custom-formatters.js']);
    if (!(address.pathname.includes('/_karma_webpack_') &&
            (name.endsWith('.js') || name.endsWith('.wasm')) ||
            target === 'wasmJs' && asset.has(name))) return null;
    return address.pathname + address.search;
}
function clock(request, later) {
    if (![request.wallTime, request.timestamp, later.timestamp].every(Number.isFinite) ||
            later.timestamp < request.timestamp) fail('CDP common clock differs');
    return Math.round((request.wallTime + later.timestamp - request.timestamp) * 1e9);
}
async function main(argv) {
    const config = options(argv);
    const pid = +config.pid;
    const port = +config['cdp-port'];
    const karma = +config['karma-port'];
    const process = processIdentity(pid, config.browser, port);
    const started = now();
    const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
    const browser = new Cdp(version.webSocketDebuggerUrl);
    const info = await browser.send('SystemInfo.getProcessInfo');
    if (info.processInfo.filter(item => item.type === 'browser' && item.id === pid).length !== 1)
        fail('CDP browser PID differs from observed process');
    const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    const pages = targets.filter(item => item.type === 'page' && item.url === 'about:blank');
    if (pages.length !== 1) fail('observer missed the blank browser target');
    const page = new Cdp(pages[0].webSocketDebuggerUrl);
    const requests = new Map();
    const responses = new Map();
    const pending = new Set();
    let error = null;
    page.onEvent = message => {
        const event = message.params;
        const id = event?.requestId;
        if (message.method === 'Network.requestWillBeSent') {
            const url = selected(event.request.url, karma, config.module, config.target);
            if (url) {
                if (requests.has(id)) error = 'duplicate CDP request ID';
                requests.set(id, {url, request: event});
            }
        } else if (message.method === 'Network.responseReceived' && requests.has(id)) {
            const item = requests.get(id);
            item.response = event;
            item.responseObservedNs = now();
        } else if (message.method === 'Network.loadingFinished' && requests.has(id)) {
            const item = requests.get(id);
            const finishedObservedNs = now();
            if (!item.response) { error = 'CDP body completed without response'; return; }
            const task = page.send('Network.getResponseBody', {requestId: id}).then(body => {
                const bytes = body.base64Encoded ? Buffer.from(body.body, 'base64') :
                    Buffer.from(body.body, 'utf8');
                const response = item.response.response;
                if (!bytes.length || bytes.length > 64 * 1024 * 1024 ||
                        response.status !== 200 || response.fromDiskCache ||
                        response.fromServiceWorker || responses.has(item.url)) {
                    error = 'CDP response body or URL differs'; return;
                }
                responses.set(item.url, {url: item.url, body_sha256: hash(bytes),
                    size: bytes.length, request_ns: clock(item.request, item.request),
                    response_ns: item.responseObservedNs,
                    finished_ns: finishedObservedNs});
            }).catch(reason => { error = `CDP body query failed: ${reason}`; });
            pending.add(task);
            task.finally(() => pending.delete(task));
        } else if (message.method === 'Network.loadingFailed' && requests.has(id)) {
            error = 'selected CDP request failed';
        }
    };
    await page.send('Network.enable', {maxTotalBufferSize: 128 * 1024 * 1024,
        maxResourceBufferSize: 64 * 1024 * 1024});
    fs.writeFileSync(config['ready-file'], JSON.stringify({pid, started_ns: started}) + '\n',
        {mode: 0o600, flag: 'wx'});
    const deadline = Date.now() + +config['timeout-ms'];
    while (!fs.existsSync(config['stop-file']) && Date.now() < deadline && !error) {
        await new Promise(resolve => setTimeout(resolve, 20));
    }
    await Promise.allSettled([...pending]);
    const finished = now();
    if (!fs.existsSync(config['stop-file']) || error ||
            responses.size < (config.target === 'wasmJs' ? 3 : 2) ||
            responses.size !== requests.size) fail(error || 'independent CDP capture incomplete');
    const finalProcess = processIdentity(pid, config.browser, port);
    if (finalProcess.sha256 !== process.sha256 ||
            finalProcess.startTicks !== process.startTicks)
        fail('live browser process identity changed during observation');
    const result = {protocol: 'cdp', clock: 'unix-epoch-ns', browser_pid: pid,
        browser_sha256: process.sha256, started_ns: started, finished_ns: finished,
        responses: [...responses.values()]};
    const temporary = `${config.output}.writing`;
    fs.writeFileSync(temporary, JSON.stringify(result) + '\n', {mode: 0o600, flag: 'wx'});
    fs.renameSync(temporary, config.output);
    page.close();
    browser.close();
}
if (require.main === module) main(process.argv.slice(2)).catch(error => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
});
module.exports = {options, selected, clock, processIdentity};
