#!/usr/bin/env python3
import os
import re
import subprocess
import sys
import zipfile

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


def declarations(jar, class_name):
    javap = os.path.join(os.environ["JAVA_HOME"], "bin", "javap")
    output = subprocess.run(
        (javap, "-package", "-classpath", jar, class_name),
        check=True, text=True, capture_output=True,
    ).stdout
    return {
        re.sub(r"\s+", " ", line.strip())
        .replace(" final ", " ")
        .replace("<? extends org.dyn4j.geometry.Vector2>", "<org.dyn4j.geometry.Vector2>")
        for line in output.splitlines()
        if line.strip().endswith(";")
    }


def main():
    if len(sys.argv) not in (3, 4):
        raise SystemExit("usage: verify-geometry-jvm-api.py baseline.jar candidate.jar [--all-root]")
    baseline, candidate = sys.argv[1:3]
    all_root = len(sys.argv) == 4 and sys.argv[3] == "--all-root"
    if len(sys.argv) == 4 and not all_root:
        raise SystemExit("only --all-root is supported")
    candidate_classes = set(classes(candidate))
    missing = []
    count = 0
    selected = [name for name in classes(baseline) if all_root or name.rsplit(".", 1)[-1] not in FOUNDATION]
    selected.extend(sorted(SUPPORT))
    with zipfile.ZipFile(candidate) as archive:
        candidate_classes.update(
            name[:-6].replace("/", ".") for name in archive.namelist() if name.endswith(".class")
        )
    for class_name in selected:
        if class_name not in candidate_classes:
            missing.append((class_name, "class missing"))
            continue
        expected = declarations(baseline, class_name)
        actual = declarations(candidate, class_name)
        count += len(expected)
        missing.extend((class_name, item) for item in sorted(expected - actual))
    for class_name, item in missing:
        print(f"{class_name}: missing {item}", file=sys.stderr)
    if missing:
        raise SystemExit(f"{len(missing)} JVM geometry declarations missing")
    print(f"JVM geometry API: {count} baseline declarations present in {len(selected)} types")


if __name__ == "__main__":
    main()
