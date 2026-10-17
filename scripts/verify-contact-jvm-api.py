#!/usr/bin/env python3
import re
import subprocess
import sys
import zipfile


PREFIX = "org/dyn4j/dynamics/contact/"
TYPES = (
    "Contact", "ContactConstraint", "ContactConstraintSolver", "ContactUpdateHandler",
    "ForceCollisionTimeOfImpactSolver", "SequentialImpulses", "SolvableContact",
    "SolvedContact", "TimeOfImpactSolver",
)


def class_names(archive):
    with zipfile.ZipFile(archive) as jar:
        return {
            name[len(PREFIX):-6].replace("/", ".")
            for name in jar.namelist()
            if name.startswith(PREFIX) and name.endswith(".class")
            and not name.endswith("package-info.class")
        }


def declarations(archive, name):
    output = subprocess.run(
        ("javap", "-classpath", archive, "-protected", "-s", f"org.dyn4j.dynamics.contact.{name}"),
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    header = next(line.strip() for line in output if line.strip().endswith("{"))
    members = set()
    for index, raw in enumerate(output):
        line = re.sub(r"\s+", " ", raw.strip())
        if not line.endswith(";") or line.startswith("descriptor: "):
            continue
        descriptor = output[index + 1].strip()
        if not descriptor.startswith("descriptor: "):
            raise ValueError(f"missing descriptor: {name}: {line}")
        if " final class " in f" {header} " and "(" in line:
            line = line.replace(" final ", " ")
        members.add(f"{line} {descriptor}")
    return header, members


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify-contact-jvm-api.py baseline.jar candidate.jar")
    baseline, candidate = sys.argv[1:]
    expected_names = class_names(baseline)
    actual_names = class_names(candidate)
    expected = {name for name in expected_names if name in TYPES or "$" in name}
    missing = [f"missing type {name}" for name in sorted(expected - actual_names)]
    if {name for name in expected if "$" not in name} != set(TYPES):
        missing.append("pinned baseline contact type inventory differs from nine types")
    count = 0
    for name in sorted(expected & actual_names):
        expected_header, expected_members = declarations(baseline, name)
        actual_header, actual_members = declarations(candidate, name)
        if name == "SolvableContact":
            actual_header = actual_header.removeprefix("public ")
        if expected_header != actual_header:
            missing.append(f"{name}: declaration {actual_header} differs from {expected_header}")
        count += len(expected_members)
        missing.extend(f"{name}: missing {item}" for item in sorted(expected_members - actual_members))
    for item in missing:
        print(item, file=sys.stderr)
    if missing:
        raise SystemExit(f"{len(missing)} contact declaration gaps")
    print(f"Contact archive: {count} baseline public/protected declarations in {len(expected)} types present")


if __name__ == "__main__":
    main()
