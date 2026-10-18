#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import secrets
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "docs/research/performance-manifest-v1.json"
TARGETS = {"js", "wasmJs", "wasmWasi", "linuxX64"}
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


def validate_inventory(path, target, build, source_sha, producer_tree, manifest, harness,
                       core, kotlin, bundle):
    inventory = json.loads(path.read_text())
    expected = {
        "format": "portable-build-inventory-v1", "target": target, "build": build,
        "source_sha": source_sha, "producer_tree": producer_tree,
        "manifest_sha256": digest(manifest), "harness": str(harness),
        "bundle_sha256": bundle, "gradle": "9.5.0", "kgp": "2.4.20",
    }
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
    for artifact in artifacts:
        actual = required_file(artifact["path"], "resolved compilation artifact")
        if digest(actual) != artifact["sha256"]:
            raise ValueError("resolved compilation artifact changed after build")
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
    if args.steps < 1 or args.warmup < 0:
        raise ValueError("steps must be positive and warm-up nonnegative")
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
    if args.target == "linuxX64" and runtime != harness:
        raise ValueError("native runtime must be the exact executable harness")
    if args.target != "linuxX64" and runtime == harness:
        raise ValueError("script target requires a separate runtime executable")
    if args.target == "linuxX64":
        with harness.open("rb") as stream:
            magic = stream.read(4)
        if magic != b"\x7fELF":
            raise ValueError("linuxX64 harness must be an ELF executable")
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
                                   producer_tree, manifest_path, harness, core, kotlin, bundle)
    if not args.archive.is_absolute() or args.archive.exists():
        raise ValueError("archive must be a new absolute path")
    args.archive.mkdir(parents=True)
    nonce = secrets.token_hex(16)
    producer_args = [
        scenario["id"], scenario["family"], scenario["variant"], scenario["size"],
        str(scenario["rate_hz"]), str(args.steps), str(args.warmup), args.mode,
        scenario["api"], args.source_sha, hashes["core"], hashes["kotlin"],
        args.build, nonce,
    ]
    command = [str(runtime)] + ([] if args.target == "linuxX64" else [str(harness)])
    stdin_bytes = b""
    if args.target == "wasmWasi":
        stdin_bytes = ("\t".join(producer_args) + "\n").encode("utf-8")
    else:
        command += producer_args
    started = time.monotonic_ns()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               stdin=subprocess.PIPE if stdin_bytes else None,
                               cwd=ROOT, env=os.environ.copy())
    image_path = Path(f"/proc/{process.pid}/exe")
    image = None
    try:
        image = {"path": os.readlink(image_path), "sha256": digest(image_path)}
    except OSError:
        pass
    stdout, stderr = process.communicate(input=stdin_bytes if stdin_bytes else None)
    ended = time.monotonic_ns()
    (args.archive / "stdout.raw").write_bytes(stdout)
    (args.archive / "stderr.raw").write_bytes(stderr)
    (args.archive / "stdin.raw").write_bytes(stdin_bytes)
    (args.archive / "build-inventory.json").write_bytes(inventory_path.read_bytes())
    process_record = {
        "qualification": "unpassed", "protocol": "portable-development-v1",
        "target": args.target, "build": args.build, "mode": args.mode,
        "scenario": scenario, "source_sha": args.source_sha,
        "producer_tree": producer_tree,
        "build_inventory_sha256": digest(args.archive / "build-inventory.json"),
        "build_inventory": {"gradle": inventory["gradle"], "kgp": inventory["kgp"],
                            "compile_configuration": inventory["compile_configuration"]},
        "command": command, "inputs": {
            label: {"path": str(path), "sha256": hashes[label]}
            for label, path in (("manifest", manifest_path), ("runtime", runtime),
                                ("harness", harness), ("core", core), ("kotlin", kotlin))
        },
        "bundle_sha256": bundle,
        "stdin_sha256": hashlib.sha256(stdin_bytes).hexdigest(),
        "stdin_bytes": len(stdin_bytes),
        "pid": process.pid, "host": platform.uname()._asdict(),
        "started_monotonic_ns": started, "ended_monotonic_ns": ended,
        "observed_image": image, "exit_code": process.returncode,
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
    if process.returncode != 0:
        raise ValueError(f"producer exited {process.returncode}; raw archive retained")
    if image is None or image["sha256"] != hashes["runtime"]:
        raise ValueError("observed process image does not match runtime; raw archive retained")
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
        "build": provider[6], "nonce": provider[7], "pid": process.pid,
        "runtime_sha256": hashes["runtime"], "harness_sha256": hashes["harness"],
    }, indent=2) + "\n")
    (args.archive / "run.json").write_text(json.dumps({
        "api": run[1], "mode": run[2], "steps": int(run[3]),
        "warmup_steps": int(run[4]), "measured_wall_ns": int(run[5]),
        "active_steps": int(run[6]), "memory_attribution": "missing",
        "allocation": "missing", "plateau": "missing", "qualification": "unpassed",
    }, indent=2) + "\n")
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
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--warmup", type=int, required=True)
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
