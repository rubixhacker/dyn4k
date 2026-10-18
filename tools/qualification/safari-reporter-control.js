const assert = require('node:assert/strict');
const realFs = require('node:fs');
const vm = require('node:vm');
const fragment = realFs.readFileSync(process.argv[2], 'utf8');
const key = 'reporter:karma-kotlin-reporter';
const pinned = '7c3232f60952aff254847ae62a866385735e3094197454d755100e962c2f2347';
const loadedPinned = '51b54a948f46db31ed64a1fd13f7d7cfe5aa8eabd6dc9886141f05c5384480d1';

function OriginalReporter(decorate) {
    decorate(this);
    this.emit = message => this.write(message);
    this.onRunStart = () => {};
    this.onBrowserStart = () => {};
    this.onBrowserComplete = () => {};
    this.specSuccess = () => {};
    this.onRunComplete = () => {};
}
OriginalReporter.$inject = ['baseReporterDecorator'];

function load(options = {}) {
    const output = [];
    const traceOutput = [];
    const asynchronous = [];
    const calls = [];
    const producer = {[key]: ['type', OriginalReporter]};
    const plugin = options.wrongReporter
        ? {[key]: ['type', function WrongReporter() {}]} : producer;
    const config = {basePath: '/fixture/build/js/packages/dyn4k-dyn4k-core-test',
        plugins: options.missingReporter ? []
            : options.duplicateReporter ? [plugin, producer] : [plugin]};
    const fakeFs = {
        constants: realFs.constants,
        readFileSync(path) {
            assert.equal(path, '/fixture/karma-kotlin-reporter.js');
            return Buffer.from('producer fixture');
        },
        lstatSync(path) {
            assert.equal(path, '/fixture/events');
            return {isDirectory: () => !options.linkedDirectory,
                isSymbolicLink: () => !!options.linkedDirectory};
        },
        realpathSync(path) {
            assert.equal(path, '/fixture/events');
            return path;
        },
        openSync(path, flags, mode) {
            assert.equal(path, '/fixture/events/dyn4k-core-' + '1'.repeat(32) + '-1234.jsonl');
            assert.equal(mode, 0o600);
            assert.ok(flags & realFs.constants.O_EXCL);
            assert.ok(flags & realFs.constants.O_NOFOLLOW);
            return 3;
        },
        closeSync(fd) {
            assert.equal(fd, 3);
        },
        writeSync(fd, buffer, offset, length) {
            if (fd === 3) {
                traceOutput.push(buffer.subarray(offset, offset + length));
                return length;
            }
            assert.equal(fd, 1);
            if (options.realWriter) {
                return realFs.writeSync(fd, buffer, offset, length);
            }
            const action = options.actions && options.actions[calls.length];
            calls.push(action || 'write');
            if (action === 'EINTR' || action === 'EAGAIN' || action === 'EIO') {
                const error = new Error(action);
                error.code = action;
                throw error;
            }
            const count = typeof action === 'number' ? Math.min(action, length) : length;
            output.push(buffer.subarray(offset, offset + count));
            return count;
        }
    };
    let hashes = 0;
    const fakeCrypto = {createHash: () => ({
        update() { return this; },
        digest: () => {
            hashes++;
            if (options.badHash || (hashes === 2 && options.badLoadedProducer)) {
                return '0'.repeat(64);
            }
            return hashes === 1 ? pinned : loadedPinned;
        }
    })};
    function fakeRequire(name) {
        if (name === 'node:fs') return fakeFs;
        if (name === 'node:crypto') return fakeCrypto;
        if (name === '/fixture/karma-kotlin-reporter.js') return producer;
        throw new Error(`unexpected require: ${name}`);
    }
    fakeRequire.resolve = name => {
        assert.equal(name, 'kotlin-web-helpers/dist/karma-kotlin-reporter');
        return '/fixture/karma-kotlin-reporter.js';
    };
    const fakeProcess = {pid: 1234, env: options.trace ? {
        DYN4K_SAFARI_EVENT_TRACE_DIR: '/fixture/events',
        DYN4K_QUALIFICATION_INVOCATION: '1'.repeat(32)
    } : {}};
    vm.runInNewContext(fragment, {config, Buffer, require: fakeRequire,
        process: fakeProcess, Atomics, SharedArrayBuffer, Int32Array});
    const Reporter = plugin[key][1];
    const reporter = new Reporter(instance => {
        instance.write = message => asynchronous.push(message);
    }, config, {});
    return {reporter, output, traceOutput, asynchronous, calls, Reporter};
}

if (process.argv[3] === '--real-stdout') {
    const actual = load({realWriter: true});
    for (let i = 0; i < 72; i++) {
        actual.reporter.emit(`##teamcity[testStdOut out='DYN4K_COLLISION_DIAGNOSTIC row=${i}']`);
    }
    assert.equal(actual.asynchronous.length, 0);
    process.exit(0);
}

if (process.argv[3] === '--trace-control') {
    const actual = load({trace: true});
    const old = {id: 'old-tab', name: 'Safari'};
    const launched = {id: 'new-tab', name: 'Safari'};
    actual.reporter.onRunStart([]);
    actual.reporter.onBrowserStart(old);
    actual.reporter.specSuccess(old, {description: 'capsuleSlice'});
    actual.reporter.onBrowserStart(launched);
    actual.reporter.specSuccess(launched, {description: 'capsuleSlice'});
    actual.reporter.onBrowserComplete(old);
    actual.reporter.onBrowserComplete(launched);
    actual.reporter.onRunComplete();
    assert.ok(actual.traceOutput.length > 0, 'no Safari browser lifecycle trace');
    const records = Buffer.concat(actual.traceOutput).toString('utf8').trim()
        .split('\n').map(line => JSON.parse(line));
    assert.deepEqual(records.filter(row => row.event === 'browser_start')
        .map(row => row.browser), ['old-tab', 'new-tab']);
    assert.deepEqual(records.filter(row => row.event === 'spec_checkpoint')
        .map(row => row.browser), ['old-tab', 'new-tab']);
    assert.ok(records.every(row => row.invocation === '1'.repeat(32)));
    assert.equal(records.at(-1).event, 'run_complete');
    assert.throws(() => load({trace: true, linkedDirectory: true}), /unsafe/);
    const bounded = load({trace: true});
    assert.throws(() => {
        for (let i = 0; i < 600; i++) {
            bounded.reporter.onBrowserStart({id: `browser-${i}`, name: 'Safari'});
        }
    }, /trace exceeds bound/);
    process.exit(0);
}

const normal = load({actions: [3, 'EINTR', 'EAGAIN', 2]});
assert.deepEqual(normal.Reporter.$inject, OriginalReporter.$inject);
const expected = [];
for (let i = 0; i < 72; i++) {
    const line = `##teamcity[testStdOut out='DYN4K_COLLISION_DIAGNOSTIC row=${i}']\n`;
    expected.push(line);
    normal.reporter.emit(line.slice(0, -1));
}
assert.equal(Buffer.concat(normal.output).toString('utf8'), expected.join(''));
assert.equal(normal.asynchronous.length, 0);
assert.deepEqual(normal.calls.slice(0, 4), [3, 'EINTR', 'EAGAIN', 2]);
for (let i = 0; i < 12000; i++) {
    normal.reporter.emit(`##teamcity[testStarted name='case-${i}' payload='${'x'.repeat(80)}']`);
}
assert.ok(Buffer.concat(normal.output).length > 1048576);
assert.equal(normal.asynchronous.length, 0);
assert.throws(() => normal.reporter.emit('x'.repeat(262145)), /exceeds/);
assert.throws(() => normal.reporter.emit("##teamcity[testStdOut out='lost'"), /incomplete/);
assert.throws(() => load({badHash: true}), /producer.*mismatch/);
assert.throws(() => load({badLoadedProducer: true}), /loaded producer mismatch/);
assert.throws(() => load({wrongReporter: true}), /provider.*mismatch/);
assert.throws(() => load({missingReporter: true}), /provider is missing/);
assert.throws(() => load({duplicateReporter: true}), /provider is missing/);
const lost = load({actions: ['EIO']});
assert.throws(() => lost.reporter.emit("##teamcity[testStdOut out='lost']"), /write failed/);
assert.equal(lost.asynchronous.length, 0);
const partialLoss = load({actions: [4, 'EIO']});
assert.throws(() => partialLoss.reporter.emit("##teamcity[testStdOut out='lost']"), /write failed/);
assert.equal(Buffer.concat(partialLoss.output).toString(), '##te');
assert.equal(partialLoss.asynchronous.length, 0);
const blocked = load({actions: Array(101).fill('EAGAIN')});
assert.throws(() => blocked.reporter.emit("##teamcity[testStdOut out='lost']"), /write failed/);
assert.equal(blocked.calls.length, 101);
const {spawnSync} = require('node:child_process');
const actual = spawnSync(process.execPath, [__filename, process.argv[2], '--real-stdout'],
    {encoding: 'utf8'});
assert.equal(actual.status, 0, actual.stderr);
assert.equal(actual.stdout, expected.join(''));
