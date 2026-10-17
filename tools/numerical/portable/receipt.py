import hashlib
import json
import math
import struct
from dataclasses import asdict, dataclass
from pathlib import Path


CATALOG = Path(__file__).resolve().parents[1] / "fixtures.json"
BUILD_FILES = ("settings.gradle.kts", "build.gradle.kts")


class Rejected(ValueError):
    pass


@dataclass(frozen=True)
class Identity:
    candidate_commit: str
    source_sha256: str
    artifact_sha256: dict[str, str]
    runtime: object


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exact(left, right):
    if isinstance(left, (int, float)) and not isinstance(left, bool) and isinstance(right, (int, float)) and not isinstance(right, bool):
        return struct.pack(">d", float(left)) == struct.pack(">d", float(right))
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(exact(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(exact(a, b) for a, b in zip(left, right))
    return type(left) is type(right) and left == right


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise Rejected(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value):
    raise Rejected(f"nonfinite JSON token: {value}")


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise Rejected("nonfinite number")
    if isinstance(value, list):
        for child in value:
            _finite(child)
    if isinstance(value, dict):
        if "nonfinite" in value:
            raise Rejected(f"nonfinite recorded value: {value['nonfinite']}")
        for child in value.values():
            _finite(child)


def records(path):
    with Path(path).open("rb") as stream:
        for number, line in enumerate(stream, 1):
            if not line.endswith(b"\n"):
                raise Rejected(f"line {number} has no newline")
            try:
                value = json.loads(line, object_pairs_hook=_pairs, parse_constant=_reject_nonfinite)
            except (UnicodeError, json.JSONDecodeError) as error:
                raise Rejected(f"line {number}: {error}") from error
            if not isinstance(value, dict):
                raise Rejected(f"line {number} is not an object")
            _finite(value)
            yield value


def inspect(path, cases):
    expected = {case["id"]: case for case in cases}
    if not expected or len(expected) != len(cases):
        raise Rejected("empty or duplicate case declaration")
    seen = set()
    current = None
    next_step = 1
    last_order = -1
    event_count = 0
    state_count = 0
    total_events = 0
    total_states = 0
    total_endpoints = 0
    endpoints = 0
    endpoint_steps = set()
    active_step = 0
    last_state = None
    step_callback_count = 0
    action_steps = []
    for row in records(path):
        kind = row.get("kind")
        case_id = row.get("id")
        if kind == "inputs":
            if current is not None or case_id not in expected or case_id in seen:
                raise Rejected("unexpected, duplicate, or interleaved case")
            case = expected[case_id]
            for field in ("family", "profile", "hz", "steps"):
                if not exact(row.get(field), case[field]):
                    raise Rejected(f"{case_id}: {field} differs")
            if "input" in case and not exact(row.get("input"), case["input"]):
                raise Rejected(f"{case_id}: input differs")
            if not exact(row.get("dt"), 1.0 / case["hz"]):
                raise Rejected(f"{case_id}: dt differs")
            current = case_id
            next_step = 1
            last_order = -1
            event_count = 0
            state_count = 0
            endpoints = 0
            endpoint_steps = set()
            active_step = 0
            last_state = None
            step_callback_count = 0
            action_steps = []
        elif kind in ("event", "action", "state"):
            if current != case_id:
                raise Rejected("record is outside its case")
            step = row.get("step")
            order = row.get("order")
            if step != active_step:
                active_step = step
                last_order = -1
                step_callback_count = 0
            if type(step) is not int or type(order) is not int or step != next_step or order <= last_order:
                raise Rejected(f"{case_id}: missing step or changed event order")
            last_order = order
            if kind == "state":
                if state_count != step - 1 or "state" not in row:
                    raise Rejected(f"{case_id}: missing or duplicate state")
                if step_callback_count < expected[case_id].get("min_step_events", 0):
                    raise Rejected(f"{case_id}: step {step} has too few callbacks")
                state_count += 1
                total_states += 1
                last_state = row["state"]
                next_step += 1
            else:
                event_count += 1
                total_events += 1
                if kind == "event":
                    step_callback_count += 1
                if kind == "action":
                    action_steps.append(step)
        elif kind == "endpoint":
            group = expected[current].get("outer_group") if current else None
            if (current != case_id or not group or row.get("step") != next_step - 1 or
                row["step"] % group or type(row.get("order")) is not int or
                row["order"] <= last_order or row["step"] in endpoint_steps or
                not exact(row.get("state"), last_state)):
                raise Rejected(f"{case_id}: invalid endpoint copy")
            last_order = row["order"]
            endpoint_steps.add(row["step"])
            endpoints += 1
            total_endpoints += 1
        elif kind == "case-end":
            if current != case_id or state_count != expected[case_id]["steps"]:
                raise Rejected(f"{case_id}: incomplete case")
            if not exact(row.get("steps"), state_count) or not exact(row.get("events"), event_count):
                raise Rejected(f"{case_id}: case-end counts differ")
            if endpoints != expected[case_id]["steps"] // expected[case_id].get("outer_group", expected[case_id]["steps"] + 1):
                raise Rejected(f"{case_id}: endpoint count differs")
            if "outer_group" in expected[case_id] and endpoint_steps != set(range(
                    expected[case_id]["outer_group"], expected[case_id]["steps"] + 1,
                    expected[case_id]["outer_group"])):
                raise Rejected(f"{case_id}: endpoint schedule differs")
            if "outer_group" in expected[case_id] and row.get("endpoints") != endpoints:
                raise Rejected(f"{case_id}: case-end endpoint count differs")
            if action_steps != expected[case_id].get("expected_actions", []):
                raise Rejected(f"{case_id}: action steps differ")
            seen.add(case_id)
            current = None
        else:
            raise Rejected(f"unknown record kind: {kind}")
    if current is not None or seen != set(expected) or total_states == 0:
        raise Rejected(f"missing cases: {sorted(set(expected) - seen)}")
    return {"expected_cases": len(expected), "executed_cases": len(seen), "states": total_states,
            "events": total_events, "endpoints": total_endpoints, "skipped": 0}


def compare_exact(reference, candidate, cases):
    inspect(reference, cases)
    inspect(candidate, cases)
    left = list(records(reference))
    right = list(records(candidate))
    if len(left) != len(right):
        raise Rejected("record count differs")
    for number, (a, b) in enumerate(zip(left, right), 1):
        if not exact(a, b):
            raise Rejected(f"record {number} differs")
    return {"status": "PASSED", "records": len(left)}


def seal(trace, cases, identity, artifacts):
    counts = inspect(trace, cases)
    if set(artifacts) != set(identity.artifact_sha256):
        raise Rejected("artifact set differs")
    for name, path in artifacts.items():
        if digest(path) != identity.artifact_sha256[name]:
            raise Rejected(f"stale artifact: {name}")
    catalog = json.loads(CATALOG.read_text())
    reference_hashes = {item["key"]: item["reference"]["gzip_sha256"] for item in catalog["fixtures"]}
    build_data = b"".join(name.encode() + b"\0" + (Path(__file__).parent / name).read_bytes()
                          for name in BUILD_FILES)
    expected_counts = {"cases": len(cases), "states": sum(item["steps"] for item in cases),
                       "endpoints": sum(item["steps"] // item["outer_group"] for item in cases if "outer_group" in item),
                       "actions": sum(len(item.get("expected_actions", [])) for item in cases)}
    return {"schema": "portable-numerical-receipt/1", **asdict(identity),
            "fixture_key": "portable-matrix/1", "source_hash_method": "SHA-256 of git archive --format=tar HEAD",
            "baseline_source_revision": "058bf6d982a0fb89b54050f929f6ea9dae53b714",
            "baseline_jar_sha256": "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e",
            "reference_source_revision": catalog["baseline_source_revision"],
            "reference_artifact_sha256": catalog["baseline_jar_sha256"],
            "reference_trace_sha256": reference_hashes,
            "frozen_catalog_sha256": digest(CATALOG),
            "build_config_sha256": hashlib.sha256(build_data).hexdigest(),
            "trace_sha256": digest(trace), "cases_sha256": hashlib.sha256(
                json.dumps(cases, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
            "counts": counts, "expected_counts": expected_counts,
            "executed_counts": counts, "skipped": 0,
            "artifact_paths": {name: str(path) for name, path in artifacts.items()}}


def verify(sealed, trace, cases, identity, artifacts):
    fresh = seal(trace, cases, identity, artifacts)
    if not exact(sealed, fresh):
        raise Rejected("receipt identity or counts differ")
    return {"status": "PASSED", "counts": fresh["counts"]}
