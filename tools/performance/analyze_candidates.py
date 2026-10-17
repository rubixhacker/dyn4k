#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict
from pathlib import Path

from analyze import bootstrap_ratio, samples
from measure import sha256


def read_archive(path):
    root = Path(path)
    evidence = json.loads((root / "evidence.json").read_text())
    for item in evidence["results"]:
        for name, digest in ((item["raw"], item["raw_sha256"]),
                             (item["warmup_raw"], item["warmup_sha256"])):
            if sha256(root / name) != digest:
                raise ValueError(f"raw checksum mismatch: {root / name}")
    return root, evidence


def summarize_pilot(evidence):
    grouped = defaultdict(dict)
    for item in evidence["results"]:
        key = ".".join((item["family"], item["variant"], item["size"],
                        f"{item['hz']}hz", item["mode"], f"repeat{item['raw'].rsplit('r', 1)[-1].split('.')[0]}"))
        grouped[key][item["api"]] = {
            "median_step_ns": item["median_step_ns"],
            "p99_step_ns": item["p99_step_ns"],
            "total_allocation_bytes": item["total_allocation_bytes"],
            "peak_rss_delta_bytes_diagnostic": item["peak_rss_delta_bytes"],
            "activity": item["activity_status"],
            "warmup": item["warmup_status"],
            "process_pid": item["process_pid"],
            "state_checksum_sha256": item["state_checksum_sha256"],
        }
    return dict(sorted(grouped.items()))


def exploratory_intervals(root, evidence):
    grouped = defaultdict(dict)
    for item in evidence["results"]:
        if item.get("mode") != "timing":
            continue
        key = (item["family"], item["variant"], item["size"], item["hz"])
        grouped[key][item["api"]] = item
    output = {}
    for key, routes in grouped.items():
        if set(routes) != {"baseline", "direct_kotlin", "compatibility"}:
            continue
        baseline = samples(root / routes["baseline"]["raw"])
        case = ".".join((key[0], key[1], key[2], f"{key[3]}hz"))
        output[case] = {}
        for api in ("direct_kotlin", "compatibility"):
            candidate = samples(root / routes[api]["raw"])
            output[case][api] = {
                metric: bootstrap_ratio(baseline, candidate, key[3], metric)
                for metric in ("median", "p99", "total")
            }
            output[case][api]["activity"] = routes[api]["activity_status"]
            output[case][api]["warmup"] = routes[api]["warmup_status"]
            output[case][api]["qualification"] = "unpassed_short_warmup_and_uncalibrated_host"
        direct = samples(root / routes["direct_kotlin"]["raw"])
        shim = samples(root / routes["compatibility"]["raw"])
        output[case]["compatibility_vs_direct"] = {
            metric: bootstrap_ratio(direct, shim, key[3], metric)
            for metric in ("median", "p99", "total")
        }
        output[case]["compatibility_vs_direct"]["qualification"] = (
            "unpassed_short_warmup_and_uncalibrated_host")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", required=True)
    parser.add_argument("--noise")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root, evidence = read_archive(args.pilot)
    result = {"schema": 1, "qualification": "unpassed", "pilot": summarize_pilot(evidence),
              "pilot_runs": len(evidence["results"]), "pilot_failures": evidence["failures"],
              "memory_attribution": "unvalidated", "reference_environment": "unavailable"}
    if args.noise:
        noise_root, noise_evidence = read_archive(args.noise)
        result["short_window_intervals"] = exploratory_intervals(noise_root, noise_evidence)
        result["noise_runs"] = len(noise_evidence["results"])
        result["noise_failures"] = noise_evidence["failures"]
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"pilot_runs": result["pilot_runs"],
                      "short_window_cases": len(result.get("short_window_intervals", {})),
                      "qualification": "unpassed"}))


if __name__ == "__main__":
    main()
