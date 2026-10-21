import hashlib
import json
import math
import re
from pathlib import Path

from cases import declared_cases
from receipt import Rejected, exact, inspect, records


CASE_ID = "P-JINT-Pulley-slack-transition-preparation-0"
CLASS_NAME = "org.dyn4j.dynamics.joint.PulleyJoint"
BASELINE_JAR_SHA256 = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
LOCATIONS = {
    "baseline": ("PulleyJoint.java", 288, 281, False),
    "candidate": ("PulleyJoint.kt", 101, 275, True),
}
WORKER_FIELDS = {"schema", "pid", "case_id", "step", "nonce",
                 "case_sha256", "artifact_sha256", "class_source_uri"}
MANIFEST_FIELDS = {"schema", "profile", "pid", "nonce", "artifact_sha256",
                   "case_sha256", "worker_receipt_sha256", "events_sha256",
                   "class_source_name", "class_source_uri", "debuggee_exit"}
EVENT_FIELDS = {"schema", "sequence", "pid", "case_id", "step", "class_name",
                "method", "source_name", "line", "code_index", "branch",
                "l1", "l2", "l", "length", "ratio", "slack_enabled", "over_length"}


def _require(condition, reason):
    if not condition:
        raise Rejected(reason)


def _digest(path, maximum=None):
    path = Path(path)
    _require(path.is_file() and not path.is_symlink(), "evidence file is absent or linked")
    if maximum is not None:
        _require(path.stat().st_size <= maximum, "evidence file exceeds one-case bound")
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value, "duplicate evidence key")
        value[key] = item
    return value


def _json(path, fields):
    _digest(path, 16 * 1024)
    try:
        value = json.loads(Path(path).read_bytes(), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_require(False, "nonfinite evidence value")))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise Rejected("evidence JSON is malformed") from error
    _require(isinstance(value, dict) and value.keys() == fields,
             "evidence schema fields differ")
    return value


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def inspect_bundle(case_path, worker_path, events_path, manifest_path, artifact_path):
    case_path = Path(case_path)
    worker_path = Path(worker_path)
    events_path = Path(events_path)
    manifest_path = Path(manifest_path)
    artifact_path = Path(artifact_path)
    _require(len({path.parent.resolve() for path in
                  (case_path, worker_path, events_path, manifest_path)}) == 1,
             "one-case evidence directory differs")
    case_hash = _digest(case_path, 16 * 1024 * 1024)
    artifact_hash = _digest(artifact_path)
    worker_hash = _digest(worker_path, 16 * 1024)
    events_hash = _digest(events_path, 64 * 1024)
    worker = _json(worker_path, WORKER_FIELDS)
    manifest = _json(manifest_path, MANIFEST_FIELDS)
    _require(isinstance(manifest["profile"], str) and
             manifest["profile"] in LOCATIONS, "Pulley JDI profile differs")
    if manifest["profile"] == "baseline":
        _require(artifact_hash == BASELINE_JAR_SHA256, "pinned baseline artifact differs")
    _require(worker["schema"] == "pulley-preparation-worker/1" and
             manifest["schema"] == "pulley-jdi/1", "Pulley evidence version differs")
    _require(type(worker["pid"]) is int and worker["pid"] > 0 and
             type(manifest["pid"]) is int and manifest["pid"] == worker["pid"],
             "worker and JDI PID differ")
    _require(worker["case_id"] == CASE_ID and type(worker["step"]) is int and
             worker["step"] == 1 and manifest["debuggee_exit"] == 0 and
             type(manifest["debuggee_exit"]) is int,
             "case, step, or debuggee completion differs")
    _require(_sha(worker["nonce"]) and worker["nonce"] == manifest["nonce"],
             "one-case nonce differs")
    _require(all(_sha(value) for value in
                 (worker["case_sha256"], worker["artifact_sha256"],
                  manifest["case_sha256"], manifest["artifact_sha256"],
                  manifest["worker_receipt_sha256"], manifest["events_sha256"])) and
             worker["case_sha256"] == manifest["case_sha256"] == case_hash and
             worker["artifact_sha256"] == manifest["artifact_sha256"] == artifact_hash and
             manifest["worker_receipt_sha256"] == worker_hash and
             manifest["events_sha256"] == events_hash,
             "one-case evidence hashes differ")
    uri = artifact_path.resolve().as_uri()
    _require(worker["class_source_uri"] == manifest["class_source_uri"] == uri,
             "loaded class source declaration differs")
    source, line, code_index, over_length = LOCATIONS[manifest["profile"]]
    _require(manifest["class_source_name"] == source,
             "loaded class source name differs")

    case = next((item for item in declared_cases() if item["id"] == CASE_ID), None)
    _require(case is not None, "frozen Pulley case declaration is absent")
    checked = inspect(case_path, [case])
    _require(type(checked["executed_cases"]) is int and
             checked["executed_cases"] == 1 and
             type(checked["states"]) is int and checked["states"] == 1,
             "one-case recorder coverage differs")
    rows = list(records(case_path))
    _require(rows[0].get("kind") == "inputs" and
             rows[-1].get("kind") == "case-end" and
             all(row.get("id") == CASE_ID for row in rows) and
             len([row for row in rows if row.get("kind") == "state"]) == 1 and
             next(row for row in rows if row.get("kind") == "state").get("step") == 1,
             "one-case raw identity differs")
    header = rows[0]
    _require(header.get("family") == case["family"] and
             header.get("profile") == case["profile"] and
             header.get("hz") == 60 and header.get("steps") == 1 and
             header.get("startStep") == 0 and exact(header.get("input"), case["input"]),
             "frozen Pulley input declaration differs")

    events = list(records(events_path))
    _require(len(events) == 1 and events[0].keys() == EVENT_FIELDS,
             "Pulley call count or event schema differs")
    event = events[0]
    _require(event["schema"] == "pulley-jdi-event/1" and
             type(event["sequence"]) is int and event["sequence"] == 1 and
             type(event["pid"]) is int and event["pid"] == worker["pid"] and
             event["case_id"] == CASE_ID and type(event["step"]) is int and
             event["step"] == 1, "Pulley call order or process differs")
    _require(event["class_name"] == CLASS_NAME and
             event["method"] == "initializeConstraints" and
             event["source_name"] == source and
             type(event["line"]) is int and event["line"] == line and
             type(event["code_index"]) is int and event["code_index"] == code_index,
             "Pulley target location differs")
    _require(all(_number(event[name]) for name in
                 ("l1", "l2", "l", "length", "ratio")) and
             event["l1"] >= 0 and event["l2"] >= 0 and event["length"] > 0 and
             exact(event["l"], event["l1"] + event["l2"]) and
             exact(event["ratio"], 1.0) and
             type(event["slack_enabled"]) is bool and not event["slack_enabled"] and
             type(event["branch"]) is bool and event["branch"] and
             event["branch"] == (event["l"] > event["length"] or
                                  not event["slack_enabled"]) and
             type(event["over_length"]) is bool and
             event["over_length"] is over_length,
             "Pulley live operands or branch differ")
    return {"status": "UNPASSED_EXTERNAL_PROCESS_PROOF", "observed_calls": 1,
            "case_sha256": case_hash, "artifact_sha256": artifact_hash,
            "worker_pid": worker["pid"]}
