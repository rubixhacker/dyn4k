#!/usr/bin/env python3
import os
import re
import subprocess
import sys


CLASSES = (
    "org.dyn4j.AVLTree",
    "org.dyn4j.BinarySearchTree",
    "org.dyn4j.BinarySearchTreeIterator",
    "org.dyn4j.BinarySearchTreeNode",
    "org.dyn4j.BinarySearchTreeSearchCriteria",
    "org.dyn4j.Reference",
    "org.dyn4j.Version",
)


def surface(jar, name):
    output = subprocess.run(
        (os.path.join(os.environ["JAVA_HOME"], "bin", "javap"), "-protected", "-classpath", jar, name),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    lines = [re.sub(r"\s+", " ", line.strip()) for line in output.splitlines()]
    header = next(line for line in lines if line.endswith("{") and name in line)
    header = header.replace(", kotlin.jvm.internal.markers.KMappedMarker", "")
    header = header.replace(", kotlin.jvm.internal.markers.KMutableIterator", "")
    declarations = {line for line in lines if line.endswith(";")}
    return header, declarations


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify-tree-jvm-api.py baseline.jar candidate.jar")
    total = 0
    failures = []
    for name in CLASSES:
        expected_header, expected = surface(sys.argv[1], name)
        actual_header, actual = surface(sys.argv[2], name)
        if expected_header != actual_header:
            failures.append(f"{name}: header {actual_header!r} != {expected_header!r}")
        total += len(expected)
        failures.extend(f"{name}: missing {item}" for item in sorted(expected - actual))
    if failures:
        print("\n".join(failures), file=sys.stderr)
        raise SystemExit(1)
    print(f"Tree JVM API: {total} baseline public/protected declarations and 7 type signatures present")


if __name__ == "__main__":
    main()
