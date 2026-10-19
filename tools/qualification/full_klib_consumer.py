#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import independent_gates


CONSUMER = "consumers/qualification/portable/full-klib"
MODULES = ("dyn4k-core", "dyn4k")
GROUP = "io.github.rubixhacker"
VERSION = "0.1.0-alpha.1"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
LOCAL_LANES = {
    "linuxX64:Linux x64:current:debug-g": ("linuxX64", "linuxx64"),
    "js:Node.js:current:development": ("js", "js"),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def git(repository, *args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C",
                                    str(repository), *args], stderr=subprocess.PIPE)


def contract(repository, lane):
    manifest = independent_gates.load_approved_manifest(repository)
    selected = independent_gates.consumer_contract(manifest, lane)
    cases = selected["cases"]
    if (len(cases) != 2523 or len({item["id"] for item in cases}) != 2523
            or sum(item["module"] == "dyn4k-core" for item in cases) != 2465
            or sum(item["module"] == "dyn4k" for item in cases) != 58
            or any(item["scope"] != "portable" for item in cases)):
        raise ValueError("approved portable selected method contract differs")
    return manifest, selected


def sources(repository, candidate, lane, cases):
    platform_root = "nativeTest" if lane.startswith("linuxX64:") else "jsTest"
    roots = tuple(f"{module}/src/commonTest/kotlin" for module in MODULES) + (
        f"dyn4k-core/src/{platform_root}/kotlin",)
    tracked = sorted(path for path in git(repository, "ls-tree", "-r", "--name-only",
                                          candidate, "--", *roots).decode().splitlines()
                     if path.endswith(".kt"))
    live = sorted(path.relative_to(repository).as_posix() for root in roots
                  for path in (repository / root).rglob("*.kt") if path.is_file())
    if tracked != live or len(tracked) != len(set(tracked)):
        raise ValueError("original common test source tree differs from candidate")
    result = {}
    for path in tracked:
        original = git(repository, "show", f"{candidate}:{path}")
        if (repository / path).read_bytes() != original:
            raise ValueError(f"original test source differs: {path}")
        result[path] = sha(original)
    for item in cases:
        source = item["source"]
        if result.get(source["path"]) != source["sha256"]:
            raise ValueError(f"approved method source differs: {item['id']}")
    return result


def input_bytes(repository, candidate, lane):
    _, selected = contract(repository, lane)
    inventory = sources(repository, candidate, lane, selected["cases"])
    by_module = {module: sorted((item for item in selected["cases"]
                                 if item["module"] == module), key=lambda item: item["id"])
                 for module in MODULES}
    content = {
        "source-inventory.tsv": "".join(f"{path}\t{digest}\n"
                                        for path, digest in sorted(inventory.items())).encode(),
        "core-cases.tsv": "".join(f"{item['id']}\t{item['classname']}\t{item['method']}\n"
                                  for item in by_module["dyn4k-core"]).encode(),
        "facade-cases.tsv": "".join(f"{item['id']}\t{item['classname']}\t{item['method']}\n"
                                    for item in by_module["dyn4k"]).encode(),
        "lane-script": ("gradle.settingsEvaluated { settings ->\n"
                        "  if (settings.rootProject.name != 'dyn4k-full-staged-klib-consumer') {\n"
                        "    throw new GradleException('qualification project differs')\n"
                        "  }\n"
                        "}\n").encode(),
    }
    return content


def prepare(repository, candidate, lane, destination):
    repository, destination = Path(repository).resolve(), Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("KLIB input directory must be empty")
    content = input_bytes(repository, candidate, lane)
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in content.items():
        (destination / name).write_bytes(data)
    return {"lane": lane, "source_count": len(content["source-inventory.tsv"].splitlines()),
            "selected_cases": 2523}


def staged_binary(staging, module, variant):
    name = f"{module}-{variant}-{VERSION}.klib"
    return staging / GROUP.replace(".", "/") / f"{module}-{variant}" / VERSION / name


def _selected_cases(path):
    rows = [line.split("\t") for line in path.read_text().splitlines()]
    if any(len(row) != 3 for row in rows) or len(rows) != len(set(map(tuple, rows))):
        raise ValueError("selected method input differs")
    return {(row[1], row[2]): row[0] for row in rows}


def _report(raw, target, selected):
    root = ET.fromstring(raw)
    if root.tag != "testsuite":
        raise ValueError("native raw XML root differs")
    cases = list(root.iter("testcase"))
    counts = {"tests": len(cases), "failures": sum(c.find("failure") is not None for c in cases),
              "errors": sum(c.find("error") is not None for c in cases),
              "skipped": sum(c.find("skipped") is not None for c in cases)}
    if (any(int(root.get(key, "-1")) != value for key, value in counts.items())
            or any(counts[key] for key in ("failures", "errors", "skipped"))):
        raise ValueError("native raw XML records missing or failing methods")
    observed = []
    for case in cases:
        classname, method = case.get("classname", ""), case.get("name", "")
        prefix, suffix = f"{target}Test.", f"[{target}]"
        if not classname.startswith(prefix) or not method.endswith(suffix):
            raise ValueError("native raw case identity differs")
        identity = selected.get((classname[len(prefix):], method[:-len(suffix)]))
        if identity is None:
            raise ValueError("native raw case is foreign")
        observed.append(identity)
        case.set("id", identity)
    return observed, ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _tap(raw, selected):
    text = raw.decode()
    if not text.startswith("TAP version 13\n") or re.search(r"(?m)^\s*not ok ", text):
        raise ValueError("Node TAP is missing or failing")
    summary = {key: re.findall(rf"(?m)^# {key} (\d+)$", text)
               for key in ("tests", "pass", "fail", "skipped", "cancelled", "todo")}
    if (any(len(value) != 1 for value in summary.values())
            or any(summary[key][0] != "0" for key in ("fail", "skipped", "cancelled", "todo"))
            or summary["tests"] != summary["pass"]):
        raise ValueError("Node TAP summary differs")
    package = classname = None
    observed = []
    passed = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.fullmatch(r"( *)(?:# Subtest:|ok \d+ -) (.+)", line)
        if not match:
            continue
        depth, name = len(match[1]), match[2]
        if line.lstrip().startswith("# Subtest:"):
            if depth == 0:
                package = name
            elif depth == 4:
                classname = f"{package}.{name}" if package else name
            elif depth == 8:
                if not classname:
                    raise ValueError("Node TAP method has no class")
                identity = selected.get((classname, name))
                if identity is None:
                    raise ValueError("Node TAP has a foreign original method")
                observed.append((classname, name, identity))
        elif depth == 8:
            identity = selected.get((classname, name))
            if identity is None:
                raise ValueError("Node TAP has a foreign passing row")
            remaining = lines[index + 1:]
            end = next((offset for offset, value in enumerate(remaining)
                        if value.strip() == "..."), None)
            if end is None:
                raise ValueError("Node TAP passing row lacks raw duration")
            duration = next((re.fullmatch(r"\s*duration_ms: ([0-9]+(?:\.[0-9]+)?)",
                                          value).group(1)
                             for value in remaining[:end]
                             if re.fullmatch(r"\s*duration_ms: ([0-9]+(?:\.[0-9]+)?)", value)), None)
            if duration is None:
                raise ValueError("Node TAP passing row lacks raw duration")
            passed.append((classname, name, identity, float(duration) / 1000))
    if (len(observed) != int(summary["tests"][0]) or len(passed) != len(observed)
            or [(item[0], item[1], item[2]) for item in passed] != observed
            or len({item[2] for item in observed}) != len(observed)):
        raise ValueError("Node TAP method rows differ from summary")
    suite = ET.Element("testsuite", {"name": "Node.js", "tests": str(len(observed)),
                                     "failures": "0", "errors": "0", "skipped": "0", "time": "0"})
    for classname, method, identity, seconds in passed:
        ET.SubElement(suite, "testcase", {"classname": classname, "name": method,
                                          "id": identity, "time": str(seconds)})
    return [item[2] for item in observed], ET.tostring(
        suite, encoding="utf-8", xml_declaration=True)


def capture(repository, project, archive, work_root, lane, node, inputs):
    repository, project, archive, work_root = map(Path, (repository, project, archive, work_root))
    target, _ = LOCAL_LANES[lane]
    observed = []
    for module, short in (("dyn4k-core", "core"), ("dyn4k", "facade")):
        selected = _selected_cases(inputs[f"{short}-cases.tsv"])
        raw_root = archive / "reports/raw" / short
        normal_root = archive / "reports/normalized" / short
        raw_root.mkdir(parents=True, exist_ok=True)
        normal_root.mkdir(parents=True, exist_ok=True)
        if target == "linuxX64":
            source = work_root / short / "test-results/linuxX64Test"
            reports = sorted(source.glob("TEST-*.xml"))
            if not reports:
                raise ValueError("native external XML is absent")
            for report in reports:
                raw = report.read_bytes()
                ids, normal = _report(raw, target, selected)
                (raw_root / report.name).write_bytes(raw)
                (normal_root / report.name).write_bytes(normal)
                observed.extend(ids)
            executable = work_root / short / "bin/linuxX64/debugTest/test.kexe"
            if not executable.is_file():
                raise ValueError("native external test executable is absent")
            runtime = {"module": short, "command": [str(executable)],
                       "executable_sha256": sha(executable.read_bytes())}
            program = executable
        else:
            built = work_root / short / "compileSync/js/test/testDevelopmentExecutable/kotlin"
            scripts = sorted(built.glob(f"dyn4k-full-staged-klib-consumer-{short}-test.js"))
            if len(scripts) != 1:
                raise ValueError("Node external test program is absent or ambiguous")
            preload = project / "node-test-preload.cjs"
            command = [str(node), "--test", "--test-reporter=tap", "--require",
                       str(preload), str(scripts[0])]
            started = time.time_ns()
            process = subprocess.Popen(command, cwd=project, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            node_stdout, node_stderr = process.communicate()
            finished = time.time_ns()
            (raw_root / "node.tap").write_bytes(node_stdout)
            (raw_root / "node.stderr").write_bytes(node_stderr)
            if process.returncode:
                raise ValueError(f"Node original tests exited {process.returncode}")
            ids, normal = _tap(node_stdout, selected)
            (normal_root / "TEST-Node.xml").write_bytes(normal)
            observed.extend(ids)
            bundle_root = archive / "runtime/bundle" / short
            bundle = {}
            for source_file in sorted(built.rglob("*")):
                if source_file.is_symlink():
                    raise ValueError("generated Node test bundle contains a symbolic path")
                if source_file.is_file():
                    relative = source_file.relative_to(built).as_posix()
                    target_file = bundle_root / relative
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source_file, target_file)
                    bundle[relative] = sha(target_file.read_bytes())
            runtime = {"module": short, "command": command, "exit_code": process.returncode,
                       "pid": process.pid, "parent_pid": os.getpid(),
                       "started_ns": started, "finished_ns": finished,
                       "node_version": subprocess.check_output([str(node), "--version"], text=True).strip(),
                       "node_sha256": sha(Path(node).read_bytes()),
                       "program_sha256": sha(scripts[0].read_bytes()),
                       "preload_sha256": sha(preload.read_bytes()),
                       "bundle_sha256": bundle}
            program = scripts[0]
        program_copy = archive / f"runtime/{short}.program"
        program_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(program, program_copy)
        print(f"QUALIFICATION_RUNTIME_{short.upper()}_PROGRAM_SHA256={sha(program_copy.read_bytes())}")
        path = archive / f"runtime/{short}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded(runtime) + b"\n")
        print(f"QUALIFICATION_RUNTIME_{short.upper()}_SHA256={sha(path.read_bytes())}")
    if len(observed) != 2523 or len(set(observed)) != 2523:
        raise ValueError("full original method set is missing or duplicate")
    for name, source in inputs.items():
        path = archive / "inputs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, path)
        print(f"QUALIFICATION_{name.upper().replace('-', '_').replace('.', '_')}_SHA256={sha(path.read_bytes())}")
    for relative in sorted((archive / "reports/normalized").rglob("TEST-*.xml")):
        print(f"QUALIFICATION_CONSUMER_XML_SHA256={sha(relative.read_bytes())}")
    for relative in sorted((archive / "reports/raw").rglob("TEST-*.xml")):
        print(f"QUALIFICATION_RAW_XML_SHA256={sha(relative.read_bytes())}")
    for relative in sorted((archive / "reports/raw").rglob("node.tap")):
        print(f"QUALIFICATION_RAW_TAP_SHA256={sha(relative.read_bytes())}")
    print(f"QUALIFICATION_CASE_COUNT={len(observed)}")


def run(repository, candidate, lane, staging, output, gradle, node, hashes):
    repository, staging, output, gradle, node = map(
        lambda path: Path(path).resolve(), (repository, staging, output, gradle, node))
    if lane not in LOCAL_LANES:
        raise ValueError("local full KLIB process route is not implemented for lane")
    if output.is_relative_to(repository) or staging == repository / "build/staging-repository":
        raise ValueError("external archive or staged binary path aliases source build")
    if git(repository, "rev-parse", "HEAD").decode().strip() != candidate:
        raise ValueError("producer checkout head differs from candidate")
    if git(repository, "status", "--porcelain").strip():
        raise ValueError("producer requires an exact clean candidate checkout")
    if output.exists() and any(output.iterdir()):
        raise ValueError("raw output directory must be empty")
    java_home = Path(os.environ["JAVA_HOME"]).resolve()
    gradle_home = Path(os.environ["GRADLE_USER_HOME"]).resolve()
    java_lines = subprocess.check_output([str(java_home / "bin/java"), "-version"],
                                         stderr=subprocess.STDOUT, text=True).splitlines()
    java_version = next((line for line in java_lines if 'version "21' in line), "")
    gradle_version = subprocess.check_output([str(gradle), "--version"], text=True)
    if 'version "21' not in java_version or "Gradle 9.5.0" not in gradle_version:
        raise ValueError("producer requires pinned JDK 21 and Gradle 9.5.0")
    manifest, selected = contract(repository, lane)
    variant = LOCAL_LANES[lane][1]
    native_identity = None
    if variant == "linuxx64":
        konan_root = Path(os.environ.get("KONAN_DATA_DIR", str(Path.home() / ".konan")))
        native_home = konan_root / "kotlin-native-prebuilt-linux-x86_64-2.4.20"
        native_executable = native_home / "bin/kotlinc-native"
        native_compiler = native_home / "konan/lib/kotlin-native-compiler-embeddable.jar"
        native_lines = subprocess.check_output([str(native_executable), "-version"],
                                               stderr=subprocess.STDOUT, text=True).splitlines()
        native_version = "\n".join(line for line in native_lines
                                   if line.startswith(("info: kotlinc-native", "Kotlin/Native:")))
        if "Kotlin/Native: 2.4.20" not in native_version:
            raise ValueError("Kotlin/Native compiler version differs from pinned toolchain")
        native_identity = {"home": str(native_home), "version": native_version,
                           "executable_sha256": sha(native_executable.read_bytes()),
                           "compiler_sha256": sha(native_compiler.read_bytes())}
    for module in MODULES:
        if sha(staged_binary(staging, module, variant).read_bytes()) != hashes[module]:
            raise ValueError(f"independently selected staged {module} KLIB differs")
    inputs = output.parent / f"{output.name}-inputs"
    prepare(repository, candidate, lane, inputs)
    output.mkdir(parents=True, exist_ok=True)
    work_root = output.parent / f"{output.name}-build"
    work_root.mkdir(parents=True, exist_ok=True)
    command = [str(gradle), "-p", str(repository / CONSUMER),
               "--project-cache-dir", str(work_root / "gradle-project-cache"),
               "--offline", "--no-daemon",
               "--console=plain", "--rerun-tasks", "--init-script", str(inputs / "lane-script"),
               f"-PqualificationCheckout={repository}",
               f"-PqualificationRepository={staging}",
               f"-PqualificationArchiveRoot={output}",
               f"-PqualificationWorkRoot={work_root}",
               f"-PqualificationSourceInventory={inputs / 'source-inventory.tsv'}",
               f"-PqualificationCoreCases={inputs / 'core-cases.tsv'}",
               f"-PqualificationFacadeCases={inputs / 'facade-cases.tsv'}",
               f"-PqualificationCoreSha256={hashes['dyn4k-core']}",
               f"-PqualificationFacadeSha256={hashes['dyn4k']}",
               f"-PqualificationLaneId={lane}",
               f"-PqualificationLaneScript={inputs / 'lane-script'}",
               f"-PqualificationNode={node}", "qualificationEvidence", lane]
    started = time.time_ns()
    with (output / "stdout.txt").open("wb") as stdout, (output / "stderr.txt").open("wb") as stderr:
        result = subprocess.Popen(command, cwd=inputs, stdout=stdout, stderr=stderr)
        exit_code = result.wait()
    finished = time.time_ns()
    for log in ("stdout.txt", "stderr.txt"):
        os.utime(output / log, ns=(finished, finished))
    if exit_code:
        raise ValueError(f"external full KLIB Gradle process exited {exit_code}")
    lane_info = manifest["lanes"][lane]
    runtime_identity = (f"{platform.system()} {platform.release()} {platform.machine()} | "
                        f"{java_version} | {subprocess.check_output([str(node), '--version'], text=True).strip()}")
    raw_xml = sorted(path.relative_to(output).as_posix() for path in
                     (output / "reports/raw").rglob("TEST-*.xml"))
    normal_xml = sorted(path.relative_to(output).as_posix() for path in
                        (output / "reports/normalized").rglob("TEST-*.xml"))
    receipt = {"schema": 1, "status": "PASSED", "candidate_sha": candidate,
               "source_tree": git(repository, "rev-parse", f"{candidate}^{{tree}}").decode().strip(),
               "lane": lane, **{key: lane_info[key] for key in
                                ("target", "runtime", "version", "configuration")},
               "runtime_identity": runtime_identity, "artifact_hashes": hashes,
               "consumer_group": "full-suite",
               "consumer_contract_sha256": independent_gates.digest(selected),
               "source_inventory_sha256": sha((inputs / "source-inventory.tsv").read_bytes()),
               "producer_paths": {"checkout": str(repository), "staging": str(staging),
                                  "archive_root": str(output), "inputs": str(inputs),
                                  "work_root": str(work_root), "gradle": str(gradle),
                                  "node": str(node)},
               "toolchain": {"java_home": str(java_home), "java_version": java_version,
                             "java_sha256": sha((java_home / "bin/java").read_bytes()),
                             "gradle_version": "Gradle 9.5.0",
                             "gradle_sha256": sha(gradle.read_bytes()),
                             "node_version": subprocess.check_output([str(node), "--version"], text=True).strip(),
                             "node_sha256": sha(node.read_bytes()),
                             "gradle_user_home": str(gradle_home), "kgp_version": "2.4.20",
                             "kotlin_native": native_identity},
               "process": {"command": command, "cwd": str(inputs), "exit_code": 0,
                           "pid": result.pid, "parent_pid": os.getpid(),
                           "started_ns": started, "finished_ns": finished,
                           "stdout": "stdout.txt", "stderr": "stderr.txt"},
               "provider_graph": "provider-graph.json",
               "resolved_artifacts": {module: f"resolved/{module}-{variant}-{VERSION}.klib"
                                      for module in MODULES},
               "consumer_xml": normal_xml, "raw_consumer_xml": raw_xml,
               "raw_consumer_tap": sorted(path.relative_to(output).as_posix() for path in
                                          (output / "reports/raw").rglob("node.tap")),
               "consumer_build_sha256": {path: sha(git(repository, "show", f"{candidate}:{path}"))
                                         for path in (f"{CONSUMER}/build.gradle.kts",
                                                      f"{CONSUMER}/settings.gradle.kts",
                                                      f"{CONSUMER}/core/build.gradle.kts",
                                                      f"{CONSUMER}/facade/build.gradle.kts",
                                                      f"{CONSUMER}/node-test-preload.cjs",
                                                      f"{CONSUMER}/linuxX64/Linux x64/current/build.gradle.kts",
                                                      f"{CONSUMER}/js/Node.js/current/build.gradle.kts")},
               "producer_sha256": sha(git(repository, "show",
                                           f"{candidate}:tools/qualification/full_klib_consumer.py")),
               "files": [{"path": path.relative_to(output).as_posix(),
                          "sha256": sha(path.read_bytes()), "mtime_ns": path.stat().st_mtime_ns}
                         for path in sorted(output.rglob("*")) if path.is_file()]}
    (output / "receipt.json").write_bytes(encoded(receipt) + b"\n")
    return receipt


def verify(root, repository, candidate, lane, hashes, runtime_identity,
           archive_digest, trusted_toolchain, replay_node=None):
    root, repository = Path(root), Path(repository).resolve()
    if lane not in LOCAL_LANES or not root.is_dir() or root.is_symlink():
        raise ValueError("full KLIB lane or archive is absent")
    receipt = json.loads((root / "receipt.json").read_bytes())
    manifest, selected = contract(repository, lane)
    if (receipt.get("candidate_sha") != candidate or receipt.get("lane") != lane
            or receipt.get("consumer_contract_sha256") != independent_gates.digest(selected)
            or receipt.get("consumer_group") != "full-suite"):
        raise ValueError("receipt differs from exact approved portable contract")
    inputs = input_bytes(repository, candidate, lane)
    for name, data in inputs.items():
        if (root / "inputs" / name).read_bytes() != data:
            raise ValueError(f"archived original input differs: {name}")
    if receipt.get("source_inventory_sha256") != sha(inputs["source-inventory.tsv"]):
        raise ValueError("receipt original source inventory differs")
    builds = (f"{CONSUMER}/build.gradle.kts", f"{CONSUMER}/settings.gradle.kts",
              f"{CONSUMER}/core/build.gradle.kts", f"{CONSUMER}/facade/build.gradle.kts",
              f"{CONSUMER}/node-test-preload.cjs",
              f"{CONSUMER}/linuxX64/Linux x64/current/build.gradle.kts",
              f"{CONSUMER}/js/Node.js/current/build.gradle.kts")
    if receipt.get("consumer_build_sha256") != {
            path: sha(git(repository, "show", f"{candidate}:{path}")) for path in builds}:
        raise ValueError("external consumer build differs from exact source")
    if receipt.get("producer_sha256") != sha(git(
            repository, "show", f"{candidate}:tools/qualification/full_klib_consumer.py")):
        raise ValueError("external producer differs from exact source")
    if receipt.get("toolchain") != trusted_toolchain:
        raise ValueError("producer toolchain differs from independent runner identity")
    paths, process = receipt.get("producer_paths"), receipt.get("process")
    if not isinstance(paths, dict) or not isinstance(process, dict):
        raise ValueError("producer path or process record is missing")
    if (set(paths) != {"checkout", "staging", "archive_root", "inputs", "work_root",
                       "gradle", "node"}
            or any(not isinstance(value, str) or not Path(value).is_absolute()
                   for value in paths.values())
            or any(Path(paths[key]).is_relative_to(Path(paths["checkout"]))
                   for key in ("archive_root", "inputs", "work_root"))):
        raise ValueError("external consumer path aliases source checkout")
    expected_command = [paths["gradle"], "-p", f"{paths['checkout']}/{CONSUMER}",
                        "--project-cache-dir", f"{paths['work_root']}/gradle-project-cache",
                        "--offline", "--no-daemon", "--console=plain", "--rerun-tasks",
                        "--init-script", f"{paths['inputs']}/lane-script",
                        f"-PqualificationCheckout={paths['checkout']}",
                        f"-PqualificationRepository={paths['staging']}",
                        f"-PqualificationArchiveRoot={paths['archive_root']}",
                        f"-PqualificationWorkRoot={paths['work_root']}",
                        f"-PqualificationSourceInventory={paths['inputs']}/source-inventory.tsv",
                        f"-PqualificationCoreCases={paths['inputs']}/core-cases.tsv",
                        f"-PqualificationFacadeCases={paths['inputs']}/facade-cases.tsv",
                        f"-PqualificationCoreSha256={hashes['dyn4k-core']}",
                        f"-PqualificationFacadeSha256={hashes['dyn4k']}",
                        f"-PqualificationLaneId={lane}",
                        f"-PqualificationLaneScript={paths['inputs']}/lane-script",
                        f"-PqualificationNode={paths['node']}", "qualificationEvidence", lane]
    if process.get("command") != expected_command or process.get("cwd") != paths["inputs"]:
        raise ValueError("external process command differs from selected lane")
    if (type(process.get("pid")) is not int or process["pid"] <= 0
            or type(process.get("parent_pid")) is not int or process["parent_pid"] <= 0):
        raise ValueError("external Gradle process identity is absent")
    output_lines = (root / "stdout.txt").read_text().splitlines()
    if ("QUALIFICATION_CASE_COUNT=2523" not in output_lines
            or f"QUALIFICATION_LANE={lane}" not in output_lines
            or f"QUALIFICATION_SOURCE_INVENTORY_TSV_SHA256={sha(inputs['source-inventory.tsv'])}"
            not in output_lines):
        raise ValueError("raw process output does not bind full original sources and methods")
    tasks = ((":core:linuxX64Test", ":facade:linuxX64Test") if lane.startswith("linuxX64:")
             else (":core:compileTestDevelopmentExecutableKotlinJs",
                   ":facade:compileTestDevelopmentExecutableKotlinJs"))
    if any(not any(line.startswith(f"> Task {task}") for line in output_lines)
           for task in tasks):
        raise ValueError("raw process output omits a required external runtime task")
    variant = LOCAL_LANES[lane][1]
    graph = json.loads((root / "provider-graph.json").read_bytes())
    if (set(graph) != {"compile", "runtime", "gradle_user_home"}
            or graph["gradle_user_home"] != trusted_toolchain["gradle_user_home"]):
        raise ValueError("provider phases are incomplete")
    for phase in ("compile", "runtime"):
        entries = graph[phase]
        if len(entries) != 2 or {entry["project"] for entry in entries} != {"core", "facade"}:
            raise ValueError("both publication provider graphs are required")
        for entry in entries:
            expected_configuration = ("linuxX64TestCompileKlibraries" if variant == "linuxx64"
                                      else "jsTestCompileClasspath" if phase == "compile"
                                      else "jsTestRuntimeClasspath")
            if entry["configuration"] != expected_configuration or any(
                    value.startswith("project ") for value in entry["components"]):
                raise ValueError("external provider used a project or wrong configuration")
            components = {value for value in entry["components"]
                          if value.startswith(f"{GROUP}:")}
            roots = {f"{GROUP}:{module}:{VERSION}" for module in MODULES}
            variants = {f"{GROUP}:{module}-{variant}:{VERSION}" for module in MODULES}
            if components != roots | variants:
                raise ValueError("external provider graph has foreign or missing source")
            artifacts = [item for item in entry["artifacts"]
                         if item["component"].startswith(f"{GROUP}:")]
            if {item["component"] for item in artifacts} != variants or len(artifacts) != 2:
                raise ValueError("external provider graph has source or duplicate binaries")
            for module in MODULES:
                item = next(value for value in artifacts
                            if value["component"] == f"{GROUP}:{module}-{variant}:{VERSION}")
                staged = staged_binary(Path(paths["staging"]), module, variant)
                copied = root / receipt["resolved_artifacts"][module]
                artifact_path = Path(item["file"])
                cache = Path(trusted_toolchain["gradle_user_home"]) / "caches/modules-2"
                if (item["sha256"] != hashes[module] or sha(copied.read_bytes()) != hashes[module]
                        or not artifact_path.is_absolute()
                        or not (artifact_path == staged or artifact_path.is_relative_to(cache))
                        or item["size"] != copied.stat().st_size
                        or (staged.name != item["name"] and
                            not item["name"].lower().startswith(f"{module}-{variant}"))):
                    raise ValueError("resolved external KLIB differs from staged publication")
    expected = {item["id"] for item in selected["cases"]}
    observed = []
    raw_paths = receipt.get("raw_consumer_xml", [])
    normal_paths = receipt.get("consumer_xml", [])
    tap_paths = receipt.get("raw_consumer_tap", [])
    for relative in raw_paths + normal_paths + tap_paths:
        independent_gates._file_path_name(relative)
    if any(not re.fullmatch(r"reports/raw/(core|facade)/TEST-[^/]+\.xml", path)
           for path in raw_paths):
        raise ValueError("native original report path differs")
    if variant == "linuxx64":
        if (tap_paths or {Path(path).parts[2] for path in raw_paths} != {"core", "facade"}
                or set(normal_paths) != {
                    str(Path("reports/normalized") / Path(path).parts[2] / Path(path).parts[3])
                    for path in raw_paths}):
            raise ValueError("native original and normalized report inventories differ")
    elif (raw_paths or set(tap_paths) != {
            "reports/raw/core/node.tap", "reports/raw/facade/node.tap"}
            or set(normal_paths) != {"reports/normalized/core/TEST-Node.xml",
                                      "reports/normalized/facade/TEST-Node.xml"}):
        raise ValueError("Node original and normalized report inventories differ")
    for normal in normal_paths:
        suite = ET.fromstring((root / normal).read_bytes())
        for case in suite.iter("testcase"):
            observed.append(case.get("id"))
    if len(observed) != len(expected) or set(observed) != expected:
        raise ValueError("normalized full KLIB method IDs differ from approved manifest")
    for raw in raw_paths:
        parts = Path(raw).parts
        normal = root / "reports/normalized" / parts[2] / parts[3]
        selected_map = _selected_cases(root / "inputs" /
                                       ("core-cases.tsv" if parts[2] == "core"
                                        else "facade-cases.tsv"))
        ids, expected_normal = _report((root / raw).read_bytes(), "linuxX64", selected_map)
        if normal.read_bytes() != expected_normal or not ids:
            raise ValueError("normalized native XML is not derived from raw assertions")
        if f"QUALIFICATION_RAW_XML_SHA256={sha((root / raw).read_bytes())}" not in output_lines:
            raise ValueError("raw Native XML is not bound to the process output")
    for tap in tap_paths:
        parts = Path(tap).parts
        normal = root / "reports/normalized" / parts[2] / "TEST-Node.xml"
        selected_map = _selected_cases(root / "inputs" /
                                       ("core-cases.tsv" if parts[2] == "core"
                                        else "facade-cases.tsv"))
        ids, expected_normal = _tap((root / tap).read_bytes(), selected_map)
        if normal.read_bytes() != expected_normal or not ids:
            raise ValueError("normalized Node XML is not derived from raw TAP")
        if f"QUALIFICATION_RAW_TAP_SHA256={sha((root / tap).read_bytes())}" not in output_lines:
            raise ValueError("raw Node TAP is not bound to the process output")
    if not raw_paths and not receipt.get("raw_consumer_tap"):
        raise ValueError("original native XML or Node TAP is absent")
    for short in ("core", "facade"):
        runtime = json.loads((root / f"runtime/{short}.json").read_bytes())
        program = root / f"runtime/{short}.program"
        if runtime.get("module") != short:
            raise ValueError("external runtime module differs")
        if (f"QUALIFICATION_RUNTIME_{short.upper()}_SHA256="
                f"{sha((root / f'runtime/{short}.json').read_bytes())}" not in output_lines
                or f"QUALIFICATION_RUNTIME_{short.upper()}_PROGRAM_SHA256="
                f"{sha(program.read_bytes())}" not in output_lines):
            raise ValueError("external runtime program is not bound to process output")
        if variant == "linuxx64":
            if (runtime.get("executable_sha256") != sha(program.read_bytes())
                    or runtime.get("command") != [
                        f"{paths['work_root']}/{short}/bin/linuxX64/debugTest/test.kexe"]):
                raise ValueError("native runtime process differs from linked executable")
        else:
            expected_program = (f"{paths['work_root']}/{short}/compileSync/js/test/"
                                f"testDevelopmentExecutable/kotlin/"
                                f"dyn4k-full-staged-klib-consumer-{short}-test.js")
            bundle_root = root / "runtime/bundle" / short
            bundle = {path.relative_to(bundle_root).as_posix(): sha(path.read_bytes())
                      for path in bundle_root.rglob("*") if path.is_file() and not path.is_symlink()}
            program_name = f"dyn4k-full-staged-klib-consumer-{short}-test.js"
            expected_node_command = [paths["node"], "--test", "--test-reporter=tap",
                                     "--require", f"{paths['checkout']}/{CONSUMER}/node-test-preload.cjs",
                                     expected_program]
            if (runtime.get("command") != expected_node_command
                    or runtime.get("exit_code") != 0
                    or runtime.get("node_sha256") != trusted_toolchain["node_sha256"]
                    or runtime.get("node_version") != trusted_toolchain["node_version"]
                    or runtime.get("program_sha256") != sha(program.read_bytes())
                    or runtime.get("bundle_sha256") != bundle
                    or bundle.get(program_name) != runtime.get("program_sha256")
                    or runtime.get("preload_sha256") != receipt["consumer_build_sha256"][
                        f"{CONSUMER}/node-test-preload.cjs"]
                    or type(runtime.get("pid")) is not int or runtime["pid"] <= 0
                    or type(runtime.get("parent_pid")) is not int or runtime["parent_pid"] <= 0
                    or not process["started_ns"] <= runtime.get("started_ns", -1)
                    <= runtime.get("finished_ns", -1) <= process["finished_ns"]):
                raise ValueError("Node runtime process differs from linked test program")
            if replay_node is not None:
                node_file = Path(replay_node).resolve()
                if sha(node_file.read_bytes()) != trusted_toolchain["node_sha256"]:
                    raise ValueError("replay Node binary differs from independent identity")
                replay_command = [str(node_file), "--test", "--test-reporter=tap",
                                  "--require", str(repository / CONSUMER / "node-test-preload.cjs"),
                                  str(bundle_root / program_name)]
                replay = subprocess.run(replay_command, cwd=bundle_root,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        check=False)
                if replay.returncode:
                    raise ValueError("transported Node test bundle failed public replay")
                selected_map = _selected_cases(root / "inputs" / f"{short}-cases.tsv")
                replay_ids, _ = _tap(replay.stdout, selected_map)
                if set(replay_ids) != set(selected_map.values()):
                    raise ValueError("transported Node test bundle changes original method outcomes")
    allowed = {item["path"] for item in receipt["files"]} | {"receipt.json"}
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual != allowed:
        raise ValueError("KLIB archive has unlisted files")
    gate = independent_gates.evaluate_gate(
        "staged-consumer", root, candidate, lane, manifest["lanes"][lane], repository,
        hashes, runtime_identity, archive_digest, manifest=manifest)
    if gate["status"] != "PASSED" or gate.get("complete_selected_suite") is not True:
        raise ValueError(f"independent staged consumer gate failed: {gate['reason']}")
    return gate


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--repository", required=True)
    prep.add_argument("--candidate-sha", required=True)
    prep.add_argument("--lane", required=True)
    prep.add_argument("--destination", required=True)
    capture_parser = sub.add_parser("capture")
    for name in ("repository", "project", "archive", "work-root", "lane", "node",
                 "source-inventory", "core-cases", "facade-cases", "lane-script"):
        capture_parser.add_argument(f"--{name}", required=True)
    produce = sub.add_parser("run")
    replay = sub.add_parser("verify")
    for route in (produce, replay):
        route.add_argument("--repository", required=True)
        route.add_argument("--candidate-sha", required=True)
        route.add_argument("--lane", required=True)
        route.add_argument("--expected-core-sha256", required=True)
        route.add_argument("--expected-facade-sha256", required=True)
    for name in ("staging", "output", "gradle", "node"):
        produce.add_argument(f"--{name}", required=True)
    for name in ("archive", "runtime-identity", "expected-archive-digest",
                 "trusted-toolchain"):
        replay.add_argument(f"--{name}", required=True)
    replay.add_argument("--replay-node")
    args = parser.parse_args()
    if args.action == "prepare":
        result = prepare(args.repository, args.candidate_sha, args.lane, args.destination)
    elif args.action == "capture":
        capture(args.repository, args.project, args.archive, args.work_root, args.lane,
                args.node, {name: Path(getattr(args, name.replace("-", "_")))
                            for name in ("source-inventory", "core-cases", "facade-cases",
                                         "lane-script")})
        return
    else:
        hashes = {"dyn4k-core": args.expected_core_sha256,
                  "dyn4k": args.expected_facade_sha256}
        if any(not SHA256.fullmatch(value) for value in hashes.values()):
            parser.error("independent staged KLIB hashes are required")
        if args.action == "run":
            result = run(args.repository, args.candidate_sha, args.lane, args.staging,
                         args.output, args.gradle, args.node, hashes)
        else:
            trusted = json.loads(Path(args.trusted_toolchain).read_bytes())
            result = verify(args.archive, args.repository, args.candidate_sha, args.lane,
                            hashes, args.runtime_identity, args.expected_archive_digest,
                            trusted, args.replay_node)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
