#!/usr/bin/env python3
import argparse
import json
import os
import platform
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import independent_gates
import compiler_modes
from full_staged_consumer import GROUP, LANE, MODULES, SHA256, VERSION, encoded, git_blob, sha


SOURCE_ROOTS = (
    "dyn4k-core/src/commonTest/kotlin", "dyn4k-core/src/jvmTest/kotlin",
    "dyn4k/src/commonTest/kotlin", "dyn4k/src/jvmTest/kotlin", "dyn4k/src/jvmTest/java",
)
CONSUMER = "consumers/qualification/portable/full-jvm"
LANES = tuple(f"jvm:Java:{version}:{configuration}"
              for version in ("minimum", "current")
              for configuration in ("no-optimize", "default"))


def lane_parts(lane):
    if lane not in LANES:
        raise ValueError(f"unsupported full JVM lane: {lane}")
    return lane.split(":")[2:]


def selected_contract(repository, lane=LANE):
    lane_parts(lane)
    manifest = independent_gates.load_approved_manifest(repository)
    contract = independent_gates.consumer_contract(manifest, lane)
    cases = contract["cases"]
    if (len(cases) != 2526 or len({item["id"] for item in cases}) != 2526
            or sum(item["module"] == "dyn4k-core" for item in cases) != 2465
            or sum(item["module"] == "dyn4k" for item in cases) != 61):
        raise ValueError("approved JVM selected case contract differs")
    return manifest, contract


def source_inventory(repository, candidate, cases):
    tracked = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "ls-tree", "-r",
         "--name-only", candidate, "--", *SOURCE_ROOTS], text=True).splitlines()
    tracked = sorted(path for path in tracked if path.endswith((".kt", ".java")))
    live = sorted(path.relative_to(repository).as_posix() for root in SOURCE_ROOTS
                  for path in (repository / root).rglob("*")
                  if path.is_file() and path.suffix in (".kt", ".java"))
    if tracked != live or len(tracked) != len(set(tracked)):
        raise ValueError("test input tree differs from exact candidate")
    sources = {}
    for relative in tracked:
        blob = git_blob(repository, candidate, relative)
        if (repository / relative).read_bytes() != blob:
            raise ValueError(f"test source checkout differs: {relative}")
        sources[relative] = sha(blob)
    for item in cases:
        source = item["source"]
        if sources.get(source["path"]) != source["sha256"]:
            raise ValueError(f"selected method source differs: {item['id']}")
    return sources


def input_bytes(cases, sources, lane=LANE):
    lane_parts(lane)
    by_module = {module: sorted((item for item in cases if item["module"] == module),
                                key=lambda item: item["id"]) for module in MODULES}
    return {
        "source-inventory.tsv": "".join(f"{path}\t{digest}\n"
                                        for path, digest in sorted(sources.items())).encode(),
        "core-cases.tsv": "".join(
            f"{item['id']}\t{item['classname']}\t{item['method']}\n"
            for item in by_module["dyn4k-core"]).encode(),
        "facade-cases.tsv": "".join(
            f"{item['id']}\t{item['classname']}\t{item['method']}\n"
            for item in by_module["dyn4k"]).encode(),
        lane: ("gradle.settingsEvaluated { settings ->\n"
               "  if (settings.rootProject.name != 'dyn4k-full-staged-jvm-consumer') {\n"
               "    throw new GradleException('qualification project differs')\n"
               "  }\n"
               "}\n").encode(),
    }


def prepare(repository, candidate, destination, lane=LANE):
    repository, destination = Path(repository).resolve(), Path(destination).resolve()
    manifest, contract = selected_contract(repository, lane)
    sources = source_inventory(repository, candidate, contract["cases"])
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("JVM input directory must be empty")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in input_bytes(contract["cases"], sources, lane).items():
        (destination / name).write_bytes(data)
    return {"manifest_sha256": independent_gates.digest(manifest),
            "contract_sha256": independent_gates.digest(contract),
            "source_count": len(sources), "selected_cases": len(contract["cases"])}


def target_binary(staging, module):
    name = f"{module}-jvm-{VERSION}.jar"
    return staging / GROUP.replace(".", "/") / f"{module}-jvm" / VERSION / name


def mode_publication(publication, repository, candidate, configuration, hashes, digest):
    if Path(publication).is_symlink():
        raise ValueError("independent JVM mode publication is symbolic")
    publication = Path(publication).resolve()
    repository = Path(repository).resolve()
    if (not publication.is_dir() or publication.is_symlink()
            or not SHA256.fullmatch(str(digest))
            or independent_gates.archive_digest(publication) != digest):
        raise ValueError("independent JVM mode publication digest differs")
    if repository != compiler_modes.ROOT:
        raise ValueError("JVM mode publication verifier requires its producing checkout")
    result = compiler_modes.replay(publication, candidate, "jvm", configuration)
    if result["status"] != "PASSED":
        raise ValueError(f"JVM mode publication is unpassed: {result['problems']}")
    receipt = json.loads((publication / "receipt.json").read_bytes())
    staging = publication / "staged"
    if (receipt.get("mode") != configuration or receipt.get("candidate_sha") != candidate
            or receipt.get("flags") != compiler_modes.jvm_flags(configuration)
            or set(receipt.get("artifacts", {})) != set(MODULES)
            or any(receipt["artifacts"][module] != {
                "path": target_binary(staging, module).relative_to(publication).as_posix(),
                "sha256": hashes[module]} for module in MODULES)
            or any(sha(target_binary(staging, module).read_bytes()) != hashes[module]
                   for module in MODULES)):
        raise ValueError("JVM mode publication differs from independently selected JARs")
    return staging


def test_worker_proof(output, checkout, runtime_executable):
    launches = re.findall(r"^Starting process 'Gradle Test Executor [^\n]*$", output, re.M)
    project = Path(checkout) / CONSUMER
    if len(launches) != 2:
        raise ValueError("both Gradle Test Executor launches are required")
    for module in ("core", "facade"):
        task = f"> Task :{module}:test\n"
        pattern = (r"Starting process 'Gradle Test Executor (\d+)'\. Working directory: "
                   + re.escape(str(project / module)) + r" Command: "
                   + re.escape(runtime_executable) + r" .+"
                   + re.escape("worker.org.gradle.process.internal.worker.GradleWorkerMain")
                   + r" 'Gradle Test Executor \1'")
        matches = [line for line in launches if re.fullmatch(pattern, line)]
        if (len(matches) != 1 or task not in output
                or output.index(task) > output.index(matches[0])):
            raise ValueError(f"{module} Gradle Test Executor launch or test task differs")
    if launches[0] == launches[1]:
        raise ValueError("Gradle Test Executor launches are duplicated")


def run(repository, candidate, staging, output, gradle, expected_hashes,
        lane=LANE, runtime_java_home=None, publication=None,
        expected_publication_digest=None):
    version, configuration = lane_parts(lane)
    if runtime_java_home is None:
        raise ValueError("independent JVM test runtime home is required")
    repository, staging, output, gradle = (Path(value).resolve()
                                           for value in (repository, staging, output, gradle))
    runtime_java_home = Path(runtime_java_home).resolve()
    head = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"],
                                   text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(repository), "status", "--porcelain"],
                                    text=True)
    if head != candidate or dirty:
        raise ValueError("full JVM producer requires exact clean candidate checkout")
    if publication is None:
        raise ValueError("independent JVM mode publication is required")
    mode_staging = mode_publication(publication, repository, candidate, configuration,
                                    expected_hashes, expected_publication_digest)
    if staging != mode_staging:
        raise ValueError("staging differs from verified JVM mode publication")
    if output.exists() and any(output.iterdir()):
        raise ValueError("full JVM raw output must be empty")
    java_home = Path(os.environ["JAVA_HOME"]).resolve()
    gradle_home = Path(os.environ["GRADLE_USER_HOME"]).resolve()
    java_version = subprocess.check_output([str(java_home / "bin/java"), "-version"],
                                           stderr=subprocess.STDOUT, text=True).splitlines()[0]
    runtime_java_version = subprocess.check_output(
        [str(runtime_java_home / "bin/java"), "-version"],
        stderr=subprocess.STDOUT, text=True).splitlines()[0]
    expected_runtime_major = "1.8" if version == "minimum" else "21"
    if f'version "{expected_runtime_major}' not in runtime_java_version:
        raise ValueError(f"full JVM {version} lane requires Java {expected_runtime_major}")
    gradle_version = subprocess.check_output([str(gradle), "--version"], text=True)
    if 'version "21' not in java_version or "Gradle 9.5.0" not in gradle_version:
        raise ValueError("full JVM producer requires JDK 21 and Gradle 9.5.0")
    for module in MODULES:
        if sha(target_binary(staging, module).read_bytes()) != expected_hashes[module]:
            raise ValueError(f"staged {module} target JAR differs from independent hash")
    inputs = output.parent / f"{output.name}-inputs"
    prepared = prepare(repository, candidate, inputs, lane)
    output.mkdir(parents=True, exist_ok=True)
    command = [str(gradle), "-p", str(repository / CONSUMER), "--offline", "--no-daemon",
               "--console=plain", "--info", "--rerun-tasks", "--init-script", str(inputs / lane),
               f"-PqualificationCheckout={repository}",
               f"-PqualificationRepository={staging}",
               f"-PqualificationArchiveRoot={output}",
               f"-PqualificationSourceInventory={inputs / 'source-inventory.tsv'}",
               f"-PqualificationCoreCases={inputs / 'core-cases.tsv'}",
               f"-PqualificationFacadeCases={inputs / 'facade-cases.tsv'}",
               f"-PqualificationCoreSha256={expected_hashes['dyn4k-core']}",
               f"-PqualificationFacadeSha256={expected_hashes['dyn4k']}",
               f"-PqualificationLaneId={lane}",
               f"-PqualificationLaneScript={inputs / lane}",
               f"-PqualificationRuntimeJavaHome={runtime_java_home}",
               f"-PqualificationRuntimeJavaSha256={sha((runtime_java_home / 'bin/java').read_bytes())}",
               f"-PqualificationBuildConfiguration={configuration}",
               f"-Dorg.gradle.java.installations.paths={runtime_java_home},{java_home}", lane]
    started = time.time_ns()
    with (output / "stdout.txt").open("wb") as stdout, (output / "stderr.txt").open("wb") as stderr:
        for log in ("stdout.txt", "stderr.txt"):
            os.utime(output / log, ns=(started, started))
        result = subprocess.run(command, cwd=inputs, stdout=stdout, stderr=stderr,
                                check=False)
    finished = time.time_ns()
    if result.returncode:
        raise ValueError(f"full JVM external Gradle process exited {result.returncode}")
    receipt = {"schema": 1, "status": "PASSED", "candidate_sha": candidate,
               "source_tree": subprocess.check_output(
                   ["git", "-C", str(repository), "rev-parse", f"{candidate}^{{tree}}"],
                   text=True).strip(),
               "lane": lane, "target": "jvm", "runtime": "Java", "version": version,
               "configuration": configuration,
               "runtime_identity": f"{runtime_java_version} | {platform.system()} {platform.release()} {platform.machine()}",
               "producer_paths": {"checkout": str(repository), "staging": str(staging),
                                  "archive_root": str(output), "inputs": str(inputs),
                                  "gradle": str(gradle)},
               "toolchain": {"java_home": str(java_home),
                             "java_version": java_version,
                             "java_executable_sha256": sha((java_home / "bin/java").read_bytes()),
                             "runtime_java_home": str(runtime_java_home),
                             "runtime_java_version": runtime_java_version,
                             "runtime_java_executable_sha256": sha((runtime_java_home / "bin/java").read_bytes()),
                             "gradle_version": "Gradle 9.5.0",
                             "gradle_executable_sha256": sha(gradle.read_bytes()),
                             "gradle_user_home": str(gradle_home)},
               "artifact_hashes": expected_hashes,
               "mode_publication": {"path": str(Path(publication).resolve()),
                                    "archive_digest": expected_publication_digest},
               "process": {"command": command, "cwd": str(inputs), "exit_code": 0,
                           "started_ns": started, "finished_ns": finished,
                           "stdout": "stdout.txt", "stderr": "stderr.txt"},
               "consumer_group": "full-suite", "consumer_contract_sha256": prepared["contract_sha256"],
               "source_inventory_sha256": sha((inputs / "source-inventory.tsv").read_bytes()),
               "consumer_build_sha256": {
                   path: sha(git_blob(repository, candidate, path)) for path in (
                       f"{CONSUMER}/build.gradle.kts", f"{CONSUMER}/core/build.gradle.kts",
                       f"{CONSUMER}/facade/build.gradle.kts", f"{CONSUMER}/settings.gradle.kts",
                       f"{CONSUMER}/jvm/Java/current/build.gradle.kts",
                       f"{CONSUMER}/jvm/Java/minimum/build.gradle.kts")},
               "provider_graph": "provider-graph.json",
               "resolved_artifacts": {
                   module: f"resolved/{module}-jvm-{VERSION}.jar" for module in MODULES},
               "consumer_xml": sorted(str(path.relative_to(output)) for path in
                                      (output / "reports/normalized").rglob("TEST-*.xml")),
               "raw_consumer_xml": sorted(str(path.relative_to(output)) for path in
                                          (output / "reports/raw").rglob("TEST-*.xml")),
               "files": [{"path": str(path.relative_to(output)), "sha256": sha(path.read_bytes()),
                          "mtime_ns": path.stat().st_mtime_ns}
                         for path in sorted(output.rglob("*")) if path.is_file()]}
    (output / "receipt.json").write_bytes(encoded(receipt) + b"\n")
    return receipt


def _same_report(raw, normalized, case_map):
    left, right = ET.fromstring(raw), ET.fromstring(normalized)
    if left.tag != "testsuite" or right.tag != "testsuite":
        raise ValueError("external Gradle XML root differs")
    observed = []

    def compare(a, b):
        if a.tag != b.tag or (a.text or "").strip() != (b.text or "").strip():
            raise ValueError("normalized XML differs from original Gradle XML")
        attributes = dict(b.attrib)
        if a.tag == "testcase":
            key = (a.get("classname"), a.get("name"))
            identity = case_map.get(key)
            if identity is None or attributes.pop("id", None) != identity:
                raise ValueError("raw Gradle method differs from selected source identity")
            observed.append(identity)
        if a.attrib != attributes or len(a) != len(b):
            raise ValueError("normalized XML changes raw Gradle result")
        for child_a, child_b in zip(a, b):
            compare(child_a, child_b)

    compare(left, right)
    return observed


def verify(root, repository, candidate, expected_hashes, runtime_identity,
           expected_archive_digest, expected_java_executable_sha256=None,
           expected_gradle_executable_sha256=None,
           expected_runtime_java_executable_sha256=None, lane=LANE,
           publication=None, expected_publication_digest=None):
    version, configuration = lane_parts(lane)
    expected_executables = {
        "java_executable_sha256": expected_java_executable_sha256,
        "gradle_executable_sha256": expected_gradle_executable_sha256,
        "runtime_java_executable_sha256": expected_runtime_java_executable_sha256,
    }
    if any(type(value) is not str or not SHA256.fullmatch(value)
           for value in expected_executables.values()):
        raise ValueError("independent Java and Gradle executable SHA-256 values are required")
    root, repository = Path(root), Path(repository).resolve()
    if not root.is_dir() or root.is_symlink():
        raise ValueError("full JVM archive is missing or symbolic")
    receipt = json.loads((root / "receipt.json").read_bytes())
    if publication is None:
        raise ValueError("independent JVM mode publication is required")
    manifest, contract = selected_contract(repository, lane)
    if (receipt.get("candidate_sha") != candidate or receipt.get("lane") != lane
            or receipt.get("version") != version
            or receipt.get("configuration") != configuration
            or receipt.get("consumer_group") != "full-suite"
            or receipt.get("consumer_contract_sha256") != independent_gates.digest(contract)):
        raise ValueError("full JVM receipt differs from approved candidate contract")
    staging = mode_publication(publication, repository, candidate, configuration,
                               expected_hashes, expected_publication_digest)
    if (receipt.get("mode_publication") != {
            "path": str(Path(publication).resolve()),
            "archive_digest": expected_publication_digest}
            or receipt.get("producer_paths", {}).get("staging") != str(staging)):
        raise ValueError("full JVM archive differs from verified mode publication")
    cases = contract["cases"]
    sources = source_inventory(repository, candidate, cases)
    expected_inputs = input_bytes(cases, sources, lane)
    expected_files = {f"inputs/{name}": data for name, data in expected_inputs.items()}
    expected_files["inputs/lane-script"] = expected_files.pop(f"inputs/{lane}")
    if receipt.get("source_inventory_sha256") != sha(expected_inputs["source-inventory.tsv"]):
        raise ValueError("receipt source inventory differs from exact candidate")
    for relative, data in expected_files.items():
        if (root / relative).read_bytes() != data:
            raise ValueError(f"archived full JVM input differs: {relative}")
    builds = (f"{CONSUMER}/build.gradle.kts", f"{CONSUMER}/core/build.gradle.kts",
              f"{CONSUMER}/facade/build.gradle.kts", f"{CONSUMER}/settings.gradle.kts",
              f"{CONSUMER}/jvm/Java/current/build.gradle.kts",
              f"{CONSUMER}/jvm/Java/minimum/build.gradle.kts")
    if receipt.get("consumer_build_sha256") != {
            path: sha(git_blob(repository, candidate, path)) for path in builds}:
        raise ValueError("consumer build source differs from exact candidate")
    process = receipt.get("process", {})
    command = process.get("command", [])
    paths = receipt.get("producer_paths")
    toolchain = receipt.get("toolchain")
    required_runtime_major = "1.8" if version == "minimum" else "21"
    if (not isinstance(paths, dict)
            or set(paths) != {"checkout", "staging", "archive_root", "inputs", "gradle"}
            or any(not isinstance(value, str) or not Path(value).is_absolute()
                   for value in paths.values())
            or not isinstance(toolchain, dict)
            or set(toolchain) != {"java_home", "java_version", "java_executable_sha256",
                                  "runtime_java_home", "runtime_java_version",
                                  "runtime_java_executable_sha256",
                                  "gradle_version", "gradle_executable_sha256",
                                  "gradle_user_home"}
            or toolchain["gradle_version"] != "Gradle 9.5.0"
            or 'version "21' not in toolchain["java_version"]
            or f'version "{required_runtime_major}' not in toolchain["runtime_java_version"]
            or receipt.get("runtime_identity") != runtime_identity
            or not runtime_identity.startswith(toolchain["runtime_java_version"] + " | ")
            or any(not SHA256.fullmatch(str(toolchain[key]))
                   for key in expected_executables)
            or any(not Path(toolchain[key]).is_absolute()
                   for key in ("java_home", "runtime_java_home", "gradle_user_home"))):
        raise ValueError("producer paths or pinned toolchain are incomplete")
    if any(toolchain[key] != value for key, value in expected_executables.items()):
        raise ValueError("independent executable SHA-256 differs from receipt")
    inputs = Path(paths["inputs"])
    expected_command = [paths["gradle"], "-p", f"{paths['checkout']}/{CONSUMER}",
                        "--offline", "--no-daemon", "--console=plain", "--info", "--rerun-tasks",
                        "--init-script", str(inputs / lane),
                        f"-PqualificationCheckout={paths['checkout']}",
                        f"-PqualificationRepository={paths['staging']}",
                        f"-PqualificationArchiveRoot={paths['archive_root']}",
                        f"-PqualificationSourceInventory={inputs / 'source-inventory.tsv'}",
                        f"-PqualificationCoreCases={inputs / 'core-cases.tsv'}",
                        f"-PqualificationFacadeCases={inputs / 'facade-cases.tsv'}",
                        f"-PqualificationCoreSha256={expected_hashes['dyn4k-core']}",
                        f"-PqualificationFacadeSha256={expected_hashes['dyn4k']}",
                        f"-PqualificationLaneId={lane}",
                        f"-PqualificationLaneScript={inputs / lane}",
                        f"-PqualificationRuntimeJavaHome={toolchain['runtime_java_home']}",
                        f"-PqualificationRuntimeJavaSha256={expected_runtime_java_executable_sha256}",
                        f"-PqualificationBuildConfiguration={configuration}",
                        f"-Dorg.gradle.java.installations.paths={toolchain['runtime_java_home']},{toolchain['java_home']}",
                        lane]
    if command != expected_command or process.get("cwd") != paths["inputs"]:
        raise ValueError("external Gradle command differs from candidate or staged bytes")
    output = (root / process["stdout"]).read_text()
    runtime_executable = str(Path(toolchain["runtime_java_home"]) / "bin/java")
    if f"QUALIFICATION_BUILD_CONFIGURATION={configuration}" not in output.splitlines():
        raise ValueError("external test JVM process or build configuration is unproven")
    test_worker_proof(output, paths["checkout"], runtime_executable)
    proof_bytes = (root / "build-configuration.json").read_bytes()
    if f"QUALIFICATION_BUILD_CONFIGURATION_SHA256={sha(proof_bytes)}" not in output.splitlines():
        raise ValueError("external build configuration proof is not bound to process")
    proof = json.loads(proof_bytes)
    if (set(proof) != {"lane", "configuration", "modules"}
            or proof["lane"] != lane or proof["configuration"] != configuration
            or not isinstance(proof["modules"], list) or len(proof["modules"]) != 2
            or {item.get("module") for item in proof["modules"]} != {"core", "facade"}):
        raise ValueError("external build configuration proof differs from selected lane")
    for item in proof["modules"]:
        args, jvm_args = item.get("compiler_args"), item.get("test_jvm_args")
        if (not isinstance(args, list) or not isinstance(jvm_args, list)
                or item.get("test_java_home") != toolchain["runtime_java_home"]
                or item.get("test_java_executable") != runtime_executable
                or item.get("test_java_sha256") != expected_runtime_java_executable_sha256
                or item.get("test_java_version") != (8 if version == "minimum" else 21)
                or item.get("kotlin_jvm_target") != ("1.8" if version == "minimum" else "21")
                or item.get("java_release") != (8 if version == "minimum" else 21)
                or ("-Xno-optimize" in args) != (configuration == "no-optimize")
                or "-Xint" in jvm_args
                or "-XshowSettings:properties" not in jvm_args):
            raise ValueError("external compile or test JVM configuration differs")
    if (receipt.get("raw_consumer_xml") is None or not isinstance(
            receipt["raw_consumer_xml"], list)):
        raise ValueError("original Gradle XML inventory is missing")
    raw_paths = receipt["raw_consumer_xml"]
    normal_paths = receipt.get("consumer_xml")
    if (not isinstance(normal_paths, list) or len(raw_paths) != len(normal_paths)
            or len(raw_paths) != len(set(raw_paths)) or not raw_paths):
        raise ValueError("Gradle XML inventories differ")
    case_maps = {module: {(item["classname"], item["method"]): item["id"]
                          for item in cases if item["module"] == module}
                 for module in MODULES}
    observed = []
    for raw_path in raw_paths:
        parts = Path(raw_path).parts
        if (len(parts) != 4 or parts[:2] != ("reports", "raw")
                or parts[2] not in ("core", "facade")
                or not parts[3].startswith("TEST-") or not parts[3].endswith(".xml")):
            raise ValueError("original Gradle XML path differs")
        normal_path = str(Path("reports/normalized") / parts[2] / parts[3])
        if normal_path not in normal_paths:
            raise ValueError("normalized XML has no original Gradle report")
        module = "dyn4k-core" if parts[2] == "core" else "dyn4k"
        observed.extend(_same_report((root / raw_path).read_bytes(),
                                     (root / normal_path).read_bytes(), case_maps[module]))
    if len(observed) != len(cases) or set(observed) != {item["id"] for item in cases}:
        raise ValueError("original Gradle XML omits or duplicates selected methods")
    graph = json.loads((root / "provider-graph.json").read_bytes())
    staging = Path(paths["staging"])
    if (not staging.is_absolute() or set(graph) != {"compile", "runtime", "gradle_user_home"}
            or graph["gradle_user_home"] != toolchain["gradle_user_home"]):
        raise ValueError("external provider graph lacks runtime or staged root")
    for phase in ("compile", "runtime"):
        entries = graph[phase]
        if len(entries) != 2 or {entry.get("project") for entry in entries} != {"core", "facade"}:
            raise ValueError("core and facade provider graphs are incomplete")
        for entry in entries:
            if entry.get("configuration") != f"test{phase.capitalize()}Classpath":
                raise ValueError("external provider configuration differs")
            selected = [a for a in entry["artifacts"]
                        if a.get("component", "").startswith(f"{GROUP}:")]
            if len(selected) != 2:
                raise ValueError("external provider graph has missing or extra dyn4k binaries")
            for module in MODULES:
                component = f"{GROUP}:{module}-jvm:{VERSION}"
                matches = [a for a in selected if a["component"] == component]
                copied = root / f"resolved/{module}-jvm-{VERSION}.jar"
                staged = target_binary(staging, module)
                if (len(matches) != 1 or matches[0]["file"] != str(staged)
                        or matches[0]["sha256"] != expected_hashes[module]
                        or matches[0]["size"] != copied.stat().st_size
                        or sha(copied.read_bytes()) != expected_hashes[module]):
                    raise ValueError("external provider graph differs from pinned staged binary")
    allowed = set(expected_files) | {"receipt.json", "stdout.txt", "stderr.txt",
                                    "provider-graph.json", "build-configuration.json"} | set(raw_paths) | set(normal_paths) | {
        f"resolved/{module}-jvm-{VERSION}.jar" for module in MODULES}
    if {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()} != allowed:
        raise ValueError("full JVM archive has missing or unlisted files")
    gate = independent_gates.evaluate_gate(
        "staged-consumer", root, candidate, lane, manifest["lanes"][lane], repository,
        expected_hashes, runtime_identity, expected_archive_digest, manifest=manifest)
    if gate["status"] != "PASSED" or gate.get("complete_selected_suite") is not True:
        raise ValueError(f"independent full JVM staged consumer gate failed: {gate['reason']}")
    return gate


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--repository", required=True)
    prep.add_argument("--candidate-sha", required=True)
    prep.add_argument("--destination", required=True)
    prep.add_argument("--lane", choices=LANES, default=LANE)
    produce = sub.add_parser("run")
    produce.add_argument("--repository", required=True)
    produce.add_argument("--candidate-sha", required=True)
    produce.add_argument("--staging", required=True)
    produce.add_argument("--mode-publication", required=True)
    produce.add_argument("--expected-mode-publication-digest", required=True)
    produce.add_argument("--output", required=True)
    produce.add_argument("--gradle", required=True)
    produce.add_argument("--lane", choices=LANES, required=True)
    produce.add_argument("--runtime-java-home", required=True)
    produce.add_argument("--expected-core-sha256", required=True)
    produce.add_argument("--expected-facade-sha256", required=True)
    replay = sub.add_parser("verify")
    replay.add_argument("--repository", required=True)
    replay.add_argument("--candidate-sha", required=True)
    replay.add_argument("--archive", required=True)
    replay.add_argument("--mode-publication", required=True)
    replay.add_argument("--expected-mode-publication-digest", required=True)
    replay.add_argument("--lane", choices=LANES, required=True)
    replay.add_argument("--expected-core-sha256", required=True)
    replay.add_argument("--expected-facade-sha256", required=True)
    replay.add_argument("--runtime-identity", required=True)
    replay.add_argument("--expected-archive-digest", required=True)
    replay.add_argument("--expected-java-executable-sha256", required=True)
    replay.add_argument("--expected-gradle-executable-sha256", required=True)
    replay.add_argument("--expected-runtime-java-executable-sha256", required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        result = prepare(args.repository, args.candidate_sha, args.destination, args.lane)
    elif args.action == "run":
        hashes = {"dyn4k-core": args.expected_core_sha256,
                  "dyn4k": args.expected_facade_sha256}
        if any(not SHA256.fullmatch(value) for value in hashes.values()):
            parser.error("independent target JAR hashes are required")
        result = run(args.repository, args.candidate_sha, args.staging, args.output,
                     args.gradle, hashes, args.lane, args.runtime_java_home,
                     args.mode_publication, args.expected_mode_publication_digest)
    else:
        hashes = {"dyn4k-core": args.expected_core_sha256,
                  "dyn4k": args.expected_facade_sha256}
        result = verify(args.archive, args.repository, args.candidate_sha,
                        hashes, args.runtime_identity, args.expected_archive_digest,
                        args.expected_java_executable_sha256,
                        args.expected_gradle_executable_sha256,
                        args.expected_runtime_java_executable_sha256, args.lane,
                        args.mode_publication, args.expected_mode_publication_digest)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
