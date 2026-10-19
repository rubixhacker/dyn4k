#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
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
KARMA_GENERATED_MIDDLE_SHA256 = "35656914fc122e8c2ba55672df48b25940f625308f580e4b59a5bc8bacc580e6"
LEGACY_CANDIDATE_SHA = "2e3665ba110e18d9669f847eb714e31befa391ce"
LEGACY_REPORTER_SHA256 = "f2d7b210b5246339700370af19f595061ae908a9c7943371a36b75e7c2101f99"
KARMA_HEADER = b"\nmodule.exports = function(config) {\n\nconfig.set("
KARMA_REPORTER_MARKER = b"// qualification-browser-reporter.js\n"
RUNTIME_INPUT_SHA256 = {
    "mocha/mocha.js": "8f46c07ab4422da71bdb27e8f54d0a9ba59b736face2c9f5534c414623c55ef6",
    "karma-mocha/lib/adapter.js": "d2ecb1de057231e7c5efe6b7a5b36e163c85f49834814ab8fc3a893a3a404933",
    "kotlin-web-helpers/dist/kotlin-test-karma-runner.js": "15261c8d909c161dfc3004934d1f2542f96abcb78071b6f3663aa927773aba18",
    "karma/lib/config.js": "fadd8d4cef5e4d62dcd9a5ccd63295ceb028925a5d2f8b7edfb1d47a09fb7e42",
    "karma/lib/helper.js": "db2c4942bde7e0d696a40d1a1a7b58ba18b9acc3843c53a8a336c86645d5de6f",
    "karma/lib/file-list.js": "b91c1f294a2f1fbd886a8d3b991c8066c70037319a8e71d97a549b0928eefc22",
    "karma/lib/preprocessor.js": "0ad9180342ad37e9a1782105a98df0b60225598fd5ccd66016fd90fbb49230f5",
    "karma-mocha/lib/index.js": "4e9a83d5ff0504ad8d2ea42ee535d5e05324b2e4e8f1796b809c8314b1cc524b",
    "karma-webpack/lib/karma-webpack/framework.js": "705fc7f4d211eee26beb549758d8ea39f502a7385c2a43756bc71e3003c99ca9",
    "karma-webpack/lib/karma-webpack/preprocessor.js": "6af7525c470abcc69165a9732bf492b4524201525183eeef55998940f3f802c6",
    "kotlin-web-helpers/dist/karma-webpack-output.js": "7accb6fbba4ce0082f6e8ae2ca165eb9dd3c6dcfed0dfb2a8ba2e9aaa43061c7",
}


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
    for element in (suite, *cases):
        raw_time = element.get("time")
        try:
            duration = float(raw_time)
        except (TypeError, ValueError):
            raise ValueError("original browser XML duration is missing or invalid") from None
        if not math.isfinite(duration) or math.copysign(1.0, duration) < 0:
            raise ValueError("original browser XML duration is nonfinite or negative")
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


def bundle_paths(work, short, mode):
    package = f"dyn4k-full-staged-browser-consumer-{short}-test"
    linked = work / short / "compileSync/js/test" / f"test{mode.capitalize()}Executable" / "kotlin" / f"{package}.js"
    selected = (work / "root/js/packages" / package / "kotlin" / f"{package}.js"
                if mode == "development" else linked)
    runner = work / "root/js/node_modules/kotlin-web-helpers/dist/kotlin-test-karma-runner.js"
    return linked, selected, runner


def configured_bundle(raw, work, short, mode, reporter, port):
    if not raw.startswith(KARMA_HEADER):
        raise ValueError("archived Karma configuration header differs")
    try:
        decoded = raw[len(KARMA_HEADER):].decode()
        configuration, end = json.JSONDecoder().raw_decode(decoded)
    except (UnicodeDecodeError, ValueError):
        raise ValueError("archived Karma base settings are invalid") from None
    linked, selected, runner = bundle_paths(work, short, mode)
    paths = [str(runner), str(selected)]
    expected = {
        "singleRun": True, "autoWatch": False,
        "basePath": str(work / "root/js/packages" /
                        f"dyn4k-full-staged-browser-consumer-{short}-test"),
        "files": paths, "frameworks": ["webpack-output", "mocha", "webpack"],
        "client": {"args": []}, "browsers": ["ChromeHeadless"],
        "customLaunchers": {}, "failOnFailingTestSuite": False,
        "failOnEmptyTestSuite": False, "reporters": ["karma-kotlin-reporter"],
        "preprocessors": {path: ["webpack", "sourcemap"] for path in paths},
        "proxies": {}, "webpackCopy": [],
    }
    if configuration != expected:
        raise ValueError("archived Karma selected bundle path or preprocessor differs")
    offset = len(KARMA_HEADER) + len(decoded[:end].encode())
    marker = raw.find(KARMA_REPORTER_MARKER, offset)
    if (marker < 0 or sha(raw[offset:marker]) != KARMA_GENERATED_MIDDLE_SHA256
            or raw.count(KARMA_REPORTER_MARKER) != 1):
        raise ValueError("archived Karma generated settings or later override differs")
    suffix = raw[marker + len(KARMA_REPORTER_MARKER):]
    if not suffix.startswith(reporter):
        raise ValueError("archived Karma reporter script differs")
    suffix = suffix[len(reporter):]
    port_match = re.fullmatch(
        rb"\n\n// qualification-port\.js\nconfig\.set\(\{port: ([1-9][0-9]{0,4})\}\);\n{5}\}\n",
        suffix)
    if port_match is None or int(port_match[1]) != port or not 1 <= port <= 65535:
        raise ValueError("archived Karma port or later override differs")
    return linked, selected


def effective_files(evidence, work, short, mode):
    files = evidence.get("effective_files")
    preprocessors = evidence.get("effective_preprocessors")
    inputs = evidence.get("input_sha256")
    tmpdir = evidence.get("tmpdir")
    if (not isinstance(files, list) or len(files) != 7
            or not all(isinstance(value, dict) and set(value) == {
                "pattern", "served", "included", "watched", "nocache", "type", "isBinary"}
                       and isinstance(value["pattern"], str) for value in files)
            or not isinstance(tmpdir, str) or not Path(tmpdir).is_absolute()):
        raise ValueError("Karma effective file list differs")
    webpack = Path(files[0]["pattern"]).parent
    if (webpack.parent != Path(tmpdir)
            or not re.fullmatch(r"_karma_webpack_[0-9]+", webpack.name)):
        raise ValueError("Karma generated webpack path differs")
    _, selected, runner = bundle_paths(work, short, mode)
    root = work / "root/js/node_modules"
    paths = [str(webpack / "runtime.js"), str(webpack / "commons.js"),
             str(root / "mocha/mocha.js"), str(root / "karma-mocha/lib/adapter.js"),
             str(runner), str(selected), str(webpack / "**/*")]
    expected = [{"pattern": path, "served": True, "included": index != 6,
                 "watched": False, "nocache": False,
                 "type": None, "isBinary": None} for index, path in enumerate(paths)]
    if (files != expected or any(
            type(value[key]) is not type(reference[key])
            for value, reference in zip(files, expected)
            for key in ("served", "included", "watched", "nocache", "type", "isBinary"))
            or preprocessors != {str(runner): ["webpack", "sourcemap"],
                                 str(selected): ["webpack", "sourcemap"]}
            or inputs != {str(root / name): digest for name, digest in RUNTIME_INPUT_SHA256.items()}):
        raise ValueError("Karma effective files, preprocessors, or toolchain inputs differ")


def selected_bundle(folder, work, short, mode, process_record, major, require_effective=False):
    linked, selected = configured_bundle(
        (folder / "karma.conf.js").read_bytes(), work, short, mode,
        (folder / "browser-reporter.js").read_bytes(), process_record["karma_port"])
    evidence = json.loads((folder / "selected-bundle.json").read_text())
    selected_bytes = (folder / "karma-selected.js").read_bytes()
    linked_bytes = (folder / "linked-executable.js").read_bytes()
    base_keys = {"source_path", "archive_path", "sha256", "node_pid",
                 "browser_id", "browser_name", "captured_ns", "complete_ns"}
    effective_keys = {"effective_files", "effective_preprocessors", "input_sha256", "tmpdir"}
    if (set(evidence) != base_keys | (effective_keys if require_effective else set())
            or evidence["source_path"] != str(selected)
            or evidence["archive_path"] != str(folder / "karma-selected.js")
            or evidence["sha256"] != sha(selected_bytes)
            or sha(selected_bytes) != sha(linked_bytes)
            or process_record.get("linked_sha256") != sha(linked_bytes)
            or type(evidence["node_pid"]) is not int or evidence["node_pid"] <= 0
            or not isinstance(evidence["browser_id"], str) or not evidence["browser_id"]
            or not isinstance(evidence["browser_name"], str)
            or not re.fullmatch(rf"Chrome Headless {major}(?:\.\d+)+ \(Linux (?:\d+\.)+\d+\)",
                                evidence["browser_name"])
            or type(evidence["captured_ns"]) is not int
            or type(evidence["complete_ns"]) is not int
            or not (process_record["started_ns"] <= evidence["captured_ns"]
                    <= evidence["complete_ns"] <= process_record["finished_ns"])):
        raise ValueError("Karma-selected bundle bytes or source-process binding differs")
    if require_effective:
        effective_files(evidence, work, short, mode)
    return linked, selected


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
            configuration = lane.rsplit(":", 1)[1]
            linked, configured, _ = bundle_paths(work, short, configuration)
            module_env = dict(env, DYN4K_BROWSER_ATTESTATION=str(launches),
                              DYN4K_BROWSER_TOKEN=token,
                              DYN4K_BROWSER_REPORTER_ATTESTATION=str(attestation),
                              DYN4K_BROWSER_RAW_KARMA=str(raw_karma),
                              DYN4K_BROWSER_REPORTER_SOURCE=str(reporter),
                              DYN4K_BROWSER_SELECTED_BUNDLE=str(configured),
                              DYN4K_BROWSER_SELECTED_ARCHIVE=str(destination / "karma-selected.js"),
                              DYN4K_BROWSER_SELECTED_ATTESTATION=str(destination / "selected-bundle.json"),
                              DYN4K_BROWSER_WORK_ROOT=str(work),
                              DYN4K_BROWSER_TMPDIR=os.environ["TMPDIR"])
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
            if not linked.is_file():
                raise ValueError(f"external {short} linked {configuration} bundle is absent")
            processes[short]["linked_sha256"] = copy(linked, destination / "linked-executable.js")
            package = f"dyn4k-full-staged-browser-consumer-{short}-test"
            generated = work / "root/js/packages" / package / "karma.conf.js"
            if (not generated.is_file()
                    or f"config.set({{port: {port}}});" not in generated.read_text()
                    or "DYN4K_BROWSER_RAW_KARMA" not in generated.read_text()):
                raise ValueError("external browser Karma configuration lacks isolated port")
            copy(generated, destination / "karma.conf.js")
            copy(reporter, destination / "browser-reporter.js")
            selected_bundle(destination, work, short, configuration, processes[short], major,
                            require_effective=True)
            if not launches.is_file() or not attestation.is_file() or not raw_karma.is_file():
                raise ValueError("real browser process or reporter producer is absent")
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
        selected_bundle(folder, Path(paths["work"]), short, mode, record, major,
                        require_effective=not (
                            candidate == LEGACY_CANDIDATE_SHA
                            and receipt["browser_support_sha256"][REPORTER]
                            == LEGACY_REPORTER_SHA256))
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
