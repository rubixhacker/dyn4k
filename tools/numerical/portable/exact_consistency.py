import copy
import math
import re

from receipt import Rejected


TRANSFORM_FIELDS = {"getCost", "getSint", "getRotationAngle", "getTranslation",
                    "getTranslationX", "getTranslationY", "getValues", "isIdentity", "type"}
DUPLICATES = {"getForce": "force", "getAccumulatedForce": "accumulatedForce",
              "getTorque": "torque", "getAccumulatedTorque": "accumulatedTorque",
              "getLinearVelocity": "velocity", "getAngularVelocity": "angularVelocity",
              "getTransform": "transform", "getPreviousTransform": "previousTransform",
              "getWorldCenter": "worldCenter", "isAtRest": "atRest"}
BODY_FIELDS = {"id", "atRest", "force", "accumulatedForce", "torque",
               "accumulatedTorque", "velocity", "angularVelocity", "worldCenter",
               "fixedOriginPosition", "transform", "previousTransform",
               "rotationIncrementSum", "rotationStepBoundBelowPi", "rotationTrackingScope"}
PROPERTY_FIELDS = set(DUPLICATES) | {"getAngularDamping", "getChangeInOrientation",
    "getChangeInPosition", "getFixtureCount", "getGravityScale", "getLinearDamping",
    "getLocalCenter", "getMass", "getRotationDiscRadius", "isAtRestDetectionEnabled",
    "isBullet", "isDynamic", "isEnabled", "isKinematic", "isStatic", "type"}
TIMESTEP_FIELDS = {"getDeltaTime", "getDeltaTimeRatio", "getInverseDeltaTime",
                   "getPreviousInverseDeltaTime", "getPrevousDeltaTime", "type"}


def require(condition, reason):
    if not condition:
        raise Rejected(reason)


def same(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if type(left) in (int, float) or type(right) in (int, float):
        return (type(left) in (int, float) and type(right) in (int, float) and
                math.isfinite(left) and math.isfinite(right) and left == right)
    if isinstance(left, dict) or isinstance(right, dict):
        return (isinstance(left, dict) and isinstance(right, dict) and
                left.keys() == right.keys() and
                all(same(left[key], right[key]) for key in left))
    if isinstance(left, list) or isinstance(right, list):
        return (isinstance(left, list) and isinstance(right, list) and
                len(left) == len(right) and
                all(same(a, b) for a, b in zip(left, right)))
    return type(left) is type(right) and left == right


def finite(value, path="snapshot"):
    if type(value) in (int, float):
        require(math.isfinite(value), f"nonfinite {path}")
    elif isinstance(value, dict):
        for key, child in value.items():
            finite(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            finite(child, f"{path}[{index}]")


def fields(value, expected, label):
    require(isinstance(value, dict) and value.keys() == expected,
            f"{label} schema")


def equal(left, right, label):
    require(same(left, right), label)


def transform_aliases(transform):
    fields(transform, TRANSFORM_FIELDS, "transform")
    require(type(transform["getRotationAngle"]) in (int, float) and
            isinstance(transform["isIdentity"], bool), "transform schema")
    equal(transform["getTranslation"],
          [transform["getTranslationX"], transform["getTranslationY"]],
          "translation alias")
    equal(transform["getValues"],
          [transform["getCost"], -transform["getSint"], transform["getTranslationX"],
           transform["getSint"], transform["getCost"], transform["getTranslationY"]],
          "matrix alias")


def check_snapshot(state, phase, prior=None):
    require(phase in ("initial", "step", "before", "after"), "snapshot phase")
    fields(state, {"bodies", "joints"}, "state")
    finite(state)
    require(len(state["bodies"]) == 2, "two bodies")
    equal(state["joints"], [], "no joints")
    for index, body in enumerate(state["bodies"]):
        fields(body, BODY_FIELDS if phase == "step" else
               BODY_FIELDS | {"properties", "fixtures"}, "body")
        equal(body["id"], f"b{index}", "body identity")
        require(isinstance(body["atRest"], bool), "atRest schema")
        require(type(body["rotationIncrementSum"]) in (int, float),
                "rotation accumulator schema")
        require(type(body["angularVelocity"]) in (int, float),
                "angular velocity schema")
        require(isinstance(body["velocity"], list) and len(body["velocity"]) == 2 and
                all(type(value) in (int, float) for value in body["velocity"]),
                "velocity schema")
        for field, target in (("force", [0, 0]), ("accumulatedForce", [0, 0]),
                              ("torque", 0), ("accumulatedTorque", 0)):
            equal(body[field], target, f"{field} zero")
        transform_aliases(body["transform"])
        transform_aliases(body["previousTransform"])
        equal(body["worldCenter"], body["transform"]["getTranslation"],
              "world center alias")
        equal(body["fixedOriginPosition"], body["worldCenter"],
              "fixed origin alias")
        if phase != "step":
            require(isinstance(body["fixtures"], list) and len(body["fixtures"]) == 1,
                    "snapshot fixtures")
            properties = body["properties"]
            fields(properties, PROPERTY_FIELDS, "properties")
            for getter, source in DUPLICATES.items():
                equal(properties[getter], body[source], f"duplicate {getter}")
            equal(properties["getLocalCenter"], [0, 0], "local center alias premise")
            equal(properties["getMass"]["getCenter"], [0, 0],
                  "mass center alias premise")
        if index == 0:
            equal(body["transform"]["getTranslation"], [0, -0.25], "floor pose")
            equal([body["transform"]["getCost"], body["transform"]["getSint"],
                   body["transform"]["getRotationAngle"]], [1, 0, 0],
                  "floor rotation")
            equal(body["velocity"], [0, 0], "floor velocity")
            equal(body["angularVelocity"], 0, "floor angular velocity")
            equal(body["rotationIncrementSum"], 0, "floor rotation accumulator")
            equal(body["previousTransform"], body["transform"],
                  "floor previous pose")
        if index == 1 and body["atRest"]:
            equal(body["velocity"], [0, 0], "sleep velocity")
            equal(body["angularVelocity"], 0, "sleep angular velocity")
            if prior is not None and prior["bodies"][1]["atRest"]:
                equal(body["transform"], prior["bodies"][1]["transform"],
                      "sleep pose freeze")
        if phase == "initial":
            equal(body["previousTransform"], body["transform"],
                  "initial previous copy")
        else:
            require(prior is not None, "prior snapshot required")
            earlier = prior["bodies"][index]
            equal(body["previousTransform"],
                  earlier["transform"] if phase == "step" else earlier["previousTransform"],
                  "phase-correct previous copy")
            if phase in ("before", "after"):
                equal(body["transform"], earlier["transform"],
                      "action current pose copy")


def check_impulse(before, after):
    finite(before)
    finite(after)
    first, second = before["bodies"][1], after["bodies"][1]
    equal([first["atRest"], first["velocity"], first["angularVelocity"]],
          [True, [0, 0], 0], "impulse sleeping input")
    equal([second["atRest"], second["velocity"], second["angularVelocity"]],
          [False, [1, 0], 0], "impulse immediate output")
    expected = copy.deepcopy(before)
    body = expected["bodies"][1]
    body["atRest"] = False
    body["velocity"] = [1, 0]
    body["properties"]["isAtRest"] = False
    body["properties"]["getLinearVelocity"] = [1, 0]
    equal(after, expected, "impulse unchanged fields")


def check_time_step(value, hz, step):
    require(hz in (30, 60, 120) and type(step) is int and step >= 1,
            "timestep scope")
    fields(value, TIMESTEP_FIELDS, "timestep")
    equal(value["type"], "org.dyn4j.dynamics.TimeStep", "timestep type")
    old = 1 / 60 if step == 1 else 1 / hz
    for key, expected in (("getDeltaTime", 1 / hz), ("getInverseDeltaTime", hz),
                          ("getPrevousDeltaTime", old),
                          ("getPreviousInverseDeltaTime", 1 / old),
                          ("getDeltaTimeRatio", (1 / hz) / old)):
        equal(value[key], expected, f"timestep {key}")


def check_endpoint(endpoint, inner, outer_hz):
    fields(endpoint, {"kind", "outerStep", "state", "step"}, "endpoint")
    group = 120 // outer_hz
    require(endpoint["kind"] == "outer-endpoint" and inner["step"] % group == 0 and
            endpoint["step"] == inner["step"] and
            endpoint["outerStep"] == inner["step"] // group and
            same(endpoint["state"], inner["state"]), "endpoint numeric copy")


def audit_rows(rows, case_id, outer_hz, configured):
    require(outer_hz in (30, 60, 120), "unsupported exact-consistency rate")
    inner_hz = 120 if configured else outer_hz
    group = 120 // outer_hz if configured else None
    expected_states = 72000 if configured else 600 * outer_hz
    action_step = 36001 if configured else 300 * outer_hz + 1
    coverage = {"initial": 0, "inner": 0, "before": 0, "after": 0,
                "impulse": 0, "timestep": 0, "endpoints": 0,
                "sleeping_states": 0, "sleep_pose_comparisons": 0}
    counts = {}
    prior = None
    before = None
    last = None
    states = 0
    ordered_step = 0
    order = 0
    action_phase = 0
    pending_endpoint = False
    lifecycle = []
    for row in rows:
        finite(row, "record")
        kind = row["kind"]
        counts[kind] = counts.get(kind, 0) + 1
        if pending_endpoint:
            require(kind == "outer-endpoint", "missing endpoint")
        if kind == "inputs":
            require(counts[kind] == 1 and states == 0, "one initial snapshot")
            equal(row["id"], case_id, "configured input identity")
            equal(row["dt"], 1 / inner_hz, "input timestep")
            equal(row["steps"], expected_states, "input state count")
            if configured:
                grouping = row["grouping"]
                equal(grouping["innerPerOuter"], group, "configured grouping")
                equal(grouping["outerHz"], outer_hz, "configured outer rate")
            else:
                require("grouping" not in row, "unexpected default grouping")
            check_snapshot(row["state"], "initial")
            prior = row["state"]
            coverage["initial"] += 1
            continue
        require(coverage["initial"] == 1, "inputs first")
        if kind == "outer-endpoint":
            require(pending_endpoint and configured, "unexpected endpoint")
            check_endpoint(row, last, outer_hz)
            coverage["endpoints"] += 1
            pending_endpoint = False
            continue
        equal(row["step"], states + 1, "record step")
        if ordered_step != row["step"]:
            ordered_step = row["step"]
            order = 0
        if kind != "state":
            equal(row["order"], order, "record order")
            order += 1
        if kind == "instrumented-callback":
            equal(row["step"], action_step, "action callback step")
            require(len(row["values"]) == 1, "action callback values")
            phase = {"before-wake": "before", "after-wake": "after"}.get(row["event"])
            require(phase is not None, "known action callback")
            equal(action_phase, 0 if phase == "before" else 2, "action callback order")
            equal(row["order"], 0 if phase == "before" else 2,
                  "action callback position")
            check_snapshot(row["values"][0], phase, prior)
            coverage[phase] += 1
            if phase == "before":
                before = row["values"][0]
                action_phase = 1
            else:
                check_impulse(before, row["values"][0])
                coverage["impulse"] += 1
                prior = row["values"][0]
                action_phase = 3
        elif kind == "action":
            equal(row["step"], action_step, "action step")
            equal(row["order"], 1, "action order")
            equal(action_phase, 1, "before/action/after sequence")
            equal(row["description"],
                  "impulse=(1,0) at center; sleepingBefore=true; precedingSecondAsleep=true",
                  "action identity")
            action_phase = 2
        elif kind == "event":
            if row["step"] == action_step:
                equal(action_phase, 3, "action before physics callbacks")
            if row["listener"] == "StepListener":
                require(len(row["payload"]) == 2, "step listener payload")
                equal(row["payload"][1], {"world": case_id},
                      "step listener world")
                check_time_step(row["payload"][0], inner_hz, row["step"])
                coverage["timestep"] += 1
                found = re.search(r"\.([^. (]+)\(", row["method"])
                require(found is not None, "step listener method")
                lifecycle.append(found.group(1))
        elif kind == "state":
            if row["step"] == action_step:
                equal(action_phase, 3, "complete action before physics state")
            equal(lifecycle, ["begin", "updatePerformed", "postSolve", "end"]
                  if row["step"] == 1 else ["begin", "postSolve", "end"],
                  "complete ordered step lifecycle")
            lifecycle = []
            states += 1
            if configured:
                equal(row["outerStep"], (states - 1) // group + 1,
                      "outer step grouping")
                equal(row["innerWithinOuter"], (states - 1) % group + 1,
                      "inner step grouping")
            else:
                require("outerStep" not in row and "innerWithinOuter" not in row,
                        "unexpected default grouping")
            check_snapshot(row["state"], "step", prior)
            coverage["inner"] += 1
            if row["state"]["bodies"][1]["atRest"]:
                coverage["sleeping_states"] += 1
                if prior["bodies"][1]["atRest"]:
                    coverage["sleep_pose_comparisons"] += 1
            prior = row["state"]
            last = row
            pending_endpoint = configured and states % group == 0
        else:
            raise Rejected(f"unclassified exact-consistency record {kind}")
    require(not pending_endpoint, "missing final endpoint")
    equal(states, expected_states, "complete inner states")
    equal(coverage["initial"], 1, "initial coverage")
    equal([coverage["before"], coverage["after"], coverage["impulse"]],
          [1, 1, 1], "wake action coverage")
    equal(coverage["timestep"], 3 * expected_states + 1,
          "timestep coverage")
    equal(coverage["endpoints"], 600 * outer_hz if configured else 0,
          "endpoint coverage")
    require(coverage["sleeping_states"] > 0 and
            coverage["sleep_pose_comparisons"] > 0, "sleep coverage")
    return {"status": "PASSED", "case_id": case_id, "outer_hz": outer_hz,
            "profile": "configured" if configured else "default",
            "groups": {name: "PASSED" for name in (
                "fixed_floor", "zero_applied_force", "sleep_velocity_and_own_run_pose",
                "immediate_center_impulse", "aliases_previous_copies_and_duplicates",
                "timestep_metadata")},
            "coverage": coverage, "counts": counts,
            "qualification": "UNPASSED"}


def audit_trace(trace, case_id, outer_hz, configured):
    from reference_diagnostic import projected_records
    try:
        return audit_rows(projected_records(trace), case_id, outer_hz, configured)
    except (Rejected, OSError, EOFError, KeyError, IndexError, TypeError, ValueError) as error:
        return {"status": "FAILED", "case_id": case_id, "outer_hz": outer_hz,
                "profile": "configured" if configured else "default",
                "reason": str(error), "qualification": "UNPASSED"}
