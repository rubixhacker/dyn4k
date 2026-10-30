"""Record golden vectors for the Kotlin port of tools/migration.

Run `python3 tools/harness/migration/vectors/generate_vectors.py` from anywhere, then
`emit_kotlin_vectors.py`. The script imports the Python reference implementation and records the
inputs and outputs of the Python `unittest` suites, plus direct calls for the evidence and artifact
rules whose fixtures are generated here.
"""
import base64
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve()
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools/migration"))

import fixed_replay  # noqa: E402
import journeys  # noqa: E402
import truck_camera  # noqa: E402
import truck_timeline  # noqa: E402
import validate_plain  # noqa: E402
import validate_scene  # noqa: E402
import test_fixed_replay as tf  # noqa: E402
import test_truck_camera as tc  # noqa: E402

vectors = {}

# ---------------------------------------------------------------- fixed replay
fixed_records = []
repeat_records = []
stream_table = {}


def intern_stream(rows):
    text = json.dumps(rows, sort_keys=True)
    key = __import__("hashlib").sha256(text.encode()).hexdigest()
    stream_table.setdefault(key, rows)
    return key

original_compare = tf.FixedReplayComparisonTest.compare
original_repeat = tf.repeatability_difference


def recording_compare(self, baseline, candidate):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for name, rows in (("baseline", baseline), ("candidate", candidate)):
            (root / f"{name}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
        report = fixed_replay.compare(
            root / "baseline.jsonl", root / "candidate.jsonl", "a" * 64, "b" * 64)
        text = json.dumps(report, indent=2, allow_nan=False) + "\n"
        (root / "comparison.json").write_text(text)
    index = self._record_index
    self._record_index += 1
    fixed_records.append({
        "case": f"{self._record_method}#{index}",
        "baseline_sha": intern_stream(baseline),
        "candidate_sha": intern_stream(candidate),
        "report_text": text,
        "exit_code": 0 if report["status"] == "PASSED" else 1,
    })
    return SimpleNamespace(returncode=0 if report["status"] == "PASSED" else 1, stderr=""), report


def recording_repeat(first, second):
    difference = original_repeat(first, second)
    repeat_records.append({"first": first, "second": second, "difference": difference})
    return difference


tf.FixedReplayComparisonTest.compare = recording_compare
tf.repeatability_difference = recording_repeat
loader = unittest.TestLoader()
tests = loader.loadTestsFromTestCase(tf.FixedReplayComparisonTest)
outcome = unittest.TestResult()
for case in tests:
    case._record_method = case._testMethodName
    case._record_index = 0
    case.run(outcome)
if not outcome.wasSuccessful():
    raise SystemExit(outcome.errors + outcome.failures)
vectors["fixed_replay"] = {"cases": fixed_records, "streams": stream_table,
                           "repeatability": repeat_records}


def _attempt(block):
    try:
        return {"ok": block()}
    except Exception as error:  # noqa: BLE001 - the vector records the message
        return {"error": str(error), "type": type(error).__name__}


vectors["process_identity"] = [
    {"stderr": text, "result": _attempt(lambda text=text: fixed_replay.process_identity(text))}
    for text in (
        "REPLAY_PROCESS pid=1 start_ms=2\n",
        "prefix\nREPLAY_PROCESS pid=9 start_ms=4\nsuffix\n",
        "",
        "REPLAY_PROCESS pid=1\n",
        "REPLAY_PROCESS pid=1 start_ms=2\nREPLAY_PROCESS pid=2 start_ms=3\n",
    )
]

difference_cases = []
for left, right in (
    (1, 1.0),
    (True, 1),
    ({"a": 1}, {"a": 1.0}),
    ([1, 2], [1]),
    ("x", "x"),
    ("x", "y"),
    (0.3, 0.30001),
    (0.3, 0.31),
    ({"b": 1, "a": 2}, {"a": 2, "b": 1}),
    ({"a": 1}, {"b": 1}),
    (0.0001, 0.00019),
    (1e-3, 1.5e-3),
):
    for path, limits in (
        ("input.power", {}),
        ("step[0].bodies[0].x", fixed_replay.LIMITS),
        ("input.angle", fixed_replay.LIMITS),
    ):
        difference_cases.append({
            "left": left, "right": right, "path": path,
            "limits": "default" if limits else "none",
            "result": fixed_replay.first_difference(left, right, path, limits),
        })
vectors["first_difference"] = difference_cases


# ---------------------------------------------------------------- scene validation
INPUTS = {
    "headless_tracking": ("Tracking", "java.awt.HeadlessException\n", "scene=Tracking\nkey c\n"),
}
bodies = [{"i": i, "x": float(i), "y": 0.0, "vx": 0.0, "vy": 0.0, "rest": True} for i in range(21)]
billiards = []
for index in range(2):
    billiards.append({
        "scene": "Billiards", "threadId": 2, "nanos": index + 1, "bodyCount": 21,
        "jointCount": 0, "resets": 0, "ccdMode": "ALL", "begin": 1, "persist": 1, "end": 1,
        "toiCalls": 5, "toiHits": 0, "toiListenerHits": 0, "bodies": bodies, "joints": [],
    })
billiards_log = "\n".join("OBS_JSON " + json.dumps(r) for r in billiards)

tracking_bodies = [{"i": i, "x": float(i), "y": 0.0, "vx": 0.0, "vy": 0.0, "rest": False}
                   for i in range(9)]
capture = [{
    "scene": "Tracking", "threadId": 2, "nanos": index + 1, "bodyCount": 9,
    "jointCount": 0, "resets": 0, "ccdMode": "ALL", "begin": 1, "persist": 1, "end": 1,
    "toiCalls": 0, "toiHits": 0, "toiListenerHits": 0, "steps": 0, "stepDt": 0.0,
    "bodies": tracking_bodies, "joints": [],
} for index in range(2)]
capture_log = ("BEGIN: 1\nEND: 1\nOBSERVER_SHUTDOWN joined=true disposed=true\n" +
               "\n".join("OBS_JSON " + json.dumps(r) for r in capture))

truck_bodies = [{"i": i, "x": float(i), "y": 0.0, "vx": 0.0, "vy": 0.0, "rest": False}
                for i in range(35)]
truck_joints = [{"i": i, "type": "WheelJoint", "motorSpeed": 1.0, "translation": 0.0}
                for i in range(2)]
truck_records = [{
    "scene": "Truck", "threadId": 2, "nanos": index + 1, "bodyCount": 35,
    "jointCount": 2, "resets": 0, "ccdMode": "NONE", "begin": 0, "persist": 0, "end": 0,
    "toiCalls": 0, "toiHits": 0, "toiListenerHits": 0, "steps": index + 1,
    "stepDt": 1 / 60, "bodies": truck_bodies, "joints": truck_joints,
} for index in range(2)]
truck_log = ("OBSERVER_SHUTDOWN joined=true disposed=true\n" +
             "\n".join("OBS_JSON " + json.dumps(r) for r in truck_records))

scene_cases = [
    ("headless_exception_tracking", "Tracking", "java.awt.HeadlessException\n", "scene=Tracking\nkey c\n"),
    ("billiards_without_ccd_hit", "Billiards", billiards_log,
     "scene=Billiards\nkeydown plus\nkeydown s\nkeyup s\n"),
    ("capture_time_without_steps", "Tracking", capture_log, "scene=Tracking\nkey c\n"),
    ("truck_observations_without_timeline", "Truck", truck_log,
     "scene=Truck\nkeydown Right\nkey s\n"),
]


def run_scene_cli(scene, log, inputs):
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        (folder / "observer.log").write_text(log)
        (folder / "inputs.log").write_text(inputs)
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/migration/validate_scene.py"), scene,
             str(folder / "observer.log"), str(folder / "inputs.log"),
             str(folder / "result.json")],
            capture_output=True, text=True, check=False,
        )
        return {
            "scene": scene, "log": log, "inputs": inputs,
            "result_text": (folder / "result.json").read_text().replace(str(folder), "<work>"),
            "stdout": result.stdout.replace(str(folder), "<work>"),
            "exit_code": result.returncode,
        }


scene_records = [run_scene_cli(*case[1:]) for case in scene_cases]
for record, case in zip(scene_records, scene_cases):
    record["case"] = case[0]
vectors["scene_validation"] = scene_records

# ---------------------------------------------------------------- truck timeline
valid_png = tc.valid_png()
vectors["valid_png_base64"] = base64.b64encode(valid_png).decode()
tt = tc.TruckTimelineTest("test_complete_timeline_reports_integrity_without_visual_claim")
timeline_records = []


def record_timeline(name, rows, directory, keep_rows=False):
    tt.write_rows(directory, rows)
    passed, evidence = truck_timeline.validate(directory)
    record = {
        "case": name,
        "rows_sha256": __import__("hashlib").sha256(
            "".join(json.dumps(row) + "\n" for row in rows).encode()).hexdigest(),
        "passed": passed, "evidence": evidence,
    }
    if keep_rows:
        record["rows"] = rows
    timeline_records.append(record)


with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    rows = tt.make_evidence(folder)
    record_timeline("complete", rows, folder, keep_rows=True)

    for change in ("missing", "late", "scene", "short", "extended"):
        changed = [dict(row) for row in rows]
        if change == "missing":
            changed = [row for row in changed
                       if not (row["kind"] == "frame" and row["name"] == "drive-4")]
        elif change == "late":
            next(row for row in changed if row["kind"] == "frame" and row["name"] == "drive-4")[
                "start_ns"] += 300_000_000
        elif change == "scene":
            changed[0]["name"] = "Crank"
        else:
            row = next(row for row in changed if row["kind"] == "key" and row["name"] == "keyup-s")
            row["start_ns"] += -500_000_000 if change == "short" else 500_000_000
            row["end_ns"] += -500_000_000 if change == "short" else 500_000_000
        record_timeline(change, changed, folder)

    rows = tt.make_evidence(folder)
    camera = next(row for row in rows if row["kind"] == "camera" and row["name"] == "follow-01")
    down = next(row for row in rows if row["kind"] == "pointer" and row["name"] == "follow-01-down")
    down["start_ns"] = camera["end_ns"] + 1
    down["end_ns"] = down["start_ns"] + 1
    record_timeline("press_after_move", rows, folder)

    rows = tt.make_evidence(folder)
    position = next(row for row in rows
                    if row["kind"] == "pointer" and row["name"] == "follow-01-position")
    down = next(row for row in rows if row["kind"] == "pointer" and row["name"] == "follow-01-down")
    position["end_ns"] = down["start_ns"] + 1
    record_timeline("overlapping_position", rows, folder)

    rows = tt.make_evidence(folder)
    up = next(row for row in rows if row["kind"] == "pointer" and row["name"] == "follow-01-up")
    up["name"] = "follow-02-up"
    record_timeline("wrong_association", rows, folder)

    for release_name, next_name in (
        ("setup-up", "follow-01-position"),
        ("follow-01-up", "follow-02-down"),
        ("follow-13-up", "brake-follow-1-position"),
        ("brake-follow-1-up", "brake-follow-2-down"),
    ):
        rows = tt.make_evidence(folder)
        release = next(row for row in rows if row["kind"] == "pointer" and row["name"] == release_name)
        next_event = next(row for row in rows if row["kind"] == "pointer" and row["name"] == next_name)
        release["start_ns"] = next_event["start_ns"]
        release["end_ns"] = release["start_ns"] + 1
        record_timeline(f"boundary_{release_name}", rows, folder)

    rows = tt.make_evidence(folder)
    rows = [row for row in rows if row["name"] != "follow-01-position"]
    record_timeline("missing_position", rows, folder)

    rows = tt.make_evidence(folder)
    release = next(row for row in rows if row["kind"] == "pointer" and row["name"] == "follow-01-up")
    rows.append(dict(release))
    record_timeline("duplicate_release", rows, folder)

    rows = tt.make_evidence(folder)
    camera = next(row for row in rows if row["kind"] == "camera" and row["name"] == "follow-13")
    key_up = next(row for row in rows if row["kind"] == "key" and row["name"] == "keyup-Right")
    pointer_up = next(row for row in rows if row["kind"] == "pointer" and row["name"] == "follow-13-up")
    camera["end_ns"] = key_up["start_ns"] + 1
    pointer_up["start_ns"] = camera["end_ns"]
    pointer_up["end_ns"] = pointer_up["start_ns"] + 1
    record_timeline("key_release_overlap", rows, folder)

    original = valid_png
    corrupt_payload = bytearray(original)
    corrupt_payload[41] ^= 1
    idat_crc = 41 + int.from_bytes(original[33:37], "big")
    corrupt_payload[idat_crc:idat_crc + 4] = zlib.crc32(corrupt_payload[37:idat_crc]).to_bytes(4, "big")
    png_cases = {
        "truncated": original[:-12],
        "corrupt_payload": bytes(corrupt_payload),
        "corrupt_crc": original[:-16] + bytes([original[-16] ^ 1]) + original[-15:],
        "malformed_chunk": original[:33] + b"\xff\xff\xff\xff" + original[37:],
        "oversized": original + b"x" * (16 * 1024 * 1024),
        "header_only": original[:24],
    }
    for name, data in png_cases.items():
        rows = tt.make_evidence(folder)
        tt.write_rows(folder, rows)
        (folder / "initial.png").write_bytes(data)
        digest = next(row for row in rows if row["kind"] == "frame_hash" and row["name"] == "initial")
        digest["sha256"] = __import__("hashlib").sha256(data).hexdigest()
        tt.write_rows(folder, rows)
        passed, evidence = truck_timeline.validate(folder)
        timeline_records.append({
            "case": f"png_{name}",
            "rows_sha256": __import__("hashlib").sha256(
                "".join(json.dumps(row) + "\n" for row in rows).encode()).hexdigest(),
            "passed": passed, "evidence": evidence})
vectors["truck_timeline"] = timeline_records

# ---------------------------------------------------------------- plain validation
plain_records = []


def plain_context(directory, scene):
    tt.make_plain_context(directory, scene)


def record_plain(name, scene, directory):
    result = validate_plain.validate(scene, directory)
    plain_records.append({
        "case": name, "scene": scene, "result_text": json.dumps(result, indent=2) + "\n",
    })


with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    tt.make_plain_truck(folder)
    record_plain("truck_complete", "Truck", folder)

    corrupt = bytearray(valid_png)
    corrupt[41] ^= 1
    idat_crc = 41 + int.from_bytes(valid_png[33:37], "big")
    corrupt[idat_crc:idat_crc + 4] = zlib.crc32(corrupt[37:idat_crc]).to_bytes(4, "big")
    malformed = {
        "header_only": valid_png[:24],
        "corrupt_payload": bytes(corrupt),
        "truncated": valid_png[:-12],
        "oversized": valid_png + b"x" * (16 * 1024 * 1024 + 1 - len(valid_png)),
    }
    for label, data in malformed.items():
        folder = Path(tempfile.mkdtemp())
        try:
            tt.make_plain_truck(folder)
            (folder / "late.png").write_bytes(data)
            record_plain(f"truck_late_{label}", "Truck", folder)
        finally:
            shutil.rmtree(folder)

    for label in ("valid", *malformed.keys()):
        folder = Path(tempfile.mkdtemp())
        try:
            plain_context(folder, "Pyramid")
            for frame_name in ("initial", "after-input", "late", "interaction"):
                (folder / (frame_name + ".png")).write_bytes(valid_png)
            if label != "valid":
                (folder / "interaction.png").write_bytes(malformed[label])
            record_plain(f"pyramid_interaction_{label}", "Pyramid", folder)
        finally:
            shutil.rmtree(folder)
vectors["plain_validation"] = plain_records

# ---------------------------------------------------------------- journeys
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_AUTHOR_DATE": "2020-01-01T00:00:00 +0000",
    "GIT_COMMITTER_DATE": "2020-01-01T00:00:00 +0000",
}
EMPTY_JAR = b"PK\x05\x06" + b"\x00" * 18


def make_repo(path, files):
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True, env=GIT_ENV)
    for relative, content in files.items():
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, env=GIT_ENV)
    subprocess.run(
        ["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
         "commit", "-qm", "fixture"],
        check=True, env=GIT_ENV,
    )
    return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


work = Path(tempfile.mkdtemp(prefix="migration-vectors-"))
samples = work / "samples"
source_files = {
    f"src/main/java/fixture/Sample{index:02d}.java":
        ("package fixture;\npublic class Sample%02d { public static class Inner { } }\n" % index).encode()
    for index in range(1, 43)
}
samples_revision = make_repo(samples, source_files)
manifest = "".join(
    f"{__import__('hashlib').sha256((samples / path).read_bytes()).hexdigest()}  {path}\n"
    for path in sorted(source_files)
)
manifest_digest = __import__("hashlib").sha256(manifest.encode()).hexdigest()
candidate = work / "candidate"
candidate_commit = make_repo(candidate, {"marker.txt": b"fixture\n"})

journeys.ROOT = candidate
journeys.SAMPLE_REVISION = samples_revision
journeys.SOURCE_MANIFEST_SHA256 = manifest_digest
journeys.PINNED_JARS = {
    "dyn4j-6.0.0.jar": __import__("hashlib").sha256(EMPTY_JAR).hexdigest(),
    "jogl-all-2.3.2.jar": __import__("hashlib").sha256(EMPTY_JAR).hexdigest(),
    "gluegen-rt-2.3.2.jar": __import__("hashlib").sha256(EMPTY_JAR).hexdigest(),
}
journey_vectors = {
    "samples_revision": samples_revision,
    "candidate_commit": candidate_commit,
    "manifest_sha256": manifest_digest,
    "empty_jar_sha256": __import__("hashlib").sha256(EMPTY_JAR).hexdigest(),
}


def attempt(block):
    try:
        return {"ok": block()}
    except Exception as error:  # noqa: BLE001 - the vector records the message
        return {"error": str(error), "type": type(error).__name__}


journey_vectors["inspect_samples"] = attempt(lambda: journeys.inspect_samples(samples))

dirty = work / "samples-dirty"
shutil.copytree(samples, dirty)
target = next(dirty.glob("src/main/java/**/*.java"))
target.write_bytes(target.read_bytes() + b"\n")
journey_vectors["inspect_samples_dirty"] = attempt(lambda: journeys.inspect_samples(dirty))

baseline = work / "resolved-baseline"
baseline.mkdir()
for name in ("dyn4j-6.0.0.jar", "jogl-all-2.3.2.jar", "gluegen-rt-2.3.2.jar"):
    (baseline / name).write_bytes(EMPTY_JAR)
journey_vectors["baseline_artifacts"] = attempt(
    lambda: journeys.inspect_artifacts("baseline", baseline, None))
changed = work / "resolved-baseline-changed"
shutil.copytree(baseline, changed)
(changed / "dyn4j-6.0.0.jar").write_bytes(b"changed")
journey_vectors["baseline_artifacts_changed"] = attempt(
    lambda: journeys.inspect_artifacts("baseline", changed, None))

resolved_candidate = work / "resolved-candidate"
resolved_candidate.mkdir()
staged = work / "staged"
staged_jar = staged / "io/github/rubixhacker/dyn4k-core-jvm/0.1.0-alpha.1" / journeys.CANDIDATE_JAR
staged_jar.parent.mkdir(parents=True)
staged_jar.write_bytes(EMPTY_JAR)
staged_jar.with_suffix(".pom").write_text(
    "<project><groupId>io.github.rubixhacker</groupId>"
    "<artifactId>dyn4k-core-jvm</artifactId><version>0.1.0-alpha.1</version></project>")
staged_jar.with_suffix(".module").write_text("{}")
shutil.copy2(staged_jar, resolved_candidate / staged_jar.name)
for name in ("jogl-all-2.3.2.jar", "gluegen-rt-2.3.2.jar"):
    (resolved_candidate / name).write_bytes(EMPTY_JAR)
journey_vectors["candidate_artifacts"] = attempt(
    lambda: journeys.inspect_artifacts("candidate", resolved_candidate, staged))
(resolved_candidate / staged_jar.name).write_bytes(b"project source output")
journey_vectors["candidate_artifacts_unstaged"] = attempt(
    lambda: journeys.inspect_artifacts("candidate", resolved_candidate, staged))
shutil.copy2(staged_jar, resolved_candidate / staged_jar.name)
(resolved_candidate / "dyn4j-6.0.0.jar").write_bytes(EMPTY_JAR)
journey_vectors["candidate_artifacts_duplicate"] = attempt(
    lambda: journeys.inspect_artifacts("candidate", resolved_candidate, staged))
(resolved_candidate / "dyn4j-6.0.0.jar").unlink()
staged_jar.with_suffix(".pom").unlink()
journey_vectors["candidate_artifacts_missing_metadata"] = attempt(
    lambda: journeys.inspect_artifacts("candidate", resolved_candidate, staged))
staged_jar.with_suffix(".pom").write_text(
    "<project><groupId>io.github.other</groupId>"
    "<artifactId>dyn4k-core-jvm</artifactId><version>0.1.0-alpha.1</version></project>")
journey_vectors["candidate_artifacts_identity"] = attempt(
    lambda: journeys.inspect_artifacts("candidate", resolved_candidate, staged))
staged_jar.with_suffix(".pom").write_text(
    "<project><groupId>io.github.rubixhacker</groupId>"
    "<artifactId>dyn4k-core-jvm</artifactId><version>0.1.0-alpha.1</version></project>")

empty = work / "resolved-empty"
empty.mkdir()
journey_vectors["baseline_artifacts_empty"] = attempt(
    lambda: journeys.inspect_artifacts("baseline", empty, None))

empty_evidence = work / "evidence-empty"
journey_vectors["unavailable_empty"] = {
    "files": {},
    "reason": "no display",
    "summary_text": None,
}
journeys.record_unavailable(empty_evidence, "no display")
journey_vectors["unavailable_empty"]["summary_text"] = (
    empty_evidence / "summary.json").read_text()
journey_vectors["unavailable_empty"]["evidence_text"] = (
    empty_evidence / "evidence.sha256").read_text()
journey_vectors["unavailable_empty"]["verify"] = attempt(
    lambda: journeys.verify_evidence(empty_evidence))

evidence = work / "evidence"
evidence.mkdir()
(evidence / "raw.log").write_text("original observation\n")
(evidence / "a.log").write_text("earlier evidence\n")
report = journeys.record_unavailable(evidence, "no display")
journey_vectors["unavailable_with_files"] = {
    "files": {"raw.log": "original observation\n", "a.log": "earlier evidence\n"},
    "reason": "no display",
    "summary_text": (evidence / "summary.json").read_text(),
    "evidence_text": (evidence / "evidence.sha256").read_text(),
    "verify": attempt(lambda: journeys.verify_evidence(evidence)),
}
(evidence / "raw.log").write_text("changed observation\n")
journey_vectors["unavailable_with_files_changed"] = attempt(
    lambda: journeys.verify_evidence(evidence))

# compile receipts. Paths, the javac identity, and its version line differ per host and checkout
# root, so the vector records the receipt with those three values replaced by placeholders.
def normalise(value, javac):
    text = json.dumps(value, indent=2, sort_keys=False) + "\n"
    text = text.replace(str(javac), "<javac>")
    text = text.replace(str(work), "<work>")
    value = json.loads(text)
    if isinstance(value, dict) and "javac_version" in value:
        value["javac_version"] = "<version>"
    return value


javac = shutil.which("javac")
output = work / "compile-ok"
receipt = journeys.compile_samples("baseline", samples, baseline, None, output, javac)
journey_vectors["compile_success"] = {
    "receipt": normalise(receipt, javac),
    "log_contains_version": "-version" in (output / "javac-version.log").read_text()
    or bool((output / "javac-version.log").read_text()),
    "class_count": receipt["class_count"],
    "classes_present": (output / "classes/fixture/Sample01.class").is_file(),
}

slow = work / "slow-javac"
slow.write_text("#!/bin/sh\nsleep 5\n")
slow.chmod(0o755)
timeout_output = work / "compile-timeout"
timeout_receipt = journeys.compile_samples("baseline", samples, baseline, None, timeout_output,
                                           slow, 0.2)
journey_vectors["compile_timeout"] = {
    "receipt": normalise(timeout_receipt, slow),
    "log_contains_timeout": "PROCESS TIMEOUT" in (timeout_output / "javac.log").read_text(),
}

missing_output = work / "compile-missing"
missing_receipt = journeys.compile_samples("baseline", samples, work / "missing", None,
                                           missing_output, javac)
journey_vectors["compile_missing_dependency"] = {
    "receipt": normalise(missing_receipt, javac),
}

# run-all against a missing headful image, with a javac wrapper that mutates one sample after the
# second `--release` compile.
wrapper = work / "counting-javac"
counter = work / "compile-count"
wrapper.write_text(
    "#!/bin/sh\n"
    f"{javac} \"$@\"\n"
    "result=$?\n"
    "if [ \"$result\" -eq 0 ] && [ \"$1\" = \"--release\" ]; then\n"
    f"  printf 'x\\n' >> \"{counter}\"\n"
    f"  if [ \"$(wc -l < \"{counter}\")\" -eq 2 ] && [ -n \"$MIGRATION_TEST_MUTATE_SOURCE\" ]; then\n"
    "    printf '\\n' >> \"$MIGRATION_TEST_MUTATE_SOURCE\"\n"
    "  fi\n"
    "fi\n"
    "exit \"$result\"\n"
)
wrapper.chmod(0o755)
resolved_root = work / "resolved-root"
(resolved_root / "baseline").mkdir(parents=True)
for name in ("dyn4j-6.0.0.jar", "jogl-all-2.3.2.jar", "gluegen-rt-2.3.2.jar"):
    (resolved_root / "baseline" / name).write_bytes(EMPTY_JAR)
(resolved_root / "candidate").mkdir(parents=True)
for name in ("jogl-all-2.3.2.jar", "gluegen-rt-2.3.2.jar"):
    (resolved_root / "candidate" / name).write_bytes(EMPTY_JAR)
shutil.copy2(staged_jar, resolved_root / "candidate" / staged_jar.name)


def run_all(change_sample):
    output = work / ("run-all-" + ("changed" if change_sample else "stable"))
    os.environ["MIGRATION_TEST_MUTATE_SOURCE"] = (
        str(samples / "src/main/java/fixture/Sample01.java") if change_sample else ""
    )
    error = None
    passed = 0
    try:
        report = journeys.run_all(
            samples, resolved_root, staged, work / "instrumentation", output,
            wrapper, javac, work / "jdk",
            "localhost/dyn4k-migration:missing-test-image", 180,
        )
        passed = report["passed_cases"]
        exit_code = 0 if passed == report["expected_cases"] else 1
    except Exception as failure:  # noqa: BLE001 - the run reports the failure
        error = str(failure)
        exit_code = 1
    receipts = {}
    # The summary text binds the digest of every written file, and the compiler receipts carry
    # the generator's temporary root. The structured summary is recorded separately.
    for path in ("preparation.json", "sample-check.json",
                 "candidate-check.json", "image-exists.log"):
        if (output / path).is_file():
            receipts[path] = (output / path).read_text()
    for provider in ("baseline", "candidate"):
        compile_path = output / provider / "compile/compile.json"
        if compile_path.is_file():
            receipts[f"{provider}-compile.json"] = compile_path.read_text()
    summary = json.loads((output / "summary.json").read_text()) if (
        output / "summary.json").is_file() else None
    normalised_summary = None
    if summary is not None:
        summary.pop("evidence_manifest_sha256", None)
        summary.pop("evidence_file_count", None)
        normalised_summary = normalise(summary, wrapper)
    changed = {}
    for key, text in receipts.items():
        value = text
        if key.endswith("compile.json"):
            value = json.dumps(normalise(json.loads(text), wrapper)) + "\n"
        else:
            value = value.replace(str(wrapper), "<javac>").replace(str(work), "<work>")
        changed[key] = value
    return {
        "output_exists": output.exists(),
        "summary_absent": not (output / "summary.json").is_file(),
        "summary": normalised_summary,
        "receipts": changed,
        "error": error,
        "exit_code": exit_code,
        "samples": samples,
        "git_status_nonempty": bool(subprocess.run(
            ["git", "-C", str(samples), "status", "--porcelain=v1"],
            capture_output=True, check=True).stdout),
    }


journey_vectors["run_all_changed"] = {
    key: value for key, value in run_all(True).items() if key not in ("samples",)
}
subprocess.run(["git", "-C", str(samples), "checkout", "--", "."], check=True, env=GIT_ENV)
journey_vectors["run_all_stable"] = {
    key: value for key, value in run_all(False).items() if key not in ("samples",)
}

vectors["journeys"] = journey_vectors
vectors["fixture"] = {
    "samples_files": source_files and {str(path): True for path in sorted(source_files)},
    "candidate_files": ["marker.txt"],
    "empty_jar_base64": base64.b64encode(EMPTY_JAR).decode(),
}

target = ROOT / "tools/harness/migration/build/vectors"
target.mkdir(parents=True, exist_ok=True)
(target / "migration-vectors.json").write_text(json.dumps(vectors, indent=1, sort_keys=True) + "\n")
print("wrote", target / "migration-vectors.json")
shutil.rmtree(work, ignore_errors=True)
