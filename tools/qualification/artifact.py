#!/usr/bin/env python3
import json
import math
import os
import platform
import shutil
import argparse
import sys
import tarfile
import tempfile
import csv
import io
import re
import subprocess
from collections import Counter
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath, PureWindowsPath

import qualify


FULL_CONFIGS = {"macosArm64": ("debug-g", "optimized-opt"),
                "iosSimulatorArm64": ("debug-g", "optimized-opt"),
                "tvosSimulatorArm64": ("debug-g", "optimized-opt"),
                "watchosSimulatorArm64": ("debug-g", "optimized-opt"),
                "iosX64": ("debug-g", "optimized-opt"),
                "mingwX64": ("debug-g", "optimized-opt"),
                "jsSafari": ("development", "production")}
FULL_SOURCE_TASK = {target: f"{target}Test" for target in FULL_CONFIGS if target != "jsSafari"}
FULL_SOURCE_TASK["jsSafari"] = "jsBrowserTest"


def _full_file(bundle, relative):
    path = bundle / portable_path(relative)
    if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(bundle.resolve()):
        raise ValueError(f"full hosted archive file is absent or unsafe: {relative}")
    return path


def _full_original_path(target, value):
    kind = PureWindowsPath if target == "mingwX64" else PurePosixPath
    path = kind(str(value))
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("full hosted original runner path is invalid")
    return path


def _full_process(bundle, folder, name, process, invocation, tasks):
    if not isinstance(process, dict) or process.get("invocation_id") != invocation:
        raise ValueError(f"full hosted {name} invocation differs")
    started, finished = process.get("started_ns"), process.get("finished_ns")
    if (type(started) is not int or type(finished) is not int
            or started <= 0 or finished < started or process.get("exit_code") != 0
            or type(process.get("pid")) is not int or process["pid"] <= 0):
        raise ValueError(f"full hosted {name} process failed or has invalid times")
    command = process.get("command")
    if (not isinstance(command, list) or not all(isinstance(arg, str) for arg in command)
            or not command or Path(command[0].replace("\\", "/")).name not in
            ("gradlew", "gradlew.bat")
            or (name != "graph" and "--rerun-tasks" not in command)
            or (invocation is not None and
                f"-PqualificationInvocationId={invocation}" not in command)
            or not all(task in command or task.removeprefix(":") in command for task in tasks)):
        raise ValueError(f"full hosted {name} process command differs")
    output = b""
    prefix = f"{folder}/{name}" if folder else name
    for stream in ("stdout", "stderr"):
        path = _full_file(bundle, f"{prefix}/{stream}.txt")
        if qualify.digest(path) != process.get(f"{stream}_sha256"):
            raise ValueError(f"full hosted {name} {stream} differs")
        if path.stat().st_mtime_ns < finished:
            raise ValueError(f"full hosted {name} {stream} is stale")
        if stream == "stdout":
            output = path.read_bytes()
    if b"BUILD SUCCESSFUL" not in output:
        raise ValueError(f"full hosted {name} successful Gradle output is absent")
    for task in tasks:
        if f"> Task {task}".encode() not in output:
            raise ValueError(f"full hosted {name} task did not execute: {task}")
    return started, finished


def _full_xml(bundle, folder, group, expected, target, window, safari_version=None,
              consumer=False, recorded_times=None):
    if not isinstance(group, dict) or group.get("expected") != len(expected):
        raise ValueError("full hosted XML expected count differs")
    reports = group.get("reports")
    if not isinstance(reports, list) or not reports:
        raise ValueError("full hosted XML reports are missing")
    seen = Counter()
    paths = []
    for item in reports:
        if not isinstance(item, dict):
            raise ValueError("full hosted XML report record is invalid")
        relative = portable_path(item.get("path"))
        if not relative.startswith(f"xml/{'consumer' if consumer else group['module']}/"):
            raise ValueError("full hosted XML report path differs")
        path = _full_file(bundle, f"{folder}/{relative}")
        paths.append(path.relative_to(bundle).as_posix())
        modified = item.get("modified_ns")
        if (type(modified) is not int or not window[0] <= modified <= window[1]
                or qualify.digest(path) != item.get("sha256")
                or recorded_times.get(path.relative_to(bundle).as_posix()) != modified):
            raise ValueError("full hosted XML is stale or differs from archived bytes")
        suite = ET.fromstring(path.read_bytes())
        if suite.tag != "testsuite" or not math.isfinite(float(suite.get("time", "nan"))):
            raise ValueError("full hosted XML suite is invalid")
        cases = list(suite.iter("testcase"))
        counts = {"tests": len(cases),
                  "failures": sum(c.find("failure") is not None for c in cases),
                  "errors": sum(c.find("error") is not None for c in cases),
                  "skipped": sum(c.find("skipped") is not None for c in cases)}
        if (any(suite.get(key) is None or int(suite.get(key)) != value
                for key, value in counts.items())
                or any(counts[key] for key in ("failures", "errors", "skipped"))):
            raise ValueError("full hosted XML has failed, skipped, or partial cases")
        for case in cases:
            classname, method = case.get("classname"), case.get("name")
            if (not classname or not method or not math.isfinite(float(case.get("time", "nan")))
                    or case.find("ignored") is not None):
                raise ValueError("full hosted XML case is ignored or invalid")
            if consumer:
                identity = (classname, method)
            elif target == "jsSafari":
                match = re.fullmatch(r"(.+)\[js, browser, Safari[^]]+\]", method)
                if (not classname.startswith("jsBrowserTest.") or match is None
                        or f"Safari{safari_version}," not in method):
                    raise ValueError("full hosted Safari reporter identity differs")
                identity = (classname.removeprefix("jsBrowserTest."), match.group(1))
            else:
                prefix, suffix = f"{target}Test.", f"[{target}]"
                if not classname.startswith(prefix) or not method.endswith(suffix):
                    raise ValueError("full hosted native reporter identity differs")
                identity = (classname.removeprefix(prefix), method.removesuffix(suffix))
            seen[identity] += 1
        if item.get("cases", len(cases)) != len(cases):
            raise ValueError("full hosted XML report case count differs")
    if len(paths) != len(set(paths)) or seen != Counter(expected):
        raise ValueError("full hosted XML cases are missing, extra, or duplicate")
    case_ids = [f"{name}#{method}" for name, method in sorted(seen)]
    if (group.get("executed") != len(expected) or group.get("case_ids") != case_ids):
        raise ValueError("full hosted XML case IDs or totals differ")
    return set(paths)


def _full_staging(bundle, receipt, target, recorded):
    names = set(qualify.MODULES)
    names.update(qualify.target_publication_name(module, target)
                 for module in qualify.MODULES)
    gav = {f"{qualify.GROUP}:{name}:{qualify.VERSION}" for name in names}
    if set(receipt.get("staged_gav", [])) != gav:
        raise ValueError("full hosted staged GAV inventory differs")
    staged_paths = set()
    ns = "{http://maven.apache.org/POM/4.0.0}"
    for name in names:
        root = f"staged/{qualify.GROUP.replace('.', '/')}/{name}/{qualify.VERSION}"
        pom_name = f"{root}/{name}-{qualify.VERSION}.pom"
        module_name = f"{root}/{name}-{qualify.VERSION}.module"
        staged_paths.update((pom_name, module_name))
        pom = ET.parse(_full_file(bundle, pom_name)).getroot()
        for key, value in (("groupId", qualify.GROUP), ("artifactId", name),
                           ("version", qualify.VERSION)):
            if pom.findtext(ns + key) != value:
                raise ValueError("full hosted staged POM identity differs")
        if name == "dyn4k" or name.startswith("dyn4k-") and not name.startswith("dyn4k-core"):
            core = name.replace("dyn4k", "dyn4k-core", 1)
            dependencies = {(d.findtext(ns + "groupId"), d.findtext(ns + "artifactId"),
                             d.findtext(ns + "version"))
                            for d in pom.findall(ns + "dependencies/" + ns + "dependency")}
            if (qualify.GROUP, core, qualify.VERSION) not in dependencies:
                raise ValueError("full hosted staged POM lacks core dependency")
        metadata = qualify.load_json_strict(_full_file(bundle, module_name))
        component = metadata.get("component", {})
        root_name = name if name in qualify.MODULES else (
            "dyn4k-core" if name.startswith("dyn4k-core-") else "dyn4k")
        if (component.get("group") != qualify.GROUP or component.get("module") != root_name
                or component.get("version") != qualify.VERSION):
            raise ValueError("full hosted staged Gradle metadata identity differs")
        if name not in qualify.MODULES and component.get("url") != (
                f"../../{root_name}/{qualify.VERSION}/{root_name}-{qualify.VERSION}.module"):
            raise ValueError("full hosted staged target metadata root link differs")
        if name in qualify.MODULES:
            target_name = qualify.target_publication_name(name, target)
            variants = metadata.get("variants", [])
            expected_link = {"group": qualify.GROUP, "module": target_name,
                             "version": qualify.VERSION,
                             "url": (f"../../{target_name}/{qualify.VERSION}/"
                                     f"{target_name}-{qualify.VERSION}.module")}
            links = [variant.get("available-at", {}) for variant in variants
                     if variant.get("available-at", {}).get("module") == target_name]
            if not links or any(link != expected_link for link in links):
                raise ValueError("full hosted staged root metadata lacks exact target link")
    for module in qualify.MODULES:
        relative = f"staged/{qualify.target_binary_path(module, target)}"
        staged_paths.update((relative, relative + ".sha256"))
    if {name for name in recorded if name.startswith("staged/")} != staged_paths:
        raise ValueError("full hosted staged archive inventory differs")


def _full_graph(bundle, folder, target, declared, hashes, staging):
    text = _full_file(bundle, f"{folder}/graph/stdout.txt").read_text()
    lines = [line.removeprefix("DYN4K_RESOLVED_GRAPH=") for line in text.splitlines()
             if line.startswith("DYN4K_RESOLVED_GRAPH=")]
    if len(lines) != 1:
        raise ValueError("full hosted external consumer graph is absent or duplicate")
    graph = json.loads(lines[0])
    config = "jsCompileClasspath" if target == "jsSafari" else f"{target}CompileKlibraries"
    if graph != declared or graph.get("configuration") != config:
        raise ValueError("full hosted external consumer graph differs")
    artifact_target = "js" if target == "jsSafari" else target
    components = graph.get("components")
    artifacts = graph.get("artifacts")
    if not isinstance(components, list) or not isinstance(artifacts, list):
        raise ValueError("full hosted external consumer graph is incomplete")
    for module in qualify.MODULES:
        name = qualify.target_publication_name(module, artifact_target)
        gav = f"{qualify.GROUP}:{name}:{qualify.VERSION}"
        expected_file = _full_original_path(target, staging) / qualify.target_binary_path(
            module, artifact_target)
        matches = [item for item in artifacts if isinstance(item, dict)
                   and item.get("component") == gav]
        if (gav not in components or len(matches) != 1
                or _full_original_path(target, matches[0].get("file", "")) != expected_file
                or matches[0].get("sha256") != hashes[module]
                or type(matches[0].get("size")) is not int or matches[0]["size"] <= 0):
            raise ValueError("full hosted external consumer resolved binary differs")


def _verify_full_hosted_directory(bundle, candidate_sha, repository):
    import full_corpus
    import hosted

    bundle, repository = Path(bundle), Path(repository)
    receipt = qualify.load_json_strict(_full_file(bundle, "receipt.json"))
    if (not isinstance(receipt, dict) or receipt.get("schema") != 2
            or receipt.get("kind") != "hosted-full-common-corpus"
            or receipt.get("status") != "FULL_COMMON_PASSED"):
        raise ValueError("full hosted receipt identity or status differs")
    if receipt.get("candidate_sha") != candidate_sha:
        raise ValueError("full hosted candidate SHA differs")
    target = receipt.get("target")
    if target not in FULL_CONFIGS:
        raise ValueError("full hosted target is invalid")
    configurations = receipt.get("configurations")
    if (not isinstance(configurations, list) or len(configurations) != 2
            or [row.get("configuration") for row in configurations if isinstance(row, dict)]
            != list(FULL_CONFIGS[target])):
        raise ValueError("full hosted configuration set differs")
    if hosted.runtime_status(target, receipt.get("runtime"))[0] != "READY":
        raise ValueError("full hosted runtime or runner identity differs")
    runtime = receipt["runtime"]
    java_version = runtime.get("java_version")
    if (not isinstance(java_version, str)
            or re.fullmatch(r"21\.[0-9]+(?:\.[0-9]+)*(?:[-+][0-9A-Za-z.-]+)?",
                            java_version) is None
            or runtime.get("gradle_version") != "9.5.0"
            or runtime.get("kgp_declared_version") != "2.4.20"):
        raise ValueError("full hosted Java, Gradle, or Kotlin plugin toolchain differs")
    simulator_family = hosted.NATIVE_TARGETS.get(target, (None, None, None))[2]
    if simulator_family:
        selected = receipt.get("selected_simulator")
        if (not isinstance(selected, dict)
                or selected not in receipt["runtime"].get("simulators", {}).get(simulator_family, [])
                or not selected.get("udid")
                or any(row.get("simulator_udid") != selected["udid"] for row in configurations)):
            raise ValueError("full hosted executed simulator identity differs")
    for key in ("github_run_id", "github_job", "runner_name", "runner_os", "runner_arch"):
        if not str(receipt.get(key) or "").strip():
            raise ValueError(f"full hosted {key} is missing")
    system = receipt["runtime"]["system"]
    machine = receipt["runtime"]["machine"].lower()
    expected_runner = ("Windows" if system == "Windows" else "macOS",
                       "ARM64" if machine == "arm64" else "X64")
    if (receipt["runner_os"], receipt["runner_arch"]) != expected_runner:
        raise ValueError("full hosted GitHub runner OS or architecture differs")
    if (not qualify.SHA40.fullmatch(str(candidate_sha)) or subprocess.run(
            ["git", "-C", str(repository), "cat-file", "-e", f"{candidate_sha}^{{commit}}"],
            capture_output=True, check=False).returncode):
        raise ValueError("full hosted candidate commit does not exist")
    final_contract = subprocess.run(
        ["git", "-C", str(repository), "cat-file", "-e",
         f"{candidate_sha}:tools/qualification/full_hosted.py"],
        capture_output=True, check=False).returncode == 0
    if final_contract:
        for key in ("archive_root", "repository_root", "staging_repository"):
            if not receipt.get(key):
                raise ValueError(f"full hosted {key} is missing")
        original_root = _full_original_path(target, receipt["archive_root"])
        repository_root = _full_original_path(target, receipt["repository_root"])
        staging_root = _full_original_path(target, receipt["staging_repository"])
        if staging_root != repository_root / "build/staging-repository":
            raise ValueError("full hosted staging repository differs from runner checkout")
        wrapper = repository_root / ("gradlew.bat" if target == "mingwX64" else "gradlew")
        consumer_root = repository_root / "consumers/qualification/portable"
    manifest_path = repository / full_corpus.MANIFEST_PATH
    mapping_path = repository / full_corpus.MAP_PATH
    manifest = qualify.load_json_strict(manifest_path)
    mapping = list(csv.DictReader(io.StringIO(mapping_path.read_text()), delimiter="\t"))
    problems = full_corpus.candidate_input_problems(
        repository, candidate_sha, manifest, mapping, manifest_path, mapping_path,
        check_checkout=False)
    if problems or manifest.get("policy") != "production":
        raise ValueError("full hosted reviewed candidate input differs: " + "; ".join(problems))
    if full_corpus.make_manifest(full_corpus.scan_sources(repository), mapping,
                                 production=True, repository=repository) != manifest:
        raise ValueError("full hosted source inventory differs from committed candidate")
    if (receipt.get("manifest_sha256") != qualify.manifest_digest(manifest)
            or receipt.get("source_tree_sha256") != manifest.get("source_tree_sha256")
            or receipt.get("map_sha256") != qualify.digest(mapping_path)
            or receipt.get("reviewed_pairs_sha256") != qualify.digest(
                repository / full_corpus.PAIR_PATH)):
        raise ValueError("full hosted source, map, or manifest binding differs")
    inventory = receipt.get("files")
    if not isinstance(inventory, list) or not inventory:
        raise ValueError("full hosted archive inventory is missing")
    recorded = {}
    recorded_times = {}
    for item in inventory:
        if not isinstance(item, dict):
            raise ValueError("full hosted archive inventory entry is invalid")
        relative = portable_path(item.get("path"))
        if relative in recorded or relative == "receipt.json":
            raise ValueError("full hosted archive inventory has duplicate or receipt path")
        path = _full_file(bundle, relative)
        if (qualify.digest(path) != item.get("sha256")
                or path.stat().st_size != item.get("size")
                or type(item.get("modified_ns")) is not int):
            raise ValueError("full hosted archive file hash differs")
        if path.stat().st_mtime_ns != item["modified_ns"]:
            raise ValueError(f"full hosted archive file timestamp differs: {relative}")
        recorded[relative] = item["sha256"]
        recorded_times[relative] = item["modified_ns"]
    actual = {p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()}
    if any(p.is_symlink() for p in bundle.rglob("*")):
        raise ValueError("full hosted archive contains a symbolic member")
    if actual != set(recorded) | {"receipt.json"}:
        raise ValueError("full hosted archive has missing or unlisted files")
    artifact_target = "js" if target == "jsSafari" else target
    hashes = receipt.get("artifact_hashes")
    if not isinstance(hashes, dict) or set(hashes) != set(qualify.MODULES):
        raise ValueError("full hosted target binary hashes are incomplete")
    for module in qualify.MODULES:
        relative = f"staged/{qualify.target_binary_path(module, artifact_target)}"
        binary = _full_file(bundle, relative)
        sidecar = _full_file(bundle, relative + ".sha256")
        digest = qualify.digest(binary)
        if digest != hashes[module] or sidecar.read_text().strip().lower() != digest:
            raise ValueError("full hosted staged target binary differs")
    _full_staging(bundle, receipt, artifact_target, recorded)
    stage = receipt.get("stage")
    stage_tasks = [f":{module}:publishKotlinMultiplatformPublicationToStagingRepository"
                   for module in qualify.MODULES]
    stage_tasks += [f":{module}:publish{artifact_target[0].upper()}{artifact_target[1:]}PublicationToStagingRepository"
                    for module in qualify.MODULES]
    stage_window = _full_process(bundle, "", "stage", stage, None, stage_tasks)
    if final_contract and _full_original_path(target, stage["command"][0]) != wrapper:
        raise ValueError("full hosted staging wrapper differs from runner checkout")
    if final_contract and any(not stage_window[0] <= recorded_times[name] <= stage_window[1]
                              for name in recorded if name.startswith("staged/")):
        raise ValueError("full hosted staged publication predates invocation")
    input_paths = (full_corpus.MANIFEST_PATH, full_corpus.MAP_PATH,
                   full_corpus.PAIR_PATH, "tools/qualification/full_corpus.py",
                   "tools/qualification/foundation-probes.json")
    if final_contract:
        input_paths += ("tools/qualification/full_hosted.py",
                        "tools/qualification/hosted.py", "tools/qualification/qualify.py",
                        "tools/qualification/artifact.py", "build.gradle.kts",
                        "consumers/qualification/portable/build.gradle.kts")
    for relative in input_paths:
        archived = _full_file(bundle, f"inputs/{relative}")
        committed = full_corpus.committed_bytes(repository, candidate_sha, relative)
        if archived.read_bytes() != committed:
            raise ValueError("full hosted archived candidate input differs")
    if {name for name in recorded if name.startswith("inputs/")} != {
            f"inputs/{name}" for name in input_paths}:
        raise ValueError("full hosted archived candidate input inventory differs")
    expected_source_paths = set()
    for source in manifest["source_files"]:
        relative = f"sources/{source['path']}"
        expected_source_paths.add(relative)
        path = _full_file(bundle, relative)
        if qualify.digest(path) != source["sha256"]:
            raise ValueError("full hosted archived source file differs")
    if {name for name in recorded if name.startswith("sources/")} != expected_source_paths:
        raise ValueError("full hosted archived source inventory differs")
    expected_cases = {}
    for module, count in (("dyn4k-core", 2454), ("dyn4k", 58)):
        ids = {(case["classname"], case["method"]) for case in manifest["cases"]
               if case["module"] == module and case["source_set"] == "commonTest"}
        if len(ids) != count:
            raise ValueError("full hosted reviewed common case count differs")
        expected_cases[module] = ids
    probe_manifest = qualify.load_json_strict(repository / "tools/qualification/foundation-probes.json")
    group = next((g for g in probe_manifest["groups"] if g["id"] == f"consumer-{target}"), None)
    if group is None:
        raise ValueError("full hosted consumer manifest group is missing")
    consumer_cases = set(qualify.expected_probe_cases(probe_manifest, group))
    used = set()
    seen_invocations = set()
    for lane in configurations:
        config = lane["configuration"]
        if lane.get("status") != "FULL_COMMON_PASSED" or not re.fullmatch(
                r"[0-9a-f]{32}", str(lane.get("invocation_id", ""))):
            raise ValueError("full hosted configuration did not pass")
        invocation = lane["invocation_id"]
        if invocation in seen_invocations:
            raise ValueError("full hosted duplicate configuration invocation")
        seen_invocations.add(invocation)
        task = FULL_SOURCE_TASK[target]
        source_tasks = [f":{module}:{task}" for module in qualify.MODULES]
        source_window = _full_process(bundle, config, "source", lane.get("source_process"),
                                      invocation, source_tasks)
        consumer_window = _full_process(bundle, config, "consumer", lane.get("consumer_process"),
                                        invocation, [f":{task}"])
        graph_window = _full_process(bundle, config, "graph", lane.get("graph_process"),
                                     invocation, ["qualificationResolvedGraph"])
        if stage_window[1] > source_window[0] or source_window[1] > consumer_window[0] or consumer_window[1] > graph_window[0]:
            raise ValueError("full hosted source and consumer invocation order differs")
        staging = receipt.get("staging_repository")
        if (not isinstance(staging, str) or not staging
                or f"-PqualificationRepository={staging}" not in lane["consumer_process"]["command"]
                or f"-PqualificationRepository={staging}" not in lane["graph_process"]["command"]):
            raise ValueError("full hosted external consumer staging repository differs")
        if final_contract:
            for process_name in ("source", "consumer", "graph"):
                command = lane[f"{process_name}_process"]["command"]
                if _full_original_path(target, command[0]) != wrapper:
                    raise ValueError("full hosted process wrapper differs from runner checkout")
                if process_name in ("consumer", "graph") and (
                        "-p" not in command or str(consumer_root) not in command):
                    raise ValueError("full hosted external consumer project differs")
            if f":dyn4k:{task}" not in lane["source_process"]["command"]:
                raise ValueError("full hosted facade source task is missing")
            if target == "jsSafari" and (
                    config == "production" and
                    "-PqualificationProduction=true" not in lane["source_process"]["command"]
                    or "-PqualificationSafari=true" not in lane["consumer_process"]["command"]):
                raise ValueError("full hosted Safari configuration differs")
        _full_graph(bundle, config, target, lane.get("consumer_graph"),
                    hashes, staging)
        if final_contract:
            graph_artifacts = lane["consumer_graph"].get("artifacts")
            resolved = lane.get("resolved_artifacts")
            if (not isinstance(graph_artifacts, list) or not isinstance(resolved, list)
                    or len(resolved) != len(graph_artifacts)):
                raise ValueError("full hosted resolved consumer artifact archive is incomplete")
            for index, (item, archived) in enumerate(zip(graph_artifacts, resolved)):
                if not isinstance(item, dict) or not isinstance(archived, dict):
                    raise ValueError("full hosted resolved consumer artifact identity is invalid")
                relative = f"{config}/resolved-artifacts/{index:03d}-{item['name']}"
                if (archived.get("archive_path") != relative
                        or any(archived.get(key) != item.get(key) for key in
                               ("component", "file", "name", "size", "sha256"))):
                    raise ValueError("full hosted resolved consumer artifact provenance differs")
                path = _full_file(bundle, relative)
                if qualify.digest(path) != item.get("sha256") or path.stat().st_size != item.get("size"):
                    raise ValueError("full hosted resolved consumer artifact bytes differ")
                used.add(relative)
        source_script = _full_file(bundle, f"{config}/qualification.init.gradle")
        graph_script = _full_file(bundle, f"{config}/qualification-graph.init.gradle")
        if not source_script.read_bytes() or not graph_script.read_bytes():
            raise ValueError("full hosted test or consumer graph script is empty")
        for script in (source_script, graph_script):
            used.add(script.relative_to(bundle).as_posix())
        command = lane["source_process"]["command"]
        source_init = f"{config}/qualification.init.gradle"
        if ("--init-script" not in command or not any(arg.endswith(source_init) for arg in command)
                or "--init-script" not in lane["consumer_process"]["command"]
                or not any(arg.endswith(source_init) for arg in lane["consumer_process"]["command"])
                or "--init-script" not in lane["graph_process"]["command"]
                or not any(arg.endswith(f"{config}/qualification-graph.init.gradle")
                           for arg in lane["graph_process"]["command"])):
            raise ValueError("full hosted source configuration script is not bound")
        if final_contract:
            if (str(original_root / source_init) not in command
                    or str(original_root / source_init) not in lane["consumer_process"]["command"]
                    or str(original_root / f"{config}/qualification-graph.init.gradle")
                    not in lane["graph_process"]["command"]):
                raise ValueError("full hosted original configuration script path differs")
        source_log = _full_file(bundle, f"{config}/source/stdout.txt").read_text()
        if target == "jsSafari":
            if "useSafari()" not in source_script.read_text():
                raise ValueError("full hosted Safari launcher is absent")
            if config == "production" and "jsTestTestProductionExecutableCompileSync" not in source_log:
                raise ValueError("full hosted production Safari executable was not built")
        else:
            mode = "Release" if config == "optimized-opt" else "Debug"
            link = f"link{mode}Test{target[0].upper()}{target[1:]}"
            if any(f"> Task :{module}:{link}" not in source_log for module in qualify.MODULES):
                raise ValueError("full hosted configured native executable was not linked")
            if config == "optimized-opt" and "RELEASE" not in source_script.read_text():
                raise ValueError("full hosted optimized native configuration script differs")
        groups = lane.get("source")
        if (not isinstance(groups, list) or len(groups) != 2
                or [g.get("module") for g in groups if isinstance(g, dict)]
                != list(qualify.MODULES)):
            raise ValueError("full hosted source report groups differ")
        for source_group in groups:
            used |= _full_xml(bundle, config, source_group,
                              expected_cases[source_group["module"]], target,
                              source_window, receipt["runtime"].get("safari_version"),
                              recorded_times=recorded_times)
        used |= _full_xml(bundle, config, lane.get("consumer"), consumer_cases, target,
                          consumer_window, consumer=True, recorded_times=recorded_times)
        source_executables = lane.get("source_executables")
        if not isinstance(source_executables, dict) or set(source_executables) != set(qualify.MODULES):
            raise ValueError("full hosted source executable records differ")
        for name, executable in [*source_executables.items(),
                                 ("consumer", lane.get("consumer_executable"))]:
            if not isinstance(executable, dict):
                raise ValueError("full hosted executable identity is missing")
            relative = executable.get("archive_path")
            if not isinstance(relative, str):
                raise ValueError("full hosted executable archive path is missing")
            path = _full_file(bundle, relative)
            original = str(executable.get("path", "")).replace("\\", "/")
            if target == "jsSafari":
                mode = "Production" if config == "production" else "Development"
                fragment = f"/build/compileSync/js/test/test{mode}Executable/kotlin/"
            else:
                mode = "releaseTest" if config == "optimized-opt" else "debugTest"
                fragment = f"/build/bin/{target}/{mode}/"
            if (fragment not in original
                    or not relative.startswith(f"{config}/executables/{name}/")
                    or path.name != original.rsplit("/", 1)[-1]):
                raise ValueError("full hosted executable configuration path differs")
            if final_contract:
                project = consumer_root if name == "consumer" else repository_root / name
                original_product = _full_original_path(target, executable.get("path", ""))
                if target == "jsSafari":
                    mode = "Production" if config == "production" else "Development"
                    parent = project / "build/compileSync/js/test" / f"test{mode}Executable/kotlin"
                else:
                    mode = "releaseTest" if config == "optimized-opt" else "debugTest"
                    parent = project / "build/bin" / target / mode
                if original_product.parent != parent:
                    raise ValueError("full hosted original test executable path differs")
            if (qualify.digest(path) != executable.get("sha256")
                    or path.stat().st_size != executable.get("size")
                    or recorded_times.get(portable_path(relative)) != executable.get("modified_ns")
                    or type(executable.get("modified_ns")) is not int):
                raise ValueError("full hosted executable bytes or identity differ")
            window = consumer_window if name == "consumer" else source_window
            if not window[0] <= executable["modified_ns"] <= window[1]:
                raise ValueError("full hosted executable predates invocation")
            used.add(portable_path(relative))
    if {p for p in recorded if p.endswith(".xml")} != used & {p for p in used if p.endswith(".xml")}:
        raise ValueError("full hosted archive contains unlisted XML")
    allowed = used | expected_source_paths | {f"inputs/{path}" for path in input_paths}
    allowed |= {p for p in recorded if p.startswith("staged/")}
    allowed |= {f"stage/{stream}.txt" for stream in ("stdout", "stderr")}
    for config in FULL_CONFIGS[target]:
        allowed |= {f"{config}/{name}/{stream}.txt"
                    for name in ("source", "consumer", "graph")
                    for stream in ("stdout", "stderr")}
    if set(recorded) != allowed:
        raise ValueError("full hosted archive contains an unexpected or missing member")
    return receipt


def verify_full_hosted(bundle, candidate_sha, repository):
    bundle = Path(bundle)
    if bundle.is_dir():
        result = _verify_full_hosted_directory(bundle, candidate_sha, repository)
        result["_verified_receipt_sha256"] = qualify.digest(bundle / "receipt.json")
        return result
    if not bundle.is_file() or bundle.suffix != ".tar":
        raise ValueError("full hosted bundle must be a directory or transport tar")
    with tempfile.TemporaryDirectory() as temporary:
        extracted = Path(temporary)
        names = set()
        try:
            archive_stream = tarfile.open(bundle, "r")
        except tarfile.TarError as error:
            raise ValueError(f"full hosted transport archive is invalid: {error}") from error
        with archive_stream as archive:
            for member in archive:
                relative = portable_path(member.name)
                if relative in names or not member.isfile():
                    raise ValueError("full hosted transport archive has duplicate or non-file member")
                names.add(relative)
                modified = member.pax_headers.get("dyn4k.mtime_ns", "")
                if not re.fullmatch(r"[0-9]+", modified):
                    raise ValueError("full hosted transport archive timestamp is missing")
                if not math.isfinite(member.mtime) or int(member.mtime) != int(modified) // 1_000_000_000:
                    raise ValueError("full hosted transport archive PAX timestamp differs")
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("full hosted transport archive bytes are missing")
                destination = extracted / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("wb") as stream:
                    shutil.copyfileobj(source, stream)
                if destination.stat().st_size != member.size:
                    raise ValueError("full hosted transport archive size differs")
                os.utime(destination, ns=(int(modified), int(modified)))
        if "receipt.json" not in names:
            raise ValueError("full hosted transport receipt is missing")
        result = _verify_full_hosted_directory(extracted, candidate_sha, repository)
        result["_verified_receipt_sha256"] = qualify.digest(extracted / "receipt.json")
        result["_verified_transport_sha256"] = qualify.digest(bundle)
        return result


def portable_path(value):
    if not isinstance(value, str) or not value:
        raise ValueError("bundle inventory path is missing")
    path = value.replace("\\", "/")
    parts = path.split("/")
    if (any(part in ("", ".", "..") for part in parts)
            or ":" in parts[0]):
        raise ValueError(f"bundle inventory path is unsafe: {value}")
    return "/".join(parts)


def collect_group(repository, destination, manifest, group, started, finished, files,
                  recorded_times=None):
    group_id = group["id"]
    expected = qualify.expected_probe_cases(manifest, group)
    paths = sorted(repository.glob(group["report_pattern"]))
    if not paths:
        raise ValueError(f"missing report group {group_id}")
    observed = []
    for path in paths:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"invalid report {path}: missing or symbolic")
        relative = path.relative_to(repository)
        file_key = portable_path((Path("xml") / relative).as_posix())
        if recorded_times is None:
            mtime_ns = path.stat().st_mtime_ns
        else:
            if file_key not in recorded_times:
                raise ValueError(f"raw report has no bound file time: {file_key}")
            mtime_ns = recorded_times[file_key]
        if type(mtime_ns) is not int or not started <= mtime_ns <= finished:
            raise ValueError(f"stale report {path}: outside bound execution")
        bundled = destination / "xml" / relative
        bundled.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, bundled)
        suite = ET.parse(bundled).getroot()
        if suite.tag != "testsuite":
            raise ValueError(f"invalid report {path}: root is not testsuite")
        cases = list(suite.iter("testcase"))
        counts = {name: int(suite.get(name, "-1")) for name in
                  ("tests", "failures", "errors", "skipped")}
        actual = {"tests": len(cases),
                  "failures": sum(case.find("failure") is not None for case in cases),
                  "errors": sum(case.find("error") is not None for case in cases),
                  "skipped": sum(case.find("skipped") is not None for case in cases)}
        if counts != actual or any(value < 0 for value in counts.values()):
            raise ValueError(f"invalid report {path}: suite counts differ from case elements")
        if counts["failures"] or counts["errors"] or counts["skipped"]:
            raise ValueError(f"invalid report {path}: failed or skipped cases")
        duration = float(suite.get("time", "nan"))
        if not math.isfinite(duration) or duration < 0:
            raise ValueError(f"invalid report {path}: suite time is invalid")
        for case in cases:
            duration = float(case.get("time", "nan"))
            identity = (case.get("classname"), case.get("name"))
            if not math.isfinite(duration) or duration < 0 or not all(identity):
                raise ValueError(f"invalid report {path}: case time or identity is invalid")
            observed.append(identity)
        files.append({"path": portable_path(bundled.relative_to(destination).as_posix()),
                      "sha256": qualify.digest(bundled), "mtime_ns": mtime_ns})
    if len(observed) != len(set(observed)):
        raise ValueError(f"duplicate cases in {group_id}")
    observed_set = set(observed)
    if any(identity not in observed_set for identity in expected):
        raise ValueError(f"missing selected cases in {group_id}")
    return {"selected": len(expected), "reported": len(observed)}


def check_probe(probe, manifest, groups, ids, candidate_sha):
    selected = {**manifest, "groups": [groups[group_id] for group_id in ids]}
    expected = sum(len(qualify.expected_probe_cases(manifest, groups[group_id])) for group_id in ids)
    if (probe.get("candidate_sha") != candidate_sha
            or probe.get("status") != "PROBE_PASSED"
            or probe.get("manifest_sha256") != qualify.manifest_digest(selected)
            or probe.get("expected") != expected or probe.get("executed") != expected
            or probe.get("failures") != 0 or probe.get("errors") != 0
            or probe.get("skipped") != 0
            or type(probe.get("reported")) is not int
            or probe.get("reported") < expected
            or probe.get("exit_code") != 0):
        raise ValueError(f"probe for {', '.join(ids)} differs from frozen executed suite")
    qualify.validate_probe_accounting(probe, manifest, ids)
    started, finished = probe.get("started_at_ns"), probe.get("finished_at_ns")
    if (type(started) is not int or type(finished) is not int
            or started <= 0 or finished < started):
        raise ValueError(f"probe for {', '.join(ids)} lacks execution time")
    return started, finished


def copy_json(path, destination):
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing evidence JSON: {path.name}")
    data = qualify.load_json_strict(path)
    if not isinstance(data, dict):
        raise ValueError(f"evidence JSON is not an object: {path.name}")
    target = destination / "json" / path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    return data


def capture_staging(repository, destination, targets, candidate_sha):
    staging = repository / "build/staging-repository"
    source_license = repository / "LICENSE.md"
    if not source_license.is_file():
        raise ValueError("repository license is missing")
    shutil.copy2(source_license, destination / "LICENSE.md")
    gav = []
    files = []
    hashes = {}
    names = {module for module in qualify.MODULES}
    names.update(qualify.target_publication_name(module, target)
                 for module in qualify.MODULES for target in targets)
    metadata_names = {qualify.target_publication_name(module, target)
                      for module in qualify.MODULES for target in targets
                      if target in qualify.APPLE_TARGETS}
    for name in sorted(names):
        base = staging / qualify.GROUP.replace(".", "/") / name / qualify.VERSION
        suffixes = (".pom", ".module", "-sources.jar", "-javadoc.jar", "-license.md")
        if name in qualify.MODULES:
            suffixes += (".jar",)
        if name in metadata_names:
            suffixes += ("-metadata.jar",)
        for suffix in suffixes:
            source = base / f"{name}-{qualify.VERSION}{suffix}"
            if not source.is_file() or source.is_symlink():
                raise ValueError(f"staged GAV descriptor missing: {name}{suffix}")
            if suffix == ".pom":
                root = ET.parse(source).getroot()
                namespace = "{http://maven.apache.org/POM/4.0.0}"
                for key, expected in (("groupId", qualify.GROUP), ("artifactId", name),
                                      ("version", qualify.VERSION)):
                    if root.findtext(namespace + key) != expected:
                        raise ValueError(f"staged GAV differs in {name} {key}")
            elif suffix == ".module":
                metadata = qualify.load_json_strict(source)
                if (not isinstance(metadata, dict)
                        or not isinstance(metadata.get("component"), dict)
                        or metadata["component"].get("version") != qualify.VERSION):
                    raise ValueError(f"staged Gradle metadata version differs in {name}")
            target_path = destination / "staged" / source.relative_to(staging)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target_path)
            files.append({"path": portable_path(target_path.relative_to(destination).as_posix()),
                          "sha256": qualify.digest(target_path)})
            sidecar = source.with_name(source.name + ".sha256")
            if not sidecar.is_file() or sidecar.read_text().strip().lower() != qualify.digest(source):
                raise ValueError(f"staged checksum differs: {source.name}")
            sidecar_path = destination / "staged" / sidecar.relative_to(staging)
            shutil.copy2(sidecar, sidecar_path)
            files.append({"path": portable_path(sidecar_path.relative_to(destination).as_posix()),
                          "sha256": qualify.digest(sidecar_path)})
        gav.append(f"{qualify.GROUP}:{name}:{qualify.VERSION}")
    for target in targets:
        hashes[target] = {}
        for module in qualify.MODULES:
            binary = staging / qualify.target_binary_path(module, target)
            sidecar = binary.with_name(binary.name + ".sha256")
            if not binary.is_file() or not sidecar.is_file() or sidecar.is_symlink():
                raise ValueError(f"staged binary or checksum missing: {module} {target}")
            actual = qualify.digest(binary)
            if sidecar.read_text().strip().lower() != actual:
                raise ValueError(f"staged binary checksum differs: {module} {target}")
            binary_path = destination / "staged" / binary.relative_to(staging)
            binary_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(binary, binary_path)
            files.append({"path": portable_path(binary_path.relative_to(destination).as_posix()),
                          "sha256": qualify.digest(binary_path)})
            target_path = destination / "staged" / sidecar.relative_to(staging)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sidecar, target_path)
            files.append({"path": portable_path(target_path.relative_to(destination).as_posix()),
                          "sha256": qualify.digest(target_path)})
            hashes[target][module] = actual
    audit = qualify.audit_staging(staging, candidate_sha, targets, source_license)
    if audit["status"] != "PASSED":
        raise ValueError("staged publication is partial or invalid: " + "; ".join(audit["errors"]))
    return gav, files, hashes, audit["content_contract"]


def stage_hosted(repository, manifest, candidate_sha, target, probe_path, matrix_path, destination):
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "json").mkdir()
    result = {"candidate_sha": candidate_sha, "route": target, "status": "PROBE_FAILED",
              "reason": "raw evidence is incomplete", "expected": 0, "executed": 0,
              "reported": 0, "groups": {}, "reported_groups": {}, "files": []}
    problems = []
    nonpass_status = None

    try:
        probe = copy_json(probe_path, destination)
        matrix = copy_json(matrix_path, destination) if matrix_path else {"candidate_sha": candidate_sha}
        if matrix.get("candidate_sha") != candidate_sha:
            raise ValueError("matrix candidate SHA differs from bundle")
        if probe.get("candidate_sha") != candidate_sha:
            raise ValueError("hosted candidate SHA differs from bundle")
        if probe.get("target") != target:
            raise ValueError("hosted target differs from bundle")
        if probe.get("status") != "PROBE_PASSED":
            nonpass_status = probe.get("status")
            if nonpass_status not in ("PROBE_FAILED", "UNAVAILABLE", "NOT_RUN"):
                raise ValueError("hosted probe status is invalid")
            result["reason"] = probe.get("reason", "hosted probe did not pass")
            return result
        qualify.validate_hosted_probe(probe, candidate_sha, repository)
        artifact_target = "js" if target == "jsSafari" else target
        result["gav"], result["staged_files"], hashes, result["staged_content_contract"] = capture_staging(
            repository, destination, (artifact_target,), candidate_sha)
        if "stage_receipt_sha256" in probe or "stage_audit_sha256" in probe:
            if not probe.get("stage_receipt_sha256") or not probe.get("stage_audit_sha256"):
                raise ValueError("hosted staging receipt and audit must both be present")
            stage_dir = repository / "build/staging-repository/.qualification" / target
            for filename, expected in (("receipt.json", probe["stage_receipt_sha256"]),
                                       ("audit.json", probe["stage_audit_sha256"]),
                                       ("stage.log", None)):
                source = stage_dir / filename
                if not source.is_file() or source.is_symlink():
                    raise ValueError(f"hosted staging {filename} is missing")
                if expected and qualify.digest(source) != expected:
                    raise ValueError(f"hosted staging {filename} bytes differ")
                destination_path = destination / "staged/.qualification" / target / filename
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination_path)
                result["staged_files"].append({
                    "path": portable_path(destination_path.relative_to(destination).as_posix()),
                    "sha256": qualify.digest(destination_path)})
        if hashes[artifact_target] != probe["artifact_hashes"]:
            raise ValueError("staged GAV binary hashes differ from hosted observation")
        groups = {group["id"]: group for group in manifest["groups"]}
        selections = {"consumer_probe": (f"consumer-{target}",)}
        if target != "jsSafari":
            selections["source_probe"] = (f"core-{target}", target)
        for key, ids in selections.items():
            suffix = "source" if key == "source_probe" else "consumer"
            sidecar = probe_path.with_name(probe_path.stem + f"-{suffix}.json")
            if copy_json(sidecar, destination) != probe[key]:
                problems.append(f"{suffix} JSON differs from hosted result")
            started, finished = check_probe(probe[key], manifest, groups, ids, candidate_sha)
            declared_groups = {item["id"]: item for item in probe[key]["groups"]}
            for group_id in ids:
                group = groups[group_id]
                expected = qualify.expected_probe_cases(manifest, group)
                result["expected"] += len(expected)
                counts = collect_group(repository, destination, manifest, group,
                                       started, finished, result["files"])
                if (counts["selected"] != declared_groups[group_id]["executed"]
                        or counts["reported"] != declared_groups[group_id]["reported"]):
                    raise ValueError(f"raw report counts differ from probe: {group_id}")
                result["groups"][group_id] = counts["selected"]
                result["reported_groups"][group_id] = counts["reported"]
                result["executed"] += counts["selected"]
                result["reported"] += counts["reported"]
        if result["executed"] != result["expected"]:
            problems.append("raw executed count differs from frozen manifest")
        result["runtime"] = probe.get("runtime")
        result["artifact_hashes"] = probe.get("artifact_hashes")
    except (KeyError, OSError, TypeError, ValueError, ET.ParseError, json.JSONDecodeError) as error:
        problems.append(str(error))
    finally:
        if nonpass_status is None or problems:
            result.update(status="PROBE_FAILED" if problems else "PROBE_PASSED",
                          reason="; ".join(problems) if problems else "raw XML matches frozen cases")
        else:
            result["status"] = nonpass_status
        (destination / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


UBUNTU_PROBES = {
    "foundation-probe.json": ("core-jvm", "jvm", "core-linuxX64", "linuxX64"),
    "web-probe.json": ("core-jsNode", "jsNode", "core-wasmJsNode", "wasmJsNode",
                       "core-wasmWasiNode", "wasmWasiNode"),
    "android-host-probe.json": ("core-androidHost", "androidHost"),
    "portable-consumer-probe.json": ("consumer-jvm", "consumer-linuxX64",
                                    "consumer-jsNode", "consumer-wasmJsNode",
                                    "consumer-wasmWasiNode", "consumer-androidHost"),
}


def ubuntu_runtime():
    import hosted

    release = platform.freedesktop_os_release()
    return {"system": platform.system(), "machine": platform.machine(),
            "kernel_release": platform.release(),
            "distribution": release.get("ID", ""),
            "os_version": release.get("VERSION_ID", ""),
            "runner_image_os": os.environ.get("ImageOS", ""),
            "runner_image_version": os.environ.get("ImageVersion", ""),
            "github_actions": os.environ.get("GITHUB_ACTIONS") == "true",
            "java_version": hosted.tool_version(["java", "-version"], r'version "([^"]+)"')}


def check_ubuntu_runtime(runtime):
    if (not isinstance(runtime, dict) or runtime.get("system") != "Linux"
            or str(runtime.get("machine", "")).lower() not in ("x86_64", "amd64")
            or not runtime.get("distribution") or not runtime.get("os_version")
            or not runtime.get("kernel_release") or not runtime.get("java_version")):
        raise ValueError("Ubuntu bundle runtime identity is incomplete or wrong")
    if runtime.get("github_actions") and (runtime.get("distribution") != "ubuntu"
                                          or not runtime.get("runner_image_os")
                                          or not runtime.get("runner_image_version")):
        raise ValueError("Ubuntu bundle runtime runner image is missing or wrong")


def stage_ubuntu(repository, manifest, candidate_sha, evidence_dir, destination):
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "json").mkdir()
    result = {"candidate_sha": candidate_sha, "route": "ubuntu-host", "status": "PROBE_FAILED",
              "reason": "raw evidence is incomplete", "expected": 0, "executed": 0,
              "reported": 0, "groups": {}, "reported_groups": {}, "files": []}
    problems = []
    try:
        result["runtime"] = ubuntu_runtime()
        check_ubuntu_runtime(result["runtime"])
        groups = {group["id"]: group for group in manifest["groups"]}
        for name, ids in UBUNTU_PROBES.items():
            probe = copy_json(evidence_dir / name, destination)
            started, finished = check_probe(probe, manifest, groups, ids, candidate_sha)
            declared_groups = {item["id"]: item for item in probe["groups"]}
            for group_id in ids:
                group = groups[group_id]
                result["expected"] += len(qualify.expected_probe_cases(manifest, group))
                counts = collect_group(repository, destination, manifest, group,
                                       started, finished, result["files"])
                if (counts["selected"] != declared_groups[group_id]["executed"]
                        or counts["reported"] != declared_groups[group_id]["reported"]):
                    raise ValueError(f"raw report counts differ from probe: {group_id}")
                result["groups"][group_id] = counts["selected"]
                result["reported_groups"][group_id] = counts["reported"]
                result["executed"] += counts["selected"]
                result["reported"] += counts["reported"]
        (result["gav"], result["staged_files"], result["artifact_hashes"],
         result["staged_content_contract"]) = capture_staging(
            repository, destination, ("jvm", "linuxX64", "js", "wasmJs", "wasmWasi", "android"), candidate_sha)
        for name in ("artifact-audit.json", "runtime-matrix.json"):
            data = copy_json(evidence_dir / name, destination)
            if data.get("candidate_sha") != candidate_sha:
                raise ValueError(f"{name} candidate SHA differs from bundle")
        provider = evidence_dir / "provider.log"
        if not provider.is_file() or provider.is_symlink() or not provider.read_bytes():
            raise ValueError("duplicate-provider diagnosis log is missing")
        shutil.copy2(provider, destination / "provider.log")
        if result["executed"] != result["expected"]:
            raise ValueError("raw executed count differs from frozen manifest")
    except (KeyError, OSError, TypeError, ValueError, ET.ParseError, json.JSONDecodeError) as error:
        problems.append(str(error))
    result["status"] = "PROBE_FAILED" if problems else "PROBE_PASSED"
    result["reason"] = "; ".join(problems) if problems else "raw XML matches frozen cases"
    (destination / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def verify_bundle(bundle, manifest, candidate_sha, require_matrix=True):
    summary = qualify.load_json_strict(bundle / "verification.json")
    if not isinstance(summary, dict):
        raise ValueError("bundle verification JSON is not an object")
    if summary.get("candidate_sha") != candidate_sha:
        raise ValueError("bundle candidate SHA differs from requested candidate")
    if summary.get("status") != "PROBE_PASSED":
        raise ValueError(summary.get("reason", "bundle did not pass"))
    route = summary.get("route")
    if route == "ubuntu-host":
        check_ubuntu_runtime(summary.get("runtime"))
        selections = UBUNTU_PROBES
    else:
        import hosted
        if route not in hosted.TARGETS:
            raise ValueError("unknown bundle route")
        name = f"hosted-{route}"
        top = qualify.load_json_strict(bundle / "json" / f"{name}.json")
        qualify.validate_hosted_probe(top, candidate_sha)
        if top.get("status") != "PROBE_PASSED":
            raise ValueError(f"hosted top status is {top.get('status')}, not PROBE_PASSED")
        if summary.get("runtime") != top.get("runtime"):
            raise ValueError("bundle runtime differs from hosted observation")
        selections = {f"{name}-consumer.json": (f"consumer-{route}",)}
        if route != "jsSafari":
            selections[f"{name}-source.json"] = (f"core-{route}", route)
    groups = {group["id"]: group for group in manifest["groups"]}
    found = {}
    found_reported = {}
    files = []
    recorded = summary.get("files")
    if (not isinstance(recorded, list) or not recorded
            or any(not isinstance(item, dict) for item in recorded)):
        raise ValueError("bundle raw file inventory is missing")
    normalized_recorded = [{**item, "path": portable_path(item.get("path"))}
                           for item in recorded]
    recorded_times = {item["path"]: item.get("mtime_ns") for item in normalized_recorded}
    if len(recorded_times) != len(recorded):
        raise ValueError("bundle raw file inventory has duplicate paths")
    import tempfile
    with tempfile.TemporaryDirectory() as temporary:
        scratch = Path(temporary)
        for name, ids in selections.items():
            probe = qualify.load_json_strict(bundle / "json" / name)
            if route != "ubuntu-host":
                role = "consumer_probe" if name.endswith("-consumer.json") else "source_probe"
                if probe != top.get(role):
                    raise ValueError(f"bundled {role} differs from hosted observation")
            started, finished = check_probe(probe, manifest, groups, ids, candidate_sha)
            declared_groups = {item["id"]: item for item in probe["groups"]}
            for group_id in ids:
                counts = collect_group(bundle / "xml", scratch, manifest, groups[group_id],
                                       started, finished, files, recorded_times)
                if (counts["selected"] != declared_groups[group_id]["executed"]
                        or counts["reported"] != declared_groups[group_id]["reported"]):
                    raise ValueError(f"bundled report counts differ from probe: {group_id}")
                found[group_id] = counts["selected"]
                found_reported[group_id] = counts["reported"]
    if (found != summary.get("groups") or sum(found.values()) != summary.get("executed")
            or found_reported != summary.get("reported_groups")
            or sum(found_reported.values()) != summary.get("reported")):
        raise ValueError("bundle counts differ from raw XML")
    if summary.get("expected") != sum(found.values()):
        raise ValueError("bundle expected count differs from frozen cases")
    if sorted(files, key=lambda item: item["path"]) != sorted(normalized_recorded,
                                                              key=lambda item: item["path"]):
        raise ValueError("bundle XML hashes differ from verification")
    actual_paths = {path.relative_to(bundle).as_posix() for path in (bundle / "xml").rglob("*.xml")}
    if actual_paths != {item["path"] for item in files}:
        raise ValueError("bundle contains unlisted XML")
    staged_files = summary.get("staged_files")
    if not isinstance(staged_files, list) or not staged_files:
        raise ValueError("staged GAV provenance is missing")
    if any(not isinstance(item, dict) for item in staged_files):
        raise ValueError("staged GAV provenance is invalid")
    staged_files = [{**item, "path": portable_path(item.get("path"))}
                    for item in staged_files]
    if len({item["path"] for item in staged_files}) != len(staged_files):
        raise ValueError("staged GAV provenance has duplicate paths")
    for item in staged_files:
        path = bundle / item["path"]
        if not path.is_file() or path.is_symlink() or qualify.digest(path) != item["sha256"]:
            raise ValueError("staged GAV descriptor or checksum differs from bundle")
    staged_paths = {path.relative_to(bundle).as_posix() for path in (bundle / "staged").rglob("*")
                    if path.is_file()}
    if staged_paths != {item["path"] for item in staged_files}:
        raise ValueError("bundle contains unlisted staged provenance")
    names = []
    for item in staged_files:
        path = bundle / item["path"]
        if path.suffix != ".pom":
            continue
        name = path.parent.parent.name
        root = ET.parse(path).getroot()
        namespace = "{http://maven.apache.org/POM/4.0.0}"
        if (root.findtext(namespace + "groupId") != qualify.GROUP
                or root.findtext(namespace + "artifactId") != name
                or root.findtext(namespace + "version") != qualify.VERSION):
            raise ValueError("bundled staged GAV identity differs")
        names.append(f"{qualify.GROUP}:{name}:{qualify.VERSION}")
    if sorted(names) != sorted(summary.get("gav", [])):
        raise ValueError("bundled staged GAV set differs")
    targets = ("jvm", "linuxX64", "js", "wasmJs", "wasmWasi", "android") if route == "ubuntu-host" else (
        "js" if route == "jsSafari" else route,)
    license_file = bundle / "LICENSE.md"
    if not license_file.is_file() or license_file.is_symlink():
        raise ValueError("bundle source license is missing")
    staged_audit = qualify.audit_staging(bundle / "staged", candidate_sha, targets, license_file,
                                         content_contract=summary.get("staged_content_contract"))
    if staged_audit["status"] != "PASSED":
        raise ValueError("bundled staged publication is partial or invalid: " + "; ".join(staged_audit["errors"]))
    if route != "ubuntu-host" and ("stage_receipt_sha256" in top or "stage_audit_sha256" in top):
        if not top.get("stage_receipt_sha256") or not top.get("stage_audit_sha256"):
            raise ValueError("bundled hosted stage identity is incomplete")
        stage_dir = bundle / "staged/.qualification" / route
        receipt_path = stage_dir / "receipt.json"
        audit_path = stage_dir / "audit.json"
        console_path = stage_dir / "stage.log"
        if (not receipt_path.is_file() or qualify.digest(receipt_path) != top["stage_receipt_sha256"]
                or not audit_path.is_file() or qualify.digest(audit_path) != top["stage_audit_sha256"]):
            raise ValueError("bundled hosted stage receipt or audit bytes differ")
        verified = qualify.audit_staging(bundle / "staged", candidate_sha, targets,
                                         license_file, receipt_path, console_path,
                                         content_contract=summary.get("staged_content_contract"))
        if verified != qualify.load_json_strict(audit_path) or verified["status"] != "PASSED":
            raise ValueError("bundled hosted stage task outcome or artifact audit differs")
    observed_hashes = {}
    for target in targets:
        observed_hashes[target] = {}
        for module in qualify.MODULES:
            relative = qualify.target_binary_path(module, target) + ".sha256"
            sidecar = bundle / "staged" / relative
            digest = sidecar.read_text().strip().lower()
            if not qualify.SHA64.fullmatch(digest):
                raise ValueError("bundled staged binary checksum is invalid")
            binary = bundle / "staged" / qualify.target_binary_path(module, target)
            if (not binary.is_file() or binary.is_symlink()
                    or qualify.digest(binary) != digest):
                raise ValueError(f"bundled staged binary checksum differs or binary is missing: {module} {target}")
            observed_hashes[target][module] = digest
    expected_hashes = (summary.get("artifact_hashes") if route == "ubuntu-host"
                       else {targets[0]: summary.get("artifact_hashes")})
    if observed_hashes != expected_hashes:
        raise ValueError("bundled staged binary hashes differ")
    matrix_name = "runtime-matrix.json" if route == "ubuntu-host" else f"matrix-{route}.json"
    matrix_path = bundle / "json" / matrix_name
    if matrix_path.is_file():
        matrix = qualify.load_json_strict(matrix_path)
        expected_lanes = {case["id"] for case in qualify.expand(qualify.matrix())}
        if (len(expected_lanes) != 112 or matrix.get("candidate_sha") != candidate_sha
                or matrix.get("total") != len(expected_lanes)):
            raise ValueError("bundle runtime matrix candidate or size differs")
        lanes = matrix.get("lanes")
        if not isinstance(lanes, list) or len(lanes) != len(expected_lanes):
            raise ValueError("bundle matrix lane set is incomplete")
        if any(not isinstance(lane, dict) or not isinstance(lane.get("id"), str)
               for lane in lanes):
            raise ValueError("bundle matrix lane identity is invalid")
        lane_ids = [lane["id"] for lane in lanes]
        if len(set(lane_ids)) != len(lane_ids) or set(lane_ids) != expected_lanes:
            raise ValueError("bundle matrix lane IDs are missing, duplicate, or unknown")
        statuses = ("PASSED", "FAILED", "UNAVAILABLE", "NOT_RUN")
        if any(lane.get("status") not in statuses for lane in lanes):
            raise ValueError("bundle matrix lane status is invalid")
        counted = {status: sum(lane["status"] == status for lane in lanes)
                   for status in statuses}
        declared = matrix.get("counts")
        if (not isinstance(declared, dict) or set(declared) != set(statuses)
                or any(type(value) is not int for value in declared.values())
                or declared != counted):
            raise ValueError("bundle matrix counts differ from lane records")
        if route != "ubuntu-host":
            bounded = matrix.get("bounded_hosted_probes", [])
            if bounded != [top]:
                raise ValueError("bundle matrix bounded observation differs from hosted probe")
    elif require_matrix:
        raise ValueError("bundle runtime matrix is missing")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Package and verify complete bounded XML evidence")
    parser.add_argument("action", choices=("hosted", "ubuntu", "verify"))
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--target")
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--matrix", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--full-hosted", action="store_true")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[2]
    qualify.require_clean_checkout(repository, args.candidate_sha)
    if args.full_hosted or (args.action == "verify" and (
            args.output.suffix == ".tar" or (args.output / "receipt.json").is_file())):
        if args.action != "verify":
            parser.error("full hosted archive supports verify only")
        try:
            result = verify_full_hosted(args.output, args.candidate_sha, repository)
        except (OSError, TypeError, ValueError, ET.ParseError, tarfile.TarError) as error:
            print(f"full hosted archive failed: {error}", file=sys.stderr)
            return 1
        print(json.dumps({"target": result["target"], "status": result["status"],
                          "configurations": len(result["configurations"])}))
        return 0
    manifest = qualify.load_json_strict(repository / "tools/qualification/foundation-probes.json")
    if args.action == "hosted":
        result = stage_hosted(repository, manifest, args.candidate_sha, args.target,
                              args.probe, args.matrix, args.output)
    elif args.action == "ubuntu":
        result = stage_ubuntu(repository, manifest, args.candidate_sha,
                              args.evidence_dir, args.output)
    else:
        result = verify_bundle(args.output, manifest, args.candidate_sha)
    print(json.dumps({"route": result["route"], "status": result["status"],
                      "executed": result["executed"], "expected": result["expected"],
                      "reported": result.get("reported", 0),
                      "reason": result["reason"]}))
    return 0 if result["status"] == "PROBE_PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
