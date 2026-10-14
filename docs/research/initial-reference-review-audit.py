# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: python3 initial-reference-review-audit.py EXTRACT_PARENT DYN4K_GIT_REPO
import collections
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

if len(sys.argv) != 3:
    raise SystemExit('Usage: python3 initial-reference-review-audit.py EXTRACT_PARENT DYN4K_GIT_REPO')
if not __debug__:
    raise SystemExit('Assertions are required; do not run with Python optimization enabled')
root = Path(sys.argv[1]).resolve()
archive = root / 'dyn4k-sleep-evidence'
revision = '0995a6bac84de882b0d04b6c3ea18162ca3b4a7c'
repo = str(Path(sys.argv[2]).resolve())

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def git_file(path: str) -> bytes:
    return subprocess.check_output(['git', '-C', repo, 'show', f'{revision}:{path}'])

def reject_constant(value: str) -> None:
    raise ValueError(value)

def finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(value)
    return parsed

checks = subprocess.run(['sha256sum', '-c', 'dyn4k-sleep-evidence/SHA256SUMS'], cwd=root, capture_output=True, text=True)
(root / 'internal-checksums.log').write_text(checks.stdout + checks.stderr)
assert checks.returncode == 0
manifest = {
    'status': 'PENDING_HUMAN_APPROVAL',
    'baseline_source_revision': '058bf6d982a0fb89b54050f929f6ea9dae53b714',
    'baseline_jar_sha256': sha((archive / 'dyn4j-6.0.0.jar').read_bytes()),
    'sleep_archive_sha256': sha((root / 'dyn4j-sleep-wake-20260914.tar.gz').read_bytes()),
    'sleep_archive_bytes': (root / 'dyn4j-sleep-wake-20260914.tar.gz').stat().st_size,
    'sleep_archive_members_verified': len(checks.stdout.splitlines()),
    'sleep_sources': {str(p.relative_to(archive)): sha(p.read_bytes()) for p in sorted((archive / 'source').iterdir())},
    'original_git_revision': revision,
    'original_inspected_files': {},
    'sleep_candidates': [],
}
for path in ['calibration/src/Capture.java', 'calibration/src/SceneCases.java', 'calibration/src/Audit.java', 'calibration/src/InputManifest.java', 'docs/research/calibration-evidence/input-manifest.jsonl', 'docs/research/calibration-evidence/audit-manifest.jsonl', 'docs/research/calibration-evidence/sources.sha256', 'docs/research/calibration-evidence/raw-archive/repeat-a-trace-sha256.txt', 'docs/research/calibration-evidence/raw-archive/repeat-b-trace-sha256.txt', 'docs/research/calibration-evidence/raw-archive/chunk-sha256.txt']:
    manifest['original_inspected_files'][path] = sha(git_file(path))
nominal_file = 'L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz'
input_rows = [row for line in git_file('docs/research/calibration-evidence/input-manifest.jsonl').splitlines() if (row := json.loads(line)).get('traceFile') == nominal_file]
assert len(input_rows) == 1
input_row = input_rows[0]
audit_rows = [row for line in git_file('docs/research/calibration-evidence/audit-manifest.jsonl').splitlines() if (row := json.loads(line)).get('file') == nominal_file]
assert len(audit_rows) == 2 and audit_rows[0] == audit_rows[1]
audit_row = audit_rows[0]
manifest['nominal_free_motion_candidate'] = {'status': 'RAW_TRACE_NOT_RECHECKED_NOT_READY_TO_FREEZE', 'published_input_manifest_entry': input_row, 'published_audit_entry': audit_row}
for hz in [30, 60, 120]:
    name = f'S-sleep-wake-hz{hz}-0.jsonl.gz'
    a = archive / 'run1' / name
    b = archive / 'run2' / name
    assert a.read_bytes() == b.read_bytes()
    row = {'status': 'PENDING_HUMAN_APPROVAL', 'hz': hz, 'selected_member': f'dyn4k-sleep-evidence/run1/{name}', 'corroborating_member': f'dyn4k-sleep-evidence/run2/{name}', 'gzip_sha256': sha(a.read_bytes()), 'gzip_bytes': a.stat().st_size}
    stream_hash = hashlib.sha256()
    kinds = collections.Counter()
    listeners = collections.Counter()
    states = 0
    ordered = (-1, -1)
    window = 0
    first_sleep = None
    return_sleep = None
    special = []
    minimum_y = None
    for raw in gzip.open(a, 'rb'):
        stream_hash.update(raw)
        e = json.loads(raw, parse_constant=reject_constant, parse_float=finite_float)
        kinds[e['kind']] += 1
        assert e['kind'] in {'inputs', 'state', 'event', 'instrumented-callback', 'action'}
        if e['kind'] != 'inputs':
            assert 'step' in e
            assert e['step'] == states + 1
        if e['kind'] in {'event', 'instrumented-callback', 'action'}:
            assert 'order' in e
        if e['kind'] == 'inputs':
            row['input_sha256_utf8_without_newline'] = sha(raw.rstrip(b'\n'))
            row['input'] = e
            assert e['steps'] == 600 * hz and e['dt'] == 1.0 / hz
            assert e['origin'] == [0, 0] and e['scale'] == 1
        if 'order' in e:
            current = (e['step'], e['order'])
            assert current > ordered
            assert e['order'] == (ordered[1] + 1 if e['step'] == ordered[0] else 0)
            ordered = current
        if e['kind'] == 'state':
            states += 1
            assert e['step'] == states
            assert len(e['state']['bodies']) == 2 and not e['state']['joints']
            for body in e['state']['bodies']:
                assert {'id', 'transform', 'previousTransform', 'worldCenter', 'fixedOriginPosition', 'velocity', 'angularVelocity', 'atRest', 'force', 'torque', 'accumulatedForce', 'accumulatedTorque', 'rotationIncrementSum'} <= body.keys()
            body = e['state']['bodies'][1]
            minimum_y = body['worldCenter'][1] if minimum_y is None else min(minimum_y, body['worldCenter'][1])
            if body['atRest'] and first_sleep is None:
                first_sleep = states
            if 299 * hz <= states <= 300 * hz:
                assert body['atRest']
                window += 1
            if states == 300 * hz + 1:
                assert not body['atRest'] and body['velocity'][0] > 0
                row['first_post_action_state'] = body
            if states > 300 * hz and body['atRest'] and return_sleep is None:
                return_sleep = states
        elif e['kind'] == 'event':
            listeners[e['listener']] += 1
        elif e['kind'] in ['instrumented-callback', 'action']:
            special.append(e)
    assert states == 600 * hz and window == hz + 1
    assert kinds['inputs'] == 1 and kinds['action'] == 1 and kinds['instrumented-callback'] == 2
    archived_summary = [json.loads(line) for line in (archive / 'run1/summary.jsonl').read_text().splitlines() if json.loads(line)['file'] == name]
    assert len(archived_summary) == 1 and archived_summary[0]['events'] == kinds['event']
    assert len(special) == 3
    before, action, after = special
    assert before['event'] == 'before-wake' and before['values'][0]['bodies'][1]['atRest']
    assert action['kind'] == 'action' and action['step'] == 300 * hz + 1
    assert after['event'] == 'after-wake'
    assert not after['values'][0]['bodies'][1]['atRest'] and after['values'][0]['bodies'][1]['velocity'] == [1, 0]
    row.update({'decompressed_sha256_including_newlines': stream_hash.hexdigest(), 'records_by_kind': dict(kinds), 'events_by_listener': dict(listeners), 'first_sleep_step': first_sleep, 'action_step': 300 * hz + 1, 'first_return_to_sleep_step': return_sleep, 'preceding_window_samples': window, 'minimum_dynamic_center_y_diagnostic': minimum_y, 'immediate_action_records': special, 'fresh_stream_audit': 'PASS', 'repeat_gzip_bytes_equal': True})
    manifest['sleep_candidates'].append(row)
(root / 'selection-manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n')
print(json.dumps({'internal_files_verified': manifest['sleep_archive_members_verified'], 'sleep': [{k: row[k] for k in ['hz', 'gzip_sha256', 'input_sha256_utf8_without_newline', 'records_by_kind', 'events_by_listener', 'first_sleep_step', 'first_return_to_sleep_step', 'fresh_stream_audit']} for row in manifest['sleep_candidates']], 'free_motion': manifest['nominal_free_motion_candidate']['status']}, indent=2))
