#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "baseline"))
from verify import compare_jars


CLASSES = (
    "org.dyn4j.Copyable",
    "org.dyn4j.Epsilon",
    "org.dyn4j.exception.ArgumentNullException",
    "org.dyn4j.geometry.Vector2",
    "org.dyn4j.geometry.Vector3",
    "org.dyn4j.geometry.Rotation",
    "org.dyn4j.geometry.Matrix22",
    "org.dyn4j.geometry.Matrix33",
    "org.dyn4j.geometry.Transform",
    "org.dyn4j.geometry.Rotatable",
    "org.dyn4j.geometry.Translatable",
    "org.dyn4j.geometry.Transformable",
    "org.dyn4j.geometry.Shiftable",
)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify-foundation-jvm-api.py baseline.jar candidate.jar")
    baseline, candidate = sys.argv[1:]
    result = compare_jars(Path(baseline), Path(candidate), set(CLASSES))
    for name in result["missing_types"]:
        print(f"{name}: missing class", file=sys.stderr)
    for mismatch in result["signature_mismatches"]:
        print(mismatch, file=sys.stderr)
    count = len(result["missing_types"]) + len(result["signature_mismatches"])
    if count:
        raise SystemExit(f"{count} foundation JVM API mismatches")
    print(f"JVM API: {result['compared_baseline_declarations']} baseline public/protected declarations present in {len(CLASSES)} types")


if __name__ == "__main__":
    main()
