#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import independent_gates


CONSUMER = "consumers/qualification/portable/full-apple-device"
PRODUCER = "tools/qualification/full_apple_device_consumer.py"
MODULES = ("dyn4k-core", "dyn4k")
VERSION = "0.1.0-alpha.1"
TARGETS = {
    "iosArm64": ("iOS physical ARM64", "iOS", 15, "LP64"),
    "tvosArm64": ("tvOS physical ARM64", "tvOS", 15, "LP64"),
    "watchosArm64": ("watchOS physical ILP32", "watchOS", 8, "ILP32"),
    "watchosDeviceArm64": ("watchOS physical LP64", "watchOS", 26, "LP64"),
}
MINIMUM_PATCHES = {"iosArm64": "15.8.8", "tvosArm64": "15.6",
                   "watchosArm64": "8.8.2", "watchosDeviceArm64": "26.6"}
BUILD_FILES = tuple(f"{CONSUMER}/{name}" for name in (
    "settings.gradle.kts", "build.gradle.kts", "core/build.gradle.kts",
    "facade/build.gradle.kts",
    "core/src/nativeTest/kotlin/qualification/DeviceImageProofTest.kt",
    "facade/src/nativeTest/kotlin/qualification/DeviceImageProofTest.kt"))
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
START = re.compile(r"^\[ RUN      \] (\S+)$")
PASS = re.compile(r"^\[       OK \] (\S+) \(([0-9]+) ms\)$")
SUMMARY = re.compile(r"^\[  PASSED  \] ([0-9]+) tests?\.?$")
IMAGE_PROOF = "qualification.DeviceImageProofTest.copyInstalledImageToDataContainer"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode() + b"\n"


def git(repository, *args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C",
                                    str(repository), *args], stderr=subprocess.PIPE)


def lane_contract(repository, lane_id):
    manifest = independent_gates.load_approved_manifest(repository)
    lane = manifest["lanes"].get(lane_id)
    if lane is None or lane["target"] not in TARGETS:
        raise ValueError("physical Apple lane is absent from approved manifest")
    runtime, _, _, _ = TARGETS[lane["target"]]
    if (lane["runtime"] != runtime or lane["version"] not in ("minimum", "current")
            or lane["configuration"] not in ("debug-g", "optimized-opt")):
        raise ValueError("physical Apple lane differs from approved matrix")
    contract = independent_gates.consumer_contract(manifest, lane_id)
    cases = contract["cases"]
    if (len(cases) != 2523 or len({item["id"] for item in cases}) != 2523
            or sum(item["module"] == "dyn4k-core" for item in cases) != 2465
            or sum(item["module"] == "dyn4k" for item in cases) != 58
            or any(item["scope"] != "portable" for item in cases)):
        raise ValueError("approved portable case contract differs")
    return lane, contract


def matrix(repository):
    manifest = independent_gates.load_approved_manifest(repository)
    return sorted(lane for lane, data in manifest["lanes"].items()
                  if data["target"] in TARGETS)


def source_inventory(repository, candidate, cases):
    roots = ("dyn4k-core/src/commonTest/kotlin", "dyn4k-core/src/nativeTest/kotlin",
             "dyn4k/src/commonTest/kotlin")
    tracked = sorted(path for path in git(repository, "ls-tree", "-r", "--name-only",
                                          candidate, "--", *roots).decode().splitlines()
                     if path.endswith(".kt"))
    live = sorted(path.relative_to(repository).as_posix() for root in roots
                  for path in (repository / root).rglob("*.kt") if path.is_file())
    if not tracked or tracked != live:
        raise ValueError("original portable test source tree differs from candidate")
    hashes = {}
    for path in tracked:
        original = git(repository, "show", f"{candidate}:{path}")
        if (repository / path).read_bytes() != original:
            raise ValueError(f"original test source differs: {path}")
        hashes[path] = sha(original)
    if any(hashes.get(item["source"]["path"]) != item["source"]["sha256"]
           for item in cases):
        raise ValueError("approved selected method differs from original source")
    return hashes


def staged(staging, module, target):
    variant = target.lower()
    name = f"{module}-{variant}-{VERSION}.klib"
    return staging / "io/github/rubixhacker" / f"{module}-{variant}" / VERSION / name


def load_os_selection(path, expected_sha256):
    if not SHA64.fullmatch(expected_sha256 or ""):
        raise ValueError("independent OS selection digest is missing")
    selected = Path(path)
    if selected.is_symlink() or not selected.is_file():
        raise ValueError("independent OS selection is absent or symbolic")
    raw = selected.read_bytes()
    if sha(raw) != expected_sha256:
        raise ValueError("independent OS selection digest differs")
    selection = json.loads(raw, object_pairs_hook=independent_gates._strict_object)
    if (set(selection) != {"schema", "roles"} or selection["schema"] != 1
            or not isinstance(selection["roles"], dict)
            or set(selection["roles"]) != set(TARGETS)):
        raise ValueError("independent OS selection matrix differs")
    for target, roles in selection["roles"].items():
        if not isinstance(roles, dict) or set(roles) != {"minimum", "current",
                                                            "minimum_source", "current_source"}:
            raise ValueError("independent OS role selection differs")
        if roles["minimum"] != MINIMUM_PATCHES[target]:
            raise ValueError("selected minimum is not the audited maintenance patch")
        floor = TARGETS[target][2]
        current = roles["current"]
        if (not isinstance(current, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,2}", current)
                or int(current.split(".")[0]) <= floor):
            raise ValueError("selected current runtime must be distinct from minimum release family")
        for key in ("minimum_source", "current_source"):
            source = roles[key]
            if not isinstance(source, str) or urlparse(source).scheme != "https" or urlparse(source).hostname not in ("support.apple.com", "developer.apple.com"):
                raise ValueError("OS role selection lacks an Apple release source")
    return selection


def expected_os(lane, version, selection):
    match = re.fullmatch(r"([0-9]+)(?:\.([0-9]+)(?:\.([0-9]+))?)?", version)
    if not match:
        raise ValueError("expected device OS must be a numeric version")
    if version != selection["roles"][lane["target"]][lane["version"]]:
        raise ValueError("device OS differs from independently selected minimum/current role")
    return version


def validate_device(record, lane, udid, model, os_version, selection):
    if not isinstance(record, dict):
        raise ValueError("physical device record is missing")
    runtime, family, _, abi = TARGETS[lane["target"]]
    if (record.get("udid") != udid or record.get("model") != model
            or record.get("os") != family or record.get("version") != os_version
            or record.get("abi") != abi or record.get("runtime") != runtime
            or record.get("kind") != "physical" or not record.get("available")
            or not isinstance(udid, str) or not udid
            or not isinstance(model, str) or not model):
        raise ValueError("selected physical device identity differs")
    expected_os(lane, os_version, selection)
    if lane["target"] == "watchosArm64" and "ILP32" not in runtime:
        raise ValueError("watchOS ILP32 lane differs")
    return record


def select_device(raw, lane, udid, model, os_version, selection):
    listing = json.loads(raw)
    devices = listing.get("result", {}).get("devices", [])
    if not isinstance(devices, list):
        raise ValueError("CoreDevice device list is invalid")
    matching = [item for item in devices if item.get("hardwareProperties", {}).get("udid") == udid]
    if len(matching) != 1:
        return None
    item = matching[0]
    properties = item.get("deviceProperties", {})
    hardware = item.get("hardwareProperties", {})
    runtime, family, _, abi = TARGETS[lane["target"]]
    cpu = hardware.get("cpuType", {}).get("name")
    expected_cpu = "arm64_32" if abi == "ILP32" else "arm64"
    if cpu not in (expected_cpu, "arm64e" if abi == "LP64" else expected_cpu):
        raise ValueError("physical device CPU ABI differs from lane")
    reality = hardware.get("reality")
    if reality != "physical" or item.get("simulator") is True:
        raise ValueError("simulator cannot satisfy a physical Apple lane")
    record = {"udid": udid, "model": hardware.get("productType"),
              "os": hardware.get("platform"),
              "version": properties.get("osVersionNumber"), "abi": abi,
              "runtime": runtime, "kind": "physical",
              "available": item.get("connectionProperties", {}).get("transportType")
              not in (None, "sameMachine"),
              "raw": item}
    if not record["available"]:
        return None
    return validate_device(record, lane, udid, model, os_version, selection)


def parse_gtest(raw, selected):
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("original device test event stream is not UTF-8") from error
    expected = {(item["classname"], item["method"]): item["id"] for item in selected}
    observed = []
    pending = None
    summaries = []
    image_proofs = 0
    for line in lines:
        if "[  FAILED  ]" in line or "[  SKIPPED ]" in line or "[  SKIPPED  ]" in line:
            raise ValueError("original device test event records failure or skip")
        start = START.fullmatch(line)
        passed = PASS.fullmatch(line)
        summary = SUMMARY.fullmatch(line)
        if start:
            if pending is not None:
                raise ValueError("device test start has no completion")
            pending = start[1]
        elif passed:
            if pending != passed[1]:
                raise ValueError("device test completion differs from start")
            if pending == IMAGE_PROOF:
                image_proofs += 1
                pending = None
                continue
            classname, separator, method = pending.rpartition(".")
            if not separator or (classname, method) not in expected:
                raise ValueError("device test event is not an original selected method")
            observed.append((expected[(classname, method)], classname, method,
                             int(passed[2]) / 1000))
            pending = None
        elif summary:
            summaries.append(int(summary[1]))
    if pending is not None or image_proofs != 1 or summaries != [len(observed) + 1]:
        raise ValueError("device test completion or summary differs")
    ids = [item[0] for item in observed]
    if len(ids) != len(expected) or len(set(ids)) != len(ids) or set(ids) != set(expected.values()):
        raise ValueError("device original method set is missing, foreign, or duplicate")
    suite = ET.Element("testsuite", {"name": "physical Apple Kotlin/Native", "tests": str(len(ids)),
                                     "failures": "0", "errors": "0", "skipped": "0",
                                     "time": str(sum(item[3] for item in observed))})
    for identity, classname, method, seconds in observed:
        ET.SubElement(suite, "testcase", {"id": identity, "classname": classname,
                                          "name": method, "time": str(seconds)})
    return ids, ET.tostring(suite, encoding="utf-8", xml_declaration=True)


def safe_file(root, relative):
    if (not isinstance(relative, str) or not relative or Path(relative).is_absolute()
            or any(part in ("", ".", "..") for part in relative.split("/"))):
        raise ValueError("unsafe archive file path")
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"archive file is missing or symbolic: {relative}")
    return path


def run_command(command, archive, name, *, timeout=600, cwd=None):
    start = time.time_ns()
    process = subprocess.run(command, cwd=cwd, capture_output=True, timeout=timeout)
    finish = time.time_ns()
    stdout = archive / f"process/{name}.stdout"
    stderr = archive / f"process/{name}.stderr"
    stdout.parent.mkdir(parents=True, exist_ok=True)
    stdout.write_bytes(process.stdout)
    stderr.write_bytes(process.stderr)
    record = {"command": [str(arg) for arg in command], "exit_code": process.returncode,
              "started_ns": start, "finished_ns": finish, "stdout": stdout.relative_to(archive).as_posix(),
              "stderr": stderr.relative_to(archive).as_posix()}
    return record


def installed_process(apps_raw, launch_raw, bundle_id):
    apps = json.loads(apps_raw)
    launch = json.loads(launch_raw)
    candidates = [item for item in apps.get("result", {}).get("apps", [])
                  if item.get("bundleIdentifier") == bundle_id]
    process = launch.get("result", {}).get("process", {})
    if (len(candidates) != 1 or launch.get("info", {}).get("outcome") != "success"
            or type(process.get("processIdentifier")) is not int
            or process["processIdentifier"] <= 0):
        raise ValueError("installed app or launched physical process identity differs")
    app_url = candidates[0].get("url")
    executable_url = process.get("executable")
    if (not isinstance(app_url, str) or not isinstance(executable_url, str)
            or urlparse(app_url).scheme != "file"
            or urlparse(executable_url).scheme != "file"):
        raise ValueError("installed or launched executable URL is invalid")
    app_path = "/" + urlparse(app_url).path.lstrip("/").rstrip("/")
    image_path = "/" + urlparse(executable_url).path.lstrip("/")
    if image_path != app_path + "/Dyn4kTests":
        raise ValueError("launched process image differs from installed test host")
    return {"pid": process["processIdentifier"], "installed_app_url": app_url,
            "process_executable_url": executable_url}


def output(archive, record):
    return safe_file(archive, record["stdout"]).read_bytes()


def require_success(record, step):
    if record["exit_code"]:
        raise ValueError(f"physical Apple {step} exited {record['exit_code']}")


def seal(archive, receipt):
    started, finished = receipt["process"]["started_ns"], receipt["process"]["finished_ns"]
    files = []
    for path in sorted(archive.rglob("*")):
        if path.is_symlink():
            raise ValueError("archive contains a symbolic path")
        if path.is_file():
            stamp = min(max(path.stat().st_mtime_ns, started), finished)
            os.utime(path, ns=(stamp, stamp))
            files.append({"path": path.relative_to(archive).as_posix(),
                          "sha256": sha(path.read_bytes()), "mtime_ns": stamp})
    receipt["files"] = files
    (archive / "receipt.json").write_bytes(encoded(receipt))
    return independent_gates.archive_digest(archive)


def unavailable(archive, candidate, lane_id, reason):
    if archive.exists() and any(archive.iterdir()):
        raise ValueError("physical Apple archive directory must be empty")
    archive.mkdir(parents=True, exist_ok=True)
    receipt = {"schema": 1, "status": "UNAVAILABLE", "candidate_sha": candidate,
               "lane": lane_id, "reason": reason, "observed_by": "full_apple_device_consumer.py",
               "observed_at_ns": time.time_ns()}
    (archive / "receipt.json").write_bytes(encoded(receipt))
    return {**receipt, "archive_sha256": independent_gates.archive_digest(archive),
            "execution": "NOT_RUN"}


def record_info_plist(bundle, bundle_id, family, os_version):
    minimum_key = {"iOS": "MinimumOSVersion", "tvOS": "MinimumOSVersion",
                   "watchOS": "MinimumOSVersion"}[family]
    info = {"CFBundleDevelopmentRegion": "en", "CFBundleExecutable": "Dyn4kTests",
            "CFBundleIdentifier": bundle_id, "CFBundleInfoDictionaryVersion": "6.0",
            "CFBundleName": "Dyn4kTests", "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": "0.1.0", "CFBundleVersion": "1",
            minimum_key: os_version}
    if family == "iOS":
        info["LSRequiresIPhoneOS"] = True
    if family == "watchOS":
        info["WKApplication"] = True
        info["WKWatchOnly"] = True
        info["WKRunsIndependentlyOfCompanionApp"] = True
    with (bundle / "Info.plist").open("wb") as stream:
        plistlib.dump(info, stream)


def require_pinned_xcode(result):
    lines = result.stdout.splitlines()
    if (result.returncode != 0 or len(lines) != 2 or lines[0] != "Xcode 26.5"
            or not lines[1].startswith("Build version ")
            or len(lines[1]) == len("Build version ")):
        raise ValueError("Xcode differs from pinned 26.5")
    return result.stdout.strip()


def run(args):
    repository = Path(args.repository).resolve()
    archive = Path(args.output).resolve()
    staging = Path(args.staging).resolve()
    lane, contract = lane_contract(repository, args.lane)
    if not SHA40.fullmatch(args.candidate):
        raise ValueError("candidate SHA is malformed")
    if (archive.is_relative_to(repository) or archive.is_relative_to(staging)
            or staging.is_relative_to(repository)
            or archive.exists() and any(archive.iterdir())):
        raise ValueError("external output/staging must be separate and empty")
    if git(repository, "rev-parse", "HEAD").decode().strip() != args.candidate:
        raise ValueError("producer checkout differs from candidate")
    if git(repository, "status", "--porcelain", "--untracked-files=all").strip():
        raise ValueError("producer requires a clean exact candidate checkout")
    selection = load_os_selection(args.os_roles_json, args.os_roles_sha256)
    expected_os(lane, args.expected_os, selection)
    if not args.udid or not args.model:
        return unavailable(archive, args.candidate, args.lane,
                           "no physical device UDID/model was supplied; test execution NOT_RUN")
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return unavailable(archive, args.candidate, args.lane,
                           "matching macOS ARM64 Xcode host is unavailable; test execution NOT_RUN")
    if not shutil.which("xcodebuild") or not shutil.which("xcrun"):
        return unavailable(archive, args.candidate, args.lane,
                           "Xcode device tools are unavailable; test execution NOT_RUN")
    xcode = subprocess.run(["xcodebuild", "-version"], capture_output=True, text=True)
    xcode_version = require_pinned_xcode(xcode)
    if not args.signing_identity or not args.provisioning_profile:
        return unavailable(archive, args.candidate, args.lane,
                           "device signing identity or provisioning profile is unavailable; test execution NOT_RUN")
    profile = Path(args.provisioning_profile).resolve()
    if not profile.is_file() or profile.is_symlink():
        raise ValueError("physical device provisioning profile is missing or symbolic")
    if not args.gradle or not args.java_home or not args.gradle_home:
        raise ValueError("pinned Gradle, JDK, and Gradle user home paths are required")
    gradle = Path(args.gradle).resolve()
    java_home = Path(args.java_home).resolve()
    gradle_home = Path(args.gradle_home).resolve()
    java_version = subprocess.run([str(java_home / "bin/java"), "-version"],
                                  capture_output=True, text=True)
    gradle_version = subprocess.run([str(gradle), "--version"], capture_output=True,
                                    text=True)
    if ('version "21' not in java_version.stderr + java_version.stdout
            or "Gradle 9.5.0" not in gradle_version.stdout):
        raise ValueError("pinned JDK 21 or Gradle 9.5.0 differs")
    hashes = {"dyn4k-core": args.core_sha256, "dyn4k": args.facade_sha256}
    if any(not SHA64.fullmatch(value or "") for value in hashes.values()):
        raise ValueError("independently audited target KLIB hashes are required")
    for module in MODULES:
        if sha(staged(staging, module, lane["target"]).read_bytes()) != hashes[module]:
            raise ValueError(f"audited staged {module} target KLIB differs")
    source_hashes = source_inventory(repository, args.candidate, contract["cases"])
    started = time.time_ns()
    steps = {}
    archive.parent.mkdir(parents=True, exist_ok=True)
    discovery = Path(tempfile.mkdtemp(prefix=f"{archive.name}-discovery-", dir=archive.parent))
    list_path = discovery / "device-list.json"
    list_record = run_command(["xcrun", "devicectl", "list", "devices", "--json-output",
                               str(list_path)], discovery, "device-list")
    steps["device-list"] = list_record
    require_success(list_record, "device discovery")
    if not list_path.is_file():
        raise ValueError("CoreDevice JSON device list is absent")
    device = select_device(list_path.read_bytes(), lane, args.udid, args.model,
                           args.expected_os, selection)
    if device is None:
        return unavailable(archive, args.candidate, args.lane,
                           "selected matching physical device is not attached; test execution NOT_RUN")
    device["raw_sha256"] = sha(list_path.read_bytes())
    archive.mkdir(parents=True)
    for path in discovery.iterdir():
        shutil.move(str(path), str(archive / path.name))
    discovery.rmdir()
    (archive / "inputs").mkdir()
    inventory = "".join(f"{path}\t{digest}\n" for path, digest in sorted(source_hashes.items()))
    (archive / "inputs/source-inventory.tsv").write_text(inventory)
    for module in MODULES:
        source = staged(staging, module, lane["target"])
        destination = archive / "resolved" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    work_root = archive.parent / f"{archive.name}-build"
    if work_root.exists():
        raise ValueError("external Apple build directory already exists")
    work_root.mkdir()
    mode = "Debug" if lane["configuration"] == "debug-g" else "Release"
    target = lane["target"]
    tasks = [":qualificationGraphs"] + [
        f":{name}:link{mode}Test{target[0].upper() + target[1:]}"
        for name in ("core", "facade")]
    command = [str(gradle), "-p", str(repository / CONSUMER),
               "--project-cache-dir", str(work_root / "gradle-project-cache"),
               "--offline", "--no-daemon", "--console=plain", "--rerun-tasks", "--info",
               f"-PqualificationCheckout={repository}",
               f"-PqualificationRepository={staging}",
               f"-PqualificationEvidence={archive}",
               f"-PqualificationWorkRoot={work_root}",
               f"-PqualificationSourceInventory={archive / 'inputs/source-inventory.tsv'}",
               f"-PqualificationCoreSha256={hashes['dyn4k-core']}",
               f"-PqualificationFacadeSha256={hashes['dyn4k']}",
               f"-PqualificationLaneId={args.lane}", f"-PqualificationTarget={target}",
               *tasks]
    environment = dict(os.environ, JAVA_HOME=str(java_home), GRADLE_USER_HOME=str(gradle_home))
    build_start = time.time_ns()
    process = subprocess.run(command, cwd=archive, capture_output=True, env=environment,
                             timeout=args.timeout)
    build_finish = time.time_ns()
    (archive / "stdout.txt").write_bytes(process.stdout)
    (archive / "stderr.txt").write_bytes(process.stderr)
    steps["gradle"] = {"command": command, "exit_code": process.returncode,
                       "started_ns": build_start, "finished_ns": build_finish,
                       "stdout": "stdout.txt", "stderr": "stderr.txt"}
    if process.returncode:
        raise ValueError(f"external Apple Gradle link exited {process.returncode}")
    for name in ("core", "facade"):
        binary = work_root / name / "bin" / target / f"{mode.lower()}Test" / "test.kexe"
        if not binary.is_file():
            raise ValueError(f"external {name} native test executable is absent")
        arch = run_command(["xcrun", "lipo", "-archs", str(binary)], archive,
                           f"{name}-architecture")
        steps[f"{name}-architecture"] = arch
        require_success(arch, "linked test architecture")
        expected_arch = "arm64_32" if target == "watchosArm64" else "arm64"
        if output(archive, arch).decode().strip() != expected_arch:
            raise ValueError("linked physical Apple test ABI differs")
        build_version = run_command(["xcrun", "vtool", "-show-build", str(binary)], archive,
                                    f"{name}-build-version")
        steps[f"{name}-build-version"] = build_version
        require_success(build_version, "linked test deployment target")
        if f"PLATFORM {TARGETS[target][1].upper()}" not in output(archive, build_version).decode().upper():
            raise ValueError("linked physical Apple test platform differs")
        bundle_id = f"io.github.rubixhacker.dyn4k.fullapple.{target.lower()}.{name}"
        bundle = archive / "hosts" / f"{name}.app"
        bundle.mkdir(parents=True)
        shutil.copyfile(binary, bundle / "Dyn4kTests")
        shutil.copyfile(profile, bundle / "embedded.mobileprovision")
        record_info_plist(bundle, bundle_id, TARGETS[target][1], args.expected_os)
        pre_sign = sha((bundle / "Dyn4kTests").read_bytes())
        sign = run_command(["codesign", "--force", "--sign", args.signing_identity,
                            "--timestamp=none", str(bundle)], archive, f"{name}-sign")
        steps[f"{name}-sign"] = sign
        require_success(sign, "code signing")
        verify_sign = run_command(["codesign", "--verify", "--strict", "--verbose=2",
                                   str(bundle)], archive, f"{name}-signature")
        steps[f"{name}-signature"] = verify_sign
        require_success(verify_sign, "signature verification")
        signed_hash = sha((bundle / "Dyn4kTests").read_bytes())
        install = run_command(["xcrun", "devicectl", "device", "install", "app", "--device",
                               args.udid, str(bundle)], archive, f"{name}-install",
                              timeout=args.timeout)
        steps[f"{name}-install"] = install
        require_success(install, "device installation")
        apps_path = archive / "process" / f"{name}-installed-apps.json"
        apps = run_command(["xcrun", "devicectl", "device", "info", "apps", "--device",
                            args.udid, "--json-output", str(apps_path)], archive,
                           f"{name}-installed-apps")
        steps[f"{name}-installed-apps"] = apps
        require_success(apps, "installed app query")
        if not apps_path.is_file() or bundle_id not in apps_path.read_text():
            raise ValueError("selected device installed app identity is absent")
        launch_path = archive / "process" / f"{name}-launch.json"
        launch = run_command(["xcrun", "devicectl", "device", "process", "launch",
                              "--console", "--terminate-existing", "--device", args.udid,
                              "--json-output", str(launch_path), bundle_id,
                              "--ktest_logger=GTEST"], archive, f"{name}-launch",
                             timeout=args.timeout)
        steps[f"{name}-launch"] = launch
        require_success(launch, "device test execution")
        if not launch_path.is_file():
            raise ValueError("physical device launch process JSON is absent")
        image = installed_process(apps_path.read_bytes(), launch_path.read_bytes(), bundle_id)
        installed = archive / "installed" / f"{name}.bin"
        installed.parent.mkdir(exist_ok=True)
        readback = run_command(["xcrun", "devicectl", "device", "copy", "from",
                                "--device", args.udid, "--domain-type", "appDataContainer",
                                "--domain-identifier", bundle_id, "--source",
                                "Documents/dyn4k-qualified-host.bin", "--destination",
                                str(installed)], archive, f"{name}-readback", timeout=args.timeout)
        steps[f"{name}-readback"] = readback
        require_success(readback, "installed executable readback")
        if not installed.is_file() or sha(installed.read_bytes()) != signed_hash:
            raise ValueError("device-retrieved installed executable differs from signed host")
        selected = [item for item in contract["cases"] if item["module"] ==
                    ("dyn4k-core" if name == "core" else "dyn4k")]
        raw = output(archive, launch)
        ids, xml = parse_gtest(raw, selected)
        report = archive / "reports" / f"{name}.xml"
        report.parent.mkdir(exist_ok=True)
        report.write_bytes(xml)
        steps[f"{name}-test"] = {"selected": len(ids), "linked_sha256": sha(binary.read_bytes()),
                                 "unsigned_host_sha256": pre_sign,
                                 "signed_host_sha256": signed_hash,
                                 "installed_binary_sha256": signed_hash,
                                 "installed_binary": f"installed/{name}.bin",
                                 "installed_bundle_id": bundle_id,
                                 "process_image": image,
                                 "host": f"hosts/{name}.app/Dyn4kTests",
                                 "report": f"reports/{name}.xml"}
    finished = time.time_ns()
    receipt = {"schema": 1, "status": "PASSED", "candidate_sha": args.candidate,
               "source_tree": git(repository, "rev-parse", f"{args.candidate}^{{tree}}").decode().strip(),
               "lane": args.lane, **{key: lane[key] for key in
                                     ("target", "runtime", "version", "configuration")},
               "runtime_identity": f"{device['model']} | {device['os']} {device['version']} | {device['udid']}",
               "device": device, "artifact_hashes": hashes,
               "os_roles_sha256": args.os_roles_sha256,
               "consumer_group": "full-suite",
               "consumer_contract_sha256": independent_gates.digest(contract),
               "source_inventory_sha256": sha(inventory.encode()),
               "consumer_build_sha256": {path: sha(git(repository, "show", f"{args.candidate}:{path}"))
                                          for path in BUILD_FILES},
               "producer_sha256": sha(git(repository, "show", f"{args.candidate}:{PRODUCER}")),
               "toolchain": {"xcode": xcode_version, "jdk": java_version.stderr.strip(),
                             "gradle": "9.5.0", "kgp": "2.4.20",
                             "java_sha256": sha((java_home / "bin/java").read_bytes()),
                             "gradle_sha256": sha(gradle.read_bytes())},
               "mode": {"native_binary": mode.lower() + "Test",
                        "compiler_flag": "-g" if mode == "Debug" else "-opt",
                        "link_tasks": tasks[1:]},
               "process": {"command": command, "cwd": str(archive), "exit_code": 0,
                           "started_ns": started, "finished_ns": finished,
                           "stdout": "stdout.txt", "stderr": "stderr.txt"},
               "steps": steps, "provider_graph": "provider-graph.json",
               "resolved_artifacts": {module: f"resolved/{staged(staging, module, target).name}"
                                      for module in MODULES},
               "consumer_xml": ["reports/core.xml", "reports/facade.xml"]}
    digest = seal(archive, receipt)
    return {"status": "PASSED", "lane": args.lane, "archive_sha256": digest,
            "selected_cases": 2523}


def verify(repository, candidate, lane_id, archive, archive_sha256, hashes,
           expected_runtime_identity, expected_toolchain, os_roles_json=None,
           os_roles_sha256=None):
    repository = Path(repository).resolve()
    archive = Path(archive).absolute()
    lane, contract = lane_contract(repository, lane_id)
    if not SHA40.fullmatch(candidate) or not SHA64.fullmatch(archive_sha256 or ""):
        raise ValueError("independent candidate/archive identity is missing")
    if any(path.is_symlink() for path in (archive, *archive.parents)) or not archive.is_dir():
        raise ValueError("physical Apple archive is absent or symbolic")
    for path in archive.rglob("*"):
        if path.is_symlink():
            raise ValueError("symbolic archive path")
        if path.is_file() and path.stat().st_nlink != 1:
            raise ValueError("hardlink in physical Apple archive")
    if independent_gates.archive_digest(archive) != archive_sha256:
        raise ValueError("physical Apple archive differs from independent digest")
    receipt = json.loads(safe_file(archive, "receipt.json").read_bytes(),
                         object_pairs_hook=independent_gates._strict_object)
    if receipt.get("status") == "UNAVAILABLE":
        if {path.name for path in archive.iterdir()} != {"receipt.json"}:
            raise ValueError("unavailability has unexpected raw files")
        if (receipt.get("schema") != 1 or receipt.get("candidate_sha") != candidate
                or receipt.get("lane") != lane_id or not receipt.get("reason")
                or receipt.get("observed_by") != "full_apple_device_consumer.py"
                or type(receipt.get("observed_at_ns")) is not int):
            raise ValueError("unavailability receipt differs from selected lane")
        return {"status": "UNAUTHENTICATED", "claimed_status": "UNAVAILABLE",
                "observed": False, "lane": lane_id, "selected_cases": 0,
                "archive_sha256": archive_sha256, "execution": "NOT_RUN"}
    if receipt.get("status") != "PASSED" or receipt.get("schema") != 1:
        raise ValueError("physical Apple run is not passed")
    selection = load_os_selection(os_roles_json, os_roles_sha256)
    if receipt.get("os_roles_sha256") != os_roles_sha256:
        raise ValueError("physical Apple OS role selection differs")
    independent_gates._inventory(archive, receipt)
    if (receipt.get("candidate_sha") != candidate
            or receipt.get("source_tree") != git(repository, "rev-parse",
                                                  f"{candidate}^{{tree}}").decode().strip()
            or receipt.get("lane") != lane_id
            or any(receipt.get(key) != lane[key] for key in
                   ("target", "runtime", "version", "configuration"))
            or receipt.get("consumer_group") != "full-suite"
            or receipt.get("consumer_contract_sha256") != independent_gates.digest(contract)
            or receipt.get("runtime_identity") != expected_runtime_identity
            or receipt.get("toolchain") != expected_toolchain
            or receipt.get("artifact_hashes") != hashes
            or set(hashes) != set(MODULES)
            or any(not SHA64.fullmatch(value) for value in hashes.values())):
        raise ValueError("physical Apple receipt differs from independent selection")
    if receipt.get("consumer_build_sha256") != {
            path: sha(git(repository, "show", f"{candidate}:{path}"))
            for path in BUILD_FILES} or receipt.get("producer_sha256") != sha(
                git(repository, "show", f"{candidate}:{PRODUCER}")):
        raise ValueError("device producer or external project differs from exact candidate")
    source_hashes = source_inventory(repository, candidate, contract["cases"])
    inventory = "".join(f"{path}\t{digest}\n" for path, digest in sorted(source_hashes.items()))
    if (safe_file(archive, "inputs/source-inventory.tsv").read_text() != inventory
            or receipt.get("source_inventory_sha256") != sha(inventory.encode())):
        raise ValueError("original portable test source differs")
    device = receipt.get("device")
    if not isinstance(device, dict):
        raise ValueError("physical device identity is absent")
    selected = select_device(safe_file(archive, "device-list.json").read_bytes(), lane,
                             device.get("udid"), device.get("model"), device.get("version"),
                             selection)
    if selected is None or selected != {key: value for key, value in device.items()
                                         if key != "raw_sha256"}:
        raise ValueError("device record differs from original CoreDevice listing")
    if device.get("raw_sha256") != sha(safe_file(archive, "device-list.json").read_bytes()):
        raise ValueError("device listing hash differs")
    identity = f"{device['model']} | {device['os']} {device['version']} | {device['udid']}"
    if identity != expected_runtime_identity:
        raise ValueError("runtime identity does not bind physical device")
    steps, process = receipt.get("steps"), receipt.get("process")
    if not isinstance(steps, dict) or not isinstance(process, dict):
        raise ValueError("physical device process timeline is absent")
    expected_steps = {"device-list", "gradle"} | {
        f"{name}-{phase}" for name in ("core", "facade") for phase in
        ("architecture", "build-version", "sign", "signature", "install",
         "installed-apps", "launch", "readback", "test")}
    if set(steps) != expected_steps:
        raise ValueError("physical device build/install/launch timeline differs")
    if (process.get("exit_code") != 0 or process.get("command") != steps["gradle"].get("command")
            or process.get("stdout") != "stdout.txt" or process.get("stderr") != "stderr.txt"
            or process.get("cwd") != str(archive)):
        raise ValueError("external Gradle process identity differs")
    start, finish = process.get("started_ns"), process.get("finished_ns")
    if type(start) is not int or type(finish) is not int or start <= 0 or finish < start:
        raise ValueError("external execution window is invalid")
    for key in expected_steps - {"core-test", "facade-test"}:
        step = steps[key]
        if (not isinstance(step, dict) or step.get("exit_code") != 0
                or type(step.get("started_ns")) is not int
                or type(step.get("finished_ns")) is not int
                or not start <= step["started_ns"] <= step["finished_ns"] <= finish
                or not isinstance(step.get("command"), list)):
            raise ValueError(f"physical device process step differs: {key}")
        safe_file(archive, step["stdout"])
        safe_file(archive, step["stderr"])
    if not (steps["device-list"]["finished_ns"] <= steps["gradle"]["started_ns"]
            and steps["gradle"]["finished_ns"] <= steps["core-sign"]["started_ns"]):
        raise ValueError("device discovery/build/sign timeline differs")
    build_stdout = safe_file(archive, "stdout.txt").read_text()
    if f"QUALIFICATION_LANE={lane_id}" not in build_stdout.splitlines():
        raise ValueError("external Gradle output lacks exact lane marker")
    mode = "Debug" if lane["configuration"] == "debug-g" else "Release"
    tasks = [f":{name}:link{mode}Test{lane['target'][0].upper() + lane['target'][1:]}"
             for name in ("core", "facade")]
    if (receipt.get("mode") != {"native_binary": mode.lower() + "Test",
                                "compiler_flag": "-g" if mode == "Debug" else "-opt",
                                "link_tasks": tasks}
            or any(f"> Task {task}" not in build_stdout for task in tasks)
            or "BUILD SUCCESSFUL" not in build_stdout):
        raise ValueError("external native test build mode differs")
    command = process["command"]
    if (Path(command[0]).name not in ("gradle", "gradlew")
            or command[-3:] != [":qualificationGraphs", *tasks]
            or ["-p", str(repository / CONSUMER)] != command[1:3]
            or not {"--offline", "--no-daemon", "--rerun-tasks", "--info",
                    f"-PqualificationLaneId={lane_id}",
                    f"-PqualificationTarget={lane['target']}",
                    f"-PqualificationCoreSha256={hashes['dyn4k-core']}",
                    f"-PqualificationFacadeSha256={hashes['dyn4k']}"} <= set(command)):
        raise ValueError("external staged native build command differs")
    graph = json.loads(safe_file(archive, "provider-graph.json").read_bytes(),
                       object_pairs_hook=independent_gates._strict_object)
    if set(graph) != {"compile", "gradle_user_home"} or len(graph["compile"]) != 2:
        raise ValueError("external Apple provider graph differs")
    for name, item in zip(("core", "facade"), graph["compile"]):
        if (item.get("project") != name
                or item.get("configuration") != f"{lane['target']}TestCompileKlibraries"
                or not isinstance(item.get("artifacts"), list)
                or not isinstance(item.get("components"), list)):
            raise ValueError("external Apple target compile graph differs")
        for module in MODULES:
            gav = f"io.github.rubixhacker:{module}-{lane['target'].lower()}:{VERSION}"
            matches = [artifact for artifact in item["artifacts"]
                       if artifact.get("component") == gav]
            if len(matches) != 1 or matches[0].get("sha256") != hashes[module]:
                raise ValueError(f"resolved {module} target KLIB differs")
        if "org.dyn4j:dyn4j" in encoded(item).decode():
            raise ValueError("baseline provider leaked into external Apple graph")
    if receipt.get("resolved_artifacts") != {
            module: f"resolved/{module}-{lane['target'].lower()}-{VERSION}.klib"
            for module in MODULES}:
        raise ValueError("resolved target KLIB paths differ")
    for module, relative in receipt["resolved_artifacts"].items():
        if sha(safe_file(archive, relative).read_bytes()) != hashes[module]:
            raise ValueError(f"archived resolved {module} KLIB differs")
    observed = []
    for name in ("core", "facade"):
        proof = steps[f"{name}-test"]
        expected_count = 2465 if name == "core" else 58
        if proof.get("selected") != expected_count:
            raise ValueError("selected original method count differs")
        host = f"hosts/{name}.app/Dyn4kTests"
        if proof.get("host") != host or proof.get("report") != f"reports/{name}.xml":
            raise ValueError("signed device host identity differs")
        signed = sha(safe_file(archive, host).read_bytes())
        installed = f"installed/{name}.bin"
        if (proof.get("signed_host_sha256") != signed
                or proof.get("installed_binary") != installed
                or sha(safe_file(archive, installed).read_bytes()) != signed
                or proof.get("installed_binary_sha256") != signed):
            raise ValueError("signed installed binary hash differs")
        bundle = archive / "hosts" / f"{name}.app"
        info = plistlib.loads(safe_file(archive, f"hosts/{name}.app/Info.plist").read_bytes())
        bundle_id = f"io.github.rubixhacker.dyn4k.fullapple.{lane['target'].lower()}.{name}"
        if (info.get("CFBundleIdentifier") != bundle_id
                or info.get("CFBundleExecutable") != "Dyn4kTests"
                or info.get("MinimumOSVersion") != device["version"]
                or proof.get("installed_bundle_id") != bundle_id):
            raise ValueError("installed test host bundle identity differs")
        if device["os"] == "watchOS" and (info.get("WKApplication") is not True
                                           or info.get("WKWatchOnly") is not True
                                           or "WKWatchKitApp" in info):
            raise ValueError("watchOS single-target app form differs")
        sign = steps[f"{name}-sign"]
        signature = steps[f"{name}-signature"]
        install = steps[f"{name}-install"]
        apps = steps[f"{name}-installed-apps"]
        launch = steps[f"{name}-launch"]
        readback = steps[f"{name}-readback"]
        signing = sign["command"]
        if (signing[:3] != ["codesign", "--force", "--sign"]
                or len(signing) != 6 or signing[3] in ("", "-")
                or signing[4:] != ["--timestamp=none", str(bundle)]
                or signature["command"] != ["codesign", "--verify", "--strict",
                                             "--verbose=2", str(bundle)]
                or install["command"] != ["xcrun", "devicectl", "device", "install",
                                          "app", "--device", device["udid"], str(bundle)]
                or apps["command"] != ["xcrun", "devicectl", "device", "info", "apps",
                                       "--device", device["udid"], "--json-output",
                                       str(archive / "process" / f"{name}-installed-apps.json")]
                or launch["command"] != ["xcrun", "devicectl", "device", "process",
                                         "launch", "--console", "--terminate-existing",
                                         "--device", device["udid"], "--json-output",
                                         str(archive / "process" / f"{name}-launch.json"),
                                         bundle_id, "--ktest_logger=GTEST"]
                or readback["command"] != ["xcrun", "devicectl", "device", "copy",
                                           "from", "--device", device["udid"],
                                           "--domain-type", "appDataContainer",
                                           "--domain-identifier", bundle_id, "--source",
                                           "Documents/dyn4k-qualified-host.bin", "--destination",
                                           str(archive / "installed" / f"{name}.bin")]):
            raise ValueError("device sign/install/launch command differs")
        expected_arch = "arm64_32" if lane["target"] == "watchosArm64" else "arm64"
        if (output(archive, steps[f"{name}-architecture"]).decode().strip() != expected_arch
                or f"PLATFORM {device['os'].upper()}" not in
                output(archive, steps[f"{name}-build-version"]).decode().upper()):
            raise ValueError("linked test ABI or platform differs")
        if (not steps[f"{name}-sign"]["finished_ns"] <= signature["started_ns"]
                <= install["started_ns"] <= apps["started_ns"] <= launch["started_ns"]
                <= launch["finished_ns"] <= readback["started_ns"]):
            raise ValueError("device sign/install/launch order differs")
        if proof.get("process_image") != installed_process(
                safe_file(archive, f"process/{name}-installed-apps.json").read_bytes(),
                safe_file(archive, f"process/{name}-launch.json").read_bytes(), bundle_id):
            raise ValueError("launched physical process differs from installed host")
        selected_cases = [item for item in contract["cases"] if item["module"] ==
                          ("dyn4k-core" if name == "core" else "dyn4k")]
        ids, normalized = parse_gtest(output(archive, launch), selected_cases)
        if safe_file(archive, f"reports/{name}.xml").read_bytes() != normalized:
            raise ValueError("normalized report differs from original device events")
        observed.extend(ids)
    if (len(observed) != 2523 or len(set(observed)) != 2523
            or set(observed) != {item["id"] for item in contract["cases"]}
            or receipt.get("consumer_xml") != ["reports/core.xml", "reports/facade.xml"]):
        raise ValueError("physical device original selected method set differs")
    return {"status": "PASSED", "lane": lane_id, "selected_cases": 2523,
            "archive_sha256": archive_sha256, "candidate_sha": candidate}


def main():
    parser = argparse.ArgumentParser(description="Full external physical Apple staged consumer")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("matrix")
    listing.add_argument("--repository", required=True)
    producer = commands.add_parser("run")
    producer.add_argument("--repository", required=True)
    producer.add_argument("--candidate", required=True)
    producer.add_argument("--lane", required=True)
    producer.add_argument("--staging", required=True)
    producer.add_argument("--output", required=True)
    producer.add_argument("--gradle")
    producer.add_argument("--java-home")
    producer.add_argument("--gradle-home")
    producer.add_argument("--udid")
    producer.add_argument("--model")
    producer.add_argument("--expected-os", required=True)
    producer.add_argument("--os-roles-json", required=True)
    producer.add_argument("--os-roles-sha256", required=True)
    producer.add_argument("--signing-identity")
    producer.add_argument("--provisioning-profile")
    producer.add_argument("--core-sha256")
    producer.add_argument("--facade-sha256")
    producer.add_argument("--timeout", type=int, default=3600)
    replay = commands.add_parser("verify")
    replay.add_argument("--repository", required=True)
    replay.add_argument("--candidate", required=True)
    replay.add_argument("--lane", required=True)
    replay.add_argument("--archive", required=True)
    replay.add_argument("--archive-sha256", required=True)
    replay.add_argument("--core-sha256", required=True)
    replay.add_argument("--facade-sha256", required=True)
    replay.add_argument("--runtime-identity", required=True)
    replay.add_argument("--toolchain-json", required=True)
    replay.add_argument("--os-roles-json", required=True)
    replay.add_argument("--os-roles-sha256", required=True)
    args = parser.parse_args()
    if args.command == "matrix":
        print("\n".join(matrix(Path(args.repository).resolve())))
    elif args.command == "run":
        print(json.dumps(run(args), sort_keys=True))
    else:
        print(json.dumps(verify(args.repository, args.candidate, args.lane,
                                args.archive, args.archive_sha256,
                                {"dyn4k-core": args.core_sha256, "dyn4k": args.facade_sha256},
                                args.runtime_identity,
                                json.loads(Path(args.toolchain_json).read_bytes()),
                                args.os_roles_json, args.os_roles_sha256), sort_keys=True))


if __name__ == "__main__":
    main()
