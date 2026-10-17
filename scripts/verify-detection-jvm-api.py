#!/usr/bin/env python3
import os
import re
import shutil
import subprocess
import sys
import zipfile

PACKAGES = ("broadphase", "narrowphase", "manifold", "continuous")
PREFIX = "org/dyn4j/collision/"
REDUNDANT_HEADER_INTERFACES = {
    "BroadphaseDetectorDecoratorAdapter": ", org.dyn4j.collision.broadphase.BroadphaseDetector<T>",
    "CollisionItemBroadphaseDetector": ", org.dyn4j.collision.broadphase.BroadphaseDetector<org.dyn4j.collision.CollisionItem<T, E>>",
    "Sap": " implements org.dyn4j.collision.broadphase.BroadphaseDetector<T>",
    "AbstractFallbackCondition": ", java.lang.Comparable<org.dyn4j.collision.narrowphase.FallbackCondition>",
    "TypedFallbackCondition": " implements org.dyn4j.collision.narrowphase.FallbackCondition, java.lang.Comparable<org.dyn4j.collision.narrowphase.FallbackCondition>",
    "SingleTypedFallbackCondition": " implements org.dyn4j.collision.narrowphase.FallbackCondition, java.lang.Comparable<org.dyn4j.collision.narrowphase.FallbackCondition>",
    "PairwiseTypedFallbackCondition": " implements org.dyn4j.collision.narrowphase.FallbackCondition, java.lang.Comparable<org.dyn4j.collision.narrowphase.FallbackCondition>",
}


def types(archive):
    with zipfile.ZipFile(archive) as jar:
        return sorted(
            name[:-6].replace("/", ".") for name in jar.namelist()
            if name.endswith(".class") and name.startswith(PREFIX)
            and name[len(PREFIX):].split("/", 1)[0] in PACKAGES
            and not name.endswith("package-info.class")
            and not re.search(r"\$(?:\d+|Detect(?:AABB|Pairs|Ray)Iterator)$", name[:-6])
        )


def surface(archive, name):
    javap = os.path.join(os.environ["JAVA_HOME"], "bin", "javap") if "JAVA_HOME" in os.environ else shutil.which("javap")
    output = subprocess.run(
        (javap, "-package", "-s", "-classpath", archive, name),
        check=True, text=True, capture_output=True,
    ).stdout
    lines = [re.sub(r"\s+", " ", line.strip()) for line in output.splitlines()]
    header = next(line for line in lines if line.endswith("{") and name in line)
    header = header.replace(", kotlin.jvm.internal.markers.KMappedMarker", "")
    header = header.replace(", kotlin.jvm.internal.markers.KMutableIterator", "")
    members = set()
    for index, line in enumerate(lines):
        if line.endswith(";") and not line.startswith("descriptor: "):
            descriptor = lines[index + 1] if index + 1 < len(lines) else ""
            if not descriptor.startswith("descriptor: "):
                raise ValueError(f"missing descriptor: {name} {line}")
            members.add(f"{line} {descriptor}")
    return header, members


def normalized_header(name, header):
    redundant = REDUNDANT_HEADER_INTERFACES.get(name.rsplit(".", 1)[-1])
    return header.replace(redundant, "") if redundant else header


def normalized_members(name, header, members):
    final_owner = " final class " in f" {header} "
    result = set()
    for member in members:
        declaration = member.split(" descriptor: ", 1)[0]
        if re.search(r"\baccess\$\d+\(", declaration) or " this$0;" in declaration:
            continue
        if "(" in declaration and (final_owner or " static " in f" {declaration} "):
            member = member.replace(" final ", " ")
        result.add(member)
    return result


def method_key(member):
    declaration, descriptor = member.split(" descriptor: ", 1)
    if "(" not in declaration:
        return None
    name = declaration.split("(", 1)[0].rsplit(" ", 1)[-1]
    if not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name):
        return None
    if name.endswith("$annotations") or name.startswith("access$"):
        return None
    return name, descriptor.split(")", 1)[0] + ")"


def supertypes(name, header):
    plain = header
    while "<" in plain:
        updated = re.sub(r"<[^<>]*>", "", plain)
        if updated == plain:
            break
        plain = updated
    remainder = plain.split(name, 1)[1].removesuffix("{").strip()
    result = []
    for keyword in ("extends", "implements"):
        match = re.search(rf"\b{keyword} (.*?)(?=\b(?:extends|implements)\b|$)", remainder)
        if match:
            result.extend(part.strip() for part in match.group(1).split(",") if part.strip())
    if not result and name != "java.lang.Object":
        result.append("java.lang.Object")
    return result


def inherited_method_keys(baseline, name, cache, seen=None):
    if name in cache:
        return cache[name]
    if seen is None:
        seen = set()
    if name in seen:
        return set()
    seen.add(name)
    try:
        header, members = surface(baseline, name)
    except subprocess.CalledProcessError:
        return set()
    keys = {key for member in members if (key := method_key(member)) is not None}
    for parent in supertypes(name, header):
        keys.update(inherited_method_keys(baseline, parent, cache, seen))
    cache[name] = keys
    return keys


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify-detection-jvm-api.py baseline.jar candidate.jar")
    baseline, candidate = sys.argv[1:]
    expected_types = types(baseline)
    actual_types = set(types(candidate))
    missing = []
    added = []
    ancestor_cache = {}
    member_count = 0
    for name in expected_types:
        if name not in actual_types:
            missing.append(f"{name}: type missing")
            continue
        expected_header, expected_members = surface(baseline, name)
        actual_header, actual_members = surface(candidate, name)
        if normalized_header(name, expected_header) != normalized_header(name, actual_header):
            missing.append(f"{name}: header {actual_header!r} != {expected_header!r}")
        expected_members = normalized_members(name, expected_header, expected_members)
        actual_members = normalized_members(name, actual_header, actual_members)
        member_count += len(expected_members)
        missing.extend(f"{name}: missing {member}" for member in sorted(expected_members - actual_members))
        if expected_header.startswith("public "):
            inherited = set()
            for parent in supertypes(name, expected_header):
                inherited.update(inherited_method_keys(baseline, parent, ancestor_cache))
            baseline_keys = {key for member in expected_members if (key := method_key(member)) is not None}
            baseline_keys.update(inherited)
            added.extend(
                f"{name}: added {member}" for member in sorted(actual_members - expected_members)
                if (key := method_key(member)) is not None and key not in baseline_keys
            )
    for line in missing:
        print(line, file=sys.stderr)
    for line in added:
        print(line, file=sys.stderr)
    if missing or added:
        raise SystemExit(f"{len(missing)} missing, {len(added)} added detection JVM declarations")
    print(f"Detection JVM API: {member_count} declarations in {len(expected_types)} types present, no added Java methods")


if __name__ == "__main__":
    main()
