import argparse
import gzip
import hashlib
import json
import math
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

from compare import Rejected, parse


CALLBACKS = ("begin", "postSolve", "end")
U = 2 ** -53


def sha(data):
    return hashlib.sha256(data).hexdigest()


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise Rejected("missing or nonfinite numeric field")
    return Decimal.from_float(float(value))


def vector(value):
    if not isinstance(value, list) or len(value) != 2:
        raise Rejected("missing vector component")
    return tuple(number(item) for item in value)


def distance(a, b):
    x, y = vector(a)
    p, q = vector(b)
    return ((x - p) ** 2 + (y - q) ** 2).sqrt()


def limit(declaration, case, name):
    rule = declaration["cases"][case]["metrics"][name]
    if rule["relative_limit"] != "0":
        raise Rejected("physical quality requires zero relative allowance")
    result = Decimal(rule["absolute_limit"])
    if not result.is_finite() or result <= 0:
        raise Rejected("invalid physical limit")
    return result


def phases(declaration):
    current = 1
    for name, first, last in declaration["phases"]:
        if name not in ("excitation", "long-run") or type(first) is not int or type(last) is not int or first != current or last < first:
            raise Rejected("physical phase schedule has a gap")
        current = last + 1
    if current - 1 != declaration["steps_per_case"]:
        raise Rejected("physical phase schedule does not cover all states")


def weld(state):
    bodies = state["bodies"]
    joint = state["joint"]
    if ([body["id"] for body in bodies] != ["ground", "member"] or
        joint["type"] != "WeldJoint" or joint["spring"] is not True or
        joint["limits"] is not True or number(joint["referenceAngle"]) != 0 or
        number(joint["frequency"]) != 8 or number(joint["dampingRatio"]) != Decimal.from_float(0.3) or
        number(joint["lowerLimit"]) != 0 or number(joint["upperLimit"]) != 0):
        raise Rejected("weld structure or mode differs")
    fixed, moving = bodies
    if (vector(fixed["center"]) != (0, 0) or number(fixed["angle"]) != 0 or
        number(fixed["cost"]) != 1 or number(fixed["sint"]) != 0 or
        vector(joint["anchor1"]) != (Decimal("-0.5"), Decimal(2))):
        raise Rejected("fixed weld body or anchor differs")
    center = vector(moving["center"])
    cosine, sine = number(moving["cost"]), number(moving["sint"])
    anchor = vector(joint["anchor2"])
    expected = (center[0] - cosine / 2, center[1] - sine / 2)
    for observed, formula in zip(anchor, expected):
        allowance = Decimal.from_float(8 * U) * (abs(formula) + abs(center[0]) + abs(center[1]) + 1)
        if abs(observed - formula) > allowance:
            raise Rejected("weld moving anchor does not follow stored transform")
    angle = float(number(moving["angle"]) - number(fixed["angle"]))
    return {"anchor_gap_m": distance(joint["anchor1"], joint["anchor2"]),
            "angular_error_rad": Decimal.from_float(abs(math.remainder(angle, 2 * math.pi)))}


def pulley(state):
    bodies = state["bodies"]
    joint = state["joint"]
    if ([body["id"] for body in bodies] != ["left", "right"] or
        joint["type"] != "PulleyJoint" or joint["slack"] is not False or
        number(joint["ratio"]) != 1 or number(joint["length"]) != 2 or
        vector(joint["pulleyAnchor1"]) != (Decimal(-1), Decimal(1)) or
        vector(joint["pulleyAnchor2"]) != (Decimal(1), Decimal(1))):
        raise Rejected("pulley structure, anchors, ratio, or mode differs")
    if vector(joint["anchor1"]) != vector(bodies[0]["center"]) or vector(joint["anchor2"]) != vector(bodies[1]["center"]):
        raise Rejected("pulley body-anchor alias differs")
    with localcontext() as context:
        context.prec = 80
        length1 = distance(joint["anchor1"], joint["pulleyAnchor1"])
        length2 = distance(joint["anchor2"], joint["pulleyAnchor2"])
        return {"absolute_rope_error_m": abs(length1 + length2 - Decimal(2))}


def audit_quality(declaration, manifest, case, path):
    try:
        phases(declaration)
        expected = manifest["cases"][case]
        if (case not in declaration["cases"] or
            manifest["baseline_source_revision"] != declaration["baseline_source_revision"] or
            manifest["baseline_jar_sha256"] != declaration["baseline_jar_sha256"]):
            raise Rejected("baseline source, JAR, or case identity differs")
        path = Path(path)
        raw = path.read_bytes()
        if path.name != expected["file"] or sha(raw) != expected["gzip_sha256"]:
            raise Rejected("frozen gzip member identity differs")
        stream = gzip.decompress(raw)
        if sha(stream) != expected["stream_sha256"]:
            raise Rejected("frozen stream identity differs")
        lines = stream.splitlines(keepends=True)
        if not lines or any(not line.endswith(b"\n") for line in lines):
            raise Rejected("empty or incomplete JSONL stream")
        if sha(lines[0][:-1]) != expected["input_sha256"]:
            raise Rejected("frozen input identity differs")
        header = parse(lines[0])
        required = {"kind": "inputs", "case": case,
                    "declaration_sha256": manifest["declaration_sha256"],
                    "capture_sha256": manifest["capture_sha256"],
                    "source_revision": declaration["baseline_source_revision"],
                    "jar_sha256": declaration["baseline_jar_sha256"],
                    "step_seconds": declaration["step_seconds"],
                    "steps": declaration["steps_per_case"]}
        if header != required:
            raise Rejected("input header or source/artifact identity differs")
        expected_counts = {"inputs": 1, "event": 3 * declaration["steps_per_case"],
                           "state": declaration["steps_per_case"]}
        if expected["counts"] != expected_counts or not expected_counts["state"]:
            raise Rejected("empty, skipped, or incomplete declared suite")
        rows = [parse(line) for line in lines[1:]]
        if len(rows) != expected_counts["event"] + expected_counts["state"]:
            raise Rejected("incomplete executed counts")
        metrics = {key: {"checked": 0, "failed": 0, "maximum": "0", "first_failure": None}
                   for key in declaration["cases"][case]["metrics"]}
        for step in range(1, declaration["steps_per_case"] + 1):
            base = (step - 1) * 4
            for order, callback in enumerate(CALLBACKS):
                if rows[base + order] != {"kind": "event", "step": step, "order": order, "callback": callback}:
                    raise Rejected("callback identity or order differs")
            row = rows[base + 3]
            if row.keys() != {"kind", "step", "state"} or row["kind"] != "state" or row["step"] != step:
                raise Rejected("state identity or order differs")
            values = weld(row["state"]) if case == "weld-spring-equal" else pulley(row["state"])
            phase = "excitation" if step <= declaration["phases"][0][2] else "long-run"
            for name, value in values.items():
                item = metrics[name]
                item["checked"] += 1
                if value > Decimal(item["maximum"]):
                    item["maximum"] = str(value)
                if value > limit(declaration, case, name):
                    item["failed"] += 1
                    if item["first_failure"] is None:
                        item["first_failure"] = {"step": step, "phase": phase,
                                                 "value": str(value), "limit": str(limit(declaration, case, name))}
        return {"status": "PHYSICAL_FAILED" if any(item["failed"] for item in metrics.values()) else "PHYSICAL_PASSED",
                "scope": "FROZEN_BASELINE_ONLY", "case": case,
                "counts": expected_counts, "metrics": metrics}
    except (Rejected, OSError, EOFError, gzip.BadGzipFile, KeyError, IndexError,
            TypeError, ValueError, ArithmeticError, InvalidOperation) as error:
        return {"status": "INVALID", "scope": "FROZEN_BASELINE_ONLY", "case": case,
                "reason": str(error)}


def main():
    parser = argparse.ArgumentParser(description="Audit frozen Weld/Pulley physical quality")
    parser.add_argument("--declaration", default="tools/numerical/weld-pulley-physical-declaration.json")
    parser.add_argument("--manifest", default="tools/numerical/weld-pulley-physical-manifest.json")
    parser.add_argument("--case", choices=("weld-spring-equal", "pulley-taut"), required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--capture-source", default="tools/numerical/WeldPulleyPhysicalCapture.java")
    parser.add_argument("--baseline-jar", required=True)
    args = parser.parse_args()
    declaration_bytes = Path(args.declaration).read_bytes()
    declaration = json.loads(declaration_bytes)
    manifest = json.loads(Path(args.manifest).read_bytes())
    try:
        if (sha(declaration_bytes) != manifest["declaration_sha256"] or
            sha(Path(args.capture_source).read_bytes()) != manifest["capture_sha256"] or
            sha(Path(args.baseline_jar).read_bytes()) != manifest["baseline_jar_sha256"]):
            raise Rejected("declaration, capture source, or baseline JAR hash differs")
        result = audit_quality(declaration, manifest, args.case, args.reference)
    except (Rejected, OSError, KeyError) as error:
        result = {"status": "INVALID", "reason": str(error)}
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "PHYSICAL_PASSED" else
                     2 if result["status"] == "PHYSICAL_FAILED" else 1)


if __name__ == "__main__":
    main()
