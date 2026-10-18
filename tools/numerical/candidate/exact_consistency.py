import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare
import receipt


BODY_FIELDS = {"id", "atRest", "force", "accumulatedForce", "torque", "accumulatedTorque",
               "velocity", "angularVelocity", "worldCenter", "fixedOriginPosition", "transform",
               "previousTransform", "rotationIncrementSum", "rotationStepBoundBelowPi",
               "rotationTrackingScope"}
DUPLICATES = {"getForce": "force", "getAccumulatedForce": "accumulatedForce",
              "getTorque": "torque", "getAccumulatedTorque": "accumulatedTorque",
              "getLinearVelocity": "velocity", "getAngularVelocity": "angularVelocity",
              "getTransform": "transform", "getPreviousTransform": "previousTransform",
              "getWorldCenter": "worldCenter", "isAtRest": "atRest"}
PROPERTY_FIELDS = set(DUPLICATES) | {"getAngularDamping", "getChangeInOrientation",
    "getChangeInPosition", "getFixtureCount", "getGravityScale", "getLinearDamping",
    "getLocalCenter", "getMass", "getRotationDiscRadius", "isAtRestDetectionEnabled",
    "isBullet", "isDynamic", "isEnabled", "isKinematic", "isStatic", "type"}
TRANSFORM_FIELDS = {"getCost", "getSint", "getRotationAngle", "getTranslation",
                    "getTranslationX", "getTranslationY", "getValues", "isIdentity", "type"}
TIMESTEP_FIELDS = {"getDeltaTime", "getDeltaTimeRatio", "getInverseDeltaTime",
                   "getPreviousInverseDeltaTime", "getPrevousDeltaTime", "type"}
SCHEMA = {
    "event": {"kind", "step", "order", "listener", "method", "payload"},
    "action": {"kind", "id", "step", "order", "description"},
    "instrumented-callback": {"kind", "id", "event", "step", "order", "values"},
    "outer-endpoint": {"kind", "step", "outerStep", "state"},
}
CONFIGURED_METHODS = {
    "StepListener.begin": 72000, "StepListener.updatePerformed": 1,
    "StepListener.postSolve": 72000, "StepListener.end": 72000,
    "CollisionListener.collision": 215991, "TimeOfImpactListener.collision": 14,
    "ContactListener.begin": 2, "ContactListener.collision": 71995,
    "ContactListener.preSolve": 143988, "ContactListener.postSolve": 143988,
    "ContactListener.persist": 143988,
}
KNOWN_METHODS = set(CONFIGURED_METHODS) | {"ContactListener.end"}


def require(condition, message):
    if not condition:
        raise compare.Rejected(message)


def keys(value, expected, label):
    require(type(value) is dict and set(value) == set(expected), label + " schema")


def exact(left, right, label):
    require(compare.same_value(left, right), label)


def numerical(left, right, label):
    require(type(left) in (int, float) and left == right, label)


def numeric_vector(left, right, label):
    require(type(left) is list and len(left) == len(right), label)
    for observed, expected in zip(left, right):
        numerical(observed, expected, label)


def transform(value):
    keys(value, TRANSFORM_FIELDS, "transform")
    for name in ("getCost", "getSint", "getRotationAngle", "getTranslationX", "getTranslationY"):
        require(type(value[name]) in (int, float), "transform numeric schema")
    require(type(value["isIdentity"]) is bool, "transform identity schema")
    exact(value["getTranslation"], [value["getTranslationX"], value["getTranslationY"]],
          "translation alias")
    exact(value["getValues"], [value["getCost"], -value["getSint"],
          value["getTranslationX"], value["getSint"], value["getCost"],
          value["getTranslationY"]], "matrix alias")


def snapshot(state, phase, prior=None):
    require(phase in ("initial", "step", "before", "after"), "snapshot phase")
    keys(state, {"bodies", "joints"}, "state")
    compare.finite(state)
    require(type(state["bodies"]) is list and len(state["bodies"]) == 2, "two bodies")
    exact(state["joints"], [], "no joints")
    for index, body in enumerate(state["bodies"]):
        keys(body, BODY_FIELDS if phase == "step" else BODY_FIELDS | {"properties", "fixtures"}, "body")
        require(body["id"] == f"b{index}" and type(body["atRest"]) is bool, "body identity or rest schema")
        for name in ("force", "accumulatedForce", "velocity", "worldCenter", "fixedOriginPosition"):
            require(type(body[name]) is list and len(body[name]) == 2 and
                    all(type(value) in (int, float) for value in body[name]), name + " vector schema")
        for name in ("angularVelocity", "rotationIncrementSum", "torque", "accumulatedTorque"):
            require(type(body[name]) in (int, float), name + " numeric schema")
        require(body["rotationStepBoundBelowPi"] is True and
                body["rotationTrackingScope"] ==
                "segment-only; unrecorded transform mutations invalidate", "rotation premise schema")
        for name in ("force", "accumulatedForce"):
            require(all(type(x) in (int, float) and x == 0 for x in body[name]), name + " zero")
        for name in ("torque", "accumulatedTorque"):
            numerical(body[name], 0, name + " zero")
        transform(body["transform"])
        transform(body["previousTransform"])
        exact(body["worldCenter"], body["transform"]["getTranslation"], "world center alias")
        exact(body["fixedOriginPosition"], body["worldCenter"], "fixed origin alias")
        if phase != "step":
            keys(body["properties"], PROPERTY_FIELDS, "properties")
            require(type(body["fixtures"]) is list and len(body["fixtures"]) == 1,
                    "one fixture per body")
            for getter, field in DUPLICATES.items():
                exact(body["properties"][getter], body[field], "duplicate " + getter)
            numeric_vector(body["properties"]["getLocalCenter"], [0, 0], "local center alias premise")
            numeric_vector(body["properties"]["getMass"]["getCenter"], [0, 0], "mass center alias premise")
        if index == 0:
            numeric_vector(body["transform"]["getTranslation"], [0, -0.25], "floor pose")
            for name, value in (("getCost", 1), ("getSint", 0), ("getRotationAngle", 0)):
                numerical(body["transform"][name], value, "floor rotation")
            require(all(v == 0 for v in body["velocity"]), "floor velocity")
            numerical(body["angularVelocity"], 0, "floor angular velocity")
            numerical(body["rotationIncrementSum"], 0, "floor rotation accumulator")
            exact(body["previousTransform"], body["transform"], "floor previous pose")
        if index == 1 and body["atRest"]:
            require(all(v == 0 for v in body["velocity"]), "sleep velocity")
            numerical(body["angularVelocity"], 0, "sleep angular velocity")
            if prior is not None and prior["bodies"][index]["atRest"]:
                exact(body["transform"], prior["bodies"][index]["transform"], "sleep pose freeze")
        if phase == "initial":
            exact(body["previousTransform"], body["transform"], "initial previous copy")
        else:
            require(prior is not None, "prior snapshot required")
            expected = prior["bodies"][index]["transform" if phase == "step" else "previousTransform"]
            exact(body["previousTransform"], expected, "phase-correct previous copy")
            if phase in ("before", "after"):
                exact(body["transform"], prior["bodies"][index]["transform"], "action current pose copy")


def impulse(before, after):
    pre, post = before["bodies"][1], after["bodies"][1]
    require(pre["atRest"] and pre["velocity"] == [0, 0] and pre["angularVelocity"] == 0,
            "impulse sleeping input")
    require(not post["atRest"] and post["velocity"] == [1, 0] and post["angularVelocity"] == 0,
            "impulse immediate output")
    expected = copy.deepcopy(before)
    moving = expected["bodies"][1]
    moving["atRest"] = False
    moving["velocity"] = [1, 0]
    moving["properties"]["isAtRest"] = False
    moving["properties"]["getLinearVelocity"] = [1, 0]
    exact(after, expected, "impulse unchanged fields")


def timestep(value, hz, step):
    keys(value, TIMESTEP_FIELDS, "TimeStep")
    require(value["type"] == "org.dyn4j.dynamics.TimeStep", "TimeStep type")
    old = 1 / 60 if step == 1 else 1 / hz
    for key, expected in {"getDeltaTime": 1 / hz, "getInverseDeltaTime": hz,
                          "getPrevousDeltaTime": old, "getPreviousInverseDeltaTime": 1 / old,
                          "getDeltaTimeRatio": (1 / hz) / old}.items():
        numerical(value[key], expected, "timestep " + key)


def fixed_callback_payload(payload):
    if type(payload) is dict:
        compare.check_fixed_body_callback_velocities(payload, {"callback_fixed_body_id": "b0"})


def endpoint(row, last, outer_hz, group):
    keys(row, SCHEMA["outer-endpoint"], "outer-endpoint")
    require(type(row["step"]) is int and type(row["outerStep"]) is int,
            "endpoint index schema")
    require(last is not None and last["step"] % group == 0, "endpoint phase")
    require(row["step"] == last["step"] and row["outerStep"] == last["step"] // group,
            "endpoint index")
    exact(row["state"], last["state"], "endpoint numeric copy")


def audit_trace(path, fixture):
    key = fixture["key"]
    configured = key.startswith("configured-")
    require(configured or key.startswith("default-sleep-"), "sleep/wake fixture required")
    outer_hz = int(key.split("-")[1 if configured else 2])
    require(outer_hz in (30, 60, 120), "outer Hz")
    hz = 120 if configured else outer_hz
    group = 120 // outer_hz if configured else 1
    expected_states = 72000 if configured else 600 * hz
    action_step = 36001 if configured else 300 * hz + 1
    coverage = Counter()
    counts = Counter()
    listeners = Counter()
    methods = Counter()
    digest = hashlib.sha256()
    input_hash = None
    prior = before = last = None
    pending = False
    states = ordered_step = order = action_phase = 0
    lifecycle = []
    for line, row in compare.records(path):
        digest.update(line)
        kind = row.get("kind")
        require(kind in fixture["counts"], "unrecognized record kind")
        counts[kind] += 1
        require(counts[kind] <= fixture["counts"][kind], "duplicate or excess " + kind)
        if pending:
            require(kind == "outer-endpoint", "missing endpoint")
        if kind == "inputs":
            expected = {"dt", "id", "kind", "origin", "scale", "settings", "state", "steps", "world"}
            keys(row, expected | ({"grouping"} if configured else set()), "inputs")
            require(sum(counts.values()) == 1 and row["id"] == fixture["id"], "input identity or order")
            input_hash = hashlib.sha256(line[:-1]).hexdigest()
            require(input_hash == fixture["reference"]["input_sha256"], "frozen input identity")
            numerical(row["dt"], 1 / hz, "input dt")
            require(type(row["steps"]) is int and row["steps"] == expected_states,
                    "input steps")
            if configured:
                keys(row["grouping"], {"actionInnerStep", "innerPerOuter", "outerDt",
                                      "outerHz", "outerSteps", "repetition"}, "grouping")
                require(all(type(row["grouping"][name]) is int for name in
                            ("innerPerOuter", "outerHz", "outerSteps", "repetition", "actionInnerStep")),
                        "grouping integer schema")
                require(row["grouping"]["innerPerOuter"] == group and
                        row["grouping"]["outerHz"] == outer_hz and
                        row["grouping"]["outerSteps"] == 600 * outer_hz and
                        row["grouping"]["actionInnerStep"] == action_step,
                        "grouping identity")
                numerical(row["grouping"]["outerDt"], 1 / outer_hz, "outer dt")
            snapshot(row["state"], "initial")
            prior = row["state"]
            coverage["initial"] += 1
            continue
        require(counts["inputs"] == 1, "inputs first")
        if kind == "outer-endpoint":
            require(pending, "unexpected endpoint")
            endpoint(row, last, outer_hz, group)
            coverage["endpoints"] += 1
            pending = False
            continue
        require(type(row.get("step")) is int, "record step schema")
        require(row["step"] == states + 1, "record step")
        if kind != "state":
            keys(row, SCHEMA[kind], kind)
            require(type(row["order"]) is int, "record order schema")
            if ordered_step != row["step"]:
                ordered_step, order = row["step"], 0
            require(row["order"] == order, "record order")
            order += 1
        if kind == "instrumented-callback":
            require(row["step"] == action_step and row["id"] == fixture["id"] and
                    type(row["values"]) is list and len(row["values"]) == 1,
                    "action snapshot identity")
            phase = {"before-wake": "before", "after-wake": "after"}.get(row["event"])
            require(phase is not None and action_phase == (0 if phase == "before" else 2)
                    and row["order"] == (0 if phase == "before" else 2), "action phase")
            value = row["values"][0]
            snapshot(value, phase, prior)
            coverage[phase] += 1
            if phase == "before":
                before, action_phase = value, 1
            else:
                impulse(before, value)
                prior, action_phase = value, 3
                coverage["impulse"] += 1
        elif kind == "action":
            require(row["step"] == action_step and row["order"] == 1 and action_phase == 1
                    and row["id"] == fixture["id"] and row["description"] ==
                    "impulse=(1,0) at center; sleepingBefore=true; precedingSecondAsleep=true",
                    "action identity or order")
            action_phase = 2
        elif kind == "event":
            if row["step"] == action_step:
                require(action_phase == 3, "callbacks before completed action")
            require(row["listener"] in {"StepListener", "ContactListener", "CollisionListener",
                    "TimeOfImpactListener", "DestructionListener", "BoundsListener"}, "listener identity")
            method = re.search(r"\.([^.( ]+)\(", row["method"])
            require(method is not None, "listener method")
            name = f"{row['listener']}.{method.group(1)}"
            require(name in KNOWN_METHODS, "unrecognized listener method")
            require(type(row["payload"]) is list, "event payload schema")
            for payload in row["payload"]:
                fixed_callback_payload(payload)
            listeners[row["listener"]] += 1
            methods[name] += 1
            if row["listener"] == "StepListener":
                require(type(row["payload"]) is list and len(row["payload"]) == 2 and
                        row["payload"][1] == {"world": fixture["id"]}, "StepListener payload")
                timestep(row["payload"][0], hz, row["step"])
                coverage["timestep"] += 1
                lifecycle.append(method.group(1))
        elif kind == "state":
            keys(row, {"kind", "step", "state"} |
                 ({"outerStep", "innerWithinOuter"} if configured else set()), "state")
            if row["step"] == action_step:
                require(action_phase == 3, "state before completed action")
            require(lifecycle == (["begin", "updatePerformed", "postSolve", "end"] if states == 0
                                  else ["begin", "postSolve", "end"]), "ordered step lifecycle")
            lifecycle = []
            if configured:
                require(type(row["outerStep"]) is int and
                        type(row["innerWithinOuter"]) is int, "inner phase schema")
                require(row["outerStep"] == states // group + 1 and
                        row["innerWithinOuter"] == states % group + 1, "inner phase index")
            snapshot(row["state"], "step", prior)
            states += 1
            coverage["inner"] += 1
            if row["state"]["bodies"][1]["atRest"]:
                coverage["sleepingStates"] += 1
                if prior["bodies"][1]["atRest"]:
                    coverage["sleepPoseComparisons"] += 1
            prior, last = row["state"], row
            pending = configured and states % group == 0
    require(not pending and not lifecycle, "incomplete endpoint or lifecycle")
    require(states == expected_states and dict(counts) == fixture["counts"], "incomplete counts")
    require(coverage["initial"] == coverage["before"] == coverage["after"] ==
            coverage["impulse"] == 1, "action coverage")
    require(coverage["timestep"] == 3 * states + 1, "timestep coverage")
    require(coverage["endpoints"] == (600 * outer_hz if configured else 0), "endpoint coverage")
    require(coverage["sleepingStates"] > 0 and coverage["sleepPoseComparisons"] > 0,
            "sleep coverage")
    if configured:
        require(dict(methods) == CONFIGURED_METHODS, "configured listener method counts")
    return {"fixture": key, "coverage": dict(coverage), "counts": dict(counts),
            "listeners": dict(listeners), "methods": dict(methods),
            "input_sha256": input_hash, "stream_sha256": digest.hexdigest()}


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_set_hash(paths, root=None):
    paths = [Path(path) for path in paths]
    require(paths and all(path.is_file() for path in paths), "recorder files unavailable")
    digest = hashlib.sha256()
    for path in sorted(paths):
        name = str(path.relative_to(root) if root else path.name).encode()
        content = path.read_bytes()
        digest.update(name + b"\0" + str(len(content)).encode() + b"\0" + content)
    return digest.hexdigest()


def recorder_sources(fixture):
    folder = "configured" if fixture["key"].startswith("configured-") else "default"
    root = Path(__file__).resolve().parent
    return sorted((root / folder).glob("*.java")) + [root / "runtime" / "RuntimeStamp.java"]


def source_archive(commit):
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "source revision")
    process = subprocess.Popen(["git", "archive", "--format=tar", commit], stdout=subprocess.PIPE)
    digest = hashlib.sha256()
    for block in iter(lambda: process.stdout.read(1024 * 1024), b""):
        digest.update(block)
    require(process.wait() == 0, "source archive unavailable")
    return digest.hexdigest()


def identity(trace, artifact, commit, sources):
    artifact = Path(artifact).resolve()
    trace = Path(trace).resolve()
    stamp = trace.parent / "runtime.json"
    runtime = compare.parse(stamp.read_bytes())
    keys(runtime, receipt.RUNTIME_FIELDS, "runtime stamp")
    require(all(type(value) is str and value for value in runtime.values()), "runtime stamp values")
    loaded = urlparse(runtime["engine_location"])
    require(loaded.scheme == "file" and loaded.netloc in ("", "localhost"), "loaded engine URL")
    require(Path(unquote(loaded.path)).resolve() == artifact, "loaded engine artifact path")
    binary = Path(runtime["process_command"])
    require(binary.is_file(), "runtime process executable")
    recorder_url = urlparse(runtime["recorder_location"])
    require(recorder_url.scheme == "file" and recorder_url.netloc in ("", "localhost"),
            "recorder code URL")
    classes = Path(unquote(recorder_url.path))
    require(classes.is_dir(), "recorder classes unavailable")
    return {"source_commit": commit, "source_archive_sha256": source_archive(commit),
            "artifact_path": str(artifact), "artifact_sha256": file_hash(artifact),
            "recorder_source_sha256": file_set_hash(sources),
            "recorder_classes_sha256": file_set_hash(classes.rglob("*.class"), classes),
            "process_sha256": file_hash(binary), "runtime_stamp_sha256": file_hash(stamp),
            "runtime": runtime, "trace_sha256": file_hash(trace)}


def verify_binding(expected, actual):
    require(type(expected) is dict and expected == actual, "stale or altered identity")


def main():
    parser = argparse.ArgumentParser(description="Audit six approved same-run groups")
    parser.add_argument("mode", choices=("seal", "verify", "reference"))
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--artifact")
    parser.add_argument("--source-commit")
    parser.add_argument("--identity")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        fixture = receipt.load_fixture(args.fixture, Path(__file__).resolve().parents[1] / "fixtures.json")
        result = audit_trace(args.trace, fixture)
        result["trace_sha256"] = file_hash(args.trace)
        result["checker_sha256"] = file_hash(__file__)
        if args.mode == "reference":
            expected = fixture["reference"]
            require(result["trace_sha256"] == expected["gzip_sha256"] and
                    result["stream_sha256"] == expected["stream_sha256"], "frozen reference hashes")
            result["source_commit"] = fixture["baseline_source_revision"]
            result["artifact_sha256"] = fixture["baseline_jar_sha256"]
        else:
            require(args.artifact and args.source_commit and args.identity, "candidate identity arguments")
            bound = identity(args.trace, args.artifact, args.source_commit,
                             recorder_sources(fixture))
            result.update(bound)
            if args.mode == "seal":
                with Path(args.identity).open("x") as stream:
                    json.dump(result, stream, indent=2, sort_keys=True)
                    stream.write("\n")
            else:
                verify_binding(compare.parse(Path(args.identity).read_bytes()), result)
        result["status"] = "SAME_RUN_PASSED"
        if args.output:
            with Path(args.output).open("x") as stream:
                json.dump(result, stream, indent=2, sort_keys=True)
                stream.write("\n")
    except (compare.Rejected, OSError, ValueError, KeyError, TypeError) as error:
        result = {"status": "SAME_RUN_FAILED", "reason": str(error)}
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "SAME_RUN_PASSED" else 1)


if __name__ == "__main__":
    main()
