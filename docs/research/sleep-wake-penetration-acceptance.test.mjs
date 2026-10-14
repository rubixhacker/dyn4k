import assert from 'node:assert/strict';
import { exact, SCALE, depth, accepts, phase, checkGeometry } from './sleep-wake-penetration-acceptance.mjs';
let checks = 0;
const equal = (a, b) => { assert.deepEqual(a, b); checks++; };
const rejects = f => { assert.throws(f); checks++; };
// Decoder known representations: signs, zero, subnormal, normal extremes.
equal(exact(0), 0n); equal(exact(-0), 0n); equal(exact(1), SCALE);
equal(exact(-0.5), -SCALE / 2n); equal(exact(Number.MIN_VALUE), 2n);
equal(exact(2 ** -1022), 1n << 53n);
equal(exact(Number.MAX_VALUE), ((1n << 53n) - 1n) << 2046n);
for (const x of [NaN, Infinity, -Infinity, null, '0', undefined]) rejects(() => exact(x));
// Rational thresholds need cross multiplication. Decimal binary64 caps round upward.
for (const den of [100, 200, 1000]) {
  const below = SCALE / BigInt(den);
  equal(accepts(below, den), true); equal(accepts(below + 1n, den), false);
  const b = Buffer.alloc(8); b.writeDoubleBE(1 / den);
  const bits = b.readBigUInt64BE();
  b.writeBigUInt64BE(bits - 1n); const predecessor = b.readDoubleBE();
  b.writeBigUInt64BE(bits + 1n); const successor = b.readDoubleBE();
  equal(accepts(exact(predecessor), den), true);
  equal(accepts(exact(1 / den), den), false);
  equal(accepts(exact(successor), den), false);
}
// Positive decimal ceilings are not dyadic, so exact equality cannot arise from finite coefficients.
// The same comparison accepts representable equality and rejects its immediate exact neighbour.
equal(accepts(SCALE / 2n, 2), true); equal(accepts(SCALE / 2n + 1n, 2), false);
equal(accepts(0n, 0), true); equal(accepts(1n, 0), false);
equal(depth(0, 1, 0.5), 0n); equal(depth(0, 1, 0.25), SCALE / 4n);
equal(depth(1, 1, 0.75), SCALE / 4n); // rejects center-height-only or normalization shortcuts
// Independent vertex enumeration, including all sign combinations and extreme/subnormal operands.
for (const s of [-1, -0.625, -Number.MIN_VALUE, 0, Number.MIN_VALUE, 0.625, 1]) {
  for (const c of [-1, -0.75, 0, 0.75, 1, Number.MAX_VALUE]) {
    for (const y of [-0.25, 0, 0.5, 1]) {
      const vertices = [-1n, 1n].flatMap(x => [-1n, 1n].map(vy => (x * exact(s) + vy * exact(c)) / 2n + exact(y)));
      const min = vertices.reduce((a,b) => a < b ? a : b);
      equal(depth(s,c,y), min < 0n ? -min : 0n);
    }
  }
}
// Check every interval edge, its immediate neighbour, and complete counts from separately listed bounds.
const bounds = {30: [[1,0],[1,3],[4,17],[18,9000],[9001,9021],[9022,18000]],60:[[1,2],[3,5],[6,34],[35,18000],[18001,18042],[18043,36000]],120:[[1,4],[5,7],[8,65],[66,36000],[36001,36083],[36084,72000]]};
for (const [hz, ranges] of Object.entries(bounds)) {
  const counts = [0,0,0,0,0,0];
  for (let step = 1; step <= Number(hz)*600; step++) counts[phase(Number(hz),step)]++;
  equal(counts, ranges.map(([a,b])=>Math.max(0,b-a+1)));
  ranges.forEach(([first,last],i) => { if(last>=first){equal(phase(hz,first),i);equal(phase(hz,last),i);if(first>1)equal(phase(hz,first-1),i-1);if(last<Number(hz)*600)equal(phase(hz,last+1),i+1);} });
  for (const step of [0,-1,0.5,Number(hz)*600+1,NaN]) rejects(()=>phase(hz,step));
}
rejects(()=>phase(90,1));
const body = (id,c,s,x,y) => ({id,transform:{getCost:c,getSint:s,getTranslationX:x,getTranslationY:y}});
const valid = () => [body('b0',1,0,0,-0.25),body('b1',1,0,0,0.5)];
checkGeometry(valid()); checks++;
for (const [index,key,value] of [[0,'getTranslationY',0],[0,'getSint',0.1],[1,'getTranslationX',10],[1,'getCost',NaN],[1,'getTranslationY',Infinity]]) {
  const b=valid();b[index].transform[key]=value;rejects(()=>checkGeometry(b));
}
const b=valid();b[1].id='wrong';rejects(()=>checkGeometry(b));
const inputBodies = () => { const b = valid();
  b[0].fixtures=[{shape:{getVertices:[[-10,-0.25],[10,-0.25],[10,0.25],[-10,0.25]]}}];
  b[1].fixtures=[{shape:{getVertices:[[-0.5,-0.5],[0.5,-0.5],[0.5,0.5],[-0.5,0.5]]}}]; return b; };
checkGeometry(inputBodies(),true); checks++;
for (const index of [0,1]) { const b=inputBodies();b[index].fixtures[0].shape.getVertices[0][0]+=0.125;rejects(()=>checkGeometry(b,true)); }
const extra=inputBodies();extra[1].fixtures.push(extra[1].fixtures[0]);rejects(()=>checkGeometry(extra,true));
console.log(JSON.stringify({status:'PASS',checks,scenarios:['binary64 decoding','exact rational thresholds and adjacent floats','zero and representable equality','four-vertex sign/extreme geometry','every phase boundary and total coverage','semantic finite/floor/span/identity rejection']}));
if (process.argv[2]) {
  const { mkdtempSync, mkdirSync, copyFileSync, symlinkSync, appendFileSync, rmSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { join, resolve } = await import('node:path');
  const { spawnSync } = await import('node:child_process');
  const root = resolve(process.argv[2]), temp = mkdtempSync(join(tmpdir(), 'penetration-hash-test-'));
  try {
    mkdirSync(join(temp,'source')); mkdirSync(join(temp,'run1'));
    for (const name of ['Capture.java','SleepWakeCases.java','audit.jq']) copyFileSync(join(root,'source',name),join(temp,'source',name));
    for (const hz of [30,60,120]) symlinkSync(join(root,'run1',`S-sleep-wake-hz${hz}-0.jsonl.gz`),join(temp,'run1',`S-sleep-wake-hz${hz}-0.jsonl.gz`));
    appendFileSync(join(temp,'source','SleepWakeCases.java'),'\n');
    const invoke = () => spawnSync(process.execPath,[new URL('./sleep-wake-penetration-acceptance.mjs',import.meta.url).pathname,temp,join(temp,'out')],{encoding:'utf8'});
    const source = invoke(); equal(source.status,1); assert.match(source.stderr,/source hash source\/SleepWakeCases.java/);
    copyFileSync(join(root,'source','SleepWakeCases.java'),join(temp,'source','SleepWakeCases.java'));
    const member = join(temp,'run1','S-sleep-wake-hz30-0.jsonl.gz');
    rmSync(member); copyFileSync(join(root,'run1','S-sleep-wake-hz30-0.jsonl.gz'),member); appendFileSync(member,'x');
    const gzip = invoke(); equal(gzip.status,1); assert.match(gzip.stderr,/gzip hash/);
    console.log(JSON.stringify({status:'PASS',scenarios:['source hash mutation rejects exit 1','gzip hash mutation rejects exit 1'],separateFromSemanticChecks:true}));
  } finally { rmSync(temp,{recursive:true,force:true}); }
}
