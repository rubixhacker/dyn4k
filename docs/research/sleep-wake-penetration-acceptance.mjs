// Frozen baseline only. Exit 0: physical pass; 2: complete physical failure; 1: invalid evidence.
import assert from 'node:assert/strict';
import { createReadStream, readFileSync, writeFileSync, mkdirSync, openSync, writeSync, closeSync, unlinkSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { createGunzip, gzipSync } from 'node:zlib';
import { createInterface } from 'node:readline';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

// One integer unit is 2^-1075 m: half the smallest positive binary64.
export const SCALE = 1n << 1075n;
export function exact(x) {
  assert.equal(typeof x, 'number'); assert.ok(Number.isFinite(x), 'finite binary64 required');
  const b = Buffer.alloc(8); b.writeDoubleBE(x);
  const bits = b.readBigUInt64BE(), exponent = Number((bits >> 52n) & 2047n);
  const fraction = bits & ((1n << 52n) - 1n);
  const magnitude = exponent === 0 ? fraction << 1n : ((1n << 52n) + fraction) << BigInt(exponent);
  return bits >> 63n ? -magnitude : magnitude;
}
const abs = x => x < 0n ? -x : x;
export const depth = (s, c, y) => {
  const d = (abs(exact(s)) + abs(exact(c))) / 2n - exact(y);
  return d > 0n ? d : 0n;
};
export const accepts = (d, denominator) => denominator === 0 ? d === 0n : d * BigInt(denominator) <= SCALE;
const ends = { 30: [0, 3, 17, 9000, 9021, 18000], 60: [2, 5, 34, 18000, 18042, 36000], 120: [4, 7, 65, 36000, 36083, 72000] };
export const names = ['initial-approach', 'impact', 'initial-settling', 'rest-before', 'wake-settling', 'rest-after'];
export const denominators = [0, 100, 200, 1000, 200, 1000];
export function phase(hz, step) {
  assert.ok(ends[hz] && Number.isInteger(step) && step >= 1 && step <= hz * 600, 'invalid Hz/step');
  return ends[hz].findIndex(end => step <= end);
}
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
function fraction(n, d = SCALE) {
  let a = abs(n), b = d;
  while (b) [a, b] = [b, a % b];
  return `${n / a}/${d / a}`;
}
function measure(d, step) { return { step, exactMetres: fraction(d), approximateMetres: Number(d >> 1000n) / 2 ** 75 }; }
export function checkGeometry(bodies, input = false) {
  assert.deepEqual(bodies.map(b => b.id), ['b0', 'b1']);
  const [floor, square] = bodies.map(b => b.transform);
  assert.deepEqual([floor.getCost, floor.getSint, floor.getTranslationX, floor.getTranslationY], [1, 0, 0, -0.25]);
  for (const t of [floor, square]) for (const key of ['getCost', 'getSint', 'getTranslationX', 'getTranslationY']) exact(t[key]);
  if (input) {
    assert.equal(bodies[0].fixtures.length, 1); assert.equal(bodies[1].fixtures.length, 1);
    assert.deepEqual(bodies[0].fixtures[0].shape.getVertices, [[-10,-0.25],[10,-0.25],[10,0.25],[-10,0.25]]);
    assert.deepEqual(bodies[1].fixtures[0].shape.getVertices, [[-0.5,-0.5],[0.5,-0.5],[0.5,0.5],[-0.5,0.5]]);
  }
  const extent = (abs(exact(square.getCost)) + abs(exact(square.getSint))) / 2n;
  assert.ok(abs(exact(square.getTranslationX)) + extent <= 10n * SCALE, 'square outside finite floor span');
  return square;
}
export async function audit(root, output) {
  const bytes = readFileSync(new URL('./initial-reference-review-manifest.json', import.meta.url));
  assert.equal(sha(bytes), 'b42174c7523bea9687e4ab015a215b4e652c2446df73d2f41e836e8a165c1208');
  const manifest = JSON.parse(bytes), sources = {};
  for (const [path, expected] of Object.entries(manifest.sleep_sources)) {
    sources[path] = sha(readFileSync(join(root, path))); assert.equal(sources[path], expected, `source hash ${path}`);
  }
  // Check all member identities before writing any output; semantic checks are separately testable.
  for (const c of manifest.sleep_candidates) assert.equal(sha(readFileSync(join(root, 'run1', `S-sleep-wake-hz${c.hz}-0.jsonl.gz`))), c.gzip_sha256, 'gzip hash');
  mkdirSync(output, { recursive: true });
  const detailsPath = join(output, 'failures.jsonl'), fd = openSync(detailsPath, 'w');
  const results = []; let total = 0, failed = 0;
  try {
    for (const c of manifest.sleep_candidates) {
      const phases = names.map((name, i) => ({ name, first: i ? ends[c.hz][i-1]+1 : 1, last: ends[c.hz][i], ceiling: i === 0 ? '0/1' : `1/${denominators[i]}`, count: 0, failed: 0, failureRanges: [], minimum: null, maximum: null, closestBoundary: null }));
      const mins = [], maxes = [], closest = [], counts = {};
      const raw = createHash('sha256');
      const stream = createReadStream(join(root, 'run1', `S-sleep-wake-hz${c.hz}-0.jsonl.gz`)).pipe(createGunzip());
      stream.on('data', chunk => raw.update(chunk));
      let states = 0;
      for await (const line of createInterface({ input: stream, crlfDelay: Infinity })) {
        const row = JSON.parse(line); counts[row.kind] = (counts[row.kind] ?? 0) + 1;
        if (row.kind === 'inputs') {
          assert.equal(states, 0); assert.equal(counts.inputs, 1);
          assert.equal(sha(line), c.input_sha256_utf8_without_newline, 'input hash');
          checkGeometry(row.state.bodies, true); assert.equal(row.steps, c.hz * 600);
        }
        if (row.kind !== 'state') continue;
        assert.equal(counts.inputs, 1); assert.equal(row.step, ++states);
        const t = checkGeometry(row.state.bodies), i = phase(c.hz, row.step), p = phases[i], den = denominators[i];
        const d = depth(t.getSint, t.getCost, t.getTranslationY);
        const margin = den === 0 ? -d : SCALE - d * BigInt(den);
        p.count++; total++;
        if (mins[i] === undefined || d < mins[i]) { mins[i] = d; p.minimum = measure(d, row.step); }
        if (maxes[i] === undefined || d > maxes[i]) { maxes[i] = d; p.maximum = measure(d, row.step); }
        if (closest[i] === undefined || abs(margin) < closest[i]) {
          closest[i] = abs(margin); p.closestBoundary = { ...measure(d, row.step), signedHeadroomMetres: fraction(margin, SCALE * BigInt(den || 1)) };
        }
        if (!accepts(d, den)) {
          failed++; p.failed++;
          const last = p.failureRanges.at(-1);
          if (last && last[1] === row.step - 1) last[1] = row.step; else p.failureRanges.push([row.step, row.step]);
          writeSync(fd, JSON.stringify({ hz: c.hz, step: row.step, phase: p.name, ceiling: p.ceiling, depth: fraction(d), excess: fraction(-margin, SCALE * BigInt(den || 1)), s: t.getSint, c: t.getCost, ty: t.getTranslationY }) + '\n');
        }
      }
      assert.equal(raw.digest('hex'), c.decompressed_sha256_including_newlines, 'decompressed hash');
      assert.deepEqual(counts, c.records_by_kind); assert.equal(states, c.hz * 600);
      results.push({ hz: c.hz, states, gzipSha256: c.gzip_sha256, rawSha256: c.decompressed_sha256_including_newlines, inputSha256: c.input_sha256_utf8_without_newline, phases });
    }
  } finally { closeSync(fd); }
  assert.equal(total, 126000);
  const compressed = gzipSync(readFileSync(detailsPath), { level: 9 });
  writeFileSync(detailsPath + '.gz', compressed); unlinkSync(detailsPath);
  const result = { status: failed ? 'COMPLETE_PHYSICAL_FAIL' : 'COMPLETE_PHYSICAL_PASS', semantics: 'Exact mathematical geometry of stored binary64 coefficients; no trig normalization or runtime rounding allowance', total, passed: total - failed, failed, manifestSha256: sha(bytes), sources, failureDetailsSha256: sha(compressed), results };
  writeFileSync(join(output, 'observations.json'), JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify({ status: result.status, total, failed, passed: result.passed }));
  return failed ? 2 : 0;
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  assert.equal(process.argv.length, 4, 'Usage: node evaluator.mjs EXTRACTED_ROOT OUTPUT_DIR');
  process.exitCode = await audit(process.argv[2], process.argv[3]);
}
