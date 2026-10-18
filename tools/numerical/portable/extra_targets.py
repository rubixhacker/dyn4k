#!/usr/bin/env python3
import argparse
import gzip
import hashlib
import html
import json
import os
import re
import selectors
import shutil
import signal
import socket
import subprocess
import sys
import time
import xml.sax
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cases import declared_cases
from receipt import Identity, Rejected, digest, records, seal


ROOT = Path(__file__).resolve().parents[3]
PORTABLE = Path(__file__).resolve().parent
VERSION = "0.1.0-alpha.1"
GROUP = ROOT / "build/staging-repository/io/github/rubixhacker"
ANDROID_GUEST_FINGERPRINT = "google/sdk_gphone64_x86_64/emu64xa:17/CE2A.260420.019/15611780:user/release-keys"
METHODS = frozenset((
    "geometryCollisionBoundaryAndScale", "freeMotionForcesDampingAndRestitution",
    "defaultContactsFrictionSleepAndWake", "configured30Repeat1", "configured30Repeat2",
    "configured60Repeat1", "configured60Repeat2", "configured120Repeat1",
    "configured120Repeat2", "everyJointWithInitialAndApplicableActiveModes",
    "independentJointBooleanModes", "independentJointNumericAndLimitModes",
    "baselineAngleNegativeRatioRemainsAnIsolatedPhysicalFailure",
    "continuousCollisionCasesAtFrozenRates", "longRunningFreeMotionInvariantScene",
))
RECORDER_METHODS = frozenset(("frozenConfigurationUsesCommonWorldGetters",
                              "recordsPublicWorldStateAndSignedZeroAtEveryStep"))
ALL_METHODS = METHODS | RECORDER_METHODS
WASM_HELPERS = ("custom-formatters.js", "dyn4k-portable-numerical-consumer-test.import-object.mjs",
                "dyn4k-portable-numerical-consumer-test.js-builtins.mjs")


def method_for_case(case):
    case_id = case["id"]
    family = case["family"]
    if family == "geometry-collision":
        return "geometryCollisionBoundaryAndScale"
    if family == "free-motion":
        return "freeMotionForcesDampingAndRestitution"
    if case_id.startswith("contacts-default-"):
        return "defaultContactsFrictionSleepAndWake"
    if case_id.startswith("contacts-configured-"):
        values = case["input"]
        return f"configured{values['outerHz']}Repeat{values['repetition']}"
    if case_id.startswith("P-JINT-") or case.get("input", {}).get("mode") in ("initial", "active"):
        return "everyJointWithInitialAndApplicableActiveModes"
    if case.get("input", {}).get("variant") in ("false", "true", "toggle"):
        return "independentJointBooleanModes"
    if case_id == "P-J-Angle-ratio-limits-off--1.0":
        return "baselineAngleNegativeRatioRemainsAnIsolatedPhysicalFailure"
    if family == "joints-limits-motors":
        return "independentJointNumericAndLimitModes"
    if family == "ccd":
        return "continuousCollisionCasesAtFrozenRates"
    if family == "long-running-invariant":
        return "longRunningFreeMotionInvariantScene"
    raise Rejected(f"case has no portable method: {case_id}")


def verify_gzip_bytes(path, compressed_hash, plain_hash, plain_size, target=None):
    path = Path(path)
    if not path.is_file() or digest(path) != compressed_hash:
        raise Rejected(f"compressed stream is absent or changed: {path}")
    actual = hashlib.sha256()
    size = 0
    try:
        with gzip.open(path, "rb") as stream:
            while chunk := stream.read(1024 * 1024):
                actual.update(chunk)
                size += len(chunk)
                if target is not None:
                    target.write(chunk)
    except (OSError, EOFError) as error:
        raise Rejected(f"compressed stream is truncated: {path}") from error
    if actual.hexdigest() != plain_hash or size != plain_size:
        raise Rejected(f"uncompressed stream differs: {path}")


def verify_browser_xml_source(xml_streams, raw):
    if not xml_streams:
        raise Rejected("browser XML archives are absent")
    extracted = hashlib.sha256()
    extracted_bytes = 0
    for name, item in sorted(xml_streams.items()):
        if not name.startswith("TEST-") or not name.endswith(".xml"):
            raise Rejected("browser XML archive name differs")
        verify_gzip_bytes(item["path"], item["gzip_sha256"], item["plain_sha256"],
                          item["plain_bytes"])
        with gzip.open(item["path"], "rb") as stream:
            for line in stream:
                if b"NUMERICAL_JSON " in line:
                    extracted.update(line)
                    extracted_bytes += len(line)
    if extracted.hexdigest() != raw["plain_sha256"] or extracted_bytes != raw["plain_bytes"]:
        raise Rejected("browser XML numerical output differs from raw stream")


def verify_segments(manifest_path, output, replay_source=None):
    manifest = json.loads(Path(manifest_path).read_text())
    if manifest.get("schema") not in ("portable-numerical-segments/1", "portable-numerical-segments/2",
                                      "portable-numerical-segments/3"):
        raise Rejected("segment manifest schema differs")
    route = ROUTES.get(manifest.get("route"))
    if route is None or manifest.get("target") != route.target:
        raise Rejected("segment target differs")
    current = git("rev-parse", "HEAD").decode().strip()
    source = replay_source or current
    if not re.fullmatch(r"[0-9a-f]{40}", source):
        raise Rejected("replay source must be an exact commit")
    if (manifest.get("candidate_commit") != source or
            manifest.get("source_sha256") != hashlib.sha256(git("archive", "--format=tar", source)).hexdigest()):
        raise Rejected("segment source differs")
    for key in ("artifact", "linked_executable"):
        value = manifest[key]
        if not Path(value["path"]).is_file() or digest(Path(value["path"])) != value["sha256"]:
            raise Rejected(f"segment {key} is absent or changed")
    runner = Path(manifest["runner"])
    process = manifest["process"]
    if process.get("timed_out"):
        raise Rejected("target process timed out")
    verify_process(runner, manifest["runner_sha256"], process.get("exit_code"),
                   process.get("command"))
    linked = manifest["linked_executable"]
    command = process["command"]
    if route.kind in ("wasmtime", "hosted-native") and command.count(linked["path"]) != 1:
        raise Rejected("target process did not select the linked executable")
    if route.kind == "wasmtime" and manifest.get("bounded_geometry") and \
            command[-3:] != ["portable-numerical", "--include",
                            "portable.PortableMatrixTest.geometryCollisionBoundaryAndScale"]:
        raise Rejected("bounded Wasmtime process did not select the geometry method")
    if route.kind == "android-guest":
        guest = manifest.get("guest", {})
        if guest.get("remote_sha256") != linked["sha256"] or command.count(guest.get("remote")) != 1:
            raise Rejected("guest process did not select the deployed linked executable")
    raw = manifest["raw_stream"]
    verify_gzip_bytes(raw["path"], raw["gzip_sha256"], raw["plain_sha256"], raw["plain_bytes"])
    if route.kind == "browser" and manifest["schema"] != "portable-numerical-segments/3":
        verify_browser_xml_source(manifest.get("xml_streams"), raw)
    cases = selected_capture_cases(route, manifest.get("bounded_geometry", False),
                                   manifest.get("bounded_methods"))
    if route.kind == "browser":
        if manifest["schema"] in ("portable-numerical-segments/2", "portable-numerical-segments/3"):
            verify_browser_invocations(manifest, route, cases)
        elif not manifest.get("bounded_geometry"):
            raise Rejected("full browser capture has no method-bound invocation ledger")
    entries = manifest["segments"]
    if len(entries) != len(cases):
        raise Rejected("segment case count differs")
    observed = observed_segment_hashes(Path(raw["path"]), cases, route.kind,
                                       manifest.get("xml_streams"), route.task,
                                       manifest.get("browser_invocations")
                                       if manifest["schema"] == "portable-numerical-segments/3" else None)
    output = Path(output)
    if output.exists():
        raise Rejected("assembled trace already exists")
    try:
        with output.open("xb") as assembled:
            for index, (entry, case) in enumerate(zip(entries, cases)):
                if entry["case_id"] != case["id"] or entry["method"] != method_for_case(case):
                    raise Rejected(f"segment case or method order differs at {index}")
                if entry["observed_index"] != index:
                    raise Rejected(f"segment process order differs at {index}")
                if any(entry[key] != observed[case["id"]][key] for key in
                       ("plain_sha256", "plain_bytes", "rows", "observed_index")):
                    raise Rejected(f"segment differs from raw process output: {case['id']}")
                segment = Path(entry["path"])
                verify_gzip_bytes(segment, entry["gzip_sha256"], entry["plain_sha256"],
                                  entry["plain_bytes"], assembled)
                row_count = 0
                first = last = None
                with gzip.open(segment, "rt", encoding="utf-8") as stream:
                    for line in stream:
                        if not line.endswith("\n"):
                            raise Rejected("segment row lacks newline")
                        row = json.loads(line)
                        if row.get("id") != case["id"]:
                            raise Rejected("segment row case differs")
                        first = row.get("kind") if row_count == 0 else first
                        last = row.get("kind")
                        row_count += 1
                if row_count != entry["rows"] or first != "inputs" or last != "case-end":
                    raise Rejected("segment is incomplete or row count differs")
    except (KeyError, TypeError, OSError, EOFError, json.JSONDecodeError) as error:
        output.unlink(missing_ok=True)
        raise Rejected(f"segment manifest or trace is malformed: {error}") from error
    except Rejected:
        output.unlink(missing_ok=True)
        raise
    return {"cases": len(cases), "trace_sha256": digest(output), "trace_bytes": output.stat().st_size,
            "source_commit": source, "historical_replay": source != current}


def expected_class(name):
    if name in METHODS:
        return "PortableMatrixTest"
    if name in RECORDER_METHODS:
        return "RecorderTest"
    raise Rejected(f"unexpected portable test method: {name}")


@dataclass(frozen=True)
class Route:
    target: str
    task: str
    runtime: str
    kind: str


ROUTES = {
    "jvm": Route("jvm", "jvmTest", "JVM", "original"),
    "android-host": Route("android", "testAndroidHostTest", "Android host JVM", "original"),
    "node-js": Route("js", "jsNodeTest", "Node.js", "original"),
    "node-wasm-js": Route("wasmJs", "wasmJsNodeTest", "Node.js", "original"),
    "node-wasm-wasi": Route("wasmWasi", "wasmWasiNodeTest", "Node.js", "original"),
    "linux-x64": Route("linuxX64", "linuxX64Test", "Linux x86_64", "original"),
    "js-chromium": Route("js", "jsBrowserTest", "Chromium", "browser"),
    "js-firefox": Route("js", "jsBrowserTest", "Firefox", "browser"),
    "wasm-js-chromium": Route("wasmJs", "wasmJsBrowserTest", "Chromium", "browser"),
    "wasm-js-firefox": Route("wasmJs", "wasmJsBrowserTest", "Firefox", "browser"),
    "wasm-wasi-wasmtime": Route("wasmWasi", "compileTestDevelopmentExecutableKotlinWasmWasi",
                                 "Wasmtime", "wasmtime"),
}
for _name in ("linuxArm64", "mingwX64", "macosArm64", "iosArm64", "iosSimulatorArm64",
              "iosX64", "tvosArm64", "tvosSimulatorArm64", "watchosArm64",
              "watchosDeviceArm64", "watchosSimulatorArm64", "androidNativeArm32",
              "androidNativeArm64", "androidNativeX86", "androidNativeX64"):
    _key = re.sub(r"([a-z])([A-Z])", r"\1-\2", _name).lower()
    ROUTES[_key] = Route(_name, f"linkDebugTest{_name[0].upper()}{_name[1:]}",
                         "Android API 37 x86_64 guest" if _name == "androidNativeX64" else _name,
                         "android-guest" if _name == "androidNativeX64" else "hosted-native")


def git(*args):
    result = subprocess.run(("git", *args), cwd=ROOT, capture_output=True, check=True)
    return result.stdout


def source_identity():
    dirty = git("status", "--porcelain", "--untracked-files=all").decode().strip()
    ignored = git("ls-files", "--others", "--ignored", "--exclude-standard", "--",
                  "tools/numerical/portable/src").decode().splitlines()
    if dirty or ignored:
        raise Rejected("source tree is dirty or contains ignored portable source")
    return (git("rev-parse", "HEAD").decode().strip(),
            hashlib.sha256(git("archive", "--format=tar", "HEAD")).hexdigest())


def artifact(target):
    suffix = {"wasmJs": "wasm-js", "wasmWasi": "wasm-wasi"}.get(target, target.lower())
    extension = "jar" if target == "jvm" else "aar" if target == "android" else "klib"
    name = f"dyn4k-core-{suffix}"
    return GROUP / name / VERSION / f"{name}-{VERSION}.{extension}"


def browser_lock_task(target):
    if target == "js":
        return "kotlinUpgradeYarnLock"
    if target == "wasmJs":
        return "kotlinWasmUpgradeYarnLock"
    raise Rejected("unknown browser target")


KARMA_REPORTER_PATCH = "\n".join((
    "const portableReporter = config.plugins.find(plugin => plugin['reporter:karma-kotlin-reporter']);",
    "if (!portableReporter) throw new Error('portable Kotlin reporter is absent');",
    "const originalReporter = portableReporter['reporter:karma-kotlin-reporter'][1];",
    "function LineSeparatedReporter(...dependencies) {",
    "    originalReporter.apply(this, dependencies);",
    "    const originalWrite = this.write;",
    "    this.write = function(message) { originalWrite.call(this, message + '\\n'); };",
    "    const fs = require('fs');",
    "    const consoleFile = fs.openSync(__NUMERICAL_CAPTURE__, 'wx');",
    "    const originalBrowserLog = this.onBrowserLog;",
    "    this.onBrowserLog = function(browser, log, type) {",
    "        const index = log.indexOf('NUMERICAL_JSON ');",
    "        if (index < 0) return originalBrowserLog(browser, log, type);",
    "        const message = log.startsWith(\"'\") && log.endsWith(\"'\") ? log.slice(1, -1) : log;",
    "        fs.writeSync(consoleFile, message + '\\n');",
    "    };",
    "    const originalRunComplete = this.onRunComplete;",
    "    this.onRunComplete = function(...args) {",
    "        try { originalRunComplete.apply(this, args); } finally { fs.closeSync(consoleFile); }",
    "    };",
    "}",
    "LineSeparatedReporter.$inject = originalReporter.$inject;",
    "portableReporter['reporter:karma-kotlin-reporter'] = ['type', LineSeparatedReporter];",
    "",
))


@contextmanager
def isolated_karma_port(project, excluded=(), numerical_output=None):
    config_dir = project / "karma.config.d"
    if config_dir.exists():
        raise Rejected(f"Karma configuration directory is already present: {config_dir}")
    for _ in range(32):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        if port not in excluded:
            break
    else:
        raise Rejected("could not reserve a distinct Karma port")
    content = (f"config.set({{port: {port}}});\n"
               "config.set({pingTimeout: 28800000, browserNoActivityTimeout: 28800000, "
               "browserDisconnectTimeout: 28800000, browserSocketTimeout: 28800000});\n"
               + KARMA_REPORTER_PATCH.replace(
                   "__NUMERICAL_CAPTURE__", json.dumps(str(numerical_output or config_dir / "numerical.jsonl"))))
    config_dir.mkdir()
    config = config_dir / "portable-port.js"
    try:
        config.write_text(content)
        yield port
    finally:
        if config.is_file() and config.read_text() == content:
            config.unlink()
        if config_dir.is_dir() and not any(config_dir.iterdir()):
            config_dir.rmdir()


def verify_karma_port(generated, port, numerical_output=None):
    if not generated.is_file():
        raise Rejected("browser test did not load isolated Karma port")
    content = generated.read_text()
    if f"config.set({{port: {port}}});" not in content:
        raise Rejected("browser test did not load isolated Karma port")
    if not all(f"{key}: 28800000" in content for key in
               ("pingTimeout", "browserNoActivityTimeout", "browserDisconnectTimeout",
                "browserSocketTimeout")):
        raise Rejected("browser test did not load long-method timeout")
    patch = KARMA_REPORTER_PATCH.replace(
        "__NUMERICAL_CAPTURE__", json.dumps(str(numerical_output or Path(generated).parent / "numerical.jsonl")))
    if patch not in content:
        raise Rejected("browser test did not load line-separated reporter")


def bounded_gradle_filter(route, enabled):
    return ["--tests", "portable.PortableMatrixTest.geometryCollisionBoundaryAndScale"] \
        if enabled and route.kind == "browser" else []


def verify_inputs(expected_source, observed_source, expected_target, observed_target,
                  artifact_path, artifact_sha256):
    if expected_source != observed_source or not re.fullmatch(r"[0-9a-f]{40}", expected_source):
        raise Rejected("executed source commit differs")
    if expected_target != observed_target:
        raise Rejected("executed target differs")
    if not artifact_path.is_file() or digest(artifact_path) != artifact_sha256:
        raise Rejected("staged target artifact is absent or changed")


def verify_process(runner, expected_sha256, exit_code, command):
    if not runner.is_file() or digest(runner) != expected_sha256:
        raise Rejected("executed runner image is absent or changed")
    if not command or Path(command[0]).resolve() != runner.resolve():
        raise Rejected("process did not start the selected runner")
    if exit_code != 0:
        raise Rejected(f"target process exited {exit_code}")


def runtime_version(runner, expected):
    if not expected or not re.fullmatch(r"\d+(?:\.\d+)+", expected):
        raise Rejected("selected runtime version is absent")
    probe = subprocess.run([str(runner), "--version"], capture_output=True, text=True)
    raw = (probe.stdout + probe.stderr).strip()
    if probe.returncode or not re.search(rf"(?<![\d.]){re.escape(expected)}(?![\d.])", raw):
        raise Rejected("selected runtime version differs")
    return raw.splitlines()[0]


def verify_methods(observed, expected=ALL_METHODS):
    if set(observed) != set(expected) or any(value != "passed" for value in observed.values()):
        raise Rejected(f"portable methods differ: missing={sorted(set(expected)-set(observed))}; "
                       f"extra={sorted(set(observed)-set(expected))}; "
                       f"not_passed={sorted(key for key, value in observed.items() if value != 'passed')}")


def open_text(path):
    return gzip.open(path, "rt", encoding="utf-8", errors="strict") if Path(path).suffix == ".gz" \
        else Path(path).open("r", encoding="utf-8", errors="strict")


def trace_row(line, xml_encoded=False):
    payload = line.split("NUMERICAL_JSON ", 1)[1].split("]]>", 1)[0].strip()
    if xml_encoded:
        payload = html.unescape(payload)
    row = json.loads(payload, parse_constant=lambda value: (_ for _ in ()).throw(Rejected(value)))
    if not isinstance(row, dict) or "kind" not in row or "id" not in row:
        raise Rejected("numerical trace row is malformed")
    return row


def output_rows(line, xml_encoded=False):
    if line.startswith("##teamcity[testStdOut "):
        match = re.search(r" out='(.*?)' flowId=", line)
        if match is None:
            raise Rejected("Wasmtime trace output is malformed")
        value = match.group(1)
        decoded = []
        index = 0
        while index < len(value):
            if value[index] == "|" and index + 1 < len(value):
                decoded.append({"n": "\n", "r": "\r", "'": "'", "[": "[",
                                "]": "]", "|": "|"}.get(value[index + 1], value[index + 1]))
                index += 2
            else:
                decoded.append(value[index])
                index += 1
        lines = "".join(decoded).splitlines()
    else:
        lines = (line,)
    for candidate in lines:
        if "NUMERICAL_JSON " in candidate:
            yield trace_row(candidate, xml_encoded)


def trace_rows(raw, xml_encoded=False):
    with open_text(raw) as source:
        for line in source:
            yield from output_rows(line, xml_encoded)


def browser_xml_rows(xml_streams, task):
    if not xml_streams:
        raise Rejected("browser method XML archives are absent")

    class BoundXml(xml.sax.handler.ContentHandler):
        def __init__(self):
            self.current = None
            self.methods = set()
            self.output_method = None
            self.in_output = False
            self.pending = ""
            self.rows = deque()

        def startElement(self, name, attrs):
            if name == "testcase":
                method = attrs.get("name", "").split("[", 1)[0]
                if attrs.get("classname") != f"{task}.portable.{expected_class(method)}":
                    raise Rejected("browser XML method class differs")
                self.current = method
                self.methods.add(method)
            elif name == "system-out":
                self.in_output = True
                self.output_method = self.current or (next(iter(self.methods)) if len(self.methods) == 1 else None)
            elif name in ("failure", "error", "skipped", "ignored") and self.current is not None:
                raise Rejected("browser numerical method did not pass")

        def characters(self, content):
            if not self.in_output:
                return
            self.pending += content
            while "\n" in self.pending:
                line, self.pending = self.pending.split("\n", 1)
                self.record(line)

        def record(self, line):
            if "NUMERICAL_JSON " in line:
                if self.output_method is None:
                    raise Rejected("browser numerical row has no enclosing test method")
                self.rows.append((trace_row(line), self.output_method))

        def endElement(self, name):
            if name == "system-out":
                self.record(self.pending)
                self.pending = ""
                self.in_output = False
                self.output_method = None
            elif name == "testcase":
                self.current = None

    for name, item in sorted(xml_streams.items()):
        handler = BoundXml()
        parser = xml.sax.make_parser()
        parser.setContentHandler(handler)
        with gzip.open(item["path"], "rb") as stream:
            while chunk := stream.read(128 * 1024):
                parser.feed(chunk)
                while handler.rows:
                    yield handler.rows.popleft()
        parser.close()
        while handler.rows:
            yield handler.rows.popleft()


def process_method_rows(raw, kind):
    active = None
    started = set()
    with open_text(raw) as source:
        for line in source:
            if kind == "wasmtime":
                event = re.match(r"^##teamcity\[(testStarted|testFinished|testFailed|testIgnored|testStdOut) name='([^']*)'", line)
                if event:
                    action, name = event.groups()
                    if action == "testStarted":
                        if active is not None or name not in ALL_METHODS:
                            raise Rejected("Wasmtime numerical method start differs")
                        active = name
                        started.add(name)
                    elif action in ("testFinished", "testFailed", "testIgnored"):
                        if active != name or action != "testFinished":
                            raise Rejected("Wasmtime numerical method did not pass")
                        active = None
                    elif active != name:
                        raise Rejected("Wasmtime numerical stdout method differs")
            else:
                start = re.match(r"\[ RUN\s+\] portable\.(PortableMatrixTest|RecorderTest)\.(\w+)", line)
                end = re.match(r"\[\s+OK\s+\] portable\.(PortableMatrixTest|RecorderTest)\.(\w+)", line)
                if start:
                    if active is not None or expected_class(start.group(2)) != start.group(1):
                        raise Rejected("native numerical method start differs")
                    active = start.group(2)
                    started.add(active)
                elif end:
                    if active != end.group(2) or expected_class(end.group(2)) != end.group(1):
                        raise Rejected("native numerical method completion differs")
                    active = None
                elif re.match(r"\[\s+(FAILED|SKIPPED|DISABLED)\s+\]", line):
                    raise Rejected("native numerical method did not pass")
            for row in output_rows(line):
                if active is None or active not in started:
                    raise Rejected("numerical row has no executed process method")
                yield row, active
    if active is not None:
        raise Rejected("numerical process method is unfinished")


def browser_console_rows(invocations):
    for item in invocations:
        for row in trace_rows(item["raw_stream"]["path"]):
            yield row, item["method"]


def bound_rows(raw, kind, xml_streams=None, task=None, browser_invocations=None):
    if kind == "browser":
        source_rows = browser_console_rows(browser_invocations) if browser_invocations is not None else \
            browser_xml_rows(xml_streams, task)
        for raw_row, source in zip_longest(trace_rows(raw, browser_invocations is None), source_rows):
            if raw_row is None or source is None or raw_row != source[0]:
                raise Rejected("browser method row differs from raw numerical stream")
            yield raw_row, source[1]
    else:
        yield from process_method_rows(raw, kind)


def observed_segment_hashes(raw, cases, kind=None, xml_streams=None, task=None,
                            browser_invocations=None):
    expected = {case["id"] for case in cases}
    ordered = [case["id"] for case in cases]
    completed = {}
    active = None
    source = bound_rows(raw, kind, xml_streams, task, browser_invocations) if kind else \
        ((row, None) for row in trace_rows(raw))
    for row, method in source:
        case_id = row["id"]
        if row["kind"] == "inputs":
            if active is not None or case_id not in expected or case_id in completed:
                raise Rejected("raw stream has duplicate, unexpected, or interleaved case")
            if case_id != ordered[len(completed)]:
                raise Rejected("raw process case order differs from declaration")
            if method is not None and method != method_for_case(cases[len(completed)]):
                raise Rejected("numerical case did not run in its declared method")
            active = {"case_id": case_id, "hash": hashlib.sha256(), "plain_bytes": 0,
                      "rows": 0, "method": method}
        if active is None or case_id != active["case_id"]:
            raise Rejected("raw numerical row is outside its case")
        if kind and method != active["method"]:
            raise Rejected("numerical row changed executed method inside case")
        encoded = (json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
        active["hash"].update(encoded)
        active["plain_bytes"] += len(encoded)
        active["rows"] += 1
        if row["kind"] == "case-end":
            completed[case_id] = {"plain_sha256": active["hash"].hexdigest(),
                                  "plain_bytes": active["plain_bytes"], "rows": active["rows"],
                                  "observed_index": len(completed)}
            active = None
    if active is not None or set(completed) != expected:
        raise Rejected("raw numerical case inventory is incomplete")
    return completed


def segment_trace(raw, directory, cases, started_ns, kind=None, xml_streams=None, task=None,
                  browser_invocations=None):
    if not raw.is_file() or raw.stat().st_mtime_ns < started_ns:
        raise Rejected("trace source is absent or stale")
    expected = {case["id"]: case for case in cases}
    ordered = [case["id"] for case in cases]
    if len(expected) != len(cases):
        raise Rejected("case declaration has duplicate ids")
    directory.mkdir()
    completed = {}
    active = None
    xml_encoded = kind is True
    if isinstance(kind, bool):
        kind = None
    try:
        source = bound_rows(raw, kind, xml_streams, task, browser_invocations) if kind else \
            ((row, None) for row in trace_rows(raw, xml_encoded))
        for row, method in source:
                case_id = row["id"]
                if row["kind"] == "inputs":
                    if active is not None or case_id not in expected or case_id in completed:
                        raise Rejected("duplicate, unexpected, or interleaved trace case")
                    if case_id != ordered[len(completed)]:
                        raise Rejected("raw process case order differs from declaration")
                    if kind and method != method_for_case(expected[case_id]):
                        raise Rejected("numerical case did not run in its declared method")
                    active = {"case_id": case_id, "method": method_for_case(expected[case_id]),
                              "path": str(directory / f"case-{len(completed):03}.jsonl.gz"),
                              "plain_bytes": 0, "rows": 0, "observed_index": len(completed)}
                    active["hash"] = hashlib.sha256()
                    active["stream"] = gzip.open(active["path"], "xb", compresslevel=3)
                if active is None or case_id != active["case_id"]:
                    raise Rejected("numerical row is outside its case")
                if kind and method != active["method"]:
                    raise Rejected("numerical row changed executed method inside case")
                encoded = (json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
                active["stream"].write(encoded)
                active["hash"].update(encoded)
                active["plain_bytes"] += len(encoded)
                active["rows"] += 1
                if row["kind"] == "case-end":
                    active["stream"].close()
                    active["plain_sha256"] = active.pop("hash").hexdigest()
                    active["gzip_sha256"] = digest(Path(active["path"]))
                    active.pop("stream")
                    completed[case_id] = active
                    active = None
    finally:
        if active is not None:
            active["stream"].close()
    if active is not None or set(completed) != set(expected):
        raise Rejected(f"trace segments are incomplete: {len(completed)}/{len(expected)} cases")
    return [completed[case["id"]] for case in cases]


def collect_trace(raw, trace, started_ns, xml_encoded=False):
    if not raw.is_file() or raw.stat().st_mtime_ns < started_ns:
        raise Rejected("trace source is absent or stale")
    count = 0
    with trace.open("x", encoding="utf-8") as target:
        for row in trace_rows(raw, xml_encoded):
            target.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")
            count += 1
    if not count:
        raise Rejected("executed process emitted no numerical trace")
    return count


def observed_counts(trace):
    counts = {"inputs": 0, "states": 0, "events": 0, "endpoints": 0, "case_ends": 0}
    for row in records(trace, allow_tagged_nonfinite=True):
        key = {"inputs": "inputs", "state": "states", "event": "events",
               "endpoint": "endpoints", "case-end": "case_ends"}.get(row["kind"])
        if key:
            counts[key] += 1
    return counts


def run_command(command, cwd, log, env=None, timeout_seconds=None):
    started = time.time_ns()
    compressed = log.suffix == ".gz"
    plain_hash = hashlib.sha256()
    plain_bytes = 0
    timed_out = False
    deadline = time.monotonic() + timeout_seconds if timeout_seconds else None
    with (gzip.open(log, "xb", compresslevel=3) if compressed else log.open("xb")) as stream:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                if deadline is not None and time.monotonic() >= deadline and not timed_out:
                    timed_out = True
                    os.killpg(process.pid, signal.SIGTERM)
                    deadline = time.monotonic() + 5
                elif timed_out and time.monotonic() >= deadline:
                    os.killpg(process.pid, signal.SIGKILL)
                    deadline = time.monotonic() + 5
                for key, _ in selector.select(timeout=0.5):
                    chunk = os.read(key.fileobj.fileno(), 1024 * 1024)
                    if chunk:
                        stream.write(chunk)
                        plain_hash.update(chunk)
                        plain_bytes += len(chunk)
                    else:
                        selector.unregister(key.fileobj)
        exit_code = process.wait()
        process.stdout.close()
    return {"command": command, "pid": process.pid, "exit_code": exit_code,
            "timed_out": timed_out, "started_ns": started, "ended_ns": time.time_ns(),
            "log": str(log), "log_sha256": digest(log), "plain_sha256": plain_hash.hexdigest(),
            "plain_bytes": plain_bytes}


def compress_file(source, target):
    plain_hash = hashlib.sha256()
    plain_bytes = 0
    with Path(source).open("rb") as original, gzip.open(target, "xb", compresslevel=3) as compressed:
        while chunk := original.read(1024 * 1024):
            compressed.write(chunk)
            plain_hash.update(chunk)
            plain_bytes += len(chunk)
    return {"path": str(target), "gzip_sha256": digest(target),
            "plain_sha256": plain_hash.hexdigest(), "plain_bytes": plain_bytes}


def browser_stdout(reports, raw):
    plain_hash = hashlib.sha256()
    plain_bytes = 0
    with gzip.open(raw, "xb", compresslevel=3) as compressed:
        for report in reports:
            with report.open("rb") as source:
                for line in source:
                    if b"NUMERICAL_JSON " in line:
                        compressed.write(line)
                        plain_hash.update(line)
                        plain_bytes += len(line)
    return {"path": str(raw), "gzip_sha256": digest(raw),
            "plain_sha256": plain_hash.hexdigest(), "plain_bytes": plain_bytes}


def native_methods(raw):
    started = set()
    finished = set()
    totals = []
    failures = False
    with open_text(raw) as stream:
        for line in stream:
            start = re.match(r"\[ RUN\s+\] portable\.(PortableMatrixTest|RecorderTest)\.(\w+)", line)
            end = re.match(r"\[\s+OK\s+\] portable\.(PortableMatrixTest|RecorderTest)\.(\w+)", line)
            if start:
                if expected_class(start.group(2)) != start.group(1):
                    raise Rejected("native method class differs")
                if start.group(2) in started:
                    raise Rejected("duplicate native method start")
                started.add(start.group(2))
            if end:
                if expected_class(end.group(2)) != end.group(1):
                    raise Rejected("native completion class differs")
                if end.group(2) in finished:
                    raise Rejected("duplicate native method completion")
                finished.add(end.group(2))
            summary = re.match(r"\[\s+PASSED\s+\] (\d+) tests\.", line)
            if summary:
                totals.append(int(summary.group(1)))
            if re.match(r"\[\s+(FAILED|SKIPPED|DISABLED)\s+\]", line):
                failures = True
    if failures or len(totals) != 1 or totals[0] != len(started) or started != finished:
        raise Rejected("native test summary or method executions differ")
    return {name: "passed" if name in finished else "failed" for name in started | finished}


def wasmtime_methods(raw):
    suites = []
    active = None
    observed = {}
    pattern = re.compile(r"^##teamcity\[(\w+) name='([^']*)'")
    with open_text(raw) as stream:
        for line in stream:
            event = pattern.match(line)
            if event is None:
                continue
            kind, name = event.groups()
            if kind == "testSuiteStarted":
                suites.append(name)
            elif kind == "testSuiteFinished":
                if not suites or suites.pop() != name or active is not None:
                    raise Rejected("unbalanced Wasmtime test suite")
            elif kind == "testStarted":
                if len(suites) != 2 or active is not None or suites[1] not in ("PortableMatrixTest", "RecorderTest"):
                    raise Rejected("wrong or overlapping Wasmtime test")
                if expected_class(name) != suites[1]:
                    raise Rejected("Wasmtime method class differs")
                active = name
            elif kind == "testFinished":
                if active != name or observed.get(name) == "passed":
                    raise Rejected("Wasmtime test completion differs")
                observed.setdefault(name, "passed")
                active = None
            elif kind in ("testFailed", "testIgnored"):
                if active is None:
                    raise Rejected("unscoped Wasmtime failure or skip")
                observed[active] = "ignored" if kind == "testIgnored" else "failed"
    if suites or active is not None:
        raise Rejected("unfinished Wasmtime test suite")
    return observed


def browser_methods(xml_dir, started_ns, task=None, browser=None):
    observed = {}
    reports = sorted(xml_dir.glob("TEST-*.xml"))
    if not reports:
        raise Rejected("browser test XML is absent")
    for report in reports:
        if report.stat().st_mtime_ns < started_ns:
            raise Rejected("browser test XML is stale")
        class Cases(xml.sax.handler.ContentHandler):
            def __init__(self):
                self.current = None
                self.counts = None
                self.count = 0
                self.bad = 0

            def startElement(self, name, attrs):
                if name == "testsuite":
                    self.counts = {key: int(attrs[key]) for key in ("tests", "failures", "errors", "skipped")}
                elif name == "testcase":
                    method = attrs.get("name", "").split("[", 1)[0]
                    classname = attrs.get("classname", "")
                    if task and classname not in (f"{task}.portable.PortableMatrixTest",
                                                      f"{task}.portable.RecorderTest"):
                        raise Rejected("browser XML target or test class differs")
                    if task and classname != f"{task}.portable.{expected_class(method)}":
                        raise Rejected("browser method class differs")
                    if browser and browser not in attrs.get("name", ""):
                        raise Rejected("browser XML runtime differs")
                    if method in observed:
                        raise Rejected("duplicate browser test method")
                    self.current = method
                    observed[method] = "passed"
                    self.count += 1
                elif name in ("skipped", "ignored", "failure", "error") and self.current is not None:
                    observed[self.current] = "ignored" if name in ("skipped", "ignored") else "failed"
                    self.bad += 1

            def endElement(self, name):
                if name == "testcase":
                    self.current = None

        handler = Cases()
        xml.sax.parse(str(report), handler)
        if handler.counts is None or handler.counts["tests"] != handler.count or \
                handler.counts["failures"] + handler.counts["errors"] + handler.counts["skipped"] != handler.bad:
            raise Rejected("browser XML summary differs from testcases")
    return observed


def selected_capture_cases(route, bounded_geometry=False, bounded_methods=None):
    if bounded_geometry and bounded_methods:
        raise Rejected("bounded browser methods conflict with geometry selection")
    cases = declared_cases()
    if bounded_methods is not None:
        if route.kind != "browser" or not isinstance(bounded_methods, list) or \
                len(bounded_methods) != 2 or len(set(bounded_methods)) != 2 or \
                not set(bounded_methods) <= METHODS:
            raise Rejected("bounded browser method pair differs")
        cases = [case for case in cases if method_for_case(case) in bounded_methods]
        if method_runs(cases) != bounded_methods:
            raise Rejected("bounded browser method order differs from declaration")
    elif bounded_geometry:
        cases = [case for case in cases if case["family"] == "geometry-collision"]
        if len(cases) != 75:
            raise Rejected("bounded geometry case declaration differs")
    return cases


def method_runs(cases):
    runs = []
    for case in cases:
        method = method_for_case(case)
        if not runs or runs[-1] != method:
            runs.append(method)
    return runs


def browser_capture_plan(cases, full):
    runs = method_runs(cases)
    if len(runs) != len(set(runs)):
        raise Rejected("browser declaration revisits an executed method")
    return runs + sorted(RECORDER_METHODS) if full else runs


def browser_profile(command):
    for index, part in enumerate(command):
        if part.startswith("--user-data-dir="):
            return part.split("=", 1)[1]
        if part in ("-profile", "--profile") and index + 1 < len(command):
            return command[index + 1]
    raise Rejected("browser process profile is absent")


def archived_browser_method(xml_path, task, browser):
    class Summary(xml.sax.handler.ContentHandler):
        def __init__(self):
            self.counts = None
            self.methods = []
            self.bad = 0

        def startElement(self, name, attrs):
            if name == "testsuite":
                self.counts = {key: int(attrs[key]) for key in ("tests", "failures", "errors", "skipped")}
            elif name == "testcase":
                method = attrs.get("name", "").split("[", 1)[0]
                if attrs.get("classname") != f"{task}.portable.{expected_class(method)}" or \
                        browser not in attrs.get("name", ""):
                    raise Rejected("archived browser test identity differs")
                self.methods.append(method)
            elif name in ("failure", "error", "skipped", "ignored"):
                self.bad += 1

    handler = Summary()
    with gzip.open(xml_path, "rb") as stream:
        xml.sax.parse(stream, handler)
    if handler.counts != {"tests": 1, "failures": 0, "errors": 0, "skipped": 0} or \
            len(handler.methods) != 1 or handler.bad:
        raise Rejected("archived browser method did not pass alone")
    return handler.methods[0]


def verify_browser_invocations(manifest, route, cases):
    console_capture = manifest["schema"] == "portable-numerical-segments/3"
    expected = method_runs(cases)
    if not manifest.get("bounded_geometry") and not manifest.get("bounded_methods"):
        expected.extend(sorted(RECORDER_METHODS))
        if set(expected) != ALL_METHODS:
            raise Rejected("full browser method inventory differs")
    invocations = manifest.get("browser_invocations")
    if not isinstance(invocations, list) or len(invocations) != len(expected):
        raise Rejected("browser method invocation count differs")
    xml_streams = manifest.get("xml_streams")
    if not isinstance(xml_streams, dict):
        raise Rejected("browser XML streams are absent")
    runner = Path(manifest["runner"])
    seen_keys = set()
    seen_ports = set()
    seen_profiles = set()
    combined_hash = hashlib.sha256()
    combined_bytes = 0
    browser = "ChromeHeadless" if route.runtime == "Chromium" else "Firefox"
    for index, (item, method) in enumerate(zip(invocations, expected)):
        if item.get("index") != index or item.get("method") != method or \
                item.get("candidate_commit") != manifest["candidate_commit"] or \
                item.get("artifact_sha256") != manifest["artifact"]["sha256"]:
            raise Rejected("browser method invocation identity differs")
        build = item["build"]
        command = build["command"]
        if build.get("timed_out") or build.get("exit_code") != 0 or \
                not command or not Path(command[0]).is_file() or \
                digest(Path(command[0])) != item["build_runner_sha256"] or \
                command.count(route.task) != 1 or command.count("--tests") != 1 or \
                command[-2:] != ["--tests", f"portable.{expected_class(method)}.{method}"] or \
                command.count(browser_lock_task(route.target)) != 1 or \
                not any(part.startswith("-PportableRepository=") for part in command):
            raise Rejected("browser method build command differs")
        if digest(Path(build["log"])) != build["log_sha256"]:
            raise Rejected("browser method build log differs")
        port = item["karma_port"]
        if not isinstance(port, int) or port in seen_ports:
            raise Rejected("browser Karma port was reused")
        seen_ports.add(port)
        config = Path(item["karma_config"])
        if digest(config) != item["karma_config_sha256"]:
            raise Rejected("browser Karma configuration differs")
        console = item.get("console_source") if console_capture else None
        verify_karma_port(config, port, console["path"] if console else None)
        linked = item["linked_executable"]
        loaded = item["loaded_input"]
        if digest(Path(linked["path"])) != linked["sha256"] or \
                digest(Path(loaded["path"])) != loaded["sha256"] or \
                f'"{loaded["source_path"]}"' not in config.read_text():
            raise Rejected("browser linked or loaded test input differs")
        if route.target == "wasmJs":
            package = item["package"]
            linked_wasm = item["linked_wasm"]
            packaged_wasm = item["packaged_wasm"]
            expected_package = Path(loaded["source_path"]).parent.parent / \
                "kotlin/dyn4k-portable-numerical-consumer-test.mjs"
            if package["source_path"] != str(expected_package) or \
                    packaged_wasm["source_path"] != str(expected_package.with_suffix(".wasm")) or \
                    linked_wasm["source_path"] != str(Path(linked["source_path"]).with_suffix(".wasm")) or \
                    '../kotlin/dyn4k-portable-numerical-consumer-test.mjs' not in \
                    Path(loaded["path"]).read_text() or \
                    'dyn4k-portable-numerical-consumer-test.wasm' not in \
                    Path(linked["path"]).read_text() or \
                    any(digest(Path(value["path"])) != value["sha256"] for value in
                        (package, linked_wasm, packaged_wasm)) or \
                    package["sha256"] != linked["sha256"] or \
                    packaged_wasm["sha256"] != linked_wasm["sha256"]:
                raise Rejected("browser linked or loaded Wasm input differs")
            helpers = item["support_inputs"]
            if set(helpers) != set(WASM_HELPERS):
                raise Rejected("browser Wasm support input inventory differs")
            for name in WASM_HELPERS:
                pair = helpers[name]
                if pair["linked"]["source_path"] != str(Path(linked["source_path"]).parent / name) or \
                        pair["package"]["source_path"] != str(expected_package.parent / name) or \
                        any(digest(Path(value["path"])) != value["sha256"] for value in pair.values()) or \
                        pair["linked"]["sha256"] != pair["package"]["sha256"]:
                    raise Rejected("browser Wasm support input differs")
        elif linked["sha256"] != loaded["sha256"]:
            raise Rejected("browser linked or loaded test input differs")
        attestation = Path(item["browser_attestation"])
        if digest(attestation) != item["browser_attestation_sha256"]:
            raise Rejected("browser process attestation differs")
        launches = [json.loads(line) for line in attestation.read_text().splitlines()]
        if not launches or launches != item["browser_processes"]:
            raise Rejected("browser process observations differ")
        profiles = set()
        for launch in launches:
            verify_process(runner, manifest["runner_sha256"], build["exit_code"], launch["command"])
            actual = Path(launch["process_executable"])
            if launch["runner_sha256"] != manifest["runner_sha256"] or \
                    not actual.is_file() or digest(actual) != launch["process_sha256"]:
                raise Rejected("browser process image differs")
            profiles.add(browser_profile(launch["command"]))
        if profiles != {item["profile"]} or item["profile"] in seen_profiles:
            raise Rejected("browser process profile differs or was reused")
        seen_profiles.add(item["profile"])
        keys = item["xml_keys"]
        if not isinstance(keys, list) or len(keys) != 1 or keys[0] in seen_keys or \
                keys[0] not in xml_streams:
            raise Rejected("browser method XML partition differs")
        seen_keys.add(keys[0])
        xml_item = xml_streams[keys[0]]
        if not xml_item.get("source_name", "").startswith("TEST-") or \
                not xml_item["source_name"].endswith(".xml") or \
                archived_browser_method(xml_item["path"], route.task, browser) != method:
            raise Rejected("browser method XML testcase differs")
        method_xml = {keys[0]: xml_item}
        raw = item["raw_stream"]
        verify_gzip_bytes(raw["path"], raw["gzip_sha256"], raw["plain_sha256"], raw["plain_bytes"])
        if console_capture:
            if digest(Path(console["path"])) != console["sha256"] or \
                    Path(console["path"]).stat().st_size != console["plain_bytes"] or \
                    console["sha256"] != raw["plain_sha256"] or \
                    console["plain_bytes"] != raw["plain_bytes"]:
                raise Rejected("browser console source differs from compressed method stream")
            with gzip.open(xml_item["path"], "rb") as archived_xml:
                if any(b"NUMERICAL_JSON " in line for line in archived_xml):
                    raise Rejected("browser XML unexpectedly duplicates console rows")
        else:
            verify_browser_xml_source(method_xml, raw)
        with gzip.open(raw["path"], "rb") as stream:
            while chunk := stream.read(1024 * 1024):
                combined_hash.update(chunk)
                combined_bytes += len(chunk)
    if seen_keys != set(xml_streams) or \
            manifest["linked_executable"] != invocations[-1]["linked_executable"] or \
            manifest["process"]["command"] != invocations[0]["browser_processes"][0]["command"] or \
            combined_hash.hexdigest() != manifest["raw_stream"]["plain_sha256"] or \
            combined_bytes != manifest["raw_stream"]["plain_bytes"]:
        raise Rejected("browser method streams do not assemble to the raw process order")


def browser_launch():
    import fcntl
    selected = Path(os.environ["DYN4K_NUMERICAL_BROWSER"]).resolve()
    attestation = Path(os.environ["DYN4K_NUMERICAL_ATTESTATION"])
    if not selected.is_file():
        return 127
    image_hash = digest(selected)
    command = [str(selected), *sys.argv[1:]]
    pid = os.getpid()
    allowed = {selected}
    if os.environ.get("DYN4K_BROWSER") == "firefox":
        allowed.add(selected.with_name("firefox-bin"))
    if os.fork() == 0:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                actual = Path(os.readlink(f"/proc/{pid}/exe")).resolve()
                if actual in allowed and digest(Path(f"/proc/{pid}/exe")) == digest(actual):
                    with attestation.open("a", encoding="utf-8") as record:
                        fcntl.flock(record, fcntl.LOCK_EX)
                        record.write(json.dumps({"command": command, "runner_sha256": image_hash,
                                                 "pid": pid, "process_executable": str(actual),
                                                 "process_sha256": digest(actual)}) + "\n")
                        record.flush()
                        os.fsync(record.fileno())
                        fcntl.flock(record, fcntl.LOCK_UN)
                    os._exit(0)
            except (OSError, ValueError):
                pass
            time.sleep(0.01)
        os._exit(1)
    os.execv(str(selected), command)


def browser_linked_binary(route, configuration):
    kind = ("testProductionExecutable/optimized" if route.target == "wasmJs" else
            "testProductionExecutable/kotlin") if configuration == "optimized" else \
            "testDevelopmentExecutable/kotlin"
    suffix = ".mjs" if route.target == "wasmJs" else ".js"
    return (PORTABLE / "build/compileSync" / route.target / "test" / kind /
            f"dyn4k-portable-numerical-consumer-test{suffix}")


def browser_loaded_input(config, linked, target):
    suffix = r"/static/load\.mjs" if target == "wasmJs" else \
        r"/kotlin/dyn4k-portable-numerical-consumer-test\.js"
    matches = set(re.findall(r'"([^"]*' + suffix + r')"', config.read_text()))
    if len(matches) != 1:
        raise Rejected("Karma loaded test input is ambiguous")
    loaded = Path(next(iter(matches)))
    if target == "js":
        if not loaded.is_file() or digest(loaded) != digest(linked):
            raise Rejected("Karma loaded test input differs from linked test")
        return {"loaded": loaded}
    package = loaded.parent.parent / "kotlin/dyn4k-portable-numerical-consumer-test.mjs"
    linked_wasm = linked.with_suffix(".wasm")
    packaged_wasm = package.with_suffix(".wasm")
    if not all(path.is_file() for path in (loaded, package, linked_wasm, packaged_wasm)) or \
            '../kotlin/dyn4k-portable-numerical-consumer-test.mjs' not in loaded.read_text() or \
            'dyn4k-portable-numerical-consumer-test.wasm' not in linked.read_text() or \
            digest(package) != digest(linked) or digest(packaged_wasm) != digest(linked_wasm):
        raise Rejected("Karma loaded Wasm test inputs differ from linked test")
    helpers = {}
    for name in WASM_HELPERS:
        original = linked.parent / name
        packaged = package.parent / name
        if not original.is_file() or not packaged.is_file() or digest(original) != digest(packaged):
            raise Rejected("Karma loaded Wasm support input differs from linked test")
        helpers[name] = (original, packaged)
    return {"loaded": loaded, "package": package, "linked_wasm": linked_wasm,
            "packaged_wasm": packaged_wasm, "helpers": helpers}


def join_browser_stdout(invocations, target):
    plain_hash = hashlib.sha256()
    plain_bytes = 0
    with gzip.open(target, "xb", compresslevel=3) as output:
        for item in invocations:
            with gzip.open(item["raw_stream"]["path"], "rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    output.write(chunk)
                    plain_hash.update(chunk)
                    plain_bytes += len(chunk)
    return {"path": str(target), "gzip_sha256": digest(target),
            "plain_sha256": plain_hash.hexdigest(), "plain_bytes": plain_bytes}


def capture_browser_methods(args, route, result, output, runner, runner_sha,
                            commit, archive, artifact_path, artifact_sha, command_base,
                            methods_to_run):
    methods = {}
    xml_streams = {}
    invocations = []
    result["browser_invocations"] = invocations
    used_ports = set()
    env = build_env()
    env.update(DYN4K_NUMERICAL_BROWSER=str(runner),
               DYN4K_BROWSER="chromium" if route.runtime == "Chromium" else "firefox")
    env["CHROME_BIN" if route.runtime == "Chromium" else "FIREFOX_BIN"] = str(Path(__file__).resolve())
    reports = PORTABLE / "build/test-results" / route.task
    generated = (PORTABLE / "build" / ("js" if route.target == "js" else "wasm") /
                 "packages" / "dyn4k-portable-numerical-consumer-test" / "karma.conf.js")
    linked_source = browser_linked_binary(route, args.configuration)
    browser_name = ("ChromeHeadless" if route.runtime == "Chromium" else "Firefox") + \
        args.expected_version.split(".", 1)[0]
    for index, method in enumerate(methods_to_run):
        slot = output / "methods" / f"{index:02}-{method}"
        slot.mkdir(parents=True)
        if reports.exists():
            shutil.rmtree(reports)
        attestation = slot / "browser-processes.jsonl"
        console = slot / "browser-console.jsonl"
        command = [*command_base, "--tests", f"portable.{expected_class(method)}.{method}"]
        env["DYN4K_NUMERICAL_ATTESTATION"] = str(attestation)
        with isolated_karma_port(PORTABLE, used_ports, console) as port:
            used_ports.add(port)
            build = run_command(command, ROOT, slot / "build.log", env, timeout_seconds=28800)
            item = {"index": index, "method": method, "candidate_commit": commit,
                    "artifact_sha256": artifact_sha, "build": build,
                    "build_runner_sha256": digest(ROOT / "gradlew"), "karma_port": port}
            invocations.append(item)
            if generated.is_file() and generated.stat().st_mtime_ns >= build["started_ns"]:
                frozen = slot / "karma.conf.js"
                shutil.copyfile(generated, frozen)
                item.update(karma_config=str(frozen), karma_config_sha256=digest(frozen))
            xml_reports = sorted(reports.glob("TEST-*.xml")) if reports.exists() else []
            keys = []
            for report in xml_reports:
                key = f"TEST-{index:02}-{report.name[5:]}"
                if key in xml_streams:
                    raise Rejected("duplicate browser XML archive key")
                xml_path = slot / f"{report.name}.gz"
                xml_streams[key] = {**compress_file(report, xml_path), "source_name": report.name}
                keys.append(key)
            item["xml_keys"] = keys
            if console.is_file():
                item["console_source"] = {"path": str(console), "sha256": digest(console),
                                          "plain_bytes": console.stat().st_size}
                item["raw_stream"] = compress_file(console, slot / "runtime-stdout.gz")
            if attestation.is_file():
                item.update(browser_attestation=str(attestation),
                            browser_attestation_sha256=digest(attestation),
                            browser_processes=[json.loads(line) for line in attestation.read_text().splitlines()])
            if linked_source.is_file() and linked_source.stat().st_mtime_ns >= build["started_ns"]:
                linked_copy = slot / f"linked{linked_source.suffix}"
                shutil.copyfile(linked_source, linked_copy)
                item["linked_executable"] = {"path": str(linked_copy),
                                              "sha256": digest(linked_copy),
                                              "source_path": str(linked_source)}
            if build["exit_code"] or build["timed_out"]:
                raise Rejected(f"browser method task failed: {method}")
            verify_karma_port(Path(item["karma_config"]), port, console)
            if args.configuration == "optimized" and \
                    f"portable numerical test input: {linked_source}" not in Path(build["log"]).read_text():
                raise Rejected("optimized browser method did not select its linked output")
            observed = browser_methods(reports, build["started_ns"], route.task, browser_name)
            verify_methods(observed, {method})
            methods.update(observed)
            inputs = browser_loaded_input(Path(item["karma_config"]), linked_source, route.target)
            loaded_source = inputs["loaded"]
            loaded_copy = slot / f"loaded{loaded_source.suffix}"
            shutil.copyfile(loaded_source, loaded_copy)
            item["loaded_input"] = {"path": str(loaded_copy), "sha256": digest(loaded_copy),
                                    "source_path": str(loaded_source)}
            if route.target == "wasmJs":
                for key in ("package", "linked_wasm", "packaged_wasm"):
                    source = inputs[key]
                    copied = slot / f"{key}{source.suffix}"
                    shutil.copyfile(source, copied)
                    item[key] = {"path": str(copied), "sha256": digest(copied),
                                 "source_path": str(source)}
                item["support_inputs"] = {}
                for name, pair in inputs["helpers"].items():
                    item["support_inputs"][name] = {}
                    for label, source in zip(("linked", "package"), pair):
                        copied = slot / f"{label}-{name}"
                        shutil.copyfile(source, copied)
                        item["support_inputs"][name][label] = {
                            "path": str(copied), "sha256": digest(copied),
                            "source_path": str(source)}
            launches = item.get("browser_processes", [])
            if not launches or any(launch.get("runner_sha256") != runner_sha or
                                   launch.get("command", [None])[0] != str(runner) or
                                   launch.get("process_sha256") != digest(Path(launch["process_executable"]))
                                   for launch in launches):
                raise Rejected("browser method process image differs from selected runner")
            profiles = {browser_profile(launch["command"]) for launch in launches}
            if len(profiles) != 1:
                raise Rejected("browser method process profile is ambiguous")
            item["profile"] = profiles.pop()
        verify_inputs(commit, source_identity()[0], route.target, route.target,
                      artifact_path, artifact_sha)
        if source_identity() != (commit, archive):
            raise Rejected("source changed during browser method execution")
    raw = output / "runtime-stdout.gz"
    raw_stream = join_browser_stdout(invocations, raw)
    first = invocations[0]
    selected_process = {"command": first["browser_processes"][0]["command"],
                        "exit_code": first["build"]["exit_code"], "timed_out": first["build"]["timed_out"]}
    result.update(xml_streams=xml_streams, linked_executable=invocations[-1]["linked_executable"],
                  build=first["build"], karma_ports=sorted(used_ports))
    return methods, raw_stream, selected_process, first["build"]["started_ns"]


def run(args):
    output = args.output.resolve()
    if output.exists():
        raise Rejected("output already exists")
    output.mkdir(parents=True)
    route = ROUTES[args.route]
    result = {"status": "FAILED", "route": args.route, "target": route.target,
              "runtime": route.runtime, "configuration": args.configuration,
              "qualification": "UNPASSED"}
    try:
        if route.kind == "original":
            raise Rejected("this route belongs to portable/run.py")
        bounded = getattr(args, "bounded_geometry", False)
        if bounded and route.kind not in ("browser", "android-guest", "wasmtime"):
            raise Rejected("bounded geometry capture requires a browser, Wasmtime, or Android Native guest")
        bounded_methods = getattr(args, "bounded_browser_methods", None)
        selected_cases = selected_capture_cases(route, bounded, bounded_methods)
        browser_plan = browser_capture_plan(selected_cases, not (bounded or bounded_methods)) \
            if route.kind == "browser" else None
        runner = args.runner.resolve() if args.runner else None
        if route.kind == "android-guest" and runner is None:
            runner = Path("/home/stewart/Android/Sdk/platform-tools/adb")
        if runner is None or not runner.is_file():
            raise Rejected("selected native, browser, or hosted runner is absent")
        runner_sha = digest(runner)
        if route.kind in ("browser", "wasmtime"):
            result["runtime_version"] = runtime_version(runner, args.expected_version)
        commit, archive = source_identity()
        result.update(candidate_commit=commit, source_sha256=archive)
        artifact_path = artifact(route.target)
        metadata_path = GROUP / "dyn4k-core" / VERSION / f"dyn4k-core-{VERSION}.jar"
        publication = f":dyn4k-core:publish{route.target[0].upper()}{route.target[1:]}PublicationToStagingRepository"
        stage = run_command([str(ROOT / "gradlew"),
                             ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
                             publication, "--rerun-tasks", "--no-daemon", "--console=plain"],
                            ROOT, output / "stage.log", build_env())
        result["stage"] = stage
        if stage["exit_code"]:
            raise Rejected("staged publication task failed")
        if not artifact_path.is_file() or artifact_path.stat().st_mtime_ns < stage["started_ns"]:
            raise Rejected("staged target publication is absent or stale")
        if not metadata_path.is_file() or metadata_path.stat().st_mtime_ns < stage["started_ns"]:
            raise Rejected("staged root metadata is absent or stale")
        artifact_sha = digest(artifact_path)
        metadata_sha = digest(metadata_path)
        result["staged_artifact_sha256"] = {"target": artifact_sha, "metadata": metadata_sha}
        verify_inputs(commit, source_identity()[0], route.target, route.target, artifact_path, artifact_sha)
        task = route.task
        if route.kind in ("hosted-native", "android-guest") and args.configuration == "optimized":
            task = task.replace("linkDebug", "linkRelease")
        if route.kind == "wasmtime" and args.configuration == "optimized":
            task = task.replace("Development", "Production") + "Optimize"
        command = [str(ROOT / "gradlew"), "-p", str(PORTABLE), task,
                   f"-PportableRepository={ROOT / 'build/staging-repository'}",
                   "--rerun-tasks", "--no-daemon", "--console=plain", "--info"]
        raw = output / "runtime-stdout.gz"
        if route.kind == "browser":
            command.insert(3, browser_lock_task(route.target))
            if args.configuration == "optimized":
                command.append("-PportableOptimized=true")
            methods, raw_stream, selected_process, trace_started = capture_browser_methods(
                args, route, result, output, runner, runner_sha, commit, archive,
                artifact_path, artifact_sha, command, browser_plan)
            build = result["build"]
            process = selected_process
        else:
            command.extend(bounded_gradle_filter(route, bounded))
            build = run_command(command, ROOT, output / "build.log", build_env(),
                                timeout_seconds=28800)
            result["build"] = build
            if build["exit_code"] or build["timed_out"]:
                raise Rejected("portable target task failed")
            binary = linked_binary(route, args.configuration)
            if not binary.is_file() or binary.stat().st_mtime_ns < build["started_ns"]:
                raise Rejected("linked test executable is absent or stale")
            result["linked_executable"] = {"path": str(binary), "sha256": digest(binary)}
            if route.kind == "android-guest":
                command, guest = guest_command(runner, binary, output, bounded)
                result["guest"] = guest
            elif route.kind == "wasmtime":
                command = wasmtime_invocation(runner, binary, bounded)
            else:
                if args.runner_arg and sum(part.count("{binary}") for part in args.runner_arg) != 1:
                    raise Rejected("hosted runner arguments must name the linked binary exactly once")
                command = [str(runner), *(part.replace("{binary}", str(binary)) for part in args.runner_arg)]
                if not args.runner_arg:
                    command.append(str(binary))
            process = run_command(command, ROOT, raw, timeout_seconds=28800)
            result["process"] = process
            verify_process(runner, runner_sha, process["exit_code"], command)
            methods = wasmtime_methods(raw) if route.kind == "wasmtime" else native_methods(raw)
            selected_process = process
            raw_stream = {"path": str(raw), "gzip_sha256": process["log_sha256"],
                          "plain_sha256": process["plain_sha256"],
                          "plain_bytes": process["plain_bytes"]}
            trace_started = build["started_ns"]
        if source_identity() != (commit, archive):
            raise Rejected("source changed during target build")
        verify_inputs(commit, source_identity()[0], route.target, route.target, artifact_path, artifact_sha)
        result["process"] = process
        verify_methods(methods, set(browser_plan) if route.kind == "browser" else
                       {"geometryCollisionBoundaryAndScale"} if bounded else ALL_METHODS)
        result["methods"] = methods
        segments = segment_trace(raw, output / "cases", selected_cases, trace_started,
                                 route.kind, result.get("xml_streams"), route.task,
                                 result.get("browser_invocations") if route.kind == "browser" else None)
        segment_manifest = output / "segments.json"
        segment_data = {"schema": "portable-numerical-segments/3" if route.kind == "browser"
                        else "portable-numerical-segments/1", "candidate_commit": commit,
                        "source_sha256": archive, "route": args.route, "target": route.target,
                        "bounded_geometry": bounded, "runner": str(runner),
                        "runner_sha256": runner_sha, "linked_executable": result["linked_executable"],
                        "artifact": {"path": str(artifact_path), "sha256": artifact_sha},
                        "process": selected_process, "raw_stream": raw_stream, "segments": segments}
        if route.kind == "browser":
            segment_data["xml_streams"] = result["xml_streams"]
            segment_data["browser_invocations"] = result["browser_invocations"]
            if bounded_methods:
                segment_data["bounded_methods"] = bounded_methods
        if route.kind == "android-guest":
            segment_data["guest"] = result["guest"]
        segment_manifest.write_text(json.dumps(segment_data, indent=2, sort_keys=True) + "\n")
        result["segments_manifest"] = {"path": str(segment_manifest), "sha256": digest(segment_manifest)}
        trace = output / "trace.jsonl"
        verified_segments = verify_segments(segment_manifest, trace)
        result["trace_rows"] = sum(entry["rows"] for entry in segments)
        result["verified_segments"] = verified_segments
        result["observed_counts"] = observed_counts(trace)
        identity = Identity(commit, archive, {"target": artifact_sha, "metadata": metadata_sha},
                            {"target": route.target, "runtime": route.runtime,
                             "runner": str(runner), "runner_sha256": runner_sha,
                             "runtime_version": result.get("runtime_version"),
                             "guest_fingerprint": result.get("guest", {}).get("properties", {}).get(
                                 "ro.build.fingerprint"),
                             "configuration": args.configuration})
        sealed = seal(trace, selected_cases, identity,
                      {"target": artifact_path, "metadata": metadata_path})
        if source_identity() != (commit, archive):
            raise Rejected("source changed during target execution")
        if route.kind != "browser":
            verify_process(runner, runner_sha, process["exit_code"], process["command"])
        if route.kind in ("browser", "wasmtime"):
            runtime_version(runner, args.expected_version)
        result.update(status="BOUNDED_CAPTURED" if bounded or bounded_methods else "CAPTURED", receipt=sealed,
                      declared_full_cases=len(declared_cases()), executed_cases=sealed["counts"]["executed_cases"],
                      trace_sha256=sealed["trace_sha256"])
    except (Rejected, OSError, ValueError, KeyError, TypeError, EOFError,
            subprocess.CalledProcessError, xml.sax.SAXException) as error:
        result["status"] = "FAILED"
        result["reason"] = str(error)
    for name in ("runtime-stdout.gz", "trace.jsonl", "segments.json"):
        if (output / name).is_file():
            result.setdefault("raw_sha256", {})[name] = digest(output / name)
    (output / "receipt.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result.get(key) for key in ("status", "route", "executed_cases", "reason")},
                     sort_keys=True))
    return 0 if result["status"] in ("CAPTURED", "BOUNDED_CAPTURED") else 1


def build_env():
    return dict(os.environ, JAVA_HOME=os.environ.get("JAVA_HOME", "/tmp/dyn4k-tools/jdk21"),
                ANDROID_HOME=os.environ.get("ANDROID_HOME", "/home/stewart/Android/Sdk"))


def linked_binary(route, configuration):
    if route.kind == "wasmtime":
        kind = "testProductionExecutable/optimized" if configuration == "optimized" else "testDevelopmentExecutable/kotlin"
        matches = sorted((PORTABLE / "build/compileSync/wasmWasi/test" / kind).glob("*.wasm"))
        if len(matches) != 1:
            raise Rejected(f"expected one linked WASI test executable, found {len(matches)}")
        return matches[0]
    kind = "releaseTest" if configuration == "optimized" else "debugTest"
    suffix = ".exe" if route.target == "mingwX64" else ".kexe"
    return PORTABLE / "build/bin" / route.target / kind / f"test{suffix}"


def wasmtime_invocation(runner, binary, bounded=False):
    command = [str(runner), "run", "-W", "gc=y", "-W", "exceptions=y",
               "-W", "function-references=y", "--invoke", "startUnitTests", str(binary)]
    if bounded:
        # The Wasm test runner uses the first trailing argument as argv[0].
        command.extend(["portable-numerical", "--include",
                        "portable.PortableMatrixTest.geometryCollisionBoundaryAndScale"])
    return command


def guest_command(adb, binary, output, bounded=False):
    prefix = [str(adb), "-P", "5038", "-s", "emulator-5558"]
    devices = subprocess.run([str(adb), "-P", "5038", "devices", "-l"],
                             capture_output=True, text=True)
    active = [line for line in devices.stdout.splitlines() if line.startswith("emulator-")]
    if devices.returncode or len(active) != 1 or active[0].split()[:2] != ["emulator-5558", "device"]:
        raise Rejected("isolated Android guest is absent or occupied by another emulator")
    properties = {}
    for name in ("ro.build.version.sdk", "ro.product.cpu.abi", "ro.boot.qemu.avd_name",
                 "ro.build.fingerprint"):
        check = subprocess.run([*prefix, "shell", "getprop", name], capture_output=True, text=True)
        if check.returncode:
            raise Rejected(f"Android guest property failed: {name}")
        properties[name] = check.stdout.strip()
    if (properties["ro.build.version.sdk"] != "37" or properties["ro.product.cpu.abi"] != "x86_64"
            or properties["ro.boot.qemu.avd_name"] != "dyn4k_api37_play_x64"
            or properties["ro.build.fingerprint"] != ANDROID_GUEST_FINGERPRINT):
        raise Rejected("wrong Android Native guest")
    active_processes = subprocess.run([*prefix, "shell", "ps", "-A"], capture_output=True, text=True)
    if active_processes.returncode or any("/data/local/tmp/dyn4k-" in line
                                           for line in active_processes.stdout.splitlines()):
        raise Rejected("Android Native guest is executing another dyn4k capture")
    remote = "/data/local/tmp/dyn4k-portable-numerical"
    for tail in (["push", str(binary), remote], ["shell", "chmod", "700", remote]):
        done = subprocess.run([*prefix, *tail], capture_output=True)
        if done.returncode:
            raise Rejected("Android Native test deployment failed")
    remote_hash = subprocess.run([*prefix, "shell", "sha256sum", remote], capture_output=True, text=True)
    if remote_hash.returncode or not remote_hash.stdout.split() or remote_hash.stdout.split()[0] != digest(binary):
        raise Rejected("guest executable bytes differ from linked test")
    command = [*prefix, "shell", remote, "--ktest_logger=GTEST"]
    if bounded:
        command.append("--ktest_filter=portable.PortableMatrixTest.geometryCollisionBoundaryAndScale")
    return command, {
        "properties": properties, "remote": remote, "remote_sha256": remote_hash.stdout.split()[0],
        "linked_sha256": digest(binary), "output": str(output)}


def main():
    if "DYN4K_NUMERICAL_BROWSER" in os.environ:
        return browser_launch()
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--verify-segments", type=Path)
    parser.add_argument("--replay-source")
    parser.add_argument("--route", choices=sorted(ROUTES))
    parser.add_argument("--configuration", choices=("debug", "optimized"), default="debug")
    parser.add_argument("--runner", type=Path)
    parser.add_argument("--runner-arg", action="append", default=[])
    parser.add_argument("--expected-version")
    parser.add_argument("--bounded-geometry", action="store_true")
    parser.add_argument("--bounded-browser-methods", nargs=2, metavar=("FIRST", "SECOND"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.list:
        print(json.dumps({key: vars(value) for key, value in ROUTES.items()}, indent=2, sort_keys=True))
        return 0
    if args.verify_segments is not None:
        if args.output is None:
            parser.error("--output is required with --verify-segments")
        try:
            print(json.dumps(verify_segments(args.verify_segments, args.output, args.replay_source), sort_keys=True))
            return 0
        except (Rejected, OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError,
                xml.sax.SAXException) as error:
            print(f"FAILED: {error}", file=sys.stderr)
            return 1
    if args.replay_source is not None:
        parser.error("--replay-source requires --verify-segments")
    if args.route is None or args.output is None:
        parser.error("--route and --output are required")
    try:
        return run(args)
    except Rejected as error:
        parser.error(str(error))


if __name__ == "__main__":
    sys.exit(main())
