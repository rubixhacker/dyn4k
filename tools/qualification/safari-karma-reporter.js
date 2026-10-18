const DYN4K_SAFARI_REPORTER_NEWLINES = true;
const reporterKey = 'reporter:karma-kotlin-reporter';
const plugin = config.plugins.find(candidate =>
    Object.prototype.hasOwnProperty.call(candidate, reporterKey));
if (!plugin || !Array.isArray(plugin[reporterKey]) ||
        plugin[reporterKey][0] !== 'type' ||
        typeof plugin[reporterKey][1] !== 'function') {
    throw new Error('Safari Kotlin reporter provider is missing');
}
const OriginalReporter = plugin[reporterKey][1];
function SafariLineReporter(baseReporterDecorator, karmaConfig, emitter) {
    OriginalReporter.call(this, baseReporterDecorator, karmaConfig, emitter);
    const originalWrite = this.write;
    if (typeof originalWrite !== 'function') {
        throw new Error('Safari Kotlin reporter writer is missing');
    }
    this.write = function(message) {
        if (typeof message !== 'string' || Buffer.byteLength(message, 'utf8') > 262144) {
            throw new Error('Safari service message exceeds 262144 bytes');
        }
        return originalWrite.call(this, message.endsWith('\n') ? message : message + '\n');
    };
}
SafariLineReporter.$inject = OriginalReporter.$inject;
plugin[reporterKey] = ['type', SafariLineReporter];
