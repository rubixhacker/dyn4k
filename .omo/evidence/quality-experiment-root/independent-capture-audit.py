# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# Run: python3 independent-capture-audit.py RUN_DIRECTORY OUTER_HZ REPETITION
import gzip,json,math,hashlib,sys
from pathlib import Path
root=Path(sys.argv[1]); hz=int(sys.argv[2]); repetition=int(sys.argv[3]); group=120//hz
path=root/f"Q-sleep-wake-outer{hz}-repeat{repetition}-0.jsonl.gz"
states=endpoints=timesteps=0; previous_sleep=False; sleep=[]; begin=[]; end=[]; toi=[]; first_solve=None; snapshots=[]; action=[]; window=[]; h=hashlib.sha256(); last=None
with gzip.open(path,"rb") as stream:
 initial=json.loads(next(stream)); assert initial["steps"]==72000 and initial["dt"]==1/120
 assert initial["settings"]["getLinearTolerance"]==1/4096 and initial["settings"]["getPositionConstraintSolverIterations"]==8
 assert initial["grouping"]=={"outerHz":hz,"outerDt":1/hz,"innerPerOuter":group,"outerSteps":600*hz,"repetition":repetition,"actionInnerStep":36001}
 floor=initial["state"]["bodies"][0]["transform"]
 for line in stream:
  state_line=b'"kind":"state"' in line
  endpoint_line=b'"kind":"outer-endpoint"' in line
  relevant=state_line or endpoint_line or b'"kind":"action"' in line or b'"kind":"instrumented-callback"' in line or b'"listener":"StepListener"' in line or b'"listener":"TimeOfImpactListener"' in line or (b'"listener":"ContactListener"' in line and (b'.begin(' in line or b'.end(' in line or b'.destroyed(' in line or (first_solve is None and b'.postSolve(' in line)))
  if not relevant: continue
  r=json.loads(line)
  if state_line:
   states+=1; assert r["step"]==states and r["outerStep"]==(states-1)//group+1 and r["innerWithinOuter"]==(states-1)%group+1
   last=r["state"]; assert [b["id"] for b in last["bodies"]]==["b0","b1"] and last["bodies"][0]["transform"]==floor
   stack=[last]
   while stack:
    value=stack.pop()
    if isinstance(value,dict): stack.extend(value.values())
    elif isinstance(value,list): stack.extend(value)
    elif isinstance(value,float): assert math.isfinite(value)
   sleeping=last["bodies"][1]["atRest"]
   if sleeping!=previous_sleep: sleep.append([states,previous_sleep,sleeping])
   previous_sleep=sleeping
   if 35880<=states<=36000: window.append(sleeping)
   h.update(json.dumps(last,sort_keys=True,separators=(",",":")).encode()); h.update(b"\n")
  elif endpoint_line:
   endpoints+=1; assert r["step"]==states and states%group==0 and r["outerStep"]==endpoints and r["state"]==last
  elif r["kind"]=="action": action.append(r)
  elif r["kind"]=="instrumented-callback": snapshots.append(r)
  elif r.get("listener")=="StepListener":
   timesteps+=1; dt=r["payload"][0]; old=1/60 if r["step"]==1 else 1/120
   expected={"getDeltaTime":1/120,"getInverseDeltaTime":120,"getPrevousDeltaTime":old,"getPreviousInverseDeltaTime":1/old,"getDeltaTimeRatio":(1/120)/old}
   assert all(dt[k]==v for k,v in expected.items())
  elif r.get("listener")=="TimeOfImpactListener":
   for p in r["payload"]:
    if isinstance(p,dict) and p.get("type")=="org.dyn4j.collision.continuous.TimeOfImpact": toi.append([r["step"],r["order"],p["getTime"]])
  elif r.get("listener")=="ContactListener":
   method=r["method"]
   if ".begin(" in method: begin.append(r["step"])
   elif ".end(" in method or ".destroyed(" in method: end.append(r["step"])
   elif ".postSolve(" in method and r["payload"][1]["isSolved"]:
    assert not r["payload"][1]["isIgnored"]; first_solve=r["step"]
assert states==72000 and endpoints==hz*600 and timesteps==216001 and len(window)==121 and all(window)
assert len(action)==1 and action[0]["step"]==36001 and action[0]["order"]==1
assert [(r["event"],r["step"],r["order"]) for r in snapshots]==[("before-wake",36001,0),("after-wake",36001,2)]
before,after=(r["values"][0]["bodies"][1] for r in snapshots)
assert before["atRest"] and not after["atRest"] and before["velocity"]==[0,0] and after["velocity"]==[1,0] and before["transform"]==after["transform"]
assert len(sleep)==3 and sleep[1]==[36001,True,False]
print(json.dumps({"status":"INDEPENDENT_CAPTURE_AND_EVENT_AUDIT_COMPLETE_NO_PHYSICAL_ACCEPTANCE","hz":hz,"repetition":repetition,"states":states,"outerEndpoints":endpoints,"timeStepPayloads":timesteps,"sleepTransitions":sleep,"contactBeginSteps":begin,"contactEndSteps":end,"toi":toi,"firstSolvedContactStep":first_solve,"windowAllAsleep":True,"pythonCanonicalStateSequenceSha256":h.hexdigest()},indent=2))
