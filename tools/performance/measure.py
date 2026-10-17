#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from manifest import manifest, validate
from analyze import activity_status


HERE = Path(__file__).resolve().parent
MANIFEST_FILE = HERE.parents[1] / "docs" / "research" / "performance-manifest-v1.json"
JAR_URL = "https://repo.maven.apache.org/maven2/org/dyn4j/dyn4j/6.0.0/dyn4j-6.0.0.jar"
JAR_HASH = manifest()["baseline_jar_sha256"]
PILOT = [
    ("separated", "default"),
    ("pile", "default"),
    ("joint", "mixed_all_types"),
    ("ccd", "default"),
    ("lifecycle", "wake"),
    ("lifecycle", "replace"),
]


def balanced_orders():
    return [
        ("baseline", "direct_kotlin", "compatibility"),
        ("direct_kotlin", "compatibility", "baseline"),
        ("compatibility", "baseline", "direct_kotlin"),
    ]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def jar_path(work, supplied):
    if supplied:
        jar = Path(supplied).resolve()
    else:
        jar = work / "dyn4j-6.0.0.jar"
        urllib.request.urlretrieve(JAR_URL, jar)
    actual = sha256(jar)
    if actual != JAR_HASH:
        raise ValueError(f"baseline artifact SHA-256 mismatch: {actual}")
    return jar


def read_text(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def host_identity(java):
    release = subprocess.run([java, "-version"], capture_output=True, text=True, check=True).stderr
    cpu = read_text("/proc/cpuinfo")
    model = next((line.split(":", 1)[1].strip() for line in (cpu or "").splitlines() if line.startswith("model name")), None)
    mem = read_text("/proc/meminfo")
    mem_kib = next((line.split()[1] for line in (mem or "").splitlines() if line.startswith("MemTotal:")), None)
    return {
        "hostname": platform.node(),
        "machine": platform.machine(),
        "system": platform.system(),
        "release": platform.release(),
        "os_version": read_text("/etc/os-release"),
        "product_name": read_text("/sys/class/dmi/id/product_name"),
        "product_version": read_text("/sys/class/dmi/id/product_version"),
        "cpu_model": model,
        "ram_kib": int(mem_kib) if mem_kib else None,
        "java_version": release.strip(),
        "power_mode": None,
        "charging_state": None,
        "temperature_c": None,
        "throttling": None,
    }


def compile_harness(javac, jar, work):
    classes = work / "classes"
    classes.mkdir()
    subprocess.run(
        [javac, "--release", "21", "-cp", str(jar), "-d", str(classes),
         str(HERE / "BaselinePilot.java"), str(HERE / "ProbeValidation.java")],
        check=True,
    )
    return classes


def run_capture(command, output, stderr_path=None, timeout=None, rss_ceiling_bytes=None):
    if timeout is None and rss_ceiling_bytes is None:
        with output.open("w") as stream:
            process = subprocess.Popen(command, stdout=stream, stderr=subprocess.PIPE, text=True)
            _, error_output = process.communicate()
        if stderr_path is not None:
            stderr_path.write_text(error_output)
        if process.returncode:
            raise RuntimeError(f"runner failed ({process.returncode}): {error_output}")
        return error_output, process.pid
    stderr_file = stderr_path or output.with_suffix(".stderr")
    reason = "bounded_end"
    with output.open("w") as stdout, stderr_file.open("w") as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, text=True)
        began = time.monotonic()
        while process.poll() is None:
            if timeout is not None and time.monotonic() - began > timeout:
                reason = "wall_time_ceiling"
                process.terminate()
                break
            if rss_ceiling_bytes is not None:
                statm = read_text(f"/proc/{process.pid}/statm")
                if statm is None:
                    reason = "rss_probe_unavailable"
                    process.terminate()
                    break
                rss = int(statm.split()[1]) * os.sysconf("SC_PAGE_SIZE")
                if rss > rss_ceiling_bytes:
                    reason = "rss_ceiling"
                    process.terminate()
                    break
            time.sleep(0.05)
        try:
            returncode = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            returncode = process.wait()
    output.with_suffix(".termination.json").write_text(json.dumps({"reason": reason, "exit_code": returncode}) + "\n")
    if reason != "bounded_end" or returncode:
        raise RuntimeError(f"runner terminated: {reason}, exit {returncode}; raw files retained")
    return stderr_file.read_text(), process.pid


def validate_csv(path, family, variant, size, hz, steps, mode):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"step", "elapsed_ns", "mutation_ns", "lateness_ns", "allocation_bytes", "heap_used_bytes", "rss_bytes", "rss_delta_bytes", "body_count", "joint_count", "awake_count", "linear_speed_sum_m_per_s", "angular_speed_sum_rad_per_s", "contact_begins", "contact_ends", "toi_events", "broadphase_candidates", "active_contact_pairs", "active_contact_points"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("raw CSV lacks required channels")
        rows = list(reader)
    if len(rows) != steps or [int(row["step"]) for row in rows] != list(range(steps)):
        raise ValueError("missing or reordered raw step samples")
    count = manifest()["families"][family][size]
    static = 1 if family in ("pile", "lifecycle") else 2 if family == "ccd" else count if family == "joint" else 0
    if any(int(row["body_count"]) != count + static for row in rows):
        raise ValueError("body count changed unexpectedly")
    if any(int(row["elapsed_ns"]) <= 0 for row in rows):
        raise ValueError("nonpositive elapsed step time")
    if any(not math.isfinite(float(row[field])) or float(row[field]) < 0
           for row in rows for field in ("linear_speed_sum_m_per_s", "angular_speed_sum_rad_per_s")):
        raise ValueError("invalid activity speed")
    if family == "joint" and any(int(row["joint_count"]) != count for row in rows):
        raise ValueError("joint topology changed")
    if family == "lifecycle" and any(int(row["joint_count"]) != (count + 9) // 10 for row in rows):
        raise ValueError("lifecycle joint topology changed")
    if mode != "timing" and any(int(row["allocation_bytes"]) < 0 for row in rows):
        raise ValueError("allocation probe unavailable")
    if any(int(row[field]) < 0 for field in ("broadphase_candidates", "active_contact_pairs", "active_contact_points") for row in (rows[0], rows[-1])):
        raise ValueError("missing diagnostic activity sample")
    return rows


def summary(rows, hz, mode):
    times = sorted(int(row["elapsed_ns"]) for row in rows)
    def percentile(p):
        return times[max(0, (len(times) * p + 99) // 100 - 1)]
    event_times = sorted(int(row["elapsed_ns"]) for row in rows if int(row["mutation_ns"]) > 0)
    final_events = sorted(int(row["elapsed_ns"]) for row in rows[-60 * hz:] if int(row["mutation_ns"]) > 0) if len(rows) >= 60 * hz else []
    def event_summary(values, tail_required):
        if not values:
            return {"count": 0, "median_ns": None, "p99_ns": None, "max_ns": None, "tail_status": "no_events"}
        return {"count": len(values), "median_ns": values[(len(values) - 1) // 2],
                "p99_ns": values[math.ceil(0.99 * len(values)) - 1] if len(values) >= tail_required else None,
                "max_ns": values[-1], "tail_status": "estimated" if len(values) >= tail_required else "insufficient_samples"}
    return {
        "samples": len(rows),
        "median_step_ns": percentile(50),
        "p95_step_ns": percentile(95),
        "p99_step_ns": percentile(99),
        "max_step_ns": times[-1],
        "compute_seconds_per_simulated_second": sum(times) / 1e9 / (len(times) / hz),
        "total_allocation_bytes": sum(int(row["allocation_bytes"]) for row in rows) if mode != "timing" else None,
        "max_lateness_ns": max(int(row["lateness_ns"]) for row in rows),
        "overrun_steps": sum(int(row["elapsed_ns"]) > 1e9 / hz for row in rows),
        "last_contact_begins": int(rows[-1]["contact_begins"]),
        "last_contact_ends": int(rows[-1]["contact_ends"]),
        "last_toi_events": int(rows[-1]["toi_events"]),
        "last_awake": int(rows[-1]["awake_count"]),
        "last_linear_speed_sum_m_per_s": float(rows[-1]["linear_speed_sum_m_per_s"]),
        "last_angular_speed_sum_rad_per_s": float(rows[-1]["angular_speed_sum_rad_per_s"]),
        "peak_broadphase_candidates": max(int(row["broadphase_candidates"]) for row in rows),
        "peak_active_contact_pairs": max(int(row["active_contact_pairs"]) for row in rows),
        "peak_active_contact_points": max(int(row["active_contact_points"]) for row in rows),
        "peak_rss_delta_bytes": max(int(row["rss_delta_bytes"]) for row in rows),
        "event_only_full": event_summary(event_times, 100),
        "event_only_final_minute": event_summary(final_events, 100),
    }


def run_scenario(java, classes, jar, out, family, variant, size, hz, steps, mode, warmup, repeat, api="baseline", runner=None, stress=False):
    name = f"{family}.{variant}.{size}.{hz}hz.{api}.{mode}.r{repeat}"
    raw = out / f"{name}.csv"
    warmup_raw = out / f"{name}.warmup.csv"
    if api == "baseline":
        command = [java, "-Xms256m", "-Xmx2g", "-XX:+UseG1GC", "-cp", os.pathsep.join((str(classes), str(jar))),
                   "BaselinePilot", family, variant, size, str(hz), str(steps), mode, str(warmup)]
    else:
        command = [str(runner), family, variant, size, str(hz), str(steps), mode, str(warmup), api]
    _, process_pid = run_capture(command, raw, warmup_raw, timeout=180 if stress else None,
                                 rss_ceiling_bytes=3 * 1024 * 1024 * 1024 if stress else None)
    warmup_lines = warmup_raw.read_text().splitlines()
    metadata = {}
    csv_lines = []
    for line in warmup_lines:
        if line.startswith("#"):
            key, value = line[1:].split("=", 1)
            metadata[key] = int(value)
        else:
            csv_lines.append(line)
    expected_metadata = {"construction_ns", "construction_allocated_bytes", "rss_empty_harness_bytes",
                         "rss_after_construction_bytes", "retained_heap_world_alive_bytes", "retained_collection_count_delta"}
    if not expected_metadata.issubset(metadata):
        raise ValueError("missing construction or retained-memory sample")
    marker = {"direct_kotlin": 1, "compatibility": 2}.get(api)
    if marker is not None and (metadata.get("process_pid") != process_pid or metadata.get("route_marker") != marker):
        raise ValueError("candidate process or route identity differs from the launcher")
    warmup_raw.write_text("\n".join(csv_lines) + "\n")
    with warmup_raw.open(newline="") as stream:
        warmup_rows = list(csv.DictReader(stream))
    if len(warmup_rows) != warmup:
        raise ValueError("missing raw warm-up steps")
    if mode == "memory" and (metadata["retained_heap_world_alive_bytes"] < 0 or metadata["retained_collection_count_delta"] <= 0):
        raise ValueError("retained-memory collection probe unavailable")
    rows = validate_csv(raw, family, variant, size, hz, steps, mode)
    result = summary(rows, hz, mode)
    result["activity_status"] = activity_status(rows, family, variant, manifest()["families"][family][size], hz)
    empty_rss = metadata["rss_empty_harness_bytes"]
    construction_rss = metadata["rss_after_construction_bytes"]
    warmup_rss = [int(row["rss_bytes"]) for row in warmup_rows if int(row["rss_bytes"]) >= 0]
    if mode == "memory" and (empty_rss < 0 or not warmup_rss):
        raise ValueError("incremental-memory probe unavailable")
    if empty_rss >= 0:
        result["peak_rss_delta_bytes"] = max([result["peak_rss_delta_bytes"], construction_rss - empty_rss]
                                             + [value - empty_rss for value in warmup_rss])
    result.update({"family": family, "variant": variant, "size": size, "hz": hz, "mode": mode, "api": api,
                   "warmup_steps": warmup, "warmup_raw": warmup_raw.name, "warmup_sha256": sha256(warmup_raw),
                   "cold_construction_ns": metadata["construction_ns"],
                   "cold_construction_allocated_bytes": metadata["construction_allocated_bytes"],
                   "rss_empty_harness_bytes": empty_rss,
                   "rss_after_construction_bytes": construction_rss,
                   "retained_heap_world_alive_bytes": metadata["retained_heap_world_alive_bytes"],
                   "retained_collection_count_delta": metadata["retained_collection_count_delta"],
                   "cold_first_step_ns": int(warmup_rows[0]["elapsed_ns"]) if warmup_rows else None,
                   "cold_process_initialization_ns": None,
                   "raw": raw.name, "raw_sha256": sha256(raw), "process_pid": process_pid,
                   "status": "capacity_report" if stress else "pilot_only" if steps < 600 * hz else "raw_unqualified"})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("probe", "pilot", "run", "stress", "matrix"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--jar")
    parser.add_argument("--java", default="java")
    parser.add_argument("--javac", default="javac")
    parser.add_argument("--family", choices=tuple(manifest()["families"]))
    parser.add_argument("--variant")
    parser.add_argument("--size", choices=("small", "medium", "stress"))
    parser.add_argument("--hz", type=int, choices=(30, 60, 120))
    parser.add_argument("--mode", choices=("timing", "allocation", "memory", "plateau"))
    parser.add_argument("--api", choices=("baseline", "direct_kotlin", "compatibility"), default="baseline")
    parser.add_argument("--runner", help="external candidate runner that emits the baseline CSV protocol")
    parser.add_argument("--candidate-artifact", help="candidate artifact file to hash")
    parser.add_argument("--warmup-seconds", type=int, default=120)
    args = parser.parse_args()
    validate(manifest())
    saved_manifest = json.loads(MANIFEST_FILE.read_text())
    validate(saved_manifest)
    if saved_manifest != manifest():
        raise ValueError("checked-in manifest differs from generator")
    if args.api != "baseline" and (not args.runner or not args.candidate_artifact):
        parser.error("candidate API needs --runner and --candidate-artifact")
    if args.api != "baseline" and args.command not in ("run", "stress"):
        parser.error("candidate API is supported by run and stress")
    if args.command == "matrix" and (not args.runner or not args.candidate_artifact):
        parser.error("matrix needs --runner and --candidate-artifact")
    if args.command in ("run", "matrix") and not 120 <= args.warmup_seconds <= 600:
        parser.error("full runs need 120 to 600 warm-up seconds")
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dyn4k-performance-") as folder:
        work = Path(folder)
        jar = jar_path(work, args.jar)
        classes = compile_harness(args.javac, jar, work)
        probe = out / "probe.json"
        run_capture([args.java, "-Xms256m", "-Xmx2g", "-XX:+UseG1GC", "-cp", str(classes), "ProbeValidation"], probe)
        probe_data = json.loads(probe.read_text())
        if probe_data["timer_min_positive_ns"] <= 0 or not probe_data["allocation_supported"]:
            raise ValueError("timer or allocation probe failed validation")
        evidence = {
            "schema": 1,
            "qualification": "unpassed",
            "baseline_jar_sha256": sha256(jar),
            "candidate_artifact_sha256": sha256(args.candidate_artifact) if args.candidate_artifact else None,
            "candidate_runner_sha256": sha256(args.runner) if args.runner else None,
            "harness_sha256": sha256(HERE / "BaselinePilot.java"),
            "manifest_sha256": sha256(MANIFEST_FILE),
            "host": host_identity(args.java),
            "java_flags": ["-Xms256m", "-Xmx2g", "-XX:+UseG1GC"],
            "probe": probe_data,
            "results": [],
        }
        if args.command == "pilot":
            for size in ("small", "medium"):
                for family, variant in PILOT:
                    for hz in (30, 60, 120):
                        evidence["results"].append(run_scenario(args.java, classes, jar, out, family, variant, size,
                            hz, 2 * hz, "timing", hz, 1))
                    for mode in ("allocation", "memory"):
                        evidence["results"].append(run_scenario(args.java, classes, jar, out, family, variant, size,
                            60, 120, mode, 60, 1))
        elif args.command in ("run", "stress", "matrix"):
            if not all((args.family, args.variant, args.size, args.hz, args.mode)):
                parser.error("measurement needs family, variant, size, hz, and mode")
            variants = {s["variant"] for s in manifest()["scenarios"] if s["family"] == args.family}
            if args.variant not in variants:
                parser.error("variant does not appear in manifest")
            if args.command == "stress" and args.size != "stress":
                parser.error("stress command requires stress size")
            if args.command == "stress" and args.mode == "plateau":
                parser.error("stress does not use plateau mode")
            if args.command in ("run", "matrix") and args.size == "stress":
                parser.error("use stress command for stress size")
            if args.command == "matrix" and args.mode == "plateau":
                parser.error("matrix does not use plateau mode")
            if args.mode == "plateau":
                raw = out / f"{args.family}.{args.variant}.{args.size}.{args.hz}hz.{args.api}.plateau.csv"
                warmup_raw = out / f"{args.family}.{args.variant}.{args.size}.{args.hz}hz.{args.api}.plateau.warmup.csv"
                if args.api == "baseline":
                    command = [args.java, "-Xms256m", "-Xmx2g", "-XX:+UseG1GC", "-cp", os.pathsep.join((str(classes), str(jar))),
                               "BaselinePilot", args.family, args.variant, args.size, str(args.hz), "1", "plateau", str(args.warmup_seconds * args.hz)]
                else:
                    command = [str(args.runner), args.family, args.variant, args.size, str(args.hz), "1", "plateau", str(args.warmup_seconds * args.hz), args.api]
                run_capture(command, raw, warmup_raw)
                with raw.open() as stream:
                    if len(list(csv.DictReader(stream))) != 100:
                        raise ValueError("plateau series lacks 100 cycles")
                with warmup_raw.open() as stream:
                    if len(list(csv.DictReader(stream))) != args.warmup_seconds * args.hz:
                        raise ValueError("plateau warm-up series is incomplete")
                evidence["plateau"] = {"raw": raw.name, "sha256": sha256(raw), "cycles": 100,
                                       "warmup_raw": warmup_raw.name, "warmup_sha256": sha256(warmup_raw)}
            elif args.command == "stress":
                try:
                    evidence["results"].append(run_scenario(args.java, classes, jar, out, args.family, args.variant,
                        args.size, args.hz, 60 * args.hz, args.mode, 30 * args.hz, 1, args.api, args.runner, True))
                except RuntimeError as exc:
                    evidence["stress_termination"] = {
                        "reason": str(exc),
                        "retained_files": {path.name: sha256(path) for path in out.glob("*.csv")},
                        "termination_files": {path.name: sha256(path) for path in out.glob("*.termination.json")},
                    }
            elif args.command == "matrix":
                evidence["run_order"] = balanced_orders()
                for repeat, order in enumerate(balanced_orders(), 1):
                    for api in order:
                        evidence["results"].append(run_scenario(args.java, classes, jar, out, args.family, args.variant,
                            args.size, args.hz, 600 * args.hz, args.mode, args.warmup_seconds * args.hz,
                            repeat, api, args.runner))
            else:
                for repeat in range(1, 4):
                    evidence["results"].append(run_scenario(args.java, classes, jar, out, args.family, args.variant,
                        args.size, args.hz, 600 * args.hz, args.mode, args.warmup_seconds * args.hz, repeat, args.api, args.runner))
        (out / "evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"output": str(out), "results": len(evidence["results"]), "qualification": "unpassed"}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc
