const fs = require('node:fs');
const crypto = require('node:crypto');
const producerKey = 'reporter:karma-kotlin-reporter';
const plugin = config.plugins.find(candidate =>
    Object.prototype.hasOwnProperty.call(candidate, producerKey));
if (!plugin || !Array.isArray(plugin[producerKey]) ||
        plugin[producerKey][0] !== 'type' ||
        typeof plugin[producerKey][1] !== 'function') {
    throw new Error('Kotlin Karma reporter provider is missing');
}
const producer = require.resolve('kotlin-web-helpers/dist/karma-kotlin-reporter');
const producerHash = crypto.createHash('sha256').update(fs.readFileSync(producer)).digest('hex');
if (producerHash !== '7c3232f60952aff254847ae62a866385735e3094197454d755100e962c2f2347') {
    throw new Error('Kotlin Karma reporter producer differs');
}
const wrapper = fs.realpathSync(process.env.DYN4K_BROWSER_REPORTER_SOURCE);
const wrapperHash = crypto.createHash('sha256').update(fs.readFileSync(wrapper)).digest('hex');
fs.writeFileSync(process.env.DYN4K_BROWSER_REPORTER_ATTESTATION,
    JSON.stringify({path: wrapper, sha256: wrapperHash,
        producer_path: producer, producer_sha256: producerHash}) + '\n');
const raw = fs.openSync(process.env.DYN4K_BROWSER_RAW_KARMA, 'wx', 0o600);
const OriginalReporter = plugin[producerKey][1];
function BrowserReporter(baseReporterDecorator, karmaConfig, emitter) {
    OriginalReporter.call(this, baseReporterDecorator, karmaConfig, emitter);
    if (typeof this.write !== 'function') {
        throw new Error('Kotlin Karma reporter writer is missing');
    }
    this.write = function(message) {
        if (typeof message !== 'string') {
            throw new Error('Karma result message is not text');
        }
        const record = JSON.stringify({sha256: crypto.createHash('sha256')
            .update(message).digest('hex'), message}) + '\n';
        fs.writeSync(raw, record);
        if (message.startsWith('##teamcity[') && message.length > 262144) {
            throw new Error('TeamCity service message exceeds 262144 characters');
        }
        const pause = new Int32Array(new SharedArrayBuffer(4));
        let remaining = message;
        while (remaining.length) {
            let width = Math.min(message.startsWith('##teamcity[') ? 262144 : 32768,
                remaining.length);
            if (width < remaining.length && /[\uD800-\uDBFF]/.test(remaining[width - 1])) {
                width -= 1;
            }
            const part = remaining.slice(0, width);
            remaining = remaining.slice(width);
            const bytes = Buffer.from(part.endsWith('\n') ? part : part + '\n', 'utf8');
            for (let offset = 0; offset < bytes.length;) {
                let written;
                try {
                    written = fs.writeSync(1, bytes, offset, bytes.length - offset);
                } catch (error) {
                    if (error.code === 'EINTR' || error.code === 'EAGAIN') {
                        Atomics.wait(pause, 0, 0, 1);
                        continue;
                    }
                    throw error;
                }
                if (!Number.isInteger(written) || written <= 0) {
                    throw new Error('Karma result write made no progress');
                }
                offset += written;
            }
        }
    };
}
BrowserReporter.$inject = OriginalReporter.$inject;
plugin[producerKey] = ['type', BrowserReporter];
