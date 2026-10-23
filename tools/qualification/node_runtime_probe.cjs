const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const argv = process.argv;
const jsRunner = argv.includes('--require') && argv.some(part =>
  part.endsWith('/kotlin-test-nodejs-runner.js')) && argv.some(part =>
  part.endsWith('-test.js'));
const wasmRunner = argv.length === 2 && argv[1].endsWith('/runUnitTests.mjs');

if (process.platform === 'linux' && (jsRunner || wasmRunner)) {
  const directory = process.env.DYN4K_NODE_OBSERVATION_DIR;
  if (!directory || !path.isAbsolute(directory)) throw new Error('Node observation directory is absent');
  const nonce = crypto.randomBytes(16).toString('hex');
  const base = `${process.pid}-${nonce}`;
  const request = path.join(directory, `${base}.json`);
  const pending = path.join(directory, `${base}.pending`);
  const acknowledgement = path.join(directory, `${base}.ack`);
  fs.writeFileSync(pending, JSON.stringify({pid: process.pid, nonce,
    argv, execPath: process.execPath, version: process.version}), {flag: 'wx', mode: 0o600});
  fs.renameSync(pending, request);
  const pause = new Int32Array(new SharedArrayBuffer(4));
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    try {
      if (fs.readFileSync(acknowledgement, 'utf8') === nonce) break;
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
    Atomics.wait(pause, 0, 0, 10);
  }
  if (!fs.existsSync(acknowledgement) ||
      fs.readFileSync(acknowledgement, 'utf8') !== nonce) {
    throw new Error('Node process observation was not acknowledged');
  }
}
