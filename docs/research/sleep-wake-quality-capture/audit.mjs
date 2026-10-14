// Candidate capture/provenance/event audit only. Never evaluates penetration acceptance.
// Usage: node audit.mjs RUN_DIRECTORY OUTER_HZ REPETITION ORIGINAL_EXTRACTED_ROOT
import assert from 'node:assert/strict';
import { createReadStream, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { createGunzip } from 'node:zlib';
import { createInterface } from 'node:readline';
import { join } from 'node:path';
assert.equal(process.argv.length, 6);
const [root, hzText, repeatText, original] = process.argv.slice(2);
const hz = Number(hzText), repetition = Number(repeatText), group = {30:4,60:2,120:1}[hz];
assert.ok(group && [1,2].includes(repetition));
const id = `Q-sleep-wake-outer${hz}-repeat${repetition}`, file = `${id}-0.jsonl.gz`;
const sha = x => createHash('sha256').update(x).digest('hex');
const originalManifestBytes = readFileSync(new URL('../initial-reference-review-manifest.json', import.meta.url));
assert.equal(sha(originalManifestBytes),'b42174c7523bea9687e4ab015a215b4e652c2446df73d2f41e836e8a165c1208');
const selection = JSON.parse(originalManifestBytes).sleep_candidates.find(c=>c.hz===120);
const originalFile = join(original,'run1','S-sleep-wake-hz120-0.jsonl.gz');
assert.equal(sha(readFileSync(originalFile)),selection.gzip_sha256);
let originalInput;
const originalStream = createReadStream(originalFile).pipe(createGunzip());
for await (const line of createInterface({input:originalStream,crlfDelay:Infinity})) {
  assert.equal(sha(line),selection.input_sha256_utf8_without_newline);originalInput=JSON.parse(line);break;
}
originalStream.destroy();
const expectedSettings = {...originalInput.settings, getLinearTolerance:1/4096, getLinearToleranceSquared:1/(4096*4096), getPositionConstraintSolverIterations:8};
const finite = value => {
  if(typeof value==='number') assert.ok(Number.isFinite(value),'nonfinite number');
  else if(value && typeof value==='object') for(const v of Object.values(value)) finite(v);
};
const phaseGaps=[];
const counts={},listeners={},methods={},firstEvents={},sleepChanges=[],contactChanges=[],toiPayloads=[],snapshots=[];
const rawHash=createHash('sha256'),stateHash=createHash('sha256'),normalizedHash=createHash('sha256');
const stream=createReadStream(join(root,file)).pipe(createGunzip());stream.on('data',chunk=>rawHash.update(chunk));
let states=0,endpoints=0,order=0,lastState,previousSleep=false,contacts=0,priorContacts=0,action,inputHash,firstSolve;
let endpointPending=false,stepMethods={},windowCount=0,windowSleeping=true,solved=0,sleepingStates=0;
for await(const line of createInterface({input:stream,crlfDelay:Infinity})) {
  const row=JSON.parse(line);finite(row);counts[row.kind]=(counts[row.kind]??0)+1;
  if(endpointPending) assert.equal(row.kind,'outer-endpoint','missing outer endpoint');
  if(row.kind==='inputs') {
    assert.equal(states,0);assert.equal(counts.inputs,1);assert.equal(row.id,id);assert.equal(row.steps,72000);assert.equal(row.dt,1/120);
    assert.equal(row.scale,1);assert.deepEqual(row.origin,[0,0]);assert.deepEqual(row.settings,expectedSettings);
    assert.deepEqual(row.state,originalInput.state);assert.deepEqual(row.world,originalInput.world);
    assert.deepEqual(row.grouping,{outerHz:hz,outerDt:1/hz,innerPerOuter:group,outerSteps:600*hz,repetition,actionInnerStep:36001});
    inputHash=sha(line);continue;
  }
  assert.equal(counts.inputs,1);
  if(row.kind==='outer-endpoint') {
    assert.ok(endpointPending);assert.equal(row.step,states);assert.equal(row.outerStep,++endpoints);assert.deepEqual(row.state,lastState);
    endpointPending=false;continue;
  }
  assert.equal(row.step,states+1);
  if('order' in row) assert.equal(row.order,order++);
  if(row.kind==='event') {
    listeners[row.listener]=(listeners[row.listener]??0)+1;
    const method=row.method.match(/\.([^.()]+)\(/)[1], key=`${row.listener}.${method}`;
    methods[key]=(methods[key]??0)+1;stepMethods[key]=(stepMethods[key]??0)+1;firstEvents[key]??={step:row.step,order:row.order};
    if(row.listener==='StepListener') assert.deepEqual(row.payload[0],{getDeltaTime:1/120,getDeltaTimeRatio:row.step===1?0.5:1,getInverseDeltaTime:120,getPreviousInverseDeltaTime:row.step===1?60:120,getPrevousDeltaTime:row.step===1?1/60:1/120,type:'org.dyn4j.dynamics.TimeStep'});
    if(row.listener==='ContactListener') {
      assert.deepEqual([row.payload[0].body1,row.payload[0].body2].sort(),['b0','b1']);
      if(method==='begin')contacts++;
      if(method==='end'||method==='destroyed')contacts--;
      assert.ok(contacts>=0);
      if(method==='postSolve'&&row.payload[1].isSolved) {solved++;firstSolve??=row.step;}
      if(method==='collision')assert.equal(row.payload[0].constraint.contacts.length,contacts);
    }
    if(row.listener==='TimeOfImpactListener') for(const payload of row.payload) {
      if(payload?.type==='org.dyn4j.collision.continuous.TimeOfImpact') toiPayloads.push({step:row.step,order:row.order,time:payload.getTime});
    }
  } else if(row.kind==='action') {
    assert.equal(row.step,36001);assert.equal(row.order,1);assert.equal(counts.action,1);action=row;
  } else if(row.kind==='instrumented-callback') {
    assert.equal(row.step,36001);assert.ok(['before-wake','after-wake'].includes(row.event));snapshots.push(row);
  } else if(row.kind==='state') {
    states++;assert.equal(row.outerStep,Math.floor((states-1)/group)+1);assert.equal(row.innerWithinOuter,(states-1)%group+1);
    assert.equal(stepMethods['StepListener.begin'],1);assert.equal(stepMethods['StepListener.postSolve'],1);assert.equal(stepMethods['StepListener.end'],1);
    const b=row.state.bodies[1];assert.deepEqual(row.state.bodies.map(b=>b.id),['b0','b1']);
    assert.deepEqual(row.state.bodies[0].transform,originalInput.state.bodies[0].transform);
    if(b.atRest!==previousSleep)sleepChanges.push({step:states,from:previousSleep,to:b.atRest});
    if(contacts!==priorContacts)contactChanges.push({step:states,from:priorContacts,to:contacts});
    if(states>=35880&&states<=36000){windowCount++;windowSleeping&&=b.atRest;}
    if(b.atRest)sleepingStates++;
    previousSleep=b.atRest;priorContacts=contacts;lastState=row.state;endpointPending=states%group===0;
    stateHash.update(JSON.stringify(row.state)+'\n');order=0;stepMethods={};
  } else assert.fail(`unknown row ${row.kind}`);
  // Only remove declared run/grouping metadata; retain every physical/callback/action value.
  const normalized=JSON.parse(JSON.stringify(row),(_key,value)=>value===id?'Q-CANDIDATE':value);
  delete normalized.outerStep;delete normalized.innerWithinOuter;
  normalizedHash.update(JSON.stringify(normalized)+'\n');
}
assert.equal(states,72000);assert.equal(endpoints,600*hz);assert.equal(endpointPending,false);assert.equal(windowCount,121);
assert.equal(counts['instrumented-callback'],2);assert.equal(counts.action,1);assert.equal(snapshots.length,2);
assert.deepEqual(snapshots.map(s=>[s.event,s.order]),[['before-wake',0],['after-wake',2]]);
const before=snapshots[0].values[0].bodies[1],after=snapshots[1].values[0].bodies[1];
assert.deepEqual(before.transform,after.transform);assert.deepEqual(after.velocity,[before.velocity[0]+1,before.velocity[1]]);
assert.equal(after.angularVelocity,before.angularVelocity);assert.equal(after.atRest,false);
if(!windowSleeping||!before.atRest)phaseGaps.push('missing sleeping prerequisite');
if(before.atRest){assert.deepEqual(before.velocity,[0,0]);assert.equal(before.angularVelocity,0);}
assert.equal(action.description,`impulse=(1,0) at center; sleepingBefore=${before.atRest}; precedingSecondAsleep=${windowSleeping}`);
const queries=readFileSync(join(root,'queries.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
assert.deepEqual(queries,[{id,payload:{actionStep:36001,awakeImmediatelyAfterImpulse:true,sleepPrerequisite:windowSleeping}}]);
const summary=JSON.parse(readFileSync(join(root,'summary.jsonl'),'utf8').trim());
assert.equal(summary.id,id);assert.equal(summary.file,file);assert.equal(summary.steps,states);assert.equal(summary.dt,1/120);assert.equal(summary.seconds,600);
assert.equal(summary.events,counts.event);assert.equal(summary.solvedContactCallbacks,solved);assert.equal(summary.toiPayloadCallbacks,toiPayloads.length);assert.equal(summary.stepsWithSleepingDynamicBody,sleepingStates);assert.equal(summary.status,undefined);
if(sleepChanges.length!==3||!sleepChanges[0].to||sleepChanges[1].to||!sleepChanges[2].to||sleepChanges[1].step!==36001)phaseGaps.push('unexpected sleep episodes');
if(contactChanges.length!==1||contactChanges[0].from!==0||contactChanges[0].to!==2)phaseGaps.push('unexpected contact episodes');
if(toiPayloads.length!==2||toiPayloads[0].step!==toiPayloads[1].step||!firstSolve)phaseGaps.push('ambiguous impact anchors');
let proposedSchedule=null;
if(!phaseGaps.length) {
  const touchdown=toiPayloads[0].step;
  proposedSchedule=[['initial-approach',1,touchdown-1],['impact',touchdown,firstSolve],['initial-settling',firstSolve+1,sleepChanges[0].step-1],['rest-before',sleepChanges[0].step,36000],['wake-settling',36001,sleepChanges[2].step-1],['rest-after',sleepChanges[2].step,72000]].map(([phase,first,last])=>({phase,first,last,count:last-first+1}));
  let covered=0;
  for(const p of proposedSchedule){assert.equal(p.first,covered+1);assert.ok(p.count>0);covered=p.last;}
  assert.equal(covered,72000);
}
console.log(JSON.stringify({status:'CAPTURE_AUDITED_CANDIDATE_PENDING_HUMAN_REFERENCE_AND_PHASE_REVIEW',id,hz,repetition,file,gzipSha256:sha(readFileSync(join(root,file))),decompressedSha256:rawHash.digest('hex'),inputSha256:inputHash,stateSequenceSha256:stateHash.digest('hex'),normalizedInnerSequenceSha256:normalizedHash.digest('hex'),states,endpoints,counts,listeners,methods,firstEvents,toiPayloads,sleepChanges,contactChanges,action:{step:action.step,order:action.order,description:action.description},window:{first:35880,last:36000,count:windowCount,allAsleep:windowSleeping},phaseGaps,proposedSchedule,physicalAcceptance:'NOT_EVALUATED_PENDING_REVIEW'},null,2));
