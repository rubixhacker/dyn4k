#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import statistics
import tempfile
from pathlib import Path

from analyze import plateau_status, warmup_status
from candidate_runner import IDENTITY, ROOT, STAGING
from manifest import manifest
from measure import (PILOT, compile_harness, host_identity, jar_path, run_capture,
                     run_scenario, sha256)


STATE_FIELDS = (
    "body_count", "joint_count", "awake_count", "linear_speed_sum_m_per_s",
    "angular_speed_sum_rad_per_s", "contact_begins", "contact_ends", "toi_events",
    "broadphase_candidates", "active_contact_pairs", "active_contact_points",
)


def state_checksum(path):
    digest = hashlib.sha256()
    with Path(path).open(newline="") as stream:
        for row in csv.DictReader(stream):
            digest.update((",".join(row[field] for field in STATE_FIELDS) + "\n").encode())
    return digest.hexdigest()


def save(out, evidence):
    (out / "evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")


def clean_warmup(path, api, process_pid):
    metadata = {}
    lines = []
    for line in path.read_text().splitlines():
        if line.startswith("#"):
            key, value = line[1:].split("=", 1)
            metadata[key] = int(value)
        else:
            lines.append(line)
    marker = {"direct_kotlin": 1, "compatibility": 2}.get(api)
    if marker is not None and (metadata.get("process_pid") != process_pid or
                               metadata.get("route_marker") != marker):
        raise ValueError("plateau route or process identity differs from the launcher")
    path.write_text("\n".join(lines) + "\n")
    return metadata


def select_scenarios(names):
    if not names:
        return PILOT
    variants = {(item["family"], item["variant"]) for item in manifest()["scenarios"]}
    selected = []
    for name in names:
        matches = [(family, variant) for family, variant in variants if name == f"{family}.{variant}"]
        if len(matches) != 1:
            raise ValueError(f"unknown frozen workload: {name}")
        selected.append(matches[0])
    return selected


def pilot(args, out, evidence, java, classes, jar):
    scenarios = select_scenarios(args.scenario)
    evidence["expected_runs"] = len(scenarios) * len(args.mode) * args.repeats * 3
    evidence["run_order"] = [
        ("baseline", "direct_kotlin", "compatibility"),
        ("direct_kotlin", "compatibility", "baseline"),
        ("compatibility", "baseline", "direct_kotlin"),
    ]
    for family, variant in scenarios:
        for mode in args.mode:
            for repeat in range(1, args.repeats + 1):
                order = evidence["run_order"][(repeat - 1) % 3]
                for position, api in enumerate(order, 1):
                    try:
                        result = run_scenario(java, classes, jar, out, family, variant, args.size,
                            args.hz, args.seconds * args.hz, mode, args.warmup_seconds * args.hz,
                            repeat, api, str(ROOT / "tools/performance/candidate_runner.py"))
                        result["workload_id"] = f"{family}.{variant}.{args.size}.{args.hz}hz.{api}"
                        result["run_order_position"] = position
                        result["state_checksum_sha256"] = state_checksum(out / result["raw"])
                        result["warmup_status"] = warmup_status(
                            list(csv.DictReader((out / result["warmup_raw"]).open())), args.hz)
                        evidence["results"].append(result)
                        if result["activity_status"] == "invalid":
                            evidence["failures"].append({"workload_id": result["workload_id"],
                                                          "repeat": repeat, "reason": "inactive scene"})
                    except (OSError, ValueError, RuntimeError) as exc:
                        evidence["failures"].append({"workload_id": f"{family}.{variant}.{args.size}.{args.hz}hz.{api}",
                                                      "repeat": repeat, "reason": str(exc)})
                    save(out, evidence)


def plateau(args, out, evidence, java, classes, jar):
    family, variant = select_scenarios(args.scenario)[0]
    evidence["expected_runs"] = 3
    for api in ("baseline", "direct_kotlin", "compatibility"):
        name = f"{family}.{variant}.{args.size}.{args.hz}hz.{api}.plateau"
        raw = out / f"{name}.csv"
        warmup = out / f"{name}.warmup.csv"
        if api == "baseline":
            command = [java, "-Xms256m", "-Xmx2g", "-XX:+UseG1GC", "-cp",
                       f"{classes}:{jar}", "BaselinePilot", family, variant, args.size,
                       str(args.hz), "1", "plateau", str(args.warmup_seconds * args.hz)]
        else:
            command = [str(ROOT / "tools/performance/candidate_runner.py"), family, variant,
                       args.size, str(args.hz), "1", "plateau", str(args.warmup_seconds * args.hz), api]
        try:
            _, pid = run_capture(command, raw, warmup)
            clean_warmup(warmup, api, pid)
            with raw.open(newline="") as stream:
                cycles = list(csv.DictReader(stream))
            with warmup.open(newline="") as stream:
                warm = list(stream)
            status = plateau_status(cycles)
            early = statistics.median(int(row["heap_after_collection_bytes"]) for row in cycles[20:40])
            late = statistics.median(int(row["heap_after_collection_bytes"]) for row in cycles[80:100])
            result = {"workload_id": f"{family}.{variant}.{args.size}.{args.hz}hz.{api}",
                      "api": api, "process_pid": pid, "cycles": len(cycles),
                      "warmup_steps": len(warm) - 1, "plateau_status": status,
                      "heap_drift_fraction": abs(late / early - 1.0) if early > 0 else None,
                      "warmup_status": warmup_status(list(csv.DictReader(warm)), args.hz),
                      "raw": raw.name, "raw_sha256": sha256(raw),
                      "warmup_raw": warmup.name, "warmup_sha256": sha256(warmup)}
            evidence["results"].append(result)
            if status != "stable" or len(warm) - 1 != args.warmup_seconds * args.hz:
                evidence["failures"].append({"workload_id": result["workload_id"],
                                              "reason": "plateau or warm-up sample invalid"})
        except (OSError, ValueError, RuntimeError) as exc:
            evidence["failures"].append({"workload_id": name, "reason": str(exc)})
        save(out, evidence)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--jar", required=True)
    parser.add_argument("--java", required=True)
    parser.add_argument("--javac", required=True)
    parser.add_argument("--scenario", action="append")
    parser.add_argument("--size", choices=("small", "medium"), default="small")
    parser.add_argument("--hz", type=int, choices=(30, 60, 120), default=60)
    parser.add_argument("--mode", action="append", choices=("timing", "allocation", "memory"))
    parser.add_argument("--seconds", type=int, default=2)
    parser.add_argument("--warmup-seconds", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--plateau", action="store_true")
    args = parser.parse_args()
    if min(args.seconds, args.warmup_seconds, args.repeats) < 1:
        parser.error("seconds, warm-up, and repeats must be positive")
    if args.plateau and len(args.scenario or []) != 1:
        parser.error("plateau needs one --scenario")
    args.mode = args.mode or ["timing", "allocation"]
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    identity = json.loads(IDENTITY.read_text())
    with tempfile.TemporaryDirectory(prefix="dyn4k-candidate-pilot-") as folder:
        jar = jar_path(Path(folder), args.jar)
        classes = compile_harness(args.javac, jar, Path(folder))
        probe_path = out / "probe.json"
        run_capture([args.java, "-Xms256m", "-Xmx2g", "-XX:+UseG1GC", "-cp",
                     str(classes), "ProbeValidation"], probe_path)
        evidence = {"schema": 1, "qualification": "unpassed", "status": "bounded_pilot_only",
                    "manifest_sha256": sha256(ROOT / "docs/research/performance-manifest-v1.json"),
                    "baseline_jar_sha256": sha256(jar),
                    "candidate_identity": identity,
                    "candidate_identity_sha256": sha256(IDENTITY),
                    "candidate_runner_sha256": sha256(ROOT / "tools/performance/candidate_runner.py"),
                    "harness_sha256": sha256(ROOT / "tools/performance/BaselinePilot.java"),
                    "direct_fixture_sha256": sha256(ROOT / "consumers/performance/src/main/kotlin/performance/DirectFixture.kt"),
                    "direct_pilot_sha256": sha256(ROOT / "consumers/performance/src/main/kotlin/performance/DirectPilot.kt"),
                    "host": host_identity(args.java), "probe": json.loads(probe_path.read_text()),
                    "results": [], "failures": []}
        if args.plateau:
            plateau(args, out, evidence, args.java, classes, jar)
        else:
            pilot(args, out, evidence, args.java, classes, jar)
        save(out, evidence)
        print(json.dumps({"output": str(out), "expected_runs": evidence["expected_runs"],
                          "completed_runs": len(evidence["results"]), "failures": len(evidence["failures"]),
                          "qualification": "unpassed"}))


if __name__ == "__main__":
    main()
