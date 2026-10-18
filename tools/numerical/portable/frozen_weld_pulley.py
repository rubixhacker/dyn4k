import copy
import gzip
import hashlib
import json
import math
from fractions import Fraction
from itertools import zip_longest
from pathlib import Path

from receipt import Rejected, records
from reference_diagnostic import projected_records, reference_records


CATALOG = Path(__file__).resolve().parents[1] / "fixtures.json"
POLICY = Path(__file__).with_name("frozen_weld_pulley_policy.json")
KEYS = ("weld-enabled-equal", "pulley-preparation-0", "pulley-preparation-1",
        "pulley-slack-transition")


BOUNDS = {
    "T": (1e-4, "m"), "V": (1e-3, "m/s"), "A": (1e-4, "rad"),
    "W": (1e-3, "rad/s"), "TRIG": (1.0000000002e-4, "dimensionless"),
    "D": (1e-4, "m"), "P": (1e-4, "m"), "I": (1e-3, "N s"),
    "F": (0.06, "N"), "TAU": (0.06, "N m"),
    "L1": (1.5e-4, "m"), "L2": (3e-4, "m"),
    "Q": (1e-6, "fraction"), "MIX": (1.5e-14, "dimensionless"),
    "AREA": (2e-13, "m^2"), "RADIUS": (1e-13, "m"),
    "STIFF": (2e-12, "N m/rad"),
    "CP": (2.0000000002e-4, "m"), "CA": (2.0000000002e-4, "rad"),
}
PINNED_TOI_DISTANCE_EPSILON = 4.806217383937352e-6
SEPARATION_ROUNDING_ULPS = 8
CASE_POSITIONS = {"weld-enabled-equal": 0, "pulley-preparation-0": 1,
                  "pulley-preparation-1": 2, "pulley-slack-transition": 3}
DUPLICATES = {"getAccumulatedForce": "accumulatedForce",
              "getAccumulatedTorque": "accumulatedTorque",
              "getAngularVelocity": "angularVelocity", "getForce": "force",
              "getLinearVelocity": "velocity", "getTorque": "torque",
              "getTransform": "transform", "getPreviousTransform": "previousTransform",
              "getWorldCenter": "worldCenter", "isAtRest": "atRest"}
INTEGER_SUFFIXES = (".step", ".order", ".outerStep", ".innerWithinOuter",
                    ".steps", ".getBodyCount", ".getFixtureCount", ".getSpringMode",
                    ".getPositionConstraintSolverIterations",
                    ".getVelocityConstraintSolverIterations",
                    ".getMaxDetectIterations", ".getMaxDistanceIterations",
                    ".getMaxRaycastIterations", ".getMaxIterations")


def policy():
    return json.loads(POLICY.read_text())


def _number(value, path):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise Rejected(f"finite numeric value required: {path}")
    try:
        binary = float(value)
    except OverflowError as error:
        raise Rejected(f"binary64 value required: {path}") from error
    if not math.isfinite(binary):
        raise Rejected(f"finite binary64 value required: {path}")
    return binary


def _same(left, right, path="value"):
    if type(left) in (int, float) or type(right) in (int, float):
        return _number(left, path) == _number(right, path)
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _same(left[key], right[key], f"{path}.{key}") for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _same(a, b, f"{path}[]") for a, b in zip(left, right))
    return type(left) is type(right) and left == right


def _bound(left, right, limit, path, orientation=False):
    a, b = _number(left, path), _number(right, path)
    if orientation:
        if abs(a) > math.pi or abs(b) > math.pi:
            raise Rejected(f"orientation domain differs: {path}")
        difference = abs(math.atan2(math.sin(a - b), math.cos(a - b)))
    else:
        difference = abs(Fraction.from_float(a) - Fraction.from_float(b))
    if difference > Fraction.from_float(limit):
        raise Rejected(f"numeric limit exceeded: {path}")


def _direction(left, right, path):
    if len(left) != 2 or len(right) != 2:
        raise Rejected(f"direction shape differs: {path}")
    a = [_number(value, path) for value in left]
    b = [_number(value, path) for value in right]
    na, nb = math.hypot(*a), math.hypot(*b)
    if na == 0 or nb == 0:
        if na != nb:
            raise Rejected(f"direction placeholder differs: {path}")
        return
    if abs(na - 1) > 1e-6 or abs(nb - 1) > 1e-6 or abs(na - nb) > 1e-6:
        raise Rejected(f"direction norm differs: {path}")
    angle = abs(math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]))
    if angle > 1e-4:
        raise Rejected(f"direction angle differs: {path}")


def _orientation_change(body):
    first = _number(body["previousTransform"]["getRotationAngle"], "previous angle")
    last = _number(body["transform"]["getRotationAngle"], "current angle")
    velocity = _number(body["angularVelocity"], "angular velocity")
    if abs(first) > math.pi or abs(last) > math.pi:
        raise Rejected("source angle getter outside signed range")
    if first == last:
        return 0.0, (False, False, "equal")
    first_negative, last_negative = first < 0, last < 0
    first = first + 2 * math.pi if first_negative else first
    last = last + 2 * math.pi if last_negative else last
    value = last - first
    if velocity == 0:
        branch = "zero-direct"
        if value > math.pi:
            value -= 2 * math.pi
            branch = "zero-subtract"
        elif value < -math.pi:
            value += 2 * math.pi
            branch = "zero-add"
    elif last < first and velocity > 0:
        value += 2 * math.pi
        branch = "positive-wrap"
    elif last > first and velocity < 0:
        value -= 2 * math.pi
        branch = "negative-wrap"
    else:
        branch = "direct"
    return value, (first_negative, last_negative, branch)


def _transform_aliases(value, path):
    if not isinstance(value, dict) or not all(name in value for name in
            ("getCost", "getSint", "getRotationAngle", "getTranslationX",
             "getTranslationY", "getTranslation", "getValues")):
        raise Rejected(f"complete transform is absent: {path}")
    x, y = value["getTranslationX"], value["getTranslationY"]
    cosine, sine = value["getCost"], value["getSint"]
    if not _same(value["getTranslation"], [x, y], path) or not _same(
            value["getValues"], [cosine, -sine, x, sine, cosine, y], path):
        raise Rejected(f"same-provider transform alias differs: {path}")


def _snapshot_aliases(state, path):
    if not isinstance(state, dict) or not isinstance(state.get("bodies"), list):
        raise Rejected(f"complete body state is absent: {path}")
    for body in state["bodies"]:
        if "transform" not in body or "previousTransform" not in body:
            raise Rejected(f"body transform is absent: {path}")
        for name in ("transform", "previousTransform"):
            _transform_aliases(body[name], f"{path}.{name}")
        if "properties" not in body:
            continue
        props = body["properties"]
        for getter, field in DUPLICATES.items():
            if getter not in props or field not in body or not _same(props[getter], body[field]):
                raise Rejected(f"same-provider body alias differs: {path}.{getter}")
        current = body["transform"]["getTranslation"]
        previous = body["previousTransform"]["getTranslation"]
        if any(abs(_number(value, path)) > 16 for value in current + previous):
            raise Rejected("CP position scale premise is absent")
        computed = [current[i] - previous[i] for i in range(2)]
        if not _same(props.get("getChangeInPosition"), computed):
            raise Rejected(f"same-provider position-change formula differs: {path}")
        angle, _ = _orientation_change(body)
        if not _same(props.get("getChangeInOrientation"), angle):
            raise Rejected(f"same-provider orientation-change formula differs: {path}")
        mass = props.get("getMass", {})
        if not _same(props.get("getLocalCenter"), mass.get("getCenter")):
            raise Rejected(f"mass center alias differs: {path}")
        if props.get("getFixtureCount") != len(body.get("fixtures", [])) or \
                type(props.get("getFixtureCount")) is not int:
            raise Rejected(f"fixture count schema differs: {path}")
        if not _same(body.get("worldCenter"), current) or not _same(
                body.get("fixedOriginPosition"), current):
            raise Rejected(f"center/translation alias differs: {path}")
    for joint in state.get("joints", []):
        if not _same(joint.get("getReactionTorque"), joint.get("reactionTorque")):
            raise Rejected(f"joint reaction torque alias differs: {path}")
        if "getCurrentLength" in joint:
            one, two = joint["getCurrentLength1"], joint["getCurrentLength2"]
            ratio = joint["getRatio"]
            expected = one + ratio * two
            if abs(_number(joint["getCurrentLength"], path) - expected) > \
                    2 * math.ulp(max(abs(expected), 1.0)):
                raise Rejected(f"same-provider Pulley length formula differs: {path}")


def _constraint_directions(value, path):
    if "getNormal" not in value or "getTangent" not in value:
        return
    normal, tangent = value["getNormal"], value["getTangent"]
    if not isinstance(normal, list) or not isinstance(tangent, list) or \
            len(normal) != 2 or len(tangent) != 2:
        raise Rejected(f"contact direction shape differs: {path}")
    n = [_number(component, path) for component in normal]
    t = [_number(component, path) for component in tangent]
    if math.hypot(*n) == 0 and math.hypot(*t) == 0:
        return
    if abs(n[0] * t[0] + n[1] * t[1]) > 1e-6 or \
            abs(t[0] - n[1]) > 1e-6 or abs(t[1] + n[0]) > 1e-6:
        raise Rejected(f"contact tangent is not source-perpendicular: {path}")


def _rule(key, path, selected):
    if path.startswith("inputs.state.") and key in ("pulley-preparation-1", "pulley-slack-transition"):
        if path in selected["header_mapped_paths"]:
            return selected["header_mapped_paths"][path]
        extra = selected["header_extra_paths"].get(path)
        if extra:
            rule = extra["rule"]
            if rule == "AL":
                return extra["detail"].split("(", 1)[1].split(")", 1)[0]
            if rule == "MAT":
                return "TRIG" if path.endswith(("getCost", "getSint")) else "T"
            return rule
        raise Rejected(f"unnamed later-header numeric field: {path}")
    entry = selected["state_event_paths"].get(path)
    if entry and entry["mask"][CASE_POSITIONS[key]] == "Y":
        return entry["rule"]
    return None


def _numeric_paths(value, path):
    if isinstance(value, dict):
        for name, child in value.items():
            yield from _numeric_paths(child, f"{path}.{name}")
    elif isinstance(value, list):
        for child in value:
            yield from _numeric_paths(child, path + "[]")
    elif type(value) in (int, float):
        yield path


def _later_header_catalog(selected, row):
    mapped = selected["header_mapped_paths"]
    extra = selected["header_extra_paths"]
    named = selected["later_header_paths"]
    if len(mapped) != 34 or len(extra) != 48 or len(named) != 82 or \
            set(named) != set(mapped) | set(extra) or set(mapped) & set(extra):
        raise Rejected("later-header numeric catalog is incomplete")
    present = set(_numeric_paths(row["state"], "inputs.state"))
    if present != set(named):
        missing = sorted(set(named) - present)
        unknown = sorted(present - set(named))
        raise Rejected(f"later-header numeric catalog differs: missing={missing}, unknown={unknown}")


def _populated_separation(value, path):
    if set(value) != {"type", "getDistance", "getNormal", "getPoint1", "getPoint2"} or \
            value["type"] != "org.dyn4j.collision.narrowphase.Separation":
        raise Rejected(f"populated TOI separation shape differs: {path}")
    distance = _number(value["getDistance"], path + ".getDistance")
    if not 0 < distance <= PINNED_TOI_DISTANCE_EPSILON:
        raise Rejected(f"populated TOI separation fixed-case epsilon cap differs: {path}")
    points = []
    for name in ("getPoint1", "getPoint2"):
        point = value[name]
        if not isinstance(point, list) or len(point) != 2:
            raise Rejected(f"populated TOI separation point shape differs: {path}.{name}")
        coordinates = [_number(component, path + "." + name) for component in point]
        if any(abs(component) > 16.0 for component in coordinates):
            raise Rejected(f"populated TOI separation point scale differs: {path}.{name}")
        points.append(coordinates)
    delta = [points[1][index] - points[0][index] for index in range(2)]
    derived = math.sqrt(delta[0] * delta[0] + delta[1] * delta[1])
    if abs(distance - derived) > SEPARATION_ROUNDING_ULPS * math.ulp(distance):
        raise Rejected(f"populated TOI separation distance formula differs: {path}")
    normal = value["getNormal"]
    if not isinstance(normal, list) or len(normal) != 2:
        raise Rejected(f"populated TOI separation normal shape differs: {path}")
    unit = [_number(component, path + ".getNormal") for component in normal]
    inverse = 1.0 / distance
    if any(abs(unit[index] - delta[index] * inverse) >
           SEPARATION_ROUNDING_ULPS * math.ulp(1.0) for index in range(2)):
        raise Rejected(f"populated TOI separation normal formula differs: {path}")
    if abs(math.hypot(*unit) - 1.0) > 1e-6:
        raise Rejected(f"populated TOI separation unit normal differs: {path}")


def _compare_separation(left, right, path, counts):
    if not isinstance(left, dict) or not isinstance(right, dict):
        raise Rejected(f"TOI separation shape differs: {path}")
    if left.keys() != right.keys():
        raise Rejected(f"TOI separation fields differ: {path}")
    if left.get("type") != "org.dyn4j.collision.narrowphase.Separation" or \
            right.get("type") != left["type"]:
        raise Rejected(f"TOI separation type differs: {path}")
    fields = ("getDistance", "getPoint1[]", "getPoint2[]")
    if _number(left.get("getDistance"), path + ".getDistance") == 0:
        for name in ("getNormal", "getPoint1", "getPoint2"):
            if not isinstance(left.get(name), list) or not isinstance(right.get(name), list) or \
                    len(left[name]) != 2 or len(right[name]) != 2 or \
                    any(_number(value, path + "." + name) != 0 for value in
                        left[name] + right[name]):
                raise Rejected(f"zero TOI separation placeholder differs: {path}.{name}")
        if _number(right.get("getDistance"), path + ".getDistance") != 0:
            raise Rejected(f"TOI separation output branch differs: {path}")
        counts["exact"] += 7
    else:
        if _number(right.get("getDistance"), path + ".getDistance") == 0:
            raise Rejected(f"TOI separation output branch differs: {path}")
        _populated_separation(left, path)
        _populated_separation(right, path)
        _bound(left["getDistance"], right["getDistance"], BOUNDS["D"][0],
               path + ".getDistance")
        for name in ("getPoint1", "getPoint2"):
            for a, b in zip(left[name], right[name]):
                _bound(a, b, BOUNDS["P"][0], path + "." + name)
        _direction(left["getNormal"], right["getNormal"], path + ".getNormal")
        counts["numeric"] += 6
        counts["populated_separation_checks"] += 1
    counts["covered_paths"].update(path + "." + name for name in
                                   (*fields, "getNormal[]"))


def _compare(key, left, right, path, selected, counts):
    if isinstance(left, dict) or isinstance(right, dict):
        if not isinstance(left, dict) or not isinstance(right, dict) or left.keys() != right.keys():
            raise Rejected(f"fields differ: {path}")
        if path == "event.payload[].separation" and key in (
                "pulley-preparation-1", "pulley-slack-transition"):
            _compare_separation(left, right, path, counts)
            return
        if path == "event.payload[].shape":
            literal = ("getArea" if left.get("type") == "org.dyn4j.geometry.Rectangle"
                       else "getRadius" if left.get("type") == "org.dyn4j.geometry.Circle"
                       else None)
            if literal is not None and not _same(left.get(literal), right.get(literal), path):
                raise Rejected(f"literal shape value differs: {path}.{literal}")
        if path in ("inputs.state", "state.state"):
            if path == "inputs.state" and key in ("pulley-preparation-1", "pulley-slack-transition"):
                _later_header_catalog(selected, {"state": left})
                _later_header_catalog(selected, {"state": right})
            _snapshot_aliases(left, path)
            _snapshot_aliases(right, path)
            for a, b in zip(left["bodies"], right["bodies"]):
                if path == "state.state":
                    _, left_branch = _orientation_change(a)
                    _, right_branch = _orientation_change(b)
                    if left_branch != right_branch:
                        raise Rejected("state orientation source branch differs")
                    if a.get("id") == "b0" or b.get("id") == "b0":
                        for name in ("transform", "previousTransform", "velocity",
                                     "angularVelocity", "worldCenter", "fixedOriginPosition"):
                            if not _same(a.get(name), b.get(name), f"{path}.{name}"):
                                raise Rejected(f"fixed-body state differs: {name}")
            if path == "inputs.state" and key in ("pulley-preparation-1", "pulley-slack-transition"):
                for a, b in zip(left["bodies"], right["bodies"]):
                    if "properties" in a and "properties" in b:
                        _, left_branch = _orientation_change(a)
                        _, right_branch = _orientation_change(b)
                        if left_branch != right_branch:
                            raise Rejected("CA source orientation branch differs")
        if path.endswith(".constraint"):
            _constraint_directions(left, path)
            _constraint_directions(right, path)
        for name in left:
            _compare(key, left[name], right[name], f"{path}.{name}", selected, counts)
        return
    if isinstance(left, list) or isinstance(right, list):
        if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right):
            raise Rejected(f"array length differs: {path}")
        if path.endswith(".getValues") and (path.startswith("state.state.bodies[]") or
              (path.startswith("inputs.state.bodies[]") and key in
               ("pulley-preparation-1", "pulley-slack-transition"))):
            if len(left) != 6:
                raise Rejected(f"transform matrix length differs: {path}")
            for index, (a, b) in enumerate(zip(left, right)):
                rule = "T" if index in (2, 5) else "TRIG"
                _bound(a, b, BOUNDS[rule][0], f"{path}[{index}]")
                counts["numeric"] += 1
            return
        if path.startswith("event.") and selected["state_event_paths"].get(path + "[]", {}).get("rule") == "DIR":
            _direction(left, right, path)
            counts["covered_paths"].add(path + "[]")
            counts["numeric"] += 1
            return
        for a, b in zip(left, right):
            _compare(key, a, b, path + "[]", selected, counts)
        return
    if type(left) in (int, float) or type(right) in (int, float):
        a, b = _number(left, path), _number(right, path)
        if (path.endswith(INTEGER_SUFFIXES) or
                (path.startswith("inputs.world.") and path.endswith(".getHeight"))) and (
                              type(left) is not int or type(right) is not int):
            raise Rejected(f"integer schema differs: {path}")
        rule = _rule(key, path, selected)
        if path in selected["state_event_paths"] and \
                selected["state_event_paths"][path]["mask"][CASE_POSITIONS[key]] == "Y":
            counts["covered_paths"].add(path)
        if rule in ("X", "Z", "TS", "EX") or rule is None:
            if rule == "Z" and a != 0:
                counts["policy_conflicts"].add(path)
            if a != b or (rule == "Z" and a == 0 and b != 0):
                raise Rejected(f"exact numeric value differs: {path}")
            counts["exact"] += 1
            return
        if rule == "MAT":
            raise Rejected(f"matrix slot has no named rule: {path}")
        if rule == "RTAU":
            if key != "weld-enabled-equal":
                if a != 0 or b != 0:
                    raise Rejected(f"Pulley reaction torque differs: {path}")
                counts["exact"] += 1
                return
            rule = "TAU"
        if rule == "ANCH1":
            rule = "X" if key == "weld-enabled-equal" else "T"
        if rule == "ANCH2":
            rule = "ANCH2_WELD" if key == "weld-enabled-equal" else "T"
        if rule == "ANCH2_WELD":
            _bound(a, b, 2e-4, path)
        elif rule == "X":
            if a != b:
                raise Rejected(f"exact anchor differs: {path}")
        elif rule in BOUNDS:
            if rule == "Q" and not (0 <= a <= 1 and 0 <= b <= 1):
                raise Rejected(f"TOI fraction domain differs: {path}")
            if rule in ("MIX", "STIFF") and a == 0 and b != 0:
                raise Rejected(f"zero formula branch differs: {path}")
            if rule == "I" and (a != 0 or b != 0) and (a == 0 or b == 0 or
                                                       (a > 0) != (b > 0)):
                raise Rejected(f"nonzero impulse sign differs: {path}")
            _bound(a, b, BOUNDS[rule][0], path, orientation=rule == "A" and
                   not path.endswith("rotationIncrementSum"))
        else:
            raise Rejected(f"rule is unavailable: {path} ({rule})")
        counts["numeric"] += 1
        return
    if type(left) is not type(right) or left != right:
        raise Rejected(f"structural or exact value differs: {path}")


def compare_records(key, reference, candidate, require_coverage=False):
    selected = policy()
    counts = {"records": 0, "exact": 0, "numeric": 0,
              "policy_conflicts": set(), "covered_paths": set(),
              "populated_separation_checks": 0}
    try:
        if key not in KEYS:
            raise Rejected(f"unknown Weld/Pulley case: {key}")
        sentinel = object()
        for left, right in zip_longest(reference, candidate, fillvalue=sentinel):
            if left is sentinel or right is sentinel:
                raise Rejected("frozen record count differs")
            if left.get("kind") != right.get("kind"):
                raise Rejected("frozen record kind differs")
            _compare(key, left, right, left["kind"], selected, counts)
            counts["records"] += 1
        if counts["records"] == 0:
            raise Rejected("zero Weld/Pulley records executed")
        covered = counts.pop("covered_paths")
        counts["covered_rule_paths"] = len(covered)
        if require_coverage:
            expected = {path for path, entry in selected["state_event_paths"].items()
                        if entry["mask"][CASE_POSITIONS[key]] == "Y"}
            missing = sorted(expected - covered)
            if missing:
                raise Rejected("adopted rule path was unvisited: " + ", ".join(missing))
        conflicts = sorted(counts.pop("policy_conflicts"))
        if conflicts:
            return {"status": "UNPASSED_POLICY_CONFLICT", "reason":
                    "adopted zero premise contradicts frozen value: " + ", ".join(conflicts),
                    "policy_conflicts": conflicts, **counts}
        return {"status": "PASSED", **counts}
    except (Rejected, KeyError, TypeError, ValueError, OverflowError) as error:
        counts.setdefault("covered_rule_paths", len(counts.pop("covered_paths", set())))
        counts["policy_conflicts"] = sorted(counts["policy_conflicts"])
        return {"status": "FAILED", "reason": str(error), **counts}


def _subset_equal(compact, complete, path="state"):
    if isinstance(compact, dict) and isinstance(complete, dict):
        return compact.keys() <= complete.keys() and all(
            _subset_equal(compact[name], complete[name], f"{path}.{name}") for name in compact)
    if isinstance(compact, list) and isinstance(complete, list):
        return len(compact) == len(complete) and all(
            _subset_equal(a, b, f"{path}[]") for a, b in zip(compact, complete))
    return _same(compact, complete, path)


def verify_provider_chain(key, current, previous):
    if key not in ("pulley-preparation-1", "pulley-slack-transition"):
        raise Rejected("case has no continuation chain")
    if not current or not previous or current[0].get("kind") != "inputs" or \
            previous[-1].get("kind") != "case-end":
        raise Rejected("complete same-provider chain is absent")
    chain = current[0].get("frozenChain")
    end = previous[-1].get("frozenEndState")
    if not isinstance(chain, dict) or not isinstance(end, dict):
        raise Rejected("complete post-action snapshot is absent")
    previous_states = [row for row in previous if row.get("kind") == "state"]
    if not previous_states or not _subset_equal(previous_states[-1]["frozenState"], end):
        raise Rejected("preceding complete end differs from its actual final step")
    expected_id = ("P-JINT-Pulley-slack-transition-preparation-0" if
                   key == "pulley-preparation-1" else
                   "P-JINT-Pulley-slack-transition-preparation-1")
    operation = ("body2.setLinearVelocity(0,10) before source step2" if
                 key == "pulley-preparation-1" else "no inter-segment action")
    if chain.get("previousCaseId") != expected_id or chain.get("operation") != operation:
        raise Rejected("continuation source or action identity differs")
    if not _same(chain.get("previousEnd"), end) or not _same(chain.get("preAction"), end):
        raise Rejected("continuation did not start from its own preceding segment")
    expected = copy.deepcopy(end)
    if key == "pulley-preparation-1":
        expected["bodies"][2]["velocity"] = [0.0, 10.0]
        expected["bodies"][2]["properties"]["getLinearVelocity"] = [0.0, 10.0]
    if not _same(chain.get("postAction"), expected):
        raise Rejected("post-action state differs from the exact source action")
    if not _same(current[0].get("frozenInput", {}).get("state"), chain["postAction"]):
        raise Rejected("continuation header differs from its actual post-action state")
    return {"status": "PASSED", "previous_case": expected_id,
            "operation": operation, "complete_bodies": len(end["bodies"]),
            "complete_joints": len(end["joints"])}


def verify_temporal_state(key, rows):
    try:
        previous = None
        checked = 0
        for row in rows:
            if row.get("kind") == "inputs":
                if previous is not None:
                    raise Rejected("duplicate temporal input")
                previous = row["frozenInput"]["state"]
            elif row.get("kind") == "state":
                if previous is None:
                    raise Rejected("temporal input is absent")
                current = row["frozenState"]
                if len(previous["bodies"]) != len(current["bodies"]):
                    raise Rejected("temporal body set differs")
                for prior, body in zip(previous["bodies"], current["bodies"]):
                    if prior["id"] != body["id"]:
                        raise Rejected("temporal body identity differs")
                    expected = copy.deepcopy(prior["transform"])
                    if key == "pulley-slack-transition" and row["step"] == 201 and \
                            body["id"] == "b2":
                        y = expected["getTranslationY"] + 0.1
                        expected["getTranslationY"] = y
                        expected["getTranslation"][1] = y
                        expected["getValues"][5] = y
                    if not _same(body["previousTransform"], expected):
                        raise Rejected(f"phase-correct previous transform differs at step {row['step']}")
                    checked += 1
                previous = current
        if checked == 0:
            raise Rejected("zero temporal body transitions")
        return {"status": "PASSED", "body_transitions": checked}
    except (Rejected, KeyError, TypeError, ValueError) as error:
        return {"status": "FAILED", "reason": str(error)}


def compare_branches(key, reference_rows, candidate_rows):
    try:
        checked = 0
        for left, right in zip_longest(reference_rows, candidate_rows):
            if left is None or right is None or left.get("step") != right.get("step"):
                raise Rejected("Pulley pre-step branch sequence differs")
            first, second = left.get("frozenBranch"), right.get("frozenBranch")
            if not isinstance(first, dict) or not isinstance(second, dict):
                return {"status": "UNPASSED_PREMISE", "reason":
                        "complete pre-step Pulley branch capture is absent"}
            if first.keys() != second.keys():
                raise Rejected("Pulley pre-step branch schema differs")
            step = left["step"]
            expected_slack = key == "pulley-slack-transition" and 201 <= step <= 400
            for branch in (first, second):
                if type(branch["slackEnabled"]) is not bool or \
                        type(branch["overLength"]) is not bool:
                    raise Rejected("Pulley branch boolean schema differs")
                if branch["slackEnabled"] != expected_slack:
                    raise Rejected("Pulley slack phase differs")
                current = _number(branch["currentLength"], "pre-step length")
                target = _number(branch["targetLength"], "target length")
                ratio = _number(branch["ratio"], "Pulley ratio")
                if target != 1.5 or ratio != 1.0:
                    raise Rejected("Pulley immutable target or ratio differs")
                if branch["overLength"] != (current > target or not expected_slack):
                    raise Rejected("Pulley source over-length decision differs")
                for index in (1, 2):
                    anchor = branch[f"anchor{index}"]
                    pulley_anchor = branch[f"pulleyAnchor{index}"]
                    if len(anchor) != 2 or len(pulley_anchor) != 2:
                        raise Rejected("Pulley anchor shape differs")
                    distance = math.hypot(*(_number(anchor[n], "anchor") -
                                             _number(pulley_anchor[n], "pulley anchor")
                                             for n in range(2)))
                    measured = _number(branch[f"length{index}"], "segment length")
                    if abs(measured - distance) > 16 * math.ulp(max(distance, 1.0)):
                        return {"status": "UNPASSED_PREMISE", "reason":
                                "Pulley segment target math premise is absent"}
                total = branch["length1"] + ratio * branch["length2"]
                if abs(current - total) > 16 * math.ulp(max(abs(total), 1.0)):
                    return {"status": "UNPASSED_PREMISE", "reason":
                            "Pulley total-length target math premise is absent"}
            if first["overLength"] != second["overLength"]:
                raise Rejected("Pulley source over-length branches differ")
            _bound(first["currentLength"], second["currentLength"], 3e-4,
                   "pre-step Pulley currentLength")
            if checked == 0 and key == "pulley-preparation-1" and step != 2:
                raise Rejected("Pulley preparation continuation omitted step 2")
            if key == "pulley-preparation-1" and checked == 1 and step != 3:
                raise Rejected("Pulley preparation continuation omitted step 3")
            checked += 1
        if checked == 0:
            raise Rejected("zero Pulley pre-step branches executed")
        return {"status": "PASSED", "steps": checked}
    except (Rejected, KeyError, TypeError, ValueError) as error:
        return {"status": "FAILED", "reason": str(error)}


def certify_observed_math(key, rows):
    try:
        if not rows or rows[0].get("kind") != "inputs" or \
                not isinstance(rows[0].get("frozenInput"), dict):
            raise Rejected("source-bound math input is absent")
        initial = rows[0]["frozenInput"]["state"]
        fixtures = {fixture["id"]: fixture for body in initial["bodies"]
                    for fixture in body["fixtures"]}
        checks = {"trig": 0, "mix": 0, "area": 0, "radius": 0,
                  "stiffness": 0, "motion_change": 0, "anchors": 0}
        initial_bodies = {body["id"]: body for body in initial["bodies"]}
        local_anchors = {}
        for joint in initial["joints"]:
            anchors = []
            for index, body_id in enumerate(joint["bodies"], 1):
                transform = initial_bodies[body_id]["transform"]
                x, y = transform["getTranslation"]
                cosine, sine = transform["getCost"], transform["getSint"]
                dx = joint[f"getAnchor{index}"][0] - x
                dy = joint[f"getAnchor{index}"][1] - y
                anchors.append((cosine * dx + sine * dy,
                                -sine * dx + cosine * dy))
            local_anchors[joint["id"]] = anchors

        def snapshot_premises(snapshot):
            bodies = {body["id"]: body for body in snapshot["bodies"]}
            for joint in snapshot["joints"]:
                for index, body_id in enumerate(joint["bodies"], 1):
                    transform = bodies[body_id]["transform"]
                    x, y = transform["getTranslation"]
                    cosine, sine = transform["getCost"], transform["getSint"]
                    local_x, local_y = local_anchors[joint["id"]][index - 1]
                    expected = [x + cosine * local_x - sine * local_y,
                                y + sine * local_x + cosine * local_y]
                    actual = joint[f"getAnchor{index}"]
                    if len(actual) != 2 or any(abs(_number(actual[n], "joint anchor") -
                            expected[n]) > 64 * math.ulp(max(abs(expected[n]), 1.0))
                            for n in range(2)):
                        raise Rejected("joint anchor target math premise differs")
                    checks["anchors"] += 1
                    if "getCurrentLength1" in joint:
                        pulley = joint[f"getPulleyAnchor{index}"]
                        distance = math.hypot(actual[0] - pulley[0], actual[1] - pulley[1])
                        measured = _number(joint[f"getCurrentLength{index}"],
                                           "Pulley segment length")
                        if abs(measured - distance) > \
                                64 * math.ulp(max(abs(distance), 1.0)):
                            raise Rejected("Pulley segment target math premise differs")

        def visit(value, listener=None):
            if isinstance(value, list):
                for child in value:
                    visit(child, listener)
            elif isinstance(value, dict):
                if {"getCost", "getSint", "getRotationAngle"} <= value.keys():
                    cost = _number(value["getCost"], "stored cosine")
                    sine = _number(value["getSint"], "stored sine")
                    angle = _number(value["getRotationAngle"], "source angle")
                    if abs(angle) > math.pi or abs(cost) > 1 or abs(sine) > 1 or \
                            abs(cost * cost + sine * sine - 1) > 64 * math.ulp(1.0) or \
                            abs(math.cos(angle) - cost) > 64 * math.ulp(1.0) or \
                            (angle > 0 and sine < 0) or (angle < 0 and sine >= 0):
                        raise Rejected("stored trig target math premise differs")
                    checks["trig"] += 1
                if "getArea" in value and "type" in value and \
                        value["type"] in ("org.dyn4j.geometry.Circle",
                                          "org.dyn4j.geometry.Rectangle"):
                    if value["type"].endswith("Circle"):
                        radius = _number(value["getRadius"], "circle radius")
                        expected = math.pi * radius * radius
                    else:
                        expected = value["getWidth"] * value["getHeight"]
                        radius = math.hypot(value["getWidth"] / 2,
                                            value["getHeight"] / 2)
                        if abs(_number(value["getRadius"], "shape radius") - radius) > \
                                64 * math.ulp(max(abs(radius), 1.0)):
                            raise Rejected("shape radius target math premise differs")
                        checks["radius"] += 1
                    if abs(_number(value["getArea"], "shape area") - expected) > \
                            64 * math.ulp(max(abs(expected), 1.0)):
                        raise Rejected("shape area target math premise differs")
                    checks["area"] += 1
                if "constraint" in value and "fixture1" in value and "fixture2" in value:
                    constraint = value["constraint"]
                    if isinstance(constraint, dict) and "getFriction" in constraint:
                        first = fixtures[value["fixture1"]]["getFriction"]
                        second = fixtures[value["fixture2"]]["getFriction"]
                        expected = math.sqrt(first * second)
                        observed = _number(constraint["getFriction"], "mixed friction")
                        initial_constraint = listener == "CollisionListener" and observed == 0.2
                        if not initial_constraint and abs(observed - expected) > \
                                64 * math.ulp(max(abs(expected), 1.0)):
                            raise Rejected("friction mix target math premise differs")
                        checks["mix"] += 1
                if "getSpringStiffness" in value:
                    stiffness = _number(value["getSpringStiffness"], "spring stiffness")
                    if stiffness != 0:
                        bodies = value["bodies"]
                        by_id = {body["id"]: body for body in initial["bodies"]}
                        inverse = sum(by_id[body_id]["properties"]["getMass"]
                                      ["getInverseInertia"] for body_id in bodies)
                        frequency = value["getSpringFrequency"]
                        expected = (1 / inverse) * (2 * math.pi * frequency) ** 2
                        if abs(stiffness - expected) > \
                                64 * math.ulp(max(abs(expected), 1.0)):
                            raise Rejected("spring stiffness target math premise differs")
                        checks["stiffness"] += 1
                if "getChangeInPosition" in value and "getChangeInOrientation" in value:
                    checks["motion_change"] += 1
                for child in value.values():
                    visit(child, listener)

        for row in rows:
            if row.get("kind") == "inputs":
                snapshot_premises(row["frozenInput"]["state"])
                visit(row["frozenInput"]["state"])
            elif row.get("kind") == "state":
                snapshot_premises(row["frozenState"])
                visit(row["frozenState"])
            elif row.get("kind") == "event":
                event = row["frozenEvent"]
                visit(event.get("payload", []), event.get("listener"))
        if not checks["trig"] or not checks["area"] or not checks["radius"] or \
                not checks["anchors"]:
            raise Rejected("observed target math coverage is incomplete")
        if key == "weld-enabled-equal" and not checks["stiffness"]:
            raise Rejected("Weld stiffness target math coverage is absent")
        if key != "weld-enabled-equal" and not checks["motion_change"]:
            raise Rejected("Pulley motion-change target math coverage is absent")
        return {"status": "UNPASSED_TARGET_MATH_EVIDENCE",
                "reason": "same-process target operation evidence is absent",
                "surrogate_status": "CONSISTENT", "observed_checks": checks}
    except (Rejected, KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        return {"status": "UNPASSED_PREMISE", "reason": str(error)}


def verify_baseline_producer(root, key, attestation=None):
    if root is None:
        raise Rejected("verified baseline producer receipt is absent")
    root = Path(root)
    if attestation is None:
        raise Rejected("current baseline XML/process attestation is absent")
    from baseline_capture import verify_attestation
    verified_process = verify_attestation(root, attestation)
    verified = json.loads((root / "verified.json").read_text())
    if verified.get("status") != "CAPTURED_WITH_FAILED_ANGLE_PHYSICAL" or \
            verified.get("baseline_source_revision") != \
            "058bf6d982a0fb89b54050f929f6ea9dae53b714" or \
            verified.get("baseline_jar_sha256") != \
            "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e":
        raise Rejected("pinned baseline source or artifact receipt differs")
    jar = root / "dyn4j-6.0.0.jar"
    if hashlib.sha256(jar.read_bytes()).hexdigest() != verified["baseline_jar_sha256"]:
        raise Rejected("baseline JAR bytes differ")
    case = root / "baseline-jvm/cases" / {
        "weld-enabled-equal": "P-JINT-Weld-enabled-equal",
        "pulley-preparation-0": "P-JINT-Pulley-slack-transition-preparation-0",
        "pulley-preparation-1": "P-JINT-Pulley-slack-transition-preparation-1",
        "pulley-slack-transition": "P-JINT-Pulley-slack-transition-main"}[key]
    case = case.with_suffix(".jsonl")
    if hashlib.sha256(case.read_bytes()).hexdigest() != \
            verified["case_sha256"][case.stem]:
        raise Rejected("baseline producer case hash differs")
    predecessor = {"pulley-preparation-1":
                   "P-JINT-Pulley-slack-transition-preparation-0",
                   "pulley-slack-transition":
                   "P-JINT-Pulley-slack-transition-preparation-1"}.get(key)
    if predecessor is not None:
        prior = root / "baseline-jvm/cases" / f"{predecessor}.jsonl"
        if hashlib.sha256(prior.read_bytes()).hexdigest() != \
                verified["case_sha256"][predecessor]:
            raise Rejected("baseline predecessor case hash differs")
    from baseline_capture import fixture_source_sha256
    from run import git
    if fixture_source_sha256() != verified.get("fixture_source_sha256") or \
            hashlib.sha256(git("archive", "--format=tar",
                               verified["candidate_recorder_commit"])).hexdigest() != \
            verified.get("source_sha256"):
        raise Rejected("baseline recorder source binding differs")
    runtime = verified.get("runtime", {})
    executable = Path(runtime.get("executable", ""))
    if not executable.is_file() or hashlib.sha256(executable.read_bytes()).hexdigest() != \
            runtime.get("executable_sha256") or runtime.get("method_executions") != 15:
        raise Rejected("baseline producer runtime/process receipt differs")
    return {"case_sha256": verified["case_sha256"][case.stem],
            "source_sha256": verified["source_sha256"],
            "recorder_commit": verified["candidate_recorder_commit"],
            "runtime_sha256": runtime["executable_sha256"],
            "attestation_sha256": hashlib.sha256(Path(attestation).read_bytes()).hexdigest(),
            "method_processes_verified": verified_process["method_processes_verified"]}


def compare_case(key, reference, candidate, previous_reference=None, previous_candidate=None,
                 reference_producer=None, baseline_root=None, baseline_attestation=None):
    if key not in KEYS:
        return {"fixture_key": key, "status": "FAILED", "reason": "unknown Weld/Pulley case"}
    fixture = next(item for item in json.loads(CATALOG.read_text())["fixtures"] if item["key"] == key)
    if hashlib.sha256(Path(reference).read_bytes()).hexdigest() != fixture["reference"]["gzip_sha256"]:
        return {"fixture_key": key, "status": "FAILED", "reason": "frozen reference hash differs"}
    try:
        with gzip.open(reference, "rb") as stream:
            first = stream.readline().rstrip(b"\n")
        if hashlib.sha256(first).hexdigest() != fixture["reference"]["input_sha256"]:
            raise Rejected("frozen input hash differs")
        raw = list(records(candidate, allow_tagged_nonfinite=False))
        compared = compare_records(key, reference_records(reference),
                                   projected_records(candidate), require_coverage=True)
        if compared["status"] == "FAILED":
            return {"fixture_key": key, **compared, "qualification": "UNPASSED"}
        expected = fixture["counts"]
        actual = {}
        for row in reference_records(reference):
            kind = row["kind"]
            actual[kind] = actual.get(kind, 0) + 1
        if actual != expected:
            raise Rejected(f"frozen case counts differ: {key}")
        if not raw or raw[0].get("kind") != "inputs" or raw[-1].get("kind") != "case-end":
            raise Rejected("portable case has no input or completion receipt")
        if raw[-1].get("steps") != fixture["counts"]["state"]:
            raise Rejected("portable case executed state count differs")
        if key in ("pulley-preparation-1", "pulley-slack-transition"):
            if reference_producer is None or previous_reference is None or \
                    previous_candidate is None:
                return {"fixture_key": key, "status": "UNPASSED_CHAINING",
                        "reason": "complete reference and candidate post-action sources are absent",
                        "comparison": compared, "qualification": "UNPASSED"}
            reference_rows = list(records(reference_producer))
            previous_reference_rows = list(records(previous_reference))
            previous_candidate_rows = list(records(previous_candidate))
            expected_previous = (Path(baseline_root) / "baseline-jvm/cases" /
                ("P-JINT-Pulley-slack-transition-preparation-0.jsonl" if
                 key == "pulley-preparation-1" else
                 "P-JINT-Pulley-slack-transition-preparation-1.jsonl"))
            if Path(previous_reference).resolve() != expected_previous.resolve():
                raise Rejected("predecessor is outside verified baseline archive")
            reference_chain = verify_provider_chain(key, reference_rows,
                                                    previous_reference_rows)
            candidate_chain = verify_provider_chain(key, raw, previous_candidate_rows)
            if not _same(reference_rows[0]["frozenInput"], next(reference_records(reference))):
                raise Rejected("pinned reference producer header differs from frozen reference")
            if compared["status"] != "PASSED":
                return {"fixture_key": key, **compared, "reference_chain": reference_chain,
                        "candidate_chain": candidate_chain, "qualification": "UNPASSED"}
        elif compared["status"] != "PASSED":
            return {"fixture_key": key, **compared, "qualification": "UNPASSED"}
        if reference_producer is None:
            return {"fixture_key": key, "status": "UNPASSED_PREMISE",
                    "reason": "source-bound baseline math and branch producer is absent",
                    "records": compared["records"], "qualification": "UNPASSED"}
        producer_rows = list(records(reference_producer))
        try:
            identity = verify_baseline_producer(baseline_root, key, baseline_attestation)
        except (Rejected, OSError, KeyError, ValueError) as error:
            return {"fixture_key": key, "status": "UNPASSED_SOURCE_BINDING",
                    "reason": str(error), "qualification": "UNPASSED"}
        if Path(reference_producer).resolve() != (Path(baseline_root) /
                "baseline-jvm/cases" / Path(reference_producer).name).resolve():
            raise Rejected("baseline producer path differs from verified archive")
        producer_comparison = compare_records(key, reference_records(reference),
                                               projected_records(reference_producer),
                                               require_coverage=True)
        if producer_comparison["status"] == "FAILED":
            raise Rejected("baseline producer differs from pinned reference: " +
                           producer_comparison["reason"])
        if key.startswith("pulley-"):
            branch = compare_branches(key,
                (row for row in producer_rows if row.get("kind") == "state"),
                (row for row in raw if row.get("kind") == "state"))
            if branch["status"] != "PASSED":
                return {"fixture_key": key, **branch, "qualification": "UNPASSED"}
        math_diagnostics = {}
        for label, producer in (("reference", producer_rows), ("candidate", raw)):
            temporal = verify_temporal_state(key, producer)
            if temporal["status"] != "PASSED":
                return {"fixture_key": key, **temporal, "provider": label,
                        "qualification": "UNPASSED"}
            premise = certify_observed_math(key, producer)
            if premise["status"] != "UNPASSED_TARGET_MATH_EVIDENCE" or \
                    premise.get("surrogate_status") != "CONSISTENT":
                return {"fixture_key": key, **premise, "provider": label,
                        "qualification": "UNPASSED"}
            math_diagnostics[label] = premise
        return {"fixture_key": key, "status": "UNPASSED_TARGET_MATH_EVIDENCE",
                "reason": "same-process target operation evidence is absent",
                "records": compared["records"], "baseline_producer": identity,
                "surrogate_math": math_diagnostics,
                "qualification": "UNPASSED"}
    except (Rejected, OSError, EOFError, KeyError, TypeError, ValueError) as error:
        return {"fixture_key": key, "status": "FAILED", "reason": str(error),
                "qualification": "UNPASSED"}
