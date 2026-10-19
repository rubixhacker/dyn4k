#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import independent_gates


CONSUMER = "consumers/qualification/portable/full-wasm-node"
MODULES = ("dyn4k-core", "dyn4k")
GROUP = "io.github.rubixhacker"
VERSION = "0.1.0-alpha.1"
LANES = {
    f"{target}:{runtime}:{role}:{mode}"
    for target, runtimes in (("wasmJs", ("Node.js",)),
                             ("wasmWasi", ("Node.js", "Wasmtime")))
    for runtime in runtimes for role in ("minimum", "current")
    for mode in ("development", "production")
}
RUNTIME_PINS = {
    ("wasmJs", "Node.js", "minimum"): (22, 23, 3),
    ("wasmJs", "Node.js", "current"): (26, 12, 0),
    ("wasmWasi", "Node.js", "minimum"): (24, 22, 0),
    ("wasmWasi", "Node.js", "current"): (26, 12, 0),
    ("wasmWasi", "Wasmtime", "minimum"): (37, 0, 3),
    ("wasmWasi", "Wasmtime", "current"): (49, 0, 3),
}
BUILD_FILES = (
    f"{CONSUMER}/settings.gradle.kts",
    f"{CONSUMER}/build.gradle.kts",
    f"{CONSUMER}/core/build.gradle.kts",
    f"{CONSUMER}/facade/build.gradle.kts",
)
TEAMCITY = re.compile(rb"^##teamcity\[(testSuiteStarted|testSuiteFinished|testStarted|testFinished|testFailed|testIgnored) name='((?:\|.|[^'])*)'(?: [^\r\n]*)?\]$")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode() + b"\n"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def git(repository, *args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C",
                                    str(repository), *args], stderr=subprocess.PIPE)


def lane_parts(lane):
    if lane not in LANES:
        raise ValueError(f"unapproved nonbrowser Wasm lane: {lane}")
    target, runtime, role, mode = lane.split(":")
    return target, runtime, role, mode


def variant_for(lane):
    return "wasm-js" if lane.startswith("wasmJs:") else "wasm-wasi"


def staged_binary(stage, module, variant):
    publication = f"{module}-{variant}"
    return (Path(stage) / GROUP.replace(".", "/") / publication / VERSION /
            f"{publication}-{VERSION}.klib")


def contract(repository, lane):
    lane_parts(lane)
    manifest = independent_gates.load_approved_manifest(repository)
    selected = independent_gates.consumer_contract(manifest, lane)
    cases = selected["cases"]
    if (len(cases) != 2523 or len({row["id"] for row in cases}) != 2523
            or sum(row["module"] == "dyn4k-core" for row in cases) != 2465
            or sum(row["module"] == "dyn4k" for row in cases) != 58
            or any(row["scope"] != "portable" for row in cases)):
        raise ValueError("approved portable selected method contract differs")
    return selected


def source_inventory(repository, candidate, lane, selected, require_live=False):
    target = lane_parts(lane)[0]
    roots = [f"{module}/src/commonTest/kotlin" for module in MODULES]
    roots.append(f"dyn4k-core/src/{target}Test/kotlin")
    tracked = sorted(path for path in git(repository, "ls-tree", "-r", "--name-only",
                                          candidate, "--", *roots).decode().splitlines()
                     if path.endswith(".kt"))
    live = sorted(path.relative_to(repository).as_posix() for root in roots
                  for path in (repository / root).rglob("*.kt") if path.is_file())
    if not tracked or (require_live and tracked != live):
        raise ValueError("original test source tree differs from candidate")
    inventory = {}
    for path in tracked:
        content = git(repository, "show", f"{candidate}:{path}")
        if require_live and (repository / path).read_bytes() != content:
            raise ValueError(f"original test source differs: {path}")
        inventory[path] = sha(content)
    for row in selected["cases"]:
        if inventory.get(row["source"]["path"]) != row["source"]["sha256"]:
            raise ValueError(f"approved method source differs: {row['id']}")
    return inventory


def input_bytes(repository, candidate, lane, require_live=False):
    selected = contract(repository, lane)
    inventory = source_inventory(repository, candidate, lane, selected, require_live)
    content = {
        "source-inventory.tsv": "".join(
            f"{path}\t{digest}\n" for path, digest in inventory.items()).encode(),
        "source-method-order.json": canonical([row["id"] for row in selected["cases"]]),
    }
    for module, short in (("dyn4k-core", "core"), ("dyn4k", "facade")):
        content[f"{short}-cases.tsv"] = "".join(
            f"{row['id']}\t{row['classname']}\t{row['method']}\n"
            for row in selected["cases"] if row["module"] == module).encode()
    return content


def selected_cases(raw):
    rows = [line.split("\t") for line in raw.decode().splitlines()]
    if (not rows or any(len(row) != 3 for row in rows)
            or len({tuple(row) for row in rows}) != len(rows)
            or len({row[0] for row in rows}) != len(rows)
            or len({(row[1], row[2]) for row in rows}) != len(rows)):
        raise ValueError("selected original method input differs")
    return {(row[1], row[2]): row[0] for row in rows}


def _unescape_name(value):
    result = bytearray()
    index = 0
    substitutions = {ord("n"): b"\n", ord("r"): b"\r", ord("'"): b"'",
                     ord("|"): b"|", ord("["): b"[", ord("]"): b"]"}
    while index < len(value):
        if value[index] == ord("|"):
            index += 1
            if index >= len(value) or value[index] not in substitutions:
                raise ValueError("invalid TeamCity name escape")
            result.extend(substitutions[value[index]])
        else:
            result.append(value[index])
        index += 1
    return result.decode("utf-8")


def parse_events(raw, selected):
    if not raw or not raw.endswith(b"\n"):
        raise ValueError("raw TeamCity event stream is missing or truncated")
    suites = []
    active = None
    observed = []
    for line in raw.splitlines():
        if not line.startswith(b"##teamcity["):
            continue
        event = TEAMCITY.fullmatch(line)
        if event is None:
            raise ValueError("malformed TeamCity event")
        kind, name = event.group(1).decode(), _unescape_name(event.group(2))
        if kind == "testSuiteStarted":
            if active is not None:
                raise ValueError("suite starts inside an active method")
            suites.append(name)
        elif kind == "testSuiteFinished":
            if not suites or suites.pop() != name or active is not None:
                raise ValueError("unbalanced TeamCity suite")
        elif kind == "testStarted":
            if len(suites) != 2 or active is not None:
                raise ValueError("unscoped or overlapping original method")
            key = (f"{suites[0]}.{suites[1]}", name)
            if key not in selected:
                raise ValueError("foreign original method event")
            active = key
        elif kind == "testFinished":
            if active is None or active[1] != name:
                raise ValueError("original method finish differs")
            observed.append(selected[active])
            active = None
        else:
            raise ValueError("failed or ignored original method")
    if active is not None or suites or not observed or len(set(observed)) != len(observed):
        raise ValueError("unfinished, empty, or duplicate original method stream")
    return observed


def normalized_xml(module, observed, selected):
    by_id = {identity: key for key, identity in selected.items()}
    suite = ET.Element("testsuite", {"name": module, "tests": str(len(observed)),
                                    "failures": "0", "errors": "0", "skipped": "0", "time": "0"})
    for identity in observed:
        classname, method = by_id[identity]
        ET.SubElement(suite, "testcase", {"id": identity, "classname": classname,
                                          "name": method, "time": "0"})
    return ET.tostring(suite, encoding="utf-8", xml_declaration=True)


def _version_tuple(text):
    value = re.search(r"(?:v|wasmtime )([0-9]+)\.([0-9]+)\.([0-9]+)", text)
    return tuple(map(int, value.groups())) if value else None


def runtime_preflight(lane, executable):
    target, runtime, role, _ = lane_parts(lane)
    executable = Path(executable)
    expected = ".".join(map(str, RUNTIME_PINS[(target, runtime, role)]))
    identity = {"expected_version": expected, "selected_path": str(executable)}
    if not executable.is_file() or executable.is_symlink():
        return {**identity, "status": "NOT_RUN",
                "reason": "selected runtime executable is absent"}
    command = [str(executable), "--version"]
    observed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, check=False)
    version = observed.stdout.strip()
    actual = _version_tuple(version)
    if observed.returncode or actual is None:
        return {**identity, "status": "FAILED", "reason": "selected runtime version probe failed"}
    if actual != RUNTIME_PINS[(target, runtime, role)]:
        return {**identity, "status": "FAILED", "reason": "selected runtime version differs from lane",
                "version": version}
    return {**identity, "status": "PASSED", "version": version,
            "sha256": sha(executable.read_bytes()), "path": str(executable.resolve())}


def _file_inventory(root):
    files = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("symbolic archive path")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            independent_gates._file_path_name(relative)
            files[relative] = {"sha256": sha(path.read_bytes()), "size": path.stat().st_size}
    return files


def archive_digest(root):
    files = _file_inventory(Path(root))
    if "receipt.json" not in files:
        raise ValueError("archive receipt is absent")
    return sha(canonical(files))


def _copy_bundle(source, destination):
    if not source.is_dir():
        raise ValueError(f"linked Wasm output is absent: {source}")
    if source.is_symlink() or any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("linked Wasm output contains a symbolic path")
    if destination.exists():
        raise ValueError("retained bundle destination is occupied")
    shutil.copytree(source, destination, symlinks=False)
    files = _file_inventory(destination)
    if not files or not any(name.endswith(".wasm") for name in files):
        raise ValueError("linked Wasm output has no binary")
    return files


def _module_name(short):
    return f"dyn4k-full-staged-wasm-node-consumer-{short}-test"


def _linked_directory(work, short, target, mode):
    kind = mode.capitalize()
    suffix = "optimized" if mode == "production" else "kotlin"
    return work / short / "compileSync" / target / "test" / f"test{kind}Executable" / suffix


def _execute(command, cwd, environment, stdout, stderr):
    started = time.time_ns()
    with stdout.open("wb") as out, stderr.open("wb") as err:
        process = subprocess.Popen(command, cwd=cwd, env=environment, stdout=out, stderr=err)
        code = process.wait()
    return {"command": command, "cwd": str(cwd), "pid": process.pid,
            "parent_pid": os.getpid(), "started_ns": started,
            "finished_ns": time.time_ns(), "exit_code": code,
            "stdout": stdout.as_posix(), "stderr": stderr.as_posix()}


def _relative_process(record, root):
    return {**record, "stdout": Path(record["stdout"]).relative_to(root).as_posix(),
            "stderr": Path(record["stderr"]).relative_to(root).as_posix()}


def _build_command(repository, stage, archive, work, inputs, gradle, lane, hashes):
    target, _, _, mode = lane_parts(lane)
    kind = mode.capitalize()
    optimize = "Optimize" if mode == "production" else ""
    task = f"compileTest{kind}ExecutableKotlin{target[0].upper() + target[1:]}{optimize}"
    return ([str(gradle), "-p", str(repository / CONSUMER),
             "--project-cache-dir", str(work / "gradle-project-cache"),
             "--offline", "--no-daemon", "--console=plain", "--rerun-tasks",
             f"-PqualificationCheckout={repository}", f"-PqualificationRepository={stage}",
             f"-PqualificationArchiveRoot={archive}", f"-PqualificationWorkRoot={work}",
             f"-PqualificationSourceInventory={inputs / 'source-inventory.tsv'}",
             f"-PqualificationCoreSha256={hashes['dyn4k-core']}",
             f"-PqualificationFacadeSha256={hashes['dyn4k']}",
             f"-PqualificationLaneId={lane}", "qualificationGraphs",
             f":core:{task}", f":facade:{task}"])


def run(repository, candidate, lane, stage, output, gradle, runtime, hashes):
    repository, stage, output, gradle, runtime = map(
        lambda value: Path(value).resolve(), (repository, stage, output, gradle, runtime))
    target, family, role, mode = lane_parts(lane)
    if output.is_relative_to(repository) or stage.is_relative_to(repository):
        raise ValueError("independent output and Maven stage must be outside source checkout")
    if output.exists() and any(output.iterdir()):
        raise ValueError("raw output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    if git(repository, "rev-parse", "HEAD").decode().strip() != candidate:
        raise ValueError("producer checkout head differs from candidate")
    if git(repository, "status", "--porcelain").strip():
        raise ValueError("producer requires an exact clean candidate checkout")
    preflight = runtime_preflight(lane, runtime)
    if preflight["status"] != "PASSED":
        status = {"candidate_sha": candidate, "lane": lane, **preflight}
        write_json(output / "status.json", status)
        return status
    if set(hashes) != set(MODULES) or any(not SHA256.fullmatch(value) for value in hashes.values()):
        raise ValueError("two independently audited staged hashes are required")
    for module in MODULES:
        if sha(staged_binary(stage, module, variant_for(lane)).read_bytes()) != hashes[module]:
            raise ValueError(f"staged {module} binary differs from independent hash")
    java_home = Path(os.environ["JAVA_HOME"]).resolve()
    gradle_home = Path(os.environ["GRADLE_USER_HOME"]).resolve()
    temp_root = Path(os.environ["TMPDIR"]).resolve()
    if not temp_root.is_dir() or not temp_root.is_relative_to(Path.home().resolve()):
        raise ValueError("TMPDIR must be an existing home-backed directory")
    java = java_home / "bin/java"
    java_version = subprocess.check_output([str(java), "-version"], stderr=subprocess.STDOUT,
                                           text=True).splitlines()[0]
    gradle_version = subprocess.check_output([str(gradle), "--version"], text=True)
    if 'version "21' not in java_version or "Gradle 9.5.0" not in gradle_version:
        raise ValueError("producer requires JDK 21 and Gradle 9.5.0")
    selected = contract(repository, lane)
    content = input_bytes(repository, candidate, lane, require_live=True)
    inputs = output / "inputs"
    inputs.mkdir()
    for name, data in content.items():
        (inputs / name).write_bytes(data)
    work = output.parent / f"{output.name}-build"
    if work.exists() and any(work.iterdir()):
        raise ValueError("external build directory must be empty")
    work.mkdir(parents=True, exist_ok=True)
    command = _build_command(repository, stage, output, work, inputs, gradle, lane, hashes)
    environment = os.environ.copy()
    environment["JAVA_HOME"] = str(java_home)
    environment["GRADLE_USER_HOME"] = str(gradle_home)
    environment["TMPDIR"] = str(temp_root)
    overall_start = time.time_ns()
    build = _execute(command, inputs, environment,
                     output / "gradle.stdout", output / "gradle.stderr")
    if build["exit_code"]:
        raise ValueError(f"external Wasm Gradle compilation exited {build['exit_code']}")
    graph = json.loads((output / "provider-graph.json").read_bytes())
    if not graph:
        raise ValueError("external provider graph is empty")
    runtimes = {}
    observed = []
    for module, short in (("dyn4k-core", "core"), ("dyn4k", "facade")):
        source = _linked_directory(work, short, target, mode)
        bundle = output / "runtime" / "bundle" / short
        _copy_bundle(source, bundle / "kotlin")
        name = _module_name(short)
        module_file = bundle / "kotlin" / f"{name}.mjs"
        wasm_file = bundle / "kotlin" / f"{name}.wasm"
        if not module_file.is_file() or not wasm_file.is_file():
            raise ValueError("linked test module or Wasm binary is missing")
        wrapper = bundle / "static" / "runUnitTests.mjs"
        wrapper.parent.mkdir(parents=True, exist_ok=True)
        wrapper.write_text(f"import * as tests from '../kotlin/{name}.mjs';\n"
                           "if (typeof tests.startUnitTests !== 'function') "
                           "throw new Error('test entry is absent');\n"
                           "tests.startUnitTests();\n")
        if family == "Node.js":
            execution = [str(runtime), str(wrapper)]
        else:
            execution = [str(runtime), "run", "-W", "gc=y", "-W", "exceptions=y",
                         "-W", "function-references=y", "--invoke", "startUnitTests",
                         str(wasm_file)]
        raw = output / "reports" / "raw" / short
        raw.mkdir(parents=True, exist_ok=True)
        record = _execute(execution, bundle, environment, raw / "stdout.log", raw / "stderr.log")
        if (sha(runtime.read_bytes()) != preflight["sha256"]
                or subprocess.check_output([str(runtime), "--version"], text=True).strip()
                != preflight["version"]):
            raise ValueError("selected runtime changed during original method execution")
        if record["exit_code"]:
            raise ValueError(f"{short} original Wasm tests exited {record['exit_code']}")
        selected_map = selected_cases(content[f"{short}-cases.tsv"])
        ids = parse_events((raw / "stdout.log").read_bytes(), selected_map)
        if set(ids) != set(selected_map.values()) or len(ids) != len(selected_map):
            raise ValueError(f"{short} full original method set is incomplete")
        observed.extend(ids)
        normalized = output / "reports" / "normalized" / short / "TEST-Wasm.xml"
        normalized.parent.mkdir(parents=True, exist_ok=True)
        normalized.write_bytes(normalized_xml(short, ids, selected_map))
        runtimes[short] = {**_relative_process(record, output), "executable_sha256": preflight["sha256"],
                           "version": preflight["version"],
                           "bundle_sha256": _file_inventory(bundle),
                           "linked_module_sha256": sha(module_file.read_bytes()),
                           "linked_wasm_sha256": sha(wasm_file.read_bytes())}
        write_json(output / "runtime" / f"{short}.json", runtimes[short])
    if len(observed) != 2523 or len(set(observed)) != 2523:
        raise ValueError("complete original method set is missing or duplicate")
    for path in BUILD_FILES:
        if (repository / path).read_bytes() != git(repository, "show", f"{candidate}:{path}"):
            raise ValueError(f"consumer build changed during capture: {path}")
    producer_path = "tools/qualification/full_wasm_node_consumer.py"
    if (repository / producer_path).read_bytes() != git(repository, "show", f"{candidate}:{producer_path}"):
        raise ValueError("producer changed during capture")
    overall_finish = time.time_ns()
    process = {**_relative_process(build, output), "started_ns": overall_start,
               "finished_ns": overall_finish}
    receipt = {"schema": "full-staged-wasm-node/1", "status": "PASSED",
               "candidate_sha": candidate, "source_tree": git(repository, "rev-parse",
                   f"{candidate}^{{tree}}").decode().strip(), "lane": lane,
               "target": target, "runtime": family, "version": role, "configuration": mode,
               "consumer_group": "full-suite", "consumer_contract_sha256": independent_gates.digest(selected),
               "source_inventory_sha256": sha(content["source-inventory.tsv"]),
               "source_method_order_sha256": sha(content["source-method-order.json"]),
               "artifact_hashes": hashes, "provider_graph": "provider-graph.json",
               "resolved_artifacts": {module: f"resolved/{module}-{variant_for(lane)}-{VERSION}.klib"
                                      for module in MODULES},
               "consumer_xml": [f"reports/normalized/{short}/TEST-Wasm.xml"
                                for short in ("core", "facade")],
               "raw_events": [f"reports/raw/{short}/stdout.log" for short in ("core", "facade")],
               "consumer_build_sha256": {path: sha(git(repository, "show", f"{candidate}:{path}"))
                                         for path in BUILD_FILES},
               "producer_sha256": sha(git(repository, "show", f"{candidate}:{producer_path}")),
               "toolchain": {"java_home": str(java_home), "java_version": java_version,
                             "java_sha256": sha(java.read_bytes()), "gradle_version": "Gradle 9.5.0",
                             "gradle_sha256": sha(gradle.read_bytes()), "gradle_user_home": str(gradle_home),
                             "kgp_version": "2.4.20"},
               "runtime_identity": {"family": family, "role": role, "version": preflight["version"],
                                    "sha256": preflight["sha256"], "path": preflight["path"],
                                    "host": f"{platform.system()} {platform.release()} {platform.machine()}"},
               "producer_paths": {"checkout": str(repository), "staging": str(stage),
                                  "archive_root": str(output), "work_root": str(work),
                                  "inputs": str(inputs), "gradle": str(gradle)},
               "process": process, "runtime_processes": {short: f"runtime/{short}.json"
                                                       for short in ("core", "facade")}}
    receipt["files"] = [{"path": path, **value} for path, value in sorted(_file_inventory(output).items())]
    write_json(output / "receipt.json", receipt)
    return receipt


def verify(root, repository, candidate, lane, hashes, expected_digest, runtime_binary=None,
           replay=False):
    root, repository = Path(root), Path(repository)
    selected = contract(repository, lane)
    if not SHA256.fullmatch(str(expected_digest)) or archive_digest(root) != expected_digest:
        raise ValueError("independent archive digest differs")
    receipt = json.loads((root / "receipt.json").read_bytes())
    if (receipt.get("schema") != "full-staged-wasm-node/1" or receipt.get("status") != "PASSED"
            or receipt.get("candidate_sha") != candidate or receipt.get("lane") != lane
            or receipt.get("consumer_group") != "full-suite"
            or receipt.get("consumer_contract_sha256") != independent_gates.digest(selected)
            or receipt.get("artifact_hashes") != hashes):
        raise ValueError("receipt differs from exact approved candidate and lane")
    current = _file_inventory(root)
    listed = receipt.get("files")
    if (not isinstance(listed, list) or {item["path"]: {"sha256": item["sha256"],
                                                         "size": item["size"]} for item in listed}
            != {key: value for key, value in current.items() if key != "receipt.json"}):
        raise ValueError("raw archive file inventory differs")
    content = input_bytes(repository, candidate, lane)
    if any((root / "inputs" / name).read_bytes() != value for name, value in content.items()):
        raise ValueError("original source or method order differs")
    if (receipt.get("source_inventory_sha256") != sha(content["source-inventory.tsv"])
            or receipt.get("source_method_order_sha256") != sha(content["source-method-order.json"])
            or receipt.get("source_tree") != git(repository, "rev-parse", f"{candidate}^{{tree}}").decode().strip()):
        raise ValueError("exact source identity differs")
    expected_build = {path: sha(git(repository, "show", f"{candidate}:{path}")) for path in BUILD_FILES}
    if (receipt.get("consumer_build_sha256") != expected_build
            or receipt.get("producer_sha256") != sha(git(repository, "show",
                f"{candidate}:tools/qualification/full_wasm_node_consumer.py"))):
        raise ValueError("candidate consumer or producer source differs")
    for path in (*BUILD_FILES, "tools/qualification/full_wasm_node_consumer.py"):
        if (repository / path).read_bytes() != git(repository, "show", f"{candidate}:{path}"):
            raise ValueError("local verifier or consumer differs from exact candidate")
    target, family, role, mode = lane_parts(lane)
    if {key: receipt.get(key) for key in ("target", "runtime", "version", "configuration")} != {
            "target": target, "runtime": family, "version": role, "configuration": mode}:
        raise ValueError("receipt route fields differ")
    identity = receipt.get("runtime_identity")
    if not isinstance(identity, dict) or identity.get("family") != family or identity.get("role") != role:
        raise ValueError("runtime identity differs from lane")
    if runtime_binary is None:
        raise ValueError("independently selected runtime executable is required")
    if (not SHA256.fullmatch(str(identity.get("sha256")))
            or not isinstance(identity.get("path"), str)
            or not Path(identity["path"]).is_absolute()):
        raise ValueError("selected runtime process identity is incomplete")
    if runtime_binary is not None:
        runtime_check = runtime_preflight(lane, Path(runtime_binary))
        if (runtime_check.get("status") != "PASSED" or runtime_check.get("sha256") != identity.get("sha256")
                or runtime_check.get("version") != identity.get("version")):
            raise ValueError("independently selected runtime bytes differ")
    paths = receipt.get("producer_paths")
    if (not isinstance(paths, dict) or set(paths) != {"checkout", "staging", "archive_root",
                                                    "work_root", "inputs", "gradle"}
            or any(not isinstance(value, str) or not Path(value).is_absolute()
                   for value in paths.values())
            or Path(paths["archive_root"]).is_relative_to(Path(paths["checkout"]))):
        raise ValueError("external producer paths differ")
    graph = json.loads((root / "provider-graph.json").read_bytes())
    if set(graph) != {"compile", "runtime", "gradle_user_home"}:
        raise ValueError("provider graph phases differ")
    toolchain = receipt.get("toolchain")
    if (not isinstance(toolchain, dict) or toolchain.get("kgp_version") != "2.4.20"
            or toolchain.get("gradle_version") != "Gradle 9.5.0"
            or not str(toolchain.get("java_version", "")).startswith('openjdk version "21.')
            or graph["gradle_user_home"] != toolchain.get("gradle_user_home")):
        raise ValueError("pinned producer toolchain differs")
    variant = variant_for(lane)
    roots = {f"{GROUP}:{module}:{VERSION}" for module in MODULES}
    variants = {f"{GROUP}:{module}-{variant}:{VERSION}" for module in MODULES}
    for phase in ("compile", "runtime"):
        entries = graph[phase]
        if len(entries) != 2 or {entry["project"] for entry in entries} != {"core", "facade"}:
            raise ValueError("provider graph omits a consumer module")
        for entry in entries:
            if entry["configuration"] != f"{target}Test{phase.capitalize()}Classpath":
                raise ValueError("provider configuration differs")
            projects = {value for value in entry["components"] if value.startswith("project ")}
            if projects != {f"project :{entry['project']}"}:
                raise ValueError("source project replaced a staged provider")
            if {value for value in entry["components"] if value.startswith(f"{GROUP}:")} != roots | variants:
                raise ValueError("provider graph contains a missing or foreign GAV")
            artifacts = [item for item in entry["artifacts"] if item["component"].startswith(f"{GROUP}:")]
            if len(artifacts) != 2 or {item["component"] for item in artifacts} != variants:
                raise ValueError("provider graph contains missing or duplicate binaries")
            for module in MODULES:
                item = next(value for value in artifacts if value["component"] ==
                            f"{GROUP}:{module}-{variant}:{VERSION}")
                path = Path(item["file"])
                expected_name = f"{module}-{variant}-{VERSION}.klib"
                if (item["sha256"] != hashes[module] or not path.is_absolute()
                        or not (path.is_relative_to(Path(paths["staging"]))
                                or path.is_relative_to(Path(graph["gradle_user_home"]) / "caches/modules-2"))
                        or item["name"] != expected_name):
                    raise ValueError("resolved staged provider hash differs")
    for module in MODULES:
        artifact = root / receipt["resolved_artifacts"][module]
        if sha(artifact.read_bytes()) != hashes[module]:
            raise ValueError("resolved staged binary differs")
    process = receipt.get("process")
    if (not isinstance(process, dict) or process.get("exit_code") != 0
            or type(process.get("pid")) is not int or process["pid"] <= 0
            or type(process.get("parent_pid")) is not int or process["parent_pid"] <= 0
            or type(process.get("started_ns")) is not int
            or type(process.get("finished_ns")) is not int
            or process["started_ns"] >= process["finished_ns"]):
        raise ValueError("Gradle process proof is incomplete")
    output = (root / process["stdout"]).read_text()
    if (f"QUALIFICATION_LANE={lane}" not in output
            or f"QUALIFICATION_PROVIDER_GRAPH_SHA256={sha((root / 'provider-graph.json').read_bytes())}" not in output
            or "BUILD SUCCESSFUL" not in output):
        raise ValueError("raw Gradle output omits provider proof")
    original = _build_command(Path(paths["checkout"]), Path(paths["staging"]),
                              Path(paths["archive_root"]), Path(paths["work_root"]),
                              Path(paths["inputs"]), Path(paths["gradle"]), lane, hashes)
    if process.get("command") != original or process.get("cwd") != paths["inputs"]:
        raise ValueError("Gradle command differs from route")
    if any(f"> Task {task}" not in output for task in original[-2:]):
        raise ValueError("raw Gradle output omits a linked Wasm test task")
    if (receipt.get("consumer_xml") != [f"reports/normalized/{short}/TEST-Wasm.xml"
                                        for short in ("core", "facade")]
            or receipt.get("raw_events") != [f"reports/raw/{short}/stdout.log"
                                            for short in ("core", "facade")]
            or receipt.get("runtime_processes") != {short: f"runtime/{short}.json"
                                                    for short in ("core", "facade")}):
        raise ValueError("full original runtime or method report inventory differs")
    expected_ids = {row["id"] for row in selected["cases"]}
    observed = []
    for short in ("core", "facade"):
        selected_map = selected_cases(content[f"{short}-cases.tsv"])
        raw = root / "reports" / "raw" / short / "stdout.log"
        ids = parse_events(raw.read_bytes(), selected_map)
        if set(ids) != set(selected_map.values()) or len(ids) != len(selected_map):
            raise ValueError("original Wasm method outcomes are incomplete")
        observed.extend(ids)
        normal = root / "reports" / "normalized" / short / "TEST-Wasm.xml"
        if normal.read_bytes() != normalized_xml(short, ids, selected_map):
            raise ValueError("normalized XML differs from raw method order")
        runtime = json.loads((root / "runtime" / f"{short}.json").read_bytes())
        bundle = root / "runtime" / "bundle" / short
        actual_bundle = _file_inventory(bundle)
        if runtime.get("bundle_sha256") != actual_bundle:
            raise ValueError("linked bundle inventory differs")
        name = _module_name(short)
        linked = bundle / "kotlin" / f"{name}.mjs"
        wasm = bundle / "kotlin" / f"{name}.wasm"
        wrapper = bundle / "static" / "runUnitTests.mjs"
        if (not linked.is_file() or not wasm.is_file() or not wrapper.is_file()
                or runtime.get("linked_module_sha256") != sha(linked.read_bytes())
                or runtime.get("linked_wasm_sha256") != sha(wasm.read_bytes())
                or wasm.name not in linked.read_text()
                or linked.name not in wrapper.read_text()):
            raise ValueError("executed Wasm module bytes differ")
        original_bundle = Path(paths["archive_root"]) / "runtime" / "bundle" / short
        original_wrapper = original_bundle / "static" / "runUnitTests.mjs"
        original_wasm = original_bundle / "kotlin" / f"{name}.wasm"
        original_command = ([identity["path"], str(original_wrapper)] if family == "Node.js" else
                            [identity["path"], "run", "-W", "gc=y", "-W", "exceptions=y",
                             "-W", "function-references=y", "--invoke", "startUnitTests", str(original_wasm)])
        if (runtime.get("command") != original_command or runtime.get("exit_code") != 0
                or runtime.get("cwd") != str(original_bundle)
                or runtime.get("stdout") != f"reports/raw/{short}/stdout.log"
                or runtime.get("stderr") != f"reports/raw/{short}/stderr.log"
                or runtime.get("executable_sha256") != identity["sha256"]
                or runtime.get("version") != identity["version"]
                or type(runtime.get("pid")) is not int or runtime["pid"] <= 0
                or not process["started_ns"] <= runtime.get("started_ns", -1)
                <= runtime.get("finished_ns", -1) <= process["finished_ns"]):
            raise ValueError("executed runtime process differs")
        if replay:
            if runtime_binary is None:
                raise ValueError("public runtime replay needs an independently selected binary")
            external = Path(runtime_binary).resolve()
            replay_command = ([str(external), str(wrapper)] if family == "Node.js" else
                              [str(external), *original_command[1:-1], str(wasm)])
            replay_result = subprocess.run(replay_command, cwd=bundle, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, check=False)
            if replay_result.returncode or parse_events(replay_result.stdout, selected_map) != ids:
                raise ValueError("transported Wasm bundle changed method outcomes")
    if len(observed) != 2523 or set(observed) != expected_ids:
        raise ValueError("complete original Wasm suite differs from approved manifest")
    return {"status": "PASSED", "candidate_sha": candidate, "lane": lane,
            "selected_methods": 2523, "core_methods": 2465, "facade_methods": 58,
            "archive_digest": expected_digest}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    produce, replay = sub.add_parser("run"), sub.add_parser("verify")
    for command in (produce, replay):
        command.add_argument("--repository", type=Path, required=True)
        command.add_argument("--candidate-sha", required=True)
        command.add_argument("--lane", choices=sorted(LANES), required=True)
        command.add_argument("--expected-core-sha256", required=True)
        command.add_argument("--expected-facade-sha256", required=True)
    for name in ("staging", "output", "gradle", "runtime"):
        produce.add_argument(f"--{name}", type=Path, required=True)
    replay.add_argument("--archive", type=Path, required=True)
    replay.add_argument("--expected-archive-digest", required=True)
    replay.add_argument("--runtime", type=Path)
    replay.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    hashes = {"dyn4k-core": args.expected_core_sha256,
              "dyn4k": args.expected_facade_sha256}
    try:
        if args.action == "run":
            result = run(args.repository, args.candidate_sha, args.lane, args.staging,
                         args.output, args.gradle, args.runtime, hashes)
        else:
            result = verify(args.archive, args.repository, args.candidate_sha, args.lane,
                            hashes, args.expected_archive_digest, args.runtime, args.replay)
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError, TypeError) as error:
        result = {"status": "FAILED", "reason": str(error), "lane": args.lane}
        if args.action == "run" and args.output.is_dir():
            write_json(args.output / "failure.json", result)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASSED" else 2 if result["status"] == "NOT_RUN" else 1


if __name__ == "__main__":
    sys.exit(main())
