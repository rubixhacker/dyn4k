#!/usr/bin/env node
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const crypto = require('node:crypto');
const {spawn} = require('node:child_process');

const archive = process.env.DYN4K_BROWSER_BIDI_ARCHIVE;
const launcher = process.env.DYN4K_BROWSER_ORIGINAL_LAUNCHER;
const moduleName = process.env.DYN4K_BROWSER_MODULE;
const target = process.env.DYN4K_BROWSER_TARGET;
const candidate = process.env.DYN4K_BROWSER_CANDIDATE;
const args = process.argv.slice(2);
const urls = args.filter(arg => /^http:\/\/[^/]+\/\?id=/.test(arg));
if (require.main === module && (!archive || !launcher || !['core', 'facade'].includes(moduleName) ||
        !['js', 'wasmJs'].includes(target) || !/^[0-9a-f]{40}$/.test(candidate) ||
        urls.length !== 1)) throw new Error('Firefox witness launch contract differs');

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
            if (fields.length >= 10 && fields[1].endsWith(`:${hexPort}`) &&
                    fields[3] === '0A' && sockets.includes(`socket:[${fields[9]}]`)) {
                return fields[9];
            }
        }
    }
    throw new Error('BiDi listening socket does not belong to Firefox PID');
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
class Bidi {
    constructor(url, Socket = WebSocket, deadlineMs = 15000) {
        this.socket = new Socket(url);
        this.sequence = 0;
        this.pending = new Map();
        this.onEvent = () => {};
        this.failure = null;
        this.connected = false;
        this.ready = new Promise((resolve, reject) => {
            this.readyResolve = resolve;
            this.readyReject = reject;
        });
        this.ready.catch(() => {});
        this.openTimer = setTimeout(() => this.fail(new Error('BiDi connection timed out')),
            deadlineMs);
        this.socket.onopen = () => {
            if (this.failure) return;
            clearTimeout(this.openTimer);
            this.connected = true;
            this.readyResolve();
        };
        this.socket.onclose = () => this.fail(new Error('BiDi WebSocket closed'));
        this.socket.onerror = event => this.fail(event?.error || new Error('BiDi WebSocket error'));
        this.socket.onmessage = event => {
            let message;
            try { message = JSON.parse(event.data); }
            catch (error) { this.fail(error); return; }
            if (message.type === 'event') {
                this.onEvent(message);
            } else if (message.id !== undefined) {
                const waiter = this.pending.get(message.id);
                if (!waiter) return;
                this.pending.delete(message.id);
                clearTimeout(waiter.timer);
                message.type === 'error'
                    ? waiter.reject(new Error(JSON.stringify(message)))
                    : waiter.resolve(message.result);
            }
        };
        this.deadlineMs = deadlineMs;
    }
    fail(error) {
        if (this.failure) return;
        this.failure = error;
        clearTimeout(this.openTimer);
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
                reject(new Error(`BiDi ${method} timed out`));
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
        this.fail(new Error('BiDi WebSocket closed'));
        try { this.socket.close(); } catch (_) {}
    }
}
async function connect(port, deadlineMs = 15000, Socket = WebSocket) {
    const deadline = Date.now() + deadlineMs;
    while (Date.now() < deadline) {
        const client = new Bidi(`ws://127.0.0.1:${port}/session`, Socket,
            Math.min(1000, deadline - Date.now()));
        try {
            await client.ready;
            return client;
        } catch (_) {
            client.close();
            await delay(Math.min(25, Math.max(0, deadline - Date.now())));
        }
    }
    throw new Error('Firefox BiDi endpoint did not appear');
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
function bodyBytes(value) {
    if (!value || typeof value.value !== 'string') throw new Error('BiDi body value is absent');
    if (value.type === 'string') return Buffer.from(value.value, 'utf8');
    if (value.type === 'base64') return Buffer.from(value.value, 'base64');
    throw new Error('BiDi body encoding differs');
}

async function main() {
    const port = await reservePort();
    const profile = fs.mkdtempSync(path.join(process.env.DYN4K_BROWSER_TMPDIR || os.tmpdir(),
        'dyn4k-bidi-'));
    const browserArgs = args.filter(arg => arg !== urls[0] &&
        !arg.startsWith('--remote-debugging-port') &&
        arg !== '--profile' && arg !== profile);
    browserArgs.push(`--remote-debugging-port=${port}`, '--no-remote',
        '--profile', profile, 'about:blank');
    const child = spawn(launcher, browserArgs, {env: process.env, stdio: 'inherit'});
    const finished = new Promise(resolve => child.once('exit',
        (code, signal) => resolve({code, signal})));
    const requests = new Map();
    const seenUrls = new Set();
    const responses = [];
    const pendingBodies = new Set();
    const contexts = [];
    const minimumResponses = target === 'wasmJs' ? 3 : 2;
    let client;
    let session;
    let failure = null;
    let stopSignal = null;
    let stopTimer = null;
    const overall = setTimeout(() => {
        failure = failure || 'Firefox BiDi capture timed out';
        child.kill('SIGTERM');
    }, 120000);
    function stopWhenCaptured() {
        if (stopSignal && requests.size >= minimumResponses &&
                responses.filter(Boolean).length === requests.size) {
            if (stopTimer) clearTimeout(stopTimer);
            child.kill(stopSignal);
        }
    }
    function persist() {
        if (!session) return;
        const temporary = `${archive}.writing`;
        fs.writeFileSync(temporary, [session, ...responses.filter(Boolean)]
            .map(value => JSON.stringify(value)).join('\n') + '\n', {mode: 0o600});
        fs.renameSync(temporary, archive);
    }
    for (const signal of ['SIGTERM', 'SIGINT']) {
        process.on(signal, () => {
            if (stopSignal) return;
            stopSignal = signal;
            stopTimer = setTimeout(() => {
                failure = failure || 'BiDi selected bodies did not finish before shutdown';
                child.kill(signal);
            }, 5000);
            stopWhenCaptured();
        });
    }
    try {
        client = await connect(port);
        const created = await client.send('session.new', {capabilities: {alwaysMatch: {}}});
        if (created?.capabilities?.['moz:processID'] !== child.pid ||
                created.capabilities.browserName !== 'firefox') {
            throw new Error('BiDi browser PID differs from selected Firefox process');
        }
        const socketInode = listeningSocketInode(child.pid, port);
        const collector = await client.send('network.addDataCollector',
            {dataTypes: ['response'], maxEncodedDataSize: 128 * 1024 * 1024});
        if (!collector?.collector) throw new Error('BiDi response collector is absent');
        client.onEvent = message => {
            if (message.method === 'browsingContext.contextCreated') {
                contexts.push({observed_ns: now(), params: message.params});
            }
        };
        await client.send('session.subscribe', {events: [
            'network.beforeRequestSent', 'network.responseCompleted', 'network.fetchError',
            'browsingContext.contextCreated']});
        await client.send('network.setCacheBehavior', {cacheBehavior: 'bypass'});
        const context = await client.send('browsingContext.create', {type: 'tab'});
        if (!context?.context) throw new Error('BiDi browser context is absent');
        session = {kind: 'session', protocol: 1, module: moduleName, target,
            candidate_sha: candidate, browser_pid: child.pid,
            bidi_browser_pid: created.capabilities['moz:processID'],
            context_id: context.context, session_id: created.sessionId,
            collector_id: collector.collector, started_ns: now(),
            bidi_port: port, bidi_socket_inode: socketInode,
            contexts,
            source_path: fs.realpathSync(__filename),
            source_sha256: hash(fs.readFileSync(__filename))};
        client.onEvent = message => {
            const event = message.params;
            if (message.method === 'browsingContext.contextCreated') {
                contexts.push({observed_ns: now(), params: event});
                persist();
            } else if (message.method === 'network.beforeRequestSent' &&
                    selected(event.request.url)) {
                const id = event.request.request;
                if (requests.has(id) || seenUrls.has(event.request.url)) {
                    failure = 'duplicate selected BiDi request';
                    return;
                }
                seenUrls.add(event.request.url);
                requests.set(id, {ordinal: requests.size, request: event,
                    request_ns: now()});
            } else if (message.method === 'network.responseCompleted' &&
                    selected(event.response.url)) {
                const id = event.request.request;
                const item = requests.get(id);
                if (!item || item.response) {
                    failure = 'BiDi response has no unique request';
                    return;
                }
                item.response = event;
                item.response_ns = now();
                const bodyPromise = client.send('network.getData',
                    {request: id, dataType: 'response', collector: session.collector_id,
                        disown: true}).then(result => {
                    const bytes = bodyBytes(result.bytes);
                    if (bytes.length === 0 || bytes.length > 64 * 1024 * 1024) {
                        failure = 'BiDi selected body size differs';
                        return;
                    }
                    const relative = `firefox-bodies/${String(item.ordinal).padStart(4, '0')}.body`;
                    fs.mkdirSync(path.dirname(path.join(path.dirname(archive), relative)),
                        {recursive: true});
                    fs.writeFileSync(path.join(path.dirname(archive), relative), bytes,
                        {flag: 'wx', mode: 0o600});
                    responses[item.ordinal] = {kind: 'response', ordinal: item.ordinal,
                        request_id: id, context_id: event.context,
                        browser_pid: child.pid, url: event.response.url,
                        method: item.request.request.method,
                        status: event.response.status,
                        mime_type: event.response.mimeType,
                        from_cache: event.response.fromCache,
                        request_ns: item.request_ns, response_ns: item.response_ns,
                        finished_ns: now(), body_path: relative,
                        body_size: bytes.length, body_sha256: hash(bytes),
                        events: {request: item.request, response: event}};
                    persist();
                    stopWhenCaptured();
                }).catch(error => { failure = `BiDi body query failed: ${error}`; });
                pendingBodies.add(bodyPromise);
                bodyPromise.finally(() => pendingBodies.delete(bodyPromise));
            } else if (message.method === 'network.fetchError' &&
                    requests.has(event.request.request)) {
                failure = 'selected BiDi request failed';
            }
        };
        persist();
        await client.send('browsingContext.navigate',
            {context: context.context, url: urls[0], wait: 'none'});
        const result = await finished;
        await Promise.allSettled([...pendingBodies]);
        persist();
        if (requests.size < minimumResponses ||
                responses.filter(Boolean).length !== requests.size) {
            failure = failure || 'BiDi selected response transcript is incomplete';
        }
        if (failure) throw new Error(failure);
        if (result.code !== 0 && result.signal !== 'SIGTERM') {
            throw new Error(`Firefox exited ${result.code ?? result.signal}`);
        }
    } finally {
        clearTimeout(overall);
        if (stopTimer) clearTimeout(stopTimer);
        if (session && (failure || responses.filter(Boolean).length !== requests.size)) {
            fs.writeFileSync(`${archive}.rejected`, JSON.stringify({failure,
                requests: [...requests].map(([id, item]) => ({id,
                    ordinal: item.ordinal, url: item.request.request.url,
                    has_response: Boolean(item.response),
                    has_body: Boolean(responses[item.ordinal])}))}) + '\n',
            {mode: 0o600});
        }
        if (client) client.close();
        if (child.exitCode === null) child.kill('SIGTERM');
        if (!failure) fs.rmSync(profile, {recursive: true, force: true});
    }
}
if (require.main === module) {
    main().catch(error => {
        console.error(`Firefox process witness: ${error.stack || error}`);
        process.exitCode = 1;
    });
}
module.exports = {Bidi, connect, bodyBytes};
