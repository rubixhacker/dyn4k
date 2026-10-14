import assert from 'node:assert/strict';
import { mkdtempSync,mkdirSync,symlinkSync,copyFileSync,appendFileSync,rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join,resolve } from 'node:path';
import { phase,stateMeasurement,checkEndpoint,identities,schedule } from './sleep-wake-quality-acceptance.mjs';
let checks=0;
const equal=(a,b)=>{assert.deepEqual(a,b);checks++;};
const rejects=f=>{assert.throws(f);checks++;};
const cases=[[1,4,0],[5,7,1],[8,65,2],[66,36000,3],[36001,36083,4],[36084,72000,5]];
for(const [first,last,i] of cases){equal(phase(first),i);equal(phase(last),i);if(first>1)equal(phase(first-1),i-1);if(last<72000)equal(phase(last+1),i+1);}
for(const bad of [0,-1,72001,1.5,NaN,Infinity,'5'])rejects(()=>phase(bad));
const counts=[0,0,0,0,0,0],endpoints={30:[0,0,0,0,0,0],60:[0,0,0,0,0,0],120:[0,0,0,0,0,0]};
for(let step=1;step<=72000;step++){counts[phase(step)]++;for(const hz of [30,60,120])if(step%(120/hz)===0)endpoints[hz][phase(step)]++;}
equal(counts,[4,3,58,35935,83,35917]);equal(endpoints[30],[1,0,15,8984,20,8980]);equal(endpoints[60],[2,1,29,17968,41,17959]);equal(endpoints[120],counts);
equal(schedule.map(p=>p[3]),[0,100,200,1000,200,1000]);
const body=(id,y)=>({id,transform:{getCost:1,getSint:0,getTranslationX:0,getTranslationY:y}});
const row=(hz,step)=>({kind:'state',step,outerStep:Math.floor((step-1)/(120/hz))+1,innerWithinOuter:(step-1)%(120/hz)+1,state:{bodies:[body('b0',-0.25),body('b1',0.5)],joints:[]}});
for(const hz of [30,60,120]){
 const wake=row(hz,36001);equal(stateMeasurement(wake,hz,36001),{i:4,d:0n});
 const endpointState=row(hz,36000),endpoint={kind:'outer-endpoint',step:36000,outerStep:300*hz,state:structuredClone(endpointState.state)};
 equal(checkEndpoint(endpoint,endpointState,hz),3);
 for(const [key,value] of [['step',35999],['outerStep',300*hz+1],['kind','state']]){const bad=structuredClone(endpoint);bad[key]=value;rejects(()=>checkEndpoint(bad,endpointState,hz));}
 const mismatched=structuredClone(endpoint);mismatched.state.bodies[1].transform.getTranslationY=0.49;rejects(()=>checkEndpoint(mismatched,endpointState,hz));
 const badState=structuredClone(wake);badState.outerStep++;rejects(()=>stateMeasurement(badState,hz,36001));
 const badInner=structuredClone(wake);badInner.innerWithinOuter=0;rejects(()=>stateMeasurement(badInner,hz,36001));
 rejects(()=>stateMeasurement(wake,hz,36002));
}
const nonEndpoint=row(30,36001);rejects(()=>checkEndpoint({kind:'outer-endpoint',step:36001,outerStep:9001,state:nonEndpoint.state},nonEndpoint,30));
rejects(()=>stateMeasurement(row(30,1),90,1));
const wrongId=row(30,1);wrongId.state.bodies[1].id='wrong';rejects(()=>stateMeasurement(wrongId,30,1));
const nonfinite=row(30,1);nonfinite.state.bodies[1].transform.getSint=Infinity;rejects(()=>stateMeasurement(nonfinite,30,1));
console.log(JSON.stringify({status:'PASS',semanticAssertions:checks,scenarios:['approved fixed phase boundaries','all inner/outer phase counts','wake uses internal index at every outer cadence','wrong/mismatched/non-endpoint duplicates reject','state grouping/identity/finite rejection']}));
if(process.argv.length===4){
 const root=resolve(process.argv[2]),archive=resolve(process.argv[3]),temp=mkdtempSync(join(tmpdir(),'quality-acceptance-identities-'));
 try {
  const badArchive=join(temp,'bad.tar.gz');copyFileSync(archive,badArchive);appendFileSync(badArchive,'x');
  assert.throws(()=>identities(root,badArchive),/archive hash/);
  const {readdirSync}=await import('node:fs');
  for(const item of readdirSync(root))symlinkSync(join(root,item),join(temp,item));
  rmSync(join(temp,'runtime.txt'));copyFileSync(join(root,'runtime.txt'),join(temp,'runtime.txt'));appendFileSync(join(temp,'runtime.txt'),'x');
  assert.throws(()=>identities(temp,archive),/source\/runtime hash runtime.txt/);
  rmSync(join(temp,'runtime.txt'));symlinkSync(join(root,'runtime.txt'),join(temp,'runtime.txt'));
  const dir='outer30-repeat1',file='Q-sleep-wake-outer30-repeat1-0.jsonl.gz';rmSync(join(temp,dir));mkdirSync(join(temp,dir));copyFileSync(join(root,dir,file),join(temp,dir,file));appendFileSync(join(temp,dir,file),'x');
  assert.throws(()=>identities(temp,archive),/gzip hash Q-sleep-wake-outer30-repeat1/);
  console.log(JSON.stringify({status:'PASS',hashRejections:3,scenarios:['archive mutation','runtime identity mutation','selected compressed stream mutation'],separateFromSemanticRejection:true}));
 } finally{rmSync(temp,{recursive:true,force:true});}
}
