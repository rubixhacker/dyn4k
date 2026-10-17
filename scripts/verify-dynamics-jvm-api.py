#!/usr/bin/env python3
import argparse
import re
import subprocess


TYPES = (
    "AbstractPhysicsBody", "Body", "BodyFixture", "ContinuousDetectionMode",
    "Force", "PhysicsBody", "Settings", "TimeStep", "Torque",
)


def surface(jar, name):
    output = subprocess.run(
        ("javap", "-classpath", jar, "-protected", "-s", f"org.dyn4j.dynamics.{name}"),
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    header = next(line.strip() for line in output if line.strip().endswith("{"))
    declarations = set()
    for index, line in enumerate(output):
        line = re.sub(r"\s+", " ", line.strip())
        if not line.startswith(("public ", "protected ")) or not line.endswith(";"):
            continue
        descriptor = output[index + 1].strip()
        if not descriptor.startswith("descriptor: "):
            raise ValueError(f"missing descriptor: {name}: {line}")
        declarations.add(f"{line} {descriptor}")
    return header, declarations


def constants(jar, name):
    output = subprocess.run(
        ("javap", "-classpath", jar, "-protected", "-constants", f"org.dyn4j.dynamics.{name}"),
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    fields = {}
    for raw in output:
        line = re.sub(r"\s+", " ", raw.strip())
        if line.startswith(("public ", "protected ")) and line.endswith(";") and "(" not in line:
            fields[line.split("=", 1)[0].removesuffix(";").split()[-1].strip()] = line
    return fields


def type_identity(header):
    match = re.match(r"public (?:(?:abstract|final) )?(class|interface|enum) ([^ ]+)(?: extends ([^ ]+))?", header)
    if match is None:
        raise ValueError(f"unknown type header: {header}")
    base = match.group(3)
    return match.group(1), match.group(2), base.rstrip(",") if base else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    args = parser.parse_args()
    missing = []
    count = 0
    for name in TYPES:
        expected_header, expected = surface(args.baseline, name)
        actual_header, actual = surface(args.candidate, name)
        if type_identity(expected_header) != type_identity(actual_header):
            missing.append(f"{name}: type identity changed: {actual_header}")
        count += len(expected)
        missing.extend(f"{name}: missing {declaration}" for declaration in sorted(expected - actual))
        expected_constants = constants(args.baseline, name)
        actual_constants = constants(args.candidate, name)
        for field, declaration in expected_constants.items():
            if field in actual_constants and declaration != actual_constants[field]:
                missing.append(f"{name}: field constant changed: {declaration} -> {actual_constants[field]}")
    for item in missing:
        print(item)
    if missing:
        raise SystemExit(f"{len(missing)} dynamics JVM API mismatches")
    print(f"Dynamics JVM API: {count} public/protected declarations present in {len(TYPES)} types")


if __name__ == "__main__":
    main()
