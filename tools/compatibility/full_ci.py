from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import exception_ci
import world_ci
from exception_ci import seal_exception, validate_exception_report
from world_ci import seal_world


ROOT = Path(__file__).resolve().parents[2]
VERSION = "0.1.0-alpha.1"
BASELINE_SHA = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
STDLIB_SHA = "2226de463d309d4a5500a481320b3dea515a6981dcae1def531fbc158884e25f"
ANNOTATIONS_SHA = "ace2a10dc8e2d5fd34925ecac03e4988b2c0f851650c94b8cef49ba1bd111478"
ADVERSE_AUDIT_SHA = "aaed70cf906eb2e1944e56b80713fe6398a5339d55f4977128b54dd70cba607a"
FIXTURE_SHA = {
    "b668a59b6b50e6d5be1ca4828d2eaa179c6f9b3623a839be3e8c2c063d9ce6a4",
    "bb3f75b5f938b5e6da6e2444f5626606daa2223d29ba5c9ba2405660e50097ed",
    "b37d307b808a55961bad6d6cfd5606ec7d27b2ba33567e8d44621d0942530ff0",
}
FIXTURES = sorted((ROOT / "tools/baseline/fixtures").glob("*.java"))
PROJECTION = ROOT / "tools/compatibility/fixtures/java_source_projection"
PARAMETER_SUITES = {
    "org.dyn4j.collision.broadphase.CollisionBodyBroadphaseTest": (
        25, ("Sap", "Sap", "DynamicAABBTree", "DynamicAABBTree", "BruteForceBroadphase")),
    "org.dyn4j.collision.broadphase.CollisionItemBroadphaseTest": (
        29, ("CollisionItemBroadphaseDetectorAdapter",) * 5),
}
PARAMETER_PATTERN = re.compile(r"([^\[]+)\[([^@\]]+)@([0-9a-fA-F]+)\]")
LANES = {f"{provider}-javac{compiler}-java{runtime}"
         for provider in ("baseline", "candidate", "android") for compiler in (8, 21)
         for runtime in (8, 21)}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json_unique(contents: str):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(contents, object_pairs_hook=unique_pairs)


def snapshot_archive(output: Path) -> dict[str, str]:
    if output.is_symlink() or not output.is_dir():
        raise ValueError("archive root is missing or a symlink")
    files = {}
    for directory, names, filenames in os.walk(output, followlinks=False):
        for name in names:
            if (Path(directory) / name).is_symlink():
                raise ValueError(f"archive symlink directory: {name}")
        for name in filenames:
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"archive symlink or non-file: {path}")
            relative = path.relative_to(output).as_posix()
            if relative != "lane-manifest.json":
                files[relative] = digest(path)
    return dict(sorted(files.items()))


def verify_archive_files(output: Path, recorded: dict[str, str]) -> dict[str, str]:
    if not isinstance(recorded, dict) or not recorded:
        raise ValueError("archive file inventory is empty")
    normalized = set()
    for name, sha in recorded.items():
        if not isinstance(name, str) or not isinstance(sha, str):
            raise ValueError("archive path or hash is unsafe")
        path = Path(name)
        if (path.is_absolute() or "\\" in name or
                not path.parts or any(part in (".", "..") for part in name.split("/")) or
                path.as_posix() != name or not re.fullmatch(r"[0-9a-f]{64}", sha)):
            raise ValueError(f"archive path or hash is unsafe: {name}")
        if path.as_posix() in normalized:
            raise ValueError(f"duplicate archive path: {name}")
        normalized.add(path.as_posix())
    actual = snapshot_archive(output)
    if set(actual) != set(recorded):
        raise ValueError("archive file set differs")
    for name, sha in recorded.items():
        if actual[name] != sha:
            raise ValueError(f"archive file hash differs: {name}")
    return actual


def relocate_exception_runs(rows: list[dict], original: Path, output: Path,
                            jdks: dict[str, Path], area: str = "fixture") -> list[dict]:
    if area not in ("fixture", "uid-adverse"):
        raise ValueError("exception process area is unsafe")
    fixture = original / "exception-serialization" / area
    copied_fixture = output / "exception-serialization" / area
    mapped = copy.deepcopy(rows)
    for row in mapped:
        operation = row.get("operation")
        runtime = row.get("runtime")
        provider = row.get("provider")
        command = row.get("command")
        if (operation not in ("ids", "write", "read") or
                runtime not in jdks or provider not in ("baseline", "jvm", "android") or
                not isinstance(command, list)):
            raise ValueError("exception process command is malformed")
        classpath = os.pathsep.join((str(fixture / "classes" / provider),
                                     str(fixture / f"{provider}.jar"),
                                     str(original / "deps/kotlin-stdlib-2.4.20.jar")))
        expected = [str(jdks[runtime] / "bin/java"), "-cp", classpath,
                    "ExceptionSerializationProbe", operation]
        if operation in ("write", "read"):
            writer_runtime = row.get("writer_runtime")
            writer_provider = row.get("writer_provider")
            case = row.get("case")
            if (writer_runtime not in jdks or writer_provider not in
                    ("baseline", "jvm", "android") or not isinstance(case, str)):
                raise ValueError("exception process command is malformed")
            expected.extend((str(fixture / f"{writer_runtime}-{writer_provider}-{case}.ser"),
                             case))
        if command != expected:
            raise ValueError("exception process command differs from declared archive root")
        row["command"][2] = os.pathsep.join((str(copied_fixture / "classes" / provider),
                                              str(copied_fixture / f"{provider}.jar"),
                                              str(output / "deps/kotlin-stdlib-2.4.20.jar")))
        if operation in ("write", "read"):
            row["command"][-2] = str(copied_fixture /
                                     f"{writer_runtime}-{writer_provider}-{case}.ser")
    return mapped


def declared_archive_root(value: str) -> Path:
    if not isinstance(value, str):
        raise ValueError("declared archive root is missing")
    path = Path(value)
    if not path.is_absolute() or str(path) != value or any(part == ".." for part in path.parts):
        raise ValueError("declared archive root is unsafe")
    return path


def archived_json(output: Path, relative: str, expected_sha: str | None = None):
    path = output / relative
    if not path.is_file() or path.is_symlink() or (expected_sha and digest(path) != expected_sha):
        raise ValueError(f"archive JSON is missing or changed: {relative}")
    return load_json_unique(path.read_text())


def verify_portable_corpus(output: Path, evidence: dict, candidate_sha: str,
                           manifest: dict, hashes: dict[str, str]) -> None:
    if seal_lanes(output, evidence, candidate_sha) != manifest["files"]:
        raise ValueError("corpus manifest differs")
    corpus = evidence["corpus"]
    if set(corpus) != LANES | {f"{provider}-javac{compiler}" for provider in
                                   ("baseline", "candidate", "android") for compiler in (8, 21)}:
        raise ValueError("corpus compile and runtime inventory differs")
    expected_identities = None
    for lane in sorted(LANES):
        row = corpus[lane]
        report = archived_json(output, row["report"], row["report_sha256"])
        validate_corpus(report)
        provider, compiler, runtime = re.fullmatch(
            r"(baseline|candidate|android)-javac(8|21)-java(8|21)", lane).groups()
        archive_hash = hashes["baseline"] if provider == "baseline" else hashes[
            "jvm" if provider == "candidate" else "android"]
        if (report.get("provider") != provider or report.get("compiler") != int(compiler) or
                report.get("runtime") != int(runtime) or
                report.get("archive_sha256") != archive_hash or
                report.get("xml_sha256") != row["xml_sha256"] or
                report.get("run_log_sha256") != digest(output / "logs" / f"run-{lane}.log")):
            raise ValueError(f"corpus process or staged provider differs: {lane}")
        identities = normalized_cases(validate_xml(output / row["xml"]))
        identity_hash = hashlib.sha256(json.dumps(sorted(
            (class_name, name, count) for (class_name, name), count in identities.items()
        )).encode()).hexdigest()
        if (identity_hash != row.get("case_id_sha256") or
                identity_hash != report.get("case_id_sha256") or
                (expected_identities is not None and identities != expected_identities)):
            raise ValueError(f"corpus case identities differ: {lane}")
        expected_identities = identities
    for provider in ("baseline", "candidate", "android"):
        for compiler in (8, 21):
            key = f"{provider}-javac{compiler}"
            row = corpus[key]
            if (row.get("compile_exit_code") != 0 or
                    row.get("compile_log_sha256") != digest(output / "logs" / f"compile-{key}.log")):
                raise ValueError(f"corpus Java compilation differs: {key}")


def verify_portable_inputs(output: Path, evidence: dict) -> dict[str, str]:
    archives = evidence.get("archives", {})
    baseline = evidence.get("baseline", {})
    baseline_report = archived_json(output, "baseline-run.json", baseline.get("run_sha256"))
    validate_corpus(baseline_report)
    if (baseline.get("verify_exit_code") != 0 or baseline.get("final_source_check_exit_code") != 0 or
            baseline.get("source_revision") != "058bf6d982a0fb89b54050f929f6ea9dae53b714" or
            baseline_report.get("commit") != baseline["source_revision"] or
            baseline.get("executed_cases") != 2385 or
            digest(output / "baseline-inventory.json") != baseline.get("inventory_sha256")):
        raise ValueError("pinned baseline source or execution differs")
    source = output / "baseline-cache/dyn4j-source"
    validate_source_inputs(source, baseline_report["test_input_sha256"])
    if digest(output / "baseline-cache/dyn4j-6.0.0-sources.jar") != (
            "83b47be47bdce27681139dab84937e0f586b70ab800dc494fbebed4b58893223"):
        raise ValueError("pinned baseline source archive differs")
    baseline_jar = output / "baseline-cache/dyn4j-6.0.0.jar"
    if digest(baseline_jar) != BASELINE_SHA:
        raise ValueError("pinned baseline binary differs")
    files = {
        "jvm": output / "archives" / f"dyn4k-core-jvm-{VERSION}.jar",
        "android_aar": output / "archives" / f"dyn4k-core-android-{VERSION}.aar",
        "android": output / "android-classes.jar",
        "stdlib": output / "deps/kotlin-stdlib-2.4.20.jar",
        "annotations": output / "deps/annotations-13.0.jar",
        "junit": output / "baseline-cache/deps/junit-4.13.1.jar",
        "hamcrest": output / "baseline-cache/deps/hamcrest-core-1.3.jar",
    }
    fields = {"jvm": "staged_jvm_jar", "android_aar": "staged_android_aar",
              "android": "staged_android_classes_jar", "stdlib": "kotlin_stdlib",
              "annotations": "annotations", "junit": "junit-4.13.1.jar",
              "hamcrest": "hamcrest-core-1.3.jar"}
    for name, path in files.items():
        if not path.is_file() or digest(path) != archives.get(fields[name]):
            raise ValueError(f"staged or dependency archive differs: {name}")
    if archives["kotlin_stdlib"] != STDLIB_SHA or archives["annotations"] != ANNOTATIONS_SHA:
        raise ValueError("Kotlin dependency archive differs")
    for name in ("jvm", "android_aar"):
        sidecar = files[name].with_name(files[name].name + ".sha256")
        if sidecar.read_text().strip().lower() != digest(files[name]):
            raise ValueError(f"staged archive sidecar differs: {name}")
    with zipfile.ZipFile(files["android_aar"]) as aar:
        if aar.namelist().count("classes.jar") != 1 or aar.read("classes.jar") != files[
                "android"].read_bytes():
            raise ValueError("Android classes.jar differs from staged AAR")
    if digest(ROOT / "tools/compatibility/PinnedCorpusReport.java") != archives.get(
            "corpus_harness_source"):
        raise ValueError("corpus harness source differs")
    return {"baseline": BASELINE_SHA, "jvm": archives["staged_jvm_jar"],
            "android": archives["staged_android_classes_jar"]}


def verify_portable_audits(output: Path, evidence: dict, hashes: dict[str, str]) -> None:
    if set(evidence.get("audits", {})) != {"jvm", "android"}:
        raise ValueError("strict audit inventory differs")
    for name in ("jvm", "android"):
        row = evidence["audits"][name]
        if row.get("status") != "PASSED" or row.get("report") != f"audit-{name}.json":
            raise ValueError(f"strict audit status differs: {name}")
        validate_audit(archived_json(output, row["report"], row["report_sha256"]), hashes[name])
    projection = evidence.get("source_projection", {})
    if projection.get("exit_code") != 0 or projection.get("observations") != 12:
        raise ValueError("source projection status differs")
    report = archived_json(output, "projection/result.json", projection.get("report_sha256"))
    if digest(PROJECTION / "frozen-adverse-audit.json") != ADVERSE_AUDIT_SHA:
        raise ValueError("frozen adverse audit source differs")
    validate_projection(report, output / "projection", PROJECTION, hashes, ADVERSE_AUDIT_SHA)


def verify_exception_process_metadata(report: dict, original: Path, output: Path,
                                      source_root: Path, jdks: dict[str, Path],
                                      hashes: dict[str, str], area: str) -> list[dict]:
    original_work = original / "exception-serialization" / area
    work = output / "exception-serialization" / area
    providers = report.get("providers")
    if not isinstance(providers, dict) or set(providers) != set(exception_ci.PROVIDERS):
        raise ValueError("exception provider inventory differs")
    source_files = {"baseline": original / "baseline-cache/dyn4j-6.0.0.jar",
                    "jvm": original / "archives" / f"dyn4k-core-jvm-{VERSION}.jar",
                    "android": original / "android-classes.jar"}
    if area == "uid-adverse":
        source_files["jvm"] = original / "exception-serialization/uid-mutant.jar"
    for provider in exception_ci.PROVIDERS:
        row = providers[provider]
        if (row != {"source": str(source_files[provider]),
                    "path": str(original_work / f"{provider}.jar"),
                    "sha256": hashes[provider]} or
                digest(work / f"{provider}.jar") != hashes[provider]):
            raise ValueError(f"exception provider archive differs: {area} {provider}")
        compile_row = report["compiles"][provider]
        command = [str(jdks["jdk8"] / "bin/javac"), "-cp",
                   str(original_work / f"{provider}.jar"), "-d",
                   str(original_work / "classes" / provider),
                   str(source_root / "tools/compatibility/fixtures/exception_serialization/"
                       "ExceptionSerializationProbe.java")]
        if compile_row.get("exit") != 0 or compile_row.get("command") != command:
            raise ValueError(f"exception Java 8 compile command differs: {area} {provider}")
    if set(report.get("versions", {})) != set(jdks):
        raise ValueError("exception runtime inventory differs")
    for runtime, row in report["versions"].items():
        if (row.get("exit") != 0 or row.get("command") !=
                [str(jdks[runtime] / "bin/java"), "-version"]):
            raise ValueError("exception runtime command differs")
    identities = report.get("identities")
    if not isinstance(identities, list) or len(identities) != 27:
        raise ValueError("exception UID process inventory differs")
    for row in identities:
        provider = row.get("provider")
        name = row.get("type")
        if provider not in hashes or not isinstance(name, str):
            raise ValueError("exception UID process identity differs")
        command = [str(jdks["jdk21"] / "bin/javap"), "-p", "-constants",
                   "-classpath", str(original_work / f"{provider}.jar"), name]
        if row.get("exit") != 0 or row.get("command") != command:
            raise ValueError("exception UID process command differs")
    return relocate_exception_runs(report["runs"], original, output, jdks, area)


def verify_portable_exception(output: Path, original: Path, evidence: dict,
                              manifest: dict, hashes: dict[str, str],
                              jdks: dict[str, Path]) -> None:
    root = output / "exception-serialization"
    summary_row = evidence.get("exception_serialization", {})
    if summary_row.get("exit_code") != 0:
        raise ValueError("exception gate did not pass")
    summary = archived_json(output, "exception-serialization/result.json",
                            summary_row.get("report_sha256"))
    if (summary.get("status") != "PASSED" or summary.get("errors") != [] or
            summary.get("providers") != hashes or
            set(summary.get("adverse", {})) != {"uid", "payload"}):
        raise ValueError("exception summary or provider identity differs")
    fixture_sha = summary["fixture"]["report_sha256"]
    fixture = archived_json(output, "exception-serialization/fixture/result.json", fixture_sha)
    if (summary["fixture"].get("processes") != 636 or
            summary["fixture"].get("identities") != 27 or
            summary["fixture"].get("stream_count") != 90 or
            summary["public_api"].get("observations") != 18):
        raise ValueError("exception fixture inventory differs")
    source_root = declared_archive_root(manifest.get("source_root"))
    normalized = copy.deepcopy(fixture)
    normalized["runs"] = verify_exception_process_metadata(
        fixture, original, output, source_root, jdks, hashes, "fixture")
    validate_exception_report(normalized, root / "fixture", hashes,
                              exception_ci.PROBE_SHA, exception_ci.DRIVER_SHA, STDLIB_SHA)

    paths = {"result.json", "fixture/result.json"}
    for provider, expected in hashes.items():
        relative = f"fixture/{provider}.jar"
        if digest(root / relative) != expected:
            raise ValueError(f"exception frozen provider archive differs: {provider}")
        paths.add(relative)
    paths.update(f"fixture/{path.name}" for path in (root / "fixture").glob("*.ser"))

    public = archived_json(output, "exception-serialization/public-api/result.json",
                           summary["public_api"]["report_sha256"])
    golden = load_json_unique(exception_ci.GOLDEN.read_text())
    expected_public = {f"{provider}:{name}" for provider in ("jvm", "android")
                       for name in golden["types"]}
    if (public.get("reference_sha256") != digest(exception_ci.GOLDEN) or
            set(public.get("observations", {})) != expected_public or
            len(expected_public) != 18):
        raise ValueError("exception public API projection differs")
    paths.add("public-api/result.json")
    for key, expected in public["observations"].items():
        provider, name = key.split(":", 1)
        relative = f"public-api/{provider}-{name.rsplit('.', 1)[-1]}.txt"
        if digest(root / relative) != expected:
            raise ValueError(f"exception public API output differs: {key}")
        paths.add(relative)

    uid = summary["adverse"]["uid"]
    uid_report = archived_json(output, "exception-serialization/uid-adverse/result.json",
                               uid["report_sha256"])
    mutant = root / "uid-mutant.jar"
    if (uid_report.get("passed") is not False or uid_report.get("failure_count") != 19 or
            uid.get("failure_count") != 19 or len(uid_report.get("runs", [])) != 636 or
            digest(mutant) != uid.get("mutant_sha256") or
            uid_report.get("providers", {}).get("jvm", {}).get("sha256") != digest(mutant)):
        raise ValueError("exception UID adverse control differs")
    adverse_hashes = {**hashes, "jvm": digest(mutant)}
    adverse_runs = verify_exception_process_metadata(
        uid_report, original, output, source_root, jdks, adverse_hashes, "uid-adverse")
    identity_keys = {(row.get("provider"), row.get("type"))
                     for row in uid_report["identities"]}
    nominal_keys = {(row.get("provider"), row.get("type"))
                    for row in fixture["identities"]}
    if (uid_report.get("cases") != fixture.get("cases") or
            len(identity_keys) != 27 or identity_keys != nominal_keys or
            sum(row.get("matches") is False for row in uid_report["identities"]) != 1 or
            sum(row.get("matches") is False for row in adverse_runs) != 18):
        raise ValueError("exception UID adverse process inventory differs")
    def run_key(row):
        return tuple(row.get(name) for name in ("operation", "runtime", "provider",
                                                "writer_runtime", "writer_provider", "case"))
    if ({run_key(row) for row in adverse_runs} != {run_key(row) for row in normalized["runs"]} or
            len({run_key(row) for row in adverse_runs}) != 636):
        raise ValueError("exception UID adverse process keys differ")
    for row in adverse_runs:
        if row["operation"] == "write":
            stream = Path(row["command"][-2])
            if digest(stream) != row.get("stream_sha256"):
                raise ValueError("exception UID adverse stream differs")
    paths.update(("uid-adverse/result.json", "uid-mutant.jar"))
    payload = summary["adverse"]["payload"]
    if (digest(root / "payload-mutant.ser") != payload.get("mutant_sha256") or
            digest(root / "payload-adverse.log") != payload.get("read_log_sha256") or
            payload.get("validator_rejection") != "exception payload differs from pinned baseline" or
            "CAUSE=java.lang.IllegalStateException:cauze" not in
            (root / "payload-adverse.log").read_text()):
        raise ValueError("exception payload adverse control differs")
    paths.update(("payload-mutant.ser", "payload-adverse.log"))
    actual_files = {path.relative_to(root).as_posix(): digest(path) for path in root.rglob("*")
                    if path.is_file() and path.relative_to(root).as_posix() in paths}
    if len(paths) != 118 or actual_files != manifest["exception_files"]:
        raise ValueError("exception raw file set or hashes differ")


def verify_portable_world(output: Path, original: Path, evidence: dict,
                          manifest: dict, hashes: dict[str, str]) -> dict[str, Path]:
    work = output / "logs/world-fixtures"
    original_work = original / "logs/world-fixtures"
    row = evidence.get("world_fixtures", {})
    if (row.get("exit_code") != 0 or row.get("executions") != 138 or
            row.get("modes") != 23 or row.get("sources") != 12 or row.get("files") != 299):
        raise ValueError("World fixture summary differs")
    report = archived_json(output, "logs/world-fixtures/result.json", row.get("report_sha256"))
    if (report.get("status") != "PASSED" or
            report.get("candidate_sha") != evidence["candidate_sha"] or
            report.get("frozen_commit") != world_ci.FROZEN_COMMIT or
            report.get("source_sha256") != world_ci.SOURCE_SHA or
            report.get("artifacts") != hashes or
            report.get("bad_archive_sha256") != world_ci.BAD_ARCHIVE_SHA):
        raise ValueError("World source, artifact, or candidate identity differs")
    world_ci.validate_sources(world_ci.SOURCE_ROOT, world_ci.SOURCE_SHA)
    world_ci.validate_sources(work / "sources", world_ci.SOURCE_SHA)
    for provider, sha in hashes.items():
        if digest(work / "archives" / f"{provider}.jar") != sha:
            raise ValueError(f"World frozen provider archive differs: {provider}")
    bad = work / "archives/bad-body-view-bc71.jar"
    if digest(bad) != world_ci.BAD_ARCHIVE_SHA:
        raise ValueError("World adverse archive differs")
    tools = report.get("tools", {})
    for name, prefix in (("javac8", "javac 1.8"), ("java8", 'openjdk version "1.8'),
                         ("java21", 'openjdk version "21')):
        if not isinstance(tools.get(name), str) or not tools[name].startswith(prefix):
            raise ValueError(f"World recorded JDK version differs: {name}")
    jdks = report.get("jdks")
    if not isinstance(jdks, dict) or set(jdks) != {"jdk8", "jdk21"}:
        raise ValueError("World recorded JDK paths differ")
    jdks = {name: declared_archive_root(path) for name, path in jdks.items()}
    if report.get("stdlib") != {"path": str(original / "deps/kotlin-stdlib-2.4.20.jar"),
                                 "sha256": STDLIB_SHA}:
        raise ValueError("World recorded Kotlin standard library differs")
    if not isinstance(report.get("compiles"), dict) or set(report["compiles"]) != set(
            world_ci.PROVIDERS):
        raise ValueError("World Java 8 compile inventory differs")
    sources = [str(original_work / "sources" / name) for name in world_ci.SOURCE_SHA]
    for provider in world_ci.PROVIDERS:
        compile_row = report["compiles"][provider]
        relative = f"compiles/{provider}.json"
        raw = archived_json(work, relative, compile_row.get("log_sha256"))
        expected = [str(jdks["jdk8"] / "bin/javac"), "-cp",
                    str(original_work / "archives" / f"{provider}.jar"), "-d",
                    str(original_work / "classes" / provider), *sources]
        if (compile_row.get("log") != relative or compile_row.get("exit") != 0 or
                raw.get("exit") != 0 or raw.get("command") != expected):
            raise ValueError(f"World Java 8 compile command differs: {provider}")
    baseline_outputs = world_ci.validate_runs(report.get("runs"), work)
    for run_row in report["runs"]:
        provider, runtime, main, mode = (run_row[key] for key in
                                         ("provider", "runtime", "main", "mode"))
        raw = archived_json(work, run_row["log"], run_row["log_sha256"])
        classpath = os.pathsep.join((str(original_work / "classes" / provider),
                                     str(original_work / "archives" / f"{provider}.jar"),
                                     str(original / "deps/kotlin-stdlib-2.4.20.jar")))
        expected = [str(jdks[runtime] / "bin/java"), "-cp", classpath, main]
        if mode is not None:
            expected.append(mode)
        if raw.get("command") != expected or raw.get("stderr") != "":
            raise ValueError("World process command or stderr differs")
    adverse_compile = archived_json(work, "compiles/bad-body-view.json")
    bad_source = original_work / "sources/org/dyn4j/world/WorldSerializableViewsConsumer.java"
    expected_compile = [str(jdks["jdk8"] / "bin/javac"), "-cp",
                        str(original_work / "archives/bad-body-view-bc71.jar"), "-d",
                        str(original_work / "classes/bad-body-view"), str(bad_source)]
    if adverse_compile.get("exit") != 0 or adverse_compile.get("command") != expected_compile:
        raise ValueError("World adverse compile command differs")
    adverse = report.get("adverse")
    if not isinstance(adverse, dict) or set(adverse) != {"jdk8", "jdk21"}:
        raise ValueError("World adverse runtime inventory differs")
    for runtime, adverse_row in adverse.items():
        relative = f"adverse/{runtime}.json"
        raw = archived_json(work, relative, adverse_row.get("log_sha256"))
        classpath = os.pathsep.join((str(original_work / "classes/bad-body-view"),
                                     str(original_work / "archives/bad-body-view-bc71.jar"),
                                     str(original / "deps/kotlin-stdlib-2.4.20.jar")))
        expected = [str(jdks[runtime] / "bin/java"), "-cp", classpath,
                    "org.dyn4j.world.WorldSerializableViewsConsumer"]
        if (adverse_row.get("log") != relative or adverse_row.get("exit") != 0 or
                raw.get("exit") != 0 or raw.get("command") != expected or
                raw.get("stderr") != ""):
            raise ValueError(f"World adverse process differs: {runtime}")
        world_ci.validate_adverse_output(baseline_outputs[(
            runtime, "org.dyn4j.world.WorldSerializableViewsConsumer", None)], raw["stdout"])
    files = world_ci.seal_files(work, report.get("files"))
    if {"result.json": row["report_sha256"], **files} != manifest["world_files"]:
        raise ValueError("World raw file set or hashes differ")
    return jdks


def validate_corpus(report: dict) -> None:
    for key, marker, expected in (("actual_executed_cases", "ACTUAL_TESTS", 2385),
                                  ("failures", "FAILURES", 0), ("ignored", "IGNORED", 0)):
        if type(report.get(key)) is not int or report[key] != expected:
            raise ValueError(f"{key} must equal {expected}")
        if report.get("output", "").splitlines().count(f"{marker}={expected}") != 1:
            raise ValueError(f"missing or conflicting {marker} marker")
    if report.get("process_exit_code") != 0:
        raise ValueError("JUnit process failed")


def parameter_groups(identities: list[tuple[str, str]], expected: int) -> dict:
    groups = {}
    for class_name, (method_count, type_names) in PARAMETER_SUITES.items():
        rows = [name for owner, name in identities if owner == class_name]
        if not rows and expected != 2385:
            continue
        seen = {}
        for name in rows:
            match = PARAMETER_PATTERN.fullmatch(name)
            if match is None:
                raise ValueError(f"{class_name} parameter group name is malformed")
            method, parameter_type, address = match.groups()
            key = (parameter_type, address)
            seen.setdefault(key, []).append(method)
        if len(seen) != 5 or len(rows) != method_count * 5:
            raise ValueError(f"{class_name} parameter group count differs")
        actual_types = tuple(key[0] for key in seen)
        if actual_types != tuple(f"org.dyn4j.collision.broadphase.{name}" for name in type_names):
            raise ValueError(f"{class_name} parameter group types differ")
        expected_methods = set(next(iter(seen.values())))
        if len(expected_methods) != method_count or any(len(methods) != method_count or
                                                        set(methods) != expected_methods
                                                        for methods in seen.values()):
            raise ValueError(f"{class_name} parameter group methods differ")
        groups[class_name] = {key: index for index, key in enumerate(seen)}
    return groups


def validate_xml(path: Path, expected: int = 2385) -> list[tuple[str, str]]:
    suite = ET.parse(path).getroot()
    if suite.tag != "testsuite" or any(suite.get(key) != str(value) for key, value in
                                       (("tests", expected), ("failures", 0),
                                        ("errors", 0), ("skipped", 0))):
        raise ValueError("JUnit XML count or status differs")
    cases = suite.findall("testcase")
    if len(cases) != expected or any(not case.get("classname") or not case.get("name")
                                     or len(case) for case in cases):
        raise ValueError("JUnit XML lacks complete passing case identities")
    identities = [(case.get("classname"), case.get("name")) for case in cases]
    if len(set(identities)) != expected:
        raise ValueError("JUnit XML has duplicate or missing case identities")
    parameter_groups(identities, expected)
    return identities


def normalized_cases(identities: list[tuple[str, str]]) -> Counter:
    groups = parameter_groups(list(identities), len(identities)) if len(identities) == 2385 else {}
    normalized = []
    for class_name, name in identities:
        if class_name in groups:
            method, parameter_type, address = PARAMETER_PATTERN.fullmatch(name).groups()
            index = groups[class_name][(parameter_type, address)]
            name = f"{method}[{parameter_type}#{index}]"
        normalized.append((class_name, name))
    return Counter(normalized)


def seal_lanes(output: Path, evidence: dict, candidate_sha: str) -> dict[str, str]:
    if evidence.get("status") != "PASSED" or evidence.get("candidate_sha") != candidate_sha:
        raise ValueError("full compatibility result is not passing at candidate SHA")
    corpus = evidence.get("corpus")
    if not isinstance(corpus, dict) or {key for key in corpus if key in LANES} != LANES:
        raise ValueError("corpus lane inventory is incomplete")
    expected_files = {f"corpus-{lane}.{suffix}" for lane in LANES for suffix in ("xml", "json")}
    actual_files = {path.name for suffix in ("xml", "json")
                    for path in output.glob(f"corpus-*.{suffix}")}
    if actual_files != expected_files:
        raise ValueError("corpus XML/JSON file set differs")
    hashes = {}
    for lane in sorted(LANES):
        row = corpus[lane]
        if row.get("status") != "PASSED" or row.get("cases") != 2385:
            raise ValueError(f"{lane} did not pass all 2385 cases")
        for suffix, field in (("xml", "xml_sha256"), ("json", "report_sha256")):
            name = f"corpus-{lane}.{suffix}"
            path = output / name
            if row.get("xml" if suffix == "xml" else "report") != name or not path.is_file() or path.is_symlink():
                raise ValueError(f"{name} is missing from passing evidence")
            actual = digest(path)
            if row.get(field) != actual:
                raise ValueError(f"{name} hash differs from passing evidence")
            hashes[name] = actual
    return hashes


def validate_projection(report: dict, work: Path, fixture: Path,
                        providers: dict[str, str], audit_sha: str) -> None:
    if report.get("audit_sha256") != audit_sha or report.get("providers") != providers:
        raise ValueError("source projection input or provider hashes differ")
    expected_keys = {(provider, compiler, runtime) for provider in providers
                     for compiler in ("jdk8", "jdk21") for runtime in ("jdk8", "jdk21")}
    observations = report.get("observations")
    if not isinstance(observations, list) or len(observations) != 12:
        raise ValueError("source projection observation matrix is incomplete")
    observed_keys = set()
    for row in observations:
        if not isinstance(row, dict):
            raise ValueError("source projection observation is malformed")
        key = (row.get("provider"), row.get("compiler"), row.get("runtime"))
        if key in observed_keys or key not in expected_keys or type(row.get("probes")) is not int or row["probes"] != 77:
            raise ValueError("source projection lane or probe count differs")
        observed_keys.add(key)
        log = work / f"run-{'-'.join(key)}.log"
        if not log.is_file() or digest(log) != row.get("run_log_sha256") or log.read_text().strip() != "(1.0, 2.0)\nACTUAL_PROBES=77":
            raise ValueError("source projection runtime log differs")
    if observed_keys != expected_keys:
        raise ValueError("source projection provider/compiler/runtime set differs")
    source_hashes = report.get("source_sha256")
    source_root = work / "sources"
    generated = {str(path.relative_to(source_root)): path for path in source_root.rglob("*.java")}
    fixtures = ("extra/Names.java", "org/dyn4j/geometry/simplify/NodeDispatchProbe.java")
    probes = [name for name in generated if re.fullmatch(r"(?:[^/]+/)+ProjectionProbe(0[1-9]|[1-6][0-9]|7[0-7])\.java", name)]
    if (report.get("source_count") != 80 or len(probes) != 77 or
            {int(re.search(r"Probe(\d+)\.java$", name)[1]) for name in probes} != set(range(1, 78)) or
            set(generated) != set(probes) | {"projection/Suite.java"} or
            not isinstance(source_hashes, dict) or set(source_hashes) != set(generated) | set(fixtures)):
        raise ValueError("source projection source inventory differs")
    for name, path in {**generated, **{name: fixture / name for name in fixtures}}.items():
        if not path.is_file() or digest(path) != source_hashes[name]:
            raise ValueError(f"source projection source hash differs: {name}")


def validate_source_inputs(source: Path, hashes: dict, expected_count: int = 218) -> None:
    if len(hashes) != expected_count:
        raise ValueError("pinned test input inventory is incomplete")
    root = source.resolve()
    for relative, expected in hashes.items():
        path = (source / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file() or digest(path) != expected:
            raise ValueError(f"pinned test source or resource changed: {relative}")


def validate_audit(report: dict, candidate_hash: str) -> None:
    api_types = report.get("compared_api_types")
    if (not isinstance(api_types, list) or len(api_types) != 216
            or any(not isinstance(name, str) or not name for name in api_types)
            or len(set(api_types)) != 216
            or report.get("compared_baseline_declarations") != 3078):
        raise ValueError("required declaration inventory is incomplete")
    if report.get("baseline_sha256") != BASELINE_SHA or report.get("candidate_sha256") != candidate_hash:
        raise ValueError("comparison archive hash differs")
    for key in ("missing_types", "signature_mismatches", "added_member_risks",
                "inventory_errors", "fixture_failures", "fixture_errors"):
        if report.get(key) != []:
            raise ValueError(f"strict comparison has {key}")
    observed = {row.get("source_sha256") for row in report.get("fixture_results", [])}
    if observed != FIXTURE_SHA or len(report["fixture_results"]) != len(FIXTURE_SHA):
        raise ValueError("permanent Java 8 fixtures were omitted or changed")
    if any(row.get("baseline_exit_code") != 0 or row.get("candidate_exit_code") != 0
           for row in report["fixture_results"]):
        raise ValueError("permanent Java 8 fixture compilation failed")


def run(command: list[str], log: Path, *, env: dict | None = None,
        timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True,
                            timeout=timeout, check=False)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(result.stdout + result.stderr)
    return result


def checked_archive(path: Path, label: str) -> str:
    if not path.is_file() or path.is_symlink() or not path.stat().st_size:
        raise ValueError(f"missing or empty {label}: {path}")
    return digest(path)


def fetch(url: str, path: Path, expected: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        urllib.request.urlretrieve(url, path)
    actual = checked_archive(path, url)
    if actual != expected:
        raise ValueError(f"dependency SHA-256 differs: {url}")
    return actual


def version(jdk: Path, executable: str, major: int) -> str:
    binary = jdk / "bin" / executable
    if not binary.is_file():
        raise ValueError(f"missing {executable}: {binary}")
    observed = subprocess.run([str(binary), "-version"], capture_output=True, text=True,
                              check=False)
    value = (observed.stdout + observed.stderr).strip()
    pattern = r"(?:1\.8\.|\b8(?:\.|\b))" if major == 8 else r"\b21(?:\.|\b)"
    if observed.returncode or not re.search(pattern, value):
        raise ValueError(f"expected Java {major} {executable}, got {value}")
    return value.splitlines()[0]


def staged_archives(staging: Path, output: Path) -> tuple[dict[str, Path], dict[str, str]]:
    base = staging / "io/github/rubixhacker"
    jvm = base / "dyn4k-core-jvm" / VERSION / f"dyn4k-core-jvm-{VERSION}.jar"
    aar = base / "dyn4k-core-android" / VERSION / f"dyn4k-core-android-{VERSION}.aar"
    hashes = {"staged_jvm_jar": checked_archive(jvm, "staged JVM JAR"),
              "staged_android_aar": checked_archive(aar, "staged Android AAR")}
    archived = output / "archives"
    archived.mkdir(parents=True, exist_ok=True)
    for archive in (jvm, aar):
        sidecar = archive.with_name(archive.name + ".sha256")
        checked_archive(sidecar, "staged SHA-256 sidecar")
        if sidecar.read_text().strip().lower() != digest(archive):
            raise ValueError(f"staged checksum differs: {archive}")
        shutil.copy2(archive, archived / archive.name)
        shutil.copy2(sidecar, archived / sidecar.name)
        if digest(archived / archive.name) != digest(archive):
            raise ValueError(f"staged archive changed during capture: {archive}")
    with zipfile.ZipFile(archived / aar.name) as opened:
        members = [name for name in opened.namelist() if name == "classes.jar"]
        if len(members) != 1:
            raise ValueError("Android AAR lacks one classes.jar")
        android = output / "android-classes.jar"
        android.write_bytes(opened.read(members[0]))
    hashes["staged_android_classes_jar"] = checked_archive(android, "Android classes.jar")
    return {"jvm": archived / jvm.name, "android": android}, hashes


def junit_report(output: str, exit_code: int) -> dict:
    def field(label: str) -> int | None:
        matches = [line.split("=", 1)[1] for line in output.splitlines()
                   if line.startswith(label + "=")]
        return int(matches[0]) if len(matches) == 1 and matches[0].isdigit() else None

    return {"actual_executed_cases": field("ACTUAL_TESTS"), "failures": field("FAILURES"),
            "ignored": field("IGNORED"), "process_exit_code": exit_code, "output": output}


def corpus_matrix(source: Path, providers: dict[str, Path], deps: list[Path],
                  jdks: dict[int, Path], output: Path, evidence: dict) -> None:
    tests = sorted((source / "src/test/java").rglob("*.java"))
    classes = sorted({".".join(path.relative_to(source / "src/test/java").with_suffix("").parts)
                      for path in tests if "@Test" in path.read_text(errors="replace")
                      or "@RunWith" in path.read_text(errors="replace")})
    if len(tests) != 199 or len(classes) != 190:
        raise ValueError(f"pinned test inventory changed: {len(tests)} files, {len(classes)} classes")
    harness = ROOT / "tools/compatibility/PinnedCorpusReport.java"
    evidence["archives"]["corpus_harness_source"] = checked_archive(harness, "JUnit XML harness")
    argfile = output / "test-sources.args"
    argfile.write_text("\n".join('"' + str(path) + '"' for path in tests) + "\n")
    expected_identities = None
    for provider, archive in providers.items():
        for compiler_major, compiler in jdks.items():
            key = f"{provider}-javac{compiler_major}"
            classes_dir = output / "classes" / key
            classes_dir.mkdir(parents=True, exist_ok=True)
            cp = os.pathsep.join(str(path) for path in
                                 [archive, *([] if provider == "baseline" else deps[:2]), *deps[2:]])
            options = (["-source", "8", "-target", "8"] if compiler_major == 8
                       else ["--release", "8"])
            command = [str(compiler / "bin/javac"), "-encoding", "UTF-8", *options,
                       "-cp", cp, "-d", str(classes_dir), "@" + str(argfile), str(harness)]
            compiled = run(command, output / "logs" / f"compile-{key}.log")
            evidence["corpus"][key] = {"compile_exit_code": compiled.returncode,
                                       "compile_log_sha256": digest(output / "logs" / f"compile-{key}.log")}
            if compiled.returncode:
                evidence["errors"].append(f"{key}: unchanged source did not compile")
                continue
            resources = source / "src/test/resources"
            if resources.exists():
                shutil.copytree(resources, classes_dir, dirs_exist_ok=True)
            for runtime_major, runtime in jdks.items():
                case = f"{key}-java{runtime_major}"
                xml = output / f"corpus-{case}.xml"
                result = run([str(runtime / "bin/java"), "-cp", os.pathsep.join([cp, str(classes_dir)]),
                              "PinnedCorpusReport", str(xml), *classes],
                             output / "logs" / f"run-{case}.log")
                report = junit_report(result.stdout, result.returncode)
                report.update({"provider": provider, "compiler": compiler_major,
                               "runtime": runtime_major, "archive_sha256": digest(archive),
                               "run_log_sha256": digest(output / "logs" / f"run-{case}.log"),
                               "xml_sha256": digest(xml) if xml.is_file() else None})
                (output / f"corpus-{case}.json").write_text(json.dumps(report, indent=2) + "\n")
                try:
                    validate_corpus(report)
                    identities = validate_xml(xml)
                    normalized = normalized_cases(identities)
                    if expected_identities is None:
                        expected_identities = normalized
                    elif normalized != expected_identities:
                        raise ValueError("JUnit case identities differ from pinned baseline run")
                    identity_hash = hashlib.sha256(json.dumps(sorted(
                        (class_name, name, count) for (class_name, name), count in normalized.items()
                    )).encode()).hexdigest()
                    report["case_id_sha256"] = identity_hash
                    (output / f"corpus-{case}.json").write_text(json.dumps(report, indent=2) + "\n")
                    evidence["corpus"][case] = {"status": "PASSED", "report": f"corpus-{case}.json",
                                                "xml": f"corpus-{case}.xml", "xml_sha256": digest(xml),
                                                "report_sha256": digest(output / f"corpus-{case}.json"),
                                                "cases": 2385, "case_id_sha256": identity_hash}
                except (OSError, ValueError, ET.ParseError) as error:
                    evidence["errors"].append(f"{case}: {error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pinned Java corpus and staged archive audits.")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--staging-repository", type=Path, required=True)
    parser.add_argument("--jdk8", type=Path, required=True)
    parser.add_argument("--jdk21", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    evidence = {"candidate_sha": args.candidate_sha, "status": "FAILED", "errors": [],
                "archives": {}, "tools": {}, "baseline": {}, "audits": {},
                "corpus": {}, "source_projection": {}, "exception_serialization": {},
                "world_fixtures": {}}
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if head != args.candidate_sha:
            raise ValueError(f"candidate SHA differs from checkout: {head}")
        jdks = {8: args.jdk8.resolve(), 21: args.jdk21.resolve()}
        for major, jdk in jdks.items():
            evidence["tools"][f"javac{major}"] = version(jdk, "javac", major)
            evidence["tools"][f"java{major}"] = version(jdk, "java", major)
        archives, hashes = staged_archives(args.staging_repository.resolve(), output)
        evidence["archives"].update(hashes)
        deps_dir = output / "deps"
        stdlib = deps_dir / "kotlin-stdlib-2.4.20.jar"
        annotations = deps_dir / "annotations-13.0.jar"
        fetch("https://repo.maven.apache.org/maven2/org/jetbrains/kotlin/kotlin-stdlib/2.4.20/kotlin-stdlib-2.4.20.jar", stdlib,
              STDLIB_SHA)
        fetch("https://repo.maven.apache.org/maven2/org/jetbrains/annotations/13.0/annotations-13.0.jar", annotations,
              ANNOTATIONS_SHA)
        evidence["archives"].update({"kotlin_stdlib": digest(stdlib), "annotations": digest(annotations)})
        baseline_cache = output / "baseline-cache"
        env = {**os.environ, "JAVA_HOME": str(jdks[21]),
               "PATH": str(jdks[21] / "bin") + os.pathsep + os.environ["PATH"]}
        baseline = run([sys.executable, str(ROOT / "tools/baseline/verify.py"),
                        "--cache", str(baseline_cache), "--inventory", str(output / "baseline-inventory.json"),
                        "--summary", str(output / "baseline-run.json")],
                       output / "logs/baseline-verify.log", env=env, timeout=1800)
        evidence["baseline"]["verify_exit_code"] = baseline.returncode
        if baseline.returncode:
            evidence["errors"].append("pinned baseline source, archive, or corpus verification failed")
        else:
            baseline_report = json.loads((output / "baseline-run.json").read_text())
            validate_corpus(baseline_report)
            evidence["baseline"].update({"source_revision": baseline_report["commit"],
                                         "executed_cases": baseline_report["actual_executed_cases"],
                                         "inventory_sha256": digest(output / "baseline-inventory.json"),
                                         "run_sha256": digest(output / "baseline-run.json")})
        binary = baseline_cache / "dyn4j-6.0.0.jar"
        if checked_archive(binary, "pinned baseline JAR") != BASELINE_SHA:
            raise ValueError("pinned baseline JAR hash differs")
        if baseline.returncode:
            raise ValueError("baseline verification must pass before candidate checks")
        source = baseline_cache / "dyn4j-source"
        validate_source_inputs(source, baseline_report["test_input_sha256"])
        junit = baseline_cache / "deps/junit-4.13.1.jar"
        hamcrest = baseline_cache / "deps/hamcrest-core-1.3.jar"
        for path in (junit, hamcrest):
            evidence["archives"][path.name] = checked_archive(path, path.name)
        for name, archive in archives.items():
            result = run([sys.executable, str(ROOT / "tools/baseline/verify.py"), "compare",
                          "--baseline-jar", str(binary), "--candidate", str(archive),
                          "--require-fixture", *(part for fixture in FIXTURES for part in
                                                 ("--fixture", str(fixture))),
                          "--dependency-jar", str(stdlib), "--dependency-jar", str(annotations)],
                         output / "logs" / f"audit-{name}.log", env=env, timeout=1800)
            try:
                audit = json.loads(result.stdout)
                (output / f"audit-{name}.json").write_text(json.dumps(audit, indent=2) + "\n")
                validate_audit(audit, digest(archive))
                if result.returncode:
                    raise ValueError("strict compare process failed")
                evidence["audits"][name] = {"status": "PASSED", "report": f"audit-{name}.json",
                                             "report_sha256": digest(output / f"audit-{name}.json")}
            except ValueError as error:
                evidence["audits"][name] = {"status": "FAILED", "exit_code": result.returncode}
                evidence["errors"].append(f"{name} strict audit: {error}")
        adverse_audit = PROJECTION / "frozen-adverse-audit.json"
        if checked_archive(adverse_audit, "frozen adverse audit") != ADVERSE_AUDIT_SHA:
            raise ValueError("frozen adverse audit hash differs")
        projection = run([sys.executable, str(PROJECTION / "probe_added_members.py"),
                          "--audit", str(adverse_audit),
                          "--baseline", str(binary), "--candidate", f"jvm={archives['jvm']}",
                          "--candidate", f"android={archives['android']}",
                          "--stdlib", str(stdlib), "--annotations", str(annotations),
                          "--jdk8", str(jdks[8]), "--jdk21", str(jdks[21]),
                          "--work", str(output / "projection")],
                         output / "logs/source-projection.log", timeout=1800)
        evidence["source_projection"]["exit_code"] = projection.returncode
        if projection.returncode:
            evidence["errors"].append("adverse Java source projection or node dispatch failed")
        else:
            try:
                projection_report = json.loads((output / "projection/result.json").read_text())
                validate_projection(projection_report, output / "projection", PROJECTION,
                                    {"baseline": BASELINE_SHA,
                                     "jvm": hashes["staged_jvm_jar"],
                                     "android": hashes["staged_android_classes_jar"]},
                                    ADVERSE_AUDIT_SHA)
                evidence["source_projection"].update({"report_sha256": digest(output / "projection/result.json"),
                                                      "observations": len(projection_report["observations"])})
            except (OSError, ValueError, KeyError, TypeError) as error:
                evidence["errors"].append(f"source projection report: {error}")
        exception = run([sys.executable, str(ROOT / "tools/compatibility/exception_ci.py"),
                         "--baseline", str(binary), "--jvm", str(archives["jvm"]),
                         "--android", str(archives["android"]),
                         "--java8", str(jdks[8]), "--java21", str(jdks[21]),
                         "--stdlib", str(stdlib),
                         "--output", str(output / "exception-serialization")],
                        output / "logs/exception-serialization.log", timeout=3600)
        evidence["exception_serialization"]["exit_code"] = exception.returncode
        exception_report = output / "exception-serialization/result.json"
        if exception_report.is_file():
            evidence["exception_serialization"]["report_sha256"] = digest(exception_report)
        if exception.returncode:
            evidence["errors"].append("exception serialization fixture or adverse controls failed")
        else:
            try:
                checked = json.loads(exception_report.read_text())
                if (checked.get("status") != "PASSED" or checked.get("providers") != {
                        "baseline": BASELINE_SHA, "jvm": hashes["staged_jvm_jar"],
                        "android": hashes["staged_android_classes_jar"]} or
                        checked.get("fixture", {}).get("processes") != 636 or
                        checked.get("fixture", {}).get("identities") != 27 or
                        checked.get("public_api", {}).get("observations") != 18 or
                        set(checked.get("adverse", {})) != {"uid", "payload"}):
                    raise ValueError("exception serialization result is incomplete")
            except (OSError, ValueError, KeyError, TypeError) as error:
                evidence["errors"].append(f"exception serialization report: {error}")
        world_output = output / "logs/world-fixtures"
        world = run([sys.executable, str(ROOT / "tools/compatibility/world_ci.py"),
                     "--candidate-sha", args.candidate_sha,
                     "--baseline", str(binary), "--jvm", str(archives["jvm"]),
                     "--android", str(archives["android"]),
                     "--java8", str(jdks[8]), "--java21", str(jdks[21]),
                     "--stdlib", str(stdlib), "--output", str(world_output)],
                    output / "logs/world-fixtures.log", timeout=3600)
        evidence["world_fixtures"]["exit_code"] = world.returncode
        world_report = world_output / "result.json"
        if world_report.is_file():
            evidence["world_fixtures"]["report_sha256"] = digest(world_report)
        if world.returncode:
            evidence["errors"].append("frozen World Java fixture or adverse control failed")
        else:
            try:
                sealed_world = seal_world(world_output, args.candidate_sha,
                                          {"baseline": BASELINE_SHA,
                                           "jvm": hashes["staged_jvm_jar"],
                                           "android": hashes["staged_android_classes_jar"]},
                                          evidence["world_fixtures"]["report_sha256"])
                evidence["world_fixtures"].update({"executions": 138, "modes": 23,
                                                    "sources": 12, "files": len(sealed_world)})
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                evidence["errors"].append(f"World fixture report: {error}")
        corpus_matrix(source, {"baseline": binary, "candidate": archives["jvm"],
                               "android": archives["android"]},
                      [stdlib, annotations, junit, hamcrest], jdks, output, evidence)
        validate_source_inputs(source, baseline_report["test_input_sha256"])
        source_check = run([sys.executable, str(ROOT / "tools/baseline/verify.py"), "check-source",
                            "--checkout", str(source),
                            "--sources-jar", str(baseline_cache / "dyn4j-6.0.0-sources.jar"),
                            "--commit", baseline_report["commit"]],
                           output / "logs/final-source-check.log")
        evidence["baseline"]["final_source_check_exit_code"] = source_check.returncode
        if source_check.returncode:
            evidence["errors"].append("pinned source or source archive changed after corpus execution")
        for label, path, expected in (("staged JVM JAR", archives["jvm"], hashes["staged_jvm_jar"]),
                                      ("staged Android AAR", output / "archives" /
                                       f"dyn4k-core-android-{VERSION}.aar", hashes["staged_android_aar"]),
                                      ("Android classes.jar", archives["android"],
                                       hashes["staged_android_classes_jar"]),
                                      ("Kotlin standard library", stdlib, STDLIB_SHA),
                                      ("annotations", annotations, ANNOTATIONS_SHA)):
            if checked_archive(path, label) != expected:
                evidence["errors"].append(f"{label} changed after verification")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.TimeoutExpired,
            zipfile.BadZipFile) as error:
        evidence["errors"].append(str(error))
    if not evidence["errors"]:
        try:
            seal_lanes(output, {**evidence, "status": "PASSED"}, args.candidate_sha)
            seal_exception(output / "exception-serialization",
                           {"baseline": BASELINE_SHA,
                            "jvm": evidence["archives"]["staged_jvm_jar"],
                            "android": evidence["archives"]["staged_android_classes_jar"]},
                           evidence["exception_serialization"]["report_sha256"])
            seal_world(output / "logs/world-fixtures", args.candidate_sha,
                       {"baseline": BASELINE_SHA,
                        "jvm": evidence["archives"]["staged_jvm_jar"],
                        "android": evidence["archives"]["staged_android_classes_jar"]},
                       evidence["world_fixtures"]["report_sha256"])
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            evidence["errors"].append(str(error))
    evidence["status"] = "PASSED" if not evidence["errors"] else "FAILED"
    (output / "result.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({"status": evidence["status"], "errors": evidence["errors"]}, indent=2))
    return 0 if evidence["status"] == "PASSED" else 1


def seal_main() -> int:
    parser = argparse.ArgumentParser(description="Seal the full compatibility lane evidence before upload.")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[2:])
    output = args.output.resolve()
    manifest = {"candidate_sha": args.candidate_sha, "status": "FAILED",
                "files": {}, "exception_files": {}, "world_files": {},
                "archive_root": str(output), "source_root": str(ROOT),
                "archive_files": {}, "error": None}
    try:
        evidence = json.loads((output / "result.json").read_text())
        manifest["files"] = seal_lanes(output, evidence, args.candidate_sha)
        manifest["exception_files"] = seal_exception(
            output / "exception-serialization",
            {"baseline": BASELINE_SHA,
             "jvm": evidence["archives"]["staged_jvm_jar"],
             "android": evidence["archives"]["staged_android_classes_jar"]},
            evidence["exception_serialization"]["report_sha256"])
        manifest["world_files"] = seal_world(
            output / "logs/world-fixtures", args.candidate_sha,
            {"baseline": BASELINE_SHA,
             "jvm": evidence["archives"]["staged_jvm_jar"],
             "android": evidence["archives"]["staged_android_classes_jar"]},
            evidence["world_fixtures"]["report_sha256"])
        manifest["archive_files"] = snapshot_archive(output)
        manifest["status"] = "PASSED"
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        manifest["error"] = str(error)
        manifest["files"] = {path.name: digest(path) for suffix in ("xml", "json")
                             for path in output.glob(f"corpus-*.{suffix}") if path.is_file()}
        world_output = output / "logs/world-fixtures"
        manifest["world_files"] = {path.relative_to(world_output).as_posix(): digest(path)
                                   for path in world_output.rglob("*") if path.is_file()}
    output.mkdir(parents=True, exist_ok=True)
    (output / "lane-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"status": manifest["status"], "files": len(manifest["files"]),
                      "exception_files": len(manifest["exception_files"]),
                      "world_files": len(manifest["world_files"]),
                      "error": manifest["error"]}, indent=2))
    return 0 if manifest["status"] == "PASSED" else 1


def verify_archive(output: Path, candidate_sha: str,
                   manifest_sha: str | None = None) -> dict[str, int]:
    manifest_path = output / "lane-manifest.json"
    if manifest_sha is not None and digest(manifest_path) != manifest_sha:
        raise ValueError("archive manifest SHA-256 differs")
    manifest = load_json_unique(manifest_path.read_text())
    if (manifest.get("status") != "PASSED" or manifest.get("error") is not None or
            manifest.get("candidate_sha") != candidate_sha):
        raise ValueError("archive manifest is not passing at candidate SHA")
    original = declared_archive_root(manifest.get("archive_root"))
    inventory = verify_archive_files(output, manifest.get("archive_files"))
    for name in inventory:
        if name.endswith(".json"):
            archived_json(output, name)
    evidence = archived_json(output, "result.json")
    if (evidence.get("status") != "PASSED" or evidence.get("errors") != [] or
            evidence.get("candidate_sha") != candidate_sha):
        raise ValueError("full compatibility result is not passing at candidate SHA")
    for field, expected, prefix in (("files", 24, ""),
                                    ("exception_files", 118, "exception-serialization/"),
                                    ("world_files", 299, "logs/world-fixtures/")):
        recorded = manifest.get(field)
        if not isinstance(recorded, dict) or len(recorded) != expected or any(
                inventory.get(prefix + name) != sha for name, sha in recorded.items()):
            raise ValueError(f"archive {field} files differ")
    hashes = verify_portable_inputs(output, evidence)
    verify_portable_audits(output, evidence, hashes)
    verify_portable_corpus(output, evidence, candidate_sha, manifest, hashes)
    jdks = verify_portable_world(output, original, evidence, manifest, hashes)
    verify_portable_exception(output, original, evidence, manifest, hashes, jdks)
    return {"files": len(inventory), "corpus_files": 24,
            "exception_files": 118, "world_files": 299}


def verify_main() -> int:
    parser = argparse.ArgumentParser(description="Verify a relocated full compatibility archive.")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args(sys.argv[2:])
    try:
        result = verify_archive(args.output.absolute(), args.candidate_sha,
                                args.manifest_sha256)
        print(json.dumps({"status": "PASSED", **result}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError,
            ET.ParseError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        print(json.dumps({"status": "FAILED", "error": str(error)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(seal_main() if sys.argv[1:2] == ["seal"] else
                     verify_main() if sys.argv[1:2] == ["verify"] else main())
