#!/usr/bin/env python3
import re
import subprocess
import sys
import zipfile


PREFIX = "org/dyn4j/world/"
EXPECTED_TYPES = 52


def names(archive):
    with zipfile.ZipFile(archive) as jar:
        return {
            entry[:-6].replace("/", ".")
            for entry in jar.namelist()
            if entry.startswith(PREFIX)
            and entry.endswith(".class")
            and not entry.endswith("package-info.class")
            and not re.search(r"\$[0-9]", entry)
        }


def declarations(archive, name):
    lines = subprocess.run(
        ("javap", "-classpath", archive, "-protected", "-s", name),
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    header = next(line.strip() for line in lines if line.strip().endswith("{"))
    final_class = " final class " in f" {header} "
    members = set()
    for index, raw in enumerate(lines):
        line = re.sub(r"\s+", " ", raw.strip())
        if not line.endswith(";") or not line.startswith(("public ", "protected ")):
            continue
        descriptor = lines[index + 1].strip()
        if not descriptor.startswith("descriptor: "):
            raise ValueError(f"missing descriptor for {name}: {line}")
        if final_class and "(" in line:
            line = line.replace(" final ", " ", 1)
        if "$" in name and line.split("(", 1)[0].endswith(name):
            line = line.split(" ", 1)[0] + " <init>();"
        members.add(f"{line} {descriptor}")
    return header.split(" implements ", 1)[0].removesuffix("{").strip(), members


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify-world-jvm-api.py baseline.jar candidate.jar")
    baseline, candidate = sys.argv[1:]
    expected = names(baseline)
    actual = names(candidate)
    gaps = []
    if len(expected) != EXPECTED_TYPES:
        gaps.append(f"pinned inventory has {len(expected)} types, expected {EXPECTED_TYPES}")
    gaps.extend(f"missing type {name}" for name in sorted(expected - actual))
    count = 0
    for name in sorted(expected & actual):
        baseline_header, baseline_members = declarations(baseline, name)
        candidate_header, candidate_members = declarations(candidate, name)
        if baseline_header != candidate_header:
            gaps.append(f"{name}: header {candidate_header} differs from {baseline_header}")
        count += len(baseline_members)
        gaps.extend(f"{name}: missing {item}" for item in sorted(baseline_members - candidate_members))
    for gap in gaps:
        print(gap, file=sys.stderr)
    if gaps:
        raise SystemExit(f"{len(gaps)} world declaration gaps")
    print(f"World archive: {count} pinned public/protected declarations in {len(expected)} types present")


if __name__ == "__main__":
    main()
