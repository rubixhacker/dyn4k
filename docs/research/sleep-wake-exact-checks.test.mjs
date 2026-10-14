import test from 'node:test';
import assert from 'node:assert/strict';
import { createReadStream, mkdtempSync, mkdirSync, writeFileSync, rmSync, readFileSync } from 'node:fs';
import { createGunzip } from 'node:zlib';
import { createInterface } from 'node:readline';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { checkSnapshot, checkImpulse, checkTimeStep, auditReference } from './sleep-wake-exact-checks.mjs';

assert.ok(process.env.SLEEP_EVIDENCE, 'Set SLEEP_EVIDENCE to extracted frozen evidence');
const samples = {};
for (const hz of [30, 60, 120]) {
  const stream = createReadStream(join(process.env.SLEEP_EVIDENCE, 'run1', `S-sleep-wake-hz${hz}-0.jsonl.gz`)).pipe(createGunzip());
  const lines = createInterface({ input: stream });
  const s = samples[hz] = {};
  let prior;
  for await (const line of lines) {
    const row = JSON.parse(line);
    if (row.kind === 'inputs') s.initial = prior = row.state;
    if (row.kind === 'instrumented-callback') s[row.event === 'before-wake' ? 'before' : 'after'] = row.values[0];
    if (row.kind === 'state') {
      if (row.step === 1) s.first = row.state;
      if (row.state.bodies[1].atRest && !s.sleep) { s.sleep = row.state; s.preSleep = prior; }
      if (s.after) { s.next = row.state; break; }
      prior = row.state;
    }
  }
  lines.close(); stream.destroy();
}
const clone = structuredClone;
const context = (s, phase) => ({ phase: phase === 'sleep' ? 'step' : phase, prior: phase === 'initial' ? undefined : phase === 'before' ? s.before : phase === 'after' ? s.before : s.preSleep });

for (const [hzString, s] of Object.entries(samples)) {
  const hz = Number(hzString);
  for (const phase of ['initial', 'before', 'after', 'sleep']) {
    test(`${hz}Hz ${phase}: valid snapshot`, () => checkSnapshot(s[phase], context(s, phase)));
    for (const bodyIndex of [0, 1]) {
      for (const field of ['force', 'accumulatedForce', 'torque', 'accumulatedTorque']) {
        test(`${hz}Hz ${phase} b${bodyIndex}: rejects ${field}`, () => {
          const bad = clone(s[phase]);
          if (Array.isArray(bad.bodies[bodyIndex][field])) bad.bodies[bodyIndex][field][0] = 0.1;
          else bad.bodies[bodyIndex][field] = 0.1;
          assert.throws(() => checkSnapshot(bad, context(s, phase)), /force|torque/i);
        });
      }
      for (const transform of ['transform', 'previousTransform']) {
        for (const field of ['getTranslation', 'getValues']) {
          test(`${hz}Hz ${phase} b${bodyIndex}: rejects ${transform}.${field}`, () => {
            const bad = clone(s[phase]); bad.bodies[bodyIndex][transform][field][0] += 0.1;
            assert.throws(() => checkSnapshot(bad, context(s, phase)), /alias/i);
          });
        }
      }
      for (const field of ['worldCenter', 'fixedOriginPosition']) {
        test(`${hz}Hz ${phase} b${bodyIndex}: rejects ${field}`, () => {
          const bad = clone(s[phase]); bad.bodies[bodyIndex][field][0] += 0.1;
          assert.throws(() => checkSnapshot(bad, context(s, phase)), /alias/i);
        });
      }
      if (phase !== 'sleep') {
        for (const field of ['getForce', 'getAccumulatedForce', 'getTorque', 'getAccumulatedTorque', 'getLinearVelocity', 'getAngularVelocity', 'getTransform', 'getPreviousTransform', 'getWorldCenter', 'isAtRest']) {
          test(`${hz}Hz ${phase} b${bodyIndex}: rejects duplicate ${field}`, () => {
            const bad = clone(s[phase]); const p = bad.bodies[bodyIndex].properties;
            if (Array.isArray(p[field])) p[field][0] += 0.1;
            else if (typeof p[field] === 'object') p[field].getRotationAngle += 0.1;
            else if (typeof p[field] === 'boolean') p[field] = !p[field];
            else p[field] += 0.1;
            assert.throws(() => checkSnapshot(bad, context(s, phase)), /duplicate/i);
          });
        }
      }
    }
  }
  test(`${hz}Hz: rejects premature previous-transform advance`, () => {
    const bad = clone(s.first); bad.bodies[1].previousTransform = clone(bad.bodies[1].transform);
    assert.throws(() => checkSnapshot(bad, {phase: 'step', prior: s.initial}), /previous/i);
  });
  for (const phase of ['initial', 'before', 'after', 'sleep']) {
    test(`${hz}Hz ${phase}: signed zero accepted`, () => {
      const value = clone(s[phase]); value.bodies[0].force = [-0, -0];
      value.bodies[1].accumulatedTorque = -0;
      checkSnapshot(value, context(s, phase));
    });
    test(`${hz}Hz ${phase}: floor sleep flag may vary`, () => {
      const value = clone(s[phase]); value.bodies[0].atRest = !value.bodies[0].atRest;
      if (value.bodies[0].properties) value.bodies[0].properties.isAtRest = value.bodies[0].atRest;
      checkSnapshot(value, context(s, phase));
    });
    for (const badNumber of [NaN, Infinity, -Infinity]) {
      test(`${hz}Hz ${phase}: rejects nonfinite ${badNumber}`, () => {
        const value = clone(s[phase]); value.bodies[1].transform.getRotationAngle = badNumber;
        assert.throws(() => checkSnapshot(value, context(s, phase)), /nonfinite/);
      });
    }
    test(`${hz}Hz ${phase}: rejects absent force`, () => {
      const value = clone(s[phase]); delete value.bodies[1].force;
      assert.throws(() => checkSnapshot(value, context(s, phase)), /force|schema/);
    });
  }
  test(`${hz}Hz: rejects sleeping velocity`, () => {
    const value = clone(s.sleep); value.bodies[1].velocity[1] = 0.1;
    assert.throws(() => checkSnapshot(value, {phase: 'step', prior: s.preSleep}), /sleep/);
  });
  test(`${hz}Hz: rejects coherent floor displacement`, () => {
    const value = clone(s.first), b = value.bodies[0];
    for (const t of [b.transform, b.previousTransform]) {
      t.getTranslationY += 0.1; t.getTranslation[1] += 0.1; t.getValues[5] += 0.1;
    }
    b.worldCenter[1] += 0.1; b.fixedOriginPosition[1] += 0.1;
    assert.throws(() => checkSnapshot(value, {phase: 'step', prior: s.initial}), /floor/);
  });
  test(`${hz}Hz: awake dynamic pose is not an exact baseline match`, () => {
    const value = clone(s.first), b = value.bodies[1];
    b.transform.getTranslationX += 0.1; b.transform.getTranslation[0] += 0.1; b.transform.getValues[2] += 0.1;
    b.worldCenter[0] += 0.1; b.fixedOriginPosition[0] += 0.1;
    checkSnapshot(value, {phase: 'step', prior: s.initial});
  });
  test(`${hz}Hz: no auditor-angle recomputation imposed`, () => {
    const value = clone(s.first); value.bodies[1].transform.getRotationAngle = 0.02;
    checkSnapshot(value, {phase: 'step', prior: s.initial});
  });
  for (const phase of ['initial', 'before', 'after', 'sleep']) {
    for (const field of ['velocity', 'angularVelocity', 'worldCenter', 'rotationIncrementSum']) {
      test(`${hz}Hz ${phase}: rejects missing ${field}`, () => {
        const value = clone(s[phase]); delete value.bodies[1][field];
        if (value.bodies[1].properties) {
          const duplicate = {velocity: 'getLinearVelocity', angularVelocity: 'getAngularVelocity', worldCenter: 'getWorldCenter'}[field];
          if (duplicate) delete value.bodies[1].properties[duplicate];
        }
        assert.throws(() => checkSnapshot(value, context(s, phase)), /schema|alias/);
      });
    }
    test(`${hz}Hz ${phase}: rejects extra snapshot field`, () => {
      const value = clone(s[phase]); value.bodies[1].unknownNumeric = 1;
      assert.throws(() => checkSnapshot(value, context(s, phase)), /schema/);
    });
  }
  test(`${hz}Hz: rejects sleeping drift in coherent aliases`, () => {
    const bad = clone(s.sleep), b = bad.bodies[1];
    b.transform.getTranslationX += 0.1; b.transform.getTranslation[0] += 0.1; b.transform.getValues[2] += 0.1;
    b.worldCenter[0] += 0.1; b.fixedOriginPosition[0] += 0.1;
    assert.throws(() => checkSnapshot(bad, {phase: 'step', prior: s.sleep}), /sleep/i);
  });
  test(`${hz}Hz: sleeping interval uses its own settled pose`, () => {
    const value = clone(s.sleep), b = value.bodies[1];
    b.transform.getTranslationX += 1; b.transform.getTranslation[0] += 1; b.transform.getValues[2] += 1;
    b.previousTransform = clone(b.transform); b.worldCenter[0] += 1; b.fixedOriginPosition[0] += 1;
    checkSnapshot(value, {phase: 'step', prior: clone(value)});
  });
  test(`${hz}Hz: initial previous transform cannot disagree in recorded angle`, () => {
    const value = clone(s.initial), b = value.bodies[1];
    b.previousTransform.getRotationAngle = 0.1;
    b.properties.getPreviousTransform.getRotationAngle = 0.1;
    assert.throws(() => checkSnapshot(value, {phase: 'initial'}), /previous copy/);
  });
  test(`${hz}Hz: immediate impulse cannot change a coherent dynamic pose`, () => {
    const value = clone(s.after), b = value.bodies[1];
    b.transform.getTranslationX += 0.1; b.transform.getTranslation[0] += 0.1; b.transform.getValues[2] += 0.1;
    b.worldCenter[0] += 0.1; b.fixedOriginPosition[0] += 0.1;
    b.properties.getTransform = clone(b.transform); b.properties.getWorldCenter = clone(b.worldCenter);
    assert.throws(() => checkImpulse(s.before, value), /impulse/);
  });
  test(`${hz}Hz: valid immediate impulse and following physics state`, () => {
    checkImpulse(s.before, s.after);
    checkSnapshot(s.next, {phase: 'step', prior: s.after});
    assert.notEqual(s.next.bodies[1].velocity[0], 1);
  });
  for (const field of ['velocity', 'angularVelocity', 'atRest', 'rotationIncrementSum', 'fixtures', 'properties']) {
    test(`${hz}Hz: rejects impulse mutation ${field}`, () => {
      const bad = clone(s.after), b = bad.bodies[1];
      if (field === 'velocity') b.velocity[0] = 0.9;
      else if (field === 'atRest') b.atRest = true;
      else if (field === 'fixtures') b.fixtures[0].getFriction = 0.6;
      else if (field === 'properties') b.properties.getMass.getMass = 2;
      else b[field] = 0.1;
      assert.throws(() => checkImpulse(s.before, bad), /impulse/i);
    });
  }
  for (const step of [1, 2]) {
    const old = step === 1 ? 1/60 : 1/hz;
    const dt = {getDeltaTime: 1/hz, getInverseDeltaTime: hz, getPrevousDeltaTime: old, getPreviousInverseDeltaTime: 1/old, getDeltaTimeRatio: (1/hz)/old};
    test(`${hz}Hz step ${step}: valid timestep`, () => checkTimeStep(dt, hz, step));
    for (const key of Object.keys(dt)) {
      test(`${hz}Hz step ${step}: rejects timestep ${key}`, () => {
        assert.throws(() => checkTimeStep({...dt, [key]: dt[key] + 0.1}, hz, step), /timestep/i);
      });
    }
  }
}

test('compressed hash guard rejects altered bytes before semantic decoding', async () => {
  const root = mkdtempSync(join(tmpdir(), 'sleep-exact-hash-'));
  const manifest = JSON.parse(readFileSync(new URL('./initial-reference-review-manifest.json', import.meta.url)));
  try {
    mkdirSync(join(root, 'run1'));
    writeFileSync(join(root, 'run1', 'S-sleep-wake-hz30-0.jsonl.gz'), 'synthetic altered bytes');
    await assert.rejects(auditReference(root, manifest.sleep_candidates[0]), /compressed identity guard/);
  } finally { rmSync(root, {recursive: true}); }
});
