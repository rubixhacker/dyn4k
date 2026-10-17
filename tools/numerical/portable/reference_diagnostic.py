import argparse
import gzip
import hashlib
import json
import math
import sys
from itertools import zip_longest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.dont_write_bytecode = True
import compare as approved

from receipt import Rejected, digest, exact, records


CATALOG = Path(__file__).resolve().parents[1] / "fixtures.json"
CHANNELS = ("transform.getTranslation.0", "transform.getTranslation.1",
            "previousTransform.getTranslation.0", "previousTransform.getTranslation.1",
            "velocity.0", "velocity.1", "angularVelocity", "rotationIncrementSum", "atRest")
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


def zero_sign_differences(reference, candidate, path="", limit=20):
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
            if len(differences) < limit:
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
    result = {"status": "PASSED", "records": 0, "numeric_checks": 0,
              "exact_numeric_checks": 0, "derived_checks": 0,
              "unpassed_channels": set()}
    sentinel = object()
    try:
        for left, right in zip_longest(reference_records(reference),
                                       records(portable, allow_tagged_nonfinite=True),
                                       fillvalue=sentinel):
            if left is sentinel or right is sentinel:
                raise Rejected("frozen record count differs")
            result["records"] += 1
            if left.get("kind") != right.get("kind"):
                raise Rejected(f"frozen record kind differs at {result['records']}")
            def zero_sign(left_value, right_value):
                if (type(left_value) in (int, float) and type(right_value) in (int, float) and
                        left_value == right_value == 0 and not exact(left_value, right_value)):
                    raise Rejected(f"signed zero differs at frozen record {result['records']}")
                if isinstance(left_value, dict) and isinstance(right_value, dict):
                    for key in left_value.keys() & right_value.keys():
                        zero_sign(left_value[key], right_value[key])
                elif isinstance(left_value, list) and isinstance(right_value, list):
                    for a, b in zip(left_value, right_value):
                        zero_sign(a, b)
            zero_sign(left, right)
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
    if digest(reference) != fixture["reference"]["gzip_sha256"]:
        raise Rejected("frozen reference gzip SHA-256 differs")
    with gzip.open(reference, "rb") as stream:
        first = stream.readline()
    if hashlib.sha256(first.rstrip(b"\n")).hexdigest() != fixture["reference"]["input_sha256"]:
        raise Rejected("frozen input line SHA-256 differs")
    strict = strict_comparison(approved_fixture, reference, portable)
    step_events = step_event_diagnostic(reference, portable)
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
                                          "state.state")
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
    return {"status": ("FAILED_APPROVED_CHANNEL" if approved_failure_count or signed_zero_differences else
                       "UNPASSED_INPUT_SCHEMA" if not header_exact else "UNPASSED_EVENT_SCHEMA"),
            "fixture_key": fixture_key, "reference_sha256": digest(reference),
            "portable_sha256": digest(portable), "input_header_exact": header_exact,
            "input_schema_differences": input_schema_differences,
            "frozen_input_projection": frozen_input_projection,
            "frozen_configuration_projection": configuration,
            "strict_approved_comparison": strict,
            "step_event_projection": step_events,
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
