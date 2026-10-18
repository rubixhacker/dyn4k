#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

from build_identity import build_log_identity, current_java, verify_build_log_identity
from android_corpus import (commit_time_ns, load_suite, verify_full_inputs, verify_jvm_xml,
                            verify_xml_pins, write_full_inputs)


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
ANDROID_VERSION_CASE = b'if ("1.8".equals(version)) return null;\n'
ANDROID_VERSION_CASE_WITH_ART = (
    b'if ("1.8".equals(version)) return null;\n'
    b'        if ("0.9".equals(version)) return '
    b'"Attempt to invoke virtual method \'java.lang.String '
    b'java.lang.Class.getName()\' on a null object reference";\n')


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def android_consumer_source(name, source):
    if name != "CollisionModelConsumer":
        return source
    if source.count(ANDROID_VERSION_CASE) != 1:
        raise ValueError("Android consumer version table differs from pinned JVM source")
    return source.replace(ANDROID_VERSION_CASE, ANDROID_VERSION_CASE_WITH_ART)


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
        if source != expected_mapping[generated]:
            raise ValueError(f"generated consumer source mapping changed: {generated}")
        if sha256(root / source) != sources[source]:
            raise ValueError(f"original consumer source changed: {source}")
        expected_bytes = android_consumer_source(Path(source).stem, (root / source).read_bytes())
        if digest != hashlib.sha256(expected_bytes).hexdigest() or \
                (root / generated).read_bytes() != expected_bytes:
            raise ValueError(f"generated consumer source changed: {generated}")
    return copies


def verify_full_consumer_sources(root, prepared):
    generated_root = Path("consumers/android-runtime/full/build/generated/consumer-java")
    expected = {str(generated_root / (name + ".java")):
                str(Path("dyn4k-core/src/jvmConsumer/java") / (name + ".java"))
                for name in CONSUMERS}
    actual = {str(path.relative_to(root)) for path in (root / generated_root).rglob("*.java")}
    expected_copies = {generated: {"source": source, "sha256": hashlib.sha256(
        android_consumer_source(Path(source).stem, (root / source).read_bytes())).hexdigest()}
                       for generated, source in expected.items()}
    if actual != set(expected) or prepared.get("full_generated_consumer_sources") != expected_copies:
        raise ValueError("full app generated Java source set differs")
    for generated, source in expected.items():
        if (root / generated).read_bytes() != android_consumer_source(
                Path(source).stem, (root / source).read_bytes()) or \
                sha256(root / source) != prepared["consumer_sources"][source]:
            raise ValueError(f"full app generated Java source changed: {generated}")
    jar = root / "consumers/android-runtime/full/build/generated/full-consumers.jar"
    if prepared.get("full_java_jar") != {"path": str(jar), "sha256": sha256(jar)}:
        raise ValueError("full app compiled Java consumer JAR changed")


def compile_full_consumers(root, generated, staged):
    output = root / "consumers/android-runtime/full/build/generated"
    libraries = []
    for artifact in ("dyn4k-core-android", "dyn4k-android"):
        path = output / (artifact + "-classes.jar")
        with zipfile.ZipFile(staged[artifact]["path"]) as aar:
            path.write_bytes(aar.read("classes.jar"))
        libraries.append(path)
    stdlib = list((Path.home() / ".gradle/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-stdlib/2.4.20").rglob("kotlin-stdlib-2.4.20.jar"))
    if len(stdlib) != 1:
        raise ValueError("pinned Kotlin standard library for Java consumer compile is unavailable")
    libraries.append(stdlib[0])
    with tempfile.TemporaryDirectory() as temporary:
        classes = Path(temporary)
        javac = Path(os.environ.get("JAVA_HOME", "")) / "bin/javac"
        if not javac.is_file():
            javac = Path("javac")
        sources = [str(root / path) for path in generated]
        subprocess.run([str(javac), "--release", "8", "-cp",
                        os.pathsep.join(map(str, libraries)),
                        "-d", str(classes), *sources], check=True)
        jar = output / "full-consumers.jar"
        with zipfile.ZipFile(jar, "w", zipfile.ZIP_DEFLATED) as archive:
            for source in sorted(classes.rglob("*.class")):
                archive.write(source, source.relative_to(classes))
    return {"path": str(jar), "sha256": sha256(jar)}


def portable_classes(root, suite):
    classes = sorted({case["classname"] for case in suite["cases"] if case["scope"] == "portable"})
    for module in ("dyn4k-core", "dyn4k"):
        compiled = root / module / "build/classes/kotlin/jvm/test"
        for name in {case["classname"] for case in suite["cases"]
                     if case["module"] == module and case["scope"] == "portable"}:
            if not (compiled / (name.replace(".", "/") + ".class")).is_file():
                raise ValueError(f"compiled portable test missing: {module}:{name}")
    return classes


def build_portable_jar(root, jar, jvm_only_classes):
    seen = set()
    with zipfile.ZipFile(jar, "w", zipfile.ZIP_DEFLATED) as archive:
        for module in ("dyn4k-core", "dyn4k"):
            directory = root / module / "build/classes/kotlin/jvm/test"
            if not directory.is_dir():
                raise ValueError(f"compiled test classes missing: {directory}")
            for entry in sorted(directory.rglob("*.class")):
                relative = entry.relative_to(directory)
                top_class = str(relative.with_suffix("")).split("$")[0].replace("/", ".")
                if top_class in jvm_only_classes:
                    continue
                if str(relative) in seen:
                    raise ValueError(f"duplicate portable class file: {relative}")
                seen.add(str(relative))
                archive.write(entry, relative)
    if not seen:
        raise ValueError("portable test JAR is empty")


def prepare(root, root_build_log):
    jdk = current_java()
    root_build = build_log_identity(root_build_log)
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
        destination.write_bytes(android_consumer_source(Path(name).name, source.read_bytes()))
        relative_source = str(source.relative_to(root))
        digest = sha256(source)
        source_hashes[relative_source] = digest
        generated_hashes[str(destination.relative_to(root))] = {
            "source": relative_source, "sha256": sha256(destination)}

    suite, suite_binding = load_suite(root)
    xml_evidence = verify_jvm_xml(root, suite, min_mtime_ns=commit_time_ns(root))
    classes = portable_classes(root, suite)
    full_inputs = write_full_inputs(root, suite)
    full_java_out = root / "consumers/android-runtime/full/build/generated/consumer-java"
    full_java_out.mkdir(parents=True, exist_ok=True)
    full_copies = {}
    for name in CONSUMERS:
        source = root / "dyn4k-core/src/jvmConsumer/java" / (name + ".java")
        destination = full_java_out / (name + ".java")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(android_consumer_source(Path(name).name, source.read_bytes()))
        full_copies[str(destination.relative_to(root))] = {
            "source": str(source.relative_to(root)), "sha256": sha256(destination)}
    jar = generated / "portable-suite.jar"
    jvm_only = {case["classname"] for case in suite["cases"] if case["scope"] == "jvm-only"}
    build_portable_jar(root, jar, jvm_only)

    staged = {}
    for artifact in ("dyn4k-core-android", "dyn4k-android"):
        path = (root / "build/staging-repository/io/github/rubixhacker" / artifact /
                VERSION / f"{artifact}-{VERSION}.aar")
        if not path.is_file():
            raise ValueError(f"staged Android AAR missing: {path}")
        staged[artifact] = {"path": str(path), "sha256": sha256(path)}
    staged_roots = {}
    for artifact in ("dyn4k-core", "dyn4k"):
        for extension in ("module", "pom"):
            path = (root / "build/staging-repository/io/github/rubixhacker" / artifact /
                    VERSION / f"{artifact}-{VERSION}.{extension}")
            if not path.is_file():
                raise ValueError(f"staged publication root missing: {path}")
            staged_roots[f"{artifact}.{extension}"] = {"path": str(path), "sha256": sha256(path)}
    full_java_jar = compile_full_consumers(root, full_copies, staged)
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
        "build_jdk": jdk,
        "root_build": root_build,
        "staged": staged,
        "staged_roots": staged_roots,
        "baseline_jar": {"path": str(baseline), "sha256": sha256(baseline)},
        "portable_classes": classes,
        "suite_manifest": suite_binding,
        "jvm_xml": xml_evidence,
        "portable_jar": {"path": str(jar), "sha256": sha256(jar)},
        "consumer_sources": source_hashes,
        "generated_consumer_sources": generated_hashes,
        "full_generated_consumer_sources": full_copies,
        "full_java_jar": full_java_jar,
        "full_inputs": full_inputs,
    }
    verify_consumer_sources(root, result)
    verify_full_consumer_sources(root, result)
    verify_full_inputs(root, suite, full_inputs)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--output", type=Path)
    operation.add_argument("--verify-consumers", type=Path)
    parser.add_argument("--root-build-log", type=Path)
    args = parser.parse_args()
    root = args.repo.resolve()
    if args.verify_consumers:
        result = json.loads(args.verify_consumers.read_text())
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        if result.get("candidate_commit") != commit:
            raise ValueError("candidate commit differs from prepared consumer sources")
        if result.get("build_jdk") != current_java():
            raise ValueError("prepared JDK identity differs")
        verify_build_log_identity(result["root_build"])
        verified = verify_consumer_sources(root, result)
        verify_full_consumer_sources(root, result)
        suite, _ = load_suite(root)
        verify_full_inputs(root, suite, result.get("full_inputs"))
        verify_xml_pins(root, result)
        print(f"verified {len(verified)} generated consumer sources; manifest sha256 {sha256(args.verify_consumers)}")
        return
    if not args.root_build_log:
        parser.error("--output requires --root-build-log")
    result = prepare(root, args.root_build_log)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"prepared {len(result['portable_classes'])} portable test classes")


if __name__ == "__main__":
    main()
