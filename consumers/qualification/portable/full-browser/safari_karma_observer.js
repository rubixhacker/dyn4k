const safariFs = require('node:fs');
const safariCrypto = require('node:crypto');
const safariPath = require('node:path');
const safariPort = Number(process.env.DYN4K_BROWSER_KARMA_PORT);
const safariToken = process.env.DYN4K_BROWSER_TOKEN;
const safariFolder = process.env.DYN4K_SAFARI_OBSERVER_ARCHIVE;
const safariWorker = safariFs.readFileSync(process.env.DYN4K_SAFARI_WORKER_SOURCE);
const safariBootstrap = safariFs.readFileSync(process.env.DYN4K_SAFARI_BOOTSTRAP_SOURCE);
const safariEvents = safariPath.join(safariFolder, 'safari-worker-events.jsonl');
const safariErrors = safariPath.join(safariFolder, 'safari-worker-errors.jsonl');
const safariBodies = safariPath.join(safariFolder, 'safari-browser-bodies');
const safariSourceRecord = safariPath.join(safariFolder, 'safari-worker-source.json');
const safariKey = 'middleware:qualification-safari-observer';
if (!Number.isInteger(safariPort) || safariPort < 1 || safariPort > 65535 ||
        !/^[0-9a-f]{64}$/.test(safariToken) ||
        config.plugins.some(item => Object.prototype.hasOwnProperty.call(item, safariKey)) ||
        JSON.stringify(config.beforeMiddleware) !== JSON.stringify(['qualification-response'])) {
    throw new Error('Safari witness Karma configuration differs');
}
safariFs.mkdirSync(safariBodies, {recursive: false});
safariFs.writeFileSync(safariEvents, '', {flag: 'wx', mode: 0o600});
safariFs.writeFileSync(safariErrors, '', {flag: 'wx', mode: 0o600});
const safariSourceHashes = {
    observer_sha256: safariCrypto.createHash('sha256').update(
        safariFs.readFileSync(process.env.DYN4K_SAFARI_OBSERVER_SOURCE)).digest('hex'),
    worker_sha256: safariCrypto.createHash('sha256').update(safariWorker).digest('hex'),
    bootstrap_sha256: safariCrypto.createHash('sha256').update(safariBootstrap).digest('hex'),
    node_pid: process.pid, token: safariToken, port: safariPort
};
safariFs.writeFileSync(safariSourceRecord, JSON.stringify(safariSourceHashes) + '\n',
    {flag: 'wx', mode: 0o600});
const safariUsedIds = new Set();
let safariOrdinal = 0;
function safariHash(bytes) {
    return safariCrypto.createHash('sha256').update(bytes).digest('hex');
}
function safariAppend(row) {
    safariFs.appendFileSync(safariEvents, JSON.stringify(row) + '\n');
}
function safariReply(response, status, contentType, body) {
    response.writeHead(status, {'Content-Type': contentType, 'Cache-Control': 'no-store'});
    response.end(body);
}
function safariObserver() {
    return function(request, response, next) {
        const address = new URL(request.url, 'http://localhost:' + safariPort);
        if (!address.pathname.startsWith('/__dyn4k_')) return next();
        if (address.pathname === '/__dyn4k_bootstrap' && request.method === 'GET' &&
                address.searchParams.get('token') === safariToken) {
            const target = address.searchParams.get('target');
            const targetUrl = target && new URL(target);
            if (!targetUrl || targetUrl.origin !== 'http://localhost:' + safariPort) {
                return safariReply(response, 400, 'text/plain', 'target differs');
            }
            return safariReply(response, 200, 'text/html',
                '<!doctype html><meta charset="utf-8"><body>' +
                '<script src="/__dyn4k_bootstrap.js"></script></body>');
        }
        if (address.pathname === '/__dyn4k_bootstrap.js' && request.method === 'GET') {
            return safariReply(response, 200, 'text/javascript', safariBootstrap);
        }
        if (address.pathname === '/__dyn4k_sw.js' && request.method === 'GET' &&
                address.searchParams.get('token') === safariToken) {
            return safariReply(response, 200, 'text/javascript', safariWorker);
        }
        if (!['/__dyn4k_record', '/__dyn4k_control', '/__dyn4k_error'].includes(
                address.pathname) || request.method !== 'POST') {
            return safariReply(response, 404, 'text/plain', 'unknown witness route');
        }
        const chunks = [];
        let size = 0;
        request.on('data', chunk => {
            size += chunk.length;
            if (size > 64 * 1024 * 1024) request.destroy();
            else chunks.push(chunk);
        });
        request.on('end', () => {
            try {
                const bytes = Buffer.concat(chunks);
                if (address.pathname === '/__dyn4k_error') {
                    const failure = JSON.parse(bytes.toString('utf8'));
                    if (failure.token !== safariToken || typeof failure.error !== 'string' ||
                            typeof failure.url !== 'string') {
                        throw new Error('Safari worker error record differs');
                    }
                    safariFs.appendFileSync(safariErrors, JSON.stringify(failure) + '\n');
                } else if (address.pathname === '/__dyn4k_control') {
                    const control = JSON.parse(bytes.toString('utf8'));
                    if (control.token !== safariToken || !control.client_id ||
                            !control.target || !control.bootstrap_url ||
                            new URL(control.target).origin !== 'http://localhost:' + safariPort) {
                        throw new Error('Safari control differs');
                    }
                    safariAppend({kind: 'control', ...control, observed_ns: Date.now() * 1000000});
                } else {
                    const metadata = JSON.parse(request.headers['x-dyn4k-metadata']);
                    if (metadata.token !== safariToken || !metadata.request_id ||
                            safariUsedIds.has(metadata.request_id) ||
                            !['navigation', 'response'].includes(metadata.kind) ||
                            (metadata.kind === 'navigation' && bytes.length !== 0) ||
                            (metadata.kind === 'response' && bytes.length === 0)) {
                        throw new Error('Safari worker event differs');
                    }
                    safariUsedIds.add(metadata.request_id);
                    const body_path = metadata.kind === 'response'
                        ? 'safari-browser-bodies/' + String(safariOrdinal++).padStart(4, '0') + '.body'
                        : null;
                    if (body_path) {
                        safariFs.writeFileSync(safariPath.join(safariFolder, body_path), bytes,
                            {flag: 'wx', mode: 0o600});
                    }
                    safariAppend({...metadata, body_path, body_size: bytes.length,
                        body_sha256: safariHash(bytes), observed_ns: Date.now() * 1000000});
                }
                safariReply(response, 204, 'text/plain', '');
            } catch (error) {
                safariReply(response, 400, 'text/plain', String(error));
            }
        });
    };
}
safariObserver.$inject = [];
config.plugins.push({[safariKey]: ['factory', safariObserver]});
config.set({beforeMiddleware: ['qualification-response', 'qualification-safari-observer']});
