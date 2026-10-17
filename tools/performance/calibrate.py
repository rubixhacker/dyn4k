#!/usr/bin/env python3
import argparse
import csv
import json
import tempfile
from pathlib import Path

from analyze import activity_status, bootstrap_ratio, warmup_status
from manifest import manifest, validate
from measure import HERE, MANIFEST_FILE, compile_harness, host_identity, jar_path, run_scenario, sha256


def rows(path):
    with Path(path).open(newline="") as stream:
        return list(csv.DictReader(stream))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--jar")
    parser.add_argument("--java", default="java")
    parser.add_argument("--javac", default="javac")
    parser.add_argument("--family", required=True, choices=tuple(manifest()["families"]))
    parser.add_argument("--variant", required=True)
    parser.add_argument("--size", required=True, choices=("small", "medium"))
    parser.add_argument("--hz", required=True, type=int, choices=(30, 60, 120))
    parser.add_argument("--warmup-seconds", type=int, default=120)
    parser.add_argument("--measurement-seconds", type=int, default=30)
    args = parser.parse_args()
    if args.warmup_seconds < 120 or args.measurement_seconds < 30:
        parser.error("calibration needs at least 120 warm-up and 30 measured seconds")
    if args.variant not in {s["variant"] for s in manifest()["scenarios"] if s["family"] == args.family}:
        parser.error("variant is absent from the manifest")
    validate(manifest())
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dyn4k-performance-calibration-") as folder:
        work = Path(folder)
        jar = jar_path(work, args.jar)
        classes = compile_harness(args.javac, jar, work)
        trials = []
        for repeat in range(1, 7):
            trials.append(run_scenario(args.java, classes, jar, out, args.family, args.variant,
                args.size, args.hz, args.measurement_seconds * args.hz, "timing", args.warmup_seconds * args.hz, repeat))
        pairs = []
        for index in range(0, 6, 2):
            left = rows(out / trials[index]["raw"])
            right = rows(out / trials[index + 1]["raw"])
            pairs.append({"a": trials[index]["raw"], "b": trials[index + 1]["raw"],
                          "median": bootstrap_ratio(left, right, args.hz, "median"),
                          "p99": bootstrap_ratio(left, right, args.hz, "p99"),
                          "total": bootstrap_ratio(left, right, args.hz, "total")})
        warmup = [warmup_status(rows(out / trial["warmup_raw"]), args.hz) for trial in trials]
        body_count = manifest()["families"][args.family][args.size]
        activity = [activity_status(rows(out / trial["raw"]), args.family, args.variant, body_count, args.hz) for trial in trials]
        report = {"schema": 1, "qualification": "method_calibration_only", "source_commit": manifest()["source_commit"],
                  "baseline_jar_sha256": sha256(jar), "manifest_sha256": sha256(MANIFEST_FILE),
                  "harness_sha256": sha256(HERE / "BaselinePilot.java"), "host": host_identity(args.java),
                  "scenario": {"family": args.family, "variant": args.variant, "size": args.size, "hz": args.hz},
                  "warmup_status": warmup, "activity_status": activity, "trials": trials, "unchanged_baseline_pairs": pairs,
                  "noise_bound": {metric: max(abs(pair[metric][edge] - 1.0) for pair in pairs for edge in ("lower_95", "upper_95"))
                                  for metric in ("median", "p99", "total")}}
        (out / "calibration.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"output": str(out), "warmup_status": warmup, "activity_status": activity,
                          "noise_bound": report["noise_bound"]}))


if __name__ == "__main__":
    main()
