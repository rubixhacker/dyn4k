#!/usr/bin/env python3
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from candidate_pilot import STATE_FIELDS, state_checksum
from candidate_runner import IDENTITY, ROOT, git, prepare
from manifest import manifest
from measure import compile_harness, host_identity, jar_path, run_capture, run_scenario, sha256
from verify_candidate_archive import verify_identity


def rows(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def first_difference(left, right):
    for step, (before, after) in enumerate(zip(left, right)):
        for field in STATE_FIELDS:
            if before[field] != after[field]:
                return {"step": step, "channel": field, "left": before[field], "right": after[field]}
    if len(left) != len(right):
        return {"step": min(len(left), len(right)), "channel": "row_count",
                "left": len(left), "right": len(right)}
    return None


def capture(out, java, javac, baseline):
    source_commit = git("rev-parse", "HEAD")
    prepare(java, source_commit)
    identity = json.loads(IDENTITY.read_text())
    verify_identity(identity)
    shutil.copyfile(IDENTITY, out / "candidate-identity.json")
    result = {
        "schema": 1,
        "purpose": "CCD fixture and staged-route diagnostic; performance qualification unpassed",
        "source_commit": source_commit,
        "candidate_identity_sha256": sha256(IDENTITY),
        "baseline_jar_sha256": sha256(baseline),
        "manifest_sha256": sha256(ROOT / "docs/research/performance-manifest-v1.json"),
        "trace_tool_sha256": sha256(ROOT / "tools/performance/ccd_route_trace.py"),
        "fixture_hash_scheme": "Per fixture, hashCode equals zero-based creation index; two walls then 25 bullet circles",
        "workloads": {route: f"ccd.default.small.60hz.{route}"
                      for route in ("baseline", "direct_kotlin", "compatibility")},
        "warmup_steps": 60,
        "measured_steps": 120,
        "host": host_identity(java),
        "identity": {},
        "timing": {},
        "comparisons": {},
        "qualification": "unpassed",
    }
    with tempfile.TemporaryDirectory(prefix="dyn4k-ccd-route-trace-") as folder:
        work = Path(folder)
        jar = jar_path(work, baseline)
        classes = compile_harness(javac, jar, work)
        for route in result["workloads"]:
            name = f"{route}.fixture-identity"
            raw = out / f"{name}.csv"
            stderr = out / f"{name}.stderr.raw"
            args = ["ccd", "default", "small", "60", "1", "fixture_identity", "0"]
            if route == "baseline":
                command = [java, "-Xms256m", "-Xmx2g", "-XX:+UseG1GC", "-cp",
                           os.pathsep.join((str(classes), str(jar))), "BaselinePilot", *args]
            else:
                command = [sys.executable, str(ROOT / "tools/performance/candidate_runner.py"),
                           *args, route]
            _, pid = run_capture(command, raw, stderr)
            result["identity"][route] = {
                "raw": raw.name, "sha256": sha256(raw), "stderr_raw": stderr.name,
                "stderr_sha256": sha256(stderr), "process_pid": pid, "rows": len(rows(raw)),
            }
            measured = run_scenario(java, classes, jar, out, "ccd", "default", "small", 60,
                                    120, "timing", 60, 1, route,
                                    str(ROOT / "tools/performance/candidate_runner.py"))
            measured["state_checksum_sha256"] = state_checksum(out / measured["raw"])
            result["timing"][route] = measured
        identities = {route: rows(out / item["raw"]) for route, item in result["identity"].items()}
        expected = list(range(27))
        for route, values in identities.items():
            if len(values) != 27 or [int(row["hash_code"]) for row in values] != expected:
                raise ValueError(f"CCD fixture creation hashes differ: {route}")
        if len({json.dumps(value, sort_keys=True) for value in identities.values()}) != 1:
            raise ValueError("CCD fixture initial identities differ")
        traces = {route: rows(out / item["raw"]) for route, item in result["timing"].items()}
        for left, right in (("direct_kotlin", "compatibility"),
                            ("baseline", "direct_kotlin"), ("baseline", "compatibility")):
            result["comparisons"][f"{left}_vs_{right}"] = {
                "first_difference": first_difference(traces[left], traces[right]),
                "recorded_channels": list(STATE_FIELDS),
            }
    (out / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(out), "comparisons": result["comparisons"],
                      "qualification": "unpassed"}, sort_keys=True))
    if result["comparisons"]["direct_kotlin_vs_compatibility"]["first_difference"]:
        raise SystemExit("staged candidate CCD routes differ")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--java", required=True)
    parser.add_argument("--javac", required=True)
    parser.add_argument("--jar", required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    baseline = Path(args.jar).resolve()
    if sha256(baseline) != manifest()["baseline_jar_sha256"]:
        raise ValueError("baseline JAR differs from the pinned artifact")
    capture(out, args.java, args.javac, baseline)


if __name__ == "__main__":
    main()
