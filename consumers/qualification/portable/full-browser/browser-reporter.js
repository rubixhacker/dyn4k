const fs = require('node:fs');
const crypto = require('node:crypto');
const path = require('node:path');
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
    const selected = process.env.DYN4K_BROWSER_SELECTED_BUNDLE;
    const archive = process.env.DYN4K_BROWSER_SELECTED_ARCHIVE;
    const recordPath = process.env.DYN4K_BROWSER_SELECTED_ATTESTATION;
    const work = process.env.DYN4K_BROWSER_WORK_ROOT;
    const tmpdir = process.env.DYN4K_BROWSER_TMPDIR;
    const root = path.join(work, 'root/js/node_modules');
    const runner = path.join(root, 'kotlin-web-helpers/dist/kotlin-test-karma-runner.js');
    const inputHashes = {
        [path.join(root, 'mocha/mocha.js')]:
            '8f46c07ab4422da71bdb27e8f54d0a9ba59b736face2c9f5534c414623c55ef6',
        [path.join(root, 'karma-mocha/lib/adapter.js')]:
            'd2ecb1de057231e7c5efe6b7a5b36e163c85f49834814ab8fc3a893a3a404933',
        [runner]: '15261c8d909c161dfc3004934d1f2542f96abcb78071b6f3663aa927773aba18',
        [path.join(root, 'karma/lib/config.js')]:
            'fadd8d4cef5e4d62dcd9a5ccd63295ceb028925a5d2f8b7edfb1d47a09fb7e42',
        [path.join(root, 'karma/lib/helper.js')]:
            'db2c4942bde7e0d696a40d1a1a7b58ba18b9acc3843c53a8a336c86645d5de6f',
        [path.join(root, 'karma/lib/file-list.js')]:
            'b91c1f294a2f1fbd886a8d3b991c8066c70037319a8e71d97a549b0928eefc22',
        [path.join(root, 'karma-mocha/lib/index.js')]:
            '4e9a83d5ff0504ad8d2ea42ee535d5e05324b2e4e8f1796b809c8314b1cc524b',
        [path.join(root, 'karma-webpack/lib/karma-webpack/framework.js')]:
            '705fc7f4d211eee26beb549758d8ea39f502a7385c2a43756bc71e3003c99ca9',
        [path.join(root, 'karma-webpack/lib/karma-webpack/preprocessor.js')]:
            '6af7525c470abcc69165a9732bf492b4524201525183eeef55998940f3f802c6',
        [path.join(root, 'kotlin-web-helpers/dist/karma-webpack-output.js')]:
            '7accb6fbba4ce0082f6e8ae2ca165eb9dd3c6dcfed0dfb2a8ba2e9aaa43061c7'
    };
    function runtimeSelection() {
        for (const [name, digest] of Object.entries(inputHashes)) {
            if (crypto.createHash('sha256').update(fs.readFileSync(name)).digest('hex') !== digest) {
                throw new Error('Karma toolchain input differs');
            }
        }
        const createPatternObject = require('karma/lib/config').createPatternObject;
        const files = config.files.map(file => {
            const pattern = createPatternObject(file);
            if (pattern.type !== undefined) {
                throw new Error('Karma effective pattern type differs');
            }
            return {pattern: pattern.pattern, served: pattern.served,
                included: pattern.included, watched: pattern.watched,
                nocache: pattern.nocache, type: null};
        });
        const webpack = path.dirname((files[0] || {}).pattern || '');
        if (!path.isAbsolute(tmpdir) || path.dirname(webpack) !== tmpdir ||
                !/^_karma_webpack_[0-9]+$/.test(path.basename(webpack))) {
            throw new Error('Karma generated webpack path differs');
        }
        const expectedPaths = [path.join(webpack, 'runtime.js'), path.join(webpack, 'commons.js'),
            path.join(root, 'mocha/mocha.js'), path.join(root, 'karma-mocha/lib/adapter.js'),
            runner, selected, path.join(webpack, '**/*')];
        const expected = expectedPaths.map((pattern, index) => ({pattern,
            served: true, included: index !== 6, watched: false,
            nocache: false, type: null}));
        const preprocessors = config.preprocessors;
        const expectedPreprocessors = {[runner]: ['webpack', 'sourcemap'],
            [selected]: ['webpack', 'sourcemap']};
        if (JSON.stringify(files) !== JSON.stringify(expected) ||
                Object.keys(preprocessors).length !== 2 ||
                Object.keys(expectedPreprocessors).some(key =>
                    JSON.stringify(preprocessors[key]) !== JSON.stringify(expectedPreprocessors[key]))) {
            throw new Error('Karma effective files or preprocessors differ');
        }
        return {effective_files: files, effective_preprocessors: expectedPreprocessors,
            input_sha256: inputHashes, tmpdir};
    }
    const runtime = runtimeSelection();
    let evidence = null;
    const originalBrowserStart = this.onBrowserStart;
    const originalRunComplete = this.onRunComplete;
    this.onBrowserStart = function(browser) {
        originalBrowserStart.call(this, browser);
        if (evidence !== null || JSON.stringify(runtimeSelection()) !== JSON.stringify(runtime)) {
            throw new Error('Karma runtime selection changed before browser start');
        }
        const bytes = fs.readFileSync(selected);
        fs.writeFileSync(archive, bytes, {flag: 'wx', mode: 0o600});
        evidence = {...runtime, source_path: selected, archive_path: archive,
            sha256: crypto.createHash('sha256').update(bytes).digest('hex'),
            node_pid: process.pid, browser_id: browser.id, browser_name: browser.name,
            captured_ns: Date.now() * 1000000};
    };
    this.onRunComplete = function() {
        if (evidence === null || JSON.stringify(runtimeSelection()) !== JSON.stringify(runtime) ||
                crypto.createHash('sha256').update(fs.readFileSync(selected))
                .digest('hex') !== evidence.sha256) {
            throw new Error('Karma selected bundle changed during browser execution');
        }
        originalRunComplete.call(this);
        evidence.complete_ns = Date.now() * 1000000;
        fs.writeFileSync(recordPath, JSON.stringify(evidence) + '\n', {flag: 'wx', mode: 0o600});
    };
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
