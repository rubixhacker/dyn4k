// Inspects frozen bytes only; the emitted schedule is a proposal, not acceptance.
// Usage: node sleep-wake-penetration-phases.mjs EXTRACTED_DYN4K_SLEEP_EVIDENCE
import assert from 'node:assert/strict';
import { createReadStream, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { createGunzip } from 'node:zlib';
import { createInterface } from 'node:readline';
import { join } from 'node:path';

assert.equal(process.argv.length, 3, 'Supply the extracted dyn4k-sleep-evidence directory');
const root = process.argv[2];
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const manifestBytes = readFileSync(new URL('./initial-reference-review-manifest.json', import.meta.url));
const manifestHash = sha(manifestBytes);
assert.equal(manifestHash, 'b42174c7523bea9687e4ab015a215b4e652c2446df73d2f41e836e8a165c1208');
const manifest = JSON.parse(manifestBytes);
const sources = {};
for (const [path, expected] of Object.entries(manifest.sleep_sources)) {
  sources[path] = sha(readFileSync(join(root, path)));
  assert.equal(sources[path], expected);
}
const results = [];
for (const candidate of manifest.sleep_candidates) {
  const hz = candidate.hz;
  const gzipHash = sha(readFileSync(join(root, 'run1', `S-sleep-wake-hz${hz}-0.jsonl.gz`)));
  assert.equal(gzipHash, candidate.gzip_sha256);
  const rawHash = createHash('sha256');
  const stream = createReadStream(join(root, 'run1', `S-sleep-wake-hz${hz}-0.jsonl.gz`)).pipe(createGunzip());
  stream.on('data', bytes => rawHash.update(bytes));
  const counts = {}, listeners = {}, methods = {}, firstEvents = {}, contactChanges = [], sleepChanges = [], toiPayloads = [], snapshots = [], initialStates = [];
  let states = 0, order = 0, contactCount = 0, lastContactCount = 0, previousSleep, action;
  let stepContactCollision = false, contactBearingSamples = 0, contactGaps = 0, firstContact, firstSolve, firstPostSolve;
  for await (const line of createInterface({ input: stream, crlfDelay: Infinity })) {
    const row = JSON.parse(line);
    counts[row.kind] = (counts[row.kind] ?? 0) + 1;
    if (row.kind === 'inputs') {
      assert.equal(states, 0); assert.equal(counts.inputs, 1);
      assert.equal(sha(line), candidate.input_sha256_utf8_without_newline);
      assert.equal(row.steps, hz * 600); assert.equal(row.dt, 1 / hz);
      previousSleep = row.state.bodies[1].atRest;
      continue;
    }
    assert.equal(row.step, states + 1);
    if ('order' in row) assert.equal(row.order, order++);
    if (row.kind === 'event') {
      listeners[row.listener] = (listeners[row.listener] ?? 0) + 1;
      const method = row.method.match(/\.([^.()]+)\(/)[1];
      const key = `${row.listener}.${method}`;
      methods[key] = (methods[key] ?? 0) + 1;
      firstEvents[key] ??= { step: row.step, order: row.order, signature: row.method };
      if (row.listener === 'ContactListener') {
        const pair = row.payload[0];
        assert.deepEqual([pair.body1, pair.body2].sort(), ['b0', 'b1']);
        if (method === 'begin') { contactCount++; firstContact ??= row.step; }
        if (method === 'end' || method === 'destroyed') contactCount--;
        assert.ok(contactCount >= 0);
        if (method === 'preSolve') firstSolve ??= row.step;
        if (method === 'postSolve' && firstPostSolve === undefined) {
          assert.equal(row.payload[1].isSolved, true);
          assert.equal(row.payload[1].isIgnored, false);
          firstPostSolve = { step: row.step, order: row.order, solved: true, ignored: false };
        }
        if (method === 'collision') {
          stepContactCollision = true;
          assert.equal(pair.constraint.contacts.length, contactCount);
        }
      }
      if (row.listener === 'TimeOfImpactListener') {
        for (const payload of row.payload) {
          if (payload?.type === 'org.dyn4j.collision.continuous.TimeOfImpact') {
            toiPayloads.push({ step: row.step, order: row.order, time: payload.getTime, signature: row.method });
          }
        }
      }
    } else if (row.kind === 'action') {
      assert.equal(row.step, candidate.action_step);
      action = { step: row.step, order: row.order, description: row.description };
    } else if (row.kind === 'instrumented-callback') {
      const b = row.values[0].bodies[1];
      snapshots.push({ event: row.event, step: row.step, order: row.order, atRest: b.atRest,
        velocity: b.velocity, angularVelocity: b.angularVelocity, transform: b.transform });
    } else if (row.kind === 'state') {
      states++;
      if (contactCount !== lastContactCount) contactChanges.push({ step: states, from: lastContactCount, to: contactCount });
      if (contactCount > 0) { contactBearingSamples++; if (!stepContactCollision) contactGaps++; }
      const b = row.state.bodies[1];
      if (b.atRest !== previousSleep) sleepChanges.push({ step: states, from: previousSleep, to: b.atRest });
      if (states <= 8) initialStates.push({ step: states, contactCount, atRest: b.atRest, transform: b.transform, velocity: b.velocity });
      previousSleep = b.atRest; lastContactCount = contactCount;
      order = 0; stepContactCollision = false;
    } else assert.fail(`Unknown record kind ${row.kind}`);
  }
  const decompressedHash = rawHash.digest('hex');
  assert.equal(decompressedHash, candidate.decompressed_sha256_including_newlines);
  assert.deepEqual(counts, candidate.records_by_kind);
  assert.deepEqual(listeners, candidate.events_by_listener);
  assert.equal(states, hz * 600);
  assert.deepEqual(sleepChanges, [
    { step: candidate.first_sleep_step, from: false, to: true },
    { step: candidate.action_step, from: true, to: false },
    { step: candidate.first_return_to_sleep_step, from: false, to: true },
  ]);
  assert.deepEqual(contactChanges, [{ step: firstContact, from: 0, to: 2 }]);
  assert.equal(contactBearingSamples, states - firstContact + 1);
  assert.equal(contactGaps, 0);
  assert.equal(toiPayloads.length, 2);
  assert.equal(toiPayloads[0].step, firstContact - 1);
  assert.equal(toiPayloads[1].step, firstContact - 1);
  assert.equal(firstSolve, firstContact + 1);
  assert.equal(firstPostSolve.step, firstSolve);
  const touchdown = initialStates.find(s => s.step === toiPayloads[0].step);
  assert.equal(touchdown.transform.getTranslationY, 0.5);
  assert.equal(touchdown.transform.getCost, 1);
  assert.equal(touchdown.transform.getSint, 0);
  assert.equal(snapshots.length, 2);
  assert.deepEqual(snapshots.map(s => [s.event, s.step, s.order, s.atRest, s.velocity, s.angularVelocity]), [
    ['before-wake', candidate.action_step, 0, true, [0, 0], 0],
    ['after-wake', candidate.action_step, 2, false, [1, 0], 0],
  ]);
  assert.equal(action.order, 1);
  assert.deepEqual(snapshots[0].transform, snapshots[1].transform);
  const schedule = [
    ['initial-approach', 1, toiPayloads[0].step - 1],
    ['impact', toiPayloads[0].step, firstSolve],
    ['settling', firstSolve + 1, candidate.first_sleep_step - 1],
    ['rest', candidate.first_sleep_step, candidate.action_step - 1],
    ['settling', candidate.action_step, candidate.first_return_to_sleep_step - 1],
    ['rest', candidate.first_return_to_sleep_step, states],
  ].filter(([, first, last]) => last >= first).map(([phase, first, last]) => ({ phase, first, last, count: last - first + 1 }));
  let covered = 0;
  for (const interval of schedule) {
    assert.equal(interval.first, covered + 1); assert.ok(interval.last >= interval.first); covered = interval.last;
  }
  assert.equal(covered, states);
  results.push({ hz, gzipHash, decompressedHash, inputHash: candidate.input_sha256_utf8_without_newline,
    states, counts, listeners, methods, firstEvents, toiPayloads, initialStates,
    firstContact, firstSolve, firstPostSolve, contactChanges, contactBearingSamples, contactGaps,
    sleepChanges, action, snapshots, proposedSchedule: schedule });
}
console.log(JSON.stringify({ status: 'VERIFIED_FROZEN_EVENTS_PROPOSED_PHASES_REQUIRE_LIVE_REVIEW',
  manifestHash, sources, results }, null, 2));
