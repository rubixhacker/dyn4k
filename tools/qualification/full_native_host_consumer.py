#!/usr/bin/env python3
import argparse
import contextlib
import ctypes
import hashlib
import io
import json
import os
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath, PureWindowsPath

import independent_gates
import qualify


PROJECT = "consumers/qualification/portable/full-native-host"
PRODUCER = "tools/qualification/full_native_host_consumer.py"
MODULES = ("dyn4k-core", "dyn4k")
TARGETS = {
    "linuxArm64": ("Linux", "aarch64", None, "4.9.156", "2.25"),
    "mingwX64": ("Windows", "AMD64", None, "10.0.10240", None),
    "macosArm64": ("Darwin", "arm64", None, "11.", None),
    "iosSimulatorArm64": ("Darwin", "arm64", "iOS", "15.", None),
    "iosX64": ("Darwin", "x86_64", "iOS", "15.", None),
    "tvosSimulatorArm64": ("Darwin", "arm64", "tvOS", "15.", None),
    "watchosSimulatorArm64": ("Darwin", "arm64", "watchOS", "8.", None),
}
SHA = re.compile(r"[0-9a-f]{64}\Z")
UDID = re.compile(r"[0-9a-fA-F-]{36}\Z")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(data):
    return (json.dumps(data, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode()


def git(repository, *args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C",
                                    str(repository), *args], stderr=subprocess.PIPE).decode().strip()


def verify_source_binding(repository, candidate):
    producer_source = subprocess.check_output(["git", "--no-replace-objects", "-C",
                                               str(repository), "show", f"{candidate}:{PRODUCER}"])
    if (git(repository, "rev-parse", "HEAD") != candidate
            or Path(__file__).resolve() != repository / PRODUCER
            or Path(__file__).read_bytes() != producer_source):
        raise ValueError("public verifier differs from exact candidate checkout")


def lane_contract(repository, lane):
    manifest = independent_gates.load_approved_manifest(repository)
    if lane not in manifest["lanes"] or manifest["lanes"][lane]["target"] not in TARGETS:
        raise ValueError("lane is not one of the 28 approved Native host routes")
    contract = independent_gates.consumer_contract(manifest, lane)
    cases = contract["cases"]
    if (len(cases) != 2523 or len({case["id"] for case in cases}) != 2523
            or sum(case["module"] == "dyn4k-core" for case in cases) != 2465
            or sum(case["module"] == "dyn4k" for case in cases) != 58
            or any(case["scope"] != "portable" for case in cases)):
        raise ValueError("approved portable method contract differs")
    return manifest, contract


def source_inputs(repository, candidate, contract):
    roots = [f"{module}/src/commonTest/kotlin" for module in MODULES]
    roots.append("dyn4k-core/src/nativeTest/kotlin")
    tracked = sorted(path for path in git(repository, "ls-tree", "-r", "--name-only",
                                          candidate, "--", *roots).splitlines()
                     if path.endswith(".kt"))
    live = sorted(path.relative_to(repository).as_posix() for root in roots
                  for path in (repository / root).rglob("*.kt") if path.is_file())
    if not tracked or tracked != live or len(tracked) != len(set(tracked)):
        raise ValueError("original Native test source tree differs from candidate")
    hashes = {}
    for path in tracked:
        original = subprocess.check_output(["git", "--no-replace-objects", "-C",
                                            str(repository), "show", f"{candidate}:{path}"])
        if (repository / path).read_bytes() != original:
            raise ValueError(f"original test source differs: {path}")
        hashes[path] = digest(original)
    for case in contract["cases"]:
        if hashes.get(case["source"]["path"]) != case["source"]["sha256"]:
            raise ValueError(f"approved source differs: {case['id']}")
    by_module = {module: sorted((case for case in contract["cases"]
                                 if case["module"] == module), key=lambda case: case["id"])
                 for module in MODULES}
    return {
        "source-inventory.tsv": "".join(f"{path}\t{value}\n"
                                         for path, value in hashes.items()).encode(),
        "core-cases.tsv": "".join(f"{case['id']}\t{case['classname']}\t{case['method']}\n"
                                  for case in by_module["dyn4k-core"]).encode(),
        "facade-cases.tsv": "".join(f"{case['id']}\t{case['classname']}\t{case['method']}\n"
                                    for case in by_module["dyn4k"]).encode(),
    }


def selected_rows(raw):
    rows = [line.split("\t") for line in raw.decode().splitlines()]
    if any(len(row) != 3 for row in rows):
        raise ValueError("selected method input is malformed")
    keys = [(row[1], row[2]) for row in rows]
    if len(keys) != len(set(keys)) or len(rows) != len({row[0] for row in rows}):
        raise ValueError("selected method input duplicates a method")
    return {(row[1], row[2]): row[0] for row in rows}


def original_report(raw, target, selected):
    suite = ET.fromstring(raw)
    if suite.tag != "testsuite":
        raise ValueError("Native raw report root differs")
    cases = list(suite.iter("testcase"))
    counts = {"tests": len(cases),
              "failures": sum(case.find("failure") is not None for case in cases),
              "errors": sum(case.find("error") is not None for case in cases),
              "skipped": sum(case.find("skipped") is not None for case in cases)}
    if (any(suite.get(key) is None or int(suite.get(key)) != value
            for key, value in counts.items())
            or any(counts[key] for key in ("failures", "errors", "skipped"))):
        raise ValueError("Native raw report has missing, failing, or skipped methods")
    try:
        suite_duration = float(suite.get("time", "nan"))
    except ValueError as error:
        raise ValueError("Native raw suite duration is invalid") from error
    if not 0 <= suite_duration < float("inf"):
        raise ValueError("Native raw suite duration is invalid")
    observed = []
    for case in cases:
        classname, method = case.get("classname", ""), case.get("name", "")
        prefix, suffix = f"{target}Test.", f"[{target}]"
        if not classname.startswith(prefix) or not method.endswith(suffix):
            raise ValueError("Native raw target identity differs")
        identity = selected.get((classname[len(prefix):], method[:-len(suffix)]))
        if identity is None:
            raise ValueError("Native raw report contains a foreign method")
        try:
            duration = float(case.get("time", "nan"))
        except ValueError as error:
            raise ValueError("Native raw method duration is invalid") from error
        if not 0 <= duration < float("inf"):
            raise ValueError("Native raw method duration is invalid")
        observed.append(identity)
        case.set("id", identity)
    if len(observed) != len(set(observed)):
        raise ValueError("Native raw report duplicates a method")
    return observed, ET.tostring(suite, encoding="utf-8", xml_declaration=True)


def check_method_coverage(observed, expected):
    if len(observed) != len(expected) or len(set(observed)) != len(observed) or set(observed) != set(expected):
        raise ValueError("original Native method set is incomplete, duplicate, or foreign")


def validate_linux_arm64_elf(data):
    if (len(data) < 64 or data[:6] != b"\x7fELF\x02\x01"
            or int.from_bytes(data[18:20], "little") != 183):
        raise ValueError("linked Linux ARM64 image is not ELF64 AArch64")


def validate_cross_build_host(host):
    if host.get("system") != "Linux" or host.get("machine") != "x86_64":
        raise ValueError("Linux ARM64 cross build requires a supported Linux x86_64 compiler host")


def original_teamcity_events(raw, selected):
    stack, active, observed = [], None, []
    for line in raw.decode("utf-8").splitlines():
        match = re.fullmatch(r"##teamcity\[(\w+) (.*)\]", line)
        if not match:
            continue
        event, body = match.groups()
        attributes = dict(re.findall(r"(\w+)='((?:[^'|]|\|.)*)'", body))
        name = attributes.get("name", "").replace("|'", "'").replace("||", "|")
        if event == "testSuiteStarted":
            if not name:
                raise ValueError("Native test suite identity is absent")
            stack.append(name)
        elif event == "testSuiteFinished":
            if not stack or stack.pop() != name or active:
                raise ValueError("Native test suite events are unbalanced")
        elif event == "testStarted":
            identity = selected.get((stack[-1], name)) if stack else None
            if active or identity is None or identity in observed:
                raise ValueError("Native test event is duplicate or foreign")
            active = (name, identity)
            observed.append(identity)
        elif event == "testFinished":
            if not active or active[0] != name:
                raise ValueError("Native test finish has no matching start")
            active = None
        elif event in ("testFailed", "testIgnored"):
            raise ValueError("Native test event failed or skipped")
    if stack or active or not observed:
        raise ValueError("Native test events are incomplete")
    return observed


def original_test_listing(raw, selected):
    suite, observed = None, []
    for line in raw.decode("utf-8").splitlines():
        if line.endswith(".") and not line.startswith(" "):
            suite = line[:-1]
        elif line.startswith("  "):
            identity = selected.get((suite, line.strip()))
            if identity is None or identity in observed:
                raise ValueError("Native listing has a foreign or duplicate method")
            observed.append(identity)
        elif line.strip():
            raise ValueError("Native listing format differs")
    check_method_coverage(observed, list(selected.values()))
    return observed


def validate_host(lane, selected, observed):
    target, runtime, role, mode = lane.split(":")
    system, machine, family, floor, libc_floor = TARGETS[target]
    if (selected.get("lane") != lane or selected.get("role") != role
            or selected.get("system") != system or selected.get("machine", "").lower() != machine.lower()
            or observed.get("system") != system or observed.get("machine", "").lower() != machine.lower()):
        raise ValueError("selected target or host identity differs")
    if observed.get("os_version") != selected.get("os_version"):
        raise ValueError("observed host version differs from selected runtime")
    actual_version = observed.get("guest_version") if family else observed["os_version"]
    if family and (observed.get("guest_family") != family
                   or observed.get("guest_udid") != selected.get("simulator_udid")
                   or observed.get("guest_runtime") != selected.get("simulator_runtime")
                   or observed.get("guest_version") != selected.get("guest_version")
                   or observed.get("guest_state") != "Booted"):
        raise ValueError("simulator device, OS, or boot state differs")
    if type(actual_version) is not str or not actual_version:
        raise ValueError("selected runtime version is missing")
    def parts(value):
        match = re.match(r"\d+(?:\.\d+)*", value)
        return tuple(int(part) for part in match.group().split(".")) if match else ()

    if not parts(actual_version) or parts(actual_version) < parts(floor):
        raise ValueError("runtime is older than the approved minimum")
    minimum_family = "4.9." if target == "linuxArm64" else floor
    if role == "minimum" and not actual_version.startswith(minimum_family):
        raise ValueError("minimum runtime family differs from approved floor")
    if role == "current" and actual_version.startswith(minimum_family):
        raise ValueError("current runtime repeats minimum family")
    if target == "linuxArm64":
        if observed.get("libc") != selected.get("libc"):
            raise ValueError("Linux glibc identity differs")
        if not parts(observed["libc"]) or parts(observed["libc"]) < parts(libc_floor):
            raise ValueError("Linux glibc is older than approved minimum")
        if role == "minimum" and not observed["libc"].startswith(libc_floor):
            raise ValueError("minimum Linux glibc differs")
    if target == "mingwX64":
        if (observed.get("windows_product_type") != "client"
                or selected.get("windows_product_type") != "client"
                or observed.get("windows_product_name") != selected.get("windows_product_name")):
            raise ValueError("Windows client product identity is absent or differs")
    if system == "Darwin" and observed.get("xcode_version") != "26.5":
        raise ValueError("pinned Xcode identity differs")
    if mode not in ("debug-g", "optimized-opt"):
        raise ValueError("Native mode differs")


def observed_host(target, selection):
    system = platform.system()
    observation = {"system": system, "machine": platform.machine(),
                   "os_version": platform.release() if system == "Linux" else platform.version(),
                   "libc": platform.libc_ver()[1] if system == "Linux" else None}
    if system == "Darwin":
        observation["os_version"] = subprocess.check_output(
            ["sw_vers", "-productVersion"], text=True).strip()
        xcode = subprocess.check_output(["xcodebuild", "-version"], text=True)
        match = re.search(r"Xcode ([0-9.]+)", xcode)
        observation["xcode_version"] = match.group(1) if match else ""
    if system == "Windows":
        probe = subprocess.check_output(["powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_OperatingSystem | Select-Object Caption,ProductType | ConvertTo-Json -Compress"],
            text=True)
        product = json.loads(probe)
        observation["windows_product_name"] = product["Caption"]
        observation["windows_product_type"] = (
            "client" if product["ProductType"] == 1 else "server")
    family = TARGETS[target][2]
    if family:
        udid = selection.get("simulator_udid", "")
        if not UDID.fullmatch(udid):
            raise ValueError("selected simulator UDID is invalid")
        devices = json.loads(subprocess.check_output(
            ["xcrun", "simctl", "list", "-j", "devices", "available"]))["devices"]
        runtimes = json.loads(subprocess.check_output(
            ["xcrun", "simctl", "list", "-j", "runtimes"]))["runtimes"]
        matches = [(runtime, device) for runtime, entries in devices.items()
                   for device in entries if device.get("udid") == udid]
        if len(matches) != 1:
            raise ValueError("selected simulator is absent or ambiguous")
        runtime, device = matches[0]
        runtime_info = [entry for entry in runtimes if entry.get("identifier") == runtime]
        if len(runtime_info) != 1 or family.lower() not in runtime.lower():
            raise ValueError("selected simulator runtime is absent or foreign")
        observation.update({"guest_family": family, "guest_udid": udid,
                            "guest_runtime": runtime, "guest_version": runtime_info[0].get("version"),
                            "guest_state": device.get("state"), "guest_name": device.get("name")})
    return observation


def mode_script(target, mode, simulator_udid=None):
    lines = ["gradle.beforeProject { project ->",
             "  project.plugins.withId('org.jetbrains.kotlin.multiplatform') {",
             "    project.afterEvaluate {",
             f"      project.tasks.matching {{ it.name == '{target}Test' }}.configureEach {{ task ->",
             "        task.testLogging.showStandardStreams = true",
             "        task.testLogging.events('started', 'passed', 'failed', 'skipped', 'standardOut', 'standardError')",
             "      }"]
    if mode == "optimized-opt":
        lines += [f"      def nativeTarget = project.kotlin.targets.findByName('{target}')",
                  "      if (nativeTarget != null) {",
                  "        def kind = nativeTarget.binaries.getTest('DEBUG').buildType",
                  "        nativeTarget.binaries.test([kind.class.valueOf('RELEASE')])",
                  "        def release = nativeTarget.binaries.getTest('RELEASE')",
                  f"        project.tasks.matching {{ it.name == '{target}Test' }}.configureEach {{ task ->",
                  f"          task.dependsOn('linkReleaseTest' + '{target}'.capitalize())",
                  "          task.executable(release.outputFile)", "        }", "      }"]
    if simulator_udid:
        lines += [f"      project.tasks.matching {{ it.name == '{target}Test' }}.configureEach {{ task ->",
                  f"        task.device.set('{simulator_udid}')", "      }"]
    lines += ["    }", "  }", "}", ""]
    return "\n".join(lines).encode()


def staged_path(staging, module, target):
    return staging / qualify.target_binary_path(module, target)


def process_snapshot(expected_folders, simulator_udid):
    def wanted(image, command):
        return (any(Path(image).parent == folder for folder in expected_folders)
                or bool(simulator_udid and simulator_udid in command and "simctl" in command))

    system = platform.system()
    if system == "Linux":
        for entry in os.scandir("/proc"):
            if not entry.name.isdecimal():
                continue
            try:
                image = os.readlink(f"/proc/{entry.name}/exe")
                command = (Path(f"/proc/{entry.name}/cmdline").read_bytes()
                           .replace(b"\0", b" ").decode(errors="replace").strip())
                if not wanted(image, command):
                    continue
                status = Path(f"/proc/{entry.name}/status").read_text()
                parent = int(re.search(r"(?m)^PPid:\s*(\d+)$", status).group(1))
                yield {"pid": int(entry.name), "parent_pid": parent,
                       "image": image, "command": command,
                       "image_sha256": digest(Path(f"/proc/{entry.name}/exe").read_bytes())}
            except (OSError, AttributeError, ValueError):
                continue
    elif system == "Darwin":
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib")
        listing = subprocess.check_output(["/bin/ps", "-axo", "pid=,ppid=,command="], text=True)
        for line in listing.splitlines():
            match = re.match(r"\s*(\d+)\s+(\d+)\s+(.+)", line)
            if not match:
                continue
            pid, parent, command = match.groups()
            buffer = ctypes.create_string_buffer(4096)
            if libproc.proc_pidpath(int(pid), buffer, len(buffer)) <= 0:
                continue
            image = buffer.value.decode(errors="replace")
            if not wanted(image, command):
                continue
            try:
                sha = digest(Path(image).read_bytes())
            except OSError:
                continue
            yield {"pid": int(pid), "parent_pid": int(parent), "image": image,
                   "command": command, "image_sha256": sha}
    elif system == "Windows":
        script = ("Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,"
                  "ExecutablePath,CommandLine | ConvertTo-Json -Compress")
        rows = json.loads(subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", script], text=True))
        for row in rows if isinstance(rows, list) else [rows]:
            image = row.get("ExecutablePath")
            if not image or not wanted(image, row.get("CommandLine") or ""):
                continue
            try:
                sha = digest(Path(image).read_bytes())
            except OSError:
                continue
            yield {"pid": row["ProcessId"], "parent_pid": row["ParentProcessId"],
                   "image": image, "command": row.get("CommandLine") or "",
                   "image_sha256": sha}


def macos_gradle_daemon_snapshot(client_pid, java):
    if platform.system() != "Darwin" or not client_pid:
        return
    libproc = ctypes.CDLL("/usr/lib/libproc.dylib")
    listing = subprocess.check_output(["/bin/ps", "-axo", "pid=,ppid=,command="], text=True)
    for line in listing.splitlines():
        match = re.match(r"\s*(\d+)\s+(\d+)\s+(.+)", line)
        if not match or int(match[2]) != client_pid:
            continue
        pid, command = int(match[1]), match[3]
        if not command.endswith(" org.gradle.launcher.daemon.bootstrap.GradleDaemon 9.5.0"):
            continue
        buffer = ctypes.create_string_buffer(4096)
        if libproc.proc_pidpath(pid, buffer, len(buffer)) <= 0:
            continue
        image = buffer.value.decode(errors="replace")
        if Path(image) != java:
            continue
        try:
            sha = digest(Path(image).read_bytes())
        except OSError:
            continue
        yield {"pid": pid, "parent_pid": client_pid, "gradle_client_pid": client_pid,
               "image": image, "command": command, "image_sha256": sha}


def observe_test_processes(work_root, target, mode, simulator_udid, stop, destination,
                           gradle_client=None, java=None):
    binary_mode = "debugTest" if mode == "debug-g" else "releaseTest"
    expected = {short: (work_root / short / "bin" / target / binary_mode).resolve()
                for short in ("core", "facade")}
    seen = set()
    with destination.open("wb") as output:
        while not stop.is_set():
            try:
                if target == "macosArm64" and gradle_client and gradle_client.get("pid"):
                    for sample in macos_gradle_daemon_snapshot(gradle_client["pid"], java):
                        sample.update({"observed_ns": time.time_ns(),
                                       "module": "gradle-daemon", "simulator_udid": None})
                        key = (sample["pid"], sample["image_sha256"], "gradle-daemon")
                        if key not in seen:
                            output.write(encoded(sample))
                            output.flush()
                            seen.add(key)
                for sample in process_snapshot(expected.values(), simulator_udid):
                    image = Path(sample["image"])
                    short = next((key for key, folder in expected.items()
                                  if image.parent == folder and image.suffix in (".kexe", ".exe")), None)
                    simulator_command = (simulator_udid and "simctl spawn" in sample["command"]
                                         and simulator_udid in sample["command"])
                    if not short and not simulator_command:
                        continue
                    sample.update({"observed_ns": time.time_ns(), "module": short,
                                   "simulator_udid": simulator_udid if simulator_command else None})
                    key = (sample["pid"], sample["image_sha256"], short)
                    if key not in seen:
                        output.write(encoded(sample))
                        output.flush()
                        seen.add(key)
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
                pass
            stop.wait(0.02 if platform.system() == "Linux" else 0.1)


def macos_host_launcher_pid(stdout, gradle_home):
    lines = stdout.splitlines()
    prefixes = ("Starting process 'Gradle build daemon'.",
                "Successfully started process 'Gradle build daemon'",
                "An attempt to start the daemon took ",
                "The client will now receive all logging from the daemon ")
    positions = [[index for index, line in enumerate(lines) if line.startswith(prefix)]
                 for prefix in prefixes]
    builds = [index for index, line in enumerate(lines) if line == "Starting Build"]
    if (any(len(found) != 1 for found in positions) or len(builds) != 1
            or positions[0][0] + 1 != positions[1][0]
            or positions[1][0] + 1 != positions[2][0]
            or positions[2][0] + 1 != positions[3][0]
            or positions[3][0] >= builds[0]
            or any(line.startswith("> Task ") for line in lines[:builds[0]])):
        raise ValueError("selected macOS Native Gradle launcher is absent or ambiguous")
    daemon_dir = str(PurePosixPath(gradle_home) / "daemon" / "9.5.0")
    start = lines[positions[0][0]]
    if (not start.startswith("Starting process 'Gradle build daemon'. Working directory: "
                             f"{daemon_dir} Command: ")
            or not start.endswith(" org.gradle.launcher.daemon.bootstrap.GradleDaemon 9.5.0")
            or not re.fullmatch(r"An attempt to start the daemon took [0-9]+(?:\.[0-9]+)? secs\.",
                                lines[positions[2][0]])):
        raise ValueError("selected macOS Native Gradle launcher startup differs")
    match = re.fullmatch(
        r"The client will now receive all logging from the daemon "
        r"\(pid: ([1-9][0-9]*)\)\. The daemon log file: "
        + re.escape(daemon_dir) + r"/daemon-([1-9][0-9]*)\.out\.log",
        lines[positions[3][0]])
    if not match or match[1] != match[2]:
        raise ValueError("selected macOS Native Gradle launcher log identity differs")
    return int(match[1])


def macos_live_daemon_binding(samples, launcher_pid, client_pid, java, java_sha,
                              started_ns=None, finished_ns=None):
    daemons = [sample for sample in samples if sample.get("module") == "gradle-daemon"]
    if len(daemons) != 1:
        raise ValueError("selected macOS Gradle daemon live observation is absent or ambiguous")
    sample = daemons[0]
    if (sample.get("pid") != launcher_pid
            or sample.get("parent_pid") != client_pid
            or sample.get("gradle_client_pid") != client_pid
            or PurePosixPath(sample.get("image", "")) != PurePosixPath(java)
            or sample.get("image_sha256") != java_sha
            or not sample.get("command", "").endswith(
                " org.gradle.launcher.daemon.bootstrap.GradleDaemon 9.5.0")
            or sample.get("observed_ns", 0) <= 0
            or started_ns is not None and sample["observed_ns"] < started_ns
            or finished_ns is not None and sample["observed_ns"] > finished_ns):
        raise ValueError("selected macOS Gradle daemon is not bound to the live client")
    return sample


def macos_gradle_client_pid(archive):
    path = archive / "runtime/gradle-client.json"
    if not path.is_file():
        raise ValueError("selected macOS Gradle client live identity is absent")
    client = json.loads(path.read_bytes())
    if (not isinstance(client, dict) or set(client) != {"pid"}
            or type(client["pid"]) is not int or client["pid"] <= 0):
        raise ValueError("selected macOS Gradle client live identity differs")
    return client["pid"]


def simulator_spawn_parent(samples, binding, simulator_udid, executable,
                           started_ns, finished_ns):
    if (not all(type(value) is int and value > 0 for value in
                (binding.get("pid"), binding.get("parent_pid"),
                 binding.get("observed_ns"), started_ns, finished_ns))
            or not started_ns <= binding["observed_ns"] <= finished_ns
            or binding.get("image") != str(executable)):
        raise ValueError("selected simulator test process identity or time differs")
    parents = [sample for sample in samples
               if sample.get("pid") == binding["parent_pid"]]
    if len(parents) != 1:
        raise ValueError("selected simulator spawn parent is absent or ambiguous")
    parent = parents[0]
    image = parent.get("image")
    if (parent.get("module") is not None
            or parent.get("simulator_udid") != simulator_udid
            or type(parent.get("pid")) is not int or parent["pid"] <= 0
            or type(parent.get("parent_pid")) is not int or parent["parent_pid"] <= 0
            or type(parent.get("observed_ns")) is not int
            or not started_ns <= parent["observed_ns"] <= binding["observed_ns"]
            or not isinstance(image, str) or not PurePosixPath(image).is_absolute()
            or PurePosixPath(image).name != "simctl"
            or not SHA.fullmatch(str(parent.get("image_sha256", "")))):
        raise ValueError("selected simulator spawn parent identity or time differs")
    try:
        command = shlex.split(parent.get("command", ""))
    except (TypeError, ValueError):
        command = []
    if len(command) < 4 or command[:2] != [image, "spawn"]:
        raise ValueError("selected simulator spawn command differs")
    arguments = command[2:]
    while arguments and arguments[0].startswith("--") and arguments[0] != "--":
        arguments = arguments[1:]
    if len(arguments) < 2 or arguments[:2] != [simulator_udid, str(executable)]:
        raise ValueError("selected simulator guest or exact test executable differs")
    return parent


def process_binding(archive, work_root, target, mode, simulator_udid, short, binary_sha,
                    executable=None):
    samples = [json.loads(line) for line in (archive / "runtime/process-observations.jsonl").read_bytes().splitlines()]
    binary_mode = "debugTest" if mode == "debug-g" else "releaseTest"
    folder = work_root / short / "bin" / target / binary_mode
    matches = [sample for sample in samples if sample.get("module") == short
               and Path(sample["image"]).parent == folder
               and (executable is None or Path(sample["image"]) == Path(executable))
               and sample.get("image_sha256") == binary_sha
               and sample.get("pid", 0) > 0 and sample.get("parent_pid", 0) > 0]
    if target == "macosArm64":
        launcher_pid = macos_host_launcher_pid(
            (archive / "stdout.txt").read_text(), Path(os.environ["GRADLE_USER_HOME"]).resolve())
        java = Path(os.environ["JAVA_HOME"]).resolve() / "bin/java"
        macos_live_daemon_binding(samples, launcher_pid, macos_gradle_client_pid(archive), java,
                                  digest(java.read_bytes()))
        matches = [sample for sample in matches if sample["parent_pid"] == launcher_pid]
    if not matches:
        raise ValueError(f"selected {short} Native test launcher and executable bytes were not observed")
    if simulator_udid:
        guest = json.loads((archive / "simctl-guest.json").read_bytes())
        started_ns = guest.get("finished_ns")
        finished_ns = time.time_ns()
        simulator_spawn_parent(samples, matches[0], simulator_udid,
                               matches[0]["image"], started_ns, finished_ns)
    return matches[0]


def gradle_command(paths, lane, mode, hashes, task="qualificationEvidence"):
    path_type = PureWindowsPath if lane.startswith("mingwX64:") else PurePosixPath
    checkout = path_type(paths["checkout"])
    output = path_type(paths["archive_root"])
    work_root = path_type(paths["work_root"])
    return [paths["gradle"], "-p", str(checkout / PROJECT), "--project-cache-dir",
            str(work_root / "gradle-project-cache"), "--offline", "--no-daemon",
            "--console=plain", "--info", "--rerun-tasks", "--init-script",
            str(output / "inputs/mode.init.gradle"),
            f"-PqualificationCheckout={checkout}",
            f"-PqualificationRepository={paths['staging']}",
            f"-PqualificationArchiveRoot={output}",
            f"-PqualificationWorkRoot={work_root}",
            f"-PqualificationSourceInventory={output / 'inputs/source-inventory.tsv'}",
            f"-PqualificationCoreCases={output / 'inputs/core-cases.tsv'}",
            f"-PqualificationFacadeCases={output / 'inputs/facade-cases.tsv'}",
            f"-PqualificationCoreSha256={hashes['dyn4k-core']}",
            f"-PqualificationFacadeSha256={hashes['dyn4k']}",
            f"-PqualificationLaneId={lane}", f"-PqualificationMode={mode}",
            f"-PqualificationPython={paths['python']}",
            task]


def capture(archive, work_root, lane, core_cases, facade_cases, simulator_udid=None):
    target, _, _, mode = lane.split(":")
    binary_mode = "debugTest" if mode == "debug-g" else "releaseTest"
    observed = []
    records = {}
    for short, input_path in (("core", core_cases), ("facade", facade_cases)):
        selected = selected_rows(input_path.read_bytes())
        source = work_root / short / "test-results" / f"{target}Test"
        reports = sorted(source.glob("TEST-*.xml"))
        if not reports:
            raise ValueError(f"original {short} Native XML is absent")
        module_ids = []
        for report in reports:
            raw = report.read_bytes()
            ids, normal = original_report(raw, target, selected)
            module_ids.extend(ids)
            for section, data in (("raw", raw), ("normalized", normal)):
                path = archive / "reports" / section / short / report.name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                print(f"QUALIFICATION_{'RAW_' if section == 'raw' else ''}XML_SHA256={digest(data)}")
        check_method_coverage(module_ids, list(selected.values()))
        observed.extend(module_ids)
        binary_dir = work_root / short / "bin" / target / binary_mode
        binaries = [path for path in binary_dir.glob("*")
                    if path.is_file() and path.suffix in (".kexe", ".exe")]
        if len(binaries) != 1:
            raise ValueError(f"selected {short} Native test executable is absent or ambiguous")
        executable = binaries[0]
        copy = archive / "runtime" / f"{short}.program"
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(executable, copy)
        print(f"QUALIFICATION_RUNTIME_{short.upper()}_PROGRAM_SHA256={digest(copy.read_bytes())}")
        binding = process_binding(archive, work_root, target, mode, simulator_udid,
                                  short, digest(copy.read_bytes()), executable)
        records[short] = {"path": str(executable), "sha256": digest(copy.read_bytes()),
                          "archive": copy.relative_to(archive).as_posix(), "mode": binary_mode,
                          "target": target, "observed_process": binding}
    if len(observed) != 2523 or len(set(observed)) != 2523:
        raise ValueError("original Native full method set is incomplete or duplicate")
    order = archive / "reports/report-traversal.json"
    order.write_bytes(encoded(observed))
    print(f"QUALIFICATION_REPORT_TRAVERSAL_SHA256={digest(order.read_bytes())}")
    print("QUALIFICATION_CASE_COUNT=2523")
    return records


def archive_files(root):
    return [{"path": path.relative_to(root).as_posix(), "sha256": digest(path.read_bytes()),
             "mtime_ns": path.stat().st_mtime_ns}
            for path in sorted(root.rglob("*")) if path.is_file() and path != root / "receipt.json"]


def windows_component(name):
    if (not name or name in (".", "..") or len(name) > 255
            or name[-1] in (".", " ") or any(char in name for char in '\\/:*?"<>|\0')
            or any(ord(char) < 32 for char in name)
            or name.split(".", 1)[0].upper() in
            {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)),
             *(f"LPT{n}" for n in range(1, 10))}):
        raise ValueError("unsafe Windows archive path component")
    return name


def windows_components(path):
    value = PureWindowsPath(str(path))
    if (not value.is_absolute() or not re.fullmatch(r"[A-Za-z]:\\", value.anchor)
            or len(str(path)) >= 32767):
        raise ValueError("Windows archive path needs a local absolute drive")
    return value.anchor, tuple(windows_component(part) for part in value.parts[1:])


def windows_transport_name(name):
    if not isinstance(name, str) or not name.startswith("raw/") or "\\" in name:
        raise ValueError("unsafe Windows transport member")
    parts = name.split("/")
    if len(parts) < 2:
        raise ValueError("unsafe Windows transport member")
    for part in parts[1:]:
        windows_component(part)
    return tuple(parts[1:])


def windows_unique_names(names):
    observed = {}
    complete = set()
    for name in names:
        if name.casefold() in complete:
            raise ValueError("Windows transport has aliased duplicate members")
        complete.add(name.casefold())
        parts = name.split("/")
        for length in range(1, len(parts) + 1):
            prefix = "/".join(parts[:length])
            previous = observed.setdefault(prefix.casefold(), prefix)
            if previous != prefix:
                raise ValueError("Windows transport has aliased duplicate members")


class WindowsArchiveApi:
    READ_ATTRIBUTES = 0x80
    WRITE_ATTRIBUTES = 0x100
    SYNCHRONIZE = 0x100000
    LIST_DIRECTORY = 0x1
    TRAVERSE = 0x20
    ADD_FILE = 0x2
    ADD_SUBDIRECTORY = 0x4
    READ_DATA = 0x1
    WRITE_DATA = 0x2

    def __init__(self):
        if os.name != "nt":
            raise ValueError("Windows archive operation requires a Windows host")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.nt = ctypes.WinDLL("ntdll")
        word, dword, handle = ctypes.c_uint16, ctypes.c_uint32, ctypes.c_void_p

        class UnicodeString(ctypes.Structure):
            _fields_ = [("Length", word), ("MaximumLength", word),
                        ("Buffer", ctypes.c_wchar_p)]

        class ObjectAttributes(ctypes.Structure):
            _fields_ = [("Length", dword), ("RootDirectory", handle),
                        ("ObjectName", ctypes.POINTER(UnicodeString)),
                        ("Attributes", dword), ("SecurityDescriptor", handle),
                        ("SecurityQualityOfService", handle)]

        class IoStatusBlock(ctypes.Structure):
            _fields_ = [("Status", ctypes.c_long), ("Information", ctypes.c_size_t)]

        class FileTime(ctypes.Structure):
            _fields_ = [("low", dword), ("high", dword)]

        class FileInformation(ctypes.Structure):
            _fields_ = [("attributes", dword), ("created", FileTime),
                        ("accessed", FileTime), ("modified", FileTime),
                        ("volume", dword), ("size_high", dword), ("size_low", dword),
                        ("links", dword), ("index_high", dword), ("index_low", dword)]

        class BasicInformation(ctypes.Structure):
            _fields_ = [("created", ctypes.c_longlong), ("accessed", ctypes.c_longlong),
                        ("modified", ctypes.c_longlong), ("changed", ctypes.c_longlong),
                        ("attributes", dword)]

        self.UnicodeString = UnicodeString
        self.ObjectAttributes = ObjectAttributes
        self.IoStatusBlock = IoStatusBlock
        self.FileTime = FileTime
        self.FileInformation = FileInformation
        self.BasicInformation = BasicInformation
        self.kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, dword, dword, handle,
                                            dword, dword, handle]
        self.kernel.CreateFileW.restype = handle
        self.kernel.CloseHandle.argtypes = [handle]
        self.kernel.CloseHandle.restype = ctypes.c_int
        self.kernel.GetFileInformationByHandle.argtypes = [handle,
                                                           ctypes.POINTER(FileInformation)]
        self.kernel.GetFileInformationByHandle.restype = ctypes.c_int
        self.kernel.ReadFile.argtypes = [handle, handle, dword, ctypes.POINTER(dword), handle]
        self.kernel.ReadFile.restype = ctypes.c_int
        self.kernel.WriteFile.argtypes = [handle, handle, dword, ctypes.POINTER(dword), handle]
        self.kernel.WriteFile.restype = ctypes.c_int
        self.kernel.SetFileTime.argtypes = [handle, handle, handle, ctypes.POINTER(FileTime)]
        self.kernel.SetFileTime.restype = ctypes.c_int
        self.kernel.SetFileInformationByHandle.argtypes = [handle, dword, handle, dword]
        self.kernel.SetFileInformationByHandle.restype = ctypes.c_int
        self.nt.NtCreateFile.argtypes = [ctypes.POINTER(handle), dword,
            ctypes.POINTER(ObjectAttributes), ctypes.POINTER(IoStatusBlock), handle,
            dword, dword, dword, dword, handle, dword]
        self.nt.NtCreateFile.restype = ctypes.c_long

    def close(self, value):
        if not self.kernel.CloseHandle(value):
            raise ctypes.WinError(ctypes.get_last_error())

    def info(self, value, directory):
        data = self.FileInformation()
        if not self.kernel.GetFileInformationByHandle(value, ctypes.byref(data)):
            raise ctypes.WinError(ctypes.get_last_error())
        if (data.attributes & 0x400 or bool(data.attributes & 0x10) != directory
                or (not directory and data.links != 1)):
            raise ValueError("Windows archive contains a reparse point, hardlink, or wrong type")
        ticks = (data.modified.high << 32) | data.modified.low
        return ((data.volume, data.index_high, data.index_low, data.links,
                 (data.size_high << 32) | data.size_low, ticks, data.attributes),
                (ticks - 116444736000000000) * 100)

    def drive(self, anchor, *, writable=False):
        access = self.READ_ATTRIBUTES | self.TRAVERSE | self.LIST_DIRECTORY
        if writable:
            access |= self.ADD_FILE | self.ADD_SUBDIRECTORY
        value = self.kernel.CreateFileW("\\\\?\\" + anchor, access, 3, None, 3,
                                        0x02000000 | 0x00200000, None)
        if value in (None, ctypes.c_void_p(-1).value):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            self.info(value, True)
            return value
        except BaseException:
            self.close(value)
            raise

    def child(self, parent, name, *, directory, create=False, writable=False):
        windows_component(name)
        text = ctypes.create_unicode_buffer(name)
        string = self.UnicodeString(len(name) * 2, (len(name) + 1) * 2,
                                    ctypes.cast(text, ctypes.c_wchar_p))
        attributes = self.ObjectAttributes(ctypes.sizeof(self.ObjectAttributes), parent,
                                           ctypes.pointer(string), 0, None, None)
        status = self.IoStatusBlock()
        value = ctypes.c_void_p()
        access = self.READ_ATTRIBUTES | self.SYNCHRONIZE
        if create:
            access |= 0x10000
        if directory:
            access |= self.LIST_DIRECTORY | self.TRAVERSE
            if writable:
                access |= self.ADD_FILE | self.ADD_SUBDIRECTORY
        else:
            access |= (self.WRITE_DATA | self.WRITE_ATTRIBUTES) if writable else self.READ_DATA
        options = 0x00200000 | 0x20 | (0x1 if directory else 0x40)
        disposition = 2 if create else 1
        result = self.nt.NtCreateFile(ctypes.byref(value), access, ctypes.byref(attributes),
            ctypes.byref(status), None, 0x80, 3 if writable else 1,
            disposition, options, None, 0)
        if create and result & 0xffffffff == 0xc0000035:
            raise ValueError("Windows archive output already exists")
        if result < 0:
            raise OSError(f"NtCreateFile rejected anchored archive member: 0x{result & 0xffffffff:08x}")
        try:
            self.info(value, directory)
            return value
        except BaseException as error:
            try:
                if create:
                    self.discard(value, directory)
            except BaseException as cleanup_error:
                error.add_note(f"Windows archive cleanup failed: {cleanup_error}")
            try:
                self.close(value)
            except BaseException as cleanup_error:
                error.add_note(f"Windows archive cleanup failed: {cleanup_error}")
            raise

    def discard(self, value, directory):
        if not directory:
            basic = self.BasicInformation(0, 0, 0, 0, 0x80)
            if not self.kernel.SetFileInformationByHandle(
                    value, 0, ctypes.byref(basic), ctypes.sizeof(basic)):
                raise ctypes.WinError(ctypes.get_last_error())
        disposition = ctypes.c_byte(1)
        if not self.kernel.SetFileInformationByHandle(
                value, 4, ctypes.byref(disposition), ctypes.sizeof(disposition)):
            raise ctypes.WinError(ctypes.get_last_error())

    @contextlib.contextmanager
    def walk(self, path, *, create_last=False, writable=False):
        anchor, parts = windows_components(path)
        stack = contextlib.ExitStack()
        try:
            current = self.drive(anchor, writable=writable and
                                 (not parts or create_last and len(parts) == 1))
            stack.callback(self.close, current)
            for index, part in enumerate(parts):
                current = self.child(current, part, directory=True,
                                     create=create_last and index == len(parts) - 1,
                                     writable=writable and (index == len(parts) - 1
                                          or create_last and index == len(parts) - 2))
                stack.callback(self.close, current)
            yield current
        except BaseException as error:
            try:
                stack.close()
            except BaseException as cleanup_error:
                error.add_note(f"Windows archive close failed: {cleanup_error}")
            raise
        else:
            stack.close()

    def read(self, value):
        before, _ = self.info(value, False)
        remaining = before[4]
        chunks = []
        while remaining:
            length = min(remaining, 1024 * 1024)
            buffer = ctypes.create_string_buffer(length)
            count = ctypes.c_uint32()
            if not self.kernel.ReadFile(value, buffer, length, ctypes.byref(count), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if not 0 < count.value <= length:
                raise ValueError("Windows archive file ended during read")
            chunks.append(buffer.raw[:count.value])
            remaining -= count.value
        if self.info(value, False)[0] != before:
            raise ValueError("Windows archive file changed during read")
        return b"".join(chunks)

    def write(self, value, data, mtime_ns, mode):
        for offset in range(0, len(data), 1024 * 1024):
            chunk = data[offset:offset + 1024 * 1024]
            buffer = ctypes.create_string_buffer(chunk)
            count = ctypes.c_uint32()
            if not self.kernel.WriteFile(value, buffer, len(chunk), ctypes.byref(count), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if count.value != len(chunk):
                raise ValueError("Windows archive file write was short")
        if mtime_ns % 100:
            raise ValueError("Windows filesystem cannot retain this nanosecond timestamp")
        ticks = mtime_ns // 100 + 116444736000000000
        if not 0 <= ticks < 1 << 64:
            raise ValueError("Windows archive timestamp is outside FILETIME")
        stamp = self.FileTime(ticks & 0xffffffff, ticks >> 32)
        if not self.kernel.SetFileTime(value, None, None, ctypes.byref(stamp)):
            raise ctypes.WinError(ctypes.get_last_error())
        basic = self.BasicInformation(0, 0, 0, 0, 0x80 if mode & 0o222 else 0x1)
        if not self.kernel.SetFileInformationByHandle(value, 0, ctypes.byref(basic),
                                                      ctypes.sizeof(basic)):
            raise ctypes.WinError(ctypes.get_last_error())
        info, observed = self.info(value, False)
        if info[4] != len(data) or observed != mtime_ns:
            raise ValueError("Windows archive bytes or timestamp differ after write")

    def read_absolute(self, path):
        anchor, parts = windows_components(path)
        if not parts:
            raise ValueError("Windows archive file path is a drive root")
        with self.walk(PureWindowsPath(anchor, *parts[:-1])) as parent:
            value = self.child(parent, parts[-1], directory=False)
            try:
                return self.read(value)
            finally:
                self.close(value)

    def write_absolute(self, path, data):
        anchor, parts = windows_components(path)
        if not parts:
            raise ValueError("Windows archive file path is a drive root")
        with self.walk(PureWindowsPath(anchor, *parts[:-1]), writable=True) as parent:
            value = self.child(parent, parts[-1], directory=False, create=True, writable=True)
            try:
                self.write(value, data, time.time_ns() // 100 * 100, 0o600)
            finally:
                self.close(value)

    def scan(self, root):
        _, parts = windows_components(root)
        if not parts:
            raise ValueError("Windows raw archive root cannot be a drive root")
        rows = []
        with self.walk(root) as anchor:
            def visit(parent, path, prefix):
                for entry in sorted(os.scandir(path), key=lambda item: item.name.casefold()):
                    name = windows_component(entry.name)
                    relative = prefix + (name,)
                    directory = entry.is_dir(follow_symlinks=False)
                    value = self.child(parent, name, directory=directory)
                    try:
                        before, mtime_ns = self.info(value, directory)
                        if directory:
                            visit(value, Path(entry.path), relative)
                        else:
                            data = self.read(value)
                            mode = 0o444 if before[-1] & 1 else 0o666
                            rows.append((relative, data, mtime_ns, mode))
                        if self.info(value, directory)[0] != before:
                            raise ValueError("Windows archive member changed during scan")
                    finally:
                        self.close(value)
            visit(anchor, Path(root), ())
        windows_unique_names(["/".join(parts) for parts, _, _, _ in rows])
        return sorted(rows)

    def write_tree(self, destination, rows, *, create):
        _, parts = windows_components(destination)
        if not parts:
            raise ValueError("Windows archive output cannot be a drive root")
        with self.walk(destination, create_last=create, writable=True) as anchor:
            if not create and any(os.scandir(destination)):
                raise ValueError("Windows archive snapshot destination is not empty")
            directories = {(): anchor}
            opened = []
            created_files = []
            try:
                for relative, data, mtime_ns, mode in rows:
                    prefix = ()
                    for part in relative[:-1]:
                        child_prefix = prefix + (part,)
                        if child_prefix not in directories:
                            directories[child_prefix] = self.child(
                                directories[prefix], part, directory=True,
                                create=True, writable=True)
                            opened.append(directories[child_prefix])
                        prefix = child_prefix
                    parent = directories[prefix]
                    value = self.child(parent, relative[-1], directory=False,
                                       create=True, writable=True)
                    if create:
                        created_files.append(value)
                    try:
                        self.write(value, data, mtime_ns, mode)
                    finally:
                        if not create:
                            self.close(value)
                while created_files:
                    self.close(created_files[-1])
                    created_files.pop()
            except BaseException as error:
                if create:
                    cleanup_errors = []
                    while created_files:
                        value = created_files.pop()
                        try:
                            self.discard(value, False)
                        except BaseException as cleanup_error:
                            cleanup_errors.append(cleanup_error)
                        try:
                            self.close(value)
                        except BaseException as cleanup_error:
                            cleanup_errors.append(cleanup_error)
                    while opened:
                        value = opened.pop()
                        try:
                            self.discard(value, True)
                        except BaseException as cleanup_error:
                            cleanup_errors.append(cleanup_error)
                        try:
                            self.close(value)
                        except BaseException as cleanup_error:
                            cleanup_errors.append(cleanup_error)
                    try:
                        self.discard(anchor, True)
                    except BaseException as cleanup_error:
                        cleanup_errors.append(cleanup_error)
                    if cleanup_errors:
                        error.add_note(f"Windows archive cleanup failed: {cleanup_errors[0]}")
                raise
            finally:
                for value in reversed(opened):
                    self.close(value)


def windows_unpack_archive(transport_path, output):
    api = WindowsArchiveApi()
    source = io.BytesIO(api.read_absolute(transport_path))
    with tarfile.open(fileobj=source, mode="r:*") as transport:
        members = transport.getmembers()
        names = [member.name for member in members]
        windows_unique_names(names)
        if "transport-mtimes.json" not in names or "raw/receipt.json" not in names:
            raise ValueError("Windows transport inventory or receipt differs")
        paths = {}
        for member in members:
            if not member.isfile():
                raise ValueError("Windows transport has a link or special member")
            if member.name != "transport-mtimes.json":
                paths[member.name] = windows_transport_name(member.name)
        mtimes = json.loads(transport.extractfile("transport-mtimes.json").read())
        if (set(mtimes) != {name[4:] for name in paths}
                or any(type(value) is not int or value < 0 or value % 100
                       for value in mtimes.values())):
            raise ValueError("Windows transport timestamps differ")
        if any(value // 100 + 116444736000000000 >= 1 << 64
               for value in mtimes.values()):
            raise ValueError("Windows transport timestamp is outside FILETIME")
        rows = []
        for name in sorted(paths):
            member = transport.getmember(name)
            if member.mode & ~0o777:
                raise ValueError("Windows transport has privileged file mode")
            rows.append((paths[name], transport.extractfile(member).read(),
                         mtimes[name[4:]], member.mode))
    api.write_tree(output, rows, create=True)
    return Path(output)


def snapshot_archive(root, destination, *, platform_name=None):
    if (platform_name or os.name) == "nt":
        if os.name != "nt":
            raise ValueError("Windows archive snapshot requires a Windows host")
        api = WindowsArchiveApi()
        rows = api.scan(root)
        if not rows or ("receipt.json",) not in [row[0] for row in rows]:
            raise ValueError("raw archive receipt is absent")
        api.write_tree(destination, rows, create=False)
        return
    if not root.is_dir() or root.is_symlink():
        raise ValueError("raw archive root is absent or linked")
    members = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        independent_gates._file_path_name(relative.as_posix())
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("raw archive contains a link or special file")
        members.append(relative)
    if not members or Path("receipt.json") not in members:
        raise ValueError("raw archive receipt is absent")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    root_fd = os.open(root, directory_flags)
    try:
        for relative in members:
            parent_fd = os.dup(root_fd)
            try:
                for part in relative.parts[:-1]:
                    child_fd = os.open(part, directory_flags, dir_fd=parent_fd)
                    os.close(parent_fd)
                    parent_fd = child_fd
                before = os.stat(relative.name, dir_fd=parent_fd, follow_symlinks=False)
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                    raise ValueError("raw archive member changed before copy")
                identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size,
                                          value.st_mtime_ns, value.st_nlink)
                fd = os.open(relative.name, file_flags, dir_fd=parent_fd)
                try:
                    opened = os.fstat(fd)
                    if identity(opened) != identity(before):
                        raise ValueError("raw archive member changed during open")
                    with os.fdopen(fd, "rb", closefd=False) as source:
                        data = source.read()
                    after = os.fstat(fd)
                    current = os.stat(relative.name, dir_fd=parent_fd, follow_symlinks=False)
                    if not identity(before) == identity(opened) == identity(after) == identity(current):
                        raise ValueError("raw archive member changed during copy")
                    copy = destination / relative
                    copy.parent.mkdir(parents=True, exist_ok=True)
                    copy.write_bytes(data)
                    copy.chmod(stat.S_IMODE(before.st_mode) & 0o777)
                    os.utime(copy, ns=(before.st_mtime_ns, before.st_mtime_ns))
                finally:
                    os.close(fd)
            finally:
                os.close(parent_fd)
    finally:
        os.close(root_fd)


def pack_archive(root, output):
    root, output = Path(root), Path(output)
    if output.exists() or not root.is_dir():
        raise ValueError("transport output exists or raw archive is absent")
    if os.name == "nt":
        api = WindowsArchiveApi()
        rows = api.scan(root)
        if not rows or ("receipt.json",) not in [row[0] for row in rows]:
            raise ValueError("raw archive receipt is absent")
        mtimes = {"/".join(relative): mtime_ns for relative, _, mtime_ns, _ in rows}
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w", format=tarfile.PAX_FORMAT) as transport:
            for relative, data, mtime_ns, mode in rows:
                info = tarfile.TarInfo("raw/" + "/".join(relative))
                info.size = len(data)
                info.mode = mode
                info.mtime = mtime_ns // 1_000_000_000
                transport.addfile(info, io.BytesIO(data))
            encoded_mtimes = encoded(mtimes)
            info = tarfile.TarInfo("transport-mtimes.json")
            info.size = len(encoded_mtimes)
            transport.addfile(info, io.BytesIO(encoded_mtimes))
        data = stream.getvalue()
        api.write_absolute(output, data)
        return digest(data)
    mtimes = {}
    with tarfile.open(output, "w", format=tarfile.PAX_FORMAT) as transport:
        for path in sorted(root.rglob("*")):
            if path.is_symlink() or (path.is_file() and path.stat().st_nlink != 1):
                raise ValueError("raw transport contains a link")
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            independent_gates._file_path_name(relative)
            mtimes[relative] = path.stat().st_mtime_ns
            transport.add(path, arcname=f"raw/{relative}", recursive=False)
        data = encoded(mtimes)
        info = tarfile.TarInfo("transport-mtimes.json")
        info.size = len(data)
        transport.addfile(info, io.BytesIO(data))
    return digest(output.read_bytes())


def unpack_archive(transport_path, output):
    output = Path(output)
    if os.name == "nt":
        return windows_unpack_archive(transport_path, output)
    if not output.is_absolute() or output.exists() or output.is_symlink():
        raise ValueError("relocated raw output must be a new, unlinked absolute directory")
    with tarfile.open(transport_path, "r") as transport:
        members = transport.getmembers()
        names = [item.name for item in members]
        if len(names) != len(set(names)) or "transport-mtimes.json" not in names:
            raise ValueError("raw transport member inventory differs")
        for member in members:
            if (not member.isfile() or (member.name != "transport-mtimes.json"
                and (not member.name.startswith("raw/") or any(
                    part in ("", ".", "..") for part in member.name.split("/")[1:])))):
                raise ValueError("raw transport has a link or unsafe path")
            if member.name.startswith("raw/"):
                independent_gates._file_path_name(member.name[4:])
        mtimes = json.loads(transport.extractfile("transport-mtimes.json").read())
        paths = {name[4:] for name in names if name.startswith("raw/")}
        if set(mtimes) != paths:
            raise ValueError("raw transport timestamps differ")
        if any(type(value) is not int or value < 0 for value in mtimes.values()):
            raise ValueError("raw transport timestamp is invalid")
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        anchor = os.open("/", directory_flags)
        try:
            for part in output.parent.parts[1:]:
                child = os.open(part, directory_flags, dir_fd=anchor)
                os.close(anchor)
                anchor = child
            os.mkdir(output.name, dir_fd=anchor)
            root_fd = os.open(output.name, directory_flags, dir_fd=anchor)
            try:
                for relative in sorted(paths):
                    parent_fd = os.dup(root_fd)
                    try:
                        for part in Path(relative).parts[:-1]:
                            try:
                                os.mkdir(part, dir_fd=parent_fd)
                            except FileExistsError:
                                pass
                            child = os.open(part, directory_flags, dir_fd=parent_fd)
                            os.close(parent_fd)
                            parent_fd = child
                        name = Path(relative).name
                        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                     0o600, dir_fd=parent_fd)
                        try:
                            with os.fdopen(fd, "wb", closefd=False) as destination:
                                destination.write(transport.extractfile(f"raw/{relative}").read())
                            member = transport.getmember(f"raw/{relative}")
                            if member.mode & ~0o777:
                                raise ValueError("raw transport has privileged file mode")
                            os.fchmod(fd, member.mode & 0o777)
                            os.utime(fd, ns=(mtimes[relative], mtimes[relative]))
                        finally:
                            os.close(fd)
                    finally:
                        os.close(parent_fd)
            finally:
                os.close(root_fd)
        finally:
            os.close(anchor)
    return output


def run(repository, candidate, lane, staging, output, gradle, native_home, selection_path, hashes,
        hash_provenance="audited"):
    repository, staging, output, gradle, native_home = map(lambda value: Path(value).resolve(),
                                              (repository, staging, output, gradle, native_home))
    selection = json.loads(Path(selection_path).read_bytes())
    manifest, contract = lane_contract(repository, lane)
    target, _, _, mode = lane.split(":")
    if (git(repository, "rev-parse", "HEAD") != candidate
            or git(repository, "status", "--porcelain")):
        raise ValueError("producer requires a clean exact candidate checkout")
    if output.is_relative_to(repository) or staging.is_relative_to(repository):
        raise ValueError("external output or Maven repository aliases source checkout")
    if output.exists() and any(output.iterdir()):
        raise ValueError("output exists; preserve the earlier attempt")
    java_home = Path(os.environ["JAVA_HOME"]).resolve()
    gradle_home = Path(os.environ["GRADLE_USER_HOME"]).resolve()
    windows = platform.system() == "Windows"
    java = java_home / "bin" / ("java.exe" if windows else "java")
    java_version = subprocess.check_output([str(java), "-version"],
                                           stderr=subprocess.STDOUT, text=True)
    gradle_version = subprocess.check_output([str(gradle), "--version"], text=True)
    if 'version "21' not in java_version or "Gradle 9.5.0" not in gradle_version:
        raise ValueError("pinned JDK 21 or Gradle 9.5.0 differs")
    native_executable = native_home / "bin" / ("kotlinc-native.bat" if windows
                                               else "kotlinc-native")
    native_compiler = native_home / "konan/lib/kotlin-native-compiler-embeddable.jar"
    native_version = subprocess.check_output([str(native_executable), "-version"],
                                             stderr=subprocess.STDOUT, text=True)
    if "Kotlin/Native: 2.4.20" not in native_version or not native_compiler.is_file():
        raise ValueError("pinned Kotlin/Native 2.4.20 compiler differs")
    for module in MODULES:
        if digest(staged_path(staging, module, target).read_bytes()) != hashes[module]:
            raise ValueError(f"independently selected {module} KLIB differs")
    inputs = source_inputs(repository, candidate, contract)
    host = observed_host(target, selection)
    family = TARGETS[target][2]
    output.mkdir(parents=True, exist_ok=True)
    started = time.time_ns()
    attempt = {"candidate_sha": candidate, "lane": lane, "status": "NOT_RUN",
               "host": host, "selection": selection,
               "artifact_hash_provenance": hash_provenance}
    (output / "attempt.json").write_bytes(encoded(attempt))
    if family and host.get("guest_state") != "Booted":
        command = ["xcrun", "simctl", "boot", selection["simulator_udid"]]
        boot = subprocess.run(command, capture_output=True, text=True, check=False)
        (output / "simctl-boot.json").write_bytes(encoded({"command": command,
            "exit_code": boot.returncode, "stdout": boot.stdout, "stderr": boot.stderr}))
        if boot.returncode:
            raise ValueError("selected simulator boot failed; attempt retained")
        command = ["xcrun", "simctl", "bootstatus", selection["simulator_udid"], "-b"]
        status = subprocess.run(command, capture_output=True, text=True, check=False)
        (output / "simctl-bootstatus.json").write_bytes(encoded({"command": command,
            "exit_code": status.returncode, "stdout": status.stdout, "stderr": status.stderr}))
        if status.returncode:
            raise ValueError("selected simulator boot status failed; attempt retained")
        host = observed_host(target, selection)
    try:
        validate_host(lane, selection, host)
    except ValueError as error:
        attempt.update({"status": "NOT_RUN", "reason": str(error), "host": host})
        (output / "attempt.json").write_bytes(encoded(attempt))
        raise
    (output / "host.json").write_bytes(encoded(host))
    if family:
        command = ["xcrun", "simctl", "spawn", selection["simulator_udid"],
                   "launchctl", "list"]
        guest_started = time.time_ns()
        guest = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        guest_stdout, guest_stderr = guest.communicate()
        guest_finished = time.time_ns()
        (output / "simctl-guest.json").write_bytes(encoded({
            "command": command, "exit_code": guest.returncode, "pid": guest.pid,
            "started_ns": guest_started, "finished_ns": guest_finished,
            "stdout_sha256": digest(guest_stdout), "stderr_sha256": digest(guest_stderr)}))
        (output / "simctl-guest.stdout").write_bytes(guest_stdout)
        (output / "simctl-guest.stderr").write_bytes(guest_stderr)
        if guest.returncode:
            raise ValueError("selected simulator guest process failed; attempt retained")
    for name, data in inputs.items():
        path = output / "inputs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    script = mode_script(target, mode, selection.get("simulator_udid") if family else None)
    (output / "inputs/mode.init.gradle").write_bytes(script)
    (output / "inputs/runtime-selection.json").write_bytes(encoded(selection))
    work_root = output.parent / f"{output.name}-build"
    if work_root.exists():
        raise ValueError("external build root exists; preserve earlier attempt")
    work_root.mkdir()
    producer_paths = {"checkout": str(repository), "staging": str(staging),
                      "archive_root": str(output), "work_root": str(work_root),
                      "gradle": str(gradle), "native_home": str(native_home),
                      "python": str(Path(sys.executable).resolve())}
    command = gradle_command(producer_paths, lane, mode, hashes)
    stop = threading.Event()
    gradle_client = {"pid": None}
    monitor = threading.Thread(target=observe_test_processes, args=(work_root, target,
        mode, selection.get("simulator_udid") if family else None, stop,
        output / "runtime/process-observations.jsonl", gradle_client, java), daemon=True)
    (output / "runtime").mkdir(exist_ok=True)
    monitor.start()
    try:
        with (output / "stdout.txt").open("wb") as stdout, (output / "stderr.txt").open("wb") as stderr:
            process = subprocess.Popen(command, cwd=output, stdout=stdout, stderr=stderr)
            if target == "macosArm64":
                gradle_client["pid"] = process.pid
                (output / "runtime/gradle-client.json").write_bytes(encoded({"pid": process.pid}))
            exit_code = process.wait()
    finally:
        stop.set()
        monitor.join()
    if exit_code:
        attempt.update({"status": "FAILED", "exit_code": exit_code, "command": command,
                        "pid": process.pid})
        (output / "attempt.json").write_bytes(encoded(attempt))
        raise ValueError(f"external Native consumer exited {exit_code}; attempt retained")
    host_after = observed_host(target, selection)
    validate_host(lane, selection, host_after)
    if host_after != host:
        raise ValueError("selected host or simulator changed during test execution")
    (output / "host-after.json").write_bytes(encoded(host_after))
    products = json.loads((output / "runtime/products.json").read_bytes())
    finished = time.time_ns()
    attempt["status"] = "CAPTURED_UNAUDITED" if hash_provenance == "staging-self" else "PASSED"
    (output / "attempt.json").write_bytes(encoded(attempt))
    stamp = (started + finished) // 2
    for path in output.rglob("*"):
        if path.is_file():
            os.utime(path, ns=(stamp, stamp))
    toolchain = {"java_home": str(java_home), "java_version": java_version.splitlines()[0],
                 "java_sha256": digest(java.read_bytes()), "gradle_version": "Gradle 9.5.0",
                 "gradle_executable": str(gradle), "gradle_sha256": digest(gradle.read_bytes()),
                 "gradle_user_home": str(gradle_home), "kgp_version": "2.4.20",
                 "native_home": str(native_home),
                 "native_version": native_version.strip(),
                 "native_sha256": digest(native_executable.read_bytes()),
                 "native_compiler_sha256": digest(native_compiler.read_bytes()),
                 "python_executable": producer_paths["python"],
                 "python_version": platform.python_version(),
                 "python_sha256": digest(Path(sys.executable).read_bytes())}
    receipt = {"schema": 1, "status": attempt["status"], "candidate_sha": candidate,
               "source_tree": git(repository, "rev-parse", f"{candidate}^{{tree}}"),
               "lane": lane, **{key: manifest["lanes"][lane][key] for key in
                                ("target", "runtime", "version", "configuration")},
               "runtime_identity": digest(encoded(host)), "artifact_hashes": hashes,
               "artifact_hash_provenance": hash_provenance,
               "consumer_group": "full-suite",
               "consumer_contract_sha256": independent_gates.digest(contract),
               "source_inventory_sha256": digest(inputs["source-inventory.tsv"]),
               "producer_paths": producer_paths,
               "host": host, "host_after": host_after, "selection": selection,
               "toolchain": toolchain,
               "process": {"command": command, "cwd": str(output), "exit_code": 0,
                           "pid": process.pid, "parent_pid": os.getpid(),
                           "started_ns": started, "finished_ns": finished,
                           "stdout": "stdout.txt", "stderr": "stderr.txt"},
               "provider_graph": "provider-graph.json",
               "resolved_artifacts": {module: f"resolved/{module}-{target.lower()}-0.1.0-alpha.1.klib"
                                      for module in MODULES},
               "consumer_xml": sorted(path.relative_to(output).as_posix() for path in
                                      (output / "reports/normalized").rglob("TEST-*.xml")),
               "raw_consumer_xml": sorted(path.relative_to(output).as_posix() for path in
                                          (output / "reports/raw").rglob("TEST-*.xml")),
               "products": products,
               "consumer_build_sha256": {path: digest(subprocess.check_output(
                   ["git", "-C", str(repository), "show", f"{candidate}:{path}"]))
                   for path in (f"{PROJECT}/build.gradle.kts", f"{PROJECT}/settings.gradle.kts",
                                f"{PROJECT}/gradle.properties", f"{PROJECT}/core/build.gradle.kts",
                                f"{PROJECT}/facade/build.gradle.kts")},
               "producer_sha256": digest(subprocess.check_output(
                   ["git", "-C", str(repository), "show", f"{candidate}:{PRODUCER}"])),
               "files": archive_files(output)}
    (output / "receipt.json").write_bytes(encoded(receipt))
    return {"status": attempt["status"], "lane": lane,
            "archive_sha256": independent_gates.archive_digest(output),
            "selected_cases": 2523}


def cross_build(repository, candidate, lane, staging, output, gradle, native_home, hashes,
                hash_provenance="audited"):
    repository, staging, output, gradle, native_home = (
        Path(value).resolve() for value in (repository, staging, output, gradle, native_home))
    if not lane.startswith("linuxArm64:"):
        raise ValueError("cross build is limited to the Linux ARM64 lane")
    if (git(repository, "rev-parse", "HEAD") != candidate
            or git(repository, "status", "--porcelain")):
        raise ValueError("cross build requires a clean exact candidate checkout")
    verify_source_binding(repository, candidate)
    manifest, contract = lane_contract(repository, lane)
    if (output.is_relative_to(repository) or staging.is_relative_to(repository)
            or output.exists() or not staging.is_dir()):
        raise ValueError("cross build output must be new and staging external")
    host = observed_host("linuxArm64", {})
    validate_cross_build_host(host)
    java_home = Path(os.environ["JAVA_HOME"]).resolve()
    gradle_home = Path(os.environ["GRADLE_USER_HOME"]).resolve()
    java = java_home / "bin/java"
    native = native_home / "bin/kotlinc-native"
    compiler = native_home / "konan/lib/kotlin-native-compiler-embeddable.jar"
    java_version = subprocess.check_output([str(java), "-version"],
                                           stderr=subprocess.STDOUT, text=True).splitlines()[0]
    gradle_version = subprocess.check_output([str(gradle), "--version"], text=True)
    native_version = subprocess.check_output([str(native), "-version"],
                                             stderr=subprocess.STDOUT, text=True).strip()
    if ('version "21' not in java_version or "Gradle 9.5.0" not in gradle_version
            or "Kotlin/Native: 2.4.20" not in native_version or not compiler.is_file()):
        raise ValueError("cross build pinned compiler toolchain differs")
    for module in MODULES:
        if digest(staged_path(staging, module, "linuxArm64").read_bytes()) != hashes[module]:
            raise ValueError(f"cross build staged {module} KLIB differs")
    inputs = source_inputs(repository, candidate, contract)
    output.mkdir()
    (output / "attempt.json").write_bytes(encoded({"status": "NOT_RUN", "lane": lane,
        "candidate_sha": candidate, "phase": "linux-x64-cross-build"}))
    (output / "inputs").mkdir()
    for name, data in inputs.items():
        (output / "inputs" / name).write_bytes(data)
    mode = lane.rsplit(":", 1)[1]
    (output / "inputs/mode.init.gradle").write_bytes(mode_script("linuxArm64", mode))
    work_root = output.parent / f"{output.name}-build"
    if work_root.exists():
        raise ValueError("external cross build root exists; preserve earlier attempt")
    work_root.mkdir()
    paths = {"checkout": str(repository), "staging": str(staging),
             "archive_root": str(output), "work_root": str(work_root),
             "gradle": str(gradle), "native_home": str(native_home),
             "python": str(Path(sys.executable).resolve())}
    command = gradle_command(paths, lane, mode, hashes, "qualificationCrossBuild")
    started = time.time_ns()
    with (output / "stdout.txt").open("wb") as stdout, (output / "stderr.txt").open("wb") as stderr:
        process = subprocess.Popen(command, cwd=output, stdout=stdout, stderr=stderr)
        exit_code = process.wait()
    if exit_code:
        (output / "attempt.json").write_bytes(encoded({"status": "FAILED", "lane": lane,
            "phase": "linux-x64-cross-build", "exit_code": exit_code, "command": command}))
        raise ValueError(f"cross build exited {exit_code}; attempt retained")
    text = (output / "stdout.txt").read_text()
    if ("BUILD SUCCESSFUL" not in text
            or f"QUALIFICATION_CROSS_BUILD_LANE={lane}" not in text
            or "QUALIFICATION_SOURCE_COUNT=" not in text):
        raise ValueError("external cross build markers are absent; attempt retained")
    graph = json.loads((output / "provider-graph.json").read_bytes())
    if (graph.get("runtime_resolution") !=
            "native-test-executable; no separate KLIB runtime resolution"
            or {entry.get("project") for entry in graph.get("compile", [])} != {"core", "facade"}):
        raise ValueError("external cross build provider graph differs")
    chosen, foreign = ("-g", "-opt") if mode == "debug-g" else ("-opt", "-g")
    flags = {}
    products = {}
    binary_mode = "debugTest" if mode == "debug-g" else "releaseTest"
    (output / "runtime").mkdir()
    for short, module in (("core", "dyn4k-core"), ("facade", "dyn4k")):
        lines = re.findall(rf"(?m)^QUALIFICATION_COMPILER_FLAGS_{short.upper()}=(.*)$", text)
        if len(lines) != 1:
            raise ValueError("cross compiler flags are absent or duplicate")
        flags[short] = json.loads(lines[0])
        entry = next(item for item in graph["compile"] if item["project"] == short)
        artifact = next((item for item in entry["artifacts"] if item["component"] ==
            f"io.github.rubixhacker:{module}-linuxarm64:0.1.0-alpha.1"), None)
        if (artifact is None or artifact["sha256"] != hashes[module]
                or chosen not in flags[short] or foreign in flags[short]
                or flags[short].count("-friend-modules") != 1
                or flags[short][flags[short].index("-friend-modules") + 1] != artifact["file"]):
            raise ValueError("cross compiler mode, friend KLIB, or provider differs")
        if f"> Task :{short}:link{'Debug' if mode == 'debug-g' else 'Release'}TestLinuxArm64" not in text:
            raise ValueError("selected Linux ARM64 test image was not linked")
        staged = output / "resolved" / f"{module}-linuxarm64-0.1.0-alpha.1.klib"
        if digest(staged.read_bytes()) != hashes[module]:
            raise ValueError("resolved staged KLIB differs from selected hash")
        binaries = list((work_root / short / "bin/linuxArm64" / binary_mode).glob("*.kexe"))
        if len(binaries) != 1:
            raise ValueError("selected Linux ARM64 test executable is absent or ambiguous")
        data = binaries[0].read_bytes()
        validate_linux_arm64_elf(data)
        copy = output / "runtime" / f"{short}.program"
        shutil.copy2(binaries[0], copy)
        products[short] = {"source_path": str(binaries[0]), "archive":
            f"runtime/{short}.program", "sha256": digest(data), "mode": binary_mode,
            "elf_class": 64, "elf_machine": "AArch64"}
    toolchain = {"java_home": str(java_home), "java_version": java_version,
        "java_sha256": digest(java.read_bytes()), "gradle_executable": str(gradle),
        "gradle_version": "Gradle 9.5.0", "gradle_sha256": digest(gradle.read_bytes()),
        "gradle_user_home": str(gradle_home), "kgp_version": "2.4.20",
        "native_home": str(native_home), "native_version": native_version,
        "native_sha256": digest(native.read_bytes()),
        "native_compiler_sha256": digest(compiler.read_bytes()),
        "python_executable": paths["python"],
        "python_sha256": digest(Path(sys.executable).read_bytes())}
    (output / "attempt.json").write_bytes(encoded({"status": "COMPILED_ONLY", "lane": lane,
        "candidate_sha": candidate, "phase": "linux-x64-cross-build"}))
    finished = time.time_ns()
    stamp = (started + finished) // 2
    for path in output.rglob("*"):
        if path.is_file():
            os.utime(path, ns=(stamp, stamp))
    receipt = {"schema": 2, "status": "COMPILED_ONLY", "phase": "linux-x64-cross-build",
        "candidate_sha": candidate, "source_tree": git(repository, "rev-parse", f"{candidate}^{{tree}}"),
        "lane": lane, "consumer_contract_sha256": independent_gates.digest(contract),
        "artifact_hashes": hashes, "artifact_hash_provenance": hash_provenance,
        "source_inventory_sha256": digest(inputs["source-inventory.tsv"]),
        "build_host": host, "toolchain": toolchain, "producer_paths": paths,
        "process": {"command": command, "cwd": str(output), "exit_code": 0,
            "pid": process.pid, "parent_pid": os.getpid(), "started_ns": started,
            "finished_ns": finished, "stdout": "stdout.txt", "stderr": "stderr.txt"},
        "compiler_flags": flags, "provider_graph": "provider-graph.json",
        "products": products, "selected_cases": 2523,
        "producer_sha256": digest((repository / PRODUCER).read_bytes()),
        "consumer_build_sha256": {path: digest((repository / path).read_bytes()) for path in
            (f"{PROJECT}/build.gradle.kts", f"{PROJECT}/settings.gradle.kts",
             f"{PROJECT}/gradle.properties", f"{PROJECT}/core/build.gradle.kts",
             f"{PROJECT}/facade/build.gradle.kts")},
        "files": archive_files(output)}
    (output / "receipt.json").write_bytes(encoded(receipt))
    return {"status": "COMPILED_ONLY", "lane": lane,
            "build_archive_sha256": independent_gates.archive_digest(output),
            "products": {key: value["sha256"] for key, value in products.items()}}


def verify_cross_build_snapshot(root, repository, candidate, lane, hashes,
                                expected_digest, trusted_toolchain=None):
    if independent_gates.archive_digest(root) != expected_digest:
        raise ValueError("cross build archive digest differs from selected transfer")
    receipt = json.loads((root / "receipt.json").read_bytes())
    independent_gates._inventory(root, receipt)
    validate_cross_build_host(receipt.get("build_host", {}))
    _, contract = lane_contract(repository, lane)
    if (receipt.get("schema") != 2 or receipt.get("status") != "COMPILED_ONLY"
            or receipt.get("phase") != "linux-x64-cross-build"
            or receipt.get("lane") != lane or receipt.get("candidate_sha") != candidate
            or receipt.get("source_tree") != git(repository, "rev-parse", f"{candidate}^{{tree}}")
            or receipt.get("artifact_hashes") != hashes
            or receipt.get("consumer_contract_sha256") != independent_gates.digest(contract)
            or receipt.get("selected_cases") != 2523):
        raise ValueError("cross build candidate, lane, KLIB, or method contract differs")
    if trusted_toolchain is not None and receipt.get("toolchain") != trusted_toolchain:
        raise ValueError("cross build toolchain differs from independent selection")
    if receipt.get("producer_sha256") != digest((repository / PRODUCER).read_bytes()):
        raise ValueError("cross build producer differs from exact source")
    for path, sha in receipt.get("consumer_build_sha256", {}).items():
        if path not in {f"{PROJECT}/{name}" for name in ("build.gradle.kts",
            "settings.gradle.kts", "gradle.properties", "core/build.gradle.kts",
            "facade/build.gradle.kts")} or digest((repository / path).read_bytes()) != sha:
            raise ValueError("cross build external project differs")
    if len(receipt.get("consumer_build_sha256", {})) != 5:
        raise ValueError("cross build external project inventory differs")
    inputs = source_inputs(repository, candidate, contract)
    if any((root / "inputs" / name).read_bytes() != data for name, data in inputs.items()):
        raise ValueError("cross build original sources or method IDs differ")
    if receipt.get("source_inventory_sha256") != digest(inputs["source-inventory.tsv"]):
        raise ValueError("cross build original source inventory differs")
    mode = lane.rsplit(":", 1)[1]
    if (root / "inputs/mode.init.gradle").read_bytes() != mode_script("linuxArm64", mode):
        raise ValueError("cross build Native mode script differs")
    paths, process = receipt["producer_paths"], receipt["process"]
    if (process.get("command") != gradle_command(paths, lane, mode, hashes,
                                                   "qualificationCrossBuild")
            or process.get("cwd") != paths["archive_root"]
            or process.get("exit_code") != 0 or process.get("pid", 0) <= 0
            or process.get("parent_pid", 0) <= 0):
        raise ValueError("cross build Gradle process differs")
    stdout = (root / "stdout.txt").read_text()
    if ("BUILD SUCCESSFUL" not in stdout
            or f"QUALIFICATION_CROSS_BUILD_LANE={lane}" not in stdout
            or f"QUALIFICATION_SOURCE_COUNT={len(inputs['source-inventory.tsv'].splitlines())}" not in stdout):
        raise ValueError("cross build Gradle source or lane markers differ")
    graph = json.loads((root / "provider-graph.json").read_bytes())
    if (graph.get("runtime_resolution") !=
            "native-test-executable; no separate KLIB runtime resolution"
            or graph.get("gradle_user_home") != receipt["toolchain"]["gradle_user_home"]
            or {entry.get("project") for entry in graph.get("compile", [])} != {"core", "facade"}
            or len(graph["compile"]) != 2):
        raise ValueError("cross build provider graph differs")
    products = receipt.get("products", {})
    if set(products) != {"core", "facade"}:
        raise ValueError("cross build executable inventory differs")
    chosen, foreign = ("-g", "-opt") if mode == "debug-g" else ("-opt", "-g")
    for short, module in (("core", "dyn4k-core"), ("facade", "dyn4k")):
        entry = next(item for item in graph["compile"] if item["project"] == short)
        staged = [item for item in entry["artifacts"] if item["component"].startswith(
            "io.github.rubixhacker:")]
        expected_gavs = {f"io.github.rubixhacker:{name}-linuxarm64:0.1.0-alpha.1"
                         for name in MODULES}
        if (entry["configuration"] != "linuxArm64TestCompileKlibraries"
                or {item["component"] for item in staged} != expected_gavs
                or len(staged) != 2):
            raise ValueError("cross build provider GAV graph differs")
        for item in staged:
            name = "dyn4k-core" if item["component"].split(":")[1] == "dyn4k-core-linuxarm64" else "dyn4k"
            if item["sha256"] != hashes[name]:
                raise ValueError("cross build provider KLIB hash differs")
        friend = next(item for item in staged if item["component"] ==
                      f"io.github.rubixhacker:{module}-linuxarm64:0.1.0-alpha.1")
        flags = receipt["compiler_flags"][short]
        marker = re.findall(rf"(?m)^QUALIFICATION_COMPILER_FLAGS_{short.upper()}=(.*)$", stdout)
        if (len(marker) != 1 or json.loads(marker[0]) != flags
                or chosen not in flags or foreign in flags
                or flags.count("-friend-modules") != 1
                or flags[flags.index("-friend-modules") + 1] != friend["file"]):
            raise ValueError("cross build compiler mode or friend KLIB differs")
        klib = root / "resolved" / f"{module}-linuxarm64-0.1.0-alpha.1.klib"
        if digest(klib.read_bytes()) != hashes[module]:
            raise ValueError("cross build resolved KLIB bytes differ")
        product = products[short]
        binary_mode = "debugTest" if mode == "debug-g" else "releaseTest"
        program = independent_gates._file_path(root, product["archive"])
        if (product["archive"] != f"runtime/{short}.program"
                or product["mode"] != binary_mode
                or product["sha256"] != digest(program.read_bytes())
                or Path(product["source_path"]).parent != Path(paths["work_root"]) /
                    short / "bin/linuxArm64" / binary_mode
                or f"> Task :{short}:link{'Debug' if mode == 'debug-g' else 'Release'}TestLinuxArm64"
                    not in stdout):
            raise ValueError("cross build selected executable or mode differs")
        if not (program.stat().st_mode &
                (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)):
            raise ValueError("cross build executable mode has no execute bit")
        validate_linux_arm64_elf(program.read_bytes())
    return receipt


def observed_linux_process(process, executable, stop, samples):
    while not stop.is_set():
        try:
            image = os.readlink(f"/proc/{process.pid}/exe")
            if image == str(executable):
                command = Path(f"/proc/{process.pid}/cmdline").read_bytes().split(b"\0")
                samples.append({"pid": process.pid, "parent_pid": os.getpid(),
                    "image": image, "image_sha256": digest(
                        Path(f"/proc/{process.pid}/exe").read_bytes()),
                    "command": [part.decode(errors="replace") for part in command if part],
                    "observed_ns": time.time_ns()})
                return
        except OSError:
            pass
        time.sleep(0.001)


def execute_transferred_test(executable, output, short, selected):
    command = [str(executable), "--ktest_logger=TEAMCITY"]
    started = time.time_ns()
    process = subprocess.Popen(command, cwd=output, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    stop, samples = threading.Event(), []
    monitor = threading.Thread(target=observed_linux_process,
        args=(process, executable, stop, samples), daemon=True)
    monitor.start()
    try:
        stdout, stderr = process.communicate()
    finally:
        stop.set()
        monitor.join()
    finished = time.time_ns()
    (output / "runtime" / f"{short}.stdout").write_bytes(stdout)
    (output / "runtime" / f"{short}.stderr").write_bytes(stderr)
    record = {"command": command, "cwd": str(output), "exit_code": process.returncode,
        "pid": process.pid, "parent_pid": os.getpid(), "started_ns": started,
        "finished_ns": finished, "observed_process": samples[0] if samples else None,
        "stdout_sha256": digest(stdout), "stderr_sha256": digest(stderr)}
    (output / "runtime" / f"{short}.process.json").write_bytes(encoded(record))
    if process.returncode or not samples:
        raise ValueError(f"transferred {short} Native test process failed or image was not observed")
    if samples[0]["image_sha256"] != digest(executable.read_bytes()):
        raise ValueError(f"transferred {short} Native image bytes differ")
    ids = original_teamcity_events(stdout, selected)
    check_method_coverage(ids, list(selected.values()))
    (output / "runtime" / f"{short}.method-order.json").write_bytes(encoded(ids))
    return record, ids


def cross_run(repository, candidate, lane, build_archive, build_digest, output,
              selection_path, hashes):
    repository, build_archive, output = (Path(value).resolve() for value in
                                         (repository, build_archive, output))
    verify_source_binding(repository, candidate)
    if output.exists() or output.is_relative_to(repository):
        raise ValueError("cross runtime output must be new and outside source checkout")
    selection = json.loads(Path(selection_path).read_bytes())
    host = observed_host("linuxArm64", selection)
    output.mkdir()
    (output / "attempt.json").write_bytes(encoded({"status": "NOT_RUN", "lane": lane,
        "phase": "linux-arm64-runtime", "host": host, "selection": selection}))
    validate_host(lane, selection, host)
    snapshot = output / "build"
    snapshot.mkdir()
    snapshot_archive(build_archive, snapshot)
    build = verify_cross_build_snapshot(snapshot, repository, candidate, lane, hashes,
                                        build_digest)
    (output / "host.json").write_bytes(encoded(host))
    (output / "selection.json").write_bytes(encoded(selection))
    (output / "runtime").mkdir()
    observed = []
    records = {}
    for short in ("core", "facade"):
        executable = snapshot / "runtime" / f"{short}.program"
        if not os.access(executable, os.X_OK):
            raise ValueError("transferred test executable mode is absent")
        selected = selected_rows((snapshot / "inputs" / f"{short}-cases.tsv").read_bytes())
        record, ids = execute_transferred_test(executable, output, short, selected)
        records[short] = record
        observed.extend(ids)
    _, contract = lane_contract(repository, lane)
    check_method_coverage(observed, [item["id"] for item in contract["cases"]])
    after = observed_host("linuxArm64", selection)
    validate_host(lane, selection, after)
    if after != host:
        raise ValueError("ARM64 runtime host identity changed during execution")
    (output / "host-after.json").write_bytes(encoded(after))
    (output / "runtime/method-order.json").write_bytes(encoded(observed))
    (output / "attempt.json").write_bytes(encoded({"status": "CAPTURED_UNAUDITED"
        if build["artifact_hash_provenance"] == "staging-self" else "PASSED",
        "lane": lane, "phase": "linux-arm64-runtime", "host": host,
        "selection": selection, "selected_cases": 2523}))
    receipt = {"schema": 3, "status": "CAPTURED_UNAUDITED"
        if build["artifact_hash_provenance"] == "staging-self" else "PASSED",
        "candidate_sha": candidate, "lane": lane, "source_tree": build["source_tree"],
        "artifact_hashes": hashes, "artifact_hash_provenance":
            build["artifact_hash_provenance"], "build_archive_sha256": build_digest,
        "build_host": build["build_host"], "runtime_host": host,
        "runtime_host_after": after, "selection": selection,
        "processes": records, "method_order": observed,
        "selected_cases": 2523, "files": archive_files(output)}
    (output / "receipt.json").write_bytes(encoded(receipt))
    return {"status": receipt["status"], "lane": lane,
            "archive_sha256": independent_gates.archive_digest(output),
            "selected_cases": 2523}


def probe_arm_image(repository, candidate, lane, build_archive, build_digest,
                    output, selection_path, hashes):
    repository, build_archive, output = (Path(value).resolve() for value in
                                         (repository, build_archive, output))
    verify_source_binding(repository, candidate)
    if output.exists() or output.is_relative_to(repository):
        raise ValueError("ARM64 probe output must be new and outside source checkout")
    selection = json.loads(Path(selection_path).read_bytes())
    host = observed_host("linuxArm64", selection)
    output.mkdir()
    (output / "probe.json").write_bytes(encoded({"status": "NOT_RUN", "host": host,
        "selection": selection, "lane": lane}))
    validate_host(lane, selection, host)
    verify_cross_build_snapshot(build_archive, repository, candidate, lane, hashes,
                                build_digest)
    records = {}
    for short in ("core", "facade"):
        executable = build_archive / "runtime" / f"{short}.program"
        data = executable.read_bytes()
        validate_linux_arm64_elf(data)
        command = [str(executable), "--ktest_list_tests"]
        started = time.time_ns()
        process = subprocess.Popen(command, cwd=output, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        finished = time.time_ns()
        (output / f"{short}.stdout").write_bytes(stdout)
        (output / f"{short}.stderr").write_bytes(stderr)
        record = {"command": command, "status": "PROBED_NOT_RUN",
            "started_ns": started, "finished_ns": finished,
            "pid": process.pid, "parent_pid": os.getpid(),
            "exit_code": process.returncode, "transferred_image_sha256": digest(data),
            "stdout_sha256": digest(stdout), "stderr_sha256": digest(stderr)}
        records[short] = record
        (output / "probe.json").write_bytes(encoded({"status": "NOT_RUN", "lane": lane,
            "host": host, "selection": selection, "images": records}))
        if process.returncode:
            raise ValueError(f"ARM64 {short} test image listing failed")
        selected = selected_rows((build_archive / "inputs" /
                                  f"{short}-cases.tsv").read_bytes())
        original_test_listing(stdout, selected)
    (output / "probe.json").write_bytes(encoded({"status": "PROBED_NOT_RUN",
        "lane": lane, "host": host, "selection": selection, "images": records,
        "build_archive_sha256": build_digest, "candidate_sha": candidate}))
    return {"status": "PROBED_NOT_RUN", "lane": lane,
            "registered_methods": 2523, "runtime_host": host}


def verify_cross_run(root, repository, candidate, lane, hashes, selection,
                     archive_digest, build_digest, trusted_build_toolchain):
    repository, root = Path(repository).resolve(), Path(root)
    verify_source_binding(repository, candidate)
    if not SHA.fullmatch(archive_digest) or not SHA.fullmatch(build_digest):
        raise ValueError("independent cross archive digests are absent")
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary:
        snapshot = Path(temporary) / "archive"
        snapshot.mkdir()
        snapshot_archive(root, snapshot)
        if independent_gates.archive_digest(snapshot) != archive_digest:
            raise ValueError("cross runtime archive digest differs")
        receipt = json.loads((snapshot / "receipt.json").read_bytes())
        files = receipt.get("files", [])
        actual = {path.relative_to(snapshot).as_posix() for path in snapshot.rglob("*")
                  if path.is_file()}
        if (not files or len(files) != len({item.get("path") for item in files})
                or {item.get("path") for item in files} | {"receipt.json"} != actual):
            raise ValueError("cross runtime file inventory differs")
        for item in files:
            path = independent_gates._file_path(snapshot, item["path"])
            if (digest(path.read_bytes()) != item.get("sha256")
                    or path.stat().st_mtime_ns != item.get("mtime_ns")):
                raise ValueError("cross runtime file bytes or timestamps differ")
        build = verify_cross_build_snapshot(snapshot / "build", repository, candidate,
            lane, hashes, build_digest, trusted_build_toolchain)
        _, contract = lane_contract(repository, lane)
        if (receipt.get("schema") != 3 or receipt.get("lane") != lane
                or receipt.get("candidate_sha") != candidate
                or receipt.get("source_tree") != build["source_tree"]
                or receipt.get("artifact_hashes") != hashes
                or receipt.get("artifact_hash_provenance") !=
                    build["artifact_hash_provenance"]
                or receipt.get("build_archive_sha256") != build_digest
                or receipt.get("build_host") != build["build_host"]
                or receipt.get("selection") != selection
                or receipt.get("selected_cases") != 2523
                or receipt.get("status") != ("CAPTURED_UNAUDITED" if
                    build["artifact_hash_provenance"] == "staging-self" else "PASSED")):
            raise ValueError("cross runtime source, lane, or build binding differs")
        host = json.loads((snapshot / "host.json").read_bytes())
        after = json.loads((snapshot / "host-after.json").read_bytes())
        validate_host(lane, selection, host)
        if (after != host or receipt.get("runtime_host") != host
                or receipt.get("runtime_host_after") != after
                or json.loads((snapshot / "selection.json").read_bytes()) != selection):
            raise ValueError("cross runtime ARM64 host identity differs")
        observed = []
        processes = receipt.get("processes", {})
        if set(processes) != {"core", "facade"}:
            raise ValueError("cross runtime process inventory differs")
        for short in ("core", "facade"):
            record = json.loads((snapshot / "runtime" /
                                 f"{short}.process.json").read_bytes())
            binary = snapshot / "build/runtime" / f"{short}.program"
            sample = record.get("observed_process") or {}
            original_output = PurePosixPath(record.get("cwd", ""))
            original_image = original_output / "build/runtime" / f"{short}.program"
            stdout = (snapshot / "runtime" / f"{short}.stdout").read_bytes()
            stderr = (snapshot / "runtime" / f"{short}.stderr").read_bytes()
            if (record != processes[short] or not original_output.is_absolute()
                    or record.get("command") != [str(original_image),
                                                  "--ktest_logger=TEAMCITY"]
                    or record.get("exit_code") != 0
                    or record.get("pid", 0) <= 0 or record.get("parent_pid", 0) <= 0
                    or sample.get("pid") != record["pid"]
                    or sample.get("parent_pid") != record["parent_pid"]
                    or sample.get("image") != str(original_image)
                    or sample.get("image_sha256") != digest(binary.read_bytes())
                    or sample.get("command") != record["command"]
                    or not record.get("started_ns", 0) <= sample.get("observed_ns", -1)
                        <= record.get("finished_ns", -1)
                    or record.get("stdout_sha256") != digest(stdout)
                    or record.get("stderr_sha256") != digest(stderr)):
                raise ValueError("cross runtime live process, image, or output differs")
            selected = selected_rows((snapshot / "build/inputs" /
                                      f"{short}-cases.tsv").read_bytes())
            ids = original_teamcity_events(stdout, selected)
            check_method_coverage(ids, list(selected.values()))
            if json.loads((snapshot / "runtime" /
                           f"{short}.method-order.json").read_bytes()) != ids:
                raise ValueError("cross runtime original event order differs")
            observed.extend(ids)
        check_method_coverage(observed, [item["id"] for item in contract["cases"]])
        if (receipt.get("method_order") != observed
                or json.loads((snapshot / "runtime/method-order.json").read_bytes()) != observed):
            raise ValueError("cross runtime method order differs")
        return {"status": receipt["status"], "lane": lane,
            "candidate_sha": candidate, "selected_cases": 2523,
            "archive_sha256": archive_digest,
            "artifact_hash_provenance": receipt["artifact_hash_provenance"],
            "complete_selected_suite": True}


def verify(root, repository, candidate, lane, hashes, selection, archive_digest,
           trusted_toolchain):
    root, repository = Path(root), Path(repository).resolve()
    verify_source_binding(repository, candidate)
    manifest, contract = lane_contract(repository, lane)
    if not root.is_dir() or root.is_symlink() or not SHA.fullmatch(archive_digest):
        raise ValueError("independent archive provenance is absent")
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary:
        snapshot = Path(temporary) / "archive"
        snapshot.mkdir()
        snapshot_archive(root, snapshot)
        return verify_snapshot(snapshot, repository, candidate, lane, hashes, selection,
                               archive_digest, trusted_toolchain, manifest, contract)


def verify_snapshot(root, repository, candidate, lane, hashes, selection, archive_digest,
                    trusted_toolchain, manifest, contract):
    if independent_gates.archive_digest(root) != archive_digest:
        raise ValueError("independent archive provenance digest differs")
    receipt = json.loads((root / "receipt.json").read_bytes())
    independent_gates._inventory(root, receipt)
    if (receipt.get("candidate_sha") != candidate or receipt.get("lane") != lane
            or receipt.get("source_tree") != git(repository, "rev-parse", f"{candidate}^{{tree}}")
            or receipt.get("consumer_contract_sha256") != independent_gates.digest(contract)
            or receipt.get("consumer_group") != "full-suite"
            or receipt.get("artifact_hashes") != hashes):
        raise ValueError("archive candidate, lane, or staged KLIB contract differs")
    if receipt.get("artifact_hash_provenance", "audited") not in ("audited", "staging-self"):
        raise ValueError("staged KLIB hash selection provenance differs")
    if any(receipt.get(key) != manifest["lanes"][lane][key]
           for key in ("target", "runtime", "version", "configuration")):
        raise ValueError("archive target, runtime, version, or mode differs")
    if (receipt.get("selection") != selection or receipt.get("toolchain") != trusted_toolchain):
        raise ValueError("independently selected runtime or toolchain differs")
    if (not re.search(r'version "21(?:\.|\")', trusted_toolchain.get("java_version", ""))
            or trusted_toolchain.get("gradle_version") != "Gradle 9.5.0"
            or trusted_toolchain.get("kgp_version") != "2.4.20"
            or "Kotlin/Native: 2.4.20" not in trusted_toolchain.get("native_version", "")
            or any(not SHA.fullmatch(str(trusted_toolchain.get(key, "")))
                   for key in ("java_sha256", "gradle_sha256", "native_sha256",
                               "native_compiler_sha256", "python_sha256"))):
        raise ValueError("independently selected pinned toolchain is invalid")
    host = json.loads((root / "host.json").read_bytes())
    validate_host(lane, selection, host)
    if receipt.get("host") != host or receipt.get("runtime_identity") != digest(encoded(host)):
        raise ValueError("host identity differs from recorded execution")
    host_after = json.loads((root / "host-after.json").read_bytes())
    if receipt.get("host_after") != host_after or host_after != host:
        raise ValueError("host or simulator changed after Native execution")
    target, _, _, mode = lane.split(":")
    for path in (f"{PROJECT}/build.gradle.kts", f"{PROJECT}/settings.gradle.kts",
                 f"{PROJECT}/gradle.properties", f"{PROJECT}/core/build.gradle.kts",
                 f"{PROJECT}/facade/build.gradle.kts"):
        actual = digest(subprocess.check_output(["git", "-C", str(repository),
                                                "show", f"{candidate}:{path}"]))
        if receipt["consumer_build_sha256"].get(path) != actual:
            raise ValueError("external consumer build differs from exact source")
    if receipt.get("producer_sha256") != digest(subprocess.check_output(
            ["git", "-C", str(repository), "show", f"{candidate}:{PRODUCER}"])):
        raise ValueError("public producer differs from exact source")
    inputs = source_inputs(repository, candidate, contract)
    for name, data in inputs.items():
        if (root / "inputs" / name).read_bytes() != data:
            raise ValueError(f"original source or method input differs: {name}")
    if receipt.get("source_inventory_sha256") != digest(inputs["source-inventory.tsv"]):
        raise ValueError("original source inventory digest differs")
    script = mode_script(target, mode, selection.get("simulator_udid")
                         if TARGETS[target][2] else None)
    if (root / "inputs/mode.init.gradle").read_bytes() != script:
        raise ValueError("Native selected compiler or executable mode differs")
    if json.loads((root / "inputs/runtime-selection.json").read_bytes()) != selection:
        raise ValueError("archived runtime selection differs")
    paths, process = receipt["producer_paths"], receipt["process"]
    path_type = PureWindowsPath if target == "mingwX64" else PurePosixPath
    if (set(paths) != {"checkout", "staging", "archive_root", "work_root", "gradle",
                       "native_home", "python"}
            or any(not path_type(value).is_absolute() for value in paths.values())
            or any(path_type(paths[key]).is_relative_to(path_type(paths["checkout"]))
                   for key in ("archive_root", "work_root", "staging"))
            or process.get("cwd") != paths["archive_root"]
            or process.get("command") != gradle_command(paths, lane, mode, hashes)
            or process.get("exit_code") != 0
            or process.get("pid", 0) <= 0 or process.get("parent_pid", 0) <= 0):
        raise ValueError("original Gradle process identity, target, or mode differs")
    if (trusted_toolchain["gradle_executable"] != paths["gradle"]
            or trusted_toolchain["native_home"] != paths["native_home"]
            or trusted_toolchain["python_executable"] != paths["python"]):
        raise ValueError("producing executable paths differ from selected toolchain")
    stdout = (root / "stdout.txt").read_text()
    if "BUILD SUCCESSFUL" not in stdout or f"QUALIFICATION_LANE={lane}" not in stdout:
        raise ValueError("original Gradle run or lane marker differs")
    launcher_pid = (macos_host_launcher_pid(stdout, trusted_toolchain["gradle_user_home"])
                    if target == "macosArm64" else None)
    compiler_flags = {}
    for short in ("core", "facade"):
        if f"> Task :{short}:{target}Test" not in stdout:
            raise ValueError("selected Native runtime task did not execute")
        flag_lines = re.findall(rf"(?m)^QUALIFICATION_COMPILER_FLAGS_{short.upper()}=(.*)$", stdout)
        chosen = "-g" if mode == "debug-g" else "-opt"
        foreign = "-opt" if mode == "debug-g" else "-g"
        if len(flag_lines) != 1:
            raise ValueError("selected Native compiler mode was not executed")
        flags = json.loads(flag_lines[0])
        if (not isinstance(flags, list) or chosen not in flags or foreign in flags
                or any(type(flag) is not str for flag in flags)):
            raise ValueError("selected Native compiler mode was not executed")
        if flags.count("-friend-modules") != 1 or flags.index("-friend-modules") + 1 >= len(flags):
            raise ValueError("selected staged Native friend module was not compiled")
        compiler_flags[short] = flags
    if mode == "optimized-opt" and any(
            f"> Task :{short}:linkReleaseTest{target[0].upper() + target[1:]}"
            not in stdout for short in ("core", "facade")):
        raise ValueError("selected optimized Native test link did not execute")
    if TARGETS[target][2]:
        guest = json.loads((root / "simctl-guest.json").read_bytes())
        if (guest.get("command") != ["xcrun", "simctl", "spawn",
                                      selection["simulator_udid"], "launchctl", "list"]
                or guest.get("exit_code") != 0 or guest.get("pid", 0) <= 0
                or guest.get("stdout_sha256") != digest((root / "simctl-guest.stdout").read_bytes())
                or guest.get("stderr_sha256") != digest((root / "simctl-guest.stderr").read_bytes())
                or not process["started_ns"] <= guest.get("started_ns", -1)
                <= guest.get("finished_ns", -1) <= process["finished_ns"]):
            raise ValueError("selected simulator guest process differs")
    if "QUALIFICATION_CASE_COUNT=2523" not in stdout:
        raise ValueError("original portable case count differs")
    order = (root / "reports/report-traversal.json").read_bytes()
    if f"QUALIFICATION_REPORT_TRAVERSAL_SHA256={digest(order)}" not in stdout:
        raise ValueError("original report traversal is not process bound")
    graph_path = independent_gates._file_path(root, receipt["provider_graph"])
    if f"QUALIFICATION_PROVIDER_GRAPH_SHA256={digest(graph_path.read_bytes())}" not in stdout:
        raise ValueError("resolved provider graph is not process bound")
    graph = json.loads(graph_path.read_bytes())
    if graph.get("gradle_user_home") != trusted_toolchain["gradle_user_home"]:
        raise ValueError("Gradle provider cache identity differs")
    expected_components = {f"io.github.rubixhacker:{module}:0.1.0-alpha.1"
                           for module in MODULES} | {
                           f"io.github.rubixhacker:{module}-{target.lower()}:0.1.0-alpha.1"
                           for module in MODULES}
    if graph.get("runtime_resolution") != "native-test-executable; no separate KLIB runtime resolution":
        raise ValueError("Native runtime graph label differs")
    for phase in ("compile",):
        entries = graph.get(phase)
        if (not isinstance(entries, list) or len(entries) != 2
                or {entry.get("project") for entry in entries} != {"core", "facade"}):
            raise ValueError("external provider graph is incomplete")
        for entry in entries:
            components = {value for value in entry["components"]
                          if value.startswith("io.github.rubixhacker:")}
            expected_artifacts = {f"io.github.rubixhacker:{module}-{target.lower()}:0.1.0-alpha.1"
                                  for module in MODULES}
            staged_artifacts = [item for item in entry["artifacts"]
                                if item["component"].startswith("io.github.rubixhacker:")]
            if (entry["configuration"] != f"{target}TestCompileKlibraries"
                    or components != expected_components
                    or len(staged_artifacts) != 2
                    or {item["component"] for item in staged_artifacts} != expected_artifacts):
                raise ValueError("external provider graph has a foreign or missing KLIB")
            for module in MODULES:
                component = f"io.github.rubixhacker:{module}-{target.lower()}:0.1.0-alpha.1"
                item = next(value for value in staged_artifacts
                            if value["component"] == component)
                candidate_path = path_type(item["file"])
                cache = path_type(trusted_toolchain["gradle_user_home"]) / "caches/modules-2"
                staged = path_type(paths["staging"]) / qualify.target_binary_path(module, target)
                if (item["sha256"] != hashes[module]
                        or item["size"] != len(independent_gates._file_path(
                            root, receipt["resolved_artifacts"][module]).read_bytes())
                        or not candidate_path.is_absolute()
                        or not (candidate_path == staged
                                or candidate_path.is_relative_to(cache))):
                    raise ValueError("resolved provider KLIB hash or origin differs")
                expected_friend = "dyn4k-core" if entry["project"] == "core" else "dyn4k"
                if phase == "compile" and module == expected_friend:
                    flags = compiler_flags[entry["project"]]
                    if path_type(flags[flags.index("-friend-modules") + 1]) != candidate_path:
                        raise ValueError("Native friend module differs from resolved staged KLIB")
    for module, relative in receipt["resolved_artifacts"].items():
        data = independent_gates._file_path(root, relative).read_bytes()
        if (digest(data) != hashes[module] or
                f"QUALIFICATION_RESOLVED_{module.upper().replace('-', '_')}_SHA256={digest(data)}"
                not in stdout):
            raise ValueError("resolved staged KLIB bytes differ")
    products = json.loads((root / "runtime/products.json").read_bytes())
    if receipt.get("products") != products or set(products) != {"core", "facade"}:
        raise ValueError("selected Native executable inventory differs")
    binary_mode = "debugTest" if mode == "debug-g" else "releaseTest"
    samples = [json.loads(line) for line in (root / "runtime/process-observations.jsonl").read_bytes().splitlines()]
    if target == "macosArm64":
        if macos_gradle_client_pid(root) != process["pid"]:
            raise ValueError("selected macOS Gradle client differs from the pinned invocation")
        macos_live_daemon_binding(
            samples, launcher_pid, process["pid"],
            PurePosixPath(trusted_toolchain["java_home"]) / "bin/java",
            trusted_toolchain["java_sha256"], process["started_ns"], process["finished_ns"])
    for short, product in products.items():
        copy = independent_gates._file_path(root, product["archive"])
        expected_path = path_type(paths["work_root"]) / short / "bin" / target / binary_mode
        if (product["mode"] != binary_mode or product["target"] != target
                or path_type(product["path"]).parent != expected_path
                or product["sha256"] != digest(copy.read_bytes())
                or f"QUALIFICATION_RUNTIME_{short.upper()}_PROGRAM_SHA256={product['sha256']}"
                not in stdout):
            raise ValueError("selected Native executable bytes, target, or mode differ")
        binding = product.get("observed_process")
        if (not isinstance(binding, dict) or binding not in samples
                or binding.get("module") != short
                or binding.get("image_sha256") != product["sha256"]
                or path_type(binding.get("image", "")) != path_type(product["path"])
                or binding.get("pid", 0) <= 0 or binding.get("parent_pid", 0) <= 0
                or launcher_pid is not None and binding.get("parent_pid") != launcher_pid
                or not process["started_ns"] <= binding.get("observed_ns", -1)
                <= process["finished_ns"]):
            raise ValueError("selected Native test process is not bound to executable bytes")
        if TARGETS[target][2]:
            simulator_spawn_parent(samples, binding, selection["simulator_udid"],
                                   product["path"], process["started_ns"],
                                   process["finished_ns"])
    observed = []
    expected_raw_paths = sorted(path.relative_to(root).as_posix() for path in
                                (root / "reports/raw").rglob("TEST-*.xml"))
    expected_normal_paths = sorted(path.relative_to(root).as_posix() for path in
                                   (root / "reports/normalized").rglob("TEST-*.xml"))
    if (receipt.get("raw_consumer_xml") != expected_raw_paths
            or receipt.get("consumer_xml") != expected_normal_paths
            or {path.replace("reports/raw/", "reports/normalized/", 1)
                for path in expected_raw_paths} != set(expected_normal_paths)):
        raise ValueError("original or normalized Native XML inventory differs")
    for short in ("core", "facade"):
        selected = selected_rows(inputs[f"{short}-cases.tsv"])
        raw_paths = sorted(path for path in receipt["raw_consumer_xml"]
                           if path.startswith(f"reports/raw/{short}/"))
        if not raw_paths:
            raise ValueError("original Native XML is absent")
        module_ids = []
        for relative in raw_paths:
            raw = (root / relative).read_bytes()
            ids, normalized = original_report(raw, target, selected)
            module_ids.extend(ids)
            normal = root / relative.replace("reports/raw/", "reports/normalized/", 1)
            if (normal.read_bytes() != normalized
                    or f"QUALIFICATION_RAW_XML_SHA256={digest(raw)}" not in stdout
                    or f"QUALIFICATION_XML_SHA256={digest(normalized)}" not in stdout):
                raise ValueError("normalized XML differs from process bound original assertions")
        check_method_coverage(module_ids, list(selected.values()))
        observed.extend(module_ids)
    check_method_coverage(observed, [case["id"] for case in contract["cases"]])
    if json.loads(order) != observed:
        raise ValueError("original Native report traversal differs")
    return {"status": "PASSED", "lane": lane, "candidate_sha": candidate,
            "selected_cases": len(observed), "archive_sha256": archive_digest,
            "artifact_hash_provenance": receipt.get("artifact_hash_provenance", "audited"),
            "complete_selected_suite": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    probe = sub.add_parser("probe")
    probe.add_argument("--lane", required=True)
    pack = sub.add_parser("pack")
    pack.add_argument("--archive", required=True)
    pack.add_argument("--output", required=True)
    unpack = sub.add_parser("unpack")
    unpack.add_argument("--transport", required=True)
    unpack.add_argument("--output", required=True)
    capture_parser = sub.add_parser("capture")
    for name in ("repository", "archive", "work-root", "lane", "core-cases", "facade-cases"):
        capture_parser.add_argument(f"--{name}", required=True)
    produce, replay = sub.add_parser("run"), sub.add_parser("verify")
    cross_produce = sub.add_parser("cross-build")
    cross_execute = sub.add_parser("cross-run")
    arm_probe = sub.add_parser("probe-arm-image")
    cross_replay = sub.add_parser("verify-cross-run")
    for route in (produce, replay, cross_produce, cross_execute, arm_probe, cross_replay):
        for name in ("repository", "candidate-sha", "lane", "expected-core-sha256",
                     "expected-facade-sha256"):
            route.add_argument(f"--{name}", required=True)
    for route in (produce, replay, cross_execute, arm_probe, cross_replay):
        route.add_argument("--runtime-selection", required=True)
    for route in (produce, cross_produce):
        for name in ("staging", "output", "gradle", "native-home"):
            route.add_argument(f"--{name}", required=True)
        route.add_argument("--hash-provenance", choices=("audited", "staging-self"),
                           default="audited")
    for route in (cross_execute, arm_probe):
        route.add_argument("--build-archive", required=True)
        route.add_argument("--output", required=True)
    for route in (cross_execute, arm_probe, cross_replay):
        route.add_argument("--expected-build-archive-digest", required=True)
    for name in ("archive", "expected-archive-digest", "trusted-toolchain"):
        replay.add_argument(f"--{name}", required=True)
    for name in ("archive", "expected-archive-digest", "trusted-build-toolchain"):
        cross_replay.add_argument(f"--{name}", required=True)
    args = parser.parse_args(argv)
    if args.action == "probe":
        target, _, role, _ = args.lane.split(":")
        if target not in TARGETS or TARGETS[target][2]:
            raise ValueError("host probe requires a supported non-simulator target")
        host = observed_host(target, {})
        print(json.dumps({"lane": args.lane, "role": role, **host}, sort_keys=True))
        return 0
    if args.action == "pack":
        print(json.dumps({"transport_sha256": pack_archive(args.archive, args.output)}))
        return 0
    if args.action == "unpack":
        unpack_archive(args.transport, args.output)
        print(json.dumps({"archive": args.output}))
        return 0
    if args.action == "capture":
        selection = json.loads((Path(args.archive) / "inputs/runtime-selection.json").read_bytes())
        records = capture(Path(args.archive), Path(args.work_root), args.lane,
                          Path(args.core_cases), Path(args.facade_cases),
                          selection.get("simulator_udid"))
        path = Path(args.archive) / "runtime/products.json"
        path.write_bytes(encoded(records))
        print(f"QUALIFICATION_RUNTIME_PRODUCTS_SHA256={digest(path.read_bytes())}")
        return 0
    hashes = {"dyn4k-core": args.expected_core_sha256,
              "dyn4k": args.expected_facade_sha256}
    if any(not SHA.fullmatch(value) for value in hashes.values()):
        parser.error("independently audited target KLIB SHA-256 values are required")
    if args.action == "run":
        result = run(args.repository, args.candidate_sha, args.lane, args.staging,
                     args.output, args.gradle, args.native_home, args.runtime_selection, hashes,
                     args.hash_provenance)
    elif args.action == "cross-build":
        result = cross_build(args.repository, args.candidate_sha, args.lane, args.staging,
            args.output, args.gradle, args.native_home, hashes, args.hash_provenance)
    elif args.action == "cross-run":
        try:
            result = cross_run(args.repository, args.candidate_sha, args.lane,
                args.build_archive, args.expected_build_archive_digest, args.output,
                args.runtime_selection, hashes)
        except Exception as error:
            output = Path(args.output)
            if output.is_dir() and list((output / "runtime").glob("*.process.json")):
                (output / "attempt.json").write_bytes(encoded({"status": "FAILED",
                    "lane": args.lane, "phase": "linux-arm64-runtime", "reason": str(error)}))
            raise
    elif args.action == "probe-arm-image":
        result = probe_arm_image(args.repository, args.candidate_sha, args.lane,
            args.build_archive, args.expected_build_archive_digest, args.output,
            args.runtime_selection, hashes)
    elif args.action == "verify-cross-run":
        result = verify_cross_run(args.archive, args.repository, args.candidate_sha,
            args.lane, hashes, json.loads(Path(args.runtime_selection).read_bytes()),
            args.expected_archive_digest, args.expected_build_archive_digest,
            json.loads(Path(args.trusted_build_toolchain).read_bytes()))
    else:
        selection = json.loads(Path(args.runtime_selection).read_bytes())
        toolchain = json.loads(Path(args.trusted_toolchain).read_bytes())
        result = verify(args.archive, args.repository, args.candidate_sha, args.lane,
                        hashes, selection, args.expected_archive_digest, toolchain)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in ("PASSED", "CAPTURED_UNAUDITED", "COMPILED_ONLY",
                                      "PROBED_NOT_RUN") else 1


if __name__ == "__main__":
    sys.exit(main())
