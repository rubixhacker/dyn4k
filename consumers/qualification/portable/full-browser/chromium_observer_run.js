#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {spawn, execFileSync} = require('node:child_process');

function hash(bytes) { return crypto.createHash('sha256').update(bytes).digest('hex'); }
function pause() { return new Promise(resolve => setTimeout(resolve, 20)); }
function read(file) {
    const stat = fs.lstatSync(file);
    if (!stat.isFile() || stat.nlink !== 1) throw new Error(`handoff file differs: ${file}`);
    return JSON.parse(fs.readFileSync(file, 'utf8'));
}
async function waitFor(file, timeoutMs, children, forbidden = []) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        if (forbidden.some(name => fs.existsSync(name))) {
            throw new Error(`premature observer control while waiting for ${file}`);
        }
        if (children.some(child => child.exitCode !== null || child.signalCode !== null)) {
            throw new Error(`browser or observer exited before ${file}`);
        }
        if (fs.existsSync(file)) return read(file);
        await pause();
    }
    throw new Error(`observer handoff timed out waiting for ${file}`);
}
async function exitOf(child, timeoutMs) {
    const deadline = Date.now() + timeoutMs;
    while (child.exitCode === null && child.signalCode === null && Date.now() < deadline) {
        await pause();
    }
    if (child.exitCode === null && child.signalCode === null) {
        throw new Error('observer process exit timed out');
    }
    return child.exitCode;
}
function option(args, name) {
    const index = args.indexOf(name);
    if (index < 0 || index + 1 >= args.length || args.indexOf(name, index + 1) >= 0) {
        throw new Error(`missing or duplicate ${name}`);
    }
    return args[index + 1];
}
function unique(file, value) {
    fs.writeFileSync(file, typeof value === 'string' ? value : JSON.stringify(value) + '\n',
        {mode: 0o600, flag: 'wx'});
}
async function moduleHandoff(root, repository, candidate, target, browser, archive,
        consumer, module) {
    const directory = path.join(root, module);
    const offerPath = path.join(directory, 'offer.json');
    const readyPath = path.join(directory, 'ready.json');
    const stopPath = path.join(directory, 'stop');
    const requestPath = path.join(directory, 'stop-request.json');
    const observationPath = path.join(directory, 'observer.json');
    const offer = await waitFor(offerPath, 1200000, [consumer]);
    const offerBytes = fs.readFileSync(offerPath);
    const offerHash = hash(offerBytes);
    const source = path.join(repository,
        'consumers/qualification/portable/full-browser/chromium_http_witness.js');
    const committed = execFileSync('git', ['-C', repository, 'show',
        `${candidate}:consumers/qualification/portable/full-browser/chromium_http_witness.js`]);
    const session = read(path.join(archive, module, 'chromium-cdp.jsonl'));
    const captureUrl = new URL(offer.capture_url);
    if (offer.module !== module || offer.target !== target ||
            offer.candidate_sha !== candidate ||
            offer.source_path !== fs.realpathSync(source) ||
            offer.source_sha256 !== hash(committed) ||
            hash(fs.readFileSync(source)) !== hash(committed) ||
            fs.realpathSync(offer.browser_path) !== fs.realpathSync(browser) ||
            captureUrl.protocol !== 'http:' ||
            !['localhost', '127.0.0.1'].includes(captureUrl.hostname) ||
            !Number.isSafeInteger(+captureUrl.port) || +captureUrl.port <= 0 ||
            session.browser_pid !== offer.browser_pid ||
            session.devtools_port !== offer.devtools_port ||
            session.devtools_socket_inode !== offer.devtools_socket_inode ||
            session.started_ns !== offer.session_started_ns ||
            session.source_sha256 !== offer.source_sha256 ||
            session.candidate_sha !== candidate ||
            !/^[0-9a-f]{64}$/.test(offer.token)) {
        throw new Error(`${module} observer offer differs from exact source or process`);
    }
    const observerPath = path.join(repository, 'tools/qualification/independent_browser_observer.js');
    const observerArgs = [observerPath, '--pid', String(offer.browser_pid),
        '--browser', browser, '--cdp-port', String(offer.devtools_port),
        '--karma-port', captureUrl.port, '--module', module, '--target', target,
        '--output', observationPath, '--ready-file', readyPath,
        '--stop-file', stopPath, '--timeout-ms', '1200000'];
    const stdout = fs.openSync(path.join(directory, 'observer.stdout'), 'wx', 0o600);
    const stderr = fs.openSync(path.join(directory, 'observer.stderr'), 'wx', 0o600);
    const observer = spawn(process.execPath, observerArgs,
        {cwd: repository, env: process.env, stdio: ['ignore', stdout, stderr]});
    fs.closeSync(stdout);
    fs.closeSync(stderr);
    try {
        const ready = await waitFor(readyPath, 12000, [consumer, observer],
            [stopPath, requestPath]);
        if (ready.pid !== offer.browser_pid ||
                !Number.isSafeInteger(ready.started_ns) ||
                ready.started_ns < offer.offered_ns) {
            throw new Error(`${module} observer readiness differs`);
        }
        unique(path.join(directory, 'allow.json'), {offer_sha256: offerHash,
            browser_pid: offer.browser_pid,
            ready_ns: Math.max(Date.now() * 1000000, offer.offered_ns + 1)});
        const request = await waitFor(requestPath, 1200000, [consumer, observer],
            [stopPath]);
        if (request.offer_sha256 !== offerHash ||
                request.browser_pid !== offer.browser_pid ||
                request.requested_ns <= ready.started_ns) {
            throw new Error(`${module} observer stop request differs`);
        }
        unique(stopPath, 'stop\n');
        const observation = await waitFor(observationPath, 15000, [consumer]);
        if (await exitOf(observer, 15000) !== 0) {
            throw new Error(`${module} independent observer failed`);
        }
        const raw = fs.readFileSync(observationPath);
        if (observation.protocol !== 'cdp' ||
                observation.browser_pid !== offer.browser_pid ||
                observation.started_ns !== ready.started_ns ||
                observation.finished_ns < request.requested_ns ||
                observation.responses?.length < (target === 'wasmJs' ? 3 : 2) ||
                observation.responses.some(item => new URL(item.url).port !== captureUrl.port ||
                    !/^[0-9a-f]{64}$/.test(item.body_sha256) || item.size <= 0)) {
            throw new Error(`${module} independent observation differs`);
        }
        const releasedNs = Math.max(Date.now() * 1000000,
            observation.finished_ns + 1, request.requested_ns + 1);
        unique(path.join(directory, 'release.json'), {offer_sha256: offerHash,
            browser_pid: offer.browser_pid, observer_sha256: hash(raw),
            released_ns: releasedNs});
        return {module, offer_sha256: offerHash, browser_pid: offer.browser_pid,
            observer_sha256: hash(raw), observer_source_sha256: hash(fs.readFileSync(observerPath)),
            response_count: observation.responses.length,
            offered_ns: offer.offered_ns, ready_ns: ready.started_ns,
            stop_requested_ns: request.requested_ns,
            observation_finished_ns: observation.finished_ns, released_ns: releasedNs};
    } finally {
        if (observer.exitCode === null && observer.signalCode === null) observer.kill('SIGTERM');
    }
}
async function main(argv) {
    if (argv[0] !== '--handoff-root' || argv[2] !== '--' || argv.length < 5) {
        throw new Error('usage: chromium_observer_run.js --handoff-root ABS -- COMMAND run ...');
    }
    const root = path.resolve(argv[1]);
    const command = argv.slice(3);
    const repository = fs.realpathSync(option(command, '--repository'));
    const candidate = option(command, '--candidate');
    const lane = option(command, '--lane');
    const browser = fs.realpathSync(option(command, '--browser'));
    const archive = path.resolve(option(command, '--output'));
    const [target, family] = lane.split(':');
    if (!path.isAbsolute(argv[1]) || !['js', 'wasmJs'].includes(target) ||
            family !== 'Chromium' ||
            !/^[0-9a-f]{40}$/.test(candidate) ||
            !root.startsWith('/var/home/stewart/') || root.startsWith(repository + '/') ||
            !archive.startsWith('/var/home/stewart/')) {
        throw new Error('observer run scope or home paths differ');
    }
    fs.mkdirSync(root, {mode: 0o700});
    const out = fs.openSync(path.join(root, 'consumer.stdout'), 'wx', 0o600);
    const err = fs.openSync(path.join(root, 'consumer.stderr'), 'wx', 0o600);
    const consumer = spawn(command[0], command.slice(1),
        {cwd: repository, env: {...process.env, DYN4K_BROWSER_OBSERVER_ROOT: root},
            stdio: ['ignore', out, err]});
    fs.closeSync(out);
    fs.closeSync(err);
    try {
        const modules = [];
        for (const module of ['core', 'facade']) {
            modules.push(await moduleHandoff(root, repository, candidate, target,
                browser, archive, consumer, module));
        }
        if (await exitOf(consumer, 120000) !== 0) {
            throw new Error('browser consumer failed after observer handoff');
        }
        unique(path.join(root, 'handoff-result.json'), {candidate_sha: candidate,
            lane, archive, command, modules, completed_ns: Date.now() * 1000000,
            controller_source_sha256: hash(fs.readFileSync(__filename))});
        process.stdout.write(JSON.stringify({archive, observer_root: root, modules}) + '\n');
    } finally {
        if (consumer.exitCode === null && consumer.signalCode === null) {
            consumer.kill('SIGTERM');
        }
    }
}
if (require.main === module) main(process.argv.slice(2)).catch(error => {
    process.stderr.write(`Chromium observer handoff: ${error.stack || error}\n`);
    process.exitCode = 1;
});
module.exports = {waitFor, option};
