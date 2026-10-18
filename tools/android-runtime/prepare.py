#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path


CONSUMERS = (
    "GeometryConsumer",
    "DetectionConsumer",
    "CollisionModelConsumer",
    "DynamicsConsumer",
    "WorldConsumer",
    "JointConsumer",
    "ContactConsumer",
    "org/dyn4j/geometry/GeometryPackageConsumer",
)
VERSION = "0.1.0-alpha.1"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_consumer_sources(root, prepared):
    source_root = Path("dyn4k-core/src/jvmConsumer/java")
    generated_root = Path("consumers/android-runtime/app/build/generated/consumer-java")
    expected_mapping = {str(generated_root / (name + ".java")):
                        str(source_root / (name + ".java")) for name in CONSUMERS}
    expected_sources = set(expected_mapping.values())
    expected_generated = set(expected_mapping)
    actual_generated = {str(path.relative_to(root)) for path in (root / generated_root).rglob("*.java")}
    if actual_generated != expected_generated:
        raise ValueError("generated consumer source set differs from expected sources")
    sources = prepared.get("consumer_sources", {})
    copies = prepared.get("generated_consumer_sources", {})
    if set(sources) != expected_sources or set(copies) != expected_generated:
        raise ValueError("consumer source manifest is incomplete or inconsistent")
    for generated, entry in copies.items():
        if not isinstance(entry, dict):
            raise ValueError(f"generated consumer source mapping changed: {generated}")
        source = entry.get("source")
        digest = entry.get("sha256")
        if source != expected_mapping[generated] or digest != sources[source]:
            raise ValueError(f"generated consumer source mapping changed: {generated}")
        if sha256(root / source) != digest:
            raise ValueError(f"original consumer source changed: {source}")
        if sha256(root / generated) != digest:
            raise ValueError(f"generated consumer source changed: {generated}")
    return copies


def portable_classes(root):
    names = []
    for module in ("dyn4k-core", "dyn4k"):
        sources = root / module / "src/commonTest/kotlin"
        compiled = root / module / "build/classes/kotlin/jvm/test"
        for source in sorted(sources.rglob("*.kt")):
            data = source.read_text()
            if "@Test" not in data:
                continue
            package = re.search(r"^package\s+([\w.]+)", data, re.MULTILINE)
            classes = re.findall(r"\bclass\s+(\w+Test)\b", data)
            if not package or not classes:
                raise ValueError(f"portable test declaration unavailable: {source}")
            for name in classes:
                class_name = package.group(1) + "." + name
                class_file = compiled / (class_name.replace(".", "/") + ".class")
                if not class_file.is_file():
                    raise ValueError(f"compiled portable test missing: {class_file}")
                names.append(class_name)
    if not names or len(names) != len(set(names)):
        raise ValueError("portable test manifest is empty or duplicated")
    return sorted(names)


def prepare(root):
    app = root / "consumers/android-runtime/app"
    generated = app / "build/generated"
    java_out = generated / "consumer-java"
    java_out.mkdir(parents=True, exist_ok=True)
    source_hashes = {}
    generated_hashes = {}
    for name in CONSUMERS:
        source = root / "dyn4k-core/src/jvmConsumer/java" / (name + ".java")
        if not source.is_file():
            raise ValueError(f"consumer source missing: {source}")
        destination = java_out / (name + ".java")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        relative_source = str(source.relative_to(root))
        digest = sha256(source)
        source_hashes[relative_source] = digest
        generated_hashes[str(destination.relative_to(root))] = {"source": relative_source, "sha256": digest}

    classes = portable_classes(root)
    jar = generated / "portable-suite.jar"
    with zipfile.ZipFile(jar, "w", zipfile.ZIP_DEFLATED) as archive:
        for module in ("dyn4k-core", "dyn4k"):
            directory = root / module / "build/classes/kotlin/jvm/test"
            if not directory.is_dir():
                raise ValueError(f"test classes missing: {directory}")
            for entry in sorted(directory.rglob("*.class")):
                relative = entry.relative_to(directory)
                top_class = str(relative.with_suffix("")).split("$")[0].replace("/", ".")
                if top_class.endswith("Test") and top_class not in classes:
                    continue
                archive.write(entry, entry.relative_to(directory))

    staged = {}
    for artifact in ("dyn4k-core-android", "dyn4k-android"):
        path = (root / "build/staging-repository/io/github/rubixhacker" / artifact /
                VERSION / f"{artifact}-{VERSION}.aar")
        if not path.is_file():
            raise ValueError(f"staged Android AAR missing: {path}")
        staged[artifact] = {"path": str(path), "sha256": sha256(path)}
    baseline = (root / "tools/baseline/dyn4j-6.0.0.jar")
    if not baseline.is_file():
        matches = list((Path.home() / ".gradle/caches/modules-2/files-2.1/org.dyn4j/dyn4j/6.0.0").rglob("dyn4j-6.0.0.jar"))
        if len(matches) != 1:
            raise ValueError("pinned baseline JAR unavailable")
        baseline = matches[0]
    if sha256(baseline) != "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e":
        raise ValueError("baseline JAR checksum mismatch")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    result = {
        "candidate_commit": commit,
        "staged": staged,
        "baseline_jar": {"path": str(baseline), "sha256": sha256(baseline)},
        "portable_classes": classes,
        "portable_jar": {"path": str(jar), "sha256": sha256(jar)},
        "consumer_sources": source_hashes,
        "generated_consumer_sources": generated_hashes,
    }
    verify_consumer_sources(root, result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--output", type=Path)
    operation.add_argument("--verify-consumers", type=Path)
    args = parser.parse_args()
    root = args.repo.resolve()
    if args.verify_consumers:
        result = json.loads(args.verify_consumers.read_text())
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        if result.get("candidate_commit") != commit:
            raise ValueError("candidate commit differs from prepared consumer sources")
        verified = verify_consumer_sources(root, result)
        print(f"verified {len(verified)} generated consumer sources; manifest sha256 {sha256(args.verify_consumers)}")
        return
    result = prepare(root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"prepared {len(result['portable_classes'])} portable test classes")


if __name__ == "__main__":
    main()
