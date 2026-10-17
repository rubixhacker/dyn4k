import hashlib
import json
import math
import struct
from dataclasses import asdict, dataclass
from itertools import zip_longest
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
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


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


def require(condition, message):
    if not condition:
        raise Rejected(message)


def validate_setup(header, case):
    settings = header.get("settings")
    setup = header.get("setup")
    require(isinstance(settings, dict) and isinstance(setup, dict), "input settings or setup is absent")
    required_settings = {"gravity", "stepFrequency", "maximumTranslation", "maximumRotation",
                         "atRestDetectionEnabled", "maximumAtRestLinearVelocity",
                         "maximumAtRestAngularVelocity", "minimumAtRestTime", "velocityIterations",
                         "positionIterations", "warmStartingEnabled", "maximumWarmStartDistance",
                         "linearTolerance", "angularTolerance", "maximumLinearCorrection",
                         "maximumAngularCorrection", "baumgarte", "continuousDetectionMode",
                         "narrowphase", "timeOfImpact"}
    require(required_settings <= settings.keys(), "input settings omit a required field")
    require(isinstance(settings["timeOfImpact"], dict), "input TOI settings are malformed")
    require(exact(settings["timeOfImpact"].get("distanceEpsilon"), 4.806217383937352e-6),
            "default TOI distance epsilon differs from pinned cbrt value")
    bodies = setup.get("bodies")
    joints = setup.get("joints")
    require(isinstance(bodies, list) and bodies and isinstance(joints, list),
            "input body or joint setup is absent")
    for index, body in enumerate(bodies):
        require(isinstance(body, dict), "input body setup is malformed")
        require(body.get("id") == f"b{index}", "input body identity differs")
        require({"transform", "massType", "mass", "inertia", "massCenter", "linearDamping",
                 "angularDamping", "initialVelocity", "initialAngularVelocity",
                 "atRestDetectionEnabled", "bullet", "fixtures"} <= body.keys(),
                "input body setup omits a required field")
        require(isinstance(body["fixtures"], list) and body["fixtures"],
                "input fixture setup is empty")
        require(len(body["fixtures"]) == 1, "input fixture count differs")
        for fixture_index, fixture in enumerate(body["fixtures"]):
            require(isinstance(fixture, dict), "input fixture setup is malformed")
            require(fixture.get("id") == f"b{index}f{fixture_index}", "input fixture identity differs")
            require({"density", "friction", "restitution", "restitutionVelocity", "sensor",
                     "filter", "shape"} <= fixture.keys(), "input fixture setup omits a required field")
            require(fixture["filter"] == "DEFAULT_FILTER", "unsupported fixture filter")
            require(isinstance(fixture["shape"], dict) and "type" in fixture["shape"],
                    "input shape setup is absent")
            require(exact(fixture["density"], 1.0) and fixture["sensor"] is False,
                    "input fixture density or sensor differs")
    for index, joint in enumerate(joints):
        require(isinstance(joint, dict), "input joint setup is malformed")
        require(joint.get("id") == f"j{index}" and isinstance(joint.get("mode"), dict) and
                isinstance(joint.get("bodies"), list), "input joint identity or mode is absent")
    family = case["family"]
    input_values = case["input"]
    if family == "geometry-collision":
        scale = input_values["scale"]
        ox, oy = input_values["origin"]
        delta = input_values["delta"]
        require(len(bodies) == 2 and not joints and
                exact(bodies[0]["fixtures"][0]["shape"].get("radius"), scale) and
                exact(bodies[1]["fixtures"][0]["shape"].get("radius"), 0.5 * scale) and
                exact(bodies[0]["transform"]["getTranslation"], [ox, oy]) and
                exact(bodies[1]["transform"]["getTranslation"], [ox + scale * (1.5 + delta), oy]),
                "geometry boundary input differs")
    if family == "free-motion":
        require(input_values["durationSeconds"] == 10, "motion duration differs")
        if case["id"] == "motion-forces-60":
            require(len(bodies) == 1 and not joints and
                    exact(settings["gravity"], [0.0, 0.0]) and
                    exact(bodies[0]["linearDamping"], input_values["damping"]) and
                    exact(bodies[0]["angularDamping"], input_values["damping"]) and
                    exact(bodies[0]["fixtures"][0]["shape"].get("radius"), 0.5) and
                    exact(input_values["force"], [1.0, 0.0]) and
                    exact(input_values["torque"], 0.25), "force and damping input differs")
        else:
            require(len(bodies) == 2 and not joints and
                    exact(settings["gravity"], input_values["gravity"]) and
                    [body["fixtures"][0]["shape"]["type"] for body in bodies] == ["Rectangle", "Circle"] and
                    all(exact(body["fixtures"][0]["restitution"], input_values["restitution"])
                        and exact(body["fixtures"][0]["restitutionVelocity"], 0.0) for body in bodies),
                    "restitution input differs")
    if family == "contacts-friction-sleep-wake":
        require(len(bodies) == 2 and not joints and
                [body["fixtures"][0]["shape"].get("type") for body in bodies] == ["Rectangle", "Rectangle"] and
                [body["massType"] for body in bodies] == ["INFINITE", "NORMAL"] and
                all(exact(body["fixtures"][0]["friction"], 0.5) for body in bodies) and
                exact(settings["gravity"], [0.0, -9.8]) and
                exact(bodies[0]["transform"]["getTranslation"], [0.0, -0.25]) and
                exact(bodies[1]["transform"]["getTranslation"], [0.0, 0.51]),
                "sleep/wake input differs")
        if case["profile"] == "configured":
            require(exact(settings["linearTolerance"], 1.0 / 4096.0) and
                    settings["positionIterations"] == 8 and case.get("outer_group") in (1, 2, 4),
                    "configured quality input differs")
    if family == "joints-limits-motors":
        require(len(joints) == 1 and joints[0]["mode"].get("type") == input_values["jointType"],
                "joint type or mode is absent")
        if case["id"].startswith("joint-"):
            active = input_values["mode"] == "active"
            mode = joints[0]["mode"]
            require(len(bodies) == 2 and joints[0]["bodies"] in ([0, 1], [1]) and
                    exact(settings["gravity"], [0.0, 0.0]), "joint body input differs")
            flag = {"Angle": "limitsEnabled", "Distance": "springEnabled",
                    "Prismatic": "motorEnabled", "Pulley": "slackEnabled",
                    "Revolute": "motorEnabled", "Weld": "springEnabled",
                    "Wheel": "motorEnabled", "Pin": "springEnabled"}.get(input_values["jointType"])
            if flag:
                require(mode.get(flag) is active, "joint active mode differs")
            if input_values["jointType"] == "Friction":
                require(exact(mode.get("maximumForce"), 20.0 if active else 10.0) and
                        exact(mode.get("maximumTorque"), 0.5 if active else 0.25),
                        "friction joint mode differs")
            if input_values["jointType"] == "Motor":
                require(exact(mode.get("maximumForce"), 10.0 if active else 1000.0),
                        "motor joint mode differs")
        elif case["id"] == "P-JINT-Weld-enabled-equal":
            mode = joints[0]["mode"]
            require(mode.get("limitsEnabled") is True and
                    exact([mode.get("lowerLimit"), mode.get("upperLimit")], input_values["limits"]) and
                    mode.get("springEnabled") is True and mode.get("springDamperEnabled") is True and
                    exact(mode.get("springDampingRatio"), 0.3), "frozen weld mode differs")
        else:
            require(len(bodies) == 3 and joints[0]["bodies"] == [1, 2] and
                    exact(bodies[2]["initialVelocity"], input_values["sourceVelocity"]),
                    "frozen pulley input differs")
    if family == "ccd":
        require(len(bodies) == 2 and not joints and bodies[1]["bullet"] is True and
                exact(bodies[1]["initialVelocity"], [0.0, input_values["speed"]]) and
                settings["continuousDetectionMode"] == input_values["mode"] and
                exact(settings["gravity"], [0.0, 0.0]) and
                exact(bodies[1]["transform"]["getTranslation"], [0.0, 1.0]) and
                bodies[1]["fixtures"][0]["shape"]["type"] == (
                    "Circle" if input_values["shape"] == "circle" else "Polygon"),
                "CCD input differs")
    if family == "long-running-invariant":
        require(len(bodies) == 1 and not joints and
                exact(bodies[0]["initialVelocity"], input_values["velocity"]) and
                exact(bodies[0]["initialAngularVelocity"], input_values["angularVelocity"]) and
                exact(settings["gravity"], [0.0, 0.0]) and
                settings["atRestDetectionEnabled"] is False, "long-run input differs")


def validate_state(state, body_ids, joint_ids):
    require(isinstance(state, dict) and isinstance(state.get("bodies"), list) and
            isinstance(state.get("joints"), list), "state body or joint channel is absent")
    require(all(isinstance(body, dict) for body in state["bodies"]) and
            all(isinstance(joint, dict) for joint in state["joints"]),
            "state body or joint channel is malformed")
    require([body.get("id") for body in state["bodies"]] == body_ids and
            [joint.get("id") for joint in state["joints"]] == joint_ids,
            "state body or joint identity differs")
    required_body = {"transform", "previousTransform", "worldCenter", "fixedOriginPosition",
                     "velocity", "angularVelocity", "force", "torque", "accumulatedForce",
                     "accumulatedTorque", "atRest", "bullet", "rotationIncrementSum",
                     "kineticEnergy", "linearMomentum", "angularMomentumCenter"}
    for body in state["bodies"]:
        require(required_body <= body.keys(), "state body channel is absent")
        for transform_name in ("transform", "previousTransform"):
            transform = body[transform_name]
            require(isinstance(transform, dict) and
                    {"getTranslation", "getTranslationX", "getTranslationY", "getCost",
                     "getSint", "getRotationAngle", "getValues"} <= transform.keys(),
                    "state transform channel is absent")
            require(exact(transform["getTranslation"],
                          [transform["getTranslationX"], transform["getTranslationY"]]),
                    "state transform aliases differ")
    for joint in state["joints"]:
        require({"reactionForce", "reactionTorque", "mode"} <= joint.keys(),
                "state joint channel is absent")


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
    body_ids = []
    joint_ids = []
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
            if case.get("require_setup"):
                validate_setup(row, case)
                body_ids = [body["id"] for body in row["setup"]["bodies"]]
                joint_ids = [joint["id"] for joint in row["setup"]["joints"]]
                validate_state(row.get("initial"), body_ids, joint_ids)
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
            if (type(step) is not int or type(order) is not int or step != next_step or
                    step > expected[current]["steps"] or order <= last_order):
                raise Rejected(f"{case_id}: missing step or changed event order")
            last_order = order
            if kind == "state":
                if state_count != step - 1 or "state" not in row:
                    raise Rejected(f"{case_id}: missing or duplicate state")
                if expected[case_id].get("require_setup"):
                    validate_state(row["state"], body_ids, joint_ids)
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
    number = 0
    sentinel = object()
    for number, (a, b) in enumerate(zip_longest(records(reference), records(candidate), fillvalue=sentinel), 1):
        if a is sentinel or b is sentinel:
            raise Rejected("record count differs")
        if not exact(a, b):
            raise Rejected(f"record {number} differs")
    return {"status": "PASSED", "records": number}


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
