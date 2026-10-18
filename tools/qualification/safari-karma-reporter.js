const DYN4K_SAFARI_REPORTER_NEWLINES = true;
const safariFs = require('node:fs');
const safariCrypto = require('node:crypto');
const reporterKey = 'reporter:karma-kotlin-reporter';
const producerPath = require.resolve('kotlin-web-helpers/dist/karma-kotlin-reporter');
const producerHash = safariCrypto.createHash('sha256')
    .update(safariFs.readFileSync(producerPath)).digest('hex');
if (producerHash !== '7c3232f60952aff254847ae62a866385735e3094197454d755100e962c2f2347') {
    throw new Error('Safari Kotlin reporter producer mismatch');
}
const producer = require(producerPath);
const providers = (config.plugins || []).filter(candidate =>
    candidate && Object.prototype.hasOwnProperty.call(candidate, reporterKey));
const plugin = providers[0];
if (providers.length !== 1 || !plugin || !Array.isArray(plugin[reporterKey]) ||
        plugin[reporterKey][0] !== 'type' ||
        typeof plugin[reporterKey][1] !== 'function') {
    throw new Error('Safari Kotlin reporter provider is missing');
}
const OriginalReporter = plugin[reporterKey][1];
if (!producer[reporterKey] || producer[reporterKey][1] !== OriginalReporter) {
    throw new Error('Safari Kotlin reporter provider mismatch');
}
const loadedProducerHash = safariCrypto.createHash('sha256')
    .update(Function.prototype.toString.call(OriginalReporter)).digest('hex');
if (loadedProducerHash !== '51b54a948f46db31ed64a1fd13f7d7cfe5aa8eabd6dc9886141f05c5384480d1') {
    throw new Error('Safari Kotlin reporter loaded producer mismatch');
}
function SafariLineReporter(baseReporterDecorator, karmaConfig, emitter) {
    OriginalReporter.call(this, baseReporterDecorator, karmaConfig, emitter);
    if (typeof this.write !== 'function') {
        throw new Error('Safari Kotlin reporter writer is missing');
    }
    this.write = function(message) {
        if (typeof message !== 'string' || Buffer.byteLength(message, 'utf8') > 262144) {
            throw new Error('Safari service message exceeds 262144 bytes');
        }
        const line = message.endsWith('\n') ? message.slice(0, -1) : message;
        if (line.startsWith('##teamcity[') && !line.endsWith(']')) {
            throw new Error('Safari service message is incomplete');
        }
        const bytes = Buffer.from(line + '\n', 'utf8');
        let written = 0;
        let stalled = 0;
        const retrySignal = new Int32Array(new SharedArrayBuffer(4));
        while (written < bytes.length) {
            let count;
            try {
                count = safariFs.writeSync(1, bytes, written, bytes.length - written);
            } catch (error) {
                if (error.code !== 'EINTR' && error.code !== 'EAGAIN') {
                    throw new Error('Safari service message write failed', {cause: error});
                }
                count = 0;
                if (error.code === 'EAGAIN') {
                    Atomics.wait(retrySignal, 0, 0, 5);
                }
            }
            if (!Number.isInteger(count) || count < 0 || count > bytes.length - written) {
                throw new Error('Safari service message write failed');
            }
            if (count === 0 && ++stalled > 100) {
                throw new Error('Safari service message write failed');
            }
            if (count > 0) {
                written += count;
                stalled = 0;
            }
        }
    };
    const traceDirectory = typeof process === 'object' && process.env &&
        process.env.DYN4K_SAFARI_EVENT_TRACE_DIR;
    if (traceDirectory) {
        const invocation = process.env.DYN4K_QUALIFICATION_INVOCATION;
        const packageName = String(karmaConfig.basePath || '').split(/[\\/]/).pop();
        const modules = Object.assign(Object.create(null), {
            'dyn4k-dyn4k-core-test': 'dyn4k-core',
            'dyn4k-dyn4k-test': 'dyn4k',
            'dyn4k-staged-portable-consumer-test': 'consumer'
        });
        const moduleName = modules[packageName];
        const directory = safariFs.lstatSync(traceDirectory);
        if (!moduleName || !/^[0-9a-f]{32}$/.test(invocation || '') ||
                directory.isSymbolicLink() || !directory.isDirectory() ||
                safariFs.realpathSync(traceDirectory) !== traceDirectory ||
                !safariFs.constants.O_NOFOLLOW) {
            throw new Error('Safari event trace source or destination is unsafe');
        }
        const tracePath = traceDirectory + '/' + moduleName + '-' + invocation + '-' +
            process.pid + '.jsonl';
        const descriptor = safariFs.openSync(tracePath,
            safariFs.constants.O_WRONLY | safariFs.constants.O_CREAT |
            safariFs.constants.O_EXCL | safariFs.constants.O_NOFOLLOW, 0o600);
        let records = 0;
        let bytes = 0;
        const counts = new Map();
        const trace = (event, browser, count, connection) => {
            const record = {event, invocation, module: moduleName, node_pid: process.pid,
                time_ms: Date.now()};
            if (browser) {
                record.browser = String(browser.id).slice(0, 64);
                record.name = String(browser.name).slice(0, 128);
            }
            if (count !== undefined) record.spec_count = count;
            if (connection) Object.assign(record, connection);
            const raw = Buffer.from(JSON.stringify(record) + '\n', 'utf8');
            if (++records > 512 || bytes + raw.length > 65536) {
                throw new Error('Safari event trace exceeds bound');
            }
            for (let offset = 0; offset < raw.length;) {
                const written = safariFs.writeSync(descriptor, raw, offset,
                    raw.length - offset);
                if (!Number.isInteger(written) || written <= 0 ||
                        written > raw.length - offset) {
                    throw new Error('Safari event trace write failed');
                }
                offset += written;
            }
            bytes += raw.length;
        };
        const socketHash = socket => {
            if (!socket || typeof socket.id !== 'string' ||
                    socket.id.length === 0 || socket.id.length > 128) {
                throw new Error('Safari socket identity is unsafe');
            }
            return safariCrypto.createHash('sha256').update(socket.id).digest('hex');
        };
        trace('reporter_init');
        const browserPath = require.resolve('karma/lib/browser');
        const serverPath = require.resolve('karma/lib/server');
        const browserModule = require.cache[browserPath];
        const serverModule = require.cache[serverPath];
        const Browser = require(browserPath);
        if (!browserModule || !serverModule ||
                !Array.isArray(serverModule.children) ||
                !serverModule.children.includes(browserModule) ||
                browserModule.exports !== Browser ||
                typeof Browser.prototype.reconnect !== 'function') {
            throw new Error('Safari Karma Browser module mismatch');
        }
        const browserHash = safariCrypto.createHash('sha256')
            .update(safariFs.readFileSync(browserPath)).digest('hex');
        if (browserHash !== '4805a14470bf3b9a523d5dd68275db24df6548a509e339dcad0f3c83f12d7962') {
            throw new Error('Safari Karma Browser source mismatch');
        }
        const originalReconnect = Browser.prototype.reconnect;
        const reconnectHash = safariCrypto.createHash('sha256')
            .update(Function.prototype.toString.call(originalReconnect)).digest('hex');
        if (reconnectHash !== '56cae9b2607b43decc815a7b5cb343d4aed5ce3760aad4fc5af02e5fa883e99b') {
            throw new Error('Safari Karma Browser reconnect implementation mismatch');
        }
        Browser.prototype.reconnect = function(newSocket, clientSaysReconnect) {
            const beforeState = this.state;
            const beforeSockets = this.activeSockets.length;
            const result = originalReconnect.apply(this, arguments);
            trace('socket_reconnect', this, counts.get(this.id) || 0, {
                before_state: beforeState,
                after_state: this.state,
                before_active_sockets: beforeSockets,
                after_active_sockets: this.activeSockets.length,
                client_says_reconnect: clientSaysReconnect === true,
                original_socket_sha256: socketHash(this.socket),
                socket_sha256: socketHash(newSocket)
            });
            return result;
        };
        trace('reconnect_hook_installed', null, undefined,
            {karma_browser_sha256: browserHash});
        const onRunStart = this.onRunStart;
        this.onRunStart = function(browsers) {
            trace('run_start');
            return onRunStart.apply(this, arguments);
        };
        const onBrowserStart = this.onBrowserStart;
        this.onBrowserStart = function(browser) {
            trace('browser_start', browser, undefined,
                {original_socket_sha256: socketHash(browser.socket)});
            return onBrowserStart.apply(this, arguments);
        };
        const specSuccess = this.specSuccess;
        this.specSuccess = function(browser) {
            const result = specSuccess.apply(this, arguments);
            const count = (counts.get(browser.id) || 0) + 1;
            counts.set(browser.id, count);
            if (count === 1 || count % 128 === 0) {
                trace('spec_checkpoint', browser, count);
            }
            return result;
        };
        const onBrowserComplete = this.onBrowserComplete;
        this.onBrowserComplete = function(browser) {
            trace('browser_complete', browser, counts.get(browser.id) || 0);
            if (onBrowserComplete) return onBrowserComplete.apply(this, arguments);
        };
        const onBrowserError = this.onBrowserError;
        this.onBrowserError = function(browser) {
            trace('browser_error', browser, counts.get(browser.id) || 0);
            if (onBrowserError) return onBrowserError.apply(this, arguments);
        };
        const onRunComplete = this.onRunComplete;
        this.onRunComplete = function() {
            const result = onRunComplete.apply(this, arguments);
            trace('run_complete');
            safariFs.closeSync(descriptor);
            return result;
        };
    }
}
SafariLineReporter.$inject = OriginalReporter.$inject;
plugin[reporterKey] = ['type', SafariLineReporter];
