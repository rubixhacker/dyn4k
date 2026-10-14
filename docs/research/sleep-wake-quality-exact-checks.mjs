// Read-only same-run checks on approved configured captures; no physics execution.
import assert from 'node:assert/strict';
import {createReadStream,readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {createGunzip} from 'node:zlib';
import {createInterface} from 'node:readline';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {checkSnapshot,checkImpulse,checkTimeStep} from './sleep-wake-exact-checks.mjs';
import {identities} from './sleep-wake-quality-acceptance.mjs';
const sha=x=>createHash('sha256').update(x).digest('hex');
export const semanticSha256='803f78a03aca84b4177de0d22d6d4f3b2bef79ce258e16d8028e65fcaeb7346a';
export function same(a,b){
  if(typeof a==='number'||typeof b==='number')return Number.isFinite(a)&&Number.isFinite(b)&&a===b;
  if(a===null||b===null||typeof a!=='object'||typeof b!=='object')return a===b;
  if(Array.isArray(a)!==Array.isArray(b))return false;
  const keys=Object.keys(a);return keys.length===Object.keys(b).length&&keys.every(k=>Object.hasOwn(b,k)&&same(a[k],b[k]));
}
function finite(x){if(typeof x==='number')assert.ok(Number.isFinite(x),'nonfinite record');else if(x&&typeof x==='object')Object.values(x).forEach(finite);}
const group=hz=>{assert.ok([30,60,120].includes(hz));return 120/hz;};
export function checkEndpoint(row,last,hz){
  assert.ok(same(Object.keys(row).sort(),['kind','outerStep','state','step']),'endpoint schema');
  assert.equal(row.kind,'outer-endpoint');assert.equal(last.step%group(hz),0);
  assert.equal(row.step,last.step);assert.equal(row.outerStep,last.step/group(hz));
  assert.ok(same(row.state,last.state),'endpoint numeric copy');
}
export function checkInner(row,hz,expected,prior){
  assert.equal(row.kind,'state');assert.equal(row.step,expected);
  assert.equal(row.outerStep,Math.floor((expected-1)/group(hz))+1);assert.equal(row.innerWithinOuter,(expected-1)%group(hz)+1);
  checkSnapshot(row.state,{phase:'step',prior});
}
export function checkInternalTimeStep(dt,step){
  assert.ok(same(Object.keys(dt).sort(),['getDeltaTime','getDeltaTimeRatio','getInverseDeltaTime','getPreviousInverseDeltaTime','getPrevousDeltaTime','type']),'TimeStep schema');
  assert.equal(dt.type,'org.dyn4j.dynamics.TimeStep');checkTimeStep(dt,120,step);
}
export async function audit(root,archive,output){
  assert.equal(sha(readFileSync(new URL('./sleep-wake-exact-checks.mjs',import.meta.url))),semanticSha256,'semantic source identity');
  const manifest=identities(root,archive),results=[];
  for(const c of manifest.candidates){
    const counts={},listeners={},methods={},coverage={initial:0,inner:0,before:0,after:0,impulse:0,timestep:0,endpoints:0,sleepingStates:0,sleepPoseComparisons:0};
    let prior,before,last,pending=false,states=0,order=0,orderedStep=0,actionPhase=0;
    let lifecycle=[];
    const raw=createHash('sha256'),stream=createReadStream(join(root,`outer${c.hz}-repeat${c.repetition}`,c.file)).pipe(createGunzip());stream.on('data',x=>raw.update(x));
    for await(const line of createInterface({input:stream,crlfDelay:Infinity})){
      const r=JSON.parse(line);finite(r);counts[r.kind]=(counts[r.kind]??0)+1;
      if(pending)assert.equal(r.kind,'outer-endpoint','missing endpoint');
      if(r.kind==='inputs'){
        assert.equal(counts.inputs,1);assert.equal(states,0);assert.equal(sha(line),c.inputSha256,'input identity');
        assert.equal(r.id,c.id);assert.equal(r.steps,72000);assert.equal(r.dt,1/120);
        checkSnapshot(r.state,{phase:'initial'});prior=r.state;coverage.initial++;continue;
      }
      assert.equal(counts.inputs,1,'inputs first');
      if(r.kind==='outer-endpoint'){
        assert.ok(pending,'unexpected endpoint');checkEndpoint(r,last,c.hz);coverage.endpoints++;pending=false;continue;
      }
      assert.equal(r.step,states+1,'record step');
      if(orderedStep!==r.step){orderedStep=r.step;order=0;}
      if(r.kind!=='state')assert.equal(r.order,order++,'record order');
      switch(r.kind){
        case 'instrumented-callback':{
          assert.equal(r.step,36001);assert.equal(r.values.length,1);
          const phase=r.event==='before-wake'?'before':r.event==='after-wake'?'after':null;assert.ok(phase);
          assert.equal(actionPhase,phase==='before'?0:2);assert.equal(r.order,phase==='before'?0:2);
          checkSnapshot(r.values[0],{phase,prior});coverage[phase]++;
          if(phase==='before'){before=r.values[0];actionPhase=1;}
          else{checkImpulse(before,r.values[0]);coverage.impulse++;prior=r.values[0];actionPhase=3;}break;
        }
        case 'action':
          assert.equal(r.step,36001);assert.equal(r.order,1);assert.equal(actionPhase,1);
          assert.equal(r.description,'impulse=(1,0) at center; sleepingBefore=true; precedingSecondAsleep=true');actionPhase=2;break;
        case 'event':{
          if(r.step===36001)assert.equal(actionPhase,3);
          listeners[r.listener]=(listeners[r.listener]??0)+1;
          const method=r.method.match(/\.([^. (]+)\(/)?.[1];assert.ok(method,'listener method');
          const key=`${r.listener}.${method}`;assert.ok(Object.hasOwn(c.methods,key),'classified listener method');methods[key]=(methods[key]??0)+1;
          if(r.listener==='StepListener'){assert.equal(r.payload.length,2);assert.ok(same(r.payload[1],{world:c.id}));checkInternalTimeStep(r.payload[0],r.step);coverage.timestep++;lifecycle.push(method);}break;
        }
        case 'state':
          if(r.step===36001)assert.equal(actionPhase,3);
          assert.ok(same(lifecycle,r.step===1?['begin','updatePerformed','postSolve','end']:['begin','postSolve','end']),'complete ordered step lifecycle');lifecycle=[];
          checkInner(r,c.hz,++states,prior);coverage.inner++;
          if(r.state.bodies[1].atRest){coverage.sleepingStates++;if(prior.bodies[1].atRest)coverage.sleepPoseComparisons++;}
          prior=r.state;last=r;pending=states%group(c.hz)===0;break;
        default:assert.fail(`unclassified record ${r.kind}`);
      }
    }
    assert.equal(pending,false);assert.equal(states,72000);assert.equal(coverage.endpoints,600*c.hz);
    assert.ok(same([coverage.initial,coverage.before,coverage.after,coverage.impulse],[1,1,1,1]));assert.equal(coverage.timestep,216001);
    assert.ok(same(counts,c.counts));assert.ok(same(listeners,c.listeners));assert.ok(same(methods,c.methods));assert.equal(raw.digest('hex'),c.decompressedSha256,'decompressed identity');
    results.push({id:c.id,hz:c.hz,repetition:c.repetition,role:c.repetition===1?'approved-reference':'corroboration',coverage,counts,listeners,methods,gzipSha256:c.gzipSha256,decompressedSha256:c.decompressedSha256,inputSha256:c.inputSha256});
    console.log(`${c.id}: exact checks pass; ${states} inner states, ${coverage.endpoints} endpoint copies`);
  }
  const totals={};for(const r of results)for(const [k,v]of Object.entries(r.coverage))totals[k]=(totals[k]??0)+v;
  assert.equal(totals.inner,432000);assert.equal(totals.endpoints,252000);assert.equal(totals.timestep,1296006);
  const result={status:'BOUNDED_CONFIGURED_EXACT_CHECKS_PASS_NOT_PORT_QUALIFICATION',manifestSha256:'7efd60aa76cab10fdc27eb8e968a2868e854433cc4556e10257dbd290a63e554',archiveSha256:manifest.archive.sha256,semanticSha256,totals,results};
  writeFileSync(output,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({status:result.status,totals}));return result;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){assert.equal(process.argv.length,5,'node evaluator.mjs PACKAGE ARCHIVE OUTPUT');await audit(...process.argv.slice(2));}
