import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from compare import (Rejected, canonical_path, check_counts, digest,
                     is_exact_numeric, is_zero_numeric, load_fixture, records,
                     rule_for)


def unit_for_path(path):
    suffixes = (
        ("getInverseInertia", "1/(kg m^2)"), ("getInverseMass", "1/kg"),
        ("getInertia", "kg m^2"), ("getMass", "kg"),
        ("getArea", "m^2"), ("getDensity", "kg/m^2"),
        ("getRestitutionVelocity", "m/s"), ("getTangentSpeed", "m/s"),
        ("getChangeInOrientation", "rad"), ("getRotationAngle", "rad"),
        ("getAngularDamping", "1/s"), ("getLinearDamping", "1/s"),
        ("getFixtureCount", "count"),
        ("getCenter[]", "m"), ("getLocalCenter[]", "m"),
        ("getVertices[][]", "m"), ("getRadius", "m"),
        ("getRotationDiscRadius", "m"), ("getHeight", "m"),
        ("getWidth", "m"), ("getForce[]", "N"),
        ("getAccumulatedForce[]", "N"), ("force[]", "N"),
        ("accumulatedForce[]", "N"), ("getTorque", "N m"),
        ("getAccumulatedTorque", "N m"), ("torque", "N m"),
        ("accumulatedTorque", "N m"), ("getNormals[][]", "dimensionless"),
    )
    for ending, unit in suffixes:
        if path.endswith(ending):
            return unit
    return "dimensionless"


def classify_path(fixture, path, cache):
    canonical = canonical_path(path)
    if canonical.endswith(".getValues[]") and not canonical.startswith("inputs."):
        return {"status": "UNPASSED_DEPENDENCY", "unit": "mixed",
                "reason": "Matrix entries alias stored cosine, sine, and translation. Cosine and translation have formula or selected limits; sine magnitude has no bound."}
    derived = fixture.get("derived_rules", {})
    if canonical.endswith(".properties.getChangeInPosition[]") and "change_in_position" in derived:
        return {"status": "DERIVED_FORMULA", "unit": "m",
                "reason": "Current minus previous translation; each source has a 1e-4 m component limit. Same-run binary64 subtraction and a 2e-4 m plus actual rounding-residual enclosure are required."}
    if canonical.endswith(".properties.getChangeInOrientation") and "change_in_orientation" in derived:
        return {"status": "DERIVED_FORMULA", "unit": "rad",
                "reason": "Source wrap and velocity branch must match exactly. Each source angle has a 1e-4 rad limit; enclosure adds 16 ulp(2*pi) for binary64 operations."}
    if canonical.endswith(".getCost") and not rule_for(fixture, path, cache) and "stored_cosine" in derived:
        return {"status": "DERIVED_FORMULA", "unit": "dimensionless",
                "reason": "Transform.getRotationAngle uses signed acos(cost). A certified cosine interval and two-ulp acos enclosure bind cost to the selected angle cap."}
    direction = rule_for(fixture, path[:-2], cache) if path.endswith("[]") else None
    rule = direction if direction and direction["metric"] == "direction" else rule_for(fixture, path, cache)
    if rule:
        return {"status": "APPROVED_LIMIT", "unit": rule["unit"],
                "reason": "Selected absolute and relative rule, including direction magnitude and unit checks where applicable.",
                "rule": rule["path"]}
    if is_zero_numeric(fixture, path, cache):
        return {"status": "EXACT_ZERO", "unit": unit_for_path(path),
                "reason": "The pinned scene applies an impulse only. It adds no force or torque; stored force and accumulators stay zero."}
    if is_exact_numeric(fixture, path, cache):
        if ".shape." in path or ".fixtures[]." in path or ".getMass." in path or ".getRotationDiscRadius" in path:
            reason = "The scene does not mutate its rectangle, fixture, or mass after the exact frozen input snapshot."
        elif ".constraint.get" in path:
            reason = "The contact handler mixes fixed fixture values; the pinned scene does not change those fixtures."
        else:
            reason = "The field is a frozen input, configuration, counter, or same-run exact identity."
        return {"status": "EXACT_IDENTITY", "unit": unit_for_path(path), "reason": reason}
    if canonical.endswith(".getSint"):
        return {"status": "UNPASSED_NO_BOUND", "unit": "dimensionless",
                "reason": "Transform.getRotationAngle uses only the sign of stored sine. The angle and cosine checks do not constrain sine magnitude; no norm/drift bound exists."}
    return {"status": "UNPASSED_UNCLASSIFIED", "unit": "unknown",
            "reason": "No matching selected limit, source identity, or proved formula enclosure."}


def classify_reference(fixture, reference, legacy_paths):
    if len(legacy_paths) != len(set(legacy_paths)):
        raise Rejected("duplicate legacy path")
    reference = Path(reference)
    frozen = fixture["reference"]
    if reference.name != frozen["file"] or digest(reference.read_bytes()) != frozen["gzip_sha256"]:
        raise Rejected("frozen reference file or hash differs")
    templates = set()
    stream_hash = hashlib.sha256()

    def visit(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, f"{path}.{key}" if path else key)
        elif isinstance(value, list):
            for child in value:
                visit(child, path + "[]")
        elif type(value) in (int, float):
            templates.add(path)

    def observed():
        for line, row in records(reference):
            stream_hash.update(line)
            visit(row, row["kind"])
            yield line, row

    counts = check_counts(observed(), fixture, reference=True)
    if stream_hash.hexdigest() != frozen["stream_sha256"]:
        raise Rejected("frozen decompressed stream hash differs")
    missing = set(legacy_paths) - templates
    if missing:
        raise Rejected("missing legacy path: " + ", ".join(sorted(missing)))
    cache = {}
    classified = {path: classify_path(fixture, path, cache) for path in sorted(set(legacy_paths))}
    summary = dict(sorted(Counter(item["status"] for item in classified.values()).items()))
    return {"fixture": fixture["key"] if "key" in fixture else fixture["id"],
            "reference_sha256": frozen["gzip_sha256"], "counts": counts,
            "observed_numeric_templates": len(templates),
            "legacy_count": len(classified), "summary": summary,
            "legacy_paths": classified}


def main():
    parser = argparse.ArgumentParser(description="Classify frozen numeric path templates")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--legacy-paths", required=True)
    args = parser.parse_args()
    legacy = json.loads(Path(args.legacy_paths).read_text())
    fixture = load_fixture(args.fixture)
    if legacy["fixture"] != args.fixture or legacy["reference_sha256"] != fixture["reference"]["gzip_sha256"]:
        raise Rejected("legacy path catalog identity differs")
    result = classify_reference(fixture, args.reference, legacy["paths"])
    print(json.dumps(result, sort_keys=True, indent=2))
    raise SystemExit(1 if result["summary"].get("UNPASSED_UNCLASSIFIED") else 0)


if __name__ == "__main__":
    main()
