#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import secrets
import signal
import subprocess
import sys
import time
import zipfile


ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "docs/research/performance-manifest-v1.json"
NATIVE_HOST_TARGETS = {"linuxX64", "linuxArm64", "mingwX64", "macosArm64"}
NATIVE_TARGET_NAMES = {"linuxX64": "linux_x64", "linuxArm64": "linux_arm64",
                       "mingwX64": "mingw_x64", "macosArm64": "macos_arm64"}
ARTIFACT_VERSION = "0.1.0-alpha.1"
ARTIFACT_GROUP = "io.github.rubixhacker"
TARGETS = {"js", "wasmJs", "wasmWasi"} | NATIVE_HOST_TARGETS
MODES = {"timing"}
STEP_HEADER = ("step", "elapsed_ns", "mutation_ns", "lateness_ns", "body_count",
               "joint_count", "awake_count", "linear_speed_sum_m_per_s",
               "angular_speed_sum_rad_per_s", "contact_begins", "contact_ends",
               "toi_events", "broadphase_candidates", "active_contact_pairs",
               "active_contact_points")


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            value.update(block)
    return value.hexdigest()


def required_file(value, label):
    path = Path(value)
    if not path.is_absolute() or not path.is_file():
        raise ValueError(f"{label} must be an absolute regular file: {value}")
    return path.resolve(strict=True)


def scenario_from_manifest(manifest, scenario_id):
    matches = [item for item in manifest["scenarios"] if item["id"] == scenario_id]
    if len(matches) != 1:
        raise ValueError(f"manifest has no unique scenario: {scenario_id}")
    scenario = matches[0]
    if scenario["api"] not in ("direct_kotlin", "compatibility"):
        raise ValueError("portable candidate requires direct_kotlin or compatibility")
    return scenario


def source_tree():
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD:consumers/performance/portable"],
        text=True).strip()


def bundle_hashes(harness):
    return {
        str(path.relative_to(harness.parent)): digest(path)
        for path in sorted(harness.parent.rglob("*")) if path.is_file()
    }


def native_module(label, target):
    if label not in ("dyn4k-core", "dyn4k") or target not in NATIVE_HOST_TARGETS:
        raise ValueError("unknown Native artifact or target")
    return f"{ARTIFACT_GROUP}:{label}-{target.lower()}:{ARTIFACT_VERSION}"


def native_artifacts(inventory, target):
    artifacts = inventory.get("resolved_artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise ValueError("Native inventory needs exactly two resolved engine artifacts")
    expected = {native_module(label, target): label for label in ("dyn4k-core", "dyn4k")}
    if {item.get("module") for item in artifacts if isinstance(item, dict)} != set(expected):
        raise ValueError("Native artifact coordinates differ from exact target, group, or version")
    return {expected[item["module"]]: item for item in artifacts}


def validate_klib(path, label, target):
    if path.suffix != ".klib" or not zipfile.is_zipfile(path):
        raise ValueError(f"{label} is not a KLIB archive")
    try:
        with zipfile.ZipFile(path) as archive:
            entries = set(archive.namelist())
            if not {"default/manifest", "default/ir/bodies.knb"} <= entries:
                raise ValueError(f"{label} KLIB lacks Native compiler entries")
            fields = dict(line.split("=", 1) for line in
                          archive.read("default/manifest").decode("utf-8").splitlines()
                          if "=" in line)
    except (zipfile.BadZipFile, KeyError, UnicodeError) as error:
        raise ValueError(f"{label} has an invalid KLIB manifest") from error
    required = {"builtins_platform": "NATIVE", "compiler_version": "2.4.20",
                "native_targets": NATIVE_TARGET_NAMES[target], "short_name": label,
                "unique_name": f"{ARTIFACT_GROUP}\\:{label}"}
    if any(fields.get(key) != value for key, value in required.items()):
        raise ValueError(f"{label} KLIB identity differs from exact target or compiler")


def validate_publication(root, label, target, selected_sha):
    module = f"{label}-{target.lower()}"
    directory = root / "io" / "github" / "rubixhacker" / module / ARTIFACT_VERSION
    stem = f"{module}-{ARTIFACT_VERSION}"
    klib = required_file(str(directory / f"{stem}.klib"), "staged KLIB")
    metadata = required_file(str(directory / f"{stem}.module"), "staged module metadata")
    sources = required_file(str(directory / f"{stem}-sources.jar"), "staged source archive")
    for path in (klib, metadata, sources):
        sidecar = required_file(str(path.with_name(path.name + ".sha256")), "staged checksum")
        if sidecar.read_text().strip().lower() != digest(path):
            raise ValueError("staged publication checksum differs from bytes")
    if digest(klib) != selected_sha:
        raise ValueError("resolved KLIB differs from staged publication")
    document = json.loads(metadata.read_text())
    if document.get("component") != {"url": f"../../{label}/{ARTIFACT_VERSION}/{label}-{ARTIFACT_VERSION}.module",
                                      "group": ARTIFACT_GROUP, "module": label,
                                      "version": ARTIFACT_VERSION,
                                      "attributes": {"org.gradle.status": "release"}}:
        raise ValueError("staged publication component differs from selected module")
    variant_name = target + "ApiElements-published"
    variants = [entry for entry in document.get("variants", []) if entry.get("name") == variant_name]
    files = variants[0].get("files", []) if len(variants) == 1 else []
    if len(files) != 1 or files[0].get("url") != klib.name or files[0].get("sha256") != selected_sha:
        raise ValueError("staged publication metadata differs from resolved KLIB")
    source_variants = [entry for entry in document.get("variants", [])
                       if entry.get("name") == target + "SourcesElements-published"]
    source_files = source_variants[0].get("files", []) if len(source_variants) == 1 else []
    if (len(source_files) != 1 or source_files[0].get("url") != sources.name or
            source_files[0].get("sha256") != digest(sources)):
        raise ValueError("staged publication metadata differs from source archive")
    source_root = ROOT / label / "src"
    sets = {"commonMain", "nativeMain", target + "Main"}
    if target.startswith("linux"):
        sets.add("linuxMain")
    if target == "macosArm64":
        sets.add("appleMain")
    expected = {str(path.relative_to(source_root)).replace("/kotlin/", "/"): path
                for path in source_root.rglob("*.kt")
                if path.relative_to(source_root).parts[0] in sets}
    try:
        with zipfile.ZipFile(sources) as archive:
            actual = {name for name in archive.namelist() if name.endswith(".kt")}
            if actual != set(expected) or not actual:
                raise ValueError("staged source archive differs from checked-out source inventory")
            for name, path in expected.items():
                if archive.read(name) != path.read_bytes():
                    raise ValueError("staged source archive differs from checked-out source bytes")
    except (zipfile.BadZipFile, KeyError) as error:
        raise ValueError("staged source archive is invalid") from error
    return {"module": native_module(label, target), "staged_klib": str(klib),
            "klib_sha256": selected_sha, "module_metadata": str(metadata),
            "module_metadata_sha256": digest(metadata), "sources": str(sources),
            "sources_sha256": digest(sources), "source_archive_matches_checkout": True,
            "source_to_link": "unpassed"}


def observed_process_image(pid):
    if sys.platform.startswith("linux"):
        path = Path(f"/proc/{pid}/exe")
        return {"method": "procfs_exe", "path": os.readlink(path),
                "identity_kind": "mapped_executable", "sha256": digest(path)}
    if sys.platform == "darwin":
        import ctypes
        library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        buffer = ctypes.create_string_buffer(4096)
        length = library.proc_pidpath(pid, buffer, len(buffer))
        if length <= 0:
            raise OSError(ctypes.get_errno(), "proc_pidpath failed")
        path = Path(os.fsdecode(buffer.value))
        return {"method": "proc_pidpath", "path": str(path),
                "identity_kind": "reported_path_only", "sha256": None}
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                       wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(buffer))
            if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
                raise ctypes.WinError(ctypes.get_last_error())
            path = Path(buffer.value)
            return {"method": "QueryFullProcessImageNameW", "path": str(path),
                    "identity_kind": "reported_path_only", "sha256": None}
        finally:
            kernel.CloseHandle(handle)
    raise OSError(f"no native process image observer for {sys.platform}")


def require_native_host(target):
    hosts = {
        "linuxX64": ("linux", {"x86_64", "amd64"}),
        "linuxArm64": ("linux", {"aarch64", "arm64"}),
        "mingwX64": ("win32", {"amd64", "x86_64"}),
        "macosArm64": ("darwin", {"arm64", "aarch64"}),
    }
    system, machines = hosts[target]
    if not sys.platform.startswith(system) or platform.machine().lower() not in machines:
        raise ValueError(f"{target} requires its matching Native host")


def require_process_image(image, expected_sha):
    if image is None or image.get("identity_kind") != "mapped_executable":
        raise ValueError("mapped process image bytes are unobserved; raw archive retained")
    if image.get("sha256") != expected_sha:
        raise ValueError("observed process image does not match runtime; raw archive retained")


def run_process(command, archive, inventory_path, stdin_bytes, timeout_seconds):
    started = time.monotonic_ns()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               stdin=subprocess.PIPE if stdin_bytes else None,
                               cwd=ROOT, env=os.environ.copy(),
                               start_new_session=(os.name == "posix"))
    image = None
    image_error = None
    try:
        image = observed_process_image(process.pid)
    except OSError as error:
        image_error = str(error)
    image_observed = time.monotonic_ns()
    termination = "natural"
    try:
        remaining = max(0.001, timeout_seconds - (image_observed - started) / 1e9)
        stdout, stderr = process.communicate(input=stdin_bytes or None, timeout=remaining)
    except subprocess.TimeoutExpired:
        termination = "host_deadline"
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except OSError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except OSError:
                pass
            try:
                stdout, stderr = process.communicate(timeout=3)
            except subprocess.TimeoutExpired as error:
                termination = "host_deadline_cleanup_incomplete"
                stdout, stderr = error.stdout or b"", error.stderr or b""
                for stream in (process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
    ended = time.monotonic_ns()
    (archive / "stdout.raw").write_bytes(stdout)
    (archive / "stderr.raw").write_bytes(stderr)
    (archive / "stdin.raw").write_bytes(stdin_bytes)
    (archive / "build-inventory.json").write_bytes(inventory_path.read_bytes())
    receipt = {"pid": process.pid, "command": command, "started_monotonic_ns": started,
               "image_observed_monotonic_ns": image_observed, "ended_monotonic_ns": ended,
               "observed_image": image, "image_observation_error": image_error,
               "exit_code": process.returncode, "termination": termination,
               "host_timeout_seconds": timeout_seconds,
               "stdout_sha256": digest(archive / "stdout.raw"),
               "stderr_sha256": digest(archive / "stderr.raw"),
               "inventory_sha256": digest(archive / "build-inventory.json")}
    (archive / "execution.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt, stdout, stderr


def validate_inventory(path, target, build, source_sha, producer_tree, manifest, harness,
                       core, kotlin, bundle, publication_root=None):
    inventory = json.loads(path.read_text())
    expected = {
        "format": "portable-build-inventory-v1", "target": target, "build": build,
        "source_sha": source_sha, "producer_tree": producer_tree,
        "manifest_sha256": digest(manifest), "harness": str(harness),
        "bundle_sha256": bundle, "gradle": "9.5.0", "kgp": "2.4.20",
    }
    if target in NATIVE_HOST_TARGETS:
        mode = "debug" if build == "development" else "release"
        expected.update({
            "compile_configuration": f"{target}CompileKlibraries",
            "compiler_mode": mode,
            "link_task": f"link{mode.title()}Executable{target[0].upper()}{target[1:]}",
        })
    if any(inventory.get(key) != value for key, value in expected.items()):
        raise ValueError("build inventory differs from selected source, build, or bundle")
    tracked = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", "HEAD",
         "consumers/performance/portable", "tools/performance/sustained_portable"],
        text=True).splitlines()
    source_files = {name: digest(ROOT / name) for name in tracked}
    if inventory.get("source_files") != source_files:
        raise ValueError("build inventory source file hashes differ from checkout")
    artifacts = inventory.get("resolved_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("build inventory has no resolved compilation artifacts")
    selected_native = native_artifacts(inventory, target) if target in NATIVE_HOST_TARGETS else None
    for artifact in artifacts:
        actual = required_file(artifact["path"], "resolved compilation artifact")
        if digest(actual) != artifact["sha256"]:
            raise ValueError("resolved compilation artifact changed after build")
    if selected_native is not None:
        if publication_root is None:
            raise ValueError("Native inventory requires an independent staged publication root")
        publication_root = Path(publication_root)
        if not publication_root.is_absolute() or not publication_root.is_dir():
            raise ValueError("staged publication root must be an absolute directory")
        inventory["publication_inputs"] = []
        for label in ("dyn4k-core", "dyn4k"):
            artifact = selected_native[label]
            validate_klib(Path(artifact["path"]), label, target)
            inventory["publication_inputs"].append(
                validate_publication(publication_root, label, target, artifact["sha256"]))
    for label, selected in (("dyn4k-core", core), ("dyn4k", kotlin)):
        selected_hash = digest(selected)
        matches = [item for item in artifacts if item["sha256"] == selected_hash and
                   ((label == "dyn4k-core" and ":dyn4k-core-" in item["module"]) or
                    (label == "dyn4k" and ":dyn4k-" in item["module"] and
                     ":dyn4k-core-" not in item["module"]))]
        if len(matches) != 1:
            raise ValueError(f"selected {label} is not the Gradle-resolved build input")
    return inventory


def validate_protocol(raw, scenario, source_sha, producer_tree, hashes, build, nonce, steps, warmup, mode):
    records = []
    for line in raw.decode("utf-8").splitlines():
        if not line.startswith("DYN4K\t"):
            raise ValueError(f"unexpected producer output: {line[:100]}")
        records.append(line.split("\t")[1:])
    def next_record(index, kind):
        if index >= len(records) or records[index][0] != kind:
            raise ValueError(f"expected {kind} at producer record {index}")
        return records[index]

    dynamic = scenario["dynamic_bodies"]
    family = scenario["family"]
    bodies = dynamic * 2 if family == "joint" else dynamic + (2 if family == "ccd" else 1 if family in ("pile", "lifecycle") else 0)
    joints = dynamic if family == "joint" else (dynamic + 9) // 10 if family == "lifecycle" else 0
    provider = next_record(0, "PROVIDER")
    if provider != ["PROVIDER", scenario["api"], source_sha, hashes["core"],
                    hashes["kotlin"], scenario["id"], build, nonce]:
        raise ValueError("provider does not match exact selected inputs")
    resolution = next_record(1, "RESOLUTION")
    if len(resolution) != 3 or int(resolution[1]) <= 0 or int(resolution[2]) < 64:
        raise ValueError("clock resolution calibration is missing or nonpositive")
    if next_record(2, "LINK") != ["LINK", source_sha, producer_tree]:
        raise ValueError("linked producer identity differs from selected source")
    construction = next_record(3, "CONSTRUCTION")
    if construction != ["CONSTRUCTION", str(bodies), str(joints)]:
        raise ValueError("construction does not match manifest fixture")
    clocks = {"warmup": [], "measure": []}
    previous_end = -1
    cursor = 4
    for step in range(warmup):
        row = next_record(cursor, "CLOCK")
        if len(row) != 5 or row[1:3] != ["warmup", str(step)]:
            raise ValueError("warmup clock stream is incomplete")
        begin, end = map(int, row[3:])
        if begin < previous_end or end <= begin:
            raise ValueError("warmup clock stream is not positive and monotonic")
        clocks["warmup"].append((step, begin, end))
        previous_end = end
        cursor += 1
    reset = next_record(cursor, "RESET")
    if reset != ["RESET", "after_warmup", str(warmup)]:
        raise ValueError("fixture reset marker does not match warm-up")
    cursor += 1
    step_rows = []
    previous_events = (0, 0, 0)
    for step in range(steps):
        clock = next_record(cursor, "CLOCK")
        if len(clock) != 5 or clock[1:3] != ["measure", str(step)]:
            raise ValueError("measure clock stream is incomplete")
        begin, end = map(int, clock[3:])
        if begin < previous_end or end <= begin:
            raise ValueError("measure clock stream is not positive and monotonic")
        clocks["measure"].append((step, begin, end))
        previous_end = end
        cursor += 1
        row = next_record(cursor, "STEP")
        if len(row) != 16 or row[1] != str(step):
            raise ValueError("malformed or out-of-order activity row")
        elapsed, mutation, lateness, body_count, joint_count, awake = map(int, row[2:8])
        if elapsed != end - begin or mutation < 0 or mutation > elapsed or lateness < 0:
            raise ValueError("invalid step timing or clock disagreement")
        if (body_count, joint_count) != (bodies, joints) or not 0 <= awake <= dynamic:
            raise ValueError("invalid fixture activity")
        for value in row[8:10]:
            speed = float(value)
            if not math.isfinite(speed) or speed < 0:
                raise ValueError("non-finite or negative physical activity")
        events = tuple(map(int, row[10:13]))
        if any(value < prior for value, prior in zip(events, previous_events)):
            raise ValueError("event counters decreased")
        previous_events = events
        pairs = tuple(map(int, row[13:16]))
        sampled = step % scenario["rate_hz"] == 0 or step == steps - 1
        if sampled:
            broad, active, points = pairs
            if broad < 0 or active < 0 or points < 0 or active > broad or points < active:
                raise ValueError("invalid sampled pair counts")
        elif pairs != (-1, -1, -1):
            raise ValueError("unsampled pair counts must be -1")
        step_rows.append(row)
        cursor += 1
    run = next_record(cursor, "RUN")
    if len(run) != 10 or next_record(cursor + 1, "COMPLETE") != ["COMPLETE", nonce] or cursor + 1 != len(records) - 1:
        raise ValueError("run requires a final matching completion marker")
    if run[:5] != ["RUN", scenario["api"], mode, str(steps), str(warmup)]:
        raise ValueError("run summary does not match selected inputs")
    if run[7:] != ["memory_attribution_missing", "plateau_missing", "unpassed"]:
        raise ValueError("run summary omitted unfinished evidence")
    if int(run[5]) < sum(end - begin for _, begin, end in clocks["measure"]) or not 0 <= int(run[6]) <= steps:
        raise ValueError("run summary has invalid elapsed time or activity count")
    if int(run[6]) != sum(int(row[7]) > 0 for row in step_rows):
        raise ValueError("run activity count disagrees with steps")
    return clocks, step_rows, provider, run


def capture(args):
    if args.target not in TARGETS or args.mode not in MODES:
        raise ValueError("unsupported target or mode")
    if args.target in NATIVE_HOST_TARGETS:
        require_native_host(args.target)
    if args.steps < 1 or args.warmup < 0:
        raise ValueError("steps must be positive and warm-up nonnegative")
    host_timeout = float(getattr(args, "host_timeout_seconds", 45.0))
    if not math.isfinite(host_timeout) or not 0 < host_timeout <= 900:
        raise ValueError("host timeout must be positive and at most 900 seconds")
    if args.build not in ("development", "optimized"):
        raise ValueError("unknown build configuration")
    manifest_path = required_file(str(MANIFEST), "manifest")
    manifest = json.loads(manifest_path.read_text())
    scenario = scenario_from_manifest(manifest, args.scenario)
    current_sha = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    if args.source_sha != current_sha:
        raise ValueError("source SHA does not match the current checkout")
    dirty = subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=all"], text=True)
    if dirty.strip():
        raise ValueError("source checkout is dirty; commit the producer before capture")
    runtime = required_file(args.runtime, "runtime")
    harness = required_file(args.harness, "harness")
    core = required_file(args.core, "core")
    kotlin = required_file(args.kotlin, "kotlin")
    if args.target in NATIVE_HOST_TARGETS and runtime != harness:
        raise ValueError("native runtime must be the exact executable harness")
    if args.target not in NATIVE_HOST_TARGETS and runtime == harness:
        raise ValueError("script target requires a separate runtime executable")
    if args.target in ("linuxX64", "linuxArm64"):
        with harness.open("rb") as stream:
            magic = stream.read(4)
        if magic != b"\x7fELF":
            raise ValueError("Linux Native harness must be an ELF executable")
    elif args.target == "mingwX64":
        with harness.open("rb") as stream:
            magic = stream.read(2)
        if magic != b"MZ":
            raise ValueError("Windows Native harness must be a PE executable")
    elif args.target == "macosArm64":
        with harness.open("rb") as stream:
            magic = stream.read(4)
        if magic not in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"):
            raise ValueError("macOS Native harness must be a Mach-O executable")
    elif args.target == "js" and harness.suffix != ".js":
        raise ValueError("JS harness must be a JavaScript entry")
    elif args.target in ("wasmJs", "wasmWasi") and harness.suffix != ".mjs":
        raise ValueError("Wasm harness must be a module entry")
    bundle = bundle_hashes(harness)
    if args.target.startswith("wasm") and not any(name.endswith(".wasm") for name in bundle):
        raise ValueError("Wasm harness has no adjacent Wasm binary")
    expected_build_path = {
        "development": ("developmentExecutable", "debugExecutable"),
        "optimized": ("productionExecutable", "releaseExecutable"),
    }[args.build]
    if not any(token in harness.parts for token in expected_build_path):
        raise ValueError("harness path does not match selected build configuration")
    hashes = {
        "manifest": digest(manifest_path), "runtime": digest(runtime),
        "harness": digest(harness), "core": digest(core), "kotlin": digest(kotlin),
    }
    producer_tree = source_tree()
    inventory_path = required_file(args.inventory, "build inventory")
    inventory = validate_inventory(inventory_path, args.target, args.build, args.source_sha,
                                   producer_tree, manifest_path, harness, core, kotlin, bundle,
                                   getattr(args, "publication_root", None))
    source_link = None
    if getattr(args, "source_link_receipt", None) is not None:
        if args.target != "linuxX64":
            raise ValueError("source-link trace receipt is limited to Linux x64")
        import native_source_link
        source_link = native_source_link.verify_receipt(
            args.source_link_receipt, str(inventory_path), args.build)
        native_source_link.require_selected_inputs(
            source_link, args.build, inventory_path, hashes["runtime"],
            {"dyn4k-core": hashes["core"], "dyn4k": hashes["kotlin"]})
    if not args.archive.is_absolute() or args.archive.exists():
        raise ValueError("archive must be a new absolute path")
    args.archive.mkdir(parents=True)
    if source_link is not None:
        receipt_path = args.archive / "source-link.json"
        receipt_path.write_bytes(Path(args.source_link_receipt).read_bytes())
    publication_archive = []
    if inventory.get("publication_inputs"):
        directory = args.archive / "publication"
        directory.mkdir()
        for item in inventory["publication_inputs"]:
            label = item["module"].split(":")[1]
            for key, expected_hash in (("staged_klib", item["klib_sha256"]),
                                       ("module_metadata", item["module_metadata_sha256"]),
                                       ("sources", item["sources_sha256"])):
                for origin in (Path(item[key]), Path(item[key] + ".sha256")):
                    target = directory / f"{label}-{origin.name}"
                    target.write_bytes(origin.read_bytes())
                    if origin.suffix == ".sha256":
                        if target.read_text().strip().lower() != expected_hash:
                            raise ValueError("staged checksum changed while archiving")
                    elif digest(target) != expected_hash:
                        raise ValueError("staged publication changed while archiving")
                    publication_archive.append({"path": str(target.relative_to(args.archive)),
                                                "sha256": digest(target)})
    nonce = secrets.token_hex(16)
    producer_args = [
        scenario["id"], scenario["family"], scenario["variant"], scenario["size"],
        str(scenario["rate_hz"]), str(args.steps), str(args.warmup), args.mode,
        scenario["api"], args.source_sha, hashes["core"], hashes["kotlin"],
        args.build, nonce,
    ]
    command = [str(runtime)] + ([] if args.target in NATIVE_HOST_TARGETS else [str(harness)])
    stdin_bytes = b""
    if args.target == "wasmWasi":
        stdin_bytes = ("\t".join(producer_args) + "\n").encode("utf-8")
    else:
        command += producer_args
    execution, stdout, stderr = run_process(
        command, args.archive, inventory_path, stdin_bytes, host_timeout)
    process_record = {
        "qualification": "unpassed", "protocol": "portable-development-v1",
        "target": args.target, "build": args.build, "mode": args.mode,
        "scenario": scenario, "source_sha": args.source_sha,
        "producer_tree": producer_tree,
        "build_inventory_sha256": digest(args.archive / "build-inventory.json"),
        "build_inventory": {"gradle": inventory["gradle"], "kgp": inventory["kgp"],
                            "compile_configuration": inventory["compile_configuration"]},
        "publication_inputs": inventory.get("publication_inputs", []),
        "publication_archive": publication_archive,
        "source_to_link": "unpassed",
        "source_link_trace": ({"receipt_sha256": digest(args.archive / "source-link.json"),
                               "source_reads": len(source_link["source_files"]),
                               "producer_source_reads": len(source_link["producer_source_files"]) + 1,
                               "build": args.build,
                               "publication_writes": source_link["observed_syscalls"]["publication"]["write"],
                               "link_writes": source_link["observed_syscalls"][args.build]["write"],
                               "executable_install": source_link["observed_syscalls"][args.build]["executable_install"],
                               "scope": "observed source reads, fresh KLIB equality, resolved KLIB reads, executable bytes"}
                              if source_link is not None else None),
        "command": command, "inputs": {
            label: {"path": str(path), "sha256": hashes[label]}
            for label, path in (("manifest", manifest_path), ("runtime", runtime),
                                ("harness", harness), ("core", core), ("kotlin", kotlin))
        },
        "bundle_sha256": bundle,
        "stdin_sha256": hashlib.sha256(stdin_bytes).hexdigest(),
        "stdin_bytes": len(stdin_bytes),
        "pid": execution["pid"], "host": platform.uname()._asdict(),
        "started_monotonic_ns": execution["started_monotonic_ns"],
        "ended_monotonic_ns": execution["ended_monotonic_ns"],
        "observed_image": execution["observed_image"],
        "process_image_identity": (
            "observed" if execution["observed_image"] is not None and
            execution["observed_image"].get("identity_kind") == "mapped_executable"
            else "unobserved"),
        "image_observation_error": execution["image_observation_error"],
        "execution_sha256": digest(args.archive / "execution.json"),
        "termination": execution["termination"],
        "host_timeout_seconds": host_timeout, "exit_code": execution["exit_code"],
        "raw": {"stdout_sha256": digest(args.archive / "stdout.raw"),
                "stdout_bytes": len(stdout), "stderr_sha256": digest(args.archive / "stderr.raw"),
                "stderr_bytes": len(stderr)},
        "memory_attribution": "missing", "plateau": "missing",
        "allocation": "missing",
        "noise_approval": "missing", "stress_ceiling_approval": "missing",
        "required_non_jvm_gates": {
            "absolute_p99_seconds": manifest["budgets"]["absolute_p99_seconds"][str(scenario["rate_hz"])],
            "shim_vs_direct": manifest["budgets"]["shim_vs_direct"],
            "java_baseline": "jvm_only",
        },
    }
    (args.archive / "capture.json").write_text(json.dumps(process_record, indent=2) + "\n")
    if execution["termination"].startswith("host_deadline"):
        raise ValueError("producer exceeded host deadline; raw archive retained")
    if execution["exit_code"] != 0:
        raise ValueError(f"producer exited {execution['exit_code']}; raw archive retained")
    try:
        clocks, steps, provider, run = validate_protocol(
            stdout, scenario, args.source_sha, producer_tree, hashes, args.build, nonce,
            args.steps, args.warmup, args.mode)
    except ValueError as error:
        process_record["protocol_error"] = str(error)
        (args.archive / "capture.json").write_text(json.dumps(process_record, indent=2) + "\n")
        raise
    for phase, filename in (("warmup", "warmup_clock.csv"), ("measure", "clock.csv")):
        lines = ["step,begin_ns,end_ns"] + [",".join(map(str, row)) for row in clocks[phase]]
        (args.archive / filename).write_text("\n".join(lines) + "\n")
    (args.archive / "activity.csv").write_text(
        ",".join(STEP_HEADER) + "\n" +
        "\n".join(",".join(row[1:]) for row in steps) + "\n")
    (args.archive / "provider.json").write_text(json.dumps({
        "api": provider[1], "source_sha": provider[2], "core_sha256": provider[3],
        "kotlin_sha256": provider[4], "scenario": provider[5],
        "build": provider[6], "nonce": provider[7], "pid": execution["pid"],
        "runtime_sha256": hashes["runtime"], "harness_sha256": hashes["harness"],
    }, indent=2) + "\n")
    (args.archive / "run.json").write_text(json.dumps({
        "api": run[1], "mode": run[2], "steps": int(run[3]),
        "warmup_steps": int(run[4]), "measured_wall_ns": int(run[5]),
        "active_steps": int(run[6]), "memory_attribution": "missing",
        "allocation": "missing", "plateau": "missing", "qualification": "unpassed",
    }, indent=2) + "\n")
    try:
        require_process_image(execution["observed_image"], hashes["runtime"])
    except ValueError as error:
        process_record["process_identity_error"] = str(error)
        (args.archive / "capture.json").write_text(json.dumps(process_record, indent=2) + "\n")
        raise
    return process_record


def main():
    parser = argparse.ArgumentParser(description="Capture a portable candidate process and its raw evidence")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--target", choices=sorted(TARGETS), required=True)
    parser.add_argument("--build", choices=("development", "optimized"), required=True)
    parser.add_argument("--mode", choices=sorted(MODES), default="timing")
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--harness", required=True)
    parser.add_argument("--core", required=True)
    parser.add_argument("--kotlin", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--publication-root", type=Path)
    parser.add_argument("--source-link-receipt", type=Path)
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--warmup", type=int, required=True)
    parser.add_argument("--host-timeout-seconds", type=float, default=45.0)
    args = parser.parse_args()
    try:
        record = capture(args)
    except (ValueError, OSError, subprocess.CalledProcessError, UnicodeError) as error:
        parser.exit(1, f"qualification: unpassed; {error}\n")
    print(json.dumps({"qualification": "unpassed", "archive": str(args.archive),
                      "pid": record["pid"], "exit_code": record["exit_code"],
                      "stdout_bytes": record["raw"]["stdout_bytes"]}))


if __name__ == "__main__":
    main()
