#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import os
import platform
import plistlib
import re
import runpy
import shutil
import socket
import stat
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

import independent_gates


CONSUMER = "consumers/qualification/portable/full-browser"
MODULES = ("dyn4k-core", "dyn4k")
VERSION = "0.1.0-alpha.1"
JAVA_SHA256 = "2a207f5e7d075afa01d97f8048389a64432a44c4a5af0f5e77d6e286ec5f401d"
DARWIN_JAVA_SHA256 = "9be1d0a740ff6502df1a762145e62860f5de4b7e17658d9cb9498da3acf9d16c"
GRADLE_SHA256 = "b88b6fc9f41fba7bf456a3f8255ee5b7c6c379202ca13f68c3feecebcbc7bd8b"
CHROMIUM = {
    "minimum": (119, "c81049295247b6892c802dcad33dcab0a0337fce31800f923f51bdb0c07e6d11"),
    "current": (155, "b866a2964538c825538c454de4867973b926650da57ec12dc3328807d768247b"),
}
FIREFOX = {
    "minimum": (120, "74b442bb10d62f01e80eeae8fee96fd98ecb1d414cf283b2fcef80410d827750"),
    "current": (158, "a19472941a7cd7252ab5e61b02eb616a50389a784323c21dc6873a23fd700789"),
}
BROWSER_VERSIONS = {"Chromium": CHROMIUM, "Firefox": FIREFOX}
LANES = {f"{target}:{family}:{role}:{mode}"
         for target in ("js", "wasmJs")
         for family in ("Chromium", "Firefox", "Safari")
         for role in ("minimum", "current")
         for mode in ("development", "production")}
SOURCE_ROOTS = ("dyn4k-core/src/commonTest/kotlin", "dyn4k/src/commonTest/kotlin",
                "dyn4k-core/src/jsTest/kotlin")
WASM_SOURCE_ROOTS = ("dyn4k-core/src/commonTest/kotlin", "dyn4k/src/commonTest/kotlin",
                     "dyn4k-core/src/wasmJsTest/kotlin")
BUILD_PATHS = tuple(f"{CONSUMER}/{name}" for name in
                    ("settings.gradle.kts", "build.gradle.kts", "core/build.gradle.kts",
                     "facade/build.gradle.kts"))
LAUNCHER = "tools/qualification/browser_wasi/browser_launcher.py"
REPORTER = f"{CONSUMER}/browser-reporter.js"
CHROMIUM_WITNESS = f"{CONSUMER}/chromium_http_witness.js"
SAFARI_WITNESS = f"{CONSUMER}/safari_response_witness.py"
SAFARI_OBSERVER = f"{CONSUMER}/safari_karma_observer.js"
SAFARI_WORKER = f"{CONSUMER}/safari_response_worker.js"
SAFARI_BOOTSTRAP = f"{CONSUMER}/safari_response_bootstrap.js"
YARN_LOCK = f"{CONSUMER}/consumer-yarn.lock"
MULTI_BROWSER_YARN_LOCK = f"{CONSUMER}/consumer-multibrowser-yarn.lock"
WASM_YARN_LOCK = f"{CONSUMER}/consumer-wasm-yarn.lock"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
KARMA_GENERATED_MIDDLE_SHA256 = "35656914fc122e8c2ba55672df48b25940f625308f580e4b59a5bc8bacc580e6"
WASM_KARMA_GENERATED_MIDDLE_SHA256 = "3e87b74eb3308a127e1859c4beaa948460c471fcb7330b5c620ab6125bbc051f"
LEGACY_CANDIDATE_SHA = "2e3665ba110e18d9669f847eb714e31befa391ce"
LEGACY_LOCK_CANDIDATES = frozenset({
    LEGACY_CANDIDATE_SHA,
    "113a4700128e05699fc99b739252385d47dd06cf",
    "266857f2a83faea0945a850fdf53db2382793a9a",
    "91726e339fc1c482543ebb53e447751c4419e81f",
})
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
WASM_INPUT_SHA256 = {**RUNTIME_INPUT_SHA256,
    "kotlin-web-helpers/dist/static/context.html":
        "0451957d938729d37d045f2eb855ea0b2afa50815ff2ed9488dd18e7135fc69d",
    "kotlin-web-helpers/dist/static/debug.html":
        "695977572217887870de5bf75b6c4ba3be2b6780e20a0f2dd83af1c8660ce03e"}


def lane_parts(lane):
    if lane not in LANES:
        raise ValueError("unsupported full browser lane")
    return lane.split(":")


def publication(target):
    return "js" if target == "js" else "wasm-js"


def browser_marker(family, major):
    if family == "Chromium":
        return rf"Chrome Headless {major}(?:\.\d+)+ \(Linux (?:\d+\.)+\d+\)"
    if family == "Firefox":
        return rf"Firefox {major}(?:\.\d+)+ \(Linux (?:\d+\.)+\d+\)"
    return rf"Safari {major}(?:\.\d+)+(?: \([^)]*\))?"


def observed_browser(item, token, family, browser, pinned):
    allowed = {browser}
    if family == "Firefox":
        allowed.add(browser.with_name("firefox-bin"))
    image = Path(item.get("process_executable", ""))
    if image not in allowed or not image.is_file():
        return False
    return (item == {"token": token, "runtime": family.lower(),
                    "selected_binary": str(browser), "selected_sha256": pinned,
                    "process_executable": str(image),
                    "process_sha256": file_hash(image), "pid": item.get("pid")}
            and type(item.get("pid")) is int and item["pid"] > 0)


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


def source_inventory(repository, candidate, cases, target="js"):
    roots = SOURCE_ROOTS if target == "js" else WASM_SOURCE_ROOTS
    tracked = sorted(path for path in git(repository, "ls-tree", "-r", "--name-only",
                                          candidate, "--", *roots).decode().splitlines()
                     if path.endswith(".kt"))
    live = sorted(path.relative_to(repository).as_posix() for root in roots
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
    target, _, _, _ = lane_parts(lane)
    inventory = source_inventory(repository, candidate, selected["cases"], target)
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
        "consumer-yarn.lock": original(repository, candidate,
                                       YARN_LOCK if candidate == LEGACY_CANDIDATE_SHA
                                       else MULTI_BROWSER_YARN_LOCK if target == "js"
                                       else WASM_YARN_LOCK),
    }


def staged(staging, module, target="js"):
    variant = publication(target)
    return staging / "io/github/rubixhacker" / f"{module}-{variant}" / VERSION / f"{module}-{variant}-{VERSION}.klib"


def rows(xml, expected, major, target="js", family="Chromium"):
    suite = ET.fromstring(xml)
    task = f"{target}BrowserTest"
    if suite.tag != "testsuite" or not suite.get("name", "").startswith(task + "."):
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
    label = "ChromeHeadless" if family == "Chromium" else family
    platform_suffix = (r", Linux(?:\d+\.)+\d+" if family != "Safari"
                       else r"(?:, [^]]+)?")
    suffix = re.compile(r"\[" + target + r", browser, " + label + str(major)
                        + r"(?:\.\d+)+" + platform_suffix + r"\]$")
    for case in cases:
        classname = case.get("classname", "")
        method = case.get("name", "")
        match = suffix.search(method)
        if not classname.startswith(task + ".") or match is None:
            raise ValueError("original browser row has wrong runtime or task")
        key = (classname.removeprefix(task + "."), method[:match.start()])
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


def karma_rows(raw, expected, major, family="Chromium"):
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
                rf"##teamcity\[testSuiteStarted name='(.+)\."
                + browser_marker(family, major) + r"' flowId='([^']+)'\]", message)
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


def bundle_paths(work, short, mode, target="js", runner_path=None):
    package = f"dyn4k-full-staged-browser-consumer-{short}-test"
    if target == "js":
        linked = work / short / "compileSync/js/test" / f"test{mode.capitalize()}Executable" / "kotlin" / f"{package}.js"
        selected = (work / "root/js/packages" / package / "kotlin" / f"{package}.js"
                    if mode == "development" else linked)
        runner = work / "root/js/node_modules/kotlin-web-helpers/dist/kotlin-test-karma-runner.js"
    else:
        linked = (work / short / "compileSync/wasmJs/test" /
                  f"test{mode.capitalize()}Executable" /
                  ("optimized" if mode == "production" else "kotlin") / f"{package}.mjs")
        selected = work / "root/wasm/packages" / package / "static/load.mjs"
        runner = runner_path
    return linked, selected, runner


def configured_bundle(raw, work, short, mode, reporter, port, target="js", family="Chromium",
                      safari_observer=None):
    if not raw.startswith(KARMA_HEADER):
        raise ValueError("archived Karma configuration header differs")
    try:
        decoded = raw[len(KARMA_HEADER):].decode()
        configuration, end = json.JSONDecoder().raw_decode(decoded)
    except (UnicodeDecodeError, ValueError):
        raise ValueError("archived Karma base settings are invalid") from None
    if (not isinstance(configuration, dict)
            or not isinstance(configuration.get("files"), list)
            or len(configuration["files"]) != 2
            or any(not isinstance(value, str) for value in configuration["files"])):
        raise ValueError("archived Karma selected bundle path or preprocessor differs")
    runner_path = Path(configuration["files"][0]) if target == "wasmJs" else None
    linked, selected, runner = bundle_paths(work, short, mode, target, runner_path)
    if target == "wasmJs":
        tooling = Path.home() / ".kotlin/kotlin-npm-tooling/yarn"
        try:
            parts = runner.relative_to(tooling).parts
        except ValueError:
            parts = ()
        if (len(parts) != 5 or not re.fullmatch(r"[0-9a-f]{32}", parts[0])
                or parts[1:] != ("node_modules", "kotlin-web-helpers", "dist",
                                 "kotlin-test-karma-runner.js")):
            raise ValueError("archived Wasm JS Karma runner path differs")
    paths = [str(runner), str(selected)]
    expected = {
        "singleRun": True, "autoWatch": False,
        "basePath": str(work / f"root/{'js' if target == 'js' else 'wasm'}/packages" /
                        f"dyn4k-full-staged-browser-consumer-{short}-test"),
        "files": paths, "frameworks": ["webpack-output", "mocha", "webpack"],
        "client": {"args": []}, "browsers": [{"Chromium": "ChromeHeadless",
                                                "Firefox": "FirefoxHeadless",
                                                "Safari": "Safari"}[family]],
        "customLaunchers": {}, "failOnFailingTestSuite": False,
        "failOnEmptyTestSuite": False, "reporters": ["karma-kotlin-reporter"],
        "preprocessors": {path: ["webpack", "sourcemap"] for path in paths},
        "proxies": {}, "webpackCopy": [],
    }
    if target == "wasmJs":
        expected["customContextFile"] = str(runner.parent / "static/context.html")
        expected["customDebugFile"] = str(runner.parent / "static/debug.html")
    if configuration != expected:
        raise ValueError("archived Karma selected bundle path or preprocessor differs")
    offset = len(KARMA_HEADER) + len(decoded[:end].encode())
    marker = raw.find(KARMA_REPORTER_MARKER, offset)
    generated_hash = (KARMA_GENERATED_MIDDLE_SHA256 if target == "js"
                      else WASM_KARMA_GENERATED_MIDDLE_SHA256)
    if (marker < 0 or sha(raw[offset:marker]) != generated_hash
            or raw.count(KARMA_REPORTER_MARKER) != 1):
        raise ValueError("archived Karma generated settings or later override differs")
    suffix = raw[marker + len(KARMA_REPORTER_MARKER):]
    if not suffix.startswith(reporter):
        raise ValueError("archived Karma reporter script differs")
    suffix = suffix[len(reporter):]
    observer_suffix = (b"\n// qualification-z-safari-observer.js\n" + safari_observer
                       if safari_observer is not None else b"")
    port_match = re.fullmatch(
        rb"\n\n// qualification-port\.js\nconfig\.set\(\{port: ([1-9][0-9]{0,4})\}\);\n"
        + re.escape(observer_suffix) + rb"\n{4}\}\n", suffix)
    if port_match is None or int(port_match[1]) != port or not 1 <= port <= 65535:
        raise ValueError("archived Karma port or later override differs")
    return linked, selected


def effective_files(evidence, work, short, mode, target="js"):
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
    runner_path = Path(files[4]["pattern"]) if target == "wasmJs" else None
    _, selected, runner = bundle_paths(work, short, mode, target, runner_path)
    root = runner.parents[2]
    paths = [str(webpack / "runtime.js"), str(webpack / "commons.js"),
             str(root.resolve() / "mocha/mocha.js"),
             str(root.resolve() / "karma-mocha/lib/adapter.js"),
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
            or inputs != {str(root / name): digest for name, digest in
                          (RUNTIME_INPUT_SHA256 if target == "js" else WASM_INPUT_SHA256).items()}):
        raise ValueError("Karma effective files, preprocessors, or toolchain inputs differ")


def reporter_producer_path(folder):
    selected = json.loads((folder / "selected-bundle.json").read_text())
    runner = selected["effective_files"][4]["pattern"]
    if not runner.endswith("/kotlin-test-karma-runner.js"):
        raise ValueError("Karma reporter producer runner path differs")
    return str(Path(runner.removesuffix("kotlin-test-karma-runner.js") +
                    "karma-kotlin-reporter.js").resolve())


def selected_bundle(folder, work, short, mode, process_record, major, require_effective=False,
                    target="js", family="Chromium", observed_folder=None, require_http=False):
    observer = folder / "safari-karma-observer.js"
    linked, selected = configured_bundle(
        (folder / "karma.conf.js").read_bytes(), work, short, mode,
        (folder / "browser-reporter.js").read_bytes(), process_record["karma_port"],
        target, family, observer.read_bytes() if observer.is_file() else None)
    evidence = json.loads((folder / "selected-bundle.json").read_text())
    selected_bytes = (folder / "karma-selected.js").read_bytes()
    linked_bytes = (folder / "linked-executable.js").read_bytes()
    base_keys = {"source_path", "archive_path", "sha256", "node_pid",
                 "browser_id", "browser_name", "captured_ns", "complete_ns"}
    effective_keys = {"effective_files", "effective_preprocessors", "input_sha256", "tmpdir"}
    if require_http:
        effective_keys.add("generated")
    asset_keys = {"assets"} if target == "wasmJs" else set()
    observed_folder = folder if observed_folder is None else observed_folder
    if (set(evidence) != base_keys | (effective_keys if require_effective else set()) | asset_keys
            or evidence["source_path"] != str(selected)
            or evidence["archive_path"] != str(observed_folder / "karma-selected.js")
            or evidence["sha256"] != sha(selected_bytes)
            or (target == "js" and sha(selected_bytes) != sha(linked_bytes))
            or process_record.get("linked_sha256") != sha(linked_bytes)
            or type(evidence["node_pid"]) is not int or evidence["node_pid"] <= 0
            or not isinstance(evidence["browser_id"], str) or not evidence["browser_id"]
            or not isinstance(evidence["browser_name"], str)
            or not re.fullmatch(browser_marker(family, major), evidence["browser_name"])
            or type(evidence["captured_ns"]) is not int
            or type(evidence["complete_ns"]) is not int
            or not (process_record["started_ns"] <= evidence["captured_ns"]
                    <= evidence["complete_ns"] <= process_record["finished_ns"])):
        raise ValueError("Karma-selected bundle bytes or source-process binding differs")
    if require_effective:
        effective_files(evidence, work, short, mode, target)
    if target == "wasmJs":
        package = f"dyn4k-full-staged-browser-consumer-{short}-test"
        names = sorted((f"{package}.wasm", f"{package}.mjs", f"{package}.wasm.map",
                        "custom-formatters.js", f"{package}.js-builtins.mjs",
                        f"{package}.import-object.mjs"))
        assets = evidence["assets"]
        if (not isinstance(assets, list) or len(assets) != len(names)
                or [item.get("name") for item in assets] != names
                or any(set(item) != {"name", "sha256"}
                       or not HEX64.fullmatch(item["sha256"])
                       or file_hash(folder / "assets" / item["name"]) != item["sha256"]
                       for item in assets)
                or file_hash(folder / "assets" / f"{package}.mjs") != sha(linked_bytes)
                or file_hash(folder / "assets" / f"{package}.wasm") !=
                   file_hash(folder / "linked-executable.wasm")
                or process_record.get("linked_wasm_sha256") !=
                   file_hash(folder / "linked-executable.wasm")):
            raise ValueError("Wasm JS served executable assets differ from linked product")
    return linked, selected


def verify_http_responses(folder, process_record, target="js", short="core"):
    evidence = json.loads((folder / "selected-bundle.json").read_text())
    witness = json.loads((folder / "http-responses.json").read_text())
    package = f"dyn4k-full-staged-browser-consumer-{short}-test"
    assets = ([] if target == "js" else
              [f"{package}.mjs", f"{package}.wasm",
              f"{package}.import-object.mjs", f"{package}.js-builtins.mjs",
              "custom-formatters.js"])
    generated = witness.get("generated")
    source_generated = evidence.get("generated")
    if (not isinstance(generated, list) or generated != source_generated
            or len(generated) != (5 if target == "wasmJs" else 4)
            or any(not isinstance(item, dict)
                or set(item) != {"name", "source_path", "size", "sha256"}
                for item in generated)):
        raise ValueError("Karma HTTP generated source inventory differs")
    generated_names = [item["name"] for item in generated]
    if (len(set(generated_names)) != len(generated) or "runtime.js" not in generated_names
            or "commons.js" not in generated_names
            or not any(re.fullmatch(r"kotlin-test-karma-runner\.[0-9]+\.js", name)
                       for name in generated_names)
            or not any(re.fullmatch(rf"{re.escape(package if target == 'js' else 'load')}"
                                    r"\.[0-9]+\.js", name) for name in generated_names)
            or (target == "wasmJs" and not any(
                re.fullmatch(r"[0-9a-f]{20}\.wasm", name) for name in generated_names))):
        raise ValueError("Karma HTTP generated executable names differ")
    webpack = Path(evidence["effective_files"][0]["pattern"]).parent
    for item in generated:
        source = folder / "http-sources" / item["name"]
        if (item["source_path"] != str(webpack / item["name"])
                or not source.is_file() or source.stat().st_size != item["size"]
                or file_hash(source) != item["sha256"]):
            raise ValueError("Karma HTTP generated source bytes differ")
    emitted_wasm = next((name for name in generated_names if name.endswith(".wasm")), None)
    if (target == "wasmJs" and (emitted_wasm is None or
            (folder / "http-sources" / emitted_wasm).read_bytes() !=
            (folder / "assets" / f"{package}.wasm").read_bytes())):
        raise ValueError("Karma HTTP emitted Wasm differs from selected package")
    allowed = set(generated_names + assets)
    required = {"runtime.js", "commons.js"}
    if emitted_wasm is not None:
        required.add(emitted_wasm)
    items = witness.get("responses")
    if (set(witness) != {"browser_id", "browser_name", "node_pid", "captured_ns",
                         "complete_ns", "generated", "responses"}
            or any(witness[key] != evidence[key] for key in
                   ("browser_id", "browser_name", "node_pid", "captured_ns", "complete_ns"))
            or not isinstance(items, list)
            or not len(required) <= len(items) <= len(allowed)
            or len({item.get("name") for item in items if isinstance(item, dict)}) != len(items)
            or not required <= {item.get("name") for item in items if isinstance(item, dict)} <= allowed):
        raise ValueError("Karma HTTP response witness is missing or uncorrelated")
    previous = process_record["started_ns"]
    for index, item in enumerate(items):
        relative = f"http-responses/{index:04d}.body"
        if (not isinstance(item, dict)
                or set(item) != {"ordinal", "name", "url", "method", "started_ns",
                                "finished_ns", "status", "content_encoding", "range",
                                "size", "sha256", "body_path"}
                or type(item["ordinal"]) is not int or item["ordinal"] != index
                or type(item["started_ns"]) is not int
                or type(item["finished_ns"]) is not int
                or not previous <= item["started_ns"] <= item["finished_ns"] <= witness["complete_ns"]
                or item["method"] != "GET" or item["status"] != 200
                or item["content_encoding"] is not None or item["range"] is not None
                or item["body_path"] != relative
                or not isinstance(item["url"], str)
                or not re.fullmatch(r"/(?:absolute|base)/[^?#]+(?:\?[^#]*)?", item["url"])
                or Path(item["url"].split("?", 1)[0]).name != item["name"]
                or type(item["size"]) is not int or not 0 < item["size"] <= 64 * 1024 * 1024
                or not isinstance(item["sha256"], str)
                or not HEX64.fullmatch(item["sha256"])):
            raise ValueError("Karma HTTP response order, URL, or process interval differs")
        body = folder / relative
        expected = (folder / "http-sources" / item["name"]
                    if item["name"] in generated_names else folder / "assets" / item["name"])
        if (not body.is_file() or body.stat().st_size != item["size"]
                or file_hash(body) != item["sha256"]
                or body.read_bytes() != expected.read_bytes()):
            raise ValueError("Karma HTTP response body differs from selected source")
        previous = item["started_ns"]
    if witness["node_pid"] <= 0 or not (
            process_record["started_ns"] <= witness["captured_ns"]
            <= witness["complete_ns"] <= process_record["finished_ns"]):
        raise ValueError("Karma HTTP response process binding differs")
    return items


def verify_chromium_process_witness(folder, process_record, launches, server,
                                    short, target, candidate, source_path=None,
                                    source_sha256=None):
    path = folder / "chromium-cdp.jsonl"
    if not path.is_file():
        raise ValueError("Chromium process witness is absent")
    try:
        records = [json.loads(line) for line in path.read_text().splitlines()]
        session, *responses = records
    except (ValueError, TypeError):
        raise ValueError("Chromium process witness is malformed") from None
    pid = session.get("browser_pid") if isinstance(session, dict) else None
    source_fields = {"source_path", "source_sha256"} if source_path is not None else set()
    if (len(launches) != 1 or type(pid) is not int
            or pid != launches[0]["pid"] or session.get("cdp_browser_pid") != pid
            or set(session) != {"kind", "protocol", "module", "target",
                                "candidate_sha", "browser_pid", "cdp_browser_pid",
                                "target_id", "started_ns", "devtools_port",
                                "devtools_socket_inode"} | source_fields
            or session["kind"] != "session" or session["protocol"] != 1
            or session["module"] != short or session["target"] != target
            or session["candidate_sha"] != candidate
            or not isinstance(session["target_id"], str) or not session["target_id"]
            or type(session["started_ns"]) is not int
            or not process_record["started_ns"] <= session["started_ns"] <= process_record["finished_ns"]
            or type(session["devtools_port"]) is not int
            or not 0 < session["devtools_port"] < 65536
            or not isinstance(session["devtools_socket_inode"], str)
            or not re.fullmatch(r"[1-9][0-9]*", session["devtools_socket_inode"])
            or (source_path is not None and (
                session.get("source_path") != source_path
                or session.get("source_sha256") != source_sha256))
            or len(responses) != len(server)):
        raise ValueError("Chromium process witness session or response count differs")
    requests = set()
    served_by_url = {item["url"]: item for item in server}
    if len(served_by_url) != len(server):
        raise ValueError("Chromium process witness server URLs are duplicated")
    previous_ns = session["started_ns"]
    previous_cdp_timestamp = 0
    for index, row in enumerate(responses):
        if not isinstance(row, dict) or set(row) != {
                "kind", "ordinal", "request_id", "target_id", "browser_pid",
                "url", "method", "status", "mime_type", "from_disk_cache",
                "from_service_worker", "request_ns", "response_ns", "finished_ns",
                "body_size", "body_sha256", "events"}:
            raise ValueError("Chromium process witness response shape differs")
        address = urlsplit(row["url"]) if isinstance(row["url"], str) else None
        events = row["events"]
        if not isinstance(events, dict) or set(events) != {"request", "response", "finish"}:
            raise ValueError("Chromium process witness CDP events differ")
        request_event, response_event, finish_event = (
            events["request"], events["response"], events["finish"])
        if (not all(isinstance(value, dict) for value in
                    (request_event, response_event, finish_event))
                or any(value.get("requestId") != row["request_id"] for value in
                       (request_event, response_event, finish_event))
                or not isinstance(request_event.get("request"), dict)
                or request_event["request"].get("url") != row["url"]
                or request_event["request"].get("method") != row["method"]
                or not isinstance(response_event.get("response"), dict)
                or response_event["response"].get("url") != row["url"]
                or response_event["response"].get("status") != row["status"]
                or response_event["response"].get("mimeType") != row["mime_type"]
                or bool(response_event["response"].get("fromDiskCache")) != row["from_disk_cache"]
                or bool(response_event["response"].get("fromServiceWorker")) != row["from_service_worker"]
                or any(type(value.get("timestamp")) not in (int, float) for value in
                       (request_event, response_event, finish_event))
                or not request_event["timestamp"] <= response_event["timestamp"]
                or not request_event["timestamp"] <= finish_event["timestamp"]):
            raise ValueError("Chromium process witness raw CDP event differs")
        relative_url = address.path + ("?" + address.query if address.query else "") if address else None
        served = served_by_url.get(relative_url)
        if (row["kind"] != "response" or type(row["ordinal"]) is not int
                or row["ordinal"] != index or row["browser_pid"] != pid
                or row["target_id"] != session["target_id"]
                or not isinstance(row["request_id"], str) or not row["request_id"]
                or row["request_id"] in requests
                or address is None or address.scheme != "http"
                or address.hostname not in {"localhost", "127.0.0.1"}
                or address.port != process_record["karma_port"]
                or served is None
                or request_event["timestamp"] < previous_cdp_timestamp
                or row["method"] != "GET" or row["status"] != 200
                or row["from_disk_cache"] is not False
                or row["from_service_worker"] is not False
                or type(row["request_ns"]) is not int
                or type(row["response_ns"]) is not int
                or type(row["finished_ns"]) is not int
                or not previous_ns <= row["request_ns"] <= row["response_ns"] <= row["finished_ns"] <= process_record["finished_ns"]
                or type(row["body_size"]) is not int
                or row["body_size"] != served["size"]
                or row["body_sha256"] != served["sha256"]):
            raise ValueError("Chromium process witness URL, body, order, or process differs")
        requests.add(row["request_id"])
        served_by_url.pop(relative_url)
        previous_ns = row["request_ns"]
        previous_cdp_timestamp = request_event["timestamp"]
    if served_by_url:
        raise ValueError("Chromium process witness omitted served responses")
    return responses


def verify_safari_response_witness(folder, process_record, launches, server,
                                   short, target, candidate, source_path,
                                   source_sha256, worker_sha256, bootstrap_sha256,
                                   observer_sha256):
    path = folder / "safari-browser-responses.jsonl"
    if not path.is_file():
        raise ValueError("Safari browser response-body witness is absent")
    if (not (folder / "safari-worker-errors.jsonl").is_file()
            or (folder / "safari-worker-errors.jsonl").stat().st_size):
        raise ValueError("Safari browser worker reported a fetch failure")
    if (file_hash(Path(source_path)) != source_sha256
            or file_hash(folder / "safari-karma-observer.js") != observer_sha256
            or file_hash(folder / "safari-response-worker.js") != worker_sha256
            or file_hash(folder / "safari-response-bootstrap.js") != bootstrap_sha256):
        raise ValueError("Safari browser observer source differs")
    attested = json.loads((folder / "safari-worker-source.json").read_text())
    selected = json.loads((folder / "selected-bundle.json").read_text())
    if attested != {"observer_sha256": observer_sha256,
                    "worker_sha256": worker_sha256,
                    "bootstrap_sha256": bootstrap_sha256,
                    "node_pid": selected["node_pid"],
                    "token": process_record["browser_token"],
                    "port": process_record["karma_port"]}:
        raise ValueError("Safari browser worker source process differs")
    try:
        records = [json.loads(line) for line in path.read_text().splitlines()]
    except (ValueError, TypeError):
        raise ValueError("Safari browser response-body witness is malformed") from None
    expected = runpy.run_path(source_path)["safari_records"](
        folder, process_record, launches, candidate, short, target, source_path,
        source_sha256, worker_sha256, bootstrap_sha256, observer_sha256)
    if records != expected or len(records) != len(server) + 1:
        raise ValueError("Safari browser response-body session or source differs")
    responses = records[1:]
    served_by_url = {item["url"]: item for item in server}
    if len(served_by_url) != len(server):
        raise ValueError("Safari Karma response URLs are duplicated")
    for index, row in enumerate(responses):
        address = urlsplit(row["url"])
        relative = address.path + ("?" + address.query if address.query else "")
        served = served_by_url.get(relative)
        body_path = f"safari-browser-bodies/{index:04d}.body"
        body = folder / body_path
        if (served is None or row["body_path"] != body_path
                or row["body_size"] != served["size"]
                or row["body_sha256"] != served["sha256"]
                or body.read_bytes() != (folder / served["body_path"]).read_bytes()):
            raise ValueError("Safari browser response URL, body, or process differs")
        served_by_url.pop(relative)
    if served_by_url:
        raise ValueError("Safari browser response witness omitted selected body")
    return responses


def runtime_pin(family, role, browser, selected_sha=None):
    if family in BROWSER_VERSIONS:
        major, pinned = BROWSER_VERSIONS[family][role]
        if selected_sha is not None and selected_sha != pinned:
            raise ValueError("independent browser hash differs from pinned binary")
        return major, pinned
    if selected_sha is None or not HEX64.fullmatch(selected_sha):
        raise ValueError("independent Safari executable SHA-256 is required")
    info = browser.parents[1] / "Info.plist"
    version = plistlib.loads(info.read_bytes())["CFBundleShortVersionString"]
    major = int(version.split(".")[0])
    if (role == "minimum" and version != "18.2"
            or role == "current" and major < 26):
        raise ValueError("Safari version does not satisfy selected role")
    return major, selected_sha


def expected_java_sha256(system, family):
    if system not in ("Linux", "Darwin") or (family == "Safari" and system != "Darwin"):
        raise ValueError("selected browser host differs")
    return DARWIN_JAVA_SHA256 if system == "Darwin" else JAVA_SHA256


def toolchain(gradle, browser, family="Chromium"):
    java_home = Path(os.environ["JAVA_HOME"]).resolve()
    java = java_home / "bin/java"
    java_version = subprocess.check_output([str(java), "-version"],
                                           stderr=subprocess.STDOUT, text=True).splitlines()[0]
    gradle_version = subprocess.check_output([str(gradle), "--version"], text=True)
    browser_version = (plistlib.loads((browser.parents[1] / "Info.plist").read_bytes())[
        "CFBundleShortVersionString"] if family == "Safari" else
        subprocess.check_output([str(browser), "--version"], text=True).strip())
    if ('version "21' not in java_version or "Gradle 9.5.0" not in gradle_version
            or {"Chromium": "Chrome", "Firefox": "Firefox", "Safari": ""}[family]
            not in browser_version or file_hash(java) != expected_java_sha256(
                platform.system(), family)
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


def capture_live_lock(lock, expected, archive, stage, execution):
    if stage not in {"graph", "core", "facade"} or lock.is_symlink():
        raise ValueError("live Yarn lock path differs")
    if any(parent.is_symlink() for parent in lock.parents):
        raise ValueError("live Yarn lock parent is symbolic")
    descriptor = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read()
        after = os.fstat(stream.fileno())
    current = os.stat(lock, follow_symlinks=False)
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
    if (not stat.S_ISREG(after.st_mode) or identity(before) != identity(after)
            or identity(after) != identity(current)):
        raise ValueError("live Yarn lock changed during observation")
    observed_ns = time.time_ns()
    relative = f"lock-observations/{stage}.yarn.lock"
    record = {"stage": stage, "source_path": str(lock), "copy_path": relative,
              "sha256": sha(raw), "expected_sha256": sha(expected),
              "observed_ns": observed_ns, "process_pid": execution["pid"],
              "process_finished_ns": execution["finished_ns"],
              "size": len(raw), "mtime_ns": after.st_mtime_ns,
              "device": after.st_dev, "inode": after.st_ino}
    destination = archive / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    (destination.parent / f"{stage}.json").write_bytes(encoded(record) + b"\n")
    if raw != expected:
        raise ValueError(f"live Yarn lock differs from exact committed fixture after {stage}")
    return record


def verify_live_lock_observations(archive, receipt, expected, lock):
    records = receipt.get("lock_observations")
    if not isinstance(records, list) or len(records) != 3:
        raise ValueError("live Yarn lock observations are incomplete")
    processes = [receipt["process"]["graph"], receipt["modules"]["core"],
                 receipt["modules"]["facade"]]
    end_times = [processes[1]["started_ns"], processes[2]["started_ns"],
                 receipt["process"]["finished_ns"]]
    keys = {"stage", "source_path", "copy_path", "sha256", "expected_sha256",
            "observed_ns", "process_pid", "process_finished_ns", "size",
            "mtime_ns", "device", "inode"}
    for stage, record, execution, end in zip(("graph", "core", "facade"),
                                             records, processes, end_times):
        relative = f"lock-observations/{stage}.yarn.lock"
        if (not isinstance(record, dict) or set(record) != keys
                or record["stage"] != stage or record["source_path"] != str(lock)
                or record["copy_path"] != relative
                or record["sha256"] != sha(expected)
                or record["expected_sha256"] != sha(expected)
                or record["size"] != len(expected)
                or record["process_pid"] != execution["pid"]
                or record["process_finished_ns"] != execution["finished_ns"]
                or any(type(record[key]) is not int or record[key] < 0
                       for key in ("observed_ns", "mtime_ns", "device", "inode"))
                or not execution["finished_ns"] <= record["observed_ns"] <= end
                or (archive / relative).read_bytes() != expected
                or json.loads((archive / "lock-observations" / f"{stage}.json").read_text())
                   != record):
            raise ValueError(f"live Yarn lock observation differs after {stage}")


def capture_archive_root(paths, archive, repository):
    if (not isinstance(paths, dict)
            or set(paths) != {"checkout", "staging", "archive", "inputs", "work"}
            or any(not isinstance(value, str) or not Path(value).is_absolute()
                   or os.path.normpath(value) != value for value in paths.values())
            or paths["checkout"] != str(repository)
            or Path(paths["archive"]).is_relative_to(repository)
            or Path(paths["staging"]).is_relative_to(repository)):
        raise ValueError("external browser provider or archive path differs")
    captured = Path(paths["archive"])
    if (not archive.is_absolute() or not archive.is_dir()
            or archive.is_relative_to(repository)
            or archive.resolve(strict=True) != archive
            or captured.exists() and captured != archive and archive.samefile(captured)):
        raise ValueError("selected browser archive path aliases another location")
    for relative in independent_gates._archive_paths(archive):
        if (archive / relative).stat().st_nlink != 1:
            raise ValueError(f"hardlink in browser archive: {relative}")
    return captured


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


def run(repository, candidate, lane, staging, output, gradle, browser, hashes,
        browser_sha256=None):
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
    target, family, role, configuration = lane_parts(lane)
    major, browser_sha = runtime_pin(family, role, browser, browser_sha256)
    identity = toolchain(gradle, browser, family)
    if identity["browser_sha256"] != browser_sha or not re.search(
            rf"\b{major}\.", identity["browser_version"]):
        raise ValueError("wrong pinned browser binary")
    for module in MODULES:
        if file_hash(staged(staging, module, target)) != hashes[module]:
            raise ValueError(f"independent staged {module} {target} KLIB hash differs")
    inputs_content = input_bytes(repository, candidate, lane)
    run_started = time.time_ns()
    inputs = output.parent / f"{output.name}-inputs"
    if inputs.exists() and any(inputs.iterdir()):
        raise ValueError("original source input directory is not empty")
    inputs.mkdir(parents=True, exist_ok=True)
    for name, data in inputs_content.items():
        (inputs / name).write_bytes(data)
    project_lock = repository / CONSUMER / "kotlin-js-store" / (
        "yarn.lock" if target == "js" else "wasm/yarn.lock")
    if (project_lock.is_symlink()
            or any(parent.is_symlink() for parent in project_lock.parents
                   if parent.is_relative_to(repository))):
        raise ValueError("external consumer lock path is symbolic")
    if project_lock.exists() and project_lock.read_bytes() != inputs_content["consumer-yarn.lock"]:
        raise ValueError("external consumer lock differs from pinned fixture")
    lock_created = not project_lock.exists()
    project_lock.parent.mkdir(parents=True, exist_ok=True)
    if lock_created:
        project_lock.write_bytes(inputs_content["consumer-yarn.lock"])
    output.mkdir(parents=True, exist_ok=True)
    work = output.parent / f"{output.name}-build"
    work.mkdir(parents=True, exist_ok=True)
    runtime = family.lower()
    launcher = repository / (LAUNCHER if family != "Safari" else
                             f"{CONSUMER}/safari_launcher.py")
    chromium_witness = repository / CHROMIUM_WITNESS
    env = dict(os.environ, JAVA_HOME=str(Path(os.environ["JAVA_HOME"]).resolve()),
               YARN_OFFLINE="true", DYN4K_BROWSER=runtime,
               DYN4K_BROWSER_SELECTED_BINARY=str(browser),
               DYN4K_BROWSER_RUNTIME=runtime,
               DYN4K_BROWSER_TARGET=target)
    env[{"Chromium": "CHROME_BIN", "Firefox": "FIREFOX_BIN",
         "Safari": "SAFARI_BIN"}[family]] = str(
             chromium_witness if family == "Chromium" else launcher)
    base = gradle_args(repository, staging, output, work, inputs, lane, hashes, gradle)
    config_roots = []
    processes = {}
    module_rows = {}
    lock_observations = []
    try:
        graph_process = process(base + ["qualificationGraphs"], inputs, env,
                                output / "graph.stdout", output / "graph.stderr")
        lock_observations.append(capture_live_lock(
            project_lock, inputs_content["consumer-yarn.lock"], output,
            "graph", graph_process))
        if graph_process["exit_code"]:
            raise ValueError(f"external {target} provider graph process failed")
        for module, short in (("dyn4k-core", "core"), ("dyn4k", "facade")):
            config_root = repository / CONSUMER / short / "karma.config.d"
            if config_root.exists():
                raise ValueError("consumer Karma configuration is already present")
            config_root.mkdir()
            config_roots.append(config_root)
            reporter = config_root / "qualification-browser-reporter.js"
            port_file = config_root / "qualification-port.js"
            reporter.write_bytes((repository / REPORTER).read_bytes())
            if family == "Safari":
                (config_root / "qualification-z-safari-observer.js").write_bytes(
                    (repository / SAFARI_OBSERVER).read_bytes())
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
            linked, configured, _ = bundle_paths(work, short, configuration, target)
            module_env = dict(env, DYN4K_BROWSER_ATTESTATION=str(launches),
                              DYN4K_BROWSER_TOKEN=token,
                              DYN4K_BROWSER_ORIGINAL_LAUNCHER=str(launcher),
                              DYN4K_BROWSER_CDP_ARCHIVE=str(destination / "chromium-cdp.jsonl"),
                              DYN4K_BROWSER_MODULE=short,
                              DYN4K_BROWSER_CANDIDATE=candidate,
                              DYN4K_BROWSER_REPORTER_ATTESTATION=str(attestation),
                              DYN4K_BROWSER_RAW_KARMA=str(raw_karma),
                              DYN4K_BROWSER_REPORTER_SOURCE=str(reporter),
                              DYN4K_BROWSER_SELECTED_BUNDLE=str(configured),
                              DYN4K_BROWSER_SELECTED_ARCHIVE=str(destination / "karma-selected.js"),
                              DYN4K_BROWSER_ASSETS_ARCHIVE=str(destination / "assets"),
                              DYN4K_BROWSER_SELECTED_ATTESTATION=str(destination / "selected-bundle.json"),
                              DYN4K_BROWSER_HTTP_ARCHIVE=str(destination / "http-responses"),
                              DYN4K_BROWSER_HTTP_ATTESTATION=str(destination / "http-responses.json"),
                              DYN4K_BROWSER_HTTP_SOURCES=str(destination / "http-sources"),
                              DYN4K_BROWSER_WORK_ROOT=str(work),
                              DYN4K_BROWSER_TMPDIR=os.environ["TMPDIR"])
            if family == "Safari":
                module_env.update(
                    DYN4K_BROWSER_KARMA_PORT=str(port),
                    DYN4K_SAFARI_REDIRECT_ARCHIVE=str(destination / "safari-redirect.html"),
                    DYN4K_SAFARI_OBSERVER_ARCHIVE=str(destination),
                    DYN4K_SAFARI_OBSERVER_SOURCE=str(repository / SAFARI_OBSERVER),
                    DYN4K_SAFARI_WORKER_SOURCE=str(repository / SAFARI_WORKER),
                    DYN4K_SAFARI_BOOTSTRAP_SOURCE=str(repository / SAFARI_BOOTSTRAP))
            command = base + [f":{short}:{target}BrowserTest"]
            execution = process(command, inputs, module_env,
                                destination / "gradle.stdout", destination / "gradle.stderr")
            lock_observations.append(capture_live_lock(
                project_lock, inputs_content["consumer-yarn.lock"], output,
                short, execution))
            processes[short] = {**execution, "browser_token": token, "karma_port": port}
            if execution["exit_code"]:
                raise ValueError(f"external {short} {family} process failed")
            xml_root = work / short / f"test-results/{target}BrowserTest"
            reports = sorted(xml_root.glob("TEST-*.xml"))
            if not reports:
                raise ValueError(f"external {short} browser XML is absent")
            selected = selected_map(inputs_content[f"{short}-cases.tsv"])
            observed = []
            for report in reports:
                raw = report.read_bytes()
                observed.extend(rows(raw, selected, major, target, family))
                copy(report, destination / "xml" / report.name)
            if len(observed) != len(selected) or set(observed) != set(selected.values()):
                raise ValueError(f"external {short} full original method set is incomplete")
            karma_rows(raw_karma.read_bytes(), selected, major, family)
            module_rows[short] = observed
            if not linked.is_file():
                raise ValueError(f"external {short} linked {configuration} bundle is absent")
            processes[short]["linked_sha256"] = copy(linked, destination / "linked-executable.js")
            if target == "wasmJs":
                processes[short]["linked_wasm_sha256"] = copy(
                    linked.with_suffix(".wasm"), destination / "linked-executable.wasm")
            package = f"dyn4k-full-staged-browser-consumer-{short}-test"
            generated = work / "root" / ("js" if target == "js" else "wasm") / "packages" / package / "karma.conf.js"
            if (not generated.is_file()
                    or f"config.set({{port: {port}}});" not in generated.read_text()
                    or "DYN4K_BROWSER_RAW_KARMA" not in generated.read_text()):
                raise ValueError("external browser Karma configuration lacks isolated port")
            copy(generated, destination / "karma.conf.js")
            copy(reporter, destination / "browser-reporter.js")
            if family == "Safari":
                copy(repository / SAFARI_OBSERVER, destination / "safari-karma-observer.js")
                copy(repository / SAFARI_WORKER, destination / "safari-response-worker.js")
                copy(repository / SAFARI_BOOTSTRAP, destination / "safari-response-bootstrap.js")
            selected_bundle(destination, work, short, configuration, processes[short], major,
                            require_effective=True, target=target, family=family,
                            require_http=True)
            verify_http_responses(destination, processes[short], target, short)
            if not launches.is_file() or not attestation.is_file() or not raw_karma.is_file():
                raise ValueError("real browser process or reporter producer is absent")
            if json.loads(attestation.read_text()) != {
                    "path": str(reporter), "sha256": file_hash(reporter),
                    "producer_path": reporter_producer_path(destination),
                    "producer_sha256": "7c3232f60952aff254847ae62a866385735e3094197454d755100e962c2f2347"}:
                raise ValueError("Karma reporter producer identity differs")
            observations = [json.loads(line) for line in launches.read_text().splitlines()]
            if not observations or any(not observed_browser(
                    item, token, family, browser, browser_sha) for item in observations):
                raise ValueError("actual pinned browser process image differs")
            if family == "Chromium":
                verify_chromium_process_witness(destination, processes[short],
                    observations, verify_http_responses(destination, processes[short], target, short),
                    short, target, candidate, str(chromium_witness),
                    sha(original(repository, candidate, CHROMIUM_WITNESS)))
            if family == "Safari":
                runpy.run_path(str(repository / SAFARI_WITNESS))["seal"](
                    destination, processes[short], observations, candidate, short, target,
                    str(repository / SAFARI_WITNESS),
                    sha(original(repository, candidate, SAFARI_WITNESS)),
                    sha(original(repository, candidate, SAFARI_WORKER)),
                    sha(original(repository, candidate, SAFARI_BOOTSTRAP)),
                    sha(original(repository, candidate, SAFARI_OBSERVER)))
                verify_safari_response_witness(destination, processes[short],
                    observations, verify_http_responses(destination, processes[short], target, short),
                    short, target, candidate, str(repository / SAFARI_WITNESS),
                    sha(original(repository, candidate, SAFARI_WITNESS)),
                    sha(original(repository, candidate, SAFARI_WORKER)),
                    sha(original(repository, candidate, SAFARI_BOOTSTRAP)),
                    sha(original(repository, candidate, SAFARI_OBSERVER)))
    finally:
        for config_root in config_roots:
            for name in ("qualification-port.js", "qualification-browser-reporter.js",
                         "qualification-z-safari-observer.js"):
                path = config_root / name
                if path.exists():
                    path.unlink()
            if config_root.exists() and not any(config_root.iterdir()):
                config_root.rmdir()
        if (lock_created and project_lock.exists()
                and project_lock.read_bytes() == inputs_content["consumer-yarn.lock"]):
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
    receipt = {"schema": 5 if family == "Safari" else
               4 if family == "Chromium" else 3,
               "status": "PASSED", "lane": lane,
               "candidate_sha": candidate,
               "source_tree": git(repository, "rev-parse", f"{candidate}^{{tree}}").decode().strip(),
               "consumer_contract_sha256": independent_gates.digest(contract(repository, lane)),
               "source_inventory_sha256": sha(inputs_content["source-inventory.tsv"]),
               "consumer_build_sha256": {path: sha(original(repository, candidate, path))
                                          for path in BUILD_PATHS},
               "producer_sha256": sha(original(repository, candidate,
                                               "tools/qualification/full_browser_consumer.py")),
               "browser_support_sha256": {path: sha(original(repository, candidate, path))
                                          for path in (launcher.relative_to(repository).as_posix(), REPORTER,
                                                       *((CHROMIUM_WITNESS,) if family == "Chromium" else
                                                         (SAFARI_WITNESS, SAFARI_OBSERVER,
                                                          SAFARI_WORKER, SAFARI_BOOTSTRAP)
                                                         if family == "Safari" else ()))},
               "toolchain": identity, "staged_hashes": hashes,
               "runtime_identity": f"{platform.system()} {platform.release()} {platform.machine()}",
               "paths": {"checkout": str(repository), "staging": str(staging),
                         "archive": str(output), "inputs": str(inputs), "work": str(work)},
               "process": {"started_ns": run_started, "finished_ns": run_finished,
                           "graph": graph_process}, "modules": processes,
               "lock_observations": lock_observations,
               "row_order_sha256": {short: sha(encoded(values))
                                    for short, values in module_rows.items()},
               "files": [{"path": path.relative_to(output).as_posix(),
                          "sha256": file_hash(path), "mtime_ns": path.stat().st_mtime_ns}
                         for path in sorted(output.rglob("*")) if path.is_file()]}
    (output / "receipt.json").write_bytes(encoded(receipt) + b"\n")
    return receipt


def verify(repository, candidate, lane, archive, digest, binary, hashes,
           browser_sha256=None):
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
    schema = receipt.get("schema")
    has_http_producer = b"DYN4K_BROWSER_HTTP_ARCHIVE" in original(
        repository, candidate, REPORTER)
    has_cdp_producer = b"DYN4K_BROWSER_CDP_ARCHIVE" in original(
        repository, candidate, "tools/qualification/full_browser_consumer.py")
    has_safari_producer = b'SAFARI_WORKER = ' in original(
        repository, candidate, "tools/qualification/full_browser_consumer.py")
    chromium = lane.split(":")[1] == "Chromium"
    safari = lane.split(":")[1] == "Safari"
    if (type(schema) is not int
            or not (schema == 5 and has_http_producer and has_safari_producer and safari
                    or schema == 4 and has_http_producer and has_cdp_producer and chromium
                    or schema == 3 and has_http_producer
                    and not (chromium and has_cdp_producer)
                    and not (safari and has_safari_producer)
                    or schema == 2 and not has_http_producer
                    and candidate not in LEGACY_LOCK_CANDIDATES
                    or schema == 1 and candidate in LEGACY_LOCK_CANDIDATES)
            or receipt.get("status") != "PASSED"
            or receipt.get("lane") != lane or receipt.get("candidate_sha") != candidate
            or receipt.get("source_tree") != git(repository, "rev-parse", f"{candidate}^{{tree}}").decode().strip()
            or receipt.get("consumer_contract_sha256") != independent_gates.digest(selected)):
        raise ValueError("browser receipt differs from exact candidate or lane")
    inputs = input_bytes(repository, candidate, lane)
    for name, raw in inputs.items():
        if (archive / "inputs" / name).read_bytes() != raw:
            raise ValueError(f"archived original source or method input differs: {name}")
    if schema in (2, 3, 4, 5):
        target = lane_parts(lane)[0]
        lock = repository / CONSUMER / "kotlin-js-store" / (
            "yarn.lock" if target == "js" else "wasm/yarn.lock")
        verify_live_lock_observations(archive, receipt, inputs["consumer-yarn.lock"], lock)
    elif "lock_observations" in receipt:
        raise ValueError("historical browser receipt has unexpected live Yarn lock observations")
    if receipt.get("source_inventory_sha256") != sha(inputs["source-inventory.tsv"]):
        raise ValueError("original source inventory hash differs")
    if receipt.get("consumer_build_sha256") != {
            path: sha(original(repository, candidate, path)) for path in BUILD_PATHS}:
        raise ValueError("exact external browser consumer source differs")
    if receipt.get("producer_sha256") != sha(original(
            repository, candidate, "tools/qualification/full_browser_consumer.py")):
        raise ValueError("browser producer source differs")
    support = (LAUNCHER if lane.split(":")[1] != "Safari" else
               f"{CONSUMER}/safari_launcher.py")
    if receipt.get("browser_support_sha256") != {
            path: sha(original(repository, candidate, path)) for path in
            (support, REPORTER, *((CHROMIUM_WITNESS,) if schema == 4 else
                                  (SAFARI_WITNESS, SAFARI_OBSERVER, SAFARI_WORKER,
                                   SAFARI_BOOTSTRAP) if schema == 5 else ())) }:
        raise ValueError("browser launcher or reporter source differs")
    target, family, role, mode = lane_parts(lane)
    major, pinned = runtime_pin(family, role, binary, browser_sha256)
    if (file_hash(binary) != pinned or receipt["toolchain"]["browser_sha256"] != pinned
            or Path(receipt["toolchain"]["browser"]) != binary
            or not re.search(rf"\b{major}\.", receipt["toolchain"]["browser_version"])):
        raise ValueError("wrong browser binary or version")
    if receipt.get("staged_hashes") != hashes:
        raise ValueError("independently selected staged KLIB hashes differ")
    runtime_identity = receipt.get("runtime_identity")
    if (type(runtime_identity) is not str
            or not re.fullmatch(r"(Linux|Darwin) [^ ]+ [^ ]+", runtime_identity)):
        raise ValueError("browser runtime host identity differs")
    if (receipt["toolchain"].get("java_sha256") != expected_java_sha256(
            runtime_identity.split(" ", 1)[0], family)
            or receipt["toolchain"].get("gradle_sha256") != GRADLE_SHA256
            or receipt["toolchain"].get("kgp_version") != "2.4.20"):
        raise ValueError("pinned JDK, Gradle, or KGP identity differs")
    paths = receipt["paths"]
    captured_archive = capture_archive_root(paths, archive, repository)
    gradle = Path(receipt["toolchain"]["gradle"])
    base = gradle_args(repository, Path(paths["staging"]), captured_archive,
                       Path(paths["work"]),
                       Path(paths["inputs"]), lane, hashes, gradle)
    graph_process = receipt["process"].get("graph", {})
    if (graph_process.get("command") != base + ["qualificationGraphs"]
            or graph_process.get("cwd") != paths["inputs"]
            or graph_process.get("exit_code") != 0
            or type(graph_process.get("pid")) is not int
            or graph_process["pid"] <= 0):
        raise ValueError("original external provider graph process differs")
    for module, short in (("dyn4k-core", "core"), ("dyn4k", "facade")):
        variant = publication(target)
        if (file_hash(archive / "resolved" / f"{module}-{variant}-{VERSION}.klib") != hashes[module]
                or file_hash(staged(Path(receipt["paths"]["staging"]), module, target)) != hashes[module]):
            raise ValueError("transported or staged provider KLIB differs")
        source = selected_map(inputs[f"{short}-cases.tsv"])
        folder = archive / short
        xml = sorted((folder / "xml").glob("TEST-*.xml"))
        if not xml:
            raise ValueError("raw browser XML is absent")
        observed = [identity for report in xml
                    for identity in rows(report.read_bytes(), source, major, target, family)]
        if len(observed) != len(source) or set(observed) != set(source.values()):
            raise ValueError("full original browser method rows differ")
        if receipt["row_order_sha256"].get(short) != sha(encoded(observed)):
            raise ValueError("original browser method order differs")
        record = receipt["modules"][short]
        if (file_hash(folder / "browser-reporter.js") != receipt["browser_support_sha256"][REPORTER]
                or file_hash(folder / "linked-executable.js") != record["linked_sha256"]):
            raise ValueError("browser reporter or linked bundle differs")
        launches = [json.loads(line) for line in (folder / "browser-launches.jsonl").read_text().splitlines()]
        if (record.get("command") != base + [f":{short}:{target}BrowserTest"]
                or record.get("cwd") != paths["inputs"]
                or type(record.get("pid")) is not int
                or type(record.get("parent_pid")) is not int
                or record["parent_pid"] != graph_process.get("parent_pid")):
            raise ValueError("original external browser process command differs")
        if not launches or any(not observed_browser(
                item, record["browser_token"], family, binary, pinned)
                for item in launches):
            raise ValueError("real browser process identity differs")
        if (record["exit_code"] != 0 or record["pid"] <= 0
                or record["started_ns"] > record["finished_ns"]
                or file_hash(folder / "karma.conf.js") == sha(b"")):
            raise ValueError("original Gradle or Karma process differs")
        selected_bundle(folder, Path(paths["work"]), short, mode, record, major,
                        require_effective=not (
                            candidate == LEGACY_CANDIDATE_SHA
                            and receipt["browser_support_sha256"][REPORTER]
                            == LEGACY_REPORTER_SHA256), target=target, family=family,
                        observed_folder=captured_archive / short,
                        require_http=schema in (3, 4, 5))
        if schema in (3, 4, 5):
            served = verify_http_responses(folder, record, target, short)
            if schema == 4:
                witness_source = original(repository, candidate, CHROMIUM_WITNESS)
                has_live_source = b"source_sha256: hash(fs.readFileSync(__filename))" in witness_source
                verify_chromium_process_witness(folder, record, launches, served,
                                                short, target, candidate,
                                                str(repository / CHROMIUM_WITNESS)
                                                if has_live_source else None,
                                                sha(witness_source) if has_live_source else None)
            if schema == 5:
                verify_safari_response_witness(folder, record, launches, served,
                    short, target, candidate, str(repository / SAFARI_WITNESS),
                    sha(original(repository, candidate, SAFARI_WITNESS)),
                    sha(original(repository, candidate, SAFARI_WORKER)),
                    sha(original(repository, candidate, SAFARI_BOOTSTRAP)),
                    sha(original(repository, candidate, SAFARI_OBSERVER)))
        text = (folder / "gradle.stdout").read_text()
        package = f"dyn4k-full-staged-browser-consumer-{short}-test"
        expected_bundle = bundle_paths(Path(paths["work"]), short, mode, target)[0]
        optimized_package = (Path(paths["work"]) / "root/wasm/packages" / package /
                             "kotlin" / f"{package}.mjs")
        if (f"> Task :{short}:{target}BrowserTest" not in text
                or "BUILD SUCCESSFUL" not in text or " FAILED" in text
                or f"QUALIFICATION_LANE={lane}" not in (archive / "graph.stdout").read_text()
                or (mode == "production" and
                    f"qualification test input: {expected_bundle}" not in text)
                or (target == "wasmJs" and mode == "production" and
                    f"qualification optimized package input: {optimized_package}" not in text)):
            raise ValueError("raw process output omits selected browser task or bundle")
        attested = json.loads((folder / "reporter-producer.json").read_text())
        if attested != {"path": str(repository / CONSUMER / short / "karma.config.d"
                                     / "qualification-browser-reporter.js"),
                        "sha256": receipt["browser_support_sha256"][REPORTER],
                        "producer_path": reporter_producer_path(folder)
                                         if candidate != LEGACY_CANDIDATE_SHA else
                                         f"{paths['work']}/root/js/node_modules/"
                                         "kotlin-web-helpers/dist/karma-kotlin-reporter.js",
                        "producer_sha256": "7c3232f60952aff254847ae62a866385735e3094197454d755100e962c2f2347"}:
            raise ValueError("browser reporter producer attestation differs")
        karma_rows((folder / "raw-karma.jsonl").read_bytes(), source, major, family)
    graph = independent_gates._json(archive / "provider-graph.json")
    if (set(graph) != {"compile", "runtime", "gradle_user_home"}
            or graph["gradle_user_home"] != receipt["toolchain"]["gradle_user_home"]):
        raise ValueError("browser provider graph is incomplete")
    configuration_prefix = "jsTest" if target == "js" else "wasmJsTest"
    for phase, configuration in (("compile", f"{configuration_prefix}CompileClasspath"),
                                 ("runtime", f"{configuration_prefix}RuntimeClasspath")):
        entries = graph[phase]
        if len(entries) != 2 or {item["project"] for item in entries} != {"core", "facade"}:
            raise ValueError("both external browser provider graphs are required")
        for entry in entries:
            roots = {f"io.github.rubixhacker:{module}:{VERSION}" for module in MODULES}
            variants = {f"io.github.rubixhacker:{module}-{publication(target)}:{VERSION}"
                        for module in MODULES}
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
                            if value["component"] ==
                            f"io.github.rubixhacker:{module}-{publication(target)}:{VERSION}")
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
        selected.add_argument("--browser-sha256")
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
                         args.output, args.gradle, args.browser, hashes,
                         args.browser_sha256)
            result = {"status": result["status"], "lane": args.lane,
                      "selected_cases": 2523, "archive": str(args.output),
                      "archive_sha256": independent_gates.archive_digest(args.output)}
        else:
            result = verify(args.repository, args.candidate, args.lane, args.archive,
                            args.archive_sha256, args.browser, hashes,
                            args.browser_sha256)
        print(json.dumps(result, sort_keys=True))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"NOT_RUN: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
