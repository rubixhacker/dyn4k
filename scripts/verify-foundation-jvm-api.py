#!/usr/bin/env python3
import os
import re
import subprocess
import sys


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


def declarations(jar, class_name):
    javap = os.path.join(os.environ["JAVA_HOME"], "bin", "javap")
    output = subprocess.run(
        (javap, "-protected", "-classpath", jar, class_name),
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    return {
        re.sub(r"\s+", " ", line.strip()).replace(" static final ", " static ")
        for line in output.splitlines()
        if line.strip().endswith(";")
    }


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify-foundation-jvm-api.py baseline.jar candidate.jar")
    baseline, candidate = sys.argv[1:]
    missing = []
    total = 0
    for class_name in CLASSES:
        expected = declarations(baseline, class_name)
        actual = declarations(candidate, class_name)
        total += len(expected)
        missing.extend((class_name, item) for item in sorted(expected - actual))
    for class_name, item in missing:
        print(f"{class_name}: missing {item}", file=sys.stderr)
    if missing:
        raise SystemExit(1)
    print(f"JVM API: {total} baseline public/protected declarations present in {len(CLASSES)} types")


if __name__ == "__main__":
    main()
