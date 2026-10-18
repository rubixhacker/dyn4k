const fs = require('node:fs');
const crypto = require('node:crypto');
const expectedProducerSha256 = '7c3232f60952aff254847ae62a866385735e3094197454d755100e962c2f2347';
const reporterKey = 'reporter:karma-kotlin-reporter';
const plugin = config.plugins.find(candidate =>
    Object.prototype.hasOwnProperty.call(candidate, reporterKey));
if (!plugin || !Array.isArray(plugin[reporterKey]) ||
        plugin[reporterKey][0] !== 'type' ||
        typeof plugin[reporterKey][1] !== 'function') {
    throw new Error('Browser Kotlin reporter provider is missing');
}
const loaded = Object.values(require.cache || {}).filter(module => module.exports === plugin);
if (loaded.length !== 1 || !loaded[0].filename ||
        !process.env.DYN4K_BROWSER_REPORTER_ATTESTATION) {
    throw new Error('Browser Kotlin reporter producer is unavailable');
}
const producerPath = fs.realpathSync(loaded[0].filename);
const producerSha256 = crypto.createHash('sha256')
    .update(fs.readFileSync(producerPath)).digest('hex');
if (producerSha256 !== expectedProducerSha256) {
    throw new Error('Browser Kotlin reporter producer bytes differ');
}
fs.writeFileSync(process.env.DYN4K_BROWSER_REPORTER_ATTESTATION,
    JSON.stringify({path: producerPath, sha256: producerSha256}) + '\n');
const OriginalReporter = plugin[reporterKey][1];
function BrowserLineReporter(baseReporterDecorator, karmaConfig, emitter) {
    OriginalReporter.call(this, baseReporterDecorator, karmaConfig, emitter);
    if (typeof this.write !== 'function' || process.stdout.fd !== 1) {
        throw new Error('Browser Kotlin reporter output is unavailable');
    }
    this.write = function(message) {
        if (typeof message !== 'string' || Buffer.byteLength(message, 'utf8') > 262144) {
            throw new Error('Browser service message exceeds 262144 bytes');
        }
        const bytes = Buffer.from(message.endsWith('\n') ? message : message + '\n', 'utf8');
        let offset = 0;
        const deadline = Date.now() + 30000;
        const pause = new Int32Array(new SharedArrayBuffer(4));
        // Karma calls process.exit before asynchronous reporter output drains.
        while (offset < bytes.length) {
            try {
                const written = fs.writeSync(1, bytes, offset, bytes.length - offset);
                if (!Number.isInteger(written) || written <= 0) {
                    throw new Error('Browser service message write made no progress');
                }
                offset += written;
            } catch (error) {
                if (error && error.code === 'EINTR') continue;
                if (error && error.code === 'EAGAIN' && Date.now() < deadline) {
                    Atomics.wait(pause, 0, 0, 1);
                    continue;
                }
                throw error;
            }
        }
    };
}
BrowserLineReporter.$inject = OriginalReporter.$inject;
plugin[reporterKey] = ['type', BrowserLineReporter];
