// Frozen-reference observations only. Does not compare or qualify a port.
// Usage: node sleep-wake-budget-audit.mjs EXTRACTED_DYN4K_SLEEP_EVIDENCE
import { createReadStream, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { createGunzip } from 'node:zlib';
import { createInterface } from 'node:readline';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const manifest = JSON.parse(readFileSync(fileURLToPath(new URL(
  './initial-reference-review-manifest.json', import.meta.url)), 'utf8'));
const root = process.argv[2];
assert.equal(process.argv.length, 3, 'Supply the extracted dyn4k-sleep-evidence directory');
const results = [];
const equal = (a, b) => {
  try { assert.deepEqual(a, b); return true; }
  catch (error) { if (error.code === 'ERR_ASSERTION') return false; throw error; }
};
// Numeric equality treats signed zeros as equal, recursively.
const numericEqual = (a, b) => JSON.stringify(a) === JSON.stringify(b);
for (const candidate of manifest.sleep_candidates) {
  const hz = candidate.hz;
  const path = join(root, 'run1', `S-sleep-wake-hz${hz}-0.jsonl.gz`);
  assert.equal(createHash('sha256').update(readFileSync(path)).digest('hex'), candidate.gzip_sha256);
  const hash = createHash('sha256');
  const stream = createReadStream(path).pipe(createGunzip());
  stream.on('data', bytes => hash.update(bytes));
  const lines = createInterface({ input: stream, crlfDelay: Infinity });
  const kinds = {}, methods = {}, checks = {}, diagnostics = {}, numericPaths = {};
  const check = (name, passed, step) => {
    const entry = checks[name] ??= { checked: 0, failures: 0, firstFailureStep: null };
    entry.checked++;
    if (!passed) { entry.failures++; entry.firstFailureStep ??= step; }
  };
  const diagnostic = (name, passed, step) => {
    const entry = diagnostics[name] ??= { checked: 0, mismatches: 0, firstMismatchStep: null };
    entry.checked++;
    if (!passed) { entry.mismatches++; entry.firstMismatchStep ??= step; }
  };
  const inventory = (value, prefix) => {
    if (typeof value === 'number') {
      assert.ok(Number.isFinite(value), `Nonfinite ${prefix}`);
      const metric = numericPaths[prefix] ??= { count: 0, min: value, max: value };
      metric.count++;
      metric.min = Math.min(metric.min, value);
      metric.max = Math.max(metric.max, value);
    } else if (Array.isArray(value)) {
      value.forEach(child => inventory(child, `${prefix}[]`));
    } else if (value !== null && typeof value === 'object') {
      for (const [key, child] of Object.entries(value)) inventory(child, `${prefix}.${key}`);
    }
  };
  let input, prior, before, after, states = 0, order = 0, orderedStep = 0;
  let firstSleep = null, returnSleep = null, precedingSleep = 0;
  const phases = {};
  for await (const line of lines) {
    const row = JSON.parse(line);
    kinds[row.kind] = (kinds[row.kind] ?? 0) + 1;
    if (row.kind !== 'inputs') assert.equal(row.step, states + 1);
    if ('order' in row) {
      if (orderedStep !== row.step) { order = 0; orderedStep = row.step; }
      assert.equal(row.order, order++);
    }
    switch (row.kind) {
      case 'inputs':
        assert.equal(createHash('sha256').update(line).digest('hex'), candidate.input_sha256_utf8_without_newline);
        assert.equal(row.dt, 1 / hz);
        assert.equal(row.steps, 600 * hz);
        input = row; prior = row.state;
        inventory(row.state, 'input.state');
        break;
      case 'event': {
        methods[row.method] = (methods[row.method] ?? 0) + 1;
        inventory(row.payload, `event.${row.method}.payload`);
        if (row.listener === 'StepListener') {
          const dt = row.payload[0];
          const old = row.step === 1 ? 1 / 60 : input.dt;
          check('fixedTimeStepPayload', dt.getDeltaTime === input.dt
            && dt.getInverseDeltaTime === 1 / input.dt
            && dt.getPrevousDeltaTime === old && dt.getPreviousInverseDeltaTime === 1 / old
            && dt.getDeltaTimeRatio === input.dt / old, row.step);
        }
        break;
      }
      case 'instrumented-callback':
        inventory(row.values, `snapshot.${row.event}`);
        if (row.event === 'before-wake') before = row.values[0];
        else if (row.event === 'after-wake') after = row.values[0];
        else assert.fail(`Unknown snapshot: ${row.event}`);
        break;
      case 'action': assert.equal(row.step, 300 * hz + 1); break;
      case 'state': {
        states++;
        const state = row.state, dynamic = state.bodies[1];
        inventory(state, 'state');
        const phase = states <= 300 * hz ? (dynamic.atRest ? 'preImpulseSleeping' : 'initialSettling')
          : (dynamic.atRest ? 'postImpulseSleeping' : 'wakeSettling');
        const phaseRow = phases[phase] ??= { states: 0, firstStep: states, lastStep: states };
        phaseRow.states++; phaseRow.lastStep = states;
        check('twoBodiesNoJoints', state.bodies.length === 2 && state.joints.length === 0, states);
        for (let i = 0; i < 2; i++) {
          const body = state.bodies[i], t = body.transform;
          check('stableBodyIds', body.id === `b${i}`, states);
          check('zeroAppliedAndAccumulatedForceTorque', numericEqual(body.force, [0, 0])
            && numericEqual(body.accumulatedForce, [0, 0]) && body.torque === 0 && body.accumulatedTorque === 0, states);
          for (const transform of [t, body.previousTransform]) {
            check('transformGetterConsistency', transform.getTranslationX === transform.getTranslation[0]
              && transform.getTranslationY === transform.getTranslation[1]
              && numericEqual(transform.getValues, [transform.getCost, -transform.getSint,
                transform.getTranslationX, transform.getSint, transform.getCost, transform.getTranslationY]), states);
          }
          check('zeroLocalCenterAndOriginPositionAliases', numericEqual(body.worldCenter, t.getTranslation)
            && numericEqual(body.fixedOriginPosition, body.worldCenter), states);
          if (body.atRest) check('sleepingVelocityZero', numericEqual(body.velocity, [0, 0]) && body.angularVelocity === 0, states);
          if (body.atRest && prior.bodies[i].atRest) diagnostic('consecutiveSleepTransformFreeze', numericEqual(t, prior.bodies[i].transform), states);
          diagnostic(`body${i}PreviousEqualsPrecedingCurrent`, numericEqual(body.previousTransform, prior.bodies[i].transform), states);
        }
        const floor = state.bodies[0];
        check('staticFloorTransformAndVelocity', numericEqual(floor.transform, input.state.bodies[0].transform)
          && numericEqual(floor.velocity, [0, 0]) && floor.angularVelocity === 0 && floor.rotationIncrementSum === 0, states);
        if (dynamic.atRest) {
          firstSleep ??= states;
          if (states > 300 * hz + 1) returnSleep ??= states;
          if (states >= 299 * hz && states <= 300 * hz) precedingSleep++;
        }
        prior = state;
        break;
      }
      default: assert.fail(`Unknown record kind: ${row.kind}`);
    }
  }
  assert.equal(hash.digest('hex'), candidate.decompressed_sha256_including_newlines);
  assert.equal(states, 600 * hz);
  assert.ok(equal(kinds, candidate.records_by_kind));
  assert.equal(firstSleep, candidate.first_sleep_step);
  assert.equal(returnSleep, candidate.first_return_to_sleep_step);
  assert.equal(precedingSleep, hz + 1);
  const pre = before.bodies[1], post = after.bodies[1];
  check('impulseActionExactVelocityAndFlags', pre.atRest && !post.atRest
    && numericEqual(pre.velocity, [0, 0]) && pre.angularVelocity === 0
    && numericEqual(post.velocity, [1, 0]) && post.angularVelocity === 0, 300 * hz + 1);
  check('impulseLeavesBothTransformsUnchanged', before.bodies.every((body, i) =>
    numericEqual(body.transform, after.bodies[i].transform)
    && numericEqual(body.previousTransform, after.bodies[i].previousTransform)), 300 * hz + 1);
  results.push({ hz, gzipSha256: candidate.gzip_sha256, states, kinds, methods,
    firstSleep, returnSleep, precedingSleep, phases, checks, diagnostics, numericPaths });
}
console.log(JSON.stringify({ scope: 'FROZEN_BASELINE_OBSERVATIONS_NOT_PORT_QUALIFICATION', results }, null, 2));
if (results.some(row => Object.values(row.checks).some(check => check.failures > 0))) process.exitCode = 1;
