import argparse
import fnmatch
import gzip
import hashlib
import json
import math
import re
from collections import Counter
from fractions import Fraction
from functools import lru_cache
from itertools import zip_longest
from math import factorial, isqrt
from pathlib import Path


class Rejected(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Rejected(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse(line):
    try:
        item = json.loads(line, object_pairs_hook=no_duplicates,
                          parse_constant=lambda value: (_ for _ in ()).throw(Rejected(f"nonfinite token: {value}")))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise Rejected(f"invalid JSON: {error}") from error
    if not isinstance(item, dict):
        raise Rejected("record is not an object")
    finite(item)
    return item


def finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise Rejected("nonfinite number")
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) > 2**53:
        raise Rejected("unsafe JSON integer")
    if isinstance(value, dict):
        for child in value.values():
            finite(child)
    elif isinstance(value, list):
        for child in value:
            finite(child)


def records(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rb") as stream:
        for line in stream:
            if not line.endswith(b"\n"):
                raise Rejected("record has no newline")
            yield line, parse(line)


def load_receipt(path, candidate, fixture, source, artifact, commit, counts):
    receipt = parse(Path(path).read_bytes())
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or receipt.get("candidate_commit") != commit:
        raise Rejected("candidate commit identity differs")
    if not all(re.fullmatch(r"[0-9a-f]{64}", value) for value in (source, artifact)):
        raise Rejected("candidate source or artifact digest is malformed")
    if receipt.get("source_sha256") != source or receipt.get("artifact_sha256") != artifact:
        raise Rejected("candidate source or artifact identity differs")
    if (receipt.get("reference_source_revision") != fixture["baseline_source_revision"] or
        receipt.get("reference_artifact_sha256") != fixture["baseline_jar_sha256"] or
        receipt.get("reference_trace_sha256") != fixture["reference"]["gzip_sha256"]):
        raise Rejected("frozen source, artifact, or reference identity differs")
    if receipt.get("trace_sha256") != digest(Path(candidate).read_bytes()):
        raise Rejected("candidate trace hash differs")
    for field in ("expected_counts", "executed_counts"):
        if receipt.get(field) != counts:
            raise Rejected(f"{field} differs from frozen counts")
    if receipt.get("skipped") != 0:
        raise Rejected("suite has skipped cases")
    if not any(value > 0 for kind, value in counts.items() if kind != "inputs"):
        raise Rejected("suite is empty")


def check_translation_aliases(state):
    for body in state["bodies"]:
        for name in ("transform", "previousTransform"):
            if name not in body:
                continue
            transform = body[name]
            translation = transform["getTranslation"]
            if (len(translation) != 2 or transform["getTranslationX"] != translation[0] or
                transform["getTranslationY"] != translation[1]):
                raise Rejected("translation getter alias differs")
            if "getValues" in transform:
                values = transform["getValues"]
                if (len(values) != 6 or values[2] != translation[0] or
                    values[5] != translation[1] or values[0] != transform["getCost"] or
                    values[1] != -transform["getSint"] or
                    values[3] != transform["getSint"] or values[4] != transform["getCost"]):
                    raise Rejected("matrix getter alias differs")
        if "fixedOriginPosition" in body and body["fixedOriginPosition"] != body["transform"]["getTranslation"]:
            raise Rejected("fixed origin position alias differs")
        if "worldCenter" in body and body["worldCenter"] != body["transform"]["getTranslation"]:
            raise Rejected("world center alias differs")


def check_counts(rows, fixture, *, reference):
    counts = Counter()
    state_step = fixture.get("start_step", 0)
    event_step = 0
    event_order = -1
    input_seen = False
    input_hash = None
    last_state = None
    for line, row in rows:
        kind = row.get("kind")
        if kind not in fixture["counts"]:
            raise Rejected(f"unexpected record kind: {kind}")
        counts[kind] += 1
        if kind == "inputs":
            if input_seen or sum(counts.values()) != 1 or row.get("id") != fixture["id"]:
                raise Rejected("wrong input order or fixture identity")
            input_seen = True
            input_hash = digest(line[:-1])
        elif not input_seen:
            raise Rejected("record precedes input")
        if kind == "state":
            state_step += 1
            if row.get("step") != state_step:
                raise Rejected("missing or reordered state")
            last_state = row.get("state")
            if fixture.get("check_translation_aliases"):
                check_translation_aliases(last_state)
        if kind == "outer-endpoint":
            group = fixture.get("inner_per_outer")
            if (type(group) is not int or group <= 0 or state_step % group or
                row.get("step") != state_step or row.get("outerStep") != state_step // group or
                row.get("state") != last_state):
                raise Rejected("outer endpoint does not copy the matching inner state")
        if kind == "event":
            step, order = row.get("step"), row.get("order")
            if type(step) is not int or type(order) is not int or step < event_step or order < 0:
                raise Rejected("invalid event step or order")
            if step == event_step and order <= event_order:
                raise Rejected("event order is not increasing")
            if step > event_step:
                event_order = -1
            event_step, event_order = step, order
        if counts[kind] > fixture["counts"][kind]:
            raise Rejected(f"too many {kind} records")
    if dict(counts) != fixture["counts"]:
        raise Rejected(f"incomplete suite: {dict(counts)}")
    if reference and input_hash != fixture["reference"]["input_sha256"]:
        raise Rejected("frozen input hash differs")
    return dict(counts)


def audit_reference(fixture, path):
    try:
        path = Path(path)
        expected = fixture["reference"]
        if path.name != expected["file"] or digest(path.read_bytes()) != expected["gzip_sha256"]:
            raise Rejected("frozen reference file or hash differs")
        stream_hash = hashlib.sha256()

        def audited():
            for line, row in records(path):
                stream_hash.update(line)
                yield line, row

        counts = check_counts(audited(), fixture, reference=True)
        if stream_hash.hexdigest() != expected["stream_sha256"]:
            raise Rejected("frozen decompressed stream hash differs")
        return {"status": "PASSED", "scope": "FROZEN_BASELINE_ONLY", "counts": counts}
    except (Rejected, OSError, EOFError, gzip.BadGzipFile, KeyError, TypeError) as error:
        return {"status": "FAILED", "scope": "FROZEN_BASELINE_ONLY", "reason": str(error)}


def rule_for(fixture, path, result):
    cache = result.setdefault("_rule_cache", {})
    if path in cache:
        return cache[path]
    matches = [rule for rule in fixture.get("rules", []) if matches_path(path, rule["path"])]
    if len(matches) > 1:
        raise Rejected(f"ambiguous numeric rule: {path}")
    cache[path] = matches[0] if matches else None
    return cache[path]


def matches_path(path, pattern):
    return fnmatch.fnmatchcase(path.replace("[]", "{array}"), pattern.replace("[]", "{array}"))


@lru_cache(maxsize=1)
def pi_bounds():
    def arctan_reciprocal(denominator):
        subtotal = sum((Fraction(1 if index % 2 == 0 else -1,
                                 (2 * index + 1) * denominator ** (2 * index + 1))
                        for index in range(50)), Fraction(0))
        return subtotal, subtotal + Fraction(1, 101 * denominator ** 101)

    low5, high5 = arctan_reciprocal(5)
    low239, high239 = arctan_reciprocal(239)
    return 16 * low5 - 4 * high239, 16 * high5 - 4 * low239


def orientation_error_bounds(reference, candidate):
    if abs(reference) > 4 or abs(candidate) > 4:
        raise Rejected("orientation outside certified wrap domain")
    difference = Fraction.from_float(float(candidate)) - Fraction.from_float(float(reference))
    pi_low, pi_high = pi_bounds()
    bounds = []
    for turns in range(-2, 3):
        endpoints = (difference - 2 * turns * pi_low,
                     difference - 2 * turns * pi_high)
        low, high = min(endpoints), max(endpoints)
        lower = Fraction(0) if low <= 0 <= high else min(abs(low), abs(high))
        bounds.append((lower, max(abs(low), abs(high))))
    return min(pair[0] for pair in bounds), min(pair[1] for pair in bounds)


def sqrt_bounds(value):
    scale = 10**70
    scaled = value * scale * scale
    floor = isqrt(scaled.numerator // scaled.denominator)
    low = Fraction(floor, scale)
    high = low if low * low == value else Fraction(floor + 1, scale)
    return low, high


@lru_cache(maxsize=16)
def tangent_bounds(angle):
    if angle < 0 or angle >= 1:
        raise Rejected("direction cap outside certified domain")
    sine = sum(((-1)**index * angle**(2 * index + 1) / factorial(2 * index + 1)
                for index in range(10)), Fraction(0))
    cosine = sum(((-1)**index * angle**(2 * index) / factorial(2 * index)
                  for index in range(10)), Fraction(0))
    sine_high = sine + angle**21 / factorial(21)
    cosine_high = cosine + angle**20 / factorial(20)
    if cosine <= 0:
        raise Rejected("direction cap has invalid cosine enclosure")
    return sine / cosine_high, sine_high / cosine


def check_direction(reference, candidate, rule, path, result):
    if len(reference) != 2 or not all(type(value) in (int, float) and math.isfinite(value)
                                           for value in reference + candidate):
        raise Rejected(f"invalid direction: {path}")
    left = tuple(Fraction.from_float(float(value)) for value in reference)
    right = tuple(Fraction.from_float(float(value)) for value in candidate)
    left_square = left[0]**2 + left[1]**2
    right_square = right[0]**2 + right[1]**2
    if left_square == 0 or right_square == 0:
        if left != right or left_square != 0:
            raise Rejected(f"direction placeholder differs: {path}")
        result["numeric_checks"] += 3
        return
    angle_cap = Fraction(str(rule["absolute"]))
    magnitude_cap = Fraction(str(rule["magnitude_absolute"]))
    unit_cap = Fraction(str(rule["unit_deviation"]))
    if min(angle_cap, magnitude_cap, unit_cap) < 0 or unit_cap >= 1:
        raise Rejected(f"invalid direction limit: {path}")
    if left == right:
        if not (1 - unit_cap)**2 <= left_square <= (1 + unit_cap)**2:
            raise Rejected(f"direction is not unit length: {path}")
        result["numeric_checks"] += 3
        return
    dot = left[0] * right[0] + left[1] * right[1]
    cross = abs(left[0] * right[1] - left[1] * right[0])
    if dot <= 0:
        raise Rejected(f"direction angle exceeded: {path}")
    tangent_low, tangent_high = tangent_bounds(angle_cap)
    ratio = cross / dot
    if ratio > tangent_high:
        raise Rejected(f"direction angle exceeded: {path}")
    if ratio > tangent_low:
        result["unpassed_channels"].add(path)
    left_low, left_high = sqrt_bounds(left_square)
    right_low, right_high = sqrt_bounds(right_square)
    difference_low = max(Fraction(0), right_low - left_high, left_low - right_high)
    difference_high = max(abs(right_low - left_high), abs(right_high - left_low))
    if difference_low > magnitude_cap:
        raise Rejected(f"direction magnitude exceeded: {path}")
    if difference_high > magnitude_cap:
        result["unpassed_channels"].add(path)
    for low, high in ((left_low, left_high), (right_low, right_high)):
        if high < 1 - unit_cap or low > 1 + unit_cap:
            raise Rejected(f"direction is not unit length: {path}")
        if low < 1 - unit_cap or high > 1 + unit_cap:
            result["unpassed_channels"].add(path)
    result["numeric_checks"] += 3


def compare_value(fixture, reference, candidate, path, result):
    if type(reference) is not type(candidate) and not (
        type(reference) in (int, float) and type(candidate) in (int, float)
    ):
        raise Rejected(f"type differs: {path}")
    if isinstance(reference, dict):
        if set(reference) != set(candidate):
            raise Rejected(f"fields differ: {path}")
        for key in reference:
            compare_value(fixture, reference[key], candidate[key], f"{path}.{key}" if path else key, result)
    elif isinstance(reference, list):
        if len(reference) != len(candidate):
            raise Rejected(f"length differs: {path}")
        if path == "state.state.bodies":
            for left, right in zip(reference, candidate):
                if left.get("id") == "b0" and left != right:
                    raise Rejected("fixed floor differs")
        rule = rule_for(fixture, path, result)
        if rule and rule["metric"] == "direction":
            check_direction(reference, candidate, rule, path, result)
            return
        for left, right in zip(reference, candidate):
            compare_value(fixture, left, right, path + "[]", result)
    elif type(reference) in (int, float):
        rule = rule_for(fixture, path, result)
        if rule:
            absolute, relative = rule["absolute"], rule["relative"]
            if not all(type(value) in (int, float) and math.isfinite(value) and value >= 0
                       for value in (absolute, relative)):
                raise Rejected(f"invalid numeric limit: {path}")
            if rule["metric"] not in ("scalar", "orientation"):
                raise Rejected(f"unknown metric: {path}")
            if reference == candidate:
                if rule["metric"] == "orientation" and abs(reference) > 4:
                    raise Rejected("orientation outside certified wrap domain")
                result["numeric_checks"] += 1
                return
            cap = Fraction(str(absolute)) + Fraction(str(relative)) * abs(Fraction.from_float(float(reference)))
            if rule["metric"] == "orientation":
                lower, upper = orientation_error_bounds(reference, candidate)
            else:
                lower = upper = abs(Fraction.from_float(float(candidate)) - Fraction.from_float(float(reference)))
            if lower > cap:
                raise Rejected(f"numeric limit exceeded: {path}")
            if upper > cap:
                result["unpassed_channels"].add(path)
            result["numeric_checks"] += 1
        elif is_exact_numeric(fixture, path, result):
            if reference != candidate:
                raise Rejected(f"exact numeric field differs: {path}")
            result["exact_numeric_checks"] += 1
        else:
            result["unpassed_channels"].add(path)
    elif reference != candidate:
        raise Rejected(f"exact field differs: {path}")


def is_exact_numeric(fixture, path, result):
    cache = result.setdefault("_exact_cache", {})
    if path not in cache:
        cache[path] = any(matches_path(path, pattern) for pattern in fixture.get("exact_numeric", []))
    return cache[path]


def compare(fixture, reference, candidate, receipt, expected_source, expected_artifact, expected_commit):
    baseline = audit_reference(fixture, reference)
    if baseline["status"] != "PASSED":
        return {"status": "FAILED", "reason": baseline["reason"]}
    result = {"status": "PASSED", "numeric_checks": 0, "exact_numeric_checks": 0,
              "unpassed_channels": set(), "counts": fixture["counts"]}
    try:
        load_receipt(receipt, candidate, fixture, expected_source, expected_artifact,
                     expected_commit, fixture["counts"])
        check_counts(records(candidate), fixture, reference=False)
        missing = object()
        for left, right in zip_longest(records(reference), records(candidate), fillvalue=missing):
            if left is missing or right is missing:
                raise Rejected("record count differs")
            if left[1]["kind"] != right[1]["kind"]:
                raise Rejected("record kind order differs")
            compare_value(fixture, left[1], right[1], left[1]["kind"], result)
        if result["unpassed_channels"]:
            result["status"] = "UNPASSED"
        result["unpassed_channels"] = sorted(result["unpassed_channels"])
        result.pop("_rule_cache", None)
        result.pop("_exact_cache", None)
        return result
    except (Rejected, OSError, EOFError, gzip.BadGzipFile, KeyError, TypeError) as error:
        return {"status": "FAILED", "reason": str(error)}


def load_fixture(key):
    catalog = json.loads(Path(__file__).with_name("fixtures.json").read_text())
    item = next(item for item in catalog["fixtures"] if item["key"] == key)
    return {**catalog["profiles"][item["profile"]], **item,
            "baseline_source_revision": catalog["baseline_source_revision"],
            "baseline_jar_sha256": catalog["baseline_jar_sha256"]}


def main():
    parser = argparse.ArgumentParser(description="Audit and compare frozen numerical traces")
    parser.add_argument("mode", choices=("audit-reference", "compare"))
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--candidate")
    parser.add_argument("--receipt")
    parser.add_argument("--expected-source")
    parser.add_argument("--expected-artifact")
    parser.add_argument("--expected-commit")
    args = parser.parse_args()
    fixture = load_fixture(args.fixture)
    if args.mode == "audit-reference":
        outcome = audit_reference(fixture, args.reference)
    else:
        if not all((args.candidate, args.receipt, args.expected_source,
                    args.expected_artifact, args.expected_commit)):
            parser.error("compare requires candidate, receipt, expected source, artifact and commit")
        outcome = compare(fixture, args.reference, args.candidate, args.receipt,
                          args.expected_source, args.expected_artifact, args.expected_commit)
    print(json.dumps(outcome, sort_keys=True))
    raise SystemExit(0 if outcome["status"] == "PASSED" else 1)


if __name__ == "__main__":
    main()
