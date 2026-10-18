import json
import math
from itertools import zip_longest
from pathlib import Path

from cases import declared_cases
from reference_diagnostic import structural_differences, value_differences
from receipt import Rejected, digest, exact, records


class Difference(Rejected):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status


def load_policy_catalog(path=None):
    source = Path(path) if path is not None else Path(__file__).with_name(
        "prospective_policy_catalog.json")
    return json.loads(source.read_text())


def verify_policy_catalog(catalog, manifest, cases, frozen_ids):
    if catalog.get("schema") != "portable-prospective-policy-proposal/1" or \
            catalog.get("qualification") != "UNPASSED":
        raise Rejected("prospective policy catalog is not an unratified proposal")
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
    paths = catalog.get("paths")
    path_sets = catalog.get("path_sets")
    proposals = catalog.get("rule_proposals")
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


def compare_host(baseline, lane, frozen_ids):
    from baseline_capture import PINNED_JAR_SHA256, fixture_source_sha256, verify_case_slices

    manifest = json.loads((Path(baseline) / "verified.json").read_text())
    cases = declared_cases()
    expected = {case["id"] for case in cases}
    verify_baseline_manifest(manifest, expected, PINNED_JAR_SHA256, fixture_source_sha256())
    verify_baseline_bytes(baseline, manifest)
    catalog = load_policy_catalog()
    verify_policy_catalog(catalog, manifest, cases, frozen_ids)
    receipt = json.loads((Path(lane) / "receipt.json").read_text())
    if receipt.get("schema") != "portable-numerical-receipt/1" or \
            receipt.get("counts", {}).get("executed_cases") != len(cases) or \
            receipt.get("counts", {}).get("states") != sum(case["steps"] for case in cases) or \
            receipt.get("trace_sha256") != digest(Path(lane) / "trace.jsonl"):
        raise Rejected("candidate host receipt is incomplete or stale")
    verify_case_slices(Path(lane), expected)
    prospective = [case for case in cases if case["id"] not in frozen_ids]
    results = []
    for case in prospective:
        case_id = case["id"]
        reference = Path(baseline) / "baseline-jvm/cases" / f"{case_id}.jsonl"
        candidate = Path(lane) / "cases" / f"{case_id}.jsonl"
        verify_reference_inventory(reference, case_id, catalog)
        results.append(compare_case(reference, candidate, case))
    if len(results) != len(expected - set(frozen_ids)):
        raise Rejected("prospective case coverage differs")
    summary = {"status": "UNPASSED", "qualification": "UNPASSED",
               "baseline_jar_sha256": manifest["baseline_jar_sha256"],
               "baseline_trace_sha256": manifest["trace_sha256"],
               "baseline_fixture_source_sha256": manifest["fixture_source_sha256"],
               "candidate_trace_sha256": receipt["trace_sha256"],
               "cases": len(results),
               "exact_diagnostic": sum(row["status"] == "EXACT_DIAGNOSTIC" for row in results),
               "unpassed_numeric": sum(row["status"] == "UNPASSED_NUMERICAL_POLICY" for row in results),
               "failed": sum(row["status"].startswith("FAILED") for row in results),
               "results": results}
    (Path(lane) / "prospective-comparison.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary
