import assert from 'node:assert/strict';
import {createReadStream,readFileSync,mkdtempSync,writeFileSync,rmSync,symlinkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createGunzip} from 'node:zlib';
import {createInterface} from 'node:readline';
import {checkSnapshot,checkImpulse} from './sleep-wake-exact-checks.mjs';
import {checkEndpoint,checkInner,checkInternalTimeStep,same} from './sleep-wake-quality-exact-checks.mjs';
import {identities} from './sleep-wake-quality-acceptance.mjs';
const root=process.env.QUALITY_EVIDENCE,archive=process.env.QUALITY_ARCHIVE;
assert.ok(root&&archive,'Supply QUALITY_EVIDENCE and QUALITY_ARCHIVE; no skipped fixtures');
let assertions=0;const pass=f=>{f();assertions++;},reject=f=>{assert.throws(f);assertions++;};
const clone=structuredClone;
function zeroFlip(x){if(typeof x==='number')return x===0?-0:x;if(Array.isArray(x))return x.map(zeroFlip);if(x&&typeof x==='object')return Object.fromEntries(Object.entries(x).reverse().map(([k,v])=>[k,zeroFlip(v)]));return x;}
for(const hz of [30,60,120]){
  const states=new Map(),endpoints=new Map();let initial,before,after,firstDt,laterDt;
  const stream=createReadStream(join(root,`outer${hz}-repeat1`,`Q-sleep-wake-outer${hz}-repeat1-0.jsonl.gz`)).pipe(createGunzip());
  for await(const line of createInterface({input:stream,crlfDelay:Infinity})){
    const r=JSON.parse(line);
    if(r.kind==='inputs')initial=r.state;
    if(r.kind==='state'&&[1,2,3,4,65,66,67,36000,36001].includes(r.step))states.set(r.step,r);
    if(r.kind==='outer-endpoint'&&r.step<=4)endpoints.set(r.step,r);
    if(r.kind==='instrumented-callback'){if(r.event==='before-wake')before=r.values[0];else after=r.values[0];}
    if(r.kind==='event'&&r.listener==='StepListener'){if(r.step===1)firstDt=r.payload[0];if(r.step===2)laterDt=r.payload[0];}
    if(r.kind==='state'&&r.step===36001)break;
  }
  stream.destroy();
  pass(()=>checkSnapshot(initial,{phase:'initial'}));
  for(const [step,prior]of [[1,initial],[2,states.get(1).state],[66,states.get(65).state],[67,states.get(66).state],[36001,after]])pass(()=>checkInner(states.get(step),hz,step,prior));
  pass(()=>checkSnapshot(before,{phase:'before',prior:states.get(36000).state}));
  pass(()=>checkSnapshot(after,{phase:'after',prior:before}));pass(()=>checkImpulse(before,after));
  pass(()=>checkInternalTimeStep(firstDt,1));pass(()=>checkInternalTimeStep(laterDt,2));
  for(const [step,row]of endpoints){
    pass(()=>checkEndpoint(row,states.get(step),hz));pass(()=>checkEndpoint(zeroFlip(row),states.get(step),hz));
    reject(()=>{const x=clone(row);delete x.state.bodies[1].force;checkEndpoint(x,states.get(step),hz);});
    reject(()=>{const x=clone(row);x.state.bodies[1].transform.getTranslationY+=.001;checkEndpoint(x,states.get(step),hz);});
    reject(()=>{const x=clone(row);x.outerStep++;checkEndpoint(x,states.get(step),hz);});
  }
  reject(()=>{const x=clone(states.get(2));x.state.bodies[1].previousTransform=clone(x.state.bodies[1].transform);checkInner(x,hz,2,states.get(1).state);});
  reject(()=>{const x=clone(states.get(67));x.state.bodies[1].velocity[0]=1;checkInner(x,hz,67,states.get(66).state);});
  reject(()=>{const x=clone(after);x.bodies[1].properties.getLinearVelocity=[0,0];checkSnapshot(x,{phase:'after',prior:before});});
  reject(()=>{const x=clone(after);x.bodies[1].fixtures[0].getFriction=.25;checkImpulse(before,x);});
  reject(()=>{const x=clone(firstDt);x.getPreviousInverseDeltaTime=120;checkInternalTimeStep(x,1);});
  reject(()=>{const x=clone(laterDt);x.getDeltaTime=1/30;checkInternalTimeStep(x,2);});
  reject(()=>{const x=clone(states.get(2));x.innerWithinOuter++;checkInner(x,hz,2,states.get(1).state);});
  pass(()=>assert.ok(same(0,-0)));
}
console.log(`${assertions} actual-profile semantic assertions passed`);
// Identity rejection is separate from semantic mutation: no mutated snapshot is hash-gated above.
const temp=mkdtempSync(join(tmpdir(),'quality-exact-identities-'));
try{
  const manifest=JSON.parse(readFileSync(new URL('./sleep-wake-quality-candidate-manifest.json',import.meta.url)));
  writeFileSync(join(temp,'bad.tar.gz'),'wrong archive');reject(()=>identities(root,join(temp,'bad.tar.gz')));
  // Frozen source guard is tested by a substituted package tree, without changing original files.
  const {readdirSync}=await import('node:fs');for(const name of readdirSync(root))symlinkSync(join(root,name),join(temp,name));
  const entry=Object.keys(manifest.sourceAndRuntimeSha256).find(x=>!x.includes('/'));
  assert.ok(entry,'top-level provenance member');rmSync(join(temp,entry));writeFileSync(join(temp,entry),'wrong provenance');reject(()=>identities(temp,archive));
  console.log('2 independent identity rejection scenarios passed');
}finally{rmSync(temp,{recursive:true,force:true});}
