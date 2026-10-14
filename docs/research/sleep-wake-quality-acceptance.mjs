// Read frozen bytes only. Exit 0: represented-geometry pass; 2: physical failures; 1: invalid evidence.
import assert from 'node:assert/strict';
import { createReadStream, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { createGunzip } from 'node:zlib';
import { createInterface } from 'node:readline';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { depth, accepts, SCALE, checkGeometry } from './sleep-wake-penetration-acceptance.mjs';

export const schedule = [
  ['initial-approach',1,4,0], ['impact',5,7,100], ['initial-settling',8,65,200],
  ['rest-before',66,36000,1000], ['wake-settling',36001,36083,200], ['rest-after',36084,72000,1000],
];
export function phase(step) {
  assert.ok(Number.isInteger(step)&&step>=1&&step<=72000,'invalid internal step');
  return schedule.findIndex(([,first,last])=>step>=first&&step<=last);
}
function group(hz) { const n={30:4,60:2,120:1}[hz];assert.ok(n,'invalid outer Hz');return n; }
export function stateMeasurement(row,hz,expectedStep) {
  assert.equal(row.kind,'state');assert.equal(row.step,expectedStep);
  const n=group(hz);assert.equal(row.outerStep,Math.floor((row.step-1)/n)+1);assert.equal(row.innerWithinOuter,(row.step-1)%n+1);
  const t=checkGeometry(row.state.bodies),i=phase(row.step);
  return {i,d:depth(t.getSint,t.getCost,t.getTranslationY)};
}
export function checkEndpoint(row,last,hz) {
  assert.equal(row.kind,'outer-endpoint');assert.equal(last.step%group(hz),0);
  assert.equal(row.step,last.step);assert.equal(row.outerStep,last.step/group(hz));assert.deepEqual(row.state,last.state);
  return phase(row.step);
}
const sha=x=>createHash('sha256').update(x).digest('hex');
export function identities(root,archive) {
  assert.equal(sha(readFileSync(new URL('./sleep-wake-penetration-acceptance.mjs',import.meta.url))),'6b5e633814b7fd11404f53362a500e45371dc3210e295f5ea59fb0401d11e52f','exact math source hash');
  const bytes=readFileSync(new URL('./sleep-wake-quality-candidate-manifest.json',import.meta.url));
  assert.equal(sha(bytes),'7efd60aa76cab10fdc27eb8e968a2868e854433cc4556e10257dbd290a63e554','manifest hash');
  const m=JSON.parse(bytes);assert.equal(sha(readFileSync(archive)),m.archive.sha256,'archive hash');
  for(const [path,expected] of Object.entries(m.sourceAndRuntimeSha256))assert.equal(sha(readFileSync(join(root,path))),expected,`source/runtime hash ${path}`);
  for(const c of m.candidates)assert.equal(sha(readFileSync(join(root,`outer${c.hz}-repeat${c.repetition}`,c.file))),c.gzipSha256,`gzip hash ${c.id}`);
  return m;
}
const abs=x=>x<0n?-x:x;
function fraction(n,d=SCALE) {let a=abs(n),b=d;while(b)[a,b]=[b,a%b];return `${n/a}/${d/a}`;}
function measure(d,step){return {step,exactMetres:fraction(d),approximateMetres:Number(d>>1000n)/2**75};}
function rangeAppend(ranges,step){const last=ranges.at(-1);if(last&&last[1]===step-1)last[1]=step;else ranges.push([step,step]);}
export async function audit(root,archive,output) {
  const manifest=identities(root,archive),results=[];let total=0,failed=0,totalEndpoints=0,failedEndpoints=0;
  for(const c of manifest.candidates) {
    const phases=schedule.map(([name,first,last,den])=>({name,first,last,ceiling:den?`1/${den}`:'0/1',count:0,failed:0,failureRanges:[],endpointCount:0,endpointFailed:0,failedOuterFrameRanges:[],minimum:null,maximum:null,closestBoundary:null}));
    const mins=[],maxes=[],closest=[],counts={},listeners={};
    const raw=createHash('sha256');const stream=createReadStream(join(root,`outer${c.hz}-repeat${c.repetition}`,c.file)).pipe(createGunzip());stream.on('data',x=>raw.update(x));
    let states=0,endpoints=0,pending=false,last,lastMeasurement;
    for await(const line of createInterface({input:stream,crlfDelay:Infinity})) {
      const row=JSON.parse(line);counts[row.kind]=(counts[row.kind]??0)+1;
      if(pending)assert.equal(row.kind,'outer-endpoint','missing outer endpoint');
      if(row.kind==='inputs') {
        assert.equal(counts.inputs,1);assert.equal(states,0);assert.equal(sha(line),c.inputSha256,'input hash');
        assert.equal(row.id,c.id);assert.equal(row.steps,72000);assert.equal(row.dt,1/120);
        assert.equal(row.grouping.outerHz,c.hz);assert.equal(row.grouping.repetition,c.repetition);
        checkGeometry(row.state.bodies,true);continue;
      }
      assert.equal(counts.inputs,1);
      if(row.kind==='event'){listeners[row.listener]=(listeners[row.listener]??0)+1;continue;}
      if(row.kind==='outer-endpoint') {
        assert.ok(pending,'unexpected outer endpoint');const i=checkEndpoint(row,last,c.hz);assert.equal(i,lastMeasurement.i);
        assert.equal(row.outerStep,++endpoints);totalEndpoints++;phases[i].endpointCount++;
        if(!accepts(lastMeasurement.d,schedule[i][3])){failedEndpoints++;phases[i].endpointFailed++;rangeAppend(phases[i].failedOuterFrameRanges,row.outerStep);}
        pending=false;continue;
      }
      if(row.kind==='instrumented-callback'||row.kind==='action')continue;
      assert.equal(row.kind,'state','unknown record kind');
      const {i,d}=stateMeasurement(row,c.hz,++states),p=phases[i],den=schedule[i][3],margin=den?SCALE-d*BigInt(den):-d;
      total++;p.count++;
      if(mins[i]===undefined||d<mins[i]){mins[i]=d;p.minimum=measure(d,row.step);}
      if(maxes[i]===undefined||d>maxes[i]){maxes[i]=d;p.maximum=measure(d,row.step);}
      if(closest[i]===undefined||abs(margin)<closest[i]){closest[i]=abs(margin);p.closestBoundary={...measure(d,row.step),signedHeadroomMetres:fraction(margin,SCALE*BigInt(den||1))};}
      if(!accepts(d,den)){failed++;p.failed++;rangeAppend(p.failureRanges,row.step);}
      last=row;lastMeasurement={i,d};pending=states%group(c.hz)===0;
    }
    assert.equal(pending,false,'missing final endpoint');assert.equal(states,72000);assert.equal(endpoints,600*c.hz);
    assert.equal(raw.digest('hex'),c.decompressedSha256,'decompressed hash');assert.deepEqual(counts,c.counts);assert.deepEqual(listeners,c.listeners);
    for(const p of phases){assert.equal(p.count,p.last-p.first+1);assert.equal(p.endpointCount,Math.floor(p.last/group(c.hz))-Math.floor((p.first-1)/group(c.hz)));}
    results.push({id:c.id,hz:c.hz,repetition:c.repetition,role:c.repetition===1?'approved-reference':'corroboration',states,endpoints,gzipSha256:c.gzipSha256,decompressedSha256:c.decompressedSha256,inputSha256:c.inputSha256,phases});
  }
  assert.equal(total,432000);assert.equal(totalEndpoints,252000);
  const result={status:failed?'REPRESENTED_BASELINE_GEOMETRY_FAIL':'REPRESENTED_BASELINE_GEOMETRY_PASS',manifestSha256:'7efd60aa76cab10fdc27eb8e968a2868e854433cc4556e10257dbd290a63e554',archiveSha256:manifest.archive.sha256,exactMathSourceSha256:'6b5e633814b7fd11404f53362a500e45371dc3210e295f5ea59fb0401d11e52f',sourceAndRuntimeSha256:manifest.sourceAndRuntimeSha256,total,failed,passed:total-failed,totalEndpoints,failedEndpoints,endpointsAreDuplicateObservations:true,results};
  writeFileSync(output,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({status:result.status,total,failed,totalEndpoints,failedEndpoints}));return failed?2:0;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){assert.equal(process.argv.length,5,'Usage: node evaluator.mjs EXTRACTED_PACKAGE ARCHIVE OUTPUT_JSON');process.exitCode=await audit(...process.argv.slice(2));}
