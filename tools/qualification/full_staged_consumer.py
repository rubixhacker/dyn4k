#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import independent_gates


CLASS = "org.dyn4j.geometry.Vector2NormalizationParityTest"
LANE = "jvm:Java:current:default"
VERSION = "0.1.0-alpha.1"
GROUP = "io.github.rubixhacker"
MODULES = ("dyn4k-core", "dyn4k")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def git_blob(repository, candidate, path):
    return subprocess.check_output(["git", "--no-replace-objects", "-C", str(repository),
                                    "show", f"{candidate}:{path}"], stderr=subprocess.PIPE)


def class_contract(manifest, lane, classname):
    selected = independent_gates.consumer_contract(manifest, lane)["cases"]
    cases = [item for item in selected if item["classname"] == classname]
    if not cases or len({item["id"] for item in cases}) != len(cases):
        raise ValueError("original class cases are missing or duplicated")
    sources = {(item["source"]["path"], item["source"]["sha256"])
               for item in cases}
    if len(sources) != 1:
        raise ValueError("original class source identity differs")
    source, source_hash = sources.pop()
    if (source != "dyn4k-core/src/commonTest/kotlin/org/dyn4j/geometry/Vector2NormalizationParityTest.kt"
            or not SHA256.fullmatch(source_hash)
            or any(item["module"] != "dyn4k-core"
                   or item["id"] != f"dyn4k-core:{classname}#{item['method']}"
                   for item in cases)):
        raise ValueError("original class is outside the bounded staged route")
    return {item["id"] for item in cases}, source, source_hash


def raw_case_ids(raw, expected):
    suite = ET.fromstring(raw)
    if suite.tag != "testsuite":
        raise ValueError("raw consumer report root differs")
    cases = list(suite.iter("testcase"))
    counts = {"tests": len(cases),
              "failures": sum(case.find("failure") is not None for case in cases),
              "errors": sum(case.find("error") is not None for case in cases),
              "skipped": sum(case.find("skipped") is not None for case in cases)}
    if (any(suite.get(key) is None or int(suite.get(key)) != value
            for key, value in counts.items())
            or any(counts[key] for key in ("failures", "errors", "skipped"))
            or not math.isfinite(float(suite.get("time", "nan")))
            or float(suite.get("time", "nan")) < 0):
        raise ValueError("raw consumer report counts or outcomes differ")
    ids = []
    for case in cases:
        classname, name = case.get("classname"), case.get("name")
        if (classname != CLASS or not name or not name.endswith("[jvm]")
                or not name[:-5] or name[:-5].endswith("[jvm]")
                or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name[:-5])
                or not math.isfinite(float(case.get("time", "nan")))
                or float(case.get("time", "nan")) < 0):
            raise ValueError("raw consumer case identity differs")
        case_id = f"dyn4k-core:{classname}#{name[:-5]}"
        if case_id not in expected:
            raise ValueError("raw consumer report has a foreign case")
        ids.append(case_id)
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError("raw consumer cases are missing or duplicated")
    return set(ids)


def staged_binary(staging, module):
    name = f"{module}-jvm-{VERSION}.jar"
    return staging / GROUP.replace(".", "/") / f"{module}-jvm" / VERSION / name


def graph_artifacts(graph, staging, expected_hashes):
    if graph.get("configuration") != "jvmTestRuntimeClasspath":
        raise ValueError("external consumer graph configuration differs")
    artifacts = graph.get("artifacts")
    components = graph.get("components")
    if (not isinstance(artifacts, list) or not isinstance(components, list)
            or len(components) != len(set(components))):
        raise ValueError("external consumer graph is invalid")
    required = {f"{GROUP}:{module}-jvm:{VERSION}" for module in MODULES}
    roots = {f"{GROUP}:{module}:{VERSION}" for module in MODULES}
    if ({item for item in components if item.startswith(f"{GROUP}:")}
            != required | roots):
        raise ValueError("external consumer graph has a missing or foreign provider")
    observed = {}
    for module in MODULES:
        component = f"{GROUP}:{module}-jvm:{VERSION}"
        matches = [item for item in artifacts if item.get("component") == component]
        if len(matches) != 1:
            raise ValueError("external consumer graph has a missing or duplicate artifact")
        item = matches[0]
        path = Path(item.get("file", ""))
        if (not path.is_absolute() or path != staged_binary(staging, module)
                or item.get("name") != path.name or not isinstance(item.get("size"), int)
                or isinstance(item["size"], bool) or item["size"] <= 0
                or item.get("sha256") != expected_hashes[module]):
            raise ValueError("external consumer did not resolve the exact staged binary")
        observed[module] = item
    if (sorted(item["component"] for item in artifacts
               if str(item.get("component", "")).startswith(f"{GROUP}:"))
            != sorted(required)):
        raise ValueError("external consumer graph has extra staged artifacts")
    return observed


def graph_from_output(output):
    lines = [line.removeprefix("DYN4K_FULL_SUITE_GRAPH=")
             for line in output.splitlines()
             if line.startswith("DYN4K_FULL_SUITE_GRAPH=")]
    if len(lines) != 1:
        raise ValueError("external staged graph observation is missing or duplicate")
    return json.loads(lines[0])


def process(command, cwd, stdout, stderr):
    started = time.time_ns()
    result = subprocess.run(command, cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False)
    finished = time.time_ns()
    stdout.write_bytes(result.stdout)
    stderr.write_bytes(result.stderr)
    return {"command": command, "cwd": str(cwd), "started_ns": started,
            "finished_ns": finished, "exit_code": result.returncode,
            "stdout": str(stdout.relative_to(stdout.parents[1])),
            "stderr": str(stderr.relative_to(stderr.parents[1]))}


def inventory(root):
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("partial archive contains a symlink")
        if path.is_file() and path != root / "receipt.json":
            files[str(path.relative_to(root))] = {
                "sha256": sha(path.read_bytes()), "mtime_ns": path.stat().st_mtime_ns}
    return files


def run(repository, candidate, staging, output, gradle, expected_hashes):
    repository, staging, output, gradle = (Path(value).resolve()
                                           for value in (repository, staging, output, gradle))
    if output.exists() and any(output.iterdir()):
        raise ValueError("raw output directory must be empty")
    java_home = Path(os.environ["JAVA_HOME"]).resolve()
    java = java_home / "bin/java"
    java_version = subprocess.check_output([str(java), "-version"],
                                           stderr=subprocess.STDOUT, text=True).splitlines()[0]
    gradle_version = subprocess.check_output([str(gradle), "--version"],
                                             text=True).splitlines()
    if ('version "21' not in java_version
            or "Gradle 9.5.0" not in gradle_version):
        raise ValueError("bounded consumer requires JDK 21 and Gradle 9.5.0")
    head = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"],
                                   text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(repository), "status",
                                     "--porcelain", "--untracked-files=no"], text=True)
    if head != candidate or dirty:
        raise ValueError("producer checkout is not the exact clean candidate")
    manifest = independent_gates.load_approved_manifest(repository)
    case_ids, source, source_hash = class_contract(manifest, LANE, CLASS)
    if sha(git_blob(repository, candidate, source)) != source_hash:
        raise ValueError("candidate original source differs from approved manifest")
    if (repository / source).read_bytes() != git_blob(repository, candidate, source):
        raise ValueError("original source checkout differs from candidate")
    for module in MODULES:
        if sha(staged_binary(staging, module).read_bytes()) != expected_hashes[module]:
            raise ValueError("staged binary differs from the independent expected hash")
    output.mkdir(parents=True, exist_ok=True)
    (output / "raw").mkdir()
    (output / "resolved").mkdir()
    consumer = repository / "consumers/qualification/portable"
    source_arg = source.split("src/commonTest/kotlin/", 1)[1]
    common = [str(gradle), "-p", str(consumer), "--offline", "--no-daemon",
              "--console=plain", f"-PqualificationRepository={staging}",
              f"-PqualificationSuiteCheckout={repository}",
              f"-PqualificationSuiteSource={source_arg}", f"-PqualificationLaneId={LANE}"]
    reports = consumer / "build/test-results/jvmTest"
    for old in reports.glob("TEST-*.xml"):
        old.unlink()
    test = process([*common, "--rerun-tasks", "jvmTest"], repository,
                   output / "raw/test.stdout", output / "raw/test.stderr")
    test_output = (output / test["stdout"]).read_text()
    if (test["exit_code"] or not all(any(line.strip() == f"> Task :{task}"
                                        for line in test_output.splitlines())
                                     for task in ("compileTestKotlinJvm", "qualificationSuiteGraph",
                                                  "jvmTest"))
            or "BUILD SUCCESSFUL" not in test_output):
        raise ValueError("external original-source JVM test task failed")
    staged_graph = graph_from_output(test_output)
    graph_artifacts(staged_graph, staging, expected_hashes)
    originals = list(reports.glob("TEST-*.xml"))
    if len(originals) != 1:
        raise ValueError("external original-source JVM report count differs")
    raw = originals[0].read_bytes()
    raw_case_ids(raw, case_ids)
    xml_path = output / "raw" / originals[0].name
    shutil.copy2(originals[0], xml_path)
    graph_process = process([*common, "qualificationSuiteGraph"], repository,
                            output / "raw/graph.stdout", output / "raw/graph.stderr")
    if graph_process["exit_code"]:
        raise ValueError("external staged graph task failed")
    graph = graph_from_output((output / graph_process["stdout"]).read_text())
    if graph != staged_graph:
        raise ValueError("test process provider graph differs from replay graph")
    artifacts = graph_artifacts(graph, staging, expected_hashes)
    for module, item in artifacts.items():
        source_binary = Path(item["file"])
        if sha(source_binary.read_bytes()) != expected_hashes[module]:
            raise ValueError("resolved external artifact bytes differ")
        shutil.copy2(source_binary, output / "resolved" / source_binary.name)
    selected = independent_gates.consumer_contract(manifest, LANE)["cases"]
    receipt = {"schema": 1, "kind": "full-staged-consumer-partial",
               "status": "NOT_RUN", "complete_selected_suite": False,
               "candidate_sha": candidate, "lane": LANE,
               "manifest_sha256": independent_gates.digest(manifest),
               "selected_case_count": len(selected),
               "selected_case_ids": sorted(item["id"] for item in selected),
               "selected_case_ids_sha256": sha(encoded(sorted(item["id"] for item in selected))),
               "observed_case_ids": sorted(case_ids),
               "remaining_case_count": len(selected) - len(case_ids),
               "original_source": source, "original_source_sha256": source_hash,
               "consumer_build_sha256": sha(git_blob(
                   repository, candidate, "consumers/qualification/portable/build.gradle.kts")),
               "staging_repository": str(staging), "expected_artifact_hashes": expected_hashes,
               "toolchain": {"java_home": str(java_home), "java_sha256": sha(java.read_bytes()),
                             "java_version": java_version, "gradle": str(gradle),
                             "gradle_sha256": sha(gradle.read_bytes()),
                             "gradle_version": "Gradle 9.5.0",
                             "gradle_user_home": str(Path(os.environ["GRADLE_USER_HOME"]).resolve())},
               "consumer_xml": str(xml_path.relative_to(output)),
               "test_process": test, "graph_process": graph_process,
               "files": inventory(output)}
    receipt["seal_sha256"] = sha(encoded(receipt))
    (output / "receipt.json").write_bytes(encoded(receipt) + b"\n")
    verify(output, repository, expected_hashes)
    return receipt


def verify(root, repository, expected_hashes):
    root, repository = Path(root).resolve(), Path(repository).resolve()
    receipt = json.loads((root / "receipt.json").read_bytes())
    seal = receipt.pop("seal_sha256", None)
    if seal != sha(encoded(receipt)):
        raise ValueError("partial receipt seal differs")
    manifest = independent_gates.load_approved_manifest(repository)
    selected = independent_gates.consumer_contract(manifest, LANE)["cases"]
    expected, source, source_hash = class_contract(manifest, LANE, CLASS)
    candidate = receipt.get("candidate_sha")
    if (not isinstance(candidate, str) or not re.fullmatch(r"[0-9a-f]{40}", candidate)
            or sha(git_blob(repository, candidate, source)) != source_hash):
        raise ValueError("partial receipt candidate source differs")
    if (receipt.get("schema") != 1 or receipt.get("kind") != "full-staged-consumer-partial"
            or receipt.get("status") != "NOT_RUN"
            or receipt.get("complete_selected_suite") is not False
            or receipt.get("lane") != LANE
            or receipt.get("manifest_sha256") != independent_gates.digest(manifest)
            or receipt.get("selected_case_count") != len(selected)
            or receipt.get("selected_case_ids") != sorted(item["id"] for item in selected)
            or receipt.get("selected_case_ids_sha256")
            != sha(encoded(sorted(item["id"] for item in selected)))
            or receipt.get("observed_case_ids") != sorted(expected)
            or receipt.get("remaining_case_count") != len(selected) - len(expected)
            or receipt.get("original_source") != source
            or receipt.get("original_source_sha256") != source_hash
            or receipt.get("consumer_build_sha256") != sha(git_blob(
                repository, candidate, "consumers/qualification/portable/build.gradle.kts"))
            or receipt.get("expected_artifact_hashes") != expected_hashes):
        raise ValueError("partial receipt contract differs from approved suite")
    toolchain = receipt.get("toolchain")
    if (not isinstance(toolchain, dict) or not toolchain.get("java_version", "").startswith(
            'openjdk version "21') or toolchain.get("gradle_version") != "Gradle 9.5.0"
            or any(not SHA256.fullmatch(str(toolchain.get(key, "")))
                   for key in ("java_sha256", "gradle_sha256"))):
        raise ValueError("partial receipt toolchain identity differs")
    if receipt.get("files") != inventory(root):
        raise ValueError("partial archive file inventory differs")
    xml_name = "TEST-org.dyn4j.geometry.Vector2NormalizationParityTest.xml"
    exact_files = {"raw/test.stdout", "raw/test.stderr", "raw/graph.stdout",
                   "raw/graph.stderr", f"raw/{xml_name}"} | {
        f"resolved/{module}-jvm-{VERSION}.jar" for module in MODULES}
    if (set(receipt["files"]) != exact_files
            or receipt.get("consumer_xml") != f"raw/{xml_name}"):
        raise ValueError("partial archive file set differs")
    raw = (root / receipt["consumer_xml"]).read_bytes()
    raw_case_ids(raw, expected)
    test, graph_process = receipt["test_process"], receipt["graph_process"]
    for process_record, task in ((test, "jvmTest"),
                                 (graph_process, "qualificationSuiteGraph")):
        command = process_record["command"]
        if (process_record["exit_code"] != 0
                or process_record["cwd"] != str(repository)
                or not isinstance(command, list) or command[-1] != task
                or "--offline" not in command
                or f"-PqualificationLaneId={LANE}" not in command
                or f"-PqualificationSuiteCheckout={repository}" not in command
                or f"-PqualificationSuiteSource={source.split('src/commonTest/kotlin/', 1)[1]}"
                not in command
                or command[1:3] != ["-p", str(repository / "consumers/qualification/portable")]
                or not 0 < process_record["started_ns"] <= process_record["finished_ns"]):
            raise ValueError("partial consumer process binding differs")
    if (test["stdout"] != "raw/test.stdout" or test["stderr"] != "raw/test.stderr"
            or graph_process["stdout"] != "raw/graph.stdout"
            or graph_process["stderr"] != "raw/graph.stderr"
            or "--rerun-tasks" not in test["command"]):
        raise ValueError("partial consumer raw process files differ")
    if test["finished_ns"] > graph_process["started_ns"]:
        raise ValueError("partial consumer process chronology differs")
    test_output = (root / test["stdout"]).read_text()
    if (not all(any(line.strip() == f"> Task :{task}"
                    for line in test_output.splitlines())
                for task in ("compileTestKotlinJvm", "qualificationSuiteGraph", "jvmTest"))
            or "BUILD SUCCESSFUL" not in test_output):
        raise ValueError("raw external test task output differs")
    xml_mtime = (root / receipt["consumer_xml"]).stat().st_mtime_ns
    if not test["started_ns"] <= xml_mtime <= test["finished_ns"]:
        raise ValueError("raw external test report was not produced in the process window")
    graph = graph_from_output((root / graph_process["stdout"]).read_text())
    if graph != graph_from_output((root / test["stdout"]).read_text()):
        raise ValueError("test process provider graph differs from replay graph")
    if graph.get("gradle_user_home") != toolchain["gradle_user_home"]:
        raise ValueError("recorded Gradle user home differs from observed runtime")
    staging = Path(receipt["staging_repository"])
    if not staging.is_absolute():
        raise ValueError("recorded staging repository is not absolute")
    artifacts = graph_artifacts(graph, staging, expected_hashes)
    for module, item in artifacts.items():
        copied = root / "resolved" / item["name"]
        if sha(copied.read_bytes()) != expected_hashes[module] or copied.stat().st_size != item["size"]:
            raise ValueError("resolved staged binary bytes differ")
    return receipt


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("run", "verify"):
        command = sub.add_parser(name)
        command.add_argument("--repository", required=True)
        command.add_argument("--expected-core-sha256", required=True)
        command.add_argument("--expected-facade-sha256", required=True)
        if name == "run":
            command.add_argument("--candidate-sha", required=True)
            command.add_argument("--staging", required=True)
            command.add_argument("--output", required=True)
            command.add_argument("--gradle", required=True)
        else:
            command.add_argument("--archive", required=True)
    args = parser.parse_args()
    hashes = {"dyn4k-core": args.expected_core_sha256,
              "dyn4k": args.expected_facade_sha256}
    if any(not SHA256.fullmatch(value) for value in hashes.values()):
        parser.error("independent expected artifact hashes are required")
    if args.action == "run":
        result = run(args.repository, args.candidate_sha, args.staging,
                     args.output, args.gradle, hashes)
    else:
        result = verify(args.archive, args.repository, hashes)
    print(json.dumps({"status": result["status"], "candidate_sha": result["candidate_sha"],
                      "observed": len(result["observed_case_ids"]),
                      "selected": result["selected_case_count"]}, sort_keys=True))


if __name__ == "__main__":
    main()
