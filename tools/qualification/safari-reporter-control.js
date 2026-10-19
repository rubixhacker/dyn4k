const assert = require('node:assert/strict');
const realFs = require('node:fs');
const vm = require('node:vm');
const fragment = realFs.readFileSync(process.argv[2], 'utf8');
const key = 'reporter:karma-kotlin-reporter';
const pinned = '7c3232f60952aff254847ae62a866385735e3094197454d755100e962c2f2347';
const loadedPinned = '51b54a948f46db31ed64a1fd13f7d7cfe5aa8eabd6dc9886141f05c5384480d1';
const browserPinned = '4805a14470bf3b9a523d5dd68275db24df6548a509e339dcad0f3c83f12d7962';
const reconnectPinned = '56cae9b2607b43decc815a7b5cb343d4aed5ce3760aad4fc5af02e5fa883e99b';

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
    const config = {urlRoot: options.urlRoot === undefined ? '/' : options.urlRoot,
        basePath: '/fixture/build/js/packages/' +
            (options.packageName === undefined ? 'dyn4k-dyn4k-core-test'
                : options.packageName),
        plugins: options.missingReporter ? []
            : options.duplicateReporter ? [plugin, producer] : [plugin],
        set(settings) { Object.assign(this, settings); }};
    let Browser = class {
        constructor(id, socket) {
            this.id = id;
            this.name = 'Safari';
            this.socket = socket;
            this.activeSockets = [socket];
            this.state = 'EXECUTING';
            this.reconnectCalls = 0;
        }
        reconnect(newSocket, clientSaysReconnect) {
            this.reconnectCalls++;
            if (clientSaysReconnect && this.state === 'EXECUTING_DISCONNECTED') {
                this.state = 'EXECUTING';
            }
            if (!this.activeSockets.some(socket => socket.id === newSocket.id)) {
                this.activeSockets.push(newSocket);
            }
            return 'delegated';
        }
    };
    let browserPath = '/fixture/karma/lib/browser.js';
    let serverPath = '/fixture/karma/lib/server.js';
    let realRequire;
    if (options.realBrowserPath) {
        realRequire = require('node:module').createRequire(options.realBrowserPath);
        browserPath = realRequire.resolve('karma/lib/browser');
        serverPath = realRequire.resolve('karma/lib/server');
        assert.equal(browserPath, options.realBrowserPath);
        realRequire(serverPath);
        Browser = realRequire(browserPath);
    }
    const originalReconnect = Browser.prototype.reconnect;
    const simulatedNoFollow = 0x04000000;
    assert.equal(simulatedNoFollow & (realFs.constants.O_WRONLY |
        realFs.constants.O_CREAT | realFs.constants.O_EXCL), 0);
    const hostConstants = options.windowsLikeFs
        ? {...realFs.constants, O_NOFOLLOW: undefined} : realFs.constants;
    const fakeFs = {
        constants: {...hostConstants,
            O_NOFOLLOW: options.noFollowUnavailable ? undefined : simulatedNoFollow},
        readFileSync(path) {
            if (path === '/fixture/karma-kotlin-reporter.js') {
                return Buffer.from('producer fixture');
            }
            assert.equal(path, browserPath);
            return options.realBrowserPath ? realFs.readFileSync(path)
                : Buffer.from('browser fixture');
        },
        lstatSync(path) {
            assert.equal(path, '/fixture/events');
            return {isDirectory: () => !options.linkedDirectory,
                isSymbolicLink: () => !!options.linkedDirectory};
        },
        realpathSync(path) {
            assert.equal(path, '/fixture/events');
            return options.mismatchedRealpath ? '/fixture/elsewhere' : path;
        },
        openSync(path, flags, mode) {
            assert.equal(path, '/fixture/events/dyn4k-core-' + '1'.repeat(32) + '-1234.jsonl');
            assert.equal(mode, 0o600);
            assert.ok(flags & realFs.constants.O_EXCL);
            assert.ok(flags & fakeFs.constants.O_NOFOLLOW);
            if (options.linkedTraceFile) {
                const error = new Error('linked trace file');
                error.code = 'ELOOP';
                throw error;
            }
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
    const fakeCrypto = {createHash: () => ({
        update(value) { this.value = value; return this; },
        digest() {
            if (options.badHash || (options.badLoadedProducer &&
                    this.value === Function.prototype.toString.call(OriginalReporter))) {
                return '0'.repeat(64);
            }
            if (this.value instanceof Buffer && this.value.toString() === 'producer fixture') {
                return pinned;
            }
            if (this.value === Function.prototype.toString.call(OriginalReporter)) {
                return loadedPinned;
            }
            if (this.value === Function.prototype.toString.call(originalReconnect)) {
                return options.badReconnectImpl ? '0'.repeat(64) : reconnectPinned;
            }
            if (this.value instanceof Buffer && this.value.toString() === 'browser fixture') {
                return options.badBrowserHash ? '0'.repeat(64) : browserPinned;
            }
            if (options.badBrowserHash && this.value instanceof Buffer) {
                return '0'.repeat(64);
            }
            return require('node:crypto').createHash('sha256').update(this.value).digest('hex');
        }
    })};
    function fakeRequire(name) {
        if (name === 'node:fs') return fakeFs;
        if (name === 'node:crypto') return fakeCrypto;
        if (name === '/fixture/karma-kotlin-reporter.js') return producer;
        if (name === browserPath) return Browser;
        throw new Error(`unexpected require: ${name}`);
    }
    fakeRequire.resolve = name => {
        if (name === 'kotlin-web-helpers/dist/karma-kotlin-reporter') {
            return '/fixture/karma-kotlin-reporter.js';
        }
        if (name === 'karma/lib/browser') return browserPath;
        assert.equal(name, 'karma/lib/server');
        return serverPath;
    };
    const browserModule = {exports: Browser};
    fakeRequire.cache = realRequire ? realRequire.cache : {
        [browserPath]: browserModule,
        [serverPath]: {children: options.wrongKarmaModule ? [] : [browserModule]}
    };
    const environment = options.trace ? {DYN4K_SAFARI_EVENT_TRACE_DIR: '/fixture/events'} : {};
    if (options.invocation !== null) {
        environment.DYN4K_QUALIFICATION_INVOCATION =
            options.invocation === undefined ? '1'.repeat(32) : options.invocation;
    }
    const fakeProcess = {pid: options.pid === undefined ? 1234 : options.pid,
        env: environment};
    vm.runInNewContext(fragment, {config, Buffer, require: fakeRequire,
        process: fakeProcess, Atomics, SharedArrayBuffer, Int32Array});
    const Reporter = plugin[key][1];
    const reporter = new Reporter(instance => {
        instance.write = message => asynchronous.push(message);
    }, config, {});
    return {reporter, config, output, traceOutput, asynchronous, calls, Reporter,
        Browser, originalReconnect};
}

if (process.argv[3] === '--windows-capability-control' ||
        process.argv[3] === '--trace-control') {
    const actual = load({trace: true, windowsLikeFs: true});
    assert.ok(actual.traceOutput.length > 0);
    assert.throws(() => load({trace: true, windowsLikeFs: true,
        noFollowUnavailable: true}), /Safari event trace source or destination is unsafe/);
    assert.throws(() => load({trace: true, windowsLikeFs: true,
        mismatchedRealpath: true}), /Safari event trace source or destination is unsafe/);
    assert.throws(() => load({trace: true, windowsLikeFs: true,
        linkedDirectory: true}), /Safari event trace source or destination is unsafe/);
    assert.throws(() => load({trace: true, windowsLikeFs: true,
        linkedTraceFile: true}), error => error.code === 'ELOOP');
    if (process.argv[3] === '--windows-capability-control') process.exit(0);
}

if (process.argv[3] === '--isolation-control') {
    const core = load();
    const facade = load({packageName: 'dyn4k-dyn4k-test'});
    const consumer = load({packageName: 'dyn4k-staged-portable-consumer-test'});
    const nextInvocation = load({invocation: '2'.repeat(32)});
    const nextProcess = load({pid: 5678});
    assert.match(core.config.urlRoot,
        /^\/dyn4k-safari\/[0-9a-f]{32}\/dyn4k-core\/1234\/$/);
    assert.equal(new Set([core, facade, consumer, nextInvocation, nextProcess]
        .map(item => item.config.urlRoot)).size, 5);
    assert.throws(() => load({invocation: 'bad'}), /Safari.*invocation.*unsafe/);
    assert.throws(() => load({invocation: ''}), /Safari.*invocation.*unsafe/);
    assert.throws(() => load({packageName: 'unknown-test'}), /Safari.*package.*unsafe/);
    assert.throws(() => load({packageName: ''}), /Safari.*package.*unsafe/);
    assert.throws(() => load({urlRoot: '/socket.io/'}), /Safari.*route.*unsafe/);
    assert.throws(() => load({pid: 0}), /Safari.*process.*unsafe/);
    const probe = load({invocation: null});
    assert.match(probe.config.urlRoot, /^\/dyn4k-safari\/probe\/dyn4k-core\/1234\/$/);
    assert.equal(core.Browser.prototype.reconnect, core.originalReconnect);
    process.exit(0);
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
    const old = new actual.Browser('old-tab', {id: 'old-socket'});
    const launched = new actual.Browser('new-tab', {id: 'new-socket'});
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
    const same = load({trace: true});
    const browser = new same.Browser('same-tab', {id: 'socket-before'});
    same.reporter.onBrowserStart(browser);
    browser.state = 'EXECUTING_DISCONNECTED';
    browser.activeSockets = [];
    assert.equal(browser.reconnect({id: 'socket-after'}, true), 'delegated');
    assert.equal(browser.reconnectCalls, 1);
    assert.notEqual(same.Browser.prototype.reconnect, same.originalReconnect);
    assert.equal(browser.state, 'EXECUTING');
    assert.equal(browser.activeSockets[0].id, 'socket-after');
    const reconnects = Buffer.concat(same.traceOutput).toString('utf8').trim()
        .split('\n').map(line => JSON.parse(line))
        .filter(row => row.event === 'socket_reconnect');
    assert.equal(reconnects.length, 1, 'silent same-ID reconnect was not traced');
    assert.equal(reconnects[0].browser, 'same-tab');
    assert.equal(reconnects[0].before_state, 'EXECUTING_DISCONNECTED');
    assert.equal(reconnects[0].after_state, 'EXECUTING');
    assert.equal(reconnects[0].client_says_reconnect, true);
    assert.notEqual(reconnects[0].socket_sha256, reconnects[0].original_socket_sha256);
    assert.ok(!Buffer.concat(same.traceOutput).toString('utf8').includes('socket-after'));
    assert.throws(() => load({trace: true, badBrowserHash: true}), /Karma Browser source mismatch/);
    assert.throws(() => load({trace: true, badReconnectImpl: true}),
        /Karma Browser reconnect implementation mismatch/);
    assert.throws(() => load({trace: true, wrongKarmaModule: true}), /Karma Browser module mismatch/);
    assert.ok(records.every(row => row.invocation === '1'.repeat(32)));
    assert.equal(records.at(-1).event, 'run_complete');
    assert.throws(() => load({trace: true, linkedDirectory: true}), /unsafe/);
    const bounded = load({trace: true});
    assert.throws(() => {
        for (let i = 0; i < 600; i++) {
            bounded.reporter.onBrowserStart(
                new bounded.Browser(`browser-${i}`, {id: `socket-${i}`}));
        }
    }, /trace exceeds bound/);
    process.exit(0);
}

if (process.argv[3] === '--real-karma-reconnect') {
    const sourcePath = process.argv[4];
    assert.ok(sourcePath, 'pinned Karma browser source path is required');
    const actual = load({trace: true, realBrowserPath: sourcePath});
    const events = [];
    const emitter = new (require('node:events').EventEmitter)();
    for (const name of ['browser_start', 'browser_register', 'browser_error',
        'browser_complete']) emitter.on(name, () => events.push(name));
    const before = new (require('node:events').EventEmitter)();
    before.id = 'real-socket-before';
    const after = new (require('node:events').EventEmitter)();
    after.id = 'real-socket-after';
    const browser = new actual.Browser('real-same-tab', 'Safari',
        {add() {}, remove() {}}, emitter, before,
        {setTimeout() {}, clearTimeout() {}}, 2000, 0, true, {});
    actual.reporter.onBrowserStart(browser);
    browser.state = actual.Browser.STATE_EXECUTING_DISCONNECTED;
    browser.activeSockets = [];
    assert.equal(browser.reconnect(after, true), undefined);
    assert.deepEqual(events, [], 'pinned silent branch emitted reporter events');
    assert.equal(browser.state, actual.Browser.STATE_EXECUTING);
    assert.equal(browser.activeSockets[0], after);
    assert.ok(after.listenerCount('result') > 0, 'pinned reconnect did not bind the socket');
    const records = Buffer.concat(actual.traceOutput).toString('utf8').trim()
        .split('\n').map(line => JSON.parse(line));
    const reconnects = records.filter(row => row.event === 'socket_reconnect');
    assert.equal(reconnects.length, 1);
    assert.equal(reconnects[0].browser, 'real-same-tab');
    assert.equal(reconnects[0].before_state, 'EXECUTING_DISCONNECTED');
    assert.equal(reconnects[0].after_state, 'EXECUTING');
    assert.notEqual(reconnects[0].original_socket_sha256,
        reconnects[0].socket_sha256);
    assert.ok(records.some(row => row.event === 'reconnect_hook_installed' &&
        row.karma_browser_sha256 === browserPinned));
    process.stdout.write('pinned silent reconnect traced with zero reporter events\n');
    process.exit(0);
}

const normal = load({actions: [3, 'EINTR', 'EAGAIN', 2]});
assert.equal(normal.Browser.prototype.reconnect, normal.originalReconnect);
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
