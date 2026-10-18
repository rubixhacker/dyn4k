import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from copy import deepcopy
from itertools import zip_longest
from pathlib import Path

from cases import declared_cases
from orthogonality import orthogonality_ulps, source_rotation_cap, validate_rotation_audit
from reference_diagnostic import structural_differences, value_differences
from receipt import Rejected, digest, exact, records


class Difference(Rejected):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status


APPROVED_RULE_IDS = frozenset((
    "bounded_angular_velocity", "bounded_contact_depth", "bounded_direction",
    "bounded_force", "bounded_geometry_distance", "bounded_impulse",
    "bounded_position", "bounded_scalar", "bounded_toi_distance", "bounded_toi_time",
    "bounded_torque", "bounded_velocity", "derived_energy", "derived_momentum",
    "derived_rotation", "derived_transform", "exact_configuration", "exact_input",
    "exact_step", "exact_structure", "reject_nonfinite"))
APPROVED_RULES_SHA256 = "dd9099d762ef22c9b6782a96c61afb80d023b56ae09ce3a6d925c782f1573441"
APPROVED_PATH_MAP_SHA256 = "da62dab0720ad551f6cf3d802cd3d2419f889ab88f63f5fd56268fb0417c269e"
APPROVED_ROTATION_CAPS_SHA256 = "3777a4121028ce3f8005450ee36163cb3731efbe7c090632b7d067b8419d6127"
PROBE_METHOD = "geometryCollisionBoundaryAndScale"
PROBE_VALUES = {
    "schema": "portable-binary64-probe/1",
    "ulpOneBits": "3cb0000000000000",
    "nextUpOneBits": "3ff0000000000001",
    "nextDownOneBits": "3fefffffffffffff",
    "negativeZeroBits": "8000000000000000",
    "positiveZeroBits": "0000000000000000",
    "negativeZeroReciprocalBits": "fff0000000000000",
    "ulpMillionBits": "3de0000000000000",
    "boundaryOriginZeroGapBits": "3d71980000000000",
    "boundaryPositiveMillionGapBits": "0000000000000000",
    "boundaryNegativeMillionGapBits": "0000000000000000",
    "maximumFinite": True,
    "positiveInfinityFinite": False,
    "nanFinite": False,
}


def load_policy_catalog(path=None):
    source = Path(path) if path is not None else Path(__file__).with_name(
        "prospective_policy_catalog.json")
    return json.loads(source.read_text())


def verify_policy_catalog(catalog, manifest, cases, frozen_ids):
    if catalog.get("schema") != "portable-prospective-policy-adopted/1" or \
            catalog.get("decision") != "https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-6244397193" or \
            catalog.get("conditional_decision") != "https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-6244770438" or \
            catalog.get("orthogonality_policy") != "fixed-32-ulps/1" or \
            catalog.get("conditional_orthogonality_policy") != "source-derived-u-n/1" or \
            catalog.get("qualification") != "UNPASSED":
        raise Rejected("prospective policy catalog adoption or qualification differs")
    if catalog.get("baseline_trace_sha256") != manifest.get("trace_sha256"):
        raise Rejected("prospective policy baseline trace differs")
    if catalog.get("baseline_source_revision") != manifest.get("baseline_source_revision"):
        raise Rejected("prospective policy baseline source differs")
    if catalog.get("baseline_jar_sha256") != manifest.get("baseline_jar_sha256") or \
            catalog.get("baseline_fixture_source_sha256") != manifest.get("fixture_source_sha256"):
        raise Rejected("prospective policy baseline identity differs")
    expected = {case["id"]: case for case in cases if case["id"] not in frozen_ids}
    if len(expected) != 318 or set(catalog.get("cases", {})) != set(expected) or \
            set(manifest.get("case_sha256", {})) != {case["id"] for case in cases}:
        raise Rejected("prospective policy case identity differs")
    caps = catalog.get("rotation_caps")
    if not isinstance(caps, dict) or set(caps) != set(expected) or any(
            type(caps[case_id]) is not int or caps[case_id] != source_rotation_cap(case)
            for case_id, case in expected.items()):
        raise Rejected("prospective source rotation cap differs")
    cap_payload = json.dumps(caps, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()
    if hashlib.sha256(cap_payload).hexdigest() != APPROVED_ROTATION_CAPS_SHA256:
        raise Rejected("prospective rotation cap inventory differs")
    paths = catalog.get("paths")
    path_sets = catalog.get("path_sets")
    proposals = catalog.get("rule_proposals")
    if not isinstance(proposals, dict) or set(proposals) != APPROVED_RULE_IDS:
        raise Rejected("prospective policy rule set differs")
    payload = json.dumps(proposals, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode()
    if hashlib.sha256(payload).hexdigest() != APPROVED_RULES_SHA256:
        raise Rejected("prospective adopted rule values differ")
    if not isinstance(paths, list) or not paths or not isinstance(path_sets, list) or not path_sets:
        raise Rejected("prospective policy path set is missing")
    names = [entry.get("path") for entry in paths]
    if names != sorted(set(names)) or any(not isinstance(name, str) or not name for name in names):
        raise Rejected("prospective policy path set is invalid")
    if any(not isinstance(entry.get("rule"), str) or not entry["rule"] or
           not isinstance(entry.get("types"), list) or not entry["types"] or
           entry["types"] != sorted(set(entry["types"]))
           for entry in paths):
        raise Rejected("prospective policy path rule is missing")
    if not isinstance(proposals, dict) or any(
            entry["rule"] not in proposals or entry["rule"] == "bounded_scalar"
            for entry in paths):
        raise Rejected("prospective policy path rule is unclassified")
    used = set()
    for path_set in path_sets:
        if not isinstance(path_set, list) or not path_set or \
                path_set != sorted(set(path_set)) or \
                any(type(index) is not int or index < 0 or index >= len(paths)
                    for index in path_set):
            raise Rejected("prospective policy path set is invalid")
        used.update(path_set)
    if used != set(range(len(paths))):
        raise Rejected("prospective policy path set leaves uncovered paths")
    for case_id, entry in catalog["cases"].items():
        case = expected[case_id]
        if entry.get("sha256") != manifest["case_sha256"][case_id] or \
                entry.get("family") != case["family"] or \
                entry.get("profile") != case["profile"] or \
                entry.get("steps") != case["steps"] or \
                type(entry.get("path_set")) is not int or \
                entry["path_set"] < 0 or entry["path_set"] >= len(path_sets):
            raise Rejected(f"prospective policy case binding differs: {case_id}")
        if entry.get("observed_paths") != len(path_sets[entry["path_set"]]):
            raise Rejected(f"prospective policy path set differs: {case_id}")
    if {entry["path_set"] for entry in catalog["cases"].values()} != set(range(len(path_sets))):
        raise Rejected("prospective policy has unreferenced path sets")
    path_payload = json.dumps({"paths": paths, "path_sets": path_sets}, sort_keys=True,
                              separators=(",", ":"), allow_nan=False).encode()
    if hashlib.sha256(path_payload).hexdigest() != APPROVED_PATH_MAP_SHA256:
        raise Rejected("prospective adopted path rules differ")


def reference_path_inventory(path):
    found = {}

    def visit(value, prefix):
        if isinstance(value, dict):
            for key, item in value.items():
                visit(item, f"{prefix}.{key}" if prefix else key)
        elif isinstance(value, list):
            if not value:
                found.setdefault(f"{prefix}[]", set()).add("empty")
            for item in value:
                visit(item, f"{prefix}[]")
        else:
            found.setdefault(prefix, set()).add(type(value).__name__)

    for record in records(path, allow_tagged_nonfinite=True):
        kind = record["kind"]
        prefix = kind + (f".{record['name']}" if kind in ("event", "action") else "")
        visit(record, prefix)
    return {name: sorted(types) for name, types in found.items()}


def verify_reference_inventory(path, case_id, catalog):
    entry = catalog["cases"][case_id]
    if digest(path) != entry["sha256"]:
        raise Rejected(f"prospective reference hash differs: {case_id}")
    observed = reference_path_inventory(path)
    expected = {catalog["paths"][index]["path"]:
                catalog["paths"][index]["types"]
                for index in catalog["path_sets"][entry["path_set"]]}
    if set(observed) != set(expected) or any(
            not set(types) <= set(expected[name]) for name, types in observed.items()):
        raise Rejected(f"prospective reference path set differs: {case_id}")


def verify_baseline_manifest(manifest, expected_ids, jar_sha256, fixture_sha256):
    expected_ids = set(expected_ids)
    if not expected_ids or set(manifest["case_sha256"]) != expected_ids or \
            manifest["inventory"]["cases"] != len(expected_ids):
        raise Rejected("baseline case identity differs")
    if manifest["status"] != "CAPTURED_WITH_FAILED_ANGLE_PHYSICAL":
        raise Rejected("baseline archive is not verified")
    if manifest["baseline_jar_sha256"] != jar_sha256:
        raise Rejected("baseline JAR identity differs")
    if manifest["fixture_source_sha256"] != fixture_sha256:
        raise Rejected("baseline fixture source differs")


def verify_reference_case(path, expected_sha256):
    if digest(path) != expected_sha256:
        raise Rejected(f"baseline reference case hash differs: {Path(path).stem}")


def verify_baseline_bytes(baseline, manifest):
    baseline = Path(baseline)
    if digest(baseline / "dyn4j-6.0.0.jar") != manifest["baseline_jar_sha256"]:
        raise Rejected("baseline JAR hash differs")
    if digest(baseline / "baseline-jvm/trace.jsonl") != manifest["trace_sha256"]:
        raise Rejected("baseline trace hash differs")


def _compare_value(left, right, path, result):
    if (isinstance(left, dict) and "nonfinite" in left) or \
            (isinstance(right, dict) and "nonfinite" in right):
        raise Difference("FAILED_NONFINITE", f"nonfinite value at {path}")
    if isinstance(left, dict) and isinstance(right, dict):
        if left.keys() != right.keys():
            raise Difference("FAILED_STRUCTURE", f"field set differs at {path}")
        for key in left:
            _compare_value(left[key], right[key], f"{path}.{key}", result)
    elif isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            raise Difference("FAILED_STRUCTURE", f"list length differs at {path}")
        for index, (a, b) in enumerate(zip(left, right)):
            _compare_value(a, b, f"{path}[{index}]", result)
    elif type(left) in (int, float) and type(right) in (int, float):
        if not math.isfinite(left) or not math.isfinite(right):
            raise Difference("FAILED_NONFINITE", f"nonfinite value at {path}")
        if exact(left, right):
            result["exact_numeric_values"] += 1
        elif left == right == 0:
            raise Difference("FAILED_SIGNED_ZERO", f"signed zero differs at {path}")
        elif type(left) is int and type(right) is int:
            raise Difference("FAILED_STRUCTURE", f"integer value differs at {path}")
        else:
            result["different_numeric_values"] += 1
            if len(result["first_numeric_differences"]) < 20:
                result["first_numeric_differences"].append(
                    {"path": path, "baseline": left, "candidate": right})
    elif type(left) is not type(right) or left != right:
        raise Difference("FAILED_STRUCTURE", f"value differs at {path}")


def compare_case(reference, candidate, case):
    result = {"case_id": case["id"], "status": "FAILED_COVERAGE", "records": 0,
              "states": 0, "exact_numeric_values": 0,
              "different_numeric_values": 0, "first_numeric_differences": [],
              "input_differences": [],
              "qualification": "UNPASSED"}
    sentinel = object()
    first = None
    last = None
    current_step = None
    try:
        for left, right in zip_longest(records(reference, allow_tagged_nonfinite=True),
                                       records(candidate, allow_tagged_nonfinite=True),
                                       fillvalue=sentinel):
            if left is sentinel or right is sentinel:
                raise Difference("FAILED_COVERAGE", "case record count differs")
            result["records"] += 1
            current_step = left.get("step")
            if first is None:
                first = (left.get("kind"), right.get("kind"))
            last = (left.get("kind"), right.get("kind"))
            if left.get("kind") != right.get("kind") or \
                    left.get("id") != case["id"] or right.get("id") != case["id"]:
                raise Difference("FAILED_STRUCTURE", f"record identity differs at {result['records']}")
            if left["kind"] == "inputs":
                if result["records"] != 1 or not exact(left, right):
                    result["input_differences"] = (
                        structural_differences(left, right, "inputs", 20) +
                        value_differences(left, right, "inputs", 20))[:20]
                    raise Difference("FAILED_INPUT", "case input identity differs")
            elif left["kind"] == "case-end":
                if not exact(left, right):
                    raise Difference("FAILED_COVERAGE", "case completion differs")
            else:
                _compare_value(left, right, left["kind"], result)
            if left["kind"] == "state":
                result["states"] += 1
        if (first != ("inputs", "inputs") or last != ("case-end", "case-end") or
                result["states"] != case["steps"] or result["records"] == 0):
            raise Difference("FAILED_COVERAGE", "case is missing inputs, states, or completion")
        result["status"] = ("UNPASSED_NUMERICAL_POLICY" if result["different_numeric_values"]
                            else "EXACT_DIAGNOSTIC")
    except Difference as error:
        result["status"] = error.status
        result["reason"] = str(error)
        if current_step is not None:
            result["failed_step"] = current_step
    except (Rejected, OSError, EOFError, KeyError, TypeError, ValueError) as error:
        result["status"] = "FAILED_COVERAGE"
        result["reason"] = str(error)
    return result


def _finite_number(value, path):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise Difference("FAILED_NONFINITE", f"nonfinite or nonnumeric value at {path}")
    return float(value)


def _numeric_identity(left, right):
    return (type(left) in (int, float) and type(right) in (int, float) and
            math.isfinite(left) and math.isfinite(right) and float(left) == float(right))


def _has_tagged_nonfinite(value):
    if isinstance(value, dict):
        return "nonfinite" in value or any(_has_tagged_nonfinite(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_tagged_nonfinite(v) for v in value)
    return False


def _represented_gap(header):
    bodies = header["setup"]["bodies"]
    scale = _finite_number(header["input"]["scale"], "input.scale")
    delta = _finite_number(header["input"]["delta"], "input.delta")
    origin = header["input"]["origin"]
    if len(bodies) != 2 or len(origin) != 2 or scale <= 0:
        raise Difference("UNPASSED_PREMISE", "boundary scene geometry is invalid")
    ox = _finite_number(origin[0], "input.origin.x")
    oy = _finite_number(origin[1], "input.origin.y")
    x0 = _finite_number(bodies[0]["transform"]["getTranslationX"], "setup.b0.x")
    x1 = _finite_number(bodies[1]["transform"]["getTranslationX"], "setup.b1.x")
    y0 = _finite_number(bodies[0]["transform"]["getTranslationY"], "setup.b0.y")
    y1 = _finite_number(bodies[1]["transform"]["getTranslationY"], "setup.b1.y")
    if not all((_numeric_identity(x0, ox), _numeric_identity(y0, oy),
                _numeric_identity(y1, oy),
                _numeric_identity(x1, ox + scale * (1.5 + delta)))):
        raise Difference("UNPASSED_PREMISE", "represented boundary setup differs from input")
    gap = (x1 - x0) - 1.5 * scale
    coordinate = max(abs(x0), abs(x1), abs(scale))
    ulp = math.ulp(coordinate)
    limit = 8 * ulp
    if gap != 0.0:
        limit = min(limit, abs(gap) / 4)
    if not math.isfinite(limit) or limit <= 0:
        raise Difference("UNPASSED_PREMISE", "represented boundary scale is invalid")
    return gap, limit


def _mass_properties(header, body_index):
    bodies = header["setup"]["bodies"]
    selected = bodies if body_index is None else [bodies[body_index]]
    masses = []
    inertias = []
    for body in selected:
        mass = _finite_number(body["mass"], "setup.mass")
        inertia = _finite_number(body["inertia"], "setup.inertia")
        if mass < 0 or inertia < 0:
            raise Difference("UNPASSED_PREMISE", "negative mass or inertia")
        if body.get("massType") != "INFINITE":
            masses.append(mass)
            inertias.append(inertia)
    return sum(masses), sum(inertias)


def _sweep_distance(case, header, previous_state):
    dt = _finite_number(header["dt"], "inputs.dt")
    speed = case.get("input", {}).get("speed")
    if type(speed) in (int, float):
        sweep = abs(_finite_number(speed, "input.speed")) * dt
    else:
        bodies = previous_state["bodies"]
        velocities = [body["velocity"] for body in bodies]
        if len(velocities) < 2:
            raise Difference("UNPASSED_PREMISE", "TOI needs two body velocities")
        dv = math.hypot(*(_finite_number(velocities[1][i], "velocity") -
                           _finite_number(velocities[0][i], "velocity") for i in (0, 1)))
        gravity = previous_state.get("gravity", [0.0, 0.0])
        sweep = dv * dt + math.hypot(*gravity) * dt * dt
    if not math.isfinite(sweep) or sweep <= 0:
        raise Difference("UNPASSED_PREMISE", "represented TOI sweep is unavailable")
    return sweep


def _transform_invariant(transform, limit_ulps):
    if not isinstance(transform, dict):
        raise Difference("FAILED_DERIVED", "transform is missing")
    required = ("getCost", "getSint", "getRotationAngle", "getTranslation",
                "getTranslationX", "getTranslationY", "getValues")
    if any(key not in transform for key in required):
        raise Difference("FAILED_DERIVED", "transform alias is missing")
    c = _finite_number(transform["getCost"], "transform.cos")
    s = _finite_number(transform["getSint"], "transform.sin")
    x = _finite_number(transform["getTranslationX"], "transform.x")
    y = _finite_number(transform["getTranslationY"], "transform.y")
    translation = transform["getTranslation"]
    values = transform["getValues"]
    if len(translation) != 2 or len(values) != 6 or any(
            not _numeric_identity(a, b) for a, b in zip(
                [x, y, c, -s, x, s, c, y], [*translation, *values])):
        raise Difference("FAILED_DERIVED", "transform aliases differ")
    if abs(c * c + s * s - 1.0) > limit_ulps * math.ulp(1.0):
        raise Difference("FAILED_DERIVED", "transform rotation is not orthogonal")
    angle = _finite_number(transform["getRotationAngle"], "transform.angle")
    expected = math.copysign(math.acos(max(-1.0, min(1.0, c))), s)
    if abs(angle - expected) > 32 * math.ulp(math.pi):
        raise Difference("FAILED_DERIVED", "transform angle differs from cosine and sine")


def _same_run_state(row, header, previous_state, rotation_cap, conditional_diagnostic):
    state = row["state"]
    current_limit = (orthogonality_ulps(row["step"] * rotation_cap)
                     if conditional_diagnostic else 32)
    previous_limit = (orthogonality_ulps((row["step"] - 1) * rotation_cap)
                      if conditional_diagnostic else 32)
    for index, body in enumerate(state["bodies"]):
        prior_body = (header["initial"]["bodies"][index] if previous_state is None
                      else previous_state["bodies"][index])
        _transform_invariant(body["transform"], current_limit)
        _transform_invariant(body["previousTransform"], previous_limit)
        expected_previous = prior_body["transform"]
        if any(not _numeric_identity(a, b) for a, b in zip(
                body["previousTransform"]["getValues"], expected_previous["getValues"])):
            raise Difference("FAILED_DERIVED", "previous transform is not the prior pose")
        mass, inertia = _mass_properties(header, index)
        velocity = body["velocity"]
        omega = _finite_number(body["angularVelocity"], "body.angularVelocity")
        if any(not math.isfinite(_finite_number(v, "body.velocity")) for v in velocity):
            raise Difference("FAILED_DERIVED", "velocity is nonfinite")
        checks = [(body["linearMomentum"][i], mass * velocity[i]) for i in (0, 1)]
        checks += [(body["angularMomentumCenter"], inertia * omega),
                   (body["kineticEnergy"],
                    0.5 * mass * sum(v * v for v in velocity) + 0.5 * inertia * omega * omega)]
        for observed, expected in checks:
            value = _finite_number(observed, "derived body value")
            if abs(value - expected) > 32 * math.ulp(max(abs(value), abs(expected), 1.0)):
                raise Difference("FAILED_DERIVED", "momentum or energy disagrees with state")
        if "rotationIncrementSum" in body:
            prior_angle = _finite_number(prior_body["transform"]["getRotationAngle"],
                                         "prior rotation")
            angle = _finite_number(body["transform"]["getRotationAngle"], "rotation")
            prior_sum = _finite_number(prior_body["rotationIncrementSum"],
                                       "prior rotation sum")
            increment = math.atan2(math.sin(angle - prior_angle),
                                   math.cos(angle - prior_angle))
            expected_sum = prior_sum + increment
            observed_sum = _finite_number(body["rotationIncrementSum"],
                                          "rotation increment sum")
            if abs(observed_sum - expected_sum) > 32 * math.ulp(
                    max(abs(observed_sum), abs(expected_sum), 1.0)):
                raise Difference("FAILED_DERIVED", "rotation sum differs from pose increments")


def _same_configuration_value(left, right):
    if type(left) in (int, float) or type(right) in (int, float):
        return _numeric_identity(left, right)
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _same_configuration_value(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _same_configuration_value(a, b) for a, b in zip(left, right))
    return type(left) is type(right) and left == right


def _advance_modes(action, case, modes):
    if not modes:
        return
    name = action["name"]
    if name.startswith("mode-transition-"):
        step = action["step"]
        if step not in (201, 401) or case["input"].get("mode") != "active":
            raise Difference("FAILED_DERIVED", "unexpected joint mode transition")
        reverse = step == 201
        joint_type = case["input"]["jointType"]
        mode = modes[0]
        if joint_type == "Angle" or joint_type == "Weld":
            mode["limitsEnabled"] = not reverse
        elif joint_type == "Distance":
            mode["lowerLimitEnabled"] = not reverse
            mode["upperLimitEnabled"] = not reverse
        elif joint_type == "Friction":
            mode["maximumForce"] = 0.0 if reverse else 10.0
        elif joint_type in ("Prismatic", "Revolute", "Wheel"):
            speed = 1.0 if joint_type == "Prismatic" else math.pi / 2
            mode["motorSpeed"] = -speed if reverse else speed
        elif joint_type == "Pulley":
            mode["slackEnabled"] = not reverse
        elif joint_type == "Motor":
            mode["linearTarget"] = [-0.5 if reverse else 0.5, 0.5]
        elif joint_type == "Pin":
            mode["target"] = [-0.5 if reverse else 0.5, 2.0]
        else:
            raise Difference("FAILED_DERIVED", "unrecognized active joint type")
        return
    matched = re.fullmatch(r"set([A-Z][A-Za-z]+)\((true|false)\)", name)
    if matched is None:
        raise Difference("FAILED_DERIVED", "unrecognized joint action")
    key = matched[1][0].lower() + matched[1][1:]
    if (key == "limitsEnabled" and key not in modes[0] and
            "lowerLimitEnabled" in modes[0] and "upperLimitEnabled" in modes[0]):
        modes[0]["lowerLimitEnabled"] = matched[2] == "true"
        modes[0]["upperLimitEnabled"] = matched[2] == "true"
        return
    if key not in modes[0] or type(modes[0][key]) is not bool:
        raise Difference("FAILED_DERIVED", "joint action has no configuration target")
    modes[0][key] = matched[2] == "true"


def _same_run_configuration(row, header, modes):
    state = row["state"]
    settings = header.get("settings", {})
    if "gravity" in state and not _same_configuration_value(
            state["gravity"], settings.get("gravity")):
        raise Difference("FAILED_DERIVED", "gravity differs from configured value")
    joints = state.get("joints", [])
    if len(joints) != len(modes):
        raise Difference("FAILED_DERIVED", "joint count differs from setup")
    for index, joint in enumerate(joints):
        mode = joint["mode"]
        expected = modes[index]
        if (not isinstance(mode, dict) or mode.keys() != expected.keys() or
                any(not _same_configuration_value(value, expected[key])
                    for key, value in mode.items() if key not in ("anchor1", "anchor2"))):
            raise Difference("FAILED_DERIVED", "joint mode differs from setup or action")


def _policy_limit(rule, path, location, case, header, previous_state,
                  current_state, body_index, rules):
    dt = _finite_number(header["dt"], "inputs.dt")
    if dt <= 0 or not _numeric_identity(dt, 1.0 / case["hz"]):
        raise Difference("UNPASSED_PREMISE", "target step duration differs")
    position = (rules["bounded_position"]["free_motion_limit_m"]
                if case["family"] == "free-motion" else rules["bounded_position"]["limit_m"])
    angle = (rules["derived_rotation"]["free_motion_limit_rad"]
             if case["family"] == "free-motion" else rules["derived_rotation"]["limit_rad"])
    if case["family"] == "geometry-collision":
        _, position = _represented_gap(header)
    mass, inertia = _mass_properties(header, body_index)
    if rule == "bounded_position":
        return position
    if rule == "bounded_velocity":
        return position / dt
    if rule == "bounded_angular_velocity":
        return angle / dt
    if rule == "derived_rotation":
        return angle
    if rule == "derived_transform":
        return (position if ((path.endswith(".getValues[]") and location in (2, 5)) or
                             path.endswith((".getTranslation[]", ".getTranslationX",
                                            ".getTranslationY"))) else angle)
    if rule == "bounded_contact_depth":
        return position if case["family"] == "geometry-collision" else rules[rule]["limit_m"]
    if rule == "bounded_geometry_distance":
        return position if case["family"] == "geometry-collision" else rules[rule]["limit_m"]
    if rule == "bounded_direction":
        return rules[rule]["limit"]
    if rule == "bounded_toi_distance":
        return rules[rule]["limit_m"]
    if rule == "bounded_toi_time":
        return min(0.001, rules["bounded_toi_distance"]["limit_m"] /
                   _sweep_distance(case, header, previous_state or header["initial"]))
    if rule == "bounded_impulse":
        return mass * position / dt
    if rule == "bounded_force":
        return mass * position / (dt * dt)
    if rule == "bounded_torque":
        return inertia * angle / (dt * dt)
    if rule in ("derived_momentum", "derived_energy"):
        if body_index is None or current_state is None:
            raise Difference("UNPASSED_PREMISE", "derived body context is absent")
        body = current_state["bodies"][body_index]
        velocity = math.hypot(*body["velocity"])
        omega = abs(body["angularVelocity"])
        ev = position / dt
        ew = angle / dt
        if rule == "derived_energy":
            propagation = (mass * (velocity * math.sqrt(2.0) * ev + ev * ev) +
                           inertia * (omega * ew + ew * ew / 2))
            energy = 0.5 * mass * velocity * velocity + 0.5 * inertia * omega * omega
            return propagation + 32 * math.ulp(max(abs(energy), abs(energy + propagation), 1.0))
        if path.endswith(".angularMomentumCenter"):
            propagation = inertia * ew
            scale = max(abs(inertia * omega), abs(propagation), 1.0)
        else:
            propagation = mass * ev
            component = body["velocity"][location] if location is not None else velocity
            scale = max(abs(mass * component), abs(propagation), 1.0)
        return propagation + 32 * math.ulp(scale)
    raise Difference("FAILED_POLICY", f"unhandled rule: {rule}")


def compare_policy_case(reference, candidate, case, catalog, rotation_audit=None,
                        conditional_diagnostic=False):
    result = {"case_id": case["id"], "status": "FAILED_COVERAGE", "qualification": "UNPASSED",
              "records": 0, "states": 0, "rule_checks": {}, "bounded_checks": 0,
              "exact_numeric_values": 0, "different_numeric_values": 0,
              "target_arithmetic": "UNPASSED_UNBOUND_AUDIT",
              "target_premises": {name: "UNPASSED" for name in
                                  ("producer", "trig", "rounding", "subnormal",
                                   "zero_product", "fma")},
              "rotation_audit": "UNPASSED_NOT_EXECUTED"}
    result["orthogonality_assessment"] = ("CONDITIONAL_U_N_DIAGNOSTIC" if
                                           conditional_diagnostic else "ACTIVE_FIXED_32_ULPS")
    expected_paths = {catalog["paths"][index]["path"]: catalog["paths"][index]
                      for index in catalog["path_sets"][catalog["cases"][case["id"]]["path_set"]]}
    observed_paths = set()
    header = None
    previous_reference = None
    previous_candidate = None
    current_reference = None
    current_step = 0
    last_order = -1
    events = 0
    actions_seen = []
    candidate_states = {}
    first_kind = None
    last_kind = None
    reference_modes = None
    candidate_modes = None
    rotation_cap = None

    def walk(left, right, path, body_index=None, location=None):
        if isinstance(left, dict) and "nonfinite" in left:
            status = ("FAILED_PHYSICAL" if case["id"] == "P-J-Angle-ratio-limits-off--1.0"
                      else "FAILED_NONFINITE")
            raise Difference(status, f"reference nonfinite value at {path}")
        if isinstance(right, dict) and "nonfinite" in right:
            raise Difference("FAILED_NONFINITE", f"candidate nonfinite value at {path}")
        if isinstance(left, dict) and isinstance(right, dict):
            if left.keys() != right.keys():
                raise Difference("FAILED_STRUCTURE", f"field set differs at {path}")
            for key in left:
                walk(left[key], right[key], f"{path}.{key}" if path else key, body_index)
            return
        if isinstance(left, list) and isinstance(right, list):
            if len(left) != len(right):
                raise Difference("FAILED_STRUCTURE", f"list length differs at {path}")
            vector_rule = expected_paths.get(path + "[]", {}).get("rule")
            if vector_rule == "bounded_direction" and left:
                values = [(_finite_number(a, path), _finite_number(b, path))
                          for a, b in zip(left, right)]
                if len(values) != 2 or math.hypot(*(a - b for a, b in values)) > catalog[
                        "rule_proposals"]["bounded_direction"]["limit"] or \
                        sum(a * b for a, b in values) < 0:
                    raise Difference("FAILED_NUMERICAL_POLICY", f"direction differs at {path}")
                for vector in (left, right):
                    magnitude = math.hypot(*vector)
                    if magnitude and abs(magnitude - 1.0) > 32 * math.ulp(1.0):
                        raise Difference("FAILED_DERIVED", f"direction is not unit length at {path}")
            if not left:
                observed_paths.add(path + "[]")
            for index, (a, b) in enumerate(zip(left, right)):
                index_body = index if path == "state.state.bodies" else body_index
                walk(a, b, path + "[]", index_body, index)
            return
        if type(left) in (int, float) and type(right) in (int, float):
            _finite_number(left, path)
            _finite_number(right, path)
        elif type(left) is not type(right):
            raise Difference("FAILED_STRUCTURE", f"value type differs at {path}")
        entry = expected_paths.get(path)
        if entry is None:
            raise Difference("FAILED_POLICY", f"unmapped path: {path}")
        observed_paths.add(path)
        rule = entry["rule"]
        result["rule_checks"][rule] = result["rule_checks"].get(rule, 0) + 1
        if rule == "reject_nonfinite":
            raise Difference("FAILED_POLICY", f"nonfinite path cannot qualify: {path}")
        if rule == "exact_input":
            valid = exact(left, right)
        elif rule == "exact_structure":
            valid = type(left) is type(right) and left == right
        elif rule in ("exact_configuration", "exact_step"):
            valid = (_numeric_identity(left, right) if type(left) in (int, float)
                     else type(left) is type(right) and left == right)
            if rule == "exact_step":
                valid = valid and _numeric_identity(left, 1.0 / case["hz"])
        else:
            if type(left) not in (int, float) or type(right) not in (int, float):
                raise Difference("FAILED_POLICY", f"bounded path is not numeric: {path}")
            limit = _policy_limit(rule, path, location, case, header, previous_reference,
                                  current_reference, body_index, catalog["rule_proposals"])
            if rule == "derived_transform" and path.endswith(".getRotationAngle"):
                delta = math.remainder(right - left, 2 * math.pi)
            else:
                delta = right - left
            valid = abs(delta) <= limit
            if rule in ("bounded_force", "bounded_torque") and left == 0 and (
                    path.startswith("state.state.bodies[]") or
                    case.get("input", {}).get("jointType") == "Angle" and
                    path.endswith(".reactionForce[]")):
                valid = right == 0
            if rule == "bounded_toi_time":
                valid = valid and 0 <= left <= 1 and 0 <= right <= 1
            result["bounded_checks"] += 1
        if not valid:
            raise Difference("FAILED_NUMERICAL_POLICY" if rule.startswith(("bounded", "derived"))
                             else "FAILED_STRUCTURE", f"{rule} differs at {path}")
        if type(left) in (int, float):
            if _numeric_identity(left, right):
                result["exact_numeric_values"] += 1
            else:
                result["different_numeric_values"] += 1

    try:
        rotation_cap = catalog["rotation_caps"][case["id"]]
        if type(rotation_cap) is not int or rotation_cap not in (1, 5, 7, 9, 11) or \
                case["steps"] * rotation_cap > 6600:
            raise Difference("FAILED_POLICY", "case rotation cap is invalid")
        if not expected_paths or any(entry["rule"] not in catalog["rule_proposals"] or
                                     entry["rule"] == "bounded_scalar" for entry in expected_paths.values()):
            raise Difference("FAILED_POLICY", "case has missing or unknown rules")
        sentinel = object()
        for left, right in zip_longest(records(reference, allow_tagged_nonfinite=True),
                                       records(candidate, allow_tagged_nonfinite=True),
                                       fillvalue=sentinel):
            if left is sentinel or right is sentinel:
                raise Difference("FAILED_COVERAGE", "case record count differs")
            result["records"] += 1
            kind = left.get("kind")
            if first_kind is None:
                first_kind = kind
            last_kind = kind
            if kind != right.get("kind") or left.get("id") != case["id"] or right.get("id") != case["id"]:
                raise Difference("FAILED_STRUCTURE", "record identity differs")
            if kind == "inputs":
                if result["records"] != 1 or not exact(left, right):
                    raise Difference("FAILED_INPUT", "case input identity differs")
                header = left
                reference_modes = [deepcopy(joint["mode"]) for joint in header["setup"]["joints"]]
                candidate_modes = deepcopy(reference_modes)
                if (header.get("family") != case["family"] or
                        header.get("profile") != case["profile"] or
                        header.get("hz") != case["hz"] or
                        header.get("steps") != case["steps"] or
                        not exact(header.get("input"), case["input"])):
                    raise Difference("FAILED_INPUT", "case declaration differs from input record")
                if not _numeric_identity(header.get("dt"), 1.0 / case["hz"]):
                    raise Difference("UNPASSED_PREMISE", "target timestep differs")
                if case["family"] == "geometry-collision":
                    gap, _ = _represented_gap(header)
                    if header["input"]["delta"] != 0 and gap == 0:
                        raise Difference("UNPASSED_PREMISE", "boundary delta rounds away")
            elif kind in ("event", "action", "state"):
                step = left.get("step")
                order = left.get("order")
                if (type(step) is not int or type(order) is not int or
                        step != result["states"] + 1 or order <= last_order and step == current_step or
                        step < current_step):
                    raise Difference("FAILED_COVERAGE", "step or event order differs")
                if step != current_step:
                    current_step = step
                    last_order = -1
                last_order = order
                if kind == "state":
                    if _has_tagged_nonfinite(right["state"]) and not _has_tagged_nonfinite(left["state"]):
                        raise Difference("FAILED_NONFINITE", "candidate became nonfinite before baseline")
                    if _has_tagged_nonfinite(left["state"]):
                        raise Difference("FAILED_PHYSICAL" if case["id"] ==
                                         "P-J-Angle-ratio-limits-off--1.0" else "FAILED_NONFINITE",
                                         "pinned reference has nonfinite physical state")
                    current_reference = left["state"]
                    candidate_states[step] = right["state"]
                    _same_run_configuration(left, header, reference_modes)
                    _same_run_configuration(right, header, candidate_modes)
                    _same_run_state(left, header, previous_reference, rotation_cap,
                                    conditional_diagnostic) if all(
                        "transform" in body for body in left["state"]["bodies"]) else None
                    _same_run_state(right, header, previous_candidate, rotation_cap,
                                    conditional_diagnostic) if all(
                        "transform" in body for body in right["state"]["bodies"]) else None
                else:
                    events += 1
                    if kind == "action":
                        actions_seen.append(step)
                        _advance_modes(left, case, reference_modes)
                        _advance_modes(right, case, candidate_modes)
            elif kind == "case-end":
                if (left.get("steps") != case["steps"] or right.get("steps") != case["steps"] or
                        left.get("events") != events or right.get("events") != events or
                        result["states"] != case["steps"]):
                    raise Difference("FAILED_COVERAGE", "case completion differs")
            else:
                raise Difference("FAILED_COVERAGE", "unexpected record kind")
            prefix = kind + (f".{left['name']}" if kind in ("event", "action") else "")
            walk(left, right, prefix)
            if kind == "state":
                result["states"] += 1
                previous_reference = left["state"]
                previous_candidate = right["state"]
        if (first_kind != "inputs" or last_kind != "case-end" or
                result["records"] == 0 or result["states"] != case["steps"] or
                observed_paths != set(expected_paths)):
            raise Difference("FAILED_COVERAGE", "case path or state coverage differs")
        if case.get("expected_actions") is not None and actions_seen != case["expected_actions"]:
            raise Difference("FAILED_COVERAGE", "case action schedule differs")
        if rotation_audit is not None:
            try:
                validate_rotation_audit(rotation_audit, case, header, candidate_states,
                                        rotation_cap)
            except (KeyError, TypeError, ValueError, OverflowError) as error:
                raise Difference("UNPASSED_PREMISE", str(error)) from error
            result["rotation_audit"] = "STRUCTURE_PASSED_ORACLE_UNPASSED"
        result["status"] = ("CONDITIONAL_DIAGNOSTIC_WITHIN" if conditional_diagnostic
                            else "PASSED_NUMERICAL_POLICY")
    except Difference as error:
        result["status"] = error.status
        result["reason"] = str(error)
        if current_step:
            result["failed_step"] = current_step
    except Rejected as error:
        result["status"] = ("FAILED_NONFINITE" if "nonfinite" in str(error).lower()
                            else "FAILED_COVERAGE")
        result["reason"] = str(error)
    except (OSError, EOFError, KeyError, IndexError, TypeError, ValueError) as error:
        result["status"] = "FAILED_COVERAGE"
        result["reason"] = str(error)
    return result


def verify_candidate_identity(receipt, publication, commit, source_sha256,
                              artifacts, runtime_proof):
    if receipt.get("schema") != "portable-numerical-receipt/1":
        raise Rejected("candidate receipt schema differs")
    if any(row.get("candidate_commit") != commit or row.get("source_sha256") != source_sha256
           for row in (receipt, publication)):
        raise Rejected("candidate source identity differs")
    if not artifacts or set(receipt.get("artifact_sha256", {})) != set(artifacts) or \
            set(publication.get("artifact_sha256", {})) != set(artifacts):
        raise Rejected("candidate artifact producer set differs")
    if receipt.get("artifact_paths") != {name: str(path) for name, path in artifacts.items()}:
        raise Rejected("candidate artifact path differs")
    for name, path in artifacts.items():
        expected = digest(path)
        if (receipt["artifact_sha256"][name] != expected or
                publication["artifact_sha256"][name] != expected):
            raise Rejected(f"candidate artifact differs: {name}")
    if (runtime_proof.get("method_executions") != 15 or
            not runtime_proof.get("host") or
            not runtime_proof.get("version") or
            runtime_proof.get("version") == "UNAVAILABLE" or
            receipt.get("runtime") != runtime_proof):
        raise Rejected("candidate runtime or process proof differs")
    executable = Path(runtime_proof.get("executable", ""))
    if (not executable.is_file() or
            digest(executable) != runtime_proof.get("executable_sha256")):
        raise Rejected("candidate runtime executable differs")


def verify_numeric_probe(lane, commit, source_sha256, trace_sha256, artifacts,
                         runtime_proof):
    lane = Path(lane)
    path = lane / "numeric-probe-receipt.json"
    if not path.exists():
        return False
    if not path.is_file():
        raise Rejected("numeric probe receipt is not a file")
    receipt = json.loads(path.read_text())
    required = {"schema", "candidate_commit", "source_sha256", "trace_sha256",
                "artifact_sha256", "runtime", "method", "xml_sha256",
                "gradle_log_sha256", "probe"}
    if not isinstance(receipt, dict) or set(receipt) != required or \
            receipt["schema"] != "portable-binary64-probe-receipt/1":
        raise Rejected("numeric probe receipt schema differs")
    if receipt["candidate_commit"] != commit or receipt["source_sha256"] != source_sha256:
        raise Rejected("numeric probe source identity differs")
    if receipt["trace_sha256"] != trace_sha256:
        raise Rejected("numeric probe trace identity differs")
    if not artifacts or receipt["artifact_sha256"] != {
            name: digest(file) for name, file in artifacts.items()}:
        raise Rejected("numeric probe artifact identity differs")
    executable = Path(runtime_proof.get("executable", ""))
    if (receipt["runtime"] != runtime_proof or not executable.is_file() or
            digest(executable) != runtime_proof.get("executable_sha256")):
        raise Rejected("numeric probe runtime identity differs")
    if receipt["method"] != PROBE_METHOD:
        raise Rejected("numeric probe method differs")
    xml_path = lane / "xml" / f"{PROBE_METHOD}.xml"
    log_path = lane / f"gradle-{PROBE_METHOD}.log"
    if not xml_path.is_file() or digest(xml_path) != receipt["xml_sha256"]:
        raise Rejected("numeric probe XML differs")
    if not log_path.is_file() or digest(log_path) != receipt["gradle_log_sha256"]:
        raise Rejected("numeric probe process log differs")
    try:
        suite = ET.parse(xml_path).getroot()
    except ET.ParseError as error:
        raise Rejected("numeric probe XML is invalid") from error
    if suite.tag != "testsuite" or any(
            suite.get(field) != value for field, value in
            (("tests", "1"), ("skipped", "0"), ("failures", "0"), ("errors", "0"))):
        raise Rejected("numeric probe test execution differs")
    tests = suite.findall("testcase")
    if (len(tests) != 1 or tests[0].get("classname") != "portable.PortableMatrixTest" or
            tests[0].get("name") != PROBE_METHOD):
        raise Rejected("numeric probe test method differs")
    output = suite.findtext("system-out")
    if output is None:
        raise Rejected("numeric probe target output is missing")
    markers = [line.split("NUMERICAL_PROBE_JSON ", 1)[1]
               for line in output.splitlines() if line.startswith("NUMERICAL_PROBE_JSON ")]
    if len(markers) != 1:
        raise Rejected("numeric probe target marker count differs")
    try:
        payload = json.loads(markers[0], parse_constant=lambda value: (_ for _ in ()).throw(
            Rejected(f"numeric probe nonfinite token: {value}")))
    except (ValueError, TypeError) as error:
        raise Rejected("numeric probe target payload is invalid") from error
    boolean_fields = ("maximumFinite", "positiveInfinityFinite", "nanFinite")
    if (not isinstance(payload, dict) or not isinstance(receipt["probe"], dict) or
            any(type(row.get(field)) is not bool
                for row in (payload, receipt["probe"]) for field in boolean_fields)):
        raise Rejected("numeric probe Boolean field type differs")
    if payload != PROBE_VALUES or receipt["probe"] != PROBE_VALUES:
        raise Rejected("numeric probe target arithmetic differs")
    inputs = []
    for line in output.splitlines():
        if line.startswith("NUMERICAL_JSON "):
            try:
                row = json.loads(line.split("NUMERICAL_JSON ", 1)[1])
            except ValueError as error:
                raise Rejected("numeric probe target input JSON is invalid") from error
            if row.get("kind") == "inputs" and row.get("id") == "geometry-boundary-s1-o3-d3":
                inputs.append(row)
    if (len(inputs) != 1 or not isinstance(inputs[0].get("input"), dict) or
            type(inputs[0]["input"].get("signedZero")) is not float or
            inputs[0]["input"]["signedZero"] != 0.0 or
            math.copysign(1.0, inputs[0]["input"]["signedZero"]) != -1.0):
        raise Rejected("numeric probe signed-zero trace transport differs")
    return True


def verify_candidate_inventory(lane, expected_ids, hosts):
    lane = Path(lane)
    if lane.name not in hosts:
        raise Rejected("candidate producer is not declared")
    expected_files = {f"{case_id}.jsonl" for case_id in expected_ids}
    cases = lane / "cases"
    if not cases.is_dir() or {path.name for path in cases.iterdir()} != expected_files:
        raise Rejected("candidate case file set differs")
    probe = lane / "numeric-probe-receipt.json"
    expected_receipts = {"receipt.json"} | ({probe.name} if probe.is_file() else set())
    if {path.name for path in lane.glob("*receipt*.json")} != expected_receipts:
        raise Rejected("candidate receipt set differs")
    root = lane.parent
    if list(root.glob("*receipt*.json")):
        raise Rejected("candidate root has an additional receipt")
    for path in root.glob("*/*receipt*.json"):
        if path.parent.name not in hosts:
            raise Rejected("candidate receipt has an undeclared producer")
        if path.name not in {"receipt.json", "numeric-probe-receipt.json"}:
            raise Rejected("candidate receipt set differs")


def compare_host(baseline, lane, frozen_ids):
    from baseline_capture import PINNED_JAR_SHA256, fixture_source_sha256, verify_case_slices
    from receipt import Identity, verify as verify_receipt
    from run import HOST_TASKS, MATRIX_METHODS, STAGED, artifacts, clean_identity, runtime

    manifest = json.loads((Path(baseline) / "verified.json").read_text())
    cases = declared_cases()
    expected = {case["id"] for case in cases}
    verify_candidate_inventory(lane, expected, HOST_TASKS)
    verify_baseline_manifest(manifest, expected, PINNED_JAR_SHA256, fixture_source_sha256())
    verify_baseline_bytes(baseline, manifest)
    catalog = load_policy_catalog()
    verify_policy_catalog(catalog, manifest, cases, frozen_ids)
    receipt = json.loads((Path(lane) / "receipt.json").read_text())
    host = Path(lane).name
    if host not in HOST_TASKS:
        raise Rejected("candidate host is not a declared producer")
    commit, source_sha256 = clean_identity()
    target_artifacts = artifacts(host)
    publication_path = Path(lane).parent / "publication.json"
    publication = json.loads(publication_path.read_text())
    if digest(Path(lane).parent / "publication.log") != publication.get("publication_log_sha256"):
        raise Rejected("candidate publication log differs")
    all_paths = {str(path.relative_to(STAGED)): path
                 for lane_host in HOST_TASKS for path in artifacts(lane_host).values()}
    if set(publication.get("artifact_sha256", {})) != set(all_paths):
        raise Rejected("candidate publication producer set differs")
    for name, path in all_paths.items():
        if digest(path) != publication["artifact_sha256"][name]:
            raise Rejected(f"candidate publication artifact differs: {name}")
    subset = {"candidate_commit": publication.get("candidate_commit"),
              "source_sha256": publication.get("source_sha256"),
              "artifact_sha256": {role: publication["artifact_sha256"][
                  str(path.relative_to(STAGED))] for role, path in target_artifacts.items()}}
    runtime_proofs = [runtime(host, Path(lane) / f"gradle-{method}.log",
                              Path(lane) / f"native-exec-{method}.log"
                              if host == "linux-x64" else None)
                      for method in MATRIX_METHODS]
    if any(proof != runtime_proofs[0] for proof in runtime_proofs[1:]):
        raise Rejected("candidate methods used different runtime producers")
    runtime_proof = {**runtime_proofs[0], "method_executions": len(runtime_proofs)}
    verify_candidate_identity(receipt, subset, commit, source_sha256,
                              target_artifacts, runtime_proof)
    identity = Identity(commit, source_sha256, receipt["artifact_sha256"], runtime_proof)
    verify_receipt(receipt, Path(lane) / "trace.jsonl", cases, identity, target_artifacts)
    verify_case_slices(Path(lane), expected)
    probe_archive_consistent = verify_numeric_probe(lane, commit, source_sha256,
                                                    receipt["trace_sha256"],
                                                    target_artifacts, runtime_proof)
    probe_verified = False
    prospective = [case for case in cases if case["id"] not in frozen_ids]
    results = []
    for case in prospective:
        case_id = case["id"]
        reference = Path(baseline) / "baseline-jvm/cases" / f"{case_id}.jsonl"
        candidate = Path(lane) / "cases" / f"{case_id}.jsonl"
        verify_reference_inventory(reference, case_id, catalog)
        compared = compare_policy_case(reference, candidate, case, catalog)
        if compared["status"] == "PASSED_NUMERICAL_POLICY" and probe_verified:
            compared["qualification"] = "PASSED_CASE_POLICY"
        results.append(compared)
    if len(results) != len(expected - set(frozen_ids)):
        raise Rejected("prospective case coverage differs")
    failed = sum(row["status"].startswith("FAILED") for row in results)
    unpassed = sum(row["status"].startswith("UNPASSED") for row in results)
    passed = sum(row["qualification"] == "PASSED_CASE_POLICY" for row in results)
    summary = {"status": ("FAILED_PHYSICAL" if any(row["status"] == "FAILED_PHYSICAL"
                            for row in results) else
                          "UNPASSED" if failed or unpassed or not probe_verified else
                          "PASSED_NUMERICAL_POLICY"),
               "qualification": "UNPASSED",
               "numeric_probe": ("PASSED" if probe_verified else
                                 "UNPASSED_UNBOUND_PRODUCER" if probe_archive_consistent else
                                 "UNPASSED_NOT_EXECUTED"),
               "baseline_jar_sha256": manifest["baseline_jar_sha256"],
               "baseline_trace_sha256": manifest["trace_sha256"],
               "baseline_fixture_source_sha256": manifest["fixture_source_sha256"],
               "candidate_trace_sha256": receipt["trace_sha256"],
               "cases": len(results),
               "exact_diagnostic": sum(row["status"] == "PASSED_NUMERICAL_POLICY" and
                                       row["different_numeric_values"] == 0 for row in results),
               "passed_case_policy": passed, "unpassed_numeric": unpassed,
               "failed": failed,
               "results": results}
    (Path(lane) / "prospective-comparison.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary
