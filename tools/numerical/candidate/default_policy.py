import hashlib
import json
import math
import struct
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare
import inventory

import exact_consistency
import receipt as receipt_module


PATHS = json.loads(Path(__file__).with_name("default_paths.json").read_text())
PATHS_SHA256 = "edb5de838c649dc2de0351f489a85c7a274f9c46eab58e8ada43282a3d94c21e"
CONFIGURED_RULES_SHA256 = "d46f544209528d80e0385ec4fa71ddf11c920d3b41256e43fae396f661661415"
CLASSES = {"APPROVED_LIMIT": 61, "EXACT_IDENTITY": 50,
           "EXACT_ZERO": 12, "DERIVED_FORMULA": 14}
TIMESTEP_FIELDS = ("getDeltaTime", "getInverseDeltaTime", "getPrevousDeltaTime",
                   "getPreviousInverseDeltaTime", "getDeltaTimeRatio")
DELTAS = {30: float.fromhex("0x1.1111111111111p-5"),
          60: float.fromhex("0x1.1111111111111p-6"),
          120: float.fromhex("0x1.1111111111111p-7")}
INVERSES = {30: float.fromhex("0x1.e000000000000p+4"),
            60: float.fromhex("0x1.e000000000000p+5"),
            120: float.fromhex("0x1.e000000000000p+6")}
TRIG_PATHS = {path for path, kind in PATHS.items()
              if kind == "DERIVED_FORMULA" and path.endswith((".getCost", ".getSint"))}


def stable_hash(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def frequency(fixture):
    if not fixture["key"].startswith("default-sleep-"):
        raise compare.Rejected("default policy scope differs")
    try:
        hz = int(fixture["key"].removeprefix("default-sleep-"))
    except ValueError as error:
        raise compare.Rejected("default frequency differs") from error
    if hz not in DELTAS or fixture["id"] != f"S-sleep-wake-hz{hz}" or \
            fixture["counts"]["state"] != 600 * hz:
        raise compare.Rejected("default frequency or duration differs")
    return hz


def with_rules(fixture):
    frequency(fixture)
    configured = compare.load_fixture("configured-120-r1")
    keys = ("rules", "derived_rules", "exact_numeric", "zero_numeric")
    if stable_hash({key: configured[key] for key in keys}) != CONFIGURED_RULES_SHA256 or \
            stable_hash(PATHS) != PATHS_SHA256:
        raise compare.Rejected("adopted default policy source differs")
    exact = list(dict.fromkeys(fixture["exact_numeric"] + configured["exact_numeric"]))
    return {**fixture, "rules": configured["rules"],
            "derived_rules": configured["derived_rules"],
            "zero_numeric": configured["zero_numeric"], "exact_numeric": exact,
            "check_translation_aliases": True, "callback_fixed_body_id": "b0"}


def coverage(fixture):
    frequency(fixture)
    cache = {}
    observed = {}
    for path, expected in PATHS.items():
        actual = inventory.classify_path(fixture, path, cache)["status"]
        if actual != expected:
            raise compare.Rejected(f"default path rule differs: {path}: {actual}")
        observed[path] = actual
    counts = dict(Counter(observed.values()))
    if counts != CLASSES or len(observed) != 137:
        raise compare.Rejected("default path coverage differs")
    return counts


def check_timestep(row, hz):
    method = next((method for method in ("begin", "updatePerformed", "postSolve", "end")
                   if ".StepListener." + method + "(" in row.get("method", "")), None)
    if row.get("listener") != "StepListener" or method is None:
        raise compare.Rejected("default callback identity differs")
    step_number = row.get("step")
    if type(step_number) is not int or not 1 <= step_number <= 600 * hz:
        raise compare.Rejected("default callback step differs")
    if method == "updatePerformed" and step_number != 1:
        raise compare.Rejected("default updatePerformed step differs")
    payload = row.get("payload")
    if type(payload) is not list or len(payload) != 2 or type(payload[0]) is not dict:
        raise compare.Rejected("default timestep payload schema differs")
    values = payload[0]
    if set(values) != set(TIMESTEP_FIELDS) | {"type"} or \
            values["type"] != "org.dyn4j.dynamics.TimeStep":
        raise compare.Rejected("default timestep schema differs")
    expected = (DELTAS[hz], INVERSES[hz],
                DELTAS[60] if step_number == 1 else DELTAS[hz],
                INVERSES[60] if step_number == 1 else INVERSES[hz],
                {30: 2.0, 60: 1.0, 120: 0.5}[hz] if step_number == 1 else 1.0)
    for field, value in zip(TIMESTEP_FIELDS, expected):
        actual = values[field]
        if type(actual) is not float or not math.isfinite(actual) or \
                struct.pack(">d", actual) != struct.pack(">d", value):
            raise compare.Rejected("default timestep " + field + " differs")
    return 5


def audit_math_and_timestep(path, fixture):
    hz = frequency(fixture)
    formula = fixture["derived_rules"]["stored_sine"]
    cosine_rule = fixture["derived_rules"]["stored_cosine"]
    eta = Fraction(str(formula["norm_absolute"]))
    growth = (formula["max_inner_steps"] * formula["max_rotations_per_step"] *
              formula["unit_roundoff_multiplier"] * Fraction(1, 2**53))
    premise_ok = (fixture["counts"]["state"] <= formula["max_inner_steps"] and
                  growth < 1 and growth / (1 - growth) < eta)
    callback_count = transform_count = 0
    failures = set()
    settings_checks = 0

    def check_transform(transform, name):
        nonlocal transform_count
        transform_count += 1
        if not premise_ok:
            failures.update((name + ".getCost", name + ".getSint"))
            return
        cost, sine = transform["getCost"], transform["getSint"]
        squared = Fraction.from_float(float(cost))**2 + Fraction.from_float(float(sine))**2
        if abs(cost) > 1 or abs(sine) > 1 or not (1 - eta)**2 <= squared <= (1 + eta)**2:
            failures.update((name + ".getCost", name + ".getSint"))
        angle = transform["getRotationAngle"]
        if (angle > 0 and sine < 0) or (angle < 0 and sine >= 0):
            failures.add(name + ".getSint")
        try:
            low, high = compare.cosine_bounds(angle, cosine_rule["taylor_terms"])
        except compare.Rejected:
            failures.add(name + ".getCost")
        else:
            allowance = Fraction.from_float(
                cosine_rule["acos_ulp_multiplier"] * math.ulp(abs(angle)))
            represented = Fraction.from_float(float(cost))
            if represented < low - allowance or represented > high + allowance:
                failures.add(name + ".getCost")

    for _, row in compare.records(path):
        kind = row["kind"]
        if kind == "inputs":
            settings = row["settings"]
            settings_checks += 1
            if not (type(settings["getMaximumRotation"]) is float and
                    0 < settings["getMaximumRotation"] < math.pi and
                    type(settings["getPositionConstraintSolverIterations"]) is int and
                    0 < settings["getPositionConstraintSolverIterations"] <= 8 and
                    type(settings["getVelocityConstraintSolverIterations"]) is int and
                    0 < settings["getVelocityConstraintSolverIterations"] <= 8):
                premise_ok = False
        if kind == "event" and row.get("listener") == "StepListener":
            callback_count += 1
            check_timestep(row, hz)
        if kind not in ("state", "instrumented-callback"):
            continue
        snapshots = [row["state"]] if kind == "state" else row["values"]
        prefix = "state.state.bodies[]" if kind == "state" else \
                 "instrumented-callback.values[].bodies[]"
        for snapshot in snapshots:
            for body in snapshot["bodies"]:
                if body["rotationStepBoundBelowPi"] is not True or \
                        body["rotationTrackingScope"] != \
                        "segment-only; unrecorded transform mutations invalidate":
                    failures.update(path for path in TRIG_PATHS if path.startswith(prefix))
                for name in ("transform", "previousTransform"):
                    check_transform(body[name], prefix + "." + name)
                if kind == "instrumented-callback":
                    for name in ("getTransform", "getPreviousTransform"):
                        check_transform(body["properties"][name],
                                        prefix + ".properties." + name)
    if settings_checks != 1 or callback_count != 3 * 600 * hz + 1:
        raise compare.Rejected("default timestep callback count differs")
    return {"timestep_callbacks": callback_count, "exact_timestep_checks": 5 * callback_count,
            "transform_checks": transform_count, "rotation_settings_checks": settings_checks,
            "unpassed_premise_paths": sorted(failures)}


def bind_process(fixture, candidate, receipt_path, source, artifact, commit):
    sealed = compare.parse(Path(receipt_path).read_bytes())
    if set(sealed) != receipt_module.RECEIPT_FIELDS:
        raise compare.Rejected("default receipt schema differs")
    artifact_path = Path(sealed["artifact_path"])
    if not artifact_path.is_absolute():
        artifact_path = receipt_module.ROOT / artifact_path
    observed = exact_consistency.identity(candidate, artifact_path, commit,
                                          exact_consistency.recorder_sources(fixture))
    expected = (("source_archive_sha256", source), ("artifact_sha256", artifact),
                ("trace_sha256", sealed["trace_sha256"]),
                ("process_sha256", sealed["runtime"]["process_command_sha256"]),
                ("runtime_stamp_sha256", sealed["runtime"]["runtime_stamp_sha256"]))
    for field, value in expected:
        if observed[field] != value:
            raise compare.Rejected("default process binding differs: " + field)
    if observed["runtime"] != {key: value for key, value in sealed["runtime"].items()
                                if key in receipt_module.RUNTIME_FIELDS}:
        raise compare.Rejected("default runtime binding differs")
    if sealed["build_config_sha256"] != receipt_module.build_config_hash():
        raise compare.Rejected("default build configuration differs")
    return observed


def compare_pair(fixture, reference, candidate, receipt, source, artifact, commit):
    selected = with_rules(fixture)
    classes = coverage(selected)
    compare.load_receipt(receipt, candidate, fixture, source, artifact, commit, fixture["counts"])
    binding = bind_process(fixture, candidate, receipt, source, artifact, commit)
    reference_inventory = inventory.classify_reference(selected, reference, list(PATHS))
    if reference_inventory["summary"] != classes:
        raise compare.Rejected("default frozen path inventory differs")
    audits = {"reference": audit_math_and_timestep(reference, selected),
              "candidate": audit_math_and_timestep(candidate, selected)}
    premise_unpassed = set(audits["reference"]["unpassed_premise_paths"] +
                           audits["candidate"]["unpassed_premise_paths"])
    same_run_failure = None
    for provider, path in (("reference", reference), ("candidate", candidate)):
        try:
            audits[provider]["same_run"] = exact_consistency.audit_trace(path, fixture)
        except compare.Rejected as error:
            audits[provider]["same_run"] = {"status": "FAILED", "reason": str(error)}
            same_run_failure = f"{provider} same-run: {error}"
    if premise_unpassed:
        selected = {**selected, "derived_rules": {key: value for key, value in
                    selected["derived_rules"].items() if key not in ("stored_cosine", "stored_sine")}}
    result = compare.compare(selected, reference, candidate, receipt, source, artifact, commit)
    if result["status"] != "FAILED":
        missing = premise_unpassed - set(result["unpassed_channels"])
        if missing:
            result["unpassed_channels"] = sorted(set(result["unpassed_channels"]) | missing)
            result["status"] = "UNPASSED"
        if set(result["unpassed_channels"]) - set(PATHS):
            raise compare.Rejected("unrecognized default numeric path")
    unpassed = set(result.get("unpassed_channels", [])) | premise_unpassed
    path_verdicts = {path: ("UNPASSED" if path in unpassed else
                            "NOT_EVALUATED" if result["status"] == "FAILED" else "PASSED")
                     for path in PATHS}
    if same_run_failure:
        result["status"] = "FAILED"
        result["reason"] = same_run_failure
        path_verdicts = {path: "UNPASSED" if path in unpassed else "NOT_EVALUATED"
                         for path in PATHS}
    result["default_policy"] = {"path_coverage": classes,
                                "required_paths": len(PATHS), "path_verdicts": path_verdicts,
                                "providers": audits, "candidate_binding": binding}
    return result
