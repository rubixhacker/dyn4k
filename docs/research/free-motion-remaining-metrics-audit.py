# Run: python3 free-motion-remaining-metrics-audit.py RAW_GZIP DYN4K_REPO OUTPUT_DIRECTORY
import collections
from decimal import Decimal, localcontext
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

if len(sys.argv) != 4 or not __debug__:
    raise SystemExit('Usage without -O: auditor RAW_GZIP DYN4K_REPO OUTPUT_DIRECTORY')
raw, repo, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
REV = '0995a6bac84de882b0d04b6c3ea18162ca3b4a7c'
RAW_SHA = '4981795bffcd2a0262040acb53c60b20607fea14a2a0c7d79e858ba68e7f2743'
INPUT_SHA = '91f914d3c9993ac238c66e88015861ece560e20333f9e831f3ff4758980b3dd9'
sha = lambda b: hashlib.sha256(b).hexdigest()
assert sha(raw.read_bytes()) == RAW_SHA
source = lambda p: subprocess.check_output(['git', '-C', repo, 'show', REV + ':' + p])

def finite(s):
    x = float(s)
    if not math.isfinite(x):
        raise ValueError(s)
    return x

def invalid(s):
    raise ValueError(s)

def parse(line):
    return json.loads(line, parse_float=finite, parse_constant=invalid)

PI = Decimal('3.141592653589793238462643383279502884197169399375105820974944592307816406286208998628')
D = Decimal.from_float
metrics = {}

def measure(name, value, step, limit=None):
    value = abs(float(value))
    assert math.isfinite(value)
    m = metrics.setdefault(name, {'samples': 0, 'maximum_absolute_residual': 0.0,
        'maximum_step': 1, 'limit': limit, 'first_violation': None})
    m['samples'] += 1
    if value > m['maximum_absolute_residual']:
        m['maximum_absolute_residual'], m['maximum_step'] = value, step
    if limit is not None and value > limit and m['first_violation'] is None:
        m['first_violation'] = step
    sample[name] = value
    return value

def principal(theta):
    return theta - ((theta + PI) // (2 * PI)) * (2 * PI)

def trig(theta):
    x = principal(theta)
    sn, cs, ts, tc = x, Decimal(1), x, Decimal(1)
    for k in range(1, 100):
        ts *= -x*x / ((2*k)*(2*k+1))
        tc *= -x*x / ((2*k-1)*(2*k))
        sn += ts
        cs += tc
        if max(abs(ts), abs(tc)) < Decimal('1e-65'):
            return sn, cs
    raise AssertionError('Taylor convergence')

def angular_difference(actual, expected):
    e = D(actual) - principal(expected)
    return min(abs(e), abs(e - 2*PI), abs(e + 2*PI))

counts = collections.Counter()
stream_sha = hashlib.sha256()
with localcontext() as ctx, gzip.open(raw, 'rb') as stream, (out/'samples.jsonl').open('w') as samples:
    ctx.prec = 75
    line = next(stream)
    stream_sha.update(line)
    assert sha(line.rstrip(b'\n')) == INPUT_SHA
    inputs = parse(line)
    index = [parse(x) for x in source('docs/research/calibration-evidence/input-manifest.jsonl').splitlines()]
    match = [x for x in index if x.get('traceFile') == raw.name]
    assert len(match) == 1 and match[0]['input'] == inputs
    initial = inputs['state']['bodies'][0]
    assert inputs['dt'] == 1/60 and inputs['steps'] == 36000 and inputs['origin'] == [0, 0]
    assert initial['worldCenter'] == [0, 0] and initial['velocity'] == [.25, -.125] and initial['angularVelocity'] == .5
    assert initial['transform']['getRotationAngle'] == 0
    assert inputs['world']['gravity'] == [0,0] and inputs['state']['joints'] == []
    mass = initial['properties']['getMass']['getMass']
    inertia = initial['properties']['getMass']['getInertia']
    assert initial['properties']['getLocalCenter'] == [0,0]
    assert initial['properties']['getLinearDamping'] == initial['properties']['getAngularDamping'] == 0
    assert not inputs['settings']['isAtRestDetectionEnabled']
    dt, omega = D(inputs['dt']), D(initial['angularVelocity'])
    previous = initial['transform']
    initial_momentum = [mass*v for v in initial['velocity']]
    initial_spin = inertia * initial['angularVelocity']
    initial_energy = .5*mass*sum(v*v for v in initial['velocity']) + .5*inertia*initial['angularVelocity']**2
    tracking_sum = 0.0
    state_count, order = 0, 0
    counts['inputs'] = 1
    body_keys = set(initial) - {'fixtures', 'properties'}
    transform_keys = set(previous)
    for line in stream:
        stream_sha.update(line)
        row = parse(line)
        counts[row['kind']] += 1
        assert row['step'] == state_count + 1
        if row['kind'] == 'event':
            assert {'step','order','listener','method','payload'} <= row.keys()
            assert row['order'] == order and row['listener'] == 'StepListener'
            method = ['begin', 'updatePerformed', 'postSolve', 'end'] if row['step'] == 1 else ['begin', 'postSolve', 'end']
            assert row['method'].split('StepListener.')[1].split('(')[0] == method[order]
            clock = row['payload'][0]
            assert clock['getDeltaTime'] == clock['getPrevousDeltaTime'] == inputs['dt']
            assert clock['getInverseDeltaTime'] == clock['getPreviousInverseDeltaTime'] == 60
            assert clock['getDeltaTimeRatio'] == 1
            order += 1
            continue
        assert row['kind'] == 'state' and len(row['state']['bodies']) == 1 and row['state']['joints'] == []
        state_count += 1
        n = state_count
        assert order == (4 if n == 1 else 3)
        order = 0
        b = row['state']['bodies'][0]
        assert set(b) == body_keys and b['id'] == 'b0' and not b['atRest']
        assert b['rotationStepBoundBelowPi'] and b['rotationTrackingScope'] == initial['rotationTrackingScope']
        t, p = b['transform'], b['previousTransform']
        assert set(t) == set(p) == transform_keys
        sample = {'step': n}
        theta = omega * (n * dt)
        prevtheta = omega * ((n-1) * dt)
        for label, trans, angle in [('current',t,theta),('previous',p,prevtheta)]:
            sn, cs = trig(angle)
            for key, expected in [('getCost',cs),('getSint',sn)]:
                sample[label+'_'+key] = measure(label+'_'+key, D(trans[key])-expected, n)
            sample[label+'_orientation_rad'] = measure(label+'_orientation_rad', angular_difference(trans['getRotationAngle'], angle), n)
            measure(label+'_unit_circle_defect', D(trans['getCost'])**2+D(trans['getSint'])**2-1, n)
            c, s = trans['getCost'], trans['getSint']
            x,y = trans['getTranslation']
            assert trans['type'] == 'org.dyn4j.geometry.Transform'
            measure(label+'_matrix_getter_consistency', max(abs(a-z) for a,z in zip(trans['getValues'],[c,-s,x,s,c,y],strict=True)), n, 0)
            measure(label+'_translation_getter_consistency', max(abs(x-trans['getTranslationX']),abs(y-trans['getTranslationY'])),n,0)
            assert trans['isIdentity'] == (c==1 and s==0 and x==0 and y==0)
            measure(label+'_angle_getter_vs_signed_acos',trans['getRotationAngle']-math.copysign(math.acos(c),1 if s>=0 else -1),n)
        measure('previous_equals_prior_current', 0 if p==previous else 1, n, 0)
        measure('world_center_equals_translation', max(abs(a-z) for a,z in zip(b['worldCenter'],t['getTranslation'],strict=True)),n,0)
        measure('fixed_origin_equals_world_center', max(abs(a-z) for a,z in zip(b['worldCenter'],b['fixedOriginPosition'],strict=True)),n,0)
        for axis in range(2):
            measure('position_'+str(axis)+'_approved',b['worldCenter'][axis]-initial['velocity'][axis]*(n*inputs['dt']),n,1e-10)
            measure('previous_position_'+str(axis)+'_inherited',p['getTranslation'][axis]-initial['velocity'][axis]*((n-1)*inputs['dt']),n,1e-10)
            measure('velocity_'+str(axis)+'_approved',b['velocity'][axis]-initial['velocity'][axis],n,0)
        measure('angular_velocity_approved',b['angularVelocity']-initial['angularVelocity'],n,0)
        for key in ['force','accumulatedForce']:
            measure(key+'_zero',max(abs(x) for x in b[key]),n,0)
        for key in ['torque','accumulatedTorque']:
            measure(key+'_zero',b[key],n,0)
        sample['unwrapped_rotation_rad'] = measure('unwrapped_rotation_rad',D(b['rotationIncrementSum'])-theta,n)
        angle_delta = t['getRotationAngle']-previous['getRotationAngle']
        increment = math.atan2(math.sin(angle_delta),math.cos(angle_delta))
        tracking_sum += increment
        measure('recorder_sum_recalculation',b['rotationIncrementSum']-tracking_sum,n)
        measure('step_rotation_vs_omega_dt_rad',D(increment)-omega*dt,n)
        measure('linear_momentum_drift_assumed_mass',max(abs(mass*v-z) for v,z in zip(b['velocity'],initial_momentum,strict=True)),n,0)
        measure('spin_momentum_drift_assumed_inertia',inertia*b['angularVelocity']-initial_spin,n,0)
        energy = .5*mass*sum(v*v for v in b['velocity']) + .5*inertia*b['angularVelocity']**2
        measure('kinetic_energy_drift_assumed_mass_inertia',energy-initial_energy,n,0)
        orbital = mass*(b['worldCenter'][0]*b['velocity'][1]-b['worldCenter'][1]*b['velocity'][0])
        measure('orbital_angular_momentum_about_fixed_origin',orbital,n)
        samples.write(json.dumps(sample,allow_nan=False)+'\n')
        previous = t
    assert state_count == 36000 and counts == {'inputs':1,'event':108001,'state':36000}
    assert stream_sha.hexdigest() == '4a2919c350f61974b8046dd5fe11e0710db37abde26b5db0af909ab4b8d83f78'
for name, m in metrics.items():
    m['role'] = ('previously_approved' if name.endswith('_approved') else 'redundant_diagnostic' if 'assumed_' in name else 'proposed_fixture_specific_check' if m['limit'] is not None else 'diagnostic_limit_missing')
    m['status'] = 'DIAGNOSTIC_NO_APPROVED_LIMIT' if m['limit'] is None else ('PASS' if m['first_violation'] is None else 'FAIL')
assert all(m['status'] != 'FAIL' for m in metrics.values())
result = {'approval':'PENDING_HUMAN_DECISION','fixture':inputs['id'],'experiment_revision':REV,
    'source_revision':'058bf6d982a0fb89b54050f929f6ea9dae53b714','raw_sha256':RAW_SHA,'input_sha256':INPUT_SHA,
    'stream_sha256':stream_sha.hexdigest(),'counts':dict(counts),'body_keys':sorted(body_keys),'transform_keys':sorted(transform_keys),
    'analytic_model':'exact binary64 input dt times integer step, initial omega=0.5; Decimal precision75 Taylor sin/cos, pi constant80 decimal places',
    'initial_mass_inertia_header_only':[mass,inertia],'initial_momentum_xy':initial_momentum,'initial_spin_angular_momentum':initial_spin,'initial_kinetic_energy':initial_energy,
    'metrics':metrics,'sample_file_sha256':sha((out/'samples.jsonl').read_bytes()),
    'capture_source_sha256':sha(source('calibration/src/Capture.java')),
    'auditor_sha256':sha(Path(__file__).read_bytes()),
    'upstream_source_sha256':{p.name:sha(p.read_bytes()) for p in sorted((out.parent/'upstream').glob('*.java'))}}
(out/'manifest.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps(result,indent=2))
