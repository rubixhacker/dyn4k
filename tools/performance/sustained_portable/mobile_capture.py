#!/usr/bin/env python3
import argparse
import ctypes
import json
import os
from pathlib import Path
import platform
import re
import secrets
import select
import shlex
import subprocess
import time

import capture


APPLE_SIMULATORS = {
    "iosSimulatorArm64": ("iOS", "arm64"),
    "iosX64": ("iOS", "x86_64"),
    "tvosSimulatorArm64": ("tvOS", "arm64"),
    "watchosSimulatorArm64": ("watchOS", "arm64"),
}
APPLE_DEVICES = {"iosArm64", "tvosArm64", "watchosArm64", "watchosDeviceArm64"}
ANDROID_ABIS = {
    "androidNativeArm32": ("armeabi-v7a", 1, 40),
    "androidNativeArm64": ("arm64-v8a", 2, 183),
    "androidNativeX86": ("x86", 1, 3),
    "androidNativeX64": ("x86_64", 2, 62),
}
TARGETS = set(APPLE_SIMULATORS) | APPLE_DEVICES | set(ANDROID_ABIS)


def command(argv, *, check=True, timeout=30):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise ValueError(f"command failed ({result.returncode}): {argv}: {result.stderr.strip()}")
    return result


def setup_command(archive, label, argv, *, check=True, timeout=30):
    setup = archive / "setup"
    setup.mkdir(exist_ok=True)
    started = time.monotonic_ns()
    try:
        result = subprocess.run(argv, capture_output=True, timeout=timeout)
        stdout, stderr = result.stdout, result.stderr
        exit_code, timed_out, launch_error = result.returncode, False, None
    except subprocess.TimeoutExpired as error:
        stdout, stderr = error.output or b"", error.stderr or b""
        exit_code, timed_out, launch_error = None, True, None
    except OSError as error:
        stdout, stderr = b"", b""
        exit_code, timed_out, launch_error = None, False, str(error)
    ended = time.monotonic_ns()
    (setup / f"{label}.stdout.bin").write_bytes(stdout)
    (setup / f"{label}.stderr.bin").write_bytes(stderr)
    (setup / f"{label}.json").write_text(json.dumps({
        "argv": argv, "exit_code": exit_code, "timed_out": timed_out,
        "launch_error": launch_error, "started_ns": started, "ended_ns": ended,
    }, indent=2) + "\n")
    if timed_out:
        raise ValueError(f"setup command timed out: {argv}")
    if launch_error is not None:
        raise ValueError(f"setup command could not launch: {argv}: {launch_error}")
    decoded = subprocess.CompletedProcess(argv, exit_code, stdout.decode("utf-8", errors="replace"),
                                          stderr.decode("utf-8", errors="replace"))
    if check and exit_code:
        raise ValueError(f"command failed ({exit_code}): {argv}: {decoded.stderr.strip()}")
    return decoded


def validate_adb_route(port, serial):
    if not isinstance(port, int) or not 5040 <= port <= 65535:
        raise ValueError("ADB port must be an explicit task-isolated port at least 5040")
    if not isinstance(serial, str) or not re.fullmatch(r"[A-Za-z0-9._:-]+", serial):
        raise ValueError("ADB serial must be explicit and valid")
    if serial == "emulator-5558":
        raise ValueError("ADB emulator-5558 is leased to the ART owner")
    return port, serial


def validate_android_identity(target, properties):
    abi = ANDROID_ABIS[target][0]
    if properties.get("ro.product.cpu.abi") != abi:
        raise ValueError("Android primary ABI differs from selected Native target")
    try:
        api = int(properties["ro.build.version.sdk"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Android API identity is missing") from error
    if api < 21 or properties.get("sys.boot_completed") != "1":
        raise ValueError("Android runtime is below API 21 or not boot complete")
    if not properties.get("ro.build.fingerprint"):
        raise ValueError("Android OS fingerprint is missing")
    return {"abi": abi, "api": api, "fingerprint": properties["ro.build.fingerprint"]}


def validate_simulator(target, udid, listing):
    family, machine = APPLE_SIMULATORS[target]
    if platform.system() != "Darwin" or platform.machine().lower() != machine:
        raise ValueError("simulator host OS or architecture differs from selected target")
    matches = []
    for runtime, devices in listing.get("devices", {}).items():
        version = re.search(r"\." + re.escape(family) + r"-([0-9]+)-([0-9]+)$", runtime)
        if not version:
            continue
        minimum = 8 if family == "watchOS" else 15
        if int(version.group(1)) < minimum:
            if any(device.get("udid") == udid for device in devices):
                raise ValueError("selected simulator OS is below the minimum policy")
            continue
        for device in devices:
            if device.get("udid") == udid and device.get("isAvailable") is True:
                if device.get("state") != "Booted":
                    raise ValueError("selected simulator is not booted")
                matches.append({"udid": udid, "runtime": runtime,
                                "os_version": f"{version.group(1)}.{version.group(2)}",
                                "name": device.get("name"),
                                "device_type": device.get("deviceTypeIdentifier")})
    if len(matches) != 1:
        raise ValueError("selected simulator does not match target family or UDID")
    return matches[0]


def validate_process_image(observed_sha, expected_sha):
    if not observed_sha or observed_sha != expected_sha:
        raise ValueError("observed process image is missing or differs from selected executable")


def validate_completion(raw, nonce):
    if raw.decode("utf-8", errors="replace").splitlines()[-1:] != [f"DYN4K\tCOMPLETE\t{nonce}"]:
        raise ValueError("producer completion marker is missing")


def simulator_protocol_bytes(raw, bundle_id, observed_pid):
    first = raw.partition(b"\n")[0]
    match = re.fullmatch(re.escape(bundle_id).encode() + rb": ([1-9][0-9]*)", first)
    if not match:
        raise ValueError("simulator console PID header is missing or malformed")
    if int(match.group(1)) != observed_pid:
        raise ValueError("simulator launch PID differs from observed process image")
    raise ValueError("simctl --console stdout-to-PID origin is unverified; Mac control required")


def validate_elf_abi(path, target):
    data = path.read_bytes()[:20]
    expected = ANDROID_ABIS[target]
    if len(data) != 20 or data[:4] != b"\x7fELF" or data[4] != expected[1] or data[5] != 1:
        raise ValueError("selected Android executable has wrong ELF class or endianness")
    if int.from_bytes(data[18:20], "little") != expected[2]:
        raise ValueError("selected Android executable has wrong ELF ABI")


def selected_artifact(inventory, module, target):
    suffix = f":{module}-{target.lower()}:"
    matches = [item for item in inventory["resolved_artifacts"] if suffix in item["module"]]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one staged {module} {target} artifact")
    return matches[0]


def validate_inventory(path, target, build):
    inventory = json.loads(path.read_text())
    sha = command(["git", "-C", str(capture.ROOT), "rev-parse", "HEAD"]).stdout.strip()
    tree = capture.source_tree()
    if command(["git", "-C", str(capture.ROOT), "status", "--porcelain",
                "--untracked-files=all"]).stdout.strip():
        raise ValueError("source checkout is dirty; commit the producer before capture")
    mode = "debug" if build == "development" else "release"
    expected = {
        "format": "portable-mobile-build-inventory-v1", "source_sha": sha,
        "producer_tree": tree, "manifest_sha256": capture.digest(capture.MANIFEST),
        "target": target, "build": build, "gradle": "9.5.0", "kgp": "2.4.20",
        "compiler_mode": mode, "compile_configuration": f"{target}CompileKlibraries",
        "link_task": f"link{mode.title()}Executable{target[0].upper()}{target[1:]}",
    }
    if any(inventory.get(key) != value for key, value in expected.items()):
        raise ValueError("mobile build inventory differs from selected source, target, or compiler")
    tracked = command(["git", "-C", str(capture.ROOT), "ls-tree", "-r", "--name-only",
                       "HEAD", "consumers/performance/portable",
                       "tools/performance/sustained_portable"]).stdout.splitlines()
    source_files = {name: capture.digest(capture.ROOT / name) for name in tracked}
    if inventory.get("source_files") != source_files:
        raise ValueError("mobile producer source bytes differ from build inventory")
    harness = capture.required_file(inventory["harness"], "mobile process image")
    linked = capture.required_file(inventory["linked_executable"], "linked executable")
    if capture.digest(linked) != inventory.get("linked_sha256"):
        raise ValueError("linked executable differs from build inventory")
    apple = target in APPLE_SIMULATORS or target in APPLE_DEVICES
    if apple:
        app = Path(inventory["app_bundle"])
        if not app.is_absolute() or app.suffix != ".app" or harness != app / "Dyn4kPerformance":
            raise ValueError("Apple app bundle or process image path is invalid")
        if inventory.get("bundle_id") != f"io.github.rubixhacker.dyn4k.performance.{target.lower()}":
            raise ValueError("Apple app bundle ID differs from target")
        if inventory.get("abi") is not None:
            raise ValueError("Apple inventory has Android ABI")
        bundle_root = app
    else:
        if harness != linked or inventory.get("app_bundle") is not None:
            raise ValueError("Android Native process image differs from linked executable")
        if inventory.get("abi") != ANDROID_ABIS[target][0]:
            raise ValueError("Android inventory ABI differs from selected target")
        validate_elf_abi(harness, target)
        bundle_root = harness.parent
    actual_bundle = {str(item.relative_to(bundle_root)): capture.digest(item)
                     for item in sorted(bundle_root.rglob("*")) if item.is_file()}
    if not actual_bundle or inventory.get("bundle_sha256") != actual_bundle:
        raise ValueError("mobile package bytes differ from build inventory")
    artifacts = inventory.get("resolved_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("mobile compilation has no resolved artifacts")
    for item in artifacts:
        artifact = capture.required_file(item["path"], "staged compilation artifact")
        if capture.digest(artifact) != item["sha256"]:
            raise ValueError("staged compilation artifact changed after build")
    selected = {module: selected_artifact(inventory, module, target) for module in
                ("dyn4k-core", "dyn4k")}
    return inventory, harness, selected


def producer_arguments(scenario, inventory, artifacts, steps, warmup, nonce):
    return [scenario["id"], scenario["family"], scenario["variant"], scenario["size"],
            str(scenario["rate_hz"]), str(steps), str(warmup), "timing", scenario["api"],
            inventory["source_sha"], artifacts["dyn4k-core"]["sha256"],
            artifacts["dyn4k"]["sha256"], inventory["build"], nonce]


def apple_process_image(executable):
    library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    library.proc_listpids.argtypes = [ctypes.c_uint32, ctypes.c_uint32,
                                     ctypes.c_void_p, ctypes.c_int]
    library.proc_listpids.restype = ctypes.c_int
    library.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    library.proc_pidpath.restype = ctypes.c_int
    pids = (ctypes.c_int * 65536)()
    count = library.proc_listpids(1, 0, pids, ctypes.sizeof(pids)) // ctypes.sizeof(ctypes.c_int)
    matches = []
    for pid in pids[:count]:
        if pid <= 0:
            continue
        buffer = ctypes.create_string_buffer(4096)
        if library.proc_pidpath(pid, buffer, len(buffer)) > 0:
            path = Path(os.fsdecode(buffer.value))
            if path == executable and path.is_file() and capture.digest(path) == capture.digest(executable):
                matches.append((pid, path))
    if len(matches) != 1:
        raise ValueError("installed simulator process image was not uniquely observable")
    return {"pid": matches[0][0], "path": str(matches[0][1]),
            "sha256": capture.digest(matches[0][1]), "method": "proc_listpids/proc_pidpath"}


def run_simulator(args, inventory, harness, producer):
    if not args.udid:
        raise ValueError("set --udid for the selected Apple simulator")
    xcode = setup_command(args.archive, "apple-xcode", ["xcodebuild", "-version"]).stdout
    if not xcode.startswith("Xcode 26.4.1\n"):
        raise ValueError("selected Xcode differs from pinned 26.4.1")
    listing = json.loads(setup_command(args.archive, "apple-device-list",
                                       ["xcrun", "simctl", "list", "-j", "devices", "available"]).stdout)
    device = validate_simulator(args.target, args.udid, listing)
    architecture = setup_command(args.archive, "apple-architecture",
                                 ["xcrun", "lipo", "-archs", str(harness)]).stdout.split()
    expected_arch = "x86_64" if args.target == "iosX64" else "arm64"
    if architecture != [expected_arch]:
        raise ValueError("Apple executable architecture differs from selected simulator")
    app = inventory["app_bundle"]
    bundle = inventory["bundle_id"]
    setup_command(args.archive, "apple-install", ["xcrun", "simctl", "install", args.udid, app], timeout=120)
    container = setup_command(args.archive, "apple-container",
                              ["xcrun", "simctl", "get_app_container", args.udid, bundle, "app"]).stdout.strip()
    installed = Path(container) / harness.name
    if not installed.is_file() or capture.digest(installed) != capture.digest(harness):
        raise ValueError("installed simulator package bytes differ from selected app")
    launch = ["xcrun", "simctl", "launch", "--console", "--terminate-running-process",
              args.udid, bundle, *producer]
    started = time.monotonic_ns()
    process = subprocess.Popen(launch, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    image = None
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and process.poll() is None:
        try:
            image = apple_process_image(installed)
            break
        except ValueError:
            time.sleep(0.02)
    try:
        stdout, stderr = process.communicate(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        (args.archive / "stdout.bin").write_bytes(stdout)
        (args.archive / "stderr.bin").write_bytes(stderr)
        raise ValueError("simulator producer exceeded capture timeout")
    (args.archive / "stdout.bin").write_bytes(stdout)
    (args.archive / "stderr.bin").write_bytes(stderr)
    ended = time.monotonic_ns()
    validate_process_image(image["sha256"] if image else None, capture.digest(harness))
    if process.returncode:
        raise ValueError(f"simulator producer exited {process.returncode}: {stderr.decode(errors='replace')[:300]}")
    return stdout, stderr, {"command": launch, "exit_code": process.returncode,
                            "image": image, "runtime": device, "xcode": xcode.strip(),
                            "bundle_id": bundle,
                            "installed_image_sha256": capture.digest(installed),
                            "started_ns": started, "ended_ns": ended}


def run_android(args, inventory, harness, producer, nonce):
    port, serial = validate_adb_route(args.adb_port, args.serial)
    adb = capture.required_file(args.adb, "ADB executable")
    prefix = [str(adb), "-P", str(port), "-s", serial]
    devices = setup_command(args.archive, "android-devices",
                            [str(adb), "-P", str(port), "devices", "-l"]).stdout.splitlines()
    listed = [row.split() for row in devices[1:] if row.strip()]
    if listed != [[serial, "device"]] and not (len(listed) == 1 and listed[0][:2] == [serial, "device"]):
        raise ValueError("task-isolated ADB server must expose only the selected ready device")
    properties = {name: setup_command(args.archive, f"android-prop-{name}",
                                      prefix + ["shell", "getprop", name]).stdout.strip() for name in
                  ("ro.product.cpu.abi", "ro.build.version.sdk", "ro.build.fingerprint", "sys.boot_completed")}
    runtime = validate_android_identity(args.target, properties)
    remote = f"/data/local/tmp/dyn4k-performance-{nonce}"
    setup_command(args.archive, "android-push", prefix + ["push", str(harness), remote], timeout=120)
    setup_command(args.archive, "android-chmod", prefix + ["shell", "chmod", "700", remote])
    deployed = setup_command(args.archive, "android-deployed-sha",
                             prefix + ["shell", "sha256sum", remote]).stdout.split()[0]
    validate_process_image(deployed, capture.digest(harness))
    guest = "echo DYN4K_PID:$$; exec " + " ".join(shlex.quote(value) for value in [remote, *producer])
    launch = prefix + ["shell", "sh -c " + shlex.quote(guest)]
    started = time.monotonic_ns()
    process = subprocess.Popen(launch, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    try:
        ready, _, _ = select.select([process.stdout], [], [], min(args.timeout, 15))
        if not ready:
            raise ValueError("Android launched PID receipt timed out")
        first = process.stdout.readline().decode("utf-8", errors="replace").strip()
        (args.archive / "pid.txt").write_text(first + "\n")
        if not re.fullmatch(r"DYN4K_PID:[1-9][0-9]*", first):
            raise ValueError("Android launched PID receipt is missing")
        pid = int(first.split(":", 1)[1])
        image_path = ""
        image_deadline = time.monotonic() + 2
        attempt = 0
        while time.monotonic() < image_deadline and process.poll() is None:
            image_path = setup_command(args.archive, f"android-process-path-{attempt}",
                                       prefix + ["shell", "readlink", f"/proc/{pid}/exe"],
                                       check=False).stdout.strip()
            attempt += 1
            if image_path == remote:
                break
            time.sleep(0.02)
        if image_path != remote:
            raise ValueError("Android process image path differs from deployed executable")
        image_sha = setup_command(args.archive, "android-process-sha",
                                  prefix + ["shell", "sha256sum", f"/proc/{pid}/exe"]).stdout.split()[0]
        validate_process_image(image_sha, capture.digest(harness))
        stdout, stderr = process.communicate(timeout=args.timeout)
    except Exception:
        process.kill()
        stdout, stderr = process.communicate()
        (args.archive / "stdout.bin").write_bytes(stdout)
        (args.archive / "stderr.bin").write_bytes(stderr)
        raise
    finally:
        setup_command(args.archive, "android-remove", prefix + ["shell", "rm", "-f", remote], check=False)
    (args.archive / "stdout.bin").write_bytes(stdout)
    (args.archive / "stderr.bin").write_bytes(stderr)
    ended = time.monotonic_ns()
    if process.returncode:
        raise ValueError(f"Android producer exited {process.returncode}: {stderr.decode(errors='replace')[:300]}")
    return stdout, stderr, {"command": launch, "exit_code": process.returncode,
                            "image": {"pid": pid, "path": image_path, "sha256": image_sha,
                                      "method": "procfs_exe/sha256sum"},
                            "runtime": runtime, "serial": serial, "adb_port": port,
                            "adb_sha256": capture.digest(adb), "deployed_sha256": deployed,
                            "started_ns": started, "ended_ns": ended}


def run(args):
    if not args.archive.is_absolute() or args.archive.exists():
        raise ValueError("archive must be a new absolute path")
    args.archive.mkdir(parents=True)
    receipt = {"format": "portable-mobile-capture-v1", "qualification": "unpassed",
               "target": args.target, "build": args.build, "scenario": args.scenario}
    try:
        inventory_path = capture.required_file(str(args.inventory), "mobile build inventory")
        inventory, harness, artifacts = validate_inventory(inventory_path, args.target, args.build)
        manifest = json.loads(capture.MANIFEST.read_text())
        scenario = capture.scenario_from_manifest(manifest, args.scenario)
        nonce = secrets.token_hex(16)
        producer = producer_arguments(scenario, inventory, artifacts, args.steps, args.warmup, nonce)
        (args.archive / "inventory.json").write_bytes(inventory_path.read_bytes())
        (args.archive / "input.json").write_text(json.dumps({"producer": producer, "nonce": nonce}, indent=2) + "\n")
        if args.target in APPLE_SIMULATORS:
            stdout, stderr, process = run_simulator(args, inventory, harness, producer)
        elif args.target in ANDROID_ABIS:
            stdout, stderr, process = run_android(args, inventory, harness, producer, nonce)
        else:
            raise ValueError("physical Apple deployment needs signing and selected device; runtime unpassed")
        (args.archive / "stdout.bin").write_bytes(stdout)
        (args.archive / "stderr.bin").write_bytes(stderr)
        receipt["process"] = process
        receipt["source_sha"] = inventory["source_sha"]
        receipt["producer_tree"] = inventory["producer_tree"]
        receipt["executable_sha256"] = capture.digest(harness)
        receipt["artifacts"] = artifacts
        if process["ended_ns"] <= process["started_ns"] or process["image"]["pid"] <= 0:
            raise ValueError("process PID or monotonic interval is invalid")
        protocol_bytes = (simulator_protocol_bytes(stdout, process["bundle_id"], process["image"]["pid"])
                          if args.target in APPLE_SIMULATORS else stdout)
        validate_completion(protocol_bytes, nonce)
        clocks, rows, provider, summary = capture.validate_protocol(
            protocol_bytes, scenario, inventory["source_sha"], inventory["producer_tree"],
            {"core": artifacts["dyn4k-core"]["sha256"], "kotlin": artifacts["dyn4k"]["sha256"]},
            args.build, nonce, args.steps, args.warmup, "timing")
        receipt.update({"protocol": "valid", "clock_counts": {key: len(value) for key, value in clocks.items()},
                        "step_count": len(rows), "provider": provider, "run": summary})
    except (OSError, ValueError, KeyError, IndexError, TypeError, UnicodeError,
            subprocess.TimeoutExpired) as error:
        receipt["error"] = str(error)
    (args.archive / "result.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return 0 if receipt.get("protocol") == "valid" else 1


def main():
    parser = argparse.ArgumentParser(description="Capture one mobile Native fixture run")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--target", choices=sorted(TARGETS), required=True)
    parser.add_argument("--build", choices=("development", "optimized"), required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--warmup", type=int, required=True)
    parser.add_argument("--udid")
    parser.add_argument("--adb", default="/var/home/stewart/Android/Sdk/platform-tools/adb")
    parser.add_argument("--adb-port", type=int)
    parser.add_argument("--serial")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    if args.steps < 1 or args.warmup < 0 or args.timeout < 1:
        parser.error("steps and timeout must be positive; warm-up must be nonnegative")
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
