// Bounded same-run consistency checker. No trajectory budgets or port qualification.
import assert from 'node:assert/strict';
import { createReadStream, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { createGunzip } from 'node:zlib';
import { createInterface } from 'node:readline';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

function finite(value, path = 'snapshot') {
  if (typeof value === 'number') assert.ok(Number.isFinite(value), `nonfinite ${path}`);
  else if (Array.isArray(value)) value.forEach((v, i) => finite(v, `${path}[${i}]`));
  else if (value !== null && typeof value === 'object') {
    for (const [key, child] of Object.entries(value)) finite(child, `${path}.${key}`);
  }
}

// Object key order is immaterial; missing/extra keys and nonfinite values fail.
function same(a, b) {
  if (typeof a === 'number' || typeof b === 'number') return Number.isFinite(a) && Number.isFinite(b) && a === b;
  if (a === null || b === null || typeof a !== 'object' || typeof b !== 'object') return a === b;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const keys = Object.keys(a), other = Object.keys(b);
  return keys.length === other.length && keys.every(key => Object.hasOwn(b, key) && same(a[key], b[key]));
}
function exact(a, b, label) { assert.ok(same(a, b), label); }
function keys(value, expected, label) {
  assert.ok(value !== null && typeof value === 'object' && !Array.isArray(value), `${label} schema`);
  exact(Object.keys(value).sort(), [...expected].sort(), `${label} schema keys`);
}
function transformAliases(t) {
  keys(t, ['getCost', 'getSint', 'getRotationAngle', 'getTranslation', 'getTranslationX', 'getTranslationY', 'getValues', 'isIdentity', 'type'], 'transform');
  assert.ok(t && typeof t.getRotationAngle === 'number' && typeof t.isIdentity === 'boolean', 'transform schema');
  exact(t.getTranslation, [t.getTranslationX, t.getTranslationY], 'translation alias');
  exact(t.getValues, [t.getCost, -t.getSint, t.getTranslationX, t.getSint, t.getCost, t.getTranslationY], 'matrix alias');
}

const duplicates = {
  getForce: 'force', getAccumulatedForce: 'accumulatedForce', getTorque: 'torque',
  getAccumulatedTorque: 'accumulatedTorque', getLinearVelocity: 'velocity',
  getAngularVelocity: 'angularVelocity', getTransform: 'transform',
  getPreviousTransform: 'previousTransform', getWorldCenter: 'worldCenter', isAtRest: 'atRest',
};
const bodyFields = ['id', 'atRest', 'force', 'accumulatedForce', 'torque', 'accumulatedTorque',
  'velocity', 'angularVelocity', 'worldCenter', 'fixedOriginPosition', 'transform', 'previousTransform',
  'rotationIncrementSum', 'rotationStepBoundBelowPi', 'rotationTrackingScope'];
const propertyFields = [...Object.keys(duplicates), 'getAngularDamping', 'getChangeInOrientation',
  'getChangeInPosition', 'getFixtureCount', 'getGravityScale', 'getLinearDamping', 'getLocalCenter',
  'getMass', 'getRotationDiscRadius', 'isAtRestDetectionEnabled', 'isBullet', 'isDynamic', 'isEnabled',
  'isKinematic', 'isStatic', 'type'];

export function checkSnapshot(state, {phase, prior} = {}) {
  assert.ok(['initial', 'step', 'before', 'after'].includes(phase), 'snapshot phase');
  keys(state, ['bodies', 'joints'], 'state');
  finite(state);
  assert.equal(state.bodies.length, 2, 'two bodies');
  exact(state.joints, [], 'no joints');
  state.bodies.forEach((b, i) => {
    keys(b, phase === 'step' ? bodyFields : [...bodyFields, 'properties', 'fixtures'], 'body');
    assert.equal(b.id, `b${i}`, 'body identity');
    assert.equal(typeof b.atRest, 'boolean', 'atRest schema');
    assert.ok(Number.isFinite(b.rotationIncrementSum), 'rotation accumulator schema');
    assert.ok(Number.isFinite(b.angularVelocity), 'angular velocity schema');
    assert.ok(Array.isArray(b.velocity) && b.velocity.length === 2 && b.velocity.every(Number.isFinite), 'velocity schema');
    exact(b.force, [0, 0], 'force zero');
    exact(b.accumulatedForce, [0, 0], 'accumulated force zero');
    exact(b.torque, 0, 'torque zero');
    exact(b.accumulatedTorque, 0, 'accumulated torque zero');
    transformAliases(b.transform); transformAliases(b.previousTransform);
    exact(b.worldCenter, b.transform.getTranslation, 'world center alias');
    exact(b.fixedOriginPosition, b.worldCenter, 'fixed origin alias');
    if (phase !== 'step') {
      assert.ok(b.properties && b.fixtures?.length === 1, 'snapshot properties and fixtures required');
      keys(b.properties, propertyFields, 'properties');
      for (const [getter, field] of Object.entries(duplicates)) exact(b.properties[getter], b[field], `duplicate ${getter}`);
      exact(b.properties.getLocalCenter, [0, 0], 'local center alias premise');
      exact(b.properties.getMass?.getCenter, [0, 0], 'mass center alias premise');
    }
    if (i === 0) {
      exact(b.transform.getTranslation, [0, -0.25], 'floor pose');
      exact([b.transform.getCost, b.transform.getSint, b.transform.getRotationAngle], [1, 0, 0], 'floor rotation');
      exact(b.velocity, [0, 0], 'floor velocity'); exact(b.angularVelocity, 0, 'floor angular velocity');
      exact(b.rotationIncrementSum, 0, 'floor rotation accumulator');
      exact(b.previousTransform, b.transform, 'floor previous pose');
    }
    if (i === 1 && b.atRest) {
      exact(b.velocity, [0, 0], 'sleep velocity'); exact(b.angularVelocity, 0, 'sleep angular velocity');
      if (prior?.bodies[i].atRest) exact(b.transform, prior.bodies[i].transform, 'sleep pose freeze');
    }
    if (phase === 'initial') exact(b.previousTransform, b.transform, 'initial previous copy');
    else {
      assert.ok(prior, 'prior snapshot required');
      exact(b.previousTransform, phase === 'step' ? prior.bodies[i].transform : prior.bodies[i].previousTransform, 'phase-correct previous copy');
      if (phase === 'before' || phase === 'after') exact(b.transform, prior.bodies[i].transform, 'action current pose copy');
    }
  });
}

export function checkImpulse(before, after) {
  finite(before); finite(after);
  const pre = before.bodies[1], post = after.bodies[1];
  exact([pre.atRest, pre.velocity, pre.angularVelocity], [true, [0, 0], 0], 'impulse sleeping input');
  exact([post.atRest, post.velocity, post.angularVelocity], [false, [1, 0], 0], 'impulse immediate output');
  // Only these recorded fields may change during the center-impulse call.
  const expected = structuredClone(before);
  expected.bodies[1].atRest = false; expected.bodies[1].velocity = [1, 0];
  expected.bodies[1].properties.isAtRest = false;
  expected.bodies[1].properties.getLinearVelocity = [1, 0];
  exact(after, expected, 'impulse unchanged fields (including fixtures, mass, poses, forces and accumulator)');
}

export function checkTimeStep(dt, hz, step) {
  assert.ok([30, 60, 120].includes(hz) && Number.isInteger(step) && step >= 1, 'timestep scope');
  const old = step === 1 ? 1 / 60 : 1 / hz;
  for (const [key, value] of Object.entries({getDeltaTime: 1/hz, getInverseDeltaTime: hz,
    getPrevousDeltaTime: old, getPreviousInverseDeltaTime: 1/old, getDeltaTimeRatio: (1/hz)/old})) {
    exact(dt[key], value, `timestep ${key}`);
  }
}

async function digest(path) {
  const hash = createHash('sha256');
  for await (const bytes of createReadStream(path)) hash.update(bytes);
  return hash.digest('hex');
}

export async function auditReference(root, candidate) {
  const hz = candidate.hz, path = join(root, 'run1', `S-sleep-wake-hz${hz}-0.jsonl.gz`);
  assert.equal(await digest(path), candidate.gzip_sha256, 'compressed identity guard');
  const hash = createHash('sha256'), stream = createReadStream(path).pipe(createGunzip());
  stream.on('data', bytes => hash.update(bytes));
  const lines = createInterface({input: stream, crlfDelay: Infinity});
  const counts = {initial: 0, step: 0, before: 0, after: 0, impulse: 0, timestep: 0, listeners: 0};
  const kinds = {};
  let prior, before, states = 0, order = 0, orderedStep = 0, actionPhase = 0, initialized = false;
  let firstSleep = null, returnSleep = null;
  try {
    for await (const line of lines) {
      const row = JSON.parse(line);
      kinds[row.kind] = (kinds[row.kind] ?? 0) + 1;
      if (row.kind !== 'inputs') {
        assert.ok(initialized, 'inputs first'); assert.equal(row.step, states + 1, 'record step');
      }
      if ('order' in row) {
        if (orderedStep !== row.step) { orderedStep = row.step; order = 0; }
        assert.equal(row.order, order++, 'record order');
      }
      switch (row.kind) {
        case 'inputs':
          assert.ok(!initialized && states === 0, 'one initial snapshot');
          assert.equal(createHash('sha256').update(line).digest('hex'), candidate.input_sha256_utf8_without_newline, 'input identity guard');
          assert.equal(row.dt, 1/hz); assert.equal(row.steps, 600*hz);
          checkSnapshot(row.state, {phase: 'initial'}); counts.initial++; prior = row.state; initialized = true;
          break;
        case 'instrumented-callback': {
          assert.equal(row.step, 300*hz+1, 'action step'); assert.equal(row.values.length, 1);
          const phase = row.event === 'before-wake' ? 'before' : row.event === 'after-wake' ? 'after' : null;
          assert.ok(phase, 'known action snapshot');
          assert.equal(actionPhase, phase === 'before' ? 0 : 2, 'before/action/after sequence');
          assert.equal(row.order, phase === 'before' ? 0 : 2, 'immediate boundary order');
          checkSnapshot(row.values[0], {phase, prior}); counts[phase]++;
          if (phase === 'before') { before = row.values[0]; actionPhase = 1; }
          else { checkImpulse(before, row.values[0]); counts.impulse++; prior = row.values[0]; actionPhase = 3; }
          break;
        }
        case 'action':
          assert.equal(row.step, 300*hz+1); assert.equal(row.order, 1); assert.equal(actionPhase, 1, 'action sequence');
          assert.equal(row.description, 'impulse=(1,0) at center; sleepingBefore=true; precedingSecondAsleep=true', 'action identity');
          actionPhase = 2; break;
        case 'event':
          if (row.step === 300*hz+1) assert.equal(actionPhase, 3, 'physics callbacks follow immediate action');
          counts.listeners++;
          if (row.listener === 'StepListener') { checkTimeStep(row.payload[0], hz, row.step); counts.timestep++; }
          break;
        case 'state':
          if (row.step === 300*hz+1) assert.equal(actionPhase, 3, 'complete action before next physics state');
          checkSnapshot(row.state, {phase: 'step', prior}); counts.step++; states++;
          if (row.state.bodies[1].atRest) {
            firstSleep ??= states;
            if (states > 300*hz+1) returnSleep ??= states;
          }
          prior = row.state; break;
        default: assert.fail(`unknown record ${row.kind}`);
      }
    }
  } finally { lines.close(); stream.destroy(); }
  assert.equal(hash.digest('hex'), candidate.decompressed_sha256_including_newlines, 'decompressed identity guard');
  assert.equal(states, 600*hz); exact(kinds, candidate.records_by_kind, 'record counts');
  assert.equal(firstSleep, candidate.first_sleep_step); assert.equal(returnSleep, candidate.first_return_to_sleep_step);
  exact([counts.initial, counts.before, counts.after, counts.impulse], [1, 1, 1, 1], 'snapshot coverage');
  return {hz, gzipSha256: candidate.gzip_sha256, decompressedSha256: candidate.decompressed_sha256_including_newlines,
    counts, firstSleep, returnSleep, status: 'BOUNDED_EXACT_CHECKS_PASS_NOT_PORT_QUALIFICATION'};
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  assert.equal(process.argv.length, 3, 'Supply extracted dyn4k-sleep-evidence directory');
  const manifest = JSON.parse(readFileSync(new URL('./initial-reference-review-manifest.json', import.meta.url), 'utf8'));
  const results = [];
  for (const candidate of manifest.sleep_candidates) results.push(await auditReference(process.argv[2], candidate));
  console.log(JSON.stringify({scope: 'APPROVED_EXACT_RELATIONSHIPS_FROZEN_BASELINE_ONLY', results}, null, 2));
}
