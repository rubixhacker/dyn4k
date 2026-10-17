#!/usr/bin/env python3
import os
import re
import subprocess
import sys
import zipfile

PACKAGES = ("hull", "decompose", "simplify")
PREFIX = "org/dyn4j/geometry/"


def classes(jar):
    with zipfile.ZipFile(jar) as archive:
        return sorted(
            name[:-6].replace("/", ".")
            for name in archive.namelist()
            if name.endswith(".class")
            and any(name.startswith(PREFIX + package + "/") for package in PACKAGES)
            and not name.endswith("package-info.class")
        )


def declarations(jar, class_name):
    javap = os.path.join(os.environ["JAVA_HOME"], "bin", "javap")
    output = subprocess.run(
        (javap, "-package", "-classpath", jar, class_name),
        check=True, text=True, capture_output=True,
    ).stdout
    return {
        re.sub(r"\s+", " ", line.strip())
        .replace("final ", "")
        .replace("<? extends org.dyn4j.geometry.Vector2>", "<org.dyn4j.geometry.Vector2>")
        for line in output.splitlines()
        if line.strip().endswith(";")
        and "access$" not in line
        and "this$0" not in line
    }


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify-polygon-jvm-api.py baseline.jar candidate.jar")
    baseline, candidate = sys.argv[1:]
    expected_classes = classes(baseline)
    actual_classes = set(classes(candidate))
    missing = []
    declaration_count = 0
    for class_name in expected_classes:
        if class_name not in actual_classes:
            missing.append((class_name, "class missing"))
            continue
        expected = declarations(baseline, class_name)
        actual = declarations(candidate, class_name)
        declaration_count += len(expected)
        missing.extend((class_name, item) for item in sorted(expected - actual))
    for class_name, item in missing:
        print(f"{class_name}: missing {item}", file=sys.stderr)
    if missing:
        raise SystemExit(f"{len(missing)} JVM polygon declarations missing")
    print(f"JVM polygon API: {declaration_count} baseline declarations present in {len(expected_classes)} types")


if __name__ == "__main__":
    main()
