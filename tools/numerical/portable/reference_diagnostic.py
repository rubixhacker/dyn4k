import argparse
import gzip
import hashlib
import json
import math
import re
import sys
from itertools import zip_longest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.dont_write_bytecode = True
import compare as approved

from receipt import Rejected, digest, exact, records


CATALOG = Path(__file__).resolve().parents[1] / "fixtures.json"
CHANNELS = ("transform.getTranslation.0", "transform.getTranslation.1",
            "previousTransform.getTranslation.0", "previousTransform.getTranslation.1",
            "velocity.0", "velocity.1", "angularVelocity", "rotationIncrementSum", "atRest")
NOMINAL_ZERO_FIELDS = ("force", "torque", "accumulatedForce", "accumulatedTorque")
NOMINAL_TIMESTEP = {
    "getDeltaTime": float.fromhex("0x1.1111111111111p-6"),
    "getPrevousDeltaTime": float.fromhex("0x1.1111111111111p-6"),
    "getInverseDeltaTime": float.fromhex("0x1.e000000000000p+5"),
    "getPreviousInverseDeltaTime": float.fromhex("0x1.e000000000000p+5"),
    "getDeltaTimeRatio": float.fromhex("0x1.0000000000000p+0"),
}
RULE_PATHS = {
    "transform.getTranslation.0": "state.state.bodies[].transform.getTranslation[]",
    "transform.getTranslation.1": "state.state.bodies[].transform.getTranslation[]",
    "previousTransform.getTranslation.0": "state.state.bodies[].previousTransform.getTranslation[]",
    "previousTransform.getTranslation.1": "state.state.bodies[].previousTransform.getTranslation[]",
    "velocity.0": "state.state.bodies[].velocity[]",
    "velocity.1": "state.state.bodies[].velocity[]",
    "angularVelocity": "state.state.bodies[].angularVelocity",
    "rotationIncrementSum": "state.state.bodies[].rotationIncrementSum",
    "atRest": "state.state.bodies[].atRest",
}


def channel(body, name):
    value = body
    for part in name.split("."):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def fixture_with_nominal_timestep_rule(fixture):
    if fixture.get("key") != "nominal-free-motion":
        raise Rejected("nominal timestep rule requires the nominal free-motion fixture")
    return {**fixture, "exact_numeric": [*fixture.get("exact_numeric", []),
            *(f"event.payload[].{name}" for name in NOMINAL_TIMESTEP),
            *(f"state.state.bodies[].{name}{'[]' if name in ('force', 'accumulatedForce') else ''}"
              for name in NOMINAL_ZERO_FIELDS)]}


def fixture_with_default_sleep_rules(fixture):
    if fixture.get("key") not in ("default-sleep-30", "default-sleep-60", "default-sleep-120"):
        raise Rejected("default sleep rules require a frozen default fixture")
    configured = approved.load_fixture("configured-30-r1")
    exact = dict.fromkeys([*fixture.get("exact_numeric", []),
                           *(pattern for pattern in configured["exact_numeric"]
                             if not pattern.startswith(("state.outerStep", "state.innerWithinOuter",
                                                        "outer-endpoint.")))])
    return {**fixture, "rules": configured["rules"], "exact_numeric": list(exact),
            "zero_numeric": configured["zero_numeric"],
            "derived_rules": configured["derived_rules"],
            "check_translation_aliases": True, "callback_fixed_body_id": "b0"}


def default_timestep_diagnostic(reference, portable, hz, expected_callbacks=None):
    if hz not in (30, 60, 120):
        raise Rejected("default timestep rate is not frozen")
    if expected_callbacks is None:
        expected_callbacks = 3 * 600 * hz + 1
    baseline = (row for row in reference_records(reference)
                if row.get("kind") == "event" and row.get("listener") == "StepListener")
    candidate = (row.get("frozenEvent") for row in
                 records(portable, allow_tagged_nonfinite=True)
                 if row.get("kind") == "event" and row.get("name", "").startswith("step."))
    sentinel = object()
    result = {"status": "PASSED", "callbacks": 0, "value_checks": 0,
              "update_performed_callbacks": 0, "first_failures": [],
              "decision": "https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-6243730891",
              "correction": "https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-6243770998"}

    def fail(message):
        if len(result["first_failures"]) < 20:
            result["first_failures"].append({"callback": result["callbacks"], "reason": message})
        result["status"] = "FAILED"

    try:
        for left, right in zip_longest(baseline, candidate, fillvalue=sentinel):
            result["callbacks"] += 1
            if left is sentinel or right is sentinel or not isinstance(right, dict):
                fail("default StepListener callback is missing")
                continue
            if any(not exact(left.get(field), right.get(field))
                   for field in ("step", "order", "method", "listener")):
                fail("default StepListener callback identity differs")
            step = left.get("step")
            if type(step) is not int or step < 1 or step > 600 * hz:
                fail("default StepListener step is outside the frozen range")
                continue
            if "updatePerformed" in left.get("method", ""):
                result["update_performed_callbacks"] += 1
            current = 1 / hz
            previous = 1 / 60 if step == 1 else current
            expected = {"getDeltaTime": current, "getInverseDeltaTime": float(hz),
                        "getPrevousDeltaTime": previous,
                        "getPreviousInverseDeltaTime": 60.0 if step == 1 else float(hz),
                        "getDeltaTimeRatio": 60 / hz if step == 1 else 1.0}
            for name, required in expected.items():
                result["value_checks"] += 1
                for label, event in (("baseline", left), ("portable", right)):
                    payload = event.get("payload")
                    value = (payload[0].get(name) if isinstance(payload, list) and payload and
                             isinstance(payload[0], dict) else None)
                    if (type(value) not in (int, float) or not math.isfinite(value) or
                            not exact(value, required)):
                        fail(f"{label} {name} differs from the per-step exact value")
        if (result["callbacks"] != expected_callbacks or
                result["value_checks"] != expected_callbacks * 5 or
                result["update_performed_callbacks"] != 1):
            fail("default StepListener callback coverage differs")
    except (Rejected, OSError, EOFError, KeyError, TypeError, ValueError) as error:
        fail(str(error))
    return result


def default_rotation_premise_diagnostic(reference, portable, hz, expected_states=None):
    if hz not in (30, 60, 120):
        raise Rejected("default rotation rate is not frozen")
    if expected_states is None:
        expected_states = 600 * hz
    fixture = fixture_with_default_sleep_rules(approved.load_fixture(f"default-sleep-{hz}"))
    expected_scope = "segment-only; unrecorded transform mutations invalidate"
    result = {"status": "PASSED", "provider_checks": {},
              "source_scope": expected_scope,
              "derived_rule_source": "configured-sleep-wake"}

    def inspect_provider(label, stream):
        counts = {"states": 0, "snapshots": 0, "bodies": 0,
                  "transform_checks": 0, "change_checks": 0}
        checks = {"unpassed_channels": set(), "numeric_checks": 0,
                  "exact_numeric_checks": 0, "derived_checks": 0}
        for row in stream:
            kind = row.get("kind")
            if kind == "state":
                counts["states"] += 1
                snapshots = [row.get("state")]
                path = "state.state.bodies[]"
            elif kind == "instrumented-callback":
                snapshots = row.get("values")
                path = "instrumented-callback.values[].bodies[]"
                if not isinstance(snapshots, list):
                    raise Rejected(f"{label} wake snapshots are absent")
                counts["snapshots"] += len(snapshots)
            else:
                continue
            for snapshot in snapshots:
                bodies = snapshot.get("bodies") if isinstance(snapshot, dict) else None
                if not isinstance(bodies, list) or not bodies:
                    raise Rejected(f"{label} default body snapshot is absent")
                for body in bodies:
                    if (not isinstance(body, dict) or
                            body.get("rotationStepBoundBelowPi") is not True or
                            body.get("rotationTrackingScope") != expected_scope):
                        raise Rejected(f"{label} rotation source scope or step bound differs")
                    counts["bodies"] += 1
                    properties = body.get("properties")
                    if properties is not None:
                        if not isinstance(properties, dict):
                            raise Rejected(f"{label} body properties are malformed")
                        current = body["transform"]["getTranslation"]
                        previous = body["previousTransform"]["getTranslation"]
                        change = properties.get("getChangeInPosition")
                        if (not isinstance(change, list) or len(change) != 2 or
                                len(current) != 2 or len(previous) != 2 or
                                any(type(value) not in (int, float) or not math.isfinite(value)
                                    for value in [*current, *previous, *change]) or
                                change != [current[i] - previous[i] for i in range(2)]):
                            raise Rejected(f"{label} represented change in position differs")
                        orientation, _ = approved.orientation_change(
                            body["previousTransform"]["getRotationAngle"],
                            body["transform"]["getRotationAngle"], body["angularVelocity"])
                        if properties.get("getChangeInOrientation") != orientation:
                            raise Rejected(f"{label} represented change in orientation differs")
                        counts["change_checks"] += 2
                    for name in ("transform", "previousTransform"):
                        transform = body.get(name)
                        if not isinstance(transform, dict) or any(
                                type(transform.get(field)) not in (int, float) or
                                not math.isfinite(transform[field])
                                for field in ("getCost", "getSint", "getRotationAngle")):
                            raise Rejected(f"{label} transform math value is absent or nonfinite")
                        location = f"{path}.{name}"
                        approved.check_cost_pair(fixture, transform, transform, location, checks)
                        approved.check_sine_pair(fixture, transform, transform, location, checks)
                        derived = checks.get("_derived_paths", set())
                        if (location + ".getCost" not in derived or
                                location + ".getSint" not in derived):
                            raise Rejected(f"{label} transform math premise was not checked")
                        counts["transform_checks"] += 2
        if counts["states"] != expected_states or not counts["bodies"] or (
                expected_states > 1 and (not counts["snapshots"] or not counts["change_checks"])):
            raise Rejected(f"{label} default rotation premise coverage differs")
        if checks["unpassed_channels"]:
            raise Rejected(f"{label} transform math enclosure is unpassed")
        result["provider_checks"][label] = counts

    try:
        inspect_provider("baseline", reference_records(reference))
        inspect_provider("portable", projected_records(portable))
    except (Rejected, approved.Rejected, OSError, EOFError, KeyError, IndexError,
            TypeError, ValueError) as error:
        result["status"] = "FAILED"
        result["reason"] = str(error)
    return result


def nominal_timestep_diagnostic(reference, portable, expected_callbacks=108001):
    baseline = (row for row in reference_records(reference)
                if row.get("kind") == "event" and row.get("listener") == "StepListener")
    candidate = (row.get("frozenEvent") for row in
                 records(portable, allow_tagged_nonfinite=True)
                 if row.get("kind") == "event" and row.get("name", "").startswith("step."))
    sentinel = object()
    result = {"status": "PASSED", "callbacks": 0, "value_checks": 0,
              "update_performed_callbacks": 0, "first_failures": [],
              "decision": "https://github.com/rubixhacker/dyn4k/issues/7#issuecomment-6243538631"}

    def fail(message):
        if len(result["first_failures"]) < 20:
            result["first_failures"].append({"callback": result["callbacks"], "reason": message})
        result["status"] = "FAILED"

    try:
        for left, right in zip_longest(baseline, candidate, fillvalue=sentinel):
            result["callbacks"] += 1
            if left is sentinel or right is sentinel or not isinstance(right, dict):
                fail("StepListener callback is missing")
                continue
            if any(not exact(left.get(field), right.get(field))
                   for field in ("step", "order", "method", "listener")):
                fail("StepListener callback identity differs")
            if "updatePerformed(" in left.get("method", ""):
                result["update_performed_callbacks"] += 1
            for name, required in NOMINAL_TIMESTEP.items():
                result["value_checks"] += 1
                for label, event in (("baseline", left), ("portable", right)):
                    payload = event.get("payload")
                    value = (payload[0].get(name) if isinstance(payload, list) and payload and
                             isinstance(payload[0], dict) else None)
                    if (type(value) not in (int, float) or not math.isfinite(value) or
                            not exact(value, required)):
                        fail(f"{label} {name} differs from fixed exact value")
        if result["callbacks"] != expected_callbacks or \
                result["value_checks"] != expected_callbacks * len(NOMINAL_TIMESTEP) or \
                result["update_performed_callbacks"] != 1:
            fail("nominal StepListener callback coverage differs")
    except (Rejected, OSError, EOFError, KeyError, TypeError, ValueError) as error:
        fail(str(error))
    return result


def structural_differences(reference, candidate, path="", limit=100):
    differences = []
    def visit(left, right, location):
        if len(differences) >= limit:
            return
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(left.keys() - right.keys()):
                differences.append({"path": f"{location}.{key}", "difference": "missing_portable"})
            for key in sorted(right.keys() - left.keys()):
                differences.append({"path": f"{location}.{key}", "difference": "extra_portable"})
            for key in sorted(left.keys() & right.keys()):
                visit(left[key], right[key], f"{location}.{key}")
        elif isinstance(left, list) and isinstance(right, list):
            if len(left) != len(right):
                differences.append({"path": location, "difference": "list_length",
                                    "reference": len(left), "portable": len(right)})
            for index, (a, b) in enumerate(zip(left, right)):
                visit(a, b, f"{location}[{index}]")
        elif type(left) is not type(right) and not (
                type(left) in (int, float) and type(right) in (int, float)):
            differences.append({"path": location, "difference": "type"})
    visit(reference, candidate, path)
    return differences[:limit]


def value_differences(reference, candidate, path="", limit=100):
    differences = []
    def visit(left, right, location):
        if len(differences) >= limit:
            return
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(left.keys() & right.keys()):
                visit(left[key], right[key], f"{location}.{key}")
        elif isinstance(left, list) and isinstance(right, list):
            for index, (a, b) in enumerate(zip(left, right)):
                visit(a, b, f"{location}[{index}]")
        elif not exact(left, right):
            differences.append({"path": location, "reference": left, "portable": right})
    visit(reference, candidate, path)
    return differences[:limit]


def zero_sign_differences(reference, candidate, path="", limit=20, fixture=None):
    differences = []
    def visit(left, right, location):
        if isinstance(left, dict) and isinstance(right, dict):
            for key in left.keys() & right.keys():
                visit(left[key], right[key], f"{location}.{key}")
        elif isinstance(left, list) and isinstance(right, list):
            for index, (a, b) in enumerate(zip(left, right)):
                visit(a, b, f"{location}[{index}]")
        elif (type(left) in (int, float) and type(right) in (int, float) and
              left == right == 0 and not exact(left, right)):
            canonical = re.sub(r"\[\d+\]", "[]", location)
            numeric_zero = fixture is not None and approved.is_zero_numeric(fixture, canonical, {})
            if not numeric_zero and len(differences) < limit:
                differences.append(location)
    visit(reference, candidate, path)
    return differences


def step_event_diagnostic(reference, portable):
    baseline = (row for row in reference_records(reference)
                if row.get("kind") == "event" and row.get("listener") == "StepListener")
    candidate = (row.get("frozenEvent") for row in
                 records(portable, allow_tagged_nonfinite=True)
                 if row.get("kind") == "event" and row.get("name", "").startswith("step."))
    sentinel = object()
    result = {"reference_events": 0, "portable_events": 0, "exact_events": 0,
              "differing_events": 0, "first_differences": []}
    for left, right in zip_longest(baseline, candidate, fillvalue=sentinel):
        if left is not sentinel:
            result["reference_events"] += 1
        if right is not sentinel:
            result["portable_events"] += 1
        if left is sentinel or right is sentinel or not exact(left, right):
            result["differing_events"] += 1
            if len(result["first_differences"]) < 20:
                result["first_differences"].append({
                    "reference_step": left.get("step") if isinstance(left, dict) else None,
                    "portable_step": right.get("step") if isinstance(right, dict) else None,
                    "reference_order": left.get("order") if isinstance(left, dict) else None,
                    "portable_order": right.get("order") if isinstance(right, dict) else None,
                    "reference_method": left.get("method") if isinstance(left, dict) else None,
                    "portable_method": right.get("method") if isinstance(right, dict) else None})
        else:
            result["exact_events"] += 1
    result["status"] = "PASSED" if result["differing_events"] == 0 and result["reference_events"] else "FAILED"
    return result


def frozen_event_diagnostic(reference, portable):
    baseline = (row for row in reference_records(reference) if row.get("kind") == "event")
    candidate = (row.get("frozenEvent") for row in
                 records(portable, allow_tagged_nonfinite=True) if row.get("kind") == "event")
    sentinel = object()
    result = {"reference_events": 0, "portable_events": 0, "exact_events": 0,
              "differing_events": 0, "first_differences": []}
    for left, right in zip_longest(baseline, candidate, fillvalue=sentinel):
        if left is not sentinel:
            result["reference_events"] += 1
        if right is not sentinel:
            result["portable_events"] += 1
        if left is sentinel or right is sentinel or not exact(left, right):
            result["differing_events"] += 1
            if len(result["first_differences"]) < 20:
                result["first_differences"].append({
                    "reference_step": left.get("step") if isinstance(left, dict) else None,
                    "portable_step": right.get("step") if isinstance(right, dict) else None,
                    "reference_order": left.get("order") if isinstance(left, dict) else None,
                    "portable_order": right.get("order") if isinstance(right, dict) else None,
                    "reference_method": left.get("method") if isinstance(left, dict) else None,
                    "portable_method": right.get("method") if isinstance(right, dict) else None,
                    "structural_differences": structural_differences(left, right, "event", 5)
                        if isinstance(left, dict) and isinstance(right, dict) else [],
                    "value_differences": value_differences(left, right, "event", 5)
                        if isinstance(left, dict) and isinstance(right, dict) else []})
        else:
            result["exact_events"] += 1
    result["status"] = "PASSED" if result["differing_events"] == 0 and result["reference_events"] else "FAILED"
    return result


def auxiliary_record_diagnostic(reference, portable):
    kinds = {"action", "instrumented-callback"}
    baseline = (row for row in reference_records(reference) if row.get("kind") in kinds)
    def candidate_records():
        for row in records(portable, allow_tagged_nonfinite=True):
            if row.get("kind") == "action":
                yield from row.get("frozenRecords", [])
            elif row.get("kind") == "instrumented-callback":
                yield row.get("frozenRecord")
    sentinel = object()
    result = {"reference_records": 0, "portable_records": 0, "exact_records": 0,
              "differing_records": 0, "first_differences": []}
    for left, right in zip_longest(baseline, candidate_records(), fillvalue=sentinel):
        if left is not sentinel:
            result["reference_records"] += 1
        if right is not sentinel:
            result["portable_records"] += 1
        if left is sentinel or right is sentinel or not exact(left, right):
            result["differing_records"] += 1
            if len(result["first_differences"]) < 20:
                result["first_differences"].append({
                    "reference_kind": left.get("kind") if isinstance(left, dict) else None,
                    "portable_kind": right.get("kind") if isinstance(right, dict) else None,
                    "reference_step": left.get("step") if isinstance(left, dict) else None,
                    "portable_step": right.get("step") if isinstance(right, dict) else None,
                    "structural_differences": structural_differences(left, right, "record", 5)
                        if isinstance(left, dict) and isinstance(right, dict) else [],
                    "value_differences": value_differences(left, right, "record", 5)
                        if isinstance(left, dict) and isinstance(right, dict) else []})
        else:
            result["exact_records"] += 1
    result["status"] = "PASSED" if result["differing_records"] == 0 and result["reference_records"] == result["portable_records"] else "FAILED"
    return result


def nominal_zero_diagnostic(reference, portable):
    baseline = (row for row in reference_records(reference) if row.get("kind") == "state")
    candidate = (row for row in records(portable, allow_tagged_nonfinite=True)
                 if row.get("kind") == "state")
    result = {"status": "PASSED", "steps": 0,
              "checked_values": 0, "failed_values": 0, "first_failures": []}
    def values(value):
        return value if isinstance(value, list) else [value]
    for left, right in zip_longest(baseline, candidate):
        if left is None or right is None or left.get("step") != right.get("step"):
            raise Rejected("nominal zero diagnostic has missing or reordered states")
        result["steps"] += 1
        left_bodies = left["state"]["bodies"]
        right_bodies = right["frozenState"]["bodies"]
        if len(left_bodies) != len(right_bodies):
            raise Rejected("nominal zero diagnostic body count differs")
        for index, (a, b) in enumerate(zip(left_bodies, right_bodies)):
            for field in NOMINAL_ZERO_FIELDS:
                for side, body in (("baseline", a), ("portable", b)):
                    for value in values(body[field]):
                        result["checked_values"] += 1
                        if not exact(value, 0.0):
                            result["failed_values"] += 1
                            if len(result["first_failures"]) < 20:
                                result["first_failures"].append({"step": left["step"],
                                    "body": index, "field": field, "side": side,
                                    "value": value})
    if not result["steps"] or result["failed_values"]:
        result["status"] = "FAILED"
    return result


def reference_records(path):
    for _, value in approved.records(path):
        yield value


def portable_case_id(fixture_key):
    if fixture_key == "nominal-free-motion":
        return "long-free-60"
    if fixture_key.startswith("default-sleep-"):
        return "contacts-default-" + fixture_key.rsplit("-", 1)[1]
    if fixture_key.startswith("configured-"):
        return "contacts-" + fixture_key
    if fixture_key == "weld-enabled-equal":
        return "P-JINT-Weld-enabled-equal"
    if fixture_key.startswith("pulley-preparation-"):
        return "P-JINT-Pulley-slack-transition-preparation-" + fixture_key.rsplit("-", 1)[1]
    if fixture_key == "pulley-slack-transition":
        return "P-JINT-Pulley-slack-transition-main"
    raise Rejected("portable case mapping is absent")


def strict_comparison(fixture, reference, portable):
    return compare_stream(fixture, reference_records(reference),
                          records(portable, allow_tagged_nonfinite=True))


def projected_records(portable):
    grouping = None
    for row in records(portable, allow_tagged_nonfinite=True):
        kind = row.get("kind")
        if kind == "inputs":
            frozen = row.get("frozenInput")
            if not isinstance(frozen, dict):
                raise Rejected("frozen input projection is absent")
            grouping = frozen.get("grouping")
            yield frozen
        elif kind == "event":
            frozen = row.get("frozenEvent")
            if not isinstance(frozen, dict):
                raise Rejected("frozen event projection is absent")
            yield frozen
        elif kind == "action":
            frozen = row.get("frozenRecords")
            if not isinstance(frozen, list) or not frozen:
                raise Rejected("frozen action projection is absent")
            yield from frozen
        elif kind == "instrumented-callback":
            frozen = row.get("frozenRecord")
            if not isinstance(frozen, dict):
                raise Rejected("frozen instrumented callback projection is absent")
            yield frozen
        elif kind == "state":
            frozen = row.get("frozenState")
            if not isinstance(frozen, dict):
                raise Rejected("frozen state projection is absent")
            result = {"kind": "state", "step": row["step"], "state": frozen}
            if grouping:
                group = grouping["innerPerOuter"]
                result["outerStep"] = (row["step"] - 1) // group + 1
                result["innerWithinOuter"] = (row["step"] - 1) % group + 1
            yield result
        elif kind == "endpoint":
            if not grouping:
                raise Rejected("unexpected frozen outer endpoint")
            yield {"kind": "outer-endpoint", "step": row["step"],
                   "outerStep": row["step"] // grouping["innerPerOuter"],
                   "state": row["frozenState"]}
        elif kind != "case-end":
            raise Rejected(f"unknown portable record kind: {kind}")


def projected_comparison(fixture, reference, portable):
    return compare_stream(fixture, reference_records(reference), projected_records(portable))


def compare_stream(fixture, reference, candidate):
    result = {"status": "PASSED", "records": 0, "numeric_checks": 0,
              "exact_numeric_checks": 0, "derived_checks": 0,
              "unpassed_channels": set()}
    sentinel = object()
    try:
        for left, right in zip_longest(reference, candidate,
                                       fillvalue=sentinel):
            if left is sentinel or right is sentinel:
                raise Rejected("frozen record count differs")
            result["records"] += 1
            if left.get("kind") != right.get("kind"):
                raise Rejected(f"frozen record kind differs at {result['records']}")
            if zero_sign_differences(left, right, left["kind"], 1, fixture):
                raise Rejected(f"signed zero differs at frozen record {result['records']}")
            approved.compare_value(fixture, left, right, left["kind"], result)
        if result["unpassed_channels"]:
            result["status"] = "UNPASSED"
    except (Rejected, approved.Rejected, OSError, EOFError, KeyError, TypeError, ValueError) as error:
        result["status"] = "FAILED"
        result["reason"] = str(error)
    result["unpassed_channels"] = sorted(result["unpassed_channels"])
    for key in ("_rule_cache", "_exact_cache", "_zero_cache", "_derived_paths"):
        result.pop(key, None)
    return result


def diagnostic(fixture_key, reference, portable):
    catalog = json.loads(CATALOG.read_text())
    fixtures = [item for item in catalog["fixtures"] if item["key"] == fixture_key]
    if len(fixtures) != 1:
        raise Rejected("fixture key is absent or duplicated")
    fixture = fixtures[0]
    approved_fixture = approved.load_fixture(fixture_key)
    if fixture_key == "nominal-free-motion":
        approved_fixture = fixture_with_nominal_timestep_rule(approved_fixture)
    if fixture_key.startswith("default-sleep-"):
        approved_fixture = fixture_with_default_sleep_rules(approved_fixture)
    if digest(reference) != fixture["reference"]["gzip_sha256"]:
        raise Rejected("frozen reference gzip SHA-256 differs")
    with gzip.open(reference, "rb") as stream:
        first = stream.readline()
    if hashlib.sha256(first.rstrip(b"\n")).hexdigest() != fixture["reference"]["input_sha256"]:
        raise Rejected("frozen input line SHA-256 differs")
    strict = strict_comparison(approved_fixture, reference, portable)
    projected = projected_comparison(approved_fixture, reference, portable)
    step_events = step_event_diagnostic(reference, portable)
    frozen_events = frozen_event_diagnostic(reference, portable)
    auxiliary = auxiliary_record_diagnostic(reference, portable)
    nominal_zero = (nominal_zero_diagnostic(reference, portable)
                    if fixture_key == "nominal-free-motion" else None)
    nominal_timestep = (nominal_timestep_diagnostic(reference, portable)
                        if fixture_key == "nominal-free-motion" else None)
    default_timestep = (default_timestep_diagnostic(reference, portable,
                        int(fixture_key.rsplit("-", 1)[1]))
                        if fixture_key.startswith("default-sleep-") else None)
    default_rotation = (default_rotation_premise_diagnostic(reference, portable,
                        int(fixture_key.rsplit("-", 1)[1]))
                        if fixture_key.startswith("default-sleep-") else None)
    ref = iter(reference_records(reference))
    wanted = portable_case_id(fixture_key)
    port = (row for row in records(portable, allow_tagged_nonfinite=True) if row.get("id") == wanted)
    try:
        ref_header = next(ref)
        port_header = next(port)
    except StopIteration as error:
        raise Rejected("reference or matching portable input is absent") from error
    header_exact = exact(ref_header, port_header)
    input_schema_differences = structural_differences(ref_header, port_header, "inputs")
    frozen_input = port_header.get("frozenInput")
    frozen_input_projection = {
        "exact": exact(ref_header, frozen_input),
        "structural_differences": structural_differences(ref_header, frozen_input, "inputs"),
        "value_differences": value_differences(ref_header, frozen_input, "inputs"),
        "signed_zero_paths": zero_sign_differences(ref_header, frozen_input, "inputs"),
    } if isinstance(frozen_input, dict) else {"status": "ABSENT"}
    projection = port_header.get("frozenConfiguration", {})
    configuration = {}
    for name in ("settings", "world", "state"):
        part = projection.get(name)
        configuration[name] = {
            "exact": exact(ref_header[name], part),
            "structural_differences": structural_differences(ref_header[name], part, name),
            "value_differences": value_differences(ref_header[name], part, name),
        }
    events = {"reference": 0, "portable": 0}

    def states(stream, label):
        for row in stream:
            if row.get("kind") in ("event", "instrumented-callback"):
                events[label] += 1
            if row.get("kind") == "state":
                yield row

    checked = 0
    exact_values = 0
    differing_values = 0
    maxima = {name: 0.0 for name in CHANNELS if name != "atRest"}
    first_differences = []
    approved_result = {"numeric_checks": 0, "exact_numeric_checks": 0,
                       "derived_checks": 0, "unpassed_channels": set()}
    full_state_result = {"numeric_checks": 0, "exact_numeric_checks": 0,
                         "derived_checks": 0, "unpassed_channels": set()}
    full_state_failed_steps = 0
    full_state_first_failures = []
    full_state_zero_sign_paths = []
    approved_failure_count = 0
    approved_failures = []
    signed_zero_differences = 0
    for baseline, candidate in zip_longest(states(ref, "reference"), states(port, "portable")):
        if baseline is None or candidate is None:
            raise Rejected("state count differs")
        if baseline.get("step") != candidate.get("step"):
            raise Rejected(f"state step differs: {baseline.get('step')} versus {candidate.get('step')}")
        checked += 1
        try:
            if not isinstance(candidate.get("frozenState"), dict):
                raise Rejected("frozen state projection is absent")
            signs = zero_sign_differences(baseline["state"], candidate["frozenState"],
                                          "state.state", fixture=approved_fixture)
            if signs:
                full_state_zero_sign_paths.extend(signs[:max(0, 20 - len(full_state_zero_sign_paths))])
                raise Rejected("signed zero differs in frozen state projection")
            approved.compare_value(approved_fixture, baseline["state"],
                                   candidate["frozenState"], "state.state", full_state_result)
        except (Rejected, approved.Rejected, KeyError, TypeError, ValueError) as error:
            full_state_failed_steps += 1
            if len(full_state_first_failures) < 20:
                full_state_first_failures.append({"step": checked, "reason": str(error)})
        left_bodies = baseline["state"]["bodies"]
        right_bodies = candidate["state"]["bodies"]
        if len(left_bodies) != len(right_bodies):
            raise Rejected(f"body count differs at step {checked}")
        for index, (left, right) in enumerate(zip(left_bodies, right_bodies)):
            if left["id"] != right["id"]:
                raise Rejected(f"body identity differs at step {checked}")
            for name in CHANNELS:
                a, b = channel(left, name), channel(right, name)
                if (isinstance(a, (int, float)) and isinstance(b, (int, float)) and
                    a == b == 0 and not exact(a, b)):
                    signed_zero_differences += 1
                if exact(a, b):
                    exact_values += 1
                else:
                    differing_values += 1
                    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and math.isfinite(a) and math.isfinite(b):
                        if name != "atRest":
                            maxima[name] = max(maxima[name], abs(a - b))
                    if len(first_differences) < 20:
                        first_differences.append({"step": checked, "body": index, "channel": name,
                                                  "reference": a, "portable": b})
                try:
                    approved.compare_value(approved_fixture, a, b, RULE_PATHS[name], approved_result)
                except approved.Rejected as error:
                    approved_failure_count += 1
                    if len(approved_failures) < 20:
                        approved_failures.append({"step": checked, "body": index,
                                                  "channel": name, "reason": str(error)})
    status = ("FAILED_APPROVED_PROJECTION" if projected["status"] == "FAILED" or
              approved_failure_count or signed_zero_differences or
              (nominal_zero is not None and nominal_zero["status"] != "PASSED") or
              (nominal_timestep is not None and nominal_timestep["status"] != "PASSED") or
              (default_timestep is not None and default_timestep["status"] != "PASSED") or
              (default_rotation is not None and default_rotation["status"] != "PASSED") else
              "UNPASSED_RULES" if projected["status"] == "UNPASSED" else
              "PASSED_APPROVED_PROJECTION")
    return {"status": status,
            "fixture_key": fixture_key, "reference_sha256": digest(reference),
            "portable_sha256": digest(portable), "input_header_exact": header_exact,
            "input_schema_differences": input_schema_differences,
            "frozen_input_projection": frozen_input_projection,
            "frozen_configuration_projection": configuration,
            "strict_approved_comparison": strict,
            "projected_approved_comparison": projected,
            "step_event_projection": step_events,
            "frozen_event_projection": frozen_events,
            "auxiliary_record_projection": auxiliary,
            "nominal_zero_invariant": nominal_zero,
            "nominal_timestep_invariant": nominal_timestep,
            "default_timestep_invariant": default_timestep,
            "default_rotation_premise": default_rotation,
            "state_steps_compared": checked, "exact_values": exact_values,
            "differing_values": differing_values, "max_absolute_differences": maxima,
            "event_records": events, "first_differences": first_differences,
            "signed_zero_differences": signed_zero_differences,
            "approved_channel_checks": {"numeric_checks": approved_result["numeric_checks"],
                                        "exact_numeric_checks": approved_result["exact_numeric_checks"],
                                        "unpassed_channels": sorted(approved_result["unpassed_channels"]),
                                        "failed_checks": approved_failure_count,
                                        "first_failures": approved_failures},
            "tolerances_applied": bool(approved_result["numeric_checks"]),
            "frozen_state_projection": {"checked_steps": checked,
                "status": ("FAILED" if full_state_failed_steps or full_state_zero_sign_paths else
                           "UNPASSED_RULES" if full_state_result["unpassed_channels"] else "PASSED"),
                "failed_steps": full_state_failed_steps,
                "first_failures": full_state_first_failures,
                "signed_zero_paths": full_state_zero_sign_paths,
                "numeric_checks": full_state_result["numeric_checks"],
                "exact_numeric_checks": full_state_result["exact_numeric_checks"],
                "derived_checks": full_state_result["derived_checks"],
                "unpassed_channels": sorted(full_state_result["unpassed_channels"])},
            "qualification": "UNPASSED"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--portable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = diagnostic(args.fixture, args.reference, args.portable)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
