#!/usr/bin/env python3
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "baseline"))
from verify import compare_jars

FOUNDATION = {
    "Matrix22", "Matrix33", "Rotatable", "Rotation", "Shiftable",
    "Transform", "Transformable", "Translatable", "Vector2", "Vector3",
}
SUPPORT = {
    "org.dyn4j.DataContainer",
    "org.dyn4j.exception.EmptyCollectionException",
    "org.dyn4j.exception.InvalidIndexException",
    "org.dyn4j.exception.NullElementException",
    "org.dyn4j.exception.ValueOutOfRangeException",
}


def classes(jar):
    with zipfile.ZipFile(jar) as archive:
        return sorted(
            name[:-6].replace("/", ".")
            for name in archive.namelist()
            if name.startswith("org/dyn4j/geometry/")
            and name.endswith(".class")
            and "/" not in name[len("org/dyn4j/geometry/"):]
            and not name.endswith("package-info.class")
            and "$Companion" not in name
        )


def main():
    if len(sys.argv) not in (3, 4):
        raise SystemExit("usage: verify-geometry-jvm-api.py baseline.jar candidate.jar [--all-root]")
    baseline, candidate = sys.argv[1:3]
    all_root = len(sys.argv) == 4 and sys.argv[3] == "--all-root"
    if len(sys.argv) == 4 and not all_root:
        raise SystemExit("only --all-root is supported")
    selected = [name for name in classes(baseline) if all_root or name.rsplit(".", 1)[-1] not in FOUNDATION]
    selected.extend(sorted(SUPPORT))
    result = compare_jars(Path(baseline), Path(candidate), set(selected), visibility="-package")
    for name in result["missing_types"]:
        print(f"{name}: missing class", file=sys.stderr)
    for mismatch in result["signature_mismatches"]:
        print(mismatch, file=sys.stderr)
    count = len(result["missing_types"]) + len(result["signature_mismatches"])
    if count:
        raise SystemExit(f"{count} JVM geometry API mismatches")
    print(f"JVM geometry API: {result['compared_baseline_declarations']} baseline declarations present in {len(selected)} types")


if __name__ == "__main__":
    main()
