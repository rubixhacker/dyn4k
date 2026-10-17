#!/usr/bin/env python3
import argparse
import csv
import json
import statistics
import tempfile
from pathlib import Path

from analyze import activity_status, warmup_status
from manifest import manifest, validate
from measure import HERE, MANIFEST_FILE, compile_harness, host_identity, jar_path, run_scenario, sha256


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
    parser.add_argument("--warmup-seconds", type=int, default=600)
    args = parser.parse_args()
    if not 120 <= args.warmup_seconds <= 600:
        parser.error("warm-up must be between 120 and 600 seconds")
    if args.variant not in {item["variant"] for item in manifest()["scenarios"] if item["family"] == args.family}:
        parser.error("variant is absent from manifest")
    validate(manifest())
    if json.loads(MANIFEST_FILE.read_text()) != manifest():
        raise ValueError("checked-in manifest differs from generator")
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dyn4k-warmup-probe-") as folder:
        work = Path(folder)
        jar = jar_path(work, args.jar)
        classes = compile_harness(args.javac, jar, work)
        result = run_scenario(args.java, classes, jar, out, args.family, args.variant, args.size,
                              args.hz, 30 * args.hz, "timing", args.warmup_seconds * args.hz, 1)
        with (out / result["warmup_raw"]).open(newline="") as stream:
            warm = list(csv.DictReader(stream))
        with (out / result["raw"]).open(newline="") as stream:
            measured = list(csv.DictReader(stream))
        window = 30 * args.hz
        medians = [statistics.median(int(row["elapsed_ns"]) for row in warm[i:i + window])
                   for i in range(0, len(warm), window)]
        report = {"schema": 1, "qualification": "warmup_probe_only", "baseline_jar_sha256": sha256(jar),
                  "manifest_sha256": sha256(MANIFEST_FILE), "harness_sha256": sha256(HERE / "BaselinePilot.java"),
                  "host": host_identity(args.java), "result": result,
                  "warmup_window_medians_ns": medians, "warmup_status": warmup_status(warm, args.hz),
                  "activity_status": activity_status(measured, args.family, args.variant,
                                                     manifest()["families"][args.family][args.size], args.hz)}
        (out / "warmup-probe.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"warmup_status": report["warmup_status"], "activity_status": report["activity_status"]}))


if __name__ == "__main__":
    main()
