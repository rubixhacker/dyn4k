#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import independent_gates


CONSUMER = "consumers/qualification/portable/full-browser"
MODULES = ("dyn4k-core", "dyn4k")
VERSION = "0.1.0-alpha.1"
JAVA_SHA256 = "2a207f5e7d075afa01d97f8048389a64432a44c4a5af0f5e77d6e286ec5f401d"
GRADLE_SHA256 = "b88b6fc9f41fba7bf456a3f8255ee5b7c6c379202ca13f68c3feecebcbc7bd8b"
CHROMIUM = {
    "minimum": (119, "c81049295247b6892c802dcad33dcab0a0337fce31800f923f51bdb0c07e6d11"),
    "current": (155, "b866a2964538c825538c454de4867973b926650da57ec12dc3328807d768247b"),
}
LANES = {f"js:Chromium:{role}:{mode}" for role in CHROMIUM
         for mode in ("development", "production")}
SOURCE_ROOTS = ("dyn4k-core/src/commonTest/kotlin", "dyn4k/src/commonTest/kotlin",
                "dyn4k-core/src/jsTest/kotlin")
BUILD_PATHS = tuple(f"{CONSUMER}/{name}" for name in
                    ("settings.gradle.kts", "build.gradle.kts", "core/build.gradle.kts",
                     "facade/build.gradle.kts"))
LAUNCHER = "tools/qualification/browser_wasi/browser_launcher.py"
REPORTER = f"{CONSUMER}/browser-reporter.js"
YARN_LOCK = f"{CONSUMER}/consumer-yarn.lock"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def git(repository, *args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C",
                                    str(repository), *args], stderr=subprocess.PIPE)


def original(repository, candidate, path):
    return git(repository, "show", f"{candidate}:{path}")


def contract(repository, lane):
    if lane not in LANES:
        raise ValueError("unsupported full browser lane")
    manifest = independent_gates.load_approved_manifest(repository)
    selected = independent_gates.consumer_contract(manifest, lane)
    cases = selected["cases"]
    if (len(cases) != 2523 or len({item["id"] for item in cases}) != 2523
            or sum(item["module"] == "dyn4k-core" for item in cases) != 2465
            or sum(item["module"] == "dyn4k" for item in cases) != 58
            or any(item["scope"] != "portable" for item in cases)):
        raise ValueError("approved portable method contract differs")
    return selected


def source_inventory(repository, candidate, cases):
    tracked = sorted(path for path in git(repository, "ls-tree", "-r", "--name-only",
                                          candidate, "--", *SOURCE_ROOTS).decode().splitlines()
                     if path.endswith(".kt"))
    live = sorted(path.relative_to(repository).as_posix() for root in SOURCE_ROOTS
                  for path in (repository / root).rglob("*.kt") if path.is_file())
    if tracked != live or len(tracked) != len(set(tracked)):
        raise ValueError("original test source tree differs from candidate")
    result = {}
    for path in tracked:
        raw = original(repository, candidate, path)
        if (repository / path).read_bytes() != raw:
            raise ValueError(f"original test source differs: {path}")
        result[path] = sha(raw)
    for case in cases:
        if result.get(case["source"]["path"]) != case["source"]["sha256"]:
            raise ValueError(f"approved original method source differs: {case['id']}")
    return result


def input_bytes(repository, candidate, lane):
    selected = contract(repository, lane)
    inventory = source_inventory(repository, candidate, selected["cases"])
    by_module = {module: sorted((item for item in selected["cases"]
                                 if item["module"] == module), key=lambda item: item["id"])
                 for module in MODULES}
    return {
        "source-inventory.tsv": "".join(f"{path}\t{digest}\n"
                                        for path, digest in sorted(inventory.items())).encode(),
        "core-cases.tsv": "".join(f"{item['id']}\t{item['classname']}\t{item['method']}\n"
                                  for item in by_module["dyn4k-core"]).encode(),
        "facade-cases.tsv": "".join(f"{item['id']}\t{item['classname']}\t{item['method']}\n"
                                    for item in by_module["dyn4k"]).encode(),
        "consumer-yarn.lock": original(repository, candidate, YARN_LOCK),
    }


def staged(staging, module):
    return staging / "io/github/rubixhacker" / f"{module}-js" / VERSION / f"{module}-js-{VERSION}.klib"


def rows(xml, expected, major):
    suite = ET.fromstring(xml)
    if suite.tag != "testsuite" or not suite.get("name", "").startswith("jsBrowserTest."):
        raise ValueError("original browser XML suite identity differs")
    cases = suite.findall("testcase")
    counts = {key: sum(case.find(tag) is not None for case in cases)
              for key, tag in (("failures", "failure"), ("errors", "error"),
                               ("skipped", "skipped"))}
    if (int(suite.get("tests", "-1")) != len(cases) or len(cases) == 0
            or any(int(suite.get(key, "-1")) != value or value for key, value in counts.items())):
        raise ValueError("original browser XML has missing, skipped, or failing rows")
    observed = []
    suffix = re.compile(r"\[js, browser, ChromeHeadless" + str(major)
                        + r"(?:\.\d+)+, Linux(?:\d+\.)+\d+\]$")
    for case in cases:
        classname = case.get("classname", "")
        method = case.get("name", "")
        match = suffix.search(method)
        if not classname.startswith("jsBrowserTest.") or match is None:
            raise ValueError("original browser row has wrong runtime or task")
        key = (classname.removeprefix("jsBrowserTest."), method[:match.start()])
        identity = expected.get(key)
        if identity is None:
            raise ValueError("original browser row is foreign")
        observed.append(identity)
    if len(observed) != len(set(observed)):
        raise ValueError("original browser XML duplicates a method")
    return observed


def selected_map(data):
    lines = [line.split("\t") for line in data.decode().splitlines()]
    if any(len(line) != 3 for line in lines) or len(lines) != len(set(map(tuple, lines))):
        raise ValueError("selected case input differs")
    return {(line[1], line[2]): line[0] for line in lines}


def karma_rows(raw, expected, major):
    active_suite = None
    active_method = None
    observed = []
    flow = None
    starts = finishes = 0
    for line in raw.decode().splitlines():
        item = json.loads(line)
        message = item["message"]
        if set(item) != {"sha256", "message"} or item["sha256"] != sha(message.encode()):
            raise ValueError("original Karma message bytes differ")
        if message.startswith("##teamcity[testSuiteStarted"):
            match = re.fullmatch(
                rf"##teamcity\[testSuiteStarted name='(.+)\.Chrome Headless "
                rf"{major}(?:\.\d+)+ \(Linux (?:\d+\.)+\d+\)' flowId='([^']+)'\]",
                message)
            if match is None or active_suite is not None or active_method is not None:
                raise ValueError("original Karma suite start differs")
            parts = match[1].split(" ", 1)
            if len(parts) != 2:
                raise ValueError("original Karma class identity differs")
            active_suite = (f"{parts[0]}.{parts[1]}", message.split(" name='", 1)[1].split("' flowId=", 1)[0])
            if flow is None:
                flow = match[2]
            elif flow != match[2]:
                raise ValueError("original Karma flow differs")
        elif message.startswith("##teamcity[testSuiteFinished"):
            match = re.fullmatch(
                r"##teamcity\[testSuiteFinished name='([^']+)' duration='(?:\d*|%s)' flowId='([^']+)'\]",
                message)
            if (match is None or active_suite is None or active_method is not None
                    or match[1] != active_suite[1] or match[2] != flow):
                raise ValueError("original Karma suite finish differs")
            active_suite = None
        elif message.startswith("##teamcity[testStarted"):
            match = re.fullmatch(
                r"##teamcity\[testStarted name='([^']+)' captureStandardOutput='true' flowId='([^']+)'\]",
                message)
            if (match is None or active_suite is None or active_method is not None
                    or match[2] != flow):
                raise ValueError("original Karma method start differs")
            identity = expected.get((active_suite[0], match[1]))
            if identity is None:
                raise ValueError("original Karma method is foreign")
            active_method = (match[1], identity)
            observed.append(identity)
            starts += 1
        elif message.startswith("##teamcity[testFinished"):
            match = re.fullmatch(
                r"##teamcity\[testFinished name='([^']+)' duration='\d*' flowId='([^']+)'\]",
                message)
            if (match is None or active_method is None or match[1] != active_method[0]
                    or match[2] != flow):
                raise ValueError("original Karma method finish differs")
            active_method = None
            finishes += 1
        elif message.startswith(("##teamcity[testFailed", "##teamcity[testIgnored")):
            raise ValueError("original Karma method failed or skipped")
        elif message.startswith("##teamcity[testStdOut") and active_method is None:
            raise ValueError("original Karma diagnostic has no method")
    if (active_suite is not None or active_method is not None
            or starts != finishes or len(observed) != len(expected)
            or len(observed) != len(set(observed)) or set(observed) != set(expected.values())):
        raise ValueError("original Karma method stream is incomplete or duplicate")
    return observed


def file_hash(path):
    return sha(path.read_bytes())


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return file_hash(target)


def toolchain(gradle, browser):
    java_home = Path(os.environ["JAVA_HOME"]).resolve()
    java = java_home / "bin/java"
    java_version = subprocess.check_output([str(java), "-version"],
                                           stderr=subprocess.STDOUT, text=True).splitlines()[0]
    gradle_version = subprocess.check_output([str(gradle), "--version"], text=True)
    browser_version = subprocess.check_output([str(browser), "--version"], text=True).strip()
    if ('version "21' not in java_version or "Gradle 9.5.0" not in gradle_version
            or "Chrome" not in browser_version or file_hash(java) != JAVA_SHA256
            or file_hash(gradle) != GRADLE_SHA256):
        raise ValueError("pinned toolchain version differs")
    return {"java_home": str(java_home), "java_version": java_version,
            "java_sha256": file_hash(java), "gradle": str(gradle),
            "gradle_sha256": file_hash(gradle), "gradle_version": "9.5.0",
            "kgp_version": "2.4.20", "browser": str(browser),
            "browser_sha256": file_hash(browser), "browser_version": browser_version,
            "gradle_user_home": str(Path(os.environ["GRADLE_USER_HOME"]).resolve())}


def process(command, cwd, env, stdout, stderr):
    started = time.time_ns()
    with stdout.open("wb") as out, stderr.open("wb") as err:
        child = subprocess.Popen(command, cwd=cwd, env=env, stdout=out, stderr=err)
        code = child.wait()
    finished = time.time_ns()
    return {"command": command, "cwd": str(cwd), "pid": child.pid,
            "parent_pid": os.getpid(), "exit_code": code,
            "started_ns": started, "finished_ns": finished,
            "stdout": stdout.name, "stderr": stderr.name}


def gradle_args(repository, staging, archive, work, inputs, lane, hashes, gradle):
    args = [str(gradle), "-p", str(repository / CONSUMER), "--project-cache-dir",
            str(work / "gradle-project-cache"), "--offline", "--no-daemon",
            "--console=plain", "--rerun-tasks",
            f"-PqualificationCheckout={repository}", f"-PqualificationRepository={staging}",
            f"-PqualificationArchiveRoot={archive}", f"-PqualificationWorkRoot={work}",
            f"-PqualificationSourceInventory={inputs / 'source-inventory.tsv'}",
            f"-PqualificationCoreSha256={hashes['dyn4k-core']}",
            f"-PqualificationFacadeSha256={hashes['dyn4k']}",
            f"-PqualificationLaneId={lane}"]
    if lane.endswith(":production"):
        args.append("-PqualificationProduction=true")
    return args


def run(repository, candidate, lane, staging, output, gradle, browser, hashes):
    repository, staging, output, gradle, browser = map(
        lambda value: Path(value).resolve(), (repository, staging, output, gradle, browser))
    if lane not in LANES or not HEX40.fullmatch(candidate):
        raise ValueError("selected full browser lane or candidate differs")
    if git(repository, "rev-parse", "HEAD").decode().strip() != candidate:
        raise ValueError("producer checkout differs from candidate")
    if git(repository, "status", "--porcelain").strip():
        raise ValueError("producer requires a clean exact candidate checkout")
    if output.is_relative_to(repository) or staging.is_relative_to(repository):
        raise ValueError("external archive or staged provider aliases checkout")
    if output.exists() and any(output.iterdir()):
        raise ValueError("raw browser output directory must be empty")
    role = lane.split(":")[2]
    major, browser_sha = CHROMIUM[role]
    identity = toolchain(gradle, browser)
    if identity["browser_sha256"] != browser_sha or not re.search(
            rf"\b{major}\.", identity["browser_version"]):
        raise ValueError("wrong pinned Chromium binary")
    for module in MODULES:
        if file_hash(staged(staging, module)) != hashes[module]:
            raise ValueError(f"independent staged {module} JS KLIB hash differs")
    inputs_content = input_bytes(repository, candidate, lane)
    run_started = time.time_ns()
    inputs = output.parent / f"{output.name}-inputs"
    if inputs.exists() and any(inputs.iterdir()):
        raise ValueError("original source input directory is not empty")
    inputs.mkdir(parents=True, exist_ok=True)
    for name, data in inputs_content.items():
        (inputs / name).write_bytes(data)
    project_lock = repository / CONSUMER / "kotlin-js-store/yarn.lock"
    if project_lock.is_symlink() or project_lock.parent.is_symlink():
        raise ValueError("external consumer lock path is symbolic")
    if project_lock.exists() and project_lock.read_bytes() != inputs_content["consumer-yarn.lock"]:
        raise ValueError("external consumer lock differs from pinned fixture")
    project_lock.parent.mkdir(parents=True, exist_ok=True)
    project_lock.write_bytes(inputs_content["consumer-yarn.lock"])
    output.mkdir(parents=True, exist_ok=True)
    work = output.parent / f"{output.name}-build"
    work.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, JAVA_HOME=str(Path(os.environ["JAVA_HOME"]).resolve()),
               YARN_OFFLINE="true", DYN4K_BROWSER="chromium",
               CHROME_BIN=str(repository / LAUNCHER),
               DYN4K_BROWSER_SELECTED_BINARY=str(browser),
               DYN4K_BROWSER_RUNTIME="chromium")
    base = gradle_args(repository, staging, output, work, inputs, lane, hashes, gradle)
    graph_process = process(base + ["qualificationGraphs"], inputs, env,
                            output / "graph.stdout", output / "graph.stderr")
    if graph_process["exit_code"]:
        raise ValueError("external JS provider graph process failed")
    config_roots = []
    processes = {}
    module_rows = {}
    try:
        for module, short in (("dyn4k-core", "core"), ("dyn4k", "facade")):
            config_root = repository / CONSUMER / short / "karma.config.d"
            if config_root.exists():
                raise ValueError("consumer Karma configuration is already present")
            config_root.mkdir()
            config_roots.append(config_root)
            reporter = config_root / "qualification-browser-reporter.js"
            port_file = config_root / "qualification-port.js"
            reporter.write_bytes((repository / REPORTER).read_bytes())
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            port_file.write_text(f"config.set({{port: {port}}});\n")
            destination = output / short
            destination.mkdir()
            token = sha(os.urandom(32))
            launches = destination / "browser-launches.jsonl"
            attestation = destination / "reporter-producer.json"
            raw_karma = destination / "raw-karma.jsonl"
            module_env = dict(env, DYN4K_BROWSER_ATTESTATION=str(launches),
                              DYN4K_BROWSER_TOKEN=token,
                              DYN4K_BROWSER_REPORTER_ATTESTATION=str(attestation),
                              DYN4K_BROWSER_RAW_KARMA=str(raw_karma),
                              DYN4K_BROWSER_REPORTER_SOURCE=str(reporter))
            command = base + [f":{short}:jsBrowserTest"]
            execution = process(command, inputs, module_env,
                                destination / "gradle.stdout", destination / "gradle.stderr")
            processes[short] = {**execution, "browser_token": token, "karma_port": port}
            if execution["exit_code"]:
                raise ValueError(f"external {short} Chromium process failed")
            xml_root = work / short / "test-results/jsBrowserTest"
            reports = sorted(xml_root.glob("TEST-*.xml"))
            if not reports:
                raise ValueError(f"external {short} browser XML is absent")
            selected = selected_map(inputs_content[f"{short}-cases.tsv"])
            observed = []
            for report in reports:
                raw = report.read_bytes()
                observed.extend(rows(raw, selected, major))
                copy(report, destination / "xml" / report.name)
            if len(observed) != len(selected) or set(observed) != set(selected.values()):
                raise ValueError(f"external {short} full original method set is incomplete")
            karma_rows(raw_karma.read_bytes(), selected, major)
            module_rows[short] = observed
            package = f"dyn4k-full-staged-browser-consumer-{short}-test"
            configuration = lane.rsplit(":", 1)[1]
            mode = configuration.capitalize()
            linked = work / short / "compileSync/js/test" / f"test{mode}Executable" / "kotlin" / f"{package}.js"
            if not linked.is_file():
                raise ValueError(f"external {short} linked {configuration} bundle is absent")
            processes[short]["linked_sha256"] = copy(linked, destination / "linked-executable.js")
            generated = work / "root/js/packages" / package / "karma.conf.js"
            if (not generated.is_file()
                    or f"config.set({{port: {port}}});" not in generated.read_text()
                    or "DYN4K_BROWSER_RAW_KARMA" not in generated.read_text()):
                raise ValueError("external browser Karma configuration lacks isolated port")
            copy(generated, destination / "karma.conf.js")
            if not launches.is_file() or not attestation.is_file() or not raw_karma.is_file():
                raise ValueError("real browser process or reporter producer is absent")
            copy(reporter, destination / "browser-reporter.js")
            if json.loads(attestation.read_text()) != {
                    "path": str(reporter), "sha256": file_hash(reporter),
                    "producer_path": str(work / "root/js/node_modules/kotlin-web-helpers/dist/karma-kotlin-reporter.js"),
                    "producer_sha256": "7c3232f60952aff254847ae62a866385735e3094197454d755100e962c2f2347"}:
                raise ValueError("Karma reporter producer identity differs")
            observations = [json.loads(line) for line in launches.read_text().splitlines()]
            if not observations or any(item != {
                    "token": token, "runtime": "chromium", "selected_binary": str(browser),
                    "selected_sha256": browser_sha, "process_executable": str(browser),
                    "process_sha256": browser_sha, "pid": item.get("pid")}
                    or type(item.get("pid")) is not int or item["pid"] <= 0
                    for item in observations):
                raise ValueError("actual pinned Chromium process image differs")
    finally:
        for config_root in config_roots:
            for name in ("qualification-port.js", "qualification-browser-reporter.js"):
                path = config_root / name
                if path.exists():
                    path.unlink()
            if config_root.exists() and not any(config_root.iterdir()):
                config_root.rmdir()
        if project_lock.exists() and project_lock.read_bytes() == inputs_content["consumer-yarn.lock"]:
            project_lock.unlink()
        if project_lock.parent.exists() and not any(project_lock.parent.iterdir()):
            project_lock.parent.rmdir()
    all_rows = module_rows.get("core", []) + module_rows.get("facade", [])
    if len(all_rows) != 2523 or len(set(all_rows)) != 2523:
        raise ValueError("full 2,523 original browser assertions did not execute")
    for name, data in inputs_content.items():
        destination = output / "inputs" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    run_finished = time.time_ns()
    receipt = {"schema": 1, "status": "PASSED", "lane": lane,
               "candidate_sha": candidate,
               "source_tree": git(repository, "rev-parse", f"{candidate}^{{tree}}").decode().strip(),
               "consumer_contract_sha256": independent_gates.digest(contract(repository, lane)),
               "source_inventory_sha256": sha(inputs_content["source-inventory.tsv"]),
               "consumer_build_sha256": {path: sha(original(repository, candidate, path))
                                          for path in BUILD_PATHS},
               "producer_sha256": sha(original(repository, candidate,
                                               "tools/qualification/full_browser_consumer.py")),
               "browser_support_sha256": {path: sha(original(repository, candidate, path))
                                          for path in (LAUNCHER, REPORTER)},
               "toolchain": identity, "staged_hashes": hashes,
               "runtime_identity": f"{platform.system()} {platform.release()} {platform.machine()}",
               "paths": {"checkout": str(repository), "staging": str(staging),
                         "archive": str(output), "inputs": str(inputs), "work": str(work)},
               "process": {"started_ns": run_started, "finished_ns": run_finished,
                           "graph": graph_process}, "modules": processes,
               "row_order_sha256": {short: sha(encoded(values))
                                    for short, values in module_rows.items()},
               "files": [{"path": path.relative_to(output).as_posix(),
                          "sha256": file_hash(path), "mtime_ns": path.stat().st_mtime_ns}
                         for path in sorted(output.rglob("*")) if path.is_file()]}
    (output / "receipt.json").write_bytes(encoded(receipt) + b"\n")
    return receipt


def verify(repository, candidate, lane, archive, digest, binary, hashes):
    repository, archive, binary = map(Path, (repository, archive, binary))
    repository = repository.resolve()
    if (lane not in LANES or archive.is_symlink() or not archive.is_dir()
            or binary.is_symlink()):
        raise ValueError("selected full browser archive or lane differs")
    if not HEX64.fullmatch(digest) or independent_gates.archive_digest(archive) != digest:
        raise ValueError("independent browser archive digest differs")
    receipt = independent_gates._json(archive / "receipt.json")
    independent_gates._inventory(archive, receipt)
    selected = contract(repository, lane)
    if (receipt.get("schema") != 1 or receipt.get("status") != "PASSED"
            or receipt.get("lane") != lane or receipt.get("candidate_sha") != candidate
            or receipt.get("source_tree") != git(repository, "rev-parse", f"{candidate}^{{tree}}").decode().strip()
            or receipt.get("consumer_contract_sha256") != independent_gates.digest(selected)):
        raise ValueError("browser receipt differs from exact candidate or lane")
    inputs = input_bytes(repository, candidate, lane)
    for name, raw in inputs.items():
        if (archive / "inputs" / name).read_bytes() != raw:
            raise ValueError(f"archived original source or method input differs: {name}")
    if receipt.get("source_inventory_sha256") != sha(inputs["source-inventory.tsv"]):
        raise ValueError("original source inventory hash differs")
    if receipt.get("consumer_build_sha256") != {
            path: sha(original(repository, candidate, path)) for path in BUILD_PATHS}:
        raise ValueError("exact external browser consumer source differs")
    if receipt.get("producer_sha256") != sha(original(
            repository, candidate, "tools/qualification/full_browser_consumer.py")):
        raise ValueError("browser producer source differs")
    if receipt.get("browser_support_sha256") != {
            path: sha(original(repository, candidate, path)) for path in (LAUNCHER, REPORTER)}:
        raise ValueError("browser launcher or reporter source differs")
    role, mode = lane.split(":")[2:]
    major, pinned = CHROMIUM[role]
    if (file_hash(binary) != pinned or receipt["toolchain"]["browser_sha256"] != pinned
            or Path(receipt["toolchain"]["browser"]) != binary
            or not re.search(rf"\b{major}\.", receipt["toolchain"]["browser_version"])):
        raise ValueError("wrong Chromium binary or version")
    if receipt.get("staged_hashes") != hashes:
        raise ValueError("independently selected staged KLIB hashes differ")
    if (receipt["toolchain"].get("java_sha256") != JAVA_SHA256
            or receipt["toolchain"].get("gradle_sha256") != GRADLE_SHA256
            or receipt["toolchain"].get("kgp_version") != "2.4.20"):
        raise ValueError("pinned JDK, Gradle, or KGP identity differs")
    paths = receipt["paths"]
    if (set(paths) != {"checkout", "staging", "archive", "inputs", "work"}
            or paths["archive"] != str(archive)
            or paths["checkout"] != str(repository)
            or any(not Path(value).is_absolute() for value in paths.values())
            or Path(paths["archive"]).is_relative_to(repository)
            or Path(paths["staging"]).is_relative_to(repository)):
        raise ValueError("external browser provider or archive path differs")
    gradle = Path(receipt["toolchain"]["gradle"])
    base = gradle_args(repository, Path(paths["staging"]), archive, Path(paths["work"]),
                       Path(paths["inputs"]), lane, hashes, gradle)
    graph_process = receipt["process"].get("graph", {})
    if (graph_process.get("command") != base + ["qualificationGraphs"]
            or graph_process.get("cwd") != paths["inputs"]
            or graph_process.get("exit_code") != 0
            or type(graph_process.get("pid")) is not int
            or graph_process["pid"] <= 0):
        raise ValueError("original external provider graph process differs")
    for module, short in (("dyn4k-core", "core"), ("dyn4k", "facade")):
        if (file_hash(archive / "resolved" / f"{module}-js-{VERSION}.klib") != hashes[module]
                or file_hash(staged(Path(receipt["paths"]["staging"]), module)) != hashes[module]):
            raise ValueError("transported or staged provider KLIB differs")
        source = selected_map(inputs[f"{short}-cases.tsv"])
        folder = archive / short
        xml = sorted((folder / "xml").glob("TEST-*.xml"))
        if not xml:
            raise ValueError("raw browser XML is absent")
        observed = [identity for report in xml
                    for identity in rows(report.read_bytes(), source, major)]
        if len(observed) != len(source) or set(observed) != set(source.values()):
            raise ValueError("full original browser method rows differ")
        if receipt["row_order_sha256"].get(short) != sha(encoded(observed)):
            raise ValueError("original browser method order differs")
        record = receipt["modules"][short]
        if (file_hash(folder / "browser-reporter.js") != receipt["browser_support_sha256"][REPORTER]
                or file_hash(folder / "linked-executable.js") != record["linked_sha256"]):
            raise ValueError("browser reporter or linked bundle differs")
        launches = [json.loads(line) for line in (folder / "browser-launches.jsonl").read_text().splitlines()]
        if (record.get("command") != base + [f":{short}:jsBrowserTest"]
                or record.get("cwd") != paths["inputs"]
                or type(record.get("pid")) is not int
                or type(record.get("parent_pid")) is not int
                or record["parent_pid"] != graph_process.get("parent_pid")):
            raise ValueError("original external browser process command differs")
        if not launches or any(item != {
                "token": record["browser_token"], "runtime": "chromium",
                "selected_binary": str(binary), "selected_sha256": pinned,
                "process_executable": str(binary), "process_sha256": pinned,
                "pid": item.get("pid")}
                or type(item.get("pid")) is not int or item["pid"] <= 0
                for item in launches):
            raise ValueError("real Chromium process identity differs")
        if (record["exit_code"] != 0 or record["pid"] <= 0
                or record["started_ns"] > record["finished_ns"]
                or file_hash(folder / "karma.conf.js") == sha(b"")):
            raise ValueError("original Gradle or Karma process differs")
        text = (folder / "gradle.stdout").read_text()
        package = f"dyn4k-full-staged-browser-consumer-{short}-test"
        expected_bundle = (f"{receipt['paths']['work']}/{short}/compileSync/js/test/"
                           f"test{mode.capitalize()}Executable/kotlin/{package}.js")
        if (f"> Task :{short}:jsBrowserTest" not in text
                or "BUILD SUCCESSFUL" not in text or " FAILED" in text
                or f"QUALIFICATION_LANE={lane}" not in (archive / "graph.stdout").read_text()
                or (mode == "production" and
                    f"qualification test input: {expected_bundle}" not in text)):
            raise ValueError("raw process output omits selected browser task or bundle")
        attested = json.loads((folder / "reporter-producer.json").read_text())
        if attested != {"path": str(repository / CONSUMER / short / "karma.config.d"
                                     / "qualification-browser-reporter.js"),
                        "sha256": receipt["browser_support_sha256"][REPORTER],
                        "producer_path": f"{paths['work']}/root/js/node_modules/"
                                         "kotlin-web-helpers/dist/karma-kotlin-reporter.js",
                        "producer_sha256": "7c3232f60952aff254847ae62a866385735e3094197454d755100e962c2f2347"}:
            raise ValueError("browser reporter producer attestation differs")
        karma_rows((folder / "raw-karma.jsonl").read_bytes(), source, major)
    graph = independent_gates._json(archive / "provider-graph.json")
    if (set(graph) != {"compile", "runtime", "gradle_user_home"}
            or graph["gradle_user_home"] != receipt["toolchain"]["gradle_user_home"]):
        raise ValueError("browser provider graph is incomplete")
    for phase, configuration in (("compile", "jsTestCompileClasspath"),
                                 ("runtime", "jsTestRuntimeClasspath")):
        entries = graph[phase]
        if len(entries) != 2 or {item["project"] for item in entries} != {"core", "facade"}:
            raise ValueError("both external browser provider graphs are required")
        for entry in entries:
            roots = {f"io.github.rubixhacker:{module}:{VERSION}" for module in MODULES}
            variants = {f"io.github.rubixhacker:{module}-js:{VERSION}" for module in MODULES}
            components = {value for value in entry["components"]
                          if value.startswith("io.github.rubixhacker:")}
            artifacts = [item for item in entry["artifacts"]
                         if item["component"].startswith("io.github.rubixhacker:")]
            if (entry["configuration"] != configuration or components != roots | variants
                    or {item["component"] for item in artifacts} != variants
                    or len(artifacts) != 2):
                raise ValueError("browser provider graph has missing or foreign modules")
            for module in MODULES:
                item = next(value for value in artifacts
                            if value["component"] == f"io.github.rubixhacker:{module}-js:{VERSION}")
                if item["sha256"] != hashes[module]:
                    raise ValueError("browser resolved provider KLIB hash differs")
    return {"status": "PASSED", "lane": lane, "selected_cases": 2523,
            "archive_sha256": digest, "candidate_sha": candidate}


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("run", "verify"):
        selected = commands.add_parser(command)
        selected.add_argument("--repository", type=Path, required=True)
        selected.add_argument("--candidate", required=True)
        selected.add_argument("--lane", choices=sorted(LANES), required=True)
        selected.add_argument("--browser", type=Path, required=True)
        selected.add_argument("--core-sha256", required=True)
        selected.add_argument("--facade-sha256", required=True)
        if command == "run":
            selected.add_argument("--staging", type=Path, required=True)
            selected.add_argument("--output", type=Path, required=True)
            selected.add_argument("--gradle", type=Path, required=True)
        else:
            selected.add_argument("--archive", type=Path, required=True)
            selected.add_argument("--archive-sha256", required=True)
    args = parser.parse_args()
    hashes = {"dyn4k-core": args.core_sha256, "dyn4k": args.facade_sha256}
    if any(not HEX64.fullmatch(value) for value in hashes.values()):
        parser.error("independent staged KLIB SHA-256 values are required")
    try:
        if args.command == "run":
            result = run(args.repository, args.candidate, args.lane, args.staging,
                         args.output, args.gradle, args.browser, hashes)
            result = {"status": result["status"], "lane": args.lane,
                      "selected_cases": 2523, "archive": str(args.output),
                      "archive_sha256": independent_gates.archive_digest(args.output)}
        else:
            result = verify(args.repository, args.candidate, args.lane, args.archive,
                            args.archive_sha256, args.browser, hashes)
        print(json.dumps(result, sort_keys=True))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"NOT_RUN: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
