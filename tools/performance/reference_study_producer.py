#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import subprocess
import sys
import time

from candidate_runner import API, CORE, ROOT, STAGING
from reference_study import (PAIR_ORDER, SOURCE_COMMIT, controls_for, policy_context,
                             verify_archive)
from sustained_archive import frozen_policy, observe_process_image, require_external_key


STUDY_KEY = ("jvm_vs_dyn4j|jvm.java|separated.default.small.30hz.compatibility|"
             "timing|median|full")
SOURCE_FILES = ("SustainedPilot.java", "SustainedSidecars.java")
STAGE_TASKS = (":dyn4k-core:publishJvmPublicationToStagingRepository",
               ":dyn4k:publishJvmPublicationToStagingRepository")
BUILD_INPUTS = ("dyn4k", "dyn4k-core", "tools/performance/sustained_jvm",
                "build.gradle.kts", "settings.gradle.kts", "gradle.properties",
                "gradle", "gradlew", "gradlew.bat", "buildSrc", "build-logic")


class ProducerError(ValueError):
    pass


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ProducerError("invalid producer arguments") from None


def need(condition, message):
    if not condition:
        raise ProducerError(message)


def child_environment(env=None):
    result = dict(os.environ if env is None else env)
    result.pop("OLLAMA_API_KEY", None)
    return result


def git_result(root, *args):
    result = subprocess.run(["git", *args], cwd=root, env=child_environment(),
                            capture_output=True, text=True)
    need(result.returncode == 0, "source check failed")
    return result.stdout.strip()


def source_trees(commit, root=ROOT):
    return {name: git_result(root, "rev-parse", f"{commit}:{name}")
            for name in ("dyn4k-core", "dyn4k")}


def check_frozen_inputs(root, source_commit):
    need(not (Path(root) / "local.properties").exists(),
         "ignored local Gradle properties are present")
    need(not git_result(root, "status", "--porcelain", "--untracked-files=all", "--",
                        *BUILD_INPUTS), "build or JVM source inputs have uncommitted changes")
    need(source_trees("HEAD", root) == source_trees(source_commit, root),
         "engine source differs from frozen reference source")
    sources = [f"tools/performance/sustained_jvm/{name}" for name in SOURCE_FILES]
    result = subprocess.run(["git", "diff", "--quiet", source_commit, "--", *sources],
                            cwd=root, env=child_environment())
    need(result.returncode == 0, "JVM producer source differs from frozen reference source")


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def read_json(path):
    return json.loads(Path(path).read_text())


def host_identity():
    need(sys.platform.startswith("linux"), "Linux procfs observation is required")
    machine = Path("/etc/machine-id").read_text().strip()
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    need(bool(machine and boot), "host or boot identity is unavailable")
    return machine, boot


def process_start_ticks(pid):
    data = Path(f"/proc/{pid}/stat").read_text()
    return int(data.rsplit(") ", 1)[1].split()[19])


def process_rss_bytes(pid):
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            fields = line.split()
            need(len(fields) == 3 and fields[2] == "kB", "unexpected procfs RSS unit")
            return int(fields[1]) * 1024
    raise ValueError("process RSS observation is unavailable")


def process_command(pid):
    raw = Path(f"/proc/{pid}/cmdline").read_bytes().rstrip(b"\0")
    return [part.decode("utf-8") for part in raw.split(b"\0")] if raw else []


def process_environment(pid):
    raw = Path(f"/proc/{pid}/environ").read_bytes().rstrip(b"\0")
    entries = dict(part.decode("utf-8").split("=", 1)
                   for part in raw.split(b"\0") if b"=" in part)
    return {name: entries.get(name) for name in
            ("DYN4K_CLOCK_NONCE", "DYN4K_SOURCE_COMMIT", "JAVA_HOME", "TMPDIR")}


def observe_process(command, env, folder, nonce, expected_image_sha, timeout=15):
    folder = Path(folder)
    need(not folder.exists(), "run folder already exists")
    folder.mkdir(parents=True)
    host_id, boot_id = host_identity()
    run_env = child_environment(env)
    run_env["DYN4K_CLOCK_NONCE"] = nonce
    started = time.monotonic_ns()
    with (folder / "series.csv").open("wb") as stdout, \
            (folder / "stderr.raw").open("wb") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, env=run_env,
                                   stdout=stdout, stderr=stderr)
        image = None
        ticks = None
        argv = None
        observed_env = None
        samples = []
        deadline = time.monotonic() + timeout

        def confirmed_exit():
            if process.poll() is not None:
                return True
            time.sleep(0.01)
            return process.poll() is not None

        try:
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    candidate = observe_process_image(process.pid)
                    if candidate["sha256"] != expected_image_sha:
                        if samples:
                            raise ProducerError("observed process image differs")
                        time.sleep(0.01)
                        continue
                    need(Path(candidate["executable_path"]).resolve() ==
                         Path(command[0]).resolve(), "observed process image path differs")
                    current_ticks = process_start_ticks(process.pid)
                    need(ticks is None or ticks == current_ticks,
                         "process start identity changed during observation")
                    current_argv = process_command(process.pid)
                    if not current_argv:
                        if process.poll() is not None and samples:
                            break
                        raise ProducerError("observed process command is unavailable")
                    need(current_argv == command, "observed process command differs")
                    current_env = process_environment(process.pid)
                    observed_nonce = current_env["DYN4K_CLOCK_NONCE"]
                    if not observed_nonce and process.poll() is not None and samples:
                        break
                    need(observed_nonce == nonce, "observed launch nonce differs")
                    if process.poll() is not None:
                        break
                    try:
                        rss = process_rss_bytes(process.pid)
                    except (OSError, ValueError):
                        if confirmed_exit() and samples:
                            break
                        raise ProducerError("process RSS observation is unavailable") from None
                    need(isinstance(rss, int) and rss >= 0,
                         "process RSS observation is invalid")
                    ticks, argv, observed_env = current_ticks, current_argv, current_env
                    image = candidate
                    samples.append({"clock_ns": time.monotonic_ns(), "os_pid": process.pid,
                                    "process_start_id": str(ticks),
                                    "rss_bytes": rss})
                except (FileNotFoundError, ProcessLookupError):
                    if confirmed_exit() and samples:
                        break
                    if not samples and process.poll() is None:
                        continue
                    raise ProducerError("process identity observation is unavailable") from None
                time.sleep(0.01)
            if process.poll() is None:
                process.kill()
                process.wait()
                raise ValueError("observed process exceeded bounded wall limit")
            code = process.wait()
        except Exception:
            if process.poll() is None:
                process.kill()
                process.wait()
            raise
    ended = time.monotonic_ns()
    need(code == 0, f"launched process failed with exit code {code}")
    need(image is not None and ticks is not None and samples,
         "executed process image and start were not observed")
    need(all(started <= item["clock_ns"] <= ended and item["rss_bytes"] >= 0
             for item in samples), "monitor clock or RSS differs")
    process_id = f"{host_id}:{boot_id}:{process.pid}:{ticks}"
    monitor = {"host_id": host_id, "boot_id": boot_id, "os_pid": process.pid,
               "process_start_id": str(ticks), "launch_nonce": nonce,
               "started_ns": started, "ended_ns": ended, "samples": samples}
    observation = {"host_id": host_id, "boot_id": boot_id,
                   "os_pid": process.pid, "process_start_id": str(ticks),
                   "process_id": process_id, "run_id": nonce,
                   "started_ns": started, "ended_ns": ended,
                   "observed_command": argv, "observed_environment": observed_env,
                   "image": image, "exit_code": code}
    write_json(folder / "monitor.json", monitor)
    write_json(folder / "observation.json", observation)
    return observation


def checked_rows(path, header, count):
    with Path(path).open(newline="") as stream:
        reader = csv.DictReader(stream)
        need(reader.fieldnames is not None and reader.fieldnames[:len(header)] == header,
             f"invalid {Path(path).name} header")
        rows = list(reader)
    need(len(rows) == count, f"invalid {Path(path).name} row count")
    return rows


def check_pilot(folder, observation, baseline_sha, harness_sha, java_sha,
                staged_core_sha, staged_kotlin_sha, seconds, warmup_seconds):
    folder = Path(folder)
    pid, nonce = observation["os_pid"], observation["run_id"]
    provider = read_json(folder / "provider.json")
    origin = read_json(folder / "clock-origin.json")
    run = read_json(folder / "run.json")
    need(provider["pid"] == pid and provider["api"] == "baseline" and
         provider["source_commit"] == SOURCE_COMMIT and
         provider["runtime_sha256"] == java_sha and
         provider["baseline_sha256"] == baseline_sha and
         provider["loaded_core_sha256"] == baseline_sha and
         provider["loaded_harness_sha256"] == harness_sha and
         provider["loaded_adapter_sha256"] == harness_sha and
         provider["loaded_kotlin_sha256"] is None and
         provider["artifact_sha256"] == {"core": staged_core_sha,
                                          "kotlin": staged_kotlin_sha},
         "provider or staged artifact differs from external file receipt")
    need(origin["pid"] == pid and origin["nonce"] == nonce and
         observation["started_ns"] <= origin["runtime_ns"] <= observation["ended_ns"],
         "process origin PID, nonce, or clock differs")
    need(observation["observed_environment"]["DYN4K_SOURCE_COMMIT"] == SOURCE_COMMIT and
         observation["observed_environment"]["DYN4K_CLOCK_NONCE"] == nonce and
         observation["image"]["sha256"] == java_sha,
         "OS-observed process environment or image differs")
    count, warmup = 30 * seconds, 30 * warmup_seconds
    series = checked_rows(folder / "series.csv", ["step", "elapsed_ns"], count)
    clocks = checked_rows(folder / "clock.csv", ["step", "begin_ns", "end_ns"], count)
    warm = checked_rows(folder / "warmup-clock.csv",
                        ["warmup_step", "begin_ns", "end_ns"], warmup)
    for index, (row, clock) in enumerate(zip(series, clocks)):
        begin, end = int(clock["begin_ns"]), int(clock["end_ns"])
        need(int(row["step"]) == index and int(clock["step"]) == index and
             int(row["elapsed_ns"]) == end - begin and
             observation["started_ns"] <= begin < end <= observation["ended_ns"],
             "series or measurement clock differs")
    for index, clock in enumerate(warm):
        begin, end = int(clock["begin_ns"]), int(clock["end_ns"])
        need(int(clock["warmup_step"]) == index and
             origin["runtime_ns"] <= begin < end <= observation["ended_ns"],
             "warm-up clock differs")
    need(run["api"] == "baseline" and run["mode"] == "timing" and
         run["sample_count"] == count and run["warmup_count"] == warmup and
         run["status"] == "complete", "run receipt differs")


def run_checked(command, cwd, env, stdout, stderr, timeout):
    with Path(stdout).open("wb") as out, Path(stderr).open("wb") as err:
        result = subprocess.run(command, cwd=cwd, env=child_environment(env), stdout=out, stderr=err,
                                timeout=timeout)
    need(result.returncode == 0, "helper command failed")


def toolchain(args, root, env):
    java = Path(args.java).resolve(strict=True)
    javac = Path(args.javac).resolve(strict=True)
    gradle = Path(args.gradle).resolve(strict=True)
    baseline = Path(args.baseline).resolve(strict=True)
    need(java.parent == javac.parent and java.parent.name == "bin" and
         java.parent.parent.name == "jdk21", "pinned JDK21 tools differ")
    need("gradle-9.5.0" in gradle.parts, "pinned Gradle 9.5.0 is required")
    need(digest(baseline) == frozen_policy()["baseline_jar_sha256"],
         "pinned dyn4j baseline bytes differ")
    check_frozen_inputs(ROOT, SOURCE_COMMIT)
    sources = [ROOT / "tools/performance/sustained_jvm" / name for name in SOURCE_FILES]
    env.update(JAVA_HOME=str(java.parent.parent),
               PATH=str(java.parent) + os.pathsep + env["PATH"],
               GRADLE_OPTS=f"-Djava.io.tmpdir={env['TMPDIR']}")
    android_sdk = Path.home() / "Android/Sdk"
    need(android_sdk.is_dir(), "cached Android SDK is unavailable")
    env["ANDROID_HOME"] = str(android_sdk)
    build = root / "build"
    build.mkdir()
    run_checked([str(gradle), "--offline", "--no-daemon", *STAGE_TASKS], ROOT, env,
                build / "stage.stdout.raw", build / "stage.stderr.raw", 180)
    core, kotlin = STAGING / CORE, STAGING / API
    need(core.is_file() and kotlin.is_file(), "staged JVM artifacts are unavailable")
    staged = root / "staged"
    staged.mkdir()
    for source, name in ((core, "core.jar"), (kotlin, "kotlin.jar")):
        shutil.copyfile(source, staged / name)
        need(digest(source) == digest(staged / name), "staged artifact changed during copy")
    classes = build / "classes"
    classes.mkdir()
    run_checked([str(javac), "--release", "21", "-cp", str(baseline),
                 "-d", str(classes), *map(str, sources)], ROOT, env,
                build / "javac.stdout.raw", build / "javac.stderr.raw", 60)
    harness = build / "sustained-harness.jar"
    run_checked([str(java.parent / "jar"), "--create", "--file", str(harness),
                 "-C", str(classes), "."], ROOT, env,
                build / "jar.stdout.raw", build / "jar.stderr.raw", 30)
    receipt = {"source_commit": SOURCE_COMMIT, "engine_source_trees": source_trees(SOURCE_COMMIT),
               "producer_sources": {name: digest(path) for name, path in zip(SOURCE_FILES, sources)},
               "baseline_sha256": digest(baseline), "harness_sha256": digest(harness),
               "staged_core_sha256": digest(staged / "core.jar"),
               "staged_kotlin_sha256": digest(staged / "kotlin.jar"),
               "runtime_sha256": digest(java), "gradle_sha256": digest(gradle),
               "gradle_command": [str(gradle), "--offline", "--no-daemon", *STAGE_TASKS],
               "java": str(java), "javac": str(javac), "gradle": str(gradle)}
    write_json(build / "receipt.json", receipt)
    return java, baseline, harness, receipt


def study_cli(command, root, key, *options):
    script = ROOT / "tools/performance/reference_study.py"
    result = subprocess.run([sys.executable, str(script), command, "--archive",
                             str(root / "archive"), "--trusted-key", str(key), *options],
                            cwd=root, env=child_environment(), capture_output=True,
                            text=True, timeout=60)
    need(result.returncode == 0, "reference study helper failed")
    return json.loads(result.stdout)


def capture(args):
    root = Path(args.output_root).resolve()
    key = Path(args.trusted_key).resolve(strict=True)
    require_external_key(key, [root])
    need(not root.exists(), "producer output root already exists")
    need(1 <= args.seconds <= 5 and 1 <= args.warmup_seconds <= 5,
         "bounded durations must be 1 to 5 seconds")
    need(STUDY_KEY in policy_context()[1] and
         controls_for(STUDY_KEY) == ["dyn4j_6_0_0_jvm"],
         "frozen JVM study assignment differs")
    home = Path.home().resolve()
    temporary = Path(os.environ.get("TMPDIR", "")).resolve()
    need(temporary.is_dir() and temporary.is_relative_to(home),
         "home-backed TMPDIR is required")
    root.mkdir(parents=True)
    env = child_environment()
    env["JAVA_TOOL_OPTIONS"] = f"-Djava.io.tmpdir={temporary}"
    java, baseline, harness, receipt = toolchain(args, root, env)
    receipt["seconds"] = args.seconds
    receipt["warmup_seconds"] = args.warmup_seconds
    write_json(root / "build/receipt.json", receipt)
    host_id, boot_id = host_identity()
    plan = {"source_commit": SOURCE_COMMIT,
            "assignments": [{"phase": "source", "key": STUDY_KEY,
                             "controls": ["dyn4j_6_0_0_jvm"]}],
            "controls": [{"row_id": "jvm.java", "control_id": "dyn4j_6_0_0_jvm",
                          "route": "baseline", "host_id": host_id, "boot_id": boot_id,
                          "artifact_path": str(baseline), "probe_path": str(harness),
                          "runtime_path": str(java), "image_path": str(java)}]}
    write_json(root / "plan.json", plan)
    study_cli("create", root, key, "--plan", str(root / "plan.json"))
    protocol_sha = digest(root / "archive/protocol.json")
    captures = []
    observations = []
    for pair, sides in enumerate(PAIR_ORDER, 1):
        for order, side in enumerate(sides, 1):
            serial = len(captures) + 1
            folder = root / "runs" / f"{serial:02d}-pair{pair}-{side}"
            folder.parent.mkdir(exist_ok=True)
            nonce = secrets.token_hex(16)
            outputs = {name: folder / name for name in
                       ("clock.csv", "warmup-clock.csv", "resource.csv",
                        "provider.json", "run.json", "clock-origin.json")}
            run_env = dict(env)
            run_env.update(DYN4K_CLOCK_CSV=str(outputs["clock.csv"]),
                           DYN4K_WARMUP_CLOCK_CSV=str(outputs["warmup-clock.csv"]),
                           DYN4K_RESOURCE_CSV=str(outputs["resource.csv"]),
                           DYN4K_PROVIDER_JSON=str(outputs["provider.json"]),
                           DYN4K_RUN_JSON=str(outputs["run.json"]),
                           DYN4K_CLOCK_ORIGIN_JSON=str(outputs["clock-origin.json"]),
                           DYN4K_SOURCE_COMMIT=SOURCE_COMMIT,
                           DYN4K_BASELINE_SHA256=receipt["baseline_sha256"],
                           DYN4K_ARTIFACT_HASHES_JSON=json.dumps({
                               "core": receipt["staged_core_sha256"],
                               "kotlin": receipt["staged_kotlin_sha256"]}))
            command = [str(java), f"-Djava.io.tmpdir={temporary}", "-cp",
                       os.pathsep.join((str(harness), str(baseline))),
                       "SustainedPilot", "separated", "default", "small", "30",
                       str(30 * args.seconds), "timing", str(30 * args.warmup_seconds),
                       "baseline"]
            observed = observe_process(command, run_env, folder, nonce,
                                       receipt["runtime_sha256"],
                                       timeout=args.seconds + args.warmup_seconds + 10)
            check_pilot(folder, observed, receipt["baseline_sha256"],
                        receipt["harness_sha256"], receipt["runtime_sha256"],
                        receipt["staged_core_sha256"], receipt["staged_kotlin_sha256"],
                        args.seconds, args.warmup_seconds)
            environment = {"host_id": host_id, "boot_id": boot_id,
                           "os_pid": observed["os_pid"],
                           "process_start_id": observed["process_start_id"],
                           "launch_nonce": nonce, "observer": observed,
                           "artifact_sha256": receipt["baseline_sha256"],
                           "probe_sha256": receipt["harness_sha256"],
                           "runtime_sha256": receipt["runtime_sha256"],
                           "image_sha256": observed["image"]["sha256"],
                           "staged_core_sha256": receipt["staged_core_sha256"],
                           "staged_kotlin_sha256": receipt["staged_kotlin_sha256"],
                           "provider_sha256": digest(outputs["provider.json"]),
                           "clock_origin_sha256": digest(outputs["clock-origin.json"]),
                           "series_sha256": digest(folder / "series.csv"),
                           "monitor_sha256": digest(folder / "monitor.json")}
            write_json(folder / "environment.json", environment)
            capture_row = {"phase": "source", "key": STUDY_KEY,
                           "control_id": "dyn4j_6_0_0_jvm", "row_id": "jvm.java",
                           "route": "baseline", "host_id": host_id, "boot_id": boot_id,
                           "pair": pair, "side": side, "order": order,
                           "process_id": observed["process_id"],
                           "run_id": nonce, "os_pid": observed["os_pid"],
                           "process_start_id": observed["process_start_id"],
                           "started_ns": observed["started_ns"],
                           "ended_ns": observed["ended_ns"],
                           "invalid_reason": None, "stop_reason": "completed",
                           **{name + "_sha256": environment[name + "_sha256"]
                              for name in ("artifact", "probe", "runtime", "image")},
                           "series_path": str((folder / "series.csv").relative_to(root)),
                           "environment_path": str((folder / "environment.json").relative_to(root)),
                           "monitor_path": str((folder / "monitor.json").relative_to(root))}
            captures.append(capture_row)
            observations.append({"observation_path": str((folder / "observation.json").relative_to(root)),
                                 "observation_sha256": digest(folder / "observation.json"),
                                 "environment_sha256": digest(folder / "environment.json"),
                                 "monitor_sha256": digest(folder / "monitor.json"),
                                 "series_sha256": digest(folder / "series.csv")})
    write_json(root / "captures.json", captures)
    write_json(root / "producer-observations.json", {
        "protocol_sha256_before_capture": protocol_sha,
        "tool_sha256": digest(__file__), "build_receipt_sha256": digest(root / "build/receipt.json"),
        "captures": observations})
    result = study_cli("seal", root, key, "--captures", str(root / "captures.json"))
    audit_output(root, key)
    return result


def audit_output(root, key):
    root = Path(root).resolve(strict=True)
    key = Path(key).resolve(strict=True)
    require_external_key(key, [root])
    result = verify_archive(root / "archive", key.read_bytes(), SOURCE_COMMIT)
    captures = read_json(root / "captures.json")
    indexed = read_json(root / "archive/archive.json")["captures"]
    controls = read_json(root / "archive/protocol.json")["controls"]
    receipt = read_json(root / "build/receipt.json")
    provenance = read_json(root / "producer-observations.json")
    need(digest(root / "build/sustained-harness.jar") == receipt["harness_sha256"] and
         digest(root / "staged/core.jar") == receipt["staged_core_sha256"] and
         digest(root / "staged/kotlin.jar") == receipt["staged_kotlin_sha256"],
         "staged artifact or probe bytes differ")
    need(len(captures) == len(indexed) == len(provenance["captures"]) == 6,
         "producer capture inventory differs")
    need(provenance["protocol_sha256_before_capture"] ==
         digest(root / "archive/protocol.json") and
         provenance["tool_sha256"] == digest(__file__) and
         provenance["build_receipt_sha256"] == digest(root / "build/receipt.json"),
         "producer or frozen protocol receipt differs")
    control = controls[0]
    for name in ("artifact", "probe", "runtime", "image"):
        expected = receipt["baseline_sha256"] if name == "artifact" else (
            receipt["harness_sha256"] if name == "probe" else receipt["runtime_sha256"])
        need(control[name + "_sha256"] == expected, "control file receipt differs")
    for position, (capture_row, index, meta) in enumerate(zip(captures, indexed,
                                                                 provenance["captures"])):
        folder = root / "runs" / f"{position + 1:02d}-pair{capture_row['pair']}-{capture_row['side']}"
        observation = read_json(root / meta["observation_path"])
        need(digest(root / meta["observation_path"]) == meta["observation_sha256"],
             "external process observation bytes differ")
        monitor = read_json(root / capture_row["monitor_path"])
        environment = read_json(root / capture_row["environment_path"])
        for name in ("series", "monitor", "environment"):
            original = root / capture_row[name + "_path"]
            need(original.is_file() and digest(original) == meta[name + "_sha256"] and
                 digest(original) == index[name + "_sha256"],
                 f"{name} source, observer, or archive bytes differ")
        for name in ("phase", "key", "control_id", "row_id", "route", "host_id",
                     "boot_id", "pair", "side", "order", "process_id", "run_id",
                     "os_pid", "process_start_id", "started_ns", "ended_ns",
                     "invalid_reason", "stop_reason", "artifact_sha256", "probe_sha256",
                     "runtime_sha256", "image_sha256"):
            need(capture_row[name] == index[name], f"capture {name} differs from sealed archive")
        for name in ("host_id", "boot_id", "os_pid", "process_start_id",
                     "started_ns", "ended_ns"):
            need(capture_row[name] == observation[name] == monitor[name],
                 f"observed {name} differs")
        need(capture_row["process_id"] == observation["process_id"] and
             capture_row["run_id"] == observation["run_id"] == monitor["launch_nonce"] ==
             environment["launch_nonce"] and
             environment["observer"] == observation,
             "observed process or launch run differs")
        need(environment["os_pid"] == observation["os_pid"] and
             environment["process_start_id"] == observation["process_start_id"] and
             environment["host_id"] == observation["host_id"] and
             environment["boot_id"] == observation["boot_id"],
             "environment process identity differs")
        for name in ("artifact", "probe", "runtime", "image"):
            need(environment[name + "_sha256"] == capture_row[name + "_sha256"],
                 f"environment {name} differs")
        need(environment["series_sha256"] == digest(folder / "series.csv") and
             environment["monitor_sha256"] == digest(folder / "monitor.json") and
             environment["provider_sha256"] == digest(folder / "provider.json") and
             environment["clock_origin_sha256"] == digest(folder / "clock-origin.json") and
             all(observation["started_ns"] <= sample["clock_ns"] <= observation["ended_ns"] and
                 sample["os_pid"] == observation["os_pid"] and
                 sample["process_start_id"] == observation["process_start_id"] and
                 sample["rss_bytes"] >= 0 for sample in monitor["samples"]) and
             bool(monitor["samples"]), "monitor or raw origin differs")
        check_pilot(folder, observation, receipt["baseline_sha256"],
                    receipt["harness_sha256"], receipt["runtime_sha256"],
                    receipt["staged_core_sha256"], receipt["staged_kotlin_sha256"],
                    receipt["seconds"], receipt["warmup_seconds"])
    return result


def main():
    parser = SafeArgumentParser()
    parser.add_argument("command", choices=("capture", "audit"))
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--trusted-key", required=True)
    parser.add_argument("--java")
    parser.add_argument("--javac")
    parser.add_argument("--gradle")
    parser.add_argument("--baseline")
    parser.add_argument("--seconds", type=int, default=1)
    parser.add_argument("--warmup-seconds", type=int, default=1)
    try:
        args = parser.parse_args()
        if args.command == "capture":
            need(all((args.java, args.javac, args.gradle, args.baseline)),
                 "capture requires pinned Java, javac, Gradle, and baseline paths")
            result = capture(args)
        else:
            result = audit_output(args.output_root, args.trusted_key)
        print(json.dumps(result, sort_keys=True))
    except Exception as exc:
        reason = str(exc) if isinstance(exc, ProducerError) else "producer failed closed"
        print(json.dumps({"qualification": "unpassed", "reason": reason}, sort_keys=True))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
