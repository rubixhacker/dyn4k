#!/usr/bin/env python3
"""Records the golden vectors the `:numerical` TestBalloon suites replay.

Run from a checkout whose `tools/numerical` Python modules are present:

    python3 tools/harness/numerical/parity/generate_vectors.py

The script writes one Kotlin constant file per suite under
`src/commonTest/kotlin/io/github/rubixhacker/harness/numerical/`. Each file records the revision it
was generated from. Re-running it rewrites those files; review the diff before committing.
"""
import base64
import fractions as _fractions
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path("/var/home/stewart/Workspace/dyn4k")
PORTABLE = REPO / "tools/numerical/portable"
sys.path.insert(0, str(PORTABLE))
sys.dont_write_bytecode = True

import cases as cases_module
import exact_consistency
import physical
import receipt
from orthogonality import direct_reset_ulps, orthogonality_ulps, source_rotation_cap
import numeric_class_witness

OUT = REPO / ("tools/harness/numerical/src/commonTest/kotlin/"
              "io/github/rubixhacker/harness/numerical")
REVISION = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def outcome(call):
    try:
        return {"result": call()}
    except receipt.Rejected as error:
        return {"error": str(error)}
    except ValueError as error:
        return {"error": str(error), "type": "ValueError"}


def with_rows(rows, action):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "trace.jsonl"
        path.write_text("".join(json.dumps(row, allow_nan=False) + "\n" for row in rows))
        return action(path)


# Rows-based adapters so the recorded inputs stay data rather than files.
def inspect_rows(rows, declared_cases, allow_tagged=False):
    return with_rows(rows, lambda path: receipt.inspect(path, declared_cases, allow_tagged))


def compare_exact_rows(reference_rows, candidate_rows, declared_cases):
    with tempfile.TemporaryDirectory() as directory:
        reference = Path(directory) / "reference.jsonl"
        candidate = Path(directory) / "candidate.jsonl"
        reference.write_text("".join(json.dumps(row) + "\n" for row in reference_rows))
        candidate.write_text("".join(json.dumps(row) + "\n" for row in candidate_rows))
        return receipt.compare_exact(reference, candidate, declared_cases)


def seal_rows(rows, declared_cases, identity, artifact_paths, artifact_sha256,
              catalog, catalog_sha256, build_config_sha256, trace_sha256):
    with tempfile.TemporaryDirectory() as directory:
        trace = Path(directory) / "trace.jsonl"
        trace.write_text("".join(json.dumps(row) + "\n" for row in rows))
        artifacts = {}
        for name, path in artifact_paths.items():
            target = Path(directory) / (name + ".jar")
            target.write_bytes(b"placeholder:" + name.encode())
            artifacts[name] = target
        observed = dict(artifact_sha256)

        def fake_digest(path):
            if isinstance(path, _Catalog):
                return catalog_sha256
            path = Path(path)
            if path.name == "trace.jsonl":
                return trace_sha256
            if path.name.endswith(".jar"):
                return observed[path.stem]
            return catalog_sha256

        original = (receipt.digest, receipt.CATALOG, receipt.BUILD_FILES)
        try:
            receipt.digest = fake_digest
            receipt.CATALOG = _Catalog(catalog)
            receipt.BUILD_FILES = ()
            result = receipt.seal(trace, declared_cases, identity, artifacts)
        finally:
            receipt.digest, receipt.CATALOG, receipt.BUILD_FILES = original
        result["artifact_paths"] = dict(artifact_paths)
        return result


class _Catalog:
    def __init__(self, catalog):
        self.catalog = catalog

    def read_text(self):
        return json.dumps(self.catalog)


def verify_rows(sealed, rows, declared_cases, identity, artifact_paths,
                artifact_sha256, catalog, catalog_sha256, build_config_sha256,
                trace_sha256):
    fresh = seal_rows(rows, declared_cases, identity, artifact_paths,
                      artifact_sha256, catalog, catalog_sha256,
                      build_config_sha256, trace_sha256)
    if fresh != sealed:
        raise receipt.Rejected("receipt identity or counts differ")
    return {"status": "PASSED", "counts": fresh["counts"]}


def nominal_free_rows(rows, expected_steps=36000):
    return with_rows(rows, lambda path: physical.nominal_free(path, expected_steps))


def sleep_wake_rows(rows, keys):
    return physical.sleep_wake_rows(rows, keys)


def kotlin(name, text):
    """Emits the text in chunks: a class-file UTF8 constant cannot exceed 65535 bytes."""
    def escape(part):
        return (part.replace("\\", "\\\\").replace('"', '\\"')
                .replace("$", "\\$"))
    chunks = [text[index:index + 20000] for index in range(0, len(text), 20000)]
    joined = " +\n    ".join('"%s"' % escape(chunk) for chunk in chunks)
    return 'internal val %s: String =\n    %s\n' % (name, joined)


def emit(file_name, constant, document):
    text = json.dumps(document, sort_keys=True)
    body = ('package io.github.rubixhacker.harness.numerical\n\n'
            '// Generated from the Python reference at revision %s. Do not edit by hand.\n'
            % document.get("revision", REVISION))
    body += kotlin(constant, text)
    (OUT / file_name).write_text(body)
    print(file_name, len(text))


# ---------------------------------------------------------------- cases
declared = cases_module.declared_cases()
case_ids = [case["id"] for case in declared]
families = sorted({case["family"] for case in declared})
caps = {}
cap_errors = {}
for case in declared:
    try:
        caps[case["id"]] = source_rotation_cap(case)
    except ValueError as error:
        cap_errors[case["id"]] = str(error)
cases_document = {
    "revision": REVISION,
    "count": len(declared),
    "canonical_sha256": hashlib.sha256(canonical(declared).encode()).hexdigest(),
    "id_list_sha256": hashlib.sha256(canonical(case_ids).encode()).hexdigest(),
    "family_counts": {family: sum(1 for c in declared if c["family"] == family)
                      for family in families},
    "profile_counts": {profile: sum(1 for c in declared if c["profile"] == profile)
                       for profile in sorted({c["profile"] for c in declared})},
    "samples": {family: next(c for c in declared if c["family"] == family)
                for family in families},
    "caps": caps,
    "cap_error": cap_errors,
}
emit("CasesVectors.kt", "CASES_VECTORS", cases_document)

# ------------------------------------------------------- orthogonality bound
sample_rotations = [0, 1, 2, 3, 4, 5, 6, 9, 10, 21, 60, 100, 333, 1000, 2345,
                    4096, 6600]
orthogonality_document = {
    "revision": REVISION,
    "direct_reset_ulps": direct_reset_ulps(),
    "ulps": {str(n): orthogonality_ulps(n) for n in sample_rotations},
    "domain_errors": {
        "-1": outcome(lambda: orthogonality_ulps(-1)),
        "6601": outcome(lambda: orthogonality_ulps(6601)),
    },
}
emit("OrthogonalityVectors.kt", "ORTHOGONALITY_VECTORS", orthogonality_document)

# ---------------------------------------------------------------- receipt
CASES = [{"id": "motion", "family": "free-motion", "profile": "default",
          "hz": 60, "steps": 2}]
HEADER = {"kind": "inputs", "id": "motion", "family": "free-motion",
          "profile": "default", "hz": 60, "steps": 2, "dt": 1 / 60,
          "input": {"velocity": [-0.0, 1.0]}}
STATE = {"kind": "state", "id": "motion", "step": 1, "order": 0,
         "state": {"x": -0.0}}


def sample():
    return [copy.deepcopy(HEADER), copy.deepcopy(STATE),
            {"kind": "event", "id": "motion", "step": 2, "order": 0, "name": "wake"},
            {"kind": "state", "id": "motion", "step": 2, "order": 1, "state": {"x": 1.0}},
            {"kind": "case-end", "id": "motion", "steps": 2, "events": 1}]


receipt_checks = []


def inspect_check(name, rows, declared_cases, allow_tagged=False):
    receipt_checks.append({
        "name": name, "rows": rows, "cases": declared_cases,
        "allow_tagged": allow_tagged,
        "outcome": outcome(lambda: inspect_rows(rows, declared_cases, allow_tagged)),
    })


def base_settings():
    keys = ("gravity", "stepFrequency", "maximumTranslation", "maximumRotation",
            "atRestDetectionEnabled", "maximumAtRestLinearVelocity",
            "maximumAtRestAngularVelocity", "minimumAtRestTime", "velocityIterations",
            "positionIterations", "warmStartingEnabled", "maximumWarmStartDistance",
            "linearTolerance", "angularTolerance", "maximumLinearCorrection",
            "maximumAngularCorrection", "baumgarte", "continuousDetectionMode",
            "narrowphase")
    settings = {key: 0 for key in keys}
    settings["timeOfImpact"] = {"distanceEpsilon": 4.806217383937352e-6}
    return settings


def body(index, x, radius):
    return {"id": f"b{index}", "transform": {"getTranslation": [x, 0.0]},
            "massType": "NORMAL", "mass": 1.0, "inertia": 1.0,
            "massCenter": [0.0, 0.0], "linearDamping": 0.0,
            "angularDamping": 0.0, "initialVelocity": [0.0, 0.0],
            "initialAngularVelocity": 0.0, "atRestDetectionEnabled": True,
            "bullet": False,
            "fixtures": [{"id": f"b{index}f0", "density": 1.0, "friction": 0.2,
                          "restitution": 0.0, "restitutionVelocity": 1.0,
                          "sensor": False, "filter": "DEFAULT_FILTER",
                          "shape": {"type": "Circle", "radius": radius}}]}


rows = sample()
inspect_check("exact-case-and-step-coverage", rows, CASES)
for label, changed in (("without-case-end", rows[:-1]),
                       ("without-state-two", rows[:2] + rows[3:]),
                       ("without-inputs", rows[1:])):
    inspect_check("exact-case-and-step-coverage/" + label, changed, CASES)
inspect_check("omitted-declared-case", rows, CASES + [{**CASES[0], "id": "omitted"}])
inspect_check("empty-declaration", rows, [])
inspect_check("input-matches", rows, [{**CASES[0], "input": HEADER["input"]}])
inspect_check("input-signed-zero-differs", rows,
              [{**CASES[0], "input": {"velocity": [0.0, 1.0]}}])

continuation_rows = copy.deepcopy(rows)
continuation_rows[0]["startStep"] = 1
continuation_rows[1]["step"] = 2
continuation_rows[2]["step"] = 3
continuation_rows[3]["step"] = 3
inspect_check("continuation", continuation_rows, [{**CASES[0], "start_step": 1}])
inspect_check("continuation-without-declaration", continuation_rows, CASES)

frozen_case = [{**CASES[0], "require_frozen_projection": True,
                "frozen_id": "baseline", "frozen_origin": [0.0, 0.0],
                "frozen_scale": 1.0}]
inspect_check("frozen-missing", sample(), frozen_case)
complete_rows = copy.deepcopy(rows)
complete_rows[0]["frozenConfiguration"] = {key: {} for key in ("settings", "world", "state")}
complete_rows[0]["frozenInput"] = {
    "kind": "inputs", "dt": complete_rows[0]["dt"], "steps": complete_rows[0]["steps"],
    "id": "baseline", "origin": [0.0, 0.0], "scale": 1.0,
    "settings": {}, "world": {}, "state": {}}
for row in complete_rows:
    if row["kind"] == "state":
        row["frozenState"] = {"bodies": [], "joints": []}
inspect_check("frozen-complete", complete_rows, frozen_case)
omitted = copy.deepcopy(complete_rows)
omitted[1].pop("frozenState")
inspect_check("frozen-state-omitted", omitted, frozen_case)
altered = copy.deepcopy(complete_rows)
altered[0]["frozenInput"]["dt"] *= 2
inspect_check("frozen-envelope-changed", altered, frozen_case)
renamed = copy.deepcopy(complete_rows)
renamed[0]["frozenInput"]["id"] = "other"
inspect_check("frozen-id-changed", renamed, frozen_case)

inspect_check("instrumented-callback-omitted", sample(),
              [{**CASES[0], "expected_instrumented_callbacks": [1]}])
inspect_check("setup-omitted", sample(), [{**CASES[0], "require_setup": True}])

setup_header = {"settings": base_settings(),
                "setup": {"bodies": [body(0, 0.0, 1.0), body(1, 1.5, 0.5)], "joints": []}}
setup_case = {"family": "geometry-collision",
              "input": {"scale": 1.0, "origin": [0.0, 0.0], "delta": 0.0}}

changed_header = copy.deepcopy(setup_header)
changed_header["setup"]["bodies"][1]["fixtures"][0]["shape"]["radius"] = 0.75
joint_settings = base_settings()
joint_settings["gravity"] = [0.0, 0.0]


def joint_body(index):
    return {"id": f"b{index}", "transform": {"getTranslation": [0.0, float(index)]},
            "massType": "NORMAL", "mass": 1.0, "inertia": 1.0,
            "massCenter": [0.0, 0.0], "linearDamping": 0.0,
            "angularDamping": 0.0, "initialVelocity": [0.0, 0.0],
            "initialAngularVelocity": 0.0, "atRestDetectionEnabled": True,
            "bullet": False,
            "fixtures": [{"id": f"b{index}f0", "density": 1.0, "friction": 0.2,
                          "restitution": 0.0, "restitutionVelocity": 1.0,
                          "sensor": False, "filter": "DEFAULT_FILTER",
                          "shape": {"type": "Circle"}}]}


joint_header = {"settings": joint_settings,
                "setup": {"bodies": [joint_body(0), joint_body(1)],
                          "joints": [{"id": "j0", "bodies": [0, 1],
                                      "mode": {"type": "Angle",
                                               "limitsEnabled": False}}]}}
joint_case = {"id": "joint-Angle-LimitsEnabled-false",
              "family": "joints-limits-motors",
              "input": {"jointType": "Angle", "field": "LimitsEnabled",
                        "initialValue": False}}
enabled_header = copy.deepcopy(joint_header)
enabled_header["setup"]["joints"][0]["mode"]["limitsEnabled"] = True

ratio_header = copy.deepcopy(enabled_header)
ratio_header["setup"]["joints"][0]["mode"]["ratio"] = 2.0
numeric_case = {**joint_case, "id": "joint-Angle-Ratio-2.0",
                "input": {"jointType": "Angle", "field": "Ratio", "initialValue": 2.0}}
ratio_low_header = copy.deepcopy(ratio_header)
ratio_low_header["setup"]["joints"][0]["mode"]["ratio"] = 1.0

limit_header = copy.deepcopy(ratio_header)
limit_mode = limit_header["setup"]["joints"][0]["mode"]
limit_mode["lowerLimit"], limit_mode["upperLimit"] = -0.5, 0.5
limit_mode["limitsEnabled"] = True
limits_case = {**joint_case, "id": "joint-Angle-limits-range",
               "input": {"jointType": "Angle", "limits": "range",
                         "lowerLimit": -0.5, "upperLimit": 0.5}}
limit_high_header = copy.deepcopy(limit_header)
limit_high_header["setup"]["joints"][0]["mode"]["upperLimit"] = 0.0

tagged_rows = sample()
tagged_rows[1]["state"]["x"] = {"nonfinite": "-Infinity"}
angle_case = {"id": "P-J-Angle-ratio-limits-off--1.0",
              "family": "joints-limits-motors", "profile": "baseline-failed",
              "hz": 60, "steps": 1, "input": {}, "min_step_events": 0}
angle_rows = [
    {"kind": "inputs", "id": angle_case["id"], "family": angle_case["family"],
     "profile": angle_case["profile"], "hz": 60, "steps": 1, "dt": 1 / 60,
     "input": {}},
    {"kind": "state", "id": angle_case["id"], "step": 1, "order": 0,
     "state": {"energy": {"nonfinite": "Infinity"}}},
    {"kind": "case-end", "id": angle_case["id"], "steps": 1, "events": 0},
]
angle_input_rows = copy.deepcopy(angle_rows)
angle_input_rows[0]["input"] = {"unexpected": {"nonfinite": "NaN"}}
angle_input_case = copy.deepcopy(angle_case)
angle_input_case["input"] = angle_input_rows[0]["input"]
other_rows = copy.deepcopy(angle_rows)
for row in other_rows:
    row["id"] = "other"
other_case = {**angle_case, "id": "other"}

endpoint_cases = [{**CASES[0], "outer_group": 2}]
endpoint_rows = copy.deepcopy(rows)
endpoint_rows[-1] = {**endpoint_rows[-1], "endpoints": 1}
endpoint_rows.insert(-1, {"kind": "endpoint", "id": "motion", "step": 2, "order": 2,
                          "state": {"x": 1.0}})
endpoint_bad_rows = endpoint_rows[:-2] + endpoint_rows[-1:]

callback_rows = sample()
callback_rows.insert(1, {"kind": "event", "id": "motion", "step": 1, "order": 0,
                         "name": "step.begin"})
callback_rows[2]["order"] = 1
callback_rows[-1]["events"] = 2
callback_expected = [{**CASES[0], "min_step_events": 1, "expected_actions": [2]}]
complete_callback_rows = copy.deepcopy(callback_rows)
complete_callback_rows.insert(-2, {"kind": "action", "id": "motion", "step": 2,
                                   "order": 1, "name": "impulse"})
complete_callback_rows[-2]["order"] = 2
complete_callback_rows[-1]["events"] = 3

compare_variants = []
for label, change in (
        ("original", lambda rows: None),
        ("signed-zero-input", lambda rows: rows[0]["input"]["velocity"].__setitem__(0, 0.0)),
        ("signed-zero-state", lambda rows: rows[1]["state"].__setitem__("x", 0.0)),
        ("event-order", lambda rows: rows[2].__setitem__("order", 1)),
        ("input-value", lambda rows: rows[0]["input"].__setitem__("velocity", [2.0, 1.0]))):
    altered_rows = copy.deepcopy(rows)
    change(altered_rows)
    compare_variants.append((label, altered_rows))

def setup_check(name, header, case):
    return {"name": name, "header": header, "case": case,
            "outcome": outcome(lambda: receipt.validate_setup(header, case))}


setup_checks = [
    setup_check("geometry-valid", setup_header, setup_case),
    setup_check("geometry-radius-changed", changed_header, setup_case),
    setup_check("boolean-joint-valid", joint_header, joint_case),
    setup_check("boolean-joint-flipped", enabled_header, joint_case),
    setup_check("numeric-joint-valid", ratio_header, numeric_case),
    setup_check("numeric-joint-changed", ratio_low_header, numeric_case),
    setup_check("limits-valid", limit_header, limits_case),
    setup_check("limits-changed", limit_high_header, limits_case),
]

identity = receipt.Identity("a" * 40, "b" * 64,
                            {"jvm": hashlib.sha256(b"staged artifact").hexdigest()},
                            "jvm-test")
catalog = {"baseline_source_revision": "058bf6d982a0fb89b54050f929f6ea9dae53b714",
           "baseline_jar_sha256": "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e",
           "fixtures": [{"key": "portable-matrix/1",
                         "reference": {"gzip_sha256": "c" * 64}}]}
sealed = seal_rows(rows, CASES, identity, {"jvm": "/artifacts/portable.jar"},
                   identity.artifact_sha256, catalog, "d" * 64, "e" * 64, "f" * 64)
tampered = copy.deepcopy(sealed)
tampered["trace_sha256"] = "0" * 64

def _records_check(name, lines, allow):
    entry = {"name": name, "lines": lines, "allow_tagged": allow}
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "trace.jsonl"
        path.write_text("".join(line + "\n" for line in lines))
        entry["outcome"] = outcome(lambda: list(receipt.records(path, allow)))
    return entry


record_cases = [
    ("tagged-disallowed", [json.dumps(row) for row in tagged_rows], False),
    ("tagged-allowed", [json.dumps(row) for row in tagged_rows], True),
    ("duplicate-key", ['{"a":1,"a":2}'], False),
    ("trailing-garbage", ['{"a":1} x'], False),
    ("unterminated", ['{"a":'], False),
    ("not-an-object", ['[]'], False),
    ("empty-string", [''], False),
    ("number", ['{"a":1,"b":1.0,"c":-0.0}'], False),
]
records_checks = [_records_check(name, lines, allow)
                  for name, lines, allow in record_cases]

receipt_document = {
    "revision": REVISION,
    "inspect": receipt_checks,
    "compare": [{"name": label, "candidate": candidate,
                 "outcome": outcome(lambda c=candidate: compare_exact_rows(rows, c, CASES))}
                for label, candidate in compare_variants],
    "records": records_checks,
    "validate_setup": setup_checks,
    "angle": {
        "case": angle_case,
        "cases": [angle_case],
        "rows": angle_rows,
        "disallowed": outcome(lambda: inspect_rows(angle_rows, [angle_case])),
        "allowed": outcome(lambda: inspect_rows(angle_rows, [angle_case], True)),
        "input_case": [angle_input_case],
        "input_rows": angle_input_rows,
        "input_outcome": outcome(lambda: inspect_rows(
            angle_input_rows, [angle_input_case], True)),
        "other_case": [other_case],
        "other_rows": other_rows,
        "other_outcome": outcome(lambda: inspect_rows(other_rows, [other_case], True)),
    },
    "endpoints": {
        "cases": endpoint_cases,
        "rows": endpoint_rows,
        "bad_rows": endpoint_bad_rows,
        "good": outcome(lambda: inspect_rows(endpoint_rows, endpoint_cases)),
        "bad": outcome(lambda: inspect_rows(endpoint_bad_rows, endpoint_cases)),
    },
    "callbacks": {
        "expected": callback_expected,
        "rows": callback_rows,
        "complete_rows": complete_callback_rows,
        "missing": outcome(lambda: inspect_rows(callback_rows, callback_expected)),
        "complete": outcome(lambda: inspect_rows(complete_callback_rows, callback_expected)),
    },
    "seal": {
        "rows": rows,
        "cases": CASES,
        "identity": {"candidate_commit": identity.candidate_commit,
                     "source_sha256": identity.source_sha256,
                     "artifact_sha256": identity.artifact_sha256,
                     "runtime": identity.runtime},
        "artifact_paths": {"jvm": "/artifacts/portable.jar"},
        "artifact_sha256": identity.artifact_sha256,
        "catalog": catalog,
        "catalog_sha256": "d" * 64,
        "build_config_sha256": sealed["build_config_sha256"],
        "trace_sha256": "f" * 64,
        "sealed": sealed,
        "stale_artifact": outcome(lambda: seal_rows(
            rows, CASES, identity, {"jvm": "/artifacts/portable.jar"},
            {"jvm": "0" * 64}, catalog, "d" * 64, sealed["build_config_sha256"],
            "f" * 64)),
        "artifact_set": outcome(lambda: seal_rows(
            rows, CASES, identity, {"other": "/artifacts/other.jar"},
            {"other": identity.artifact_sha256["jvm"]}, catalog, "d" * 64,
            sealed["build_config_sha256"], "f" * 64)),
        "verify": outcome(lambda: verify_rows(
            sealed, rows, CASES, identity, {"jvm": "/artifacts/portable.jar"},
            identity.artifact_sha256, catalog, "d" * 64,
            sealed["build_config_sha256"], "f" * 64)),
        "verify_tampered": outcome(lambda: verify_rows(
            tampered, rows, CASES, identity, {"jvm": "/artifacts/portable.jar"},
            identity.artifact_sha256, catalog, "d" * 64,
            sealed["build_config_sha256"], "f" * 64)),
    },
}
emit("ReceiptVectors.kt", "RECEIPT_VECTORS", receipt_document)

# ------------------------------------------------------- exact consistency
def transform(x, y):
    return {"type": "org.dyn4j.geometry.Transform", "getCost": 1.0,
            "getSint": 0.0, "getRotationAngle": 0.0,
            "getTranslation": [x, y], "getTranslationX": x, "getTranslationY": y,
            "getValues": [1.0, 0.0, x, 0.0, 1.0, y], "isIdentity": False}


def ec_body(index):
    current = transform(0.0, -0.25 if index == 0 else 0.5)
    value = {"id": f"b{index}", "atRest": False, "force": [0.0, 0.0],
             "accumulatedForce": [0.0, 0.0], "torque": 0.0,
             "accumulatedTorque": 0.0, "velocity": [0.0, 0.0],
             "angularVelocity": 0.0,
             "worldCenter": copy.deepcopy(current["getTranslation"]),
             "fixedOriginPosition": copy.deepcopy(current["getTranslation"]),
             "transform": current, "previousTransform": copy.deepcopy(current),
             "rotationIncrementSum": 0.0, "rotationStepBoundBelowPi": True,
             "rotationTrackingScope": "initial", "fixtures": [{}]}
    value["properties"] = {
        "getForce": copy.deepcopy(value["force"]),
        "getAccumulatedForce": copy.deepcopy(value["accumulatedForce"]),
        "getTorque": value["torque"],
        "getAccumulatedTorque": value["accumulatedTorque"],
        "getLinearVelocity": copy.deepcopy(value["velocity"]),
        "getAngularVelocity": value["angularVelocity"],
        "getTransform": copy.deepcopy(value["transform"]),
        "getPreviousTransform": copy.deepcopy(value["previousTransform"]),
        "getWorldCenter": copy.deepcopy(value["worldCenter"]), "isAtRest": False,
        "getAngularDamping": 0.0, "getChangeInOrientation": 0.0,
        "getChangeInPosition": [0.0, 0.0], "getFixtureCount": 1,
        "getGravityScale": 1.0, "getLinearDamping": 0.0,
        "getLocalCenter": [0.0, 0.0], "getMass": {"getCenter": [0.0, 0.0]},
        "getRotationDiscRadius": 1.0, "isAtRestDetectionEnabled": True,
        "isBullet": False, "isDynamic": index == 1, "isEnabled": True,
        "isKinematic": False, "isStatic": index == 0,
        "type": "org.dyn4j.dynamics.Body"}
    return value


def snapshot():
    return {"bodies": [ec_body(0), ec_body(1)], "joints": []}


ec_checks = []


def call_value(call, arguments):
    if call == "check_snapshot":
        return exact_consistency.check_snapshot(
            arguments.get("state"), arguments.get("phase"), arguments.get("prior"))
    if call == "check_impulse":
        return exact_consistency.check_impulse(arguments["before"], arguments["after"])
    if call == "check_time_step":
        return exact_consistency.check_time_step(
            arguments["value"], arguments["hz"], arguments["step"])
    if call == "check_endpoint":
        return exact_consistency.check_endpoint(
            arguments["endpoint"], arguments["inner"], arguments["outerHz"])
    raise AssertionError(call)


def check(name, call, **arguments):
    entry = {"name": name, "call": call,
             "outcome": outcome(lambda: call_value(call, arguments))}
    entry.update(arguments)
    ec_checks.append(entry)


initial = snapshot()
check("initial", "check_snapshot", state=initial, phase="initial")
current = copy.deepcopy(initial)
for item in current["bodies"]:
    item.pop("fixtures")
    item.pop("properties")
check("step", "check_snapshot", state=current, phase="step", prior=initial)

for reason, change in (
        ("force", lambda state: state["bodies"][0]["force"].__setitem__(0, 0.1)),
        ("alias", lambda state: state["bodies"][0]["transform"].__setitem__(
            "getTranslationY", -0.2)),
        ("previous", lambda state: state["bodies"][0]["previousTransform"].__setitem__(
            "getRotationAngle", 0.1))):
    bad = copy.deepcopy(current)
    change(bad)
    check("step/" + reason, "check_snapshot", state=bad, phase="step", prior=initial)
bad_sleep = copy.deepcopy(current)
bad_sleep["bodies"][1]["atRest"] = True
bad_sleep["bodies"][1]["velocity"][0] = 0.1
check("step/sleep", "check_snapshot", state=bad_sleep, phase="step", prior=initial)

sleeping = copy.deepcopy(current)
sleeping["bodies"][1]["atRest"] = True
check("sleeping", "check_snapshot", state=sleeping, phase="step",
      prior=copy.deepcopy(sleeping))
drift = copy.deepcopy(sleeping)
moving = drift["bodies"][1]
moving["transform"] = transform(1.0, 0.5)
moving["worldCenter"] = [1.0, 0.5]
moving["fixedOriginPosition"] = [1.0, 0.5]
check("sleep-drift", "check_snapshot", state=drift, phase="step", prior=sleeping)

duplicate = copy.deepcopy(initial)
duplicate["bodies"][1]["properties"]["getForce"] = [0.1, 0.0]
check("duplicate", "check_snapshot", state=duplicate, phase="initial")
nonfinite = copy.deepcopy(initial)
nonfinite["bodies"][1]["transform"]["getRotationAngle"] = float("inf")
check("nonfinite", "check_snapshot", state=nonfinite, phase="initial")
signed_zero = copy.deepcopy(initial)
signed_zero["bodies"][1]["force"] = [-0.0, 0.0]
signed_zero["bodies"][1]["properties"]["getForce"] = [-0.0, 0.0]
check("signed-zero", "check_snapshot", state=signed_zero, phase="initial")

before = snapshot()
before["bodies"][1]["atRest"] = True
before["bodies"][1]["properties"]["isAtRest"] = True
after = copy.deepcopy(before)
dynamic = after["bodies"][1]
dynamic["atRest"] = False
dynamic["velocity"] = [1.0, 0.0]
dynamic["properties"]["isAtRest"] = False
dynamic["properties"]["getLinearVelocity"] = [1.0, 0.0]
check("impulse", "check_impulse", before=before, after=after)
bad_impulse = copy.deepcopy(after)
bad_impulse["bodies"][1]["fixtures"][0]["getFriction"] = 0.6
check("impulse/extra-field", "check_impulse", before=before, after=bad_impulse)
wrong_velocity = copy.deepcopy(after)
wrong_velocity["bodies"][1]["velocity"][0] = 0.9
check("impulse/velocity", "check_impulse", before=before, after=wrong_velocity)

timestep = {"type": "org.dyn4j.dynamics.TimeStep", "getDeltaTime": 1 / 120,
            "getInverseDeltaTime": 120.0, "getPrevousDeltaTime": 1 / 60,
            "getPreviousInverseDeltaTime": 60.0, "getDeltaTimeRatio": 0.5}
check("timestep", "check_time_step", value=timestep, hz=120, step=1)
check("timestep/ratio", "check_time_step",
      value={**timestep, "getDeltaTimeRatio": 1.0}, hz=120, step=1)
check("timestep/hz", "check_time_step", value=timestep, hz=90, step=1)

endpoint_state = snapshot()
inner = {"kind": "state", "step": 4, "state": endpoint_state}
endpoint = {"kind": "outer-endpoint", "step": 4, "outerStep": 1,
            "state": copy.deepcopy(endpoint_state)}
check("endpoint", "check_endpoint", endpoint=endpoint, inner=inner, outerHz=30)
bad_endpoint = copy.deepcopy(endpoint)
bad_endpoint["state"]["bodies"][1]["velocity"][0] = 0.1
check("endpoint/state", "check_endpoint", endpoint=bad_endpoint, inner=inner, outerHz=30)
wrong_step = copy.deepcopy(endpoint)
wrong_step["outerStep"] = 2
check("endpoint/outer-step", "check_endpoint", endpoint=wrong_step, inner=inner, outerHz=30)

emit("ExactConsistencyVectors.kt", "EXACT_VECTORS",
     {"revision": REVISION, "checks": ec_checks})

# ---------------------------------------------------------------- physical
catalog_document = json.loads(
    (REPO / "tools/numerical/fixtures.json").read_text())
merged = {}
for key in ("default-sleep-30", "default-sleep-60", "default-sleep-120",
            "configured-30-r1", "configured-30-r2", "configured-60-r1",
            "configured-60-r2", "configured-120-r1", "configured-120-r2"):
    item = next(entry for entry in catalog_document["fixtures"] if entry["key"] == key)
    profile = catalog_document["profiles"][item["profile"]]
    full = {**profile, **item}
    merged[key] = {name: full[name] for name in (
        "id", "counts", "physical_phase_ceilings_m", "physical_phases_by_hz",
        "physical_phases_inner_steps", "physical_phases_steps") if name in full}

nominal_rows = [{"kind": "state", "id": "long-free-60", "step": 1,
                 "state": {"bodies": [{"worldCenter": [0.25 / 60, -0.125 / 60],
                                       "velocity": [0.25, -0.125],
                                       "angularVelocity": 0.5,
                                       "rotationIncrementSum": 0.5 / 60,
                                       "kineticEnergy": 1.0,
                                       "linearMomentum": [0.25, -0.125],
                                       "angularMomentumCenter": 0.5}]}}]
drifted_rows = copy.deepcopy(nominal_rows)
drifted_rows[0]["state"]["bodies"][0]["worldCenter"][1] += 2e-10
rotation_rows = copy.deepcopy(nominal_rows)
rotation_rows[0]["state"]["bodies"][0]["rotationIncrementSum"] += 1e-6
velocity_rows = copy.deepcopy(nominal_rows)
velocity_rows[0]["state"]["bodies"][0]["velocity"] = [0.5, -0.125]
momentum_rows = copy.deepcopy(nominal_rows)
momentum_rows[0]["state"]["bodies"][0]["linearMomentum"] = [0.5, -0.125]



def fixtures_state():
    return {"bodies": [
        {"id": "b0", "transform": {"getCost": 1, "getSint": 0,
                                   "getTranslation": [0, -0.25]}},
        {"id": "b1", "transform": {"getCost": 1, "getSint": 0,
                                   "getTranslation": [0, 0.5]}}]}

nominal_checks = []
for name, rows, steps in (
        ("exact", nominal_rows, 1),
        ("exact-default-steps", nominal_rows, 36000),
        ("drift", drifted_rows, 1),
        ("rotation", rotation_rows, 1),
        ("velocity", velocity_rows, 1),
        ("momentum", momentum_rows, 1),
        ("empty", [], 1)):
    nominal_checks.append({"name": name, "rows": rows, "expected_steps": steps,
                           "outcome": outcome(lambda r=rows, s=steps: nominal_free_rows(r, s))})

sleep_checks = []


def sleep_check(name, rows, keys):
    sleep_checks.append({"name": name, "rows": rows, "keys": keys,
                         "outcome": outcome(lambda r=rows, k=keys: sleep_wake_rows(r, k))})


sleep_check("empty", [], ["default-sleep-30"])
sleep_check("defaults", [], None)
sleep_check("invalid-state", [{"kind": "state", "id": "contacts-default-30", "step": 2,
                               "state": {"bodies": []}}], ["default-sleep-30"])
sleep_check("complete", [{"kind": "state", "id": "contacts-default-30", "step": 1,
                          "state": fixtures_state()}], ["default-sleep-30"])
sleep_check("out-of-schedule", [{"kind": "state", "id": "contacts-default-30", "step": 3,
                                "state": fixtures_state()}], ["default-sleep-30"])

physical_document = {
    "revision": REVISION,
    "fixtures": merged,
    "nominal": nominal_checks,
    "sleep_wake": sleep_checks,
}
emit("PhysicalVectors.kt", "PHYSICAL_VECTORS", physical_document)

# ------------------------------------------------------- class witness
def witness_record(name="portable/PortableMatrixTest", value=b"class",
                   origin="file:/fixture/"):
    return ("CLASS\t1\t" + name + "\t" + hashlib.sha256(value).hexdigest()
            + "\tL1\t" + origin + "\tjava:1\n").encode()


def witness(rows=None, status="OK", loaded=None):
    callback = witness_record() if rows is None else rows
    snapshot = (b"LOADED\t1\tportable/PortableMatrixTest\tL1\tfile:/fixture/\n"
                if loaded is None else loaded)
    helpers = b"".join(("HELPER\t" + name + "\tsystem\tfile:/agent/\n").encode()
                       for name in ("dyn4k/witness/NumericClassWitness",
                                    "dyn4k/witness/NumericClassWitness$Observer",
                                    "dyn4k/witness/NumericClassWitness$1"))
    body = b"BEGIN\tclass-witness/2\n" + helpers + callback + b"SEALED\t1\n" + snapshot
    end = f"END\t{status}\t1\t"
    return body + (end + f"{len(body) + len(end) + 21:020d}\n").encode()


witness_cases = []


def witness_check(name, raw, expected, origins=None, profile="numeric"):
    result = outcome(lambda: numeric_class_witness.read_witness(raw, expected, origins, profile))
    witness_cases.append({"name": name, "raw_base64": base64.b64encode(raw).decode(),
                          "expected_classes": {key: base64.b64encode(value).decode()
                                               for key, value in expected.items()},
                          "expected_origins": origins, "profile": profile,
                          "outcome": result})


expected_classes = {"portable/PortableMatrixTest": b"class"}
good = witness()
witness_check("good", good, expected_classes,
              {"portable/PortableMatrixTest": "file:/fixture/"})
digest = hashlib.sha256(b"class").hexdigest().encode()
for label, invalid in (
        ("end-fail", good.replace(b"END\tOK", b"END\tFAIL")),
        ("truncated", good[:-31]),
        ("digest", good.replace(digest, b"0" * 64)),
        ("origin", good.replace(b"file:/fixture/", b"file:/shadow/")),
        ("thread", good.replace(b"java:1", b"os:1")),
        ("sequence", witness(witness_record() + witness_record().replace(
            b"CLASS\t1", b"CLASS\t2"))),
        ("helper-renamed", good.replace(b"NumericClassWitness$1",
                                        b"NumericClassWitness$2")),
        ("helper-swapped", good.replace(b"NumericClassWitness$Observer",
                                        b"NumericClassWitness$1")),
        ("no-loaded", witness(loaded=b"")),
        ("loader", witness(
            loaded=b"LOADED\t1\tportable/PortableMatrixTest\tL2\tfile:/fixture/\n")),
        ("loaded-origin", witness(
            loaded=b"LOADED\t1\tportable/PortableMatrixTest\tL1\tfile:/shadow/\n"))):
    witness_check(label, invalid, expected_classes,
                  {"portable/PortableMatrixTest": "file:/fixture/"})
def boolean_witness(focus=True):
    transform = b"transform-class"
    digest = hashlib.sha256(transform).hexdigest()
    helpers = b"".join(("HELPER\t" + name + "\tsystem\tfile:/agent/\n").encode()
                       for name in ("dyn4k/witness/NumericClassWitness",
                                    "dyn4k/witness/NumericClassWitness$Observer",
                                    "dyn4k/witness/NumericClassWitness$1"))
    body = b"BEGIN\tclass-witness/3\n" + helpers
    body += ("CLASS\t1\torg/dyn4j/geometry/Transform\t" + digest
             + "\tL1\tfile:/fixture/\tjava:1\n").encode()
    body += b"SEALED\t1\n"
    body += b"LOADED\t1\torg/dyn4j/geometry/Transform\tL1\tfile:/fixture/\n"
    if focus:
        body += b"FOCUS\torg/dyn4j/geometry/Transform\tL1\t1\n"
    end = "END\tOK\t1\t"
    return body + (end + f"{len(body) + len(end) + 21:020d}\n").encode()


boolean_classes = {"org/dyn4j/geometry/Transform": b"transform-class"}
witness_check("boolean-valid", boolean_witness(), boolean_classes,
              {"org/dyn4j/geometry/Transform": "file:/fixture/"}, profile="boolean")
witness_check("boolean-no-focus", boolean_witness(focus=False), boolean_classes,
              {"org/dyn4j/geometry/Transform": "file:/fixture/"}, profile="boolean")
witness_check("profile", good, expected_classes, None, profile="other")
witness_check("no-origins", good, expected_classes)

emit("ClassWitnessVectors.kt", "WITNESS_VECTORS",
     {"revision": REVISION, "cases": witness_cases})
print("revision", REVISION)

# ---------------------------------------------------------------- compare
sys.path.insert(0, str(REPO / "tools/numerical"))
import gzip as _gzip
import tempfile as _tempfile
import compare as _compare
import weld_pulley_quality as _quality


def _scenario(fixture, rows, candidate=None):
    """Writes the reference, candidate and receipt the comparator reads, then compares."""
    with _tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        data = b"".join(
            json.dumps(row, separators=(",", ":"), sort_keys=True).encode() + b"\n"
            for row in rows)
        reference = root / "reference.jsonl.gz"
        reference.write_bytes(_gzip.compress(data, mtime=0))
        fixture = copy.deepcopy(fixture)
        fixture["reference"] = {
            "file": "reference.jsonl.gz",
            "gzip_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
            "stream_sha256": hashlib.sha256(data).hexdigest(),
            "input_sha256": hashlib.sha256(data.splitlines()[0]).hexdigest(),
        }
        candidate_rows = rows if candidate is None else candidate
        candidate_data = b"".join(
            json.dumps(row, separators=(",", ":"), sort_keys=True).encode() + b"\n"
            for row in candidate_rows)
        candidate_path = root / "candidate.jsonl"
        candidate_path.write_bytes(candidate_data)
        receipt = root / "receipt.json"
        receipt.write_text(json.dumps({
            "source_sha256": "c" * 64,
            "artifact_sha256": "d" * 64,
            "candidate_commit": "1" * 40,
            "trace_sha256": hashlib.sha256(candidate_data).hexdigest(),
            "reference_source_revision": fixture["baseline_source_revision"],
            "reference_artifact_sha256": fixture["baseline_jar_sha256"],
            "reference_trace_sha256": fixture["reference"]["gzip_sha256"],
            "expected_counts": fixture["counts"],
            "executed_counts": fixture["counts"],
            "skipped": 0,
        }))
        return _compare.compare(fixture, reference, candidate_path, receipt,
                                "c" * 64, "d" * 64, "1" * 40)


BASE_FIXTURE = {
    "id": "sample",
    "source_sha256": "a" * 64,
    "artifact_sha256": "b" * 64,
    "baseline_source_revision": "f" * 40,
    "baseline_jar_sha256": "e" * 64,
    "counts": {"inputs": 1, "event": 1, "state": 1},
    "rules": [
        {"path": "event.payload[].velocity[]", "metric": "scalar", "absolute": 0.1,
         "relative": 0, "unit": "m/s"},
        {"path": "state.state.position[]", "metric": "scalar", "absolute": 0.1,
         "relative": 0.01, "unit": "m"},
        {"path": "state.state.normal", "metric": "direction", "absolute": 0.01,
         "relative": 0, "magnitude_absolute": 0.001, "unit_deviation": 0.001, "unit": "rad"},
        {"path": "state.state.angle", "metric": "orientation", "absolute": 0.01,
         "relative": 0, "unit": "rad"},
        {"path": "state.state.sum", "metric": "scalar", "absolute": 0.01,
         "relative": 0, "unit": "rad"},
    ],
    "exact_numeric": ["inputs.dt", "event.step", "event.order", "state.step"],
}
BASE_ROWS = [
    {"kind": "inputs", "id": "sample", "dt": 0.5},
    {"kind": "event", "step": 1, "order": 0, "listener": "StepListener", "method": "begin",
     "payload": [{"velocity": [1.0, -2.0], "getPoint": [0.0, 0.0], "getDepth": 0.1,
                  "getNormalImpulse": 0.25}]},
    {"kind": "state", "step": 1, "state": {"position": [2.0, 3.0], "normal": [1.0, 0.0],
                                          "angle": 3.141592653589793, "sum": 9.0}},
]


def _mutate(rows, path, value):
    altered = copy.deepcopy(rows)
    target = altered[2]["state"]
    target[path] = value
    return altered


compare_cases = [
    ("identical", BASE_ROWS, None),
    ("component-limit", _mutate(BASE_ROWS, "position", [2.11, 3.12]), None),
    ("unpassed-channel", _mutate(BASE_ROWS, "position", [2.0, 3.0]).__class__(_mutate(
        BASE_ROWS, "sum", 9.0)), None),
    ("scalar-exceeded", _mutate(BASE_ROWS, "sum", 9.02), None),
    ("direction-reversed", _mutate(BASE_ROWS, "normal", [-1.0, 0.0]), None),
    ("orientation-wrap", _mutate(BASE_ROWS, "angle", -3.141592653589793), None),
]
compare_vectors = []
for name, rows, candidate in compare_cases:
    compare_vectors.append({"name": name, "fixture": BASE_FIXTURE, "rows": rows,
                            "candidate": candidate,
                            "outcome": _scenario(BASE_FIXTURE, rows, candidate)})

quality_root = REPO / "tools/numerical"
declaration_bytes = (quality_root / "weld-pulley-physical-declaration.json").read_bytes()
quality_declaration = json.loads(declaration_bytes)
quality_manifest = json.loads(
    (quality_root / "weld-pulley-physical-manifest.json").read_bytes())
quality_cases = {}
for case in ("weld-spring-equal", "pulley-taut"):
    reference = quality_root / "references" / quality_manifest["cases"][case]["file"]
    quality_cases[case] = _quality.audit_quality(quality_declaration, quality_manifest,
                                                 case, reference)

decimal_samples = []
for numerator, denominator in ((1, 3), (1, 2), (0, 1), (-7, 8), (3141592653589793, 10 ** 15),
                               (4387163687516115, 2 ** 53), (1, 10 ** 18),
                               (4124582955192690, 2 ** 60)):
    decimal_samples.append({"numerator": numerator, "denominator": denominator,
                            "shown": _quality.shown(_fractions.Fraction(numerator, denominator))})

emit("CompareVectors.kt", "COMPARE_VECTORS", {
    "revision": REVISION,
    "compare": compare_vectors,
    "decimal_sample": decimal_samples,
    "weld_pulley": quality_cases,
})
