# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: python3 weld-pulley-physical-checks-audit.py DYN4K_GIT_REPO NEW_OUTPUT_DIRECTORY
import collections
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tarfile

if len(sys.argv) != 3 or not __debug__:
    raise SystemExit('Usage without -O: python3 weld-pulley-physical-checks-audit.py DYN4K_GIT_REPO NEW_OUTPUT_DIRECTORY')
repo, out = str(Path(sys.argv[1]).resolve()), Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=False)
rev = '0995a6bac84de882b0d04b6c3ea18162ca3b4a7c'
base = 'docs/research/calibration-evidence/interactions/'
names = ['P-JINT-Weld-enabled-equal-0.jsonl.gz', 'P-JINT-Pulley-slack-transition-preparation-0.jsonl.gz', 'P-JINT-Pulley-slack-transition-preparation-1.jsonl.gz', 'P-JINT-Pulley-slack-transition-0.jsonl.gz']

def git(path: str) -> bytes:
    return subprocess.check_output(['git', '-C', repo, 'show', f'{rev}:{path}'])

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def finite(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(value)
    return result

def reject(value: str) -> None:
    raise ValueError(value)

def parse(raw: bytes):
    return json.loads(raw, parse_float=finite, parse_constant=reject)

def distance(a: list[float], b: list[float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)

archives = {rep: git(base + f'raw-repeat-{rep}.tar.gz') for rep in ['a', 'b']}
tarballs = {rep: tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') for rep, data in archives.items()}
audits = [json.loads(line) for line in git(base + 'audit-manifest.jsonl').splitlines()]
inputs = [json.loads(line) for line in git(base + 'input-manifest.jsonl').splitlines()]
result = {'approval': 'PENDING_HUMAN_DECISION', 'experiment_revision': rev, 'archive_sha256': {rep: sha(data) for rep, data in archives.items()}, 'source_sha256': {p: sha(git(p)) for p in ['calibration/src/InteractionCases.java', 'calibration/src/Capture.java', base + 'audit-manifest.jsonl', base + 'input-manifest.jsonl', base + 'queries.jsonl']}, 'traces': []}
all_samples = []
for name in names:
    extracted = {}
    for rep, archive in tarballs.items():
        member = f'interactions-final-{rep}/{name}'
        file = archive.extractfile(member)
        assert file is not None
        extracted[rep] = file.read()
    assert extracted['a'] == extracted['b']
    raw = extracted['a']
    expected = [r for r in audits if r.get('file') == name]
    assert len(expected) == 1 and sha(raw) == expected[0]['rawSha256']
    expected_input = [r for r in inputs if r.get('traceFile') == name]
    assert len(expected_input) == 1
    lines = gzip.decompress(raw).splitlines(keepends=True)
    header = parse(lines[0])
    assert header == expected_input[0]['input'] and sha(lines[0].rstrip(b'\n')) == expected_input[0]['inputSha256']
    assert header['dt'] == 1/60 and header['origin'] == [0, 0] and header['scale'] == 1
    count = collections.Counter(inputs=1)
    state_step = expected[0]['startStep']
    order = -1
    event_step = state_step
    actions, bindings, samples = [], [], []
    for line in lines[1:]:
        e = parse(line)
        assert e['kind'] in {'state', 'event', 'action', 'instrumented-callback'}
        assert e['step'] == state_step + 1
        count[e['kind']] += 1
        if e['kind'] != 'state':
            assert e['order'] == (order + 1 if e['step'] == event_step else 0)
            order, event_step = e['order'], e['step']
            if e['kind'] == 'action':
                actions.append(e)
            elif e['kind'] == 'instrumented-callback':
                bindings.append(e)
            else:
                assert {'listener', 'method', 'payload'} <= e.keys()
            continue
        state_step += 1
        bodies, joints = e['state']['bodies'], e['state']['joints']
        assert len(joints) == 1
        j = joints[0]
        for b in bodies:
            assert {'id', 'transform', 'previousTransform', 'worldCenter', 'fixedOriginPosition', 'velocity', 'angularVelocity', 'atRest', 'force', 'torque', 'accumulatedForce', 'accumulatedTorque'} <= b.keys()
        sample = {'trace': name, 'step': state_step}
        if 'Weld' in name:
            assert len(bodies) == 2 and j['isLimitsEnabled'] and j['isSpringEnabled']
            assert j['getLowerLimit'] == j['getUpperLimit'] == j['getLimitsReferenceAngle'] == 0
            angle = bodies[1]['transform']['getRotationAngle'] - bodies[0]['transform']['getRotationAngle'] - j['getLimitsReferenceAngle']
            assert -math.pi < angle < math.pi and angle == j['getAngularTranslation']
            sample.update({'phase': 'equal_limits_enabled', 'angle_rad': angle, 'anchor_gap_m': distance(j['getAnchor1'], j['getAnchor2']), 'body_asleep': bodies[1]['atRest']})
        else:
            assert len(bodies) == 3 and j['getRatio'] == 1 and j['getLength'] == 1.5
            l1 = distance(j['getAnchor1'], j['getPulleyAnchor1'])
            l2 = distance(j['getAnchor2'], j['getPulleyAnchor2'])
            assert l1 == j['getCurrentLength1'] and l2 == j['getCurrentLength2']
            measured = l1 + j['getRatio'] * l2 - j['getLength']
            phase = 'preparation' if 'preparation' in name else ('disabled_before' if state_step <= 200 else 'enabled' if state_step <= 400 else 'disabled_after')
            assert j['isSlackEnabled'] == (phase == 'enabled')
            sample.update({'phase': phase, 'length_error_m': measured, 'slack_enabled': j['isSlackEnabled'], 'reaction_force': j['reactionForce'], 'anchor1': j['getAnchor1'], 'anchor2': j['getAnchor2'], 'body2_velocity': bodies[2]['velocity'], 'public_current_length_error_m': j['getCurrentLength'] - j['getLength']})
        samples.append(sample)
    assert count['state'] == expected[0]['states'] and count['event'] == expected[0]['listenerEvents']
    assert len(lines) == expected[0]['rawRecords'] and count['state'] == header['steps']
    if name == 'P-JINT-Pulley-slack-transition-0.jsonl.gz':
        assert [(a['step'], a['order'], a['description']) for a in actions] == [(201, 0, 'body2.setLinearVelocity(0,10)'), (201, 1, 'body2.translate(0,.1)'), (201, 2, 'setSlackEnabled(true)'), (401, 0, 'setSlackEnabled(false)')]
    else:
        assert actions == []
    if 'Weld' in name:
        assert header['state']['bodies'][1]['accumulatedForce'] == [0, -10]
        assert header['state']['bodies'][1]['accumulatedTorque'] == -5
    phases = {}
    for phase in dict.fromkeys(s['phase'] for s in samples):
        selected = [s for s in samples if s['phase'] == phase]
        metrics = ['angle_rad', 'anchor_gap_m'] if 'Weld' in name else ['length_error_m']
        phases[phase] = {'steps': [selected[0]['step'], selected[-1]['step']], 'samples': len(selected)}
        for metric in metrics:
            lo, hi = min(selected, key=lambda s:s[metric]), max(selected, key=lambda s:s[metric])
            phases[phase][metric] = {'minimum': lo[metric], 'minimum_step': lo['step'], 'maximum': hi[metric], 'maximum_step': hi['step']}
        if 'Weld' not in name:
            phases[phase]['positive_error_steps'] = [s['step'] for s in selected if s['length_error_m'] > 0]
            phases[phase]['above_configured_linear_tolerance_steps_diagnostic_only'] = [s['step'] for s in selected if s['length_error_m'] > header['settings']['getLinearTolerance']]
    result['traces'].append({'file': name, 'gzip_sha256': sha(raw), 'gzip_bytes': len(raw), 'input_sha256': sha(lines[0].rstrip(b'\n')), 'decompressed_sha256': sha(b''.join(lines)), 'input': header, 'counts': dict(count), 'repeat_bytes_equal': True, 'audit': 'PASS', 'actions': actions, 'bindings': bindings, 'phase_measurements': phases})
    all_samples.extend(samples)
    (out / name).write_bytes(raw)
for archive in tarballs.values():
    archive.close()
queries = [json.loads(line) for line in git(base + 'queries.jsonl').splitlines() if b'Pulley-slack-transition-preparation' in line]
assert len(queries) == 1 and queries[0]['payload']['values'] == ['body2.setLinearVelocity(0,10) before source step2']
result['preparation_query_records'] = queries
pulley_samples = [s for s in all_samples if s['trace'] == 'P-JINT-Pulley-slack-transition-0.jsonl.gz']
result['pulley_transition_samples'] = [s for s in pulley_samples if s['step'] in [200, 201, 204, 208, 209, 210, 266, 267, 268, 399, 400, 401]]
before = next(s for s in pulley_samples if s['step'] == 200)
after_translation_anchor = [before['anchor2'][0], before['anchor2'][1] + 0.1]
result['reconstructed_pre_step201_after_actions_length_error_m'] = distance(before['anchor1'], [-1, 1]) + distance(after_translation_anchor, [1, 1]) - 1.5
result['pre_step201_measurement_status'] = 'Reconstructed from step200 geometry and exact translation action; no immediate pre-solve state or private solver flag was recorded'
(out / 'manifest.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
(out / 'samples.jsonl').write_text(''.join(json.dumps(s, allow_nan=False) + '\n' for s in all_samples))
print(json.dumps([{k:r[k] for k in ['file', 'counts', 'audit', 'phase_measurements']} for r in result['traces']], indent=2))
