# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: python3 free-motion-reference-review-audit.py EVIDENCE_DIRECTORY DYN4K_GIT_REPO
import collections
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

if len(sys.argv) != 3 or not __debug__:
    raise SystemExit('Usage (without -O): python3 free-motion-reference-review-audit.py EVIDENCE_DIRECTORY DYN4K_GIT_REPO')
out = Path(sys.argv[1]).resolve()
repo = str(Path(sys.argv[2]).resolve())
revision = '0995a6bac84de882b0d04b6c3ea18162ca3b4a7c'
name = 'L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz'
expected_raw = '4981795bffcd2a0262040acb53c60b20607fea14a2a0c7d79e858ba68e7f2743'
expected_input = '91f914d3c9993ac238c66e88015861ece560e20333f9e831f3ff4758980b3dd9'

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def source(path: str) -> bytes:
    return subprocess.check_output(['git', '-C', repo, 'show', f'{revision}:{path}'])

def finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(value)
    return parsed

def reject_constant(value: str) -> None:
    raise ValueError(value)

raw = (out / name).read_bytes()
assert len(raw) == 3945330 and sha(raw) == expected_raw
input_index = source('docs/research/calibration-evidence/input-manifest.jsonl')
input_matches = [r for line in input_index.splitlines() if (r := json.loads(line)).get('traceFile') == name]
assert len(input_matches) == 1
audit_index = source('docs/research/calibration-evidence/audit-manifest.jsonl')
audit_matches = [r for line in audit_index.splitlines() if (r := json.loads(line)).get('file') == name]
assert len(audit_matches) == 2 and audit_matches[0] == audit_matches[1]
expected_audit = audit_matches[0]
kinds = collections.Counter()
methods = collections.Counter()
states = 0
last_order = -1
last_event_step = 0
stream_hash = hashlib.sha256()
max_errors = [0.0, 0.0]
max_steps = [0, 0]
first_violation = [None, None]
last_state = None
with gzip.open(out / name, 'rb') as stream:
    header = next(stream)
    stream_hash.update(header)
    assert sha(header.rstrip(b'\n')) == expected_input
    inputs = json.loads(header, parse_float=finite_float, parse_constant=reject_constant)
    assert inputs == input_matches[0]['input']
    assert inputs['kind'] == 'inputs' and inputs['steps'] == 36000 and inputs['dt'] == 1 / 60
    assert inputs['origin'] == [0, 0] and inputs['scale'] == 1
    assert len(inputs['state']['bodies']) == 1 and inputs['state']['joints'] == []
    initial_body = inputs['state']['bodies'][0]
    assert initial_body['worldCenter'] == [0, 0] and initial_body['velocity'] == [0.25, -0.125]
    assert inputs['world']['gravity'] == [0, 0] and not inputs['settings']['isAtRestDetectionEnabled']
    kinds['inputs'] = 1
    for line in stream:
        stream_hash.update(line)
        event = json.loads(line, parse_float=finite_float, parse_constant=reject_constant)
        assert event['kind'] in {'event', 'state'}
        kinds[event['kind']] += 1
        assert event['step'] == states + 1
        if event['kind'] == 'event':
            assert {'step', 'order', 'listener', 'method', 'payload'} <= event.keys()
            assert event['order'] == (last_order + 1 if event['step'] == last_event_step else 0)
            assert event['listener'] == 'StepListener'
            last_order, last_event_step = event['order'], event['step']
            methods[event['method']] += 1
        else:
            states += 1
            assert len(event['state']['bodies']) == 1 and event['state']['joints'] == []
            body = event['state']['bodies'][0]
            assert {'id', 'transform', 'previousTransform', 'worldCenter', 'fixedOriginPosition', 'velocity', 'angularVelocity', 'atRest', 'force', 'torque', 'accumulatedForce', 'accumulatedTorque', 'rotationIncrementSum'} <= body.keys()
            assert body['id'] == 'b0' and not body['atRest']
            assert len(body['worldCenter']) == 2
            for axis in range(2):
                assert body['fixedOriginPosition'][axis] == body['worldCenter'][axis] - inputs['origin'][axis]
                expected = initial_body['worldCenter'][axis] + initial_body['velocity'][axis] * (states * inputs['dt'])
                error = abs(body['worldCenter'][axis] - expected)
                if error > max_errors[axis]:
                    max_errors[axis], max_steps[axis] = error, states
                if error > 1e-10 and first_violation[axis] is None:
                    first_violation[axis] = states
            last_state = body
assert states == expected_audit['states'] == expected_audit['plannedSteps'] == 36000
assert kinds['event'] == expected_audit['listenerEvents'] == 108001
assert sum(kinds.values()) == expected_audit['rawRecords'] == 144002
assert first_violation == [None, None]
manifest = {
    'approval': 'PENDING_HUMAN_APPROVAL',
    'fixture': inputs['id'],
    'original_experiment_revision': revision,
    'baseline_source_revision': '058bf6d982a0fb89b54050f929f6ea9dae53b714',
    'baseline_jar_sha256_provenance_only': '204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e',
    'retrieval': json.loads((out / 'retrieval.json').read_text()),
    'raw_file': name,
    'input_sha256_utf8_excluding_newline': expected_input,
    'decompressed_stream_sha256_including_newlines': stream_hash.hexdigest(),
    'input': inputs,
    'record_counts': dict(kinds),
    'callback_method_counts': dict(methods),
    'state_event_audit': 'PASS',
    'analytical_position': {'formula': 'initial_position[axis] + initial_velocity[axis] * (step * fixed_dt)', 'units': 'metres', 'samples_per_axis': states, 'absolute_limit_per_axis': 1e-10, 'relative_limit': 0, 'maximum_absolute_errors_xy': max_errors, 'maximum_error_steps_xy': max_steps, 'first_violating_steps_xy': first_violation, 'result': 'PASS'},
    'final_state': last_state,
    'proposed_roles': ['numerical_trajectory_reference_pending_other_limits', 'exact_discrete_and_callback_behavior', 'fixture_specific_approved_analytical_position_check', 'physical_diagnostics_without_new_limits'],
    'source_sha256': {p: sha(source(p)) for p in ['calibration/src/SceneCases.java', 'calibration/src/Capture.java', 'calibration/src/Audit.java', 'docs/research/calibration-evidence/input-manifest.jsonl', 'docs/research/calibration-evidence/audit-manifest.jsonl']},
}
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n')
print(json.dumps({k: manifest[k] for k in ['approval', 'record_counts', 'callback_method_counts', 'state_event_audit', 'analytical_position']}, indent=2))
