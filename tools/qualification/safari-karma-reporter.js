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
}
SafariLineReporter.$inject = OriginalReporter.$inject;
plugin[reporterKey] = ['type', SafariLineReporter];
