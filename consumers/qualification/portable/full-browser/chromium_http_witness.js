#!/usr/bin/env node
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const crypto = require('node:crypto');
const {spawn} = require('node:child_process');

const archive = process.env.DYN4K_BROWSER_CDP_ARCHIVE;
const launcher = process.env.DYN4K_BROWSER_ORIGINAL_LAUNCHER;
const moduleName = process.env.DYN4K_BROWSER_MODULE;
const target = process.env.DYN4K_BROWSER_TARGET;
const candidate = process.env.DYN4K_BROWSER_CANDIDATE;
const args = process.argv.slice(2);
const urls = args.filter(arg => /^http:\/\/[^/]+\/\?id=/.test(arg));
if (require.main === module && (!archive || !launcher || !['core', 'facade'].includes(moduleName) ||
        !['js', 'wasmJs'].includes(target) || !/^[0-9a-f]{40}$/.test(candidate) ||
        urls.length !== 1)) throw new Error('Chromium witness launch contract differs');

function now() { return Date.now() * 1000000; }
function hash(bytes) { return crypto.createHash('sha256').update(bytes).digest('hex'); }
function delay(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
function listeningSocketInode(pid, port) {
    const hexPort = port.toString(16).toUpperCase().padStart(4, '0');
    const sockets = fs.readdirSync(`/proc/${pid}/fd`).map(fd => {
        try { return fs.readlinkSync(`/proc/${pid}/fd/${fd}`); }
        catch (_) { return ''; }
    });
    for (const table of ['/proc/net/tcp', '/proc/net/tcp6']) {
        for (const line of fs.readFileSync(table, 'utf8').split('\n').slice(1)) {
            const fields = line.trim().split(/\s+/);
            if (fields.length < 10 || !fields[1].endsWith(`:${hexPort}`) ||
                    fields[3] !== '0A') continue;
            if (sockets.includes(`socket:[${fields[9]}]`)) return fields[9];
        }
    }
    throw new Error('CDP listening socket does not belong to Chromium PID');
}
function reservePort() {
    return new Promise((resolve, reject) => {
        const server = net.createServer();
        server.once('error', reject);
        server.listen(0, '127.0.0.1', () => {
            const port = server.address().port;
            server.close(() => resolve(port));
        });
    });
}
class Cdp {
    constructor(url, Socket = WebSocket, deadlineMs = 15000) {
        this.socket = new Socket(url);
        this.sequence = 0;
        this.pending = new Map();
        this.onEvent = () => {};
        this.deadlineMs = deadlineMs;
        this.connected = false;
        this.failure = null;
        this.ready = new Promise((resolve, reject) => {
            this.readyResolve = resolve;
            this.readyReject = reject;
        });
        this.ready.catch(() => {});
        this.connectionTimer = setTimeout(() => {
            this.fail(new Error('CDP connection timed out'));
            try { this.socket.close(); } catch (_) {}
        }, deadlineMs);
        this.socket.onopen = () => {
            if (this.failure) return;
            clearTimeout(this.connectionTimer);
            this.connected = true;
            this.readyResolve();
        };
        this.socket.onclose = () => this.fail(new Error('CDP WebSocket closed'));
        this.socket.onerror = event => this.fail(event instanceof Error ? event :
            event?.error instanceof Error ? event.error : new Error('CDP WebSocket error'));
        this.socket.onmessage = event => {
            let message;
            try { message = JSON.parse(event.data); }
            catch (error) { this.fail(error); return; }
            if (message.id !== undefined) {
                const waiter = this.pending.get(message.id);
                if (waiter) {
                    this.pending.delete(message.id);
                    clearTimeout(waiter.timer);
                    message.error ? waiter.reject(new Error(JSON.stringify(message.error)))
                        : waiter.resolve(message.result);
                }
            } else this.onEvent(message);
        };
    }
    fail(error) {
        if (this.failure) return;
        this.failure = error;
        clearTimeout(this.connectionTimer);
        if (!this.connected) this.readyReject(error);
        for (const waiter of this.pending.values()) {
            clearTimeout(waiter.timer);
            waiter.reject(error);
        }
        this.pending.clear();
    }
    async send(method, params = {}) {
        await this.ready;
        if (this.failure) throw this.failure;
        const id = ++this.sequence;
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => {
                this.pending.delete(id);
                reject(new Error(`CDP ${method} timed out`));
            }, this.deadlineMs);
            this.pending.set(id, {resolve, reject, timer});
            try { this.socket.send(JSON.stringify({id, method, params})); }
            catch (error) {
                clearTimeout(timer);
                this.pending.delete(id);
                reject(error);
            }
        });
    }
    close() {
        this.fail(new Error('CDP WebSocket closed'));
        try { this.socket.close(); } catch (_) {}
    }
}

async function endpoint(port, route, fetcher = fetch, timeoutMs = 15000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        const remaining = deadline - Date.now();
        const controller = new AbortController();
        let timer;
        const expired = new Promise((resolve, reject) => {
            timer = setTimeout(() => {
                controller.abort();
                reject(new Error('Chromium CDP discovery request timed out'));
            }, remaining);
        });
        try {
            const response = await Promise.race([
                fetcher(`http://127.0.0.1:${port}${route}`, {signal: controller.signal}),
                expired]);
            if (response.ok) return await Promise.race([response.json(), expired]);
        } catch (_) {
        } finally {
            clearTimeout(timer);
        }
        const pause = Math.min(25, deadline - Date.now());
        if (pause > 0) await delay(pause);
    }
    throw new Error(`Chromium CDP endpoint ${route} did not appear`);
}

function selected(url) {
    const parsed = new URL(url);
    const name = path.posix.basename(parsed.pathname);
    const packageName = `dyn4k-full-staged-browser-consumer-${moduleName}-test`;
    const assets = new Set([`${packageName}.mjs`, `${packageName}.wasm`,
        `${packageName}.import-object.mjs`, `${packageName}.js-builtins.mjs`,
        'custom-formatters.js']);
    return parsed.pathname.includes('/_karma_webpack_') &&
        (name.endsWith('.js') || name.endsWith('.wasm')) ||
        target === 'wasmJs' && assets.has(name);
}

async function main() {
    const port = await reservePort();
    const profile = fs.mkdtempSync(path.join(process.env.DYN4K_BROWSER_TMPDIR || os.tmpdir(),
        'dyn4k-cdp-'));
    const browserArgs = args.filter(arg => arg !== urls[0] &&
        !arg.startsWith('--remote-debugging-port=') &&
        !arg.startsWith('--user-data-dir='));
    browserArgs.push(`--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
        '--no-first-run', 'about:blank');
    const child = spawn(launcher, browserArgs, {env: process.env, stdio: 'inherit'});
    const finished = new Promise(resolve => child.once('exit', (code, signal) => resolve({code, signal})));
    let page;
    let browser;
    let session;
    const requests = new Map();
    const responses = [];
    const pendingBodies = new Set();
    let failure = null;
    let stopSignal = null;
    let stopTimer = null;
    const minimumResponses = target === 'wasmJs' ? 3 : 2;
    function stopWhenCaptured() {
        if (stopSignal && requests.size >= minimumResponses &&
                responses.filter(Boolean).length === requests.size) {
            if (stopTimer) clearTimeout(stopTimer);
            child.kill(stopSignal);
        }
    }
    function persist() {
        if (!session) return;
        const complete = responses.filter(Boolean);
        const temporary = `${archive}.writing`;
        fs.writeFileSync(temporary, [session, ...complete].map(value =>
            JSON.stringify(value)).join('\n') + '\n', {mode: 0o600});
        fs.renameSync(temporary, archive);
    }
    for (const signal of ['SIGTERM', 'SIGINT']) {
        process.on(signal, () => {
            if (stopSignal) return;
            stopSignal = signal;
            stopTimer = setTimeout(() => {
                failure = failure || 'CDP selected bodies did not finish before browser shutdown';
                child.kill(signal);
            }, 5000);
            stopWhenCaptured();
        });
    }
    try {
        const version = await endpoint(port, '/json/version');
        browser = new Cdp(version.webSocketDebuggerUrl);
        const info = await browser.send('SystemInfo.getProcessInfo');
        const browserProcesses = info.processInfo.filter(item => item.type === 'browser');
        if (browserProcesses.length !== 1 || browserProcesses[0].id !== child.pid) {
            throw new Error('CDP browser PID differs from launched Chromium process');
        }
        const targets = await endpoint(port, '/json/list');
        const pages = targets.filter(item => item.type === 'page' && item.url === 'about:blank');
        if (pages.length !== 1) throw new Error('CDP initial page target differs');
        page = new Cdp(pages[0].webSocketDebuggerUrl);
        session = {kind: 'session', protocol: 1, module: moduleName, target,
            candidate_sha: candidate, browser_pid: child.pid,
            cdp_browser_pid: browserProcesses[0].id, target_id: pages[0].id,
            started_ns: now(), devtools_port: port,
            devtools_socket_inode: listeningSocketInode(child.pid, port),
            source_path: fs.realpathSync(__filename),
            source_sha256: hash(fs.readFileSync(__filename))};
        page.onEvent = message => {
            const event = message.params;
            if (message.method === 'Network.requestWillBeSent' &&
                    selected(event.request.url)) {
                if (requests.has(event.requestId)) failure = 'duplicate CDP request ID';
                requests.set(event.requestId, {ordinal: requests.size, request: event,
                    request_ns: now()});
            } else if (message.method === 'Network.responseReceived' &&
                    requests.has(event.requestId)) {
                const item = requests.get(event.requestId);
                item.response = event;
                item.response_ns = now();
            } else if (message.method === 'Network.loadingFinished' &&
                    requests.has(event.requestId)) {
                const item = requests.get(event.requestId);
                const finishNs = now();
                if (!item.response) {
                    failure = 'CDP loading finished without response';
                    return;
                }
                const bodyPromise = page.send('Network.getResponseBody',
                    {requestId: event.requestId}).then(result => {
                    const bytes = result.base64Encoded
                        ? Buffer.from(result.body, 'base64') : Buffer.from(result.body, 'utf8');
                    if (bytes.length === 0 || bytes.length > 64 * 1024 * 1024) {
                        failure = 'CDP response body size differs';
                        return;
                    }
                    const response = item.response.response;
                    responses[item.ordinal] = {kind: 'response', ordinal: item.ordinal,
                        request_id: event.requestId, target_id: session.target_id,
                        browser_pid: child.pid, url: response.url,
                        method: item.request.request.method, status: response.status,
                        mime_type: response.mimeType,
                        from_disk_cache: response.fromDiskCache || false,
                        from_service_worker: response.fromServiceWorker || false,
                        request_ns: item.request_ns, response_ns: item.response_ns,
                        finished_ns: finishNs, body_size: bytes.length,
                        body_sha256: hash(bytes),
                        events: {request: item.request, response: item.response,
                            finish: event}};
                    persist();
                    stopWhenCaptured();
                }).catch(error => { failure = `CDP body query failed: ${error}`; });
                pendingBodies.add(bodyPromise);
                bodyPromise.finally(() => pendingBodies.delete(bodyPromise));
            } else if (message.method === 'Network.loadingFailed' &&
                    requests.has(event.requestId)) failure = 'selected CDP request failed';
        };
        await page.send('Network.enable', {maxTotalBufferSize: 128 * 1024 * 1024,
            maxResourceBufferSize: 64 * 1024 * 1024});
        await page.send('Page.enable');
        persist();
        await page.send('Page.navigate', {url: urls[0]});
        const result = await finished;
        await Promise.allSettled([...pendingBodies]);
        persist();
        if (requests.size < minimumResponses ||
                responses.filter(Boolean).length !== requests.size)
            failure = failure || 'CDP selected response transcript is incomplete';
        if (failure) throw new Error(failure);
        if (result.code !== 0 && result.signal !== 'SIGTERM')
            throw new Error(`Chromium exited ${result.code ?? result.signal}`);
    } finally {
        if (stopTimer) clearTimeout(stopTimer);
        if (session && (failure || responses.filter(Boolean).length !== requests.size)) {
            fs.writeFileSync(`${archive}.rejected`, JSON.stringify({failure,
                requests: [...requests].map(([id, item]) => ({id,
                    ordinal: item.ordinal, url: item.request.request.url,
                    has_response: Boolean(item.response),
                    has_body: Boolean(responses[item.ordinal])}))}) + '\n',
            {mode: 0o600});
        }
        if (page) page.close();
        if (browser) browser.close();
        if (child.exitCode === null) child.kill('SIGTERM');
        fs.rmSync(profile, {recursive: true, force: true});
    }
}
if (require.main === module) {
    main().catch(error => {
        console.error(`Chromium process witness: ${error.stack || error}`);
        process.exitCode = 1;
    });
}
module.exports = {Cdp, endpoint};
