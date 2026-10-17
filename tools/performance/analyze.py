#!/usr/bin/env python3
import argparse
import csv
import json
import math
import random
import statistics
from pathlib import Path

from manifest import manifest


def samples(path):
    with Path(path).open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"empty sample file: {path}")
    return rows


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def warmup_status(rows, hz):
    window = 30 * hz
    if len(rows) < 4 * window:
        return "unvalidated"
    medians = [statistics.median(int(row["elapsed_ns"]) for row in rows[i:i + window])
               for i in range(0, len(rows) - window + 1, window)]
    latest = medians[-3:]
    center = statistics.median(latest)
    if center <= 0:
        return "invalid"
    return "converged" if max(abs(item / center - 1.0) for item in latest) <= 0.05 else "not_converged"


def activity_status(rows, family, variant, count, hz):
    first = rows[0]
    last = rows[-1]
    contacts = int(last["contact_begins"]) - int(first["contact_begins"])
    toi = int(last["toi_events"]) - int(first["toi_events"])
    awake = int(last["awake_count"])
    peak_pairs = max(int(row["active_contact_pairs"]) for row in rows)
    peak_points = max(int(row["active_contact_points"]) for row in rows)
    if family == "separated":
        return "valid" if contacts == 0 and awake >= math.ceil(0.9 * count) and float(last["linear_speed_sum_m_per_s"]) >= 0.6 * count else "invalid"
    if family == "pile":
        return "valid" if contacts > 0 and peak_pairs > 0 and peak_points > 0 else "invalid"
    if family == "joint":
        return "valid" if awake >= math.ceil(0.8 * count) and int(last["joint_count"]) == count and float(last["angular_speed_sum_rad_per_s"]) > 0.01 else "invalid"
    if family == "ccd":
        return "valid" if toi > 0 and contacts > 0 and peak_pairs > 0 else "invalid"
    if family == "lifecycle":
        if variant == "settle":
            return "valid" if len(rows) >= 30 * hz and awake <= math.floor(0.2 * count) else "unvalidated"
        if variant == "wake":
            return "valid" if len(rows) >= 30 * hz and awake > 0 and contacts > 0 else "unvalidated"
        if variant == "replace":
            return "valid" if len(rows) >= 2 * hz and contacts > 0 else "unvalidated"
    return "invalid"


def bootstrap_ratio(a, b, hz, metric="median", draws=2000, seed=17017):
    if len(a) != len(b) or len(a) < 30 * hz:
        raise ValueError("paired baseline series need at least 30 seconds and equal step counts")
    blocks_a = [[int(row["elapsed_ns"]) for row in a[i:i + hz]] for i in range(0, len(a), hz)]
    blocks_b = [[int(row["elapsed_ns"]) for row in b[i:i + hz]] for i in range(0, len(b), hz)]
    if any(len(block) != hz for block in blocks_a + blocks_b):
        raise ValueError("partial time block")
    rng = random.Random(seed)
    ratios = []
    for _ in range(draws):
        picks = [rng.randrange(len(blocks_a)) for _ in blocks_a]
        aa = [value for index in picks for value in blocks_a[index]]
        bb = [value for index in picks for value in blocks_b[index]]
        if metric == "median":
            numerator, denominator = statistics.median(bb), statistics.median(aa)
        elif metric == "p99":
            numerator, denominator = percentile(bb, 0.99), percentile(aa, 0.99)
        elif metric == "total":
            numerator, denominator = sum(bb), sum(aa)
        else:
            raise ValueError("unknown metric")
        if denominator <= 0:
            raise ValueError("nonpositive baseline")
        ratios.append(numerator / denominator)
    return {"lower_95": percentile(ratios, 0.025), "upper_95": percentile(ratios, 0.975), "draws": draws, "block_seconds": 1}


def plateau_status(rows):
    if len(rows) != 100:
        return "invalid"
    heap = [int(row["heap_after_collection_bytes"]) for row in rows]
    gc = [int(row["collection_count"]) for row in rows]
    if any(heap_value < 0 for heap_value in heap) or gc[-1] <= gc[0]:
        return "invalid"
    early = statistics.median(heap[20:40])
    late = statistics.median(heap[80:100])
    return "stable" if early > 0 and abs(late / early - 1.0) <= 0.05 else "not_stable"


def compare_pair(baseline, candidate, hz, metric, limit):
    first = samples(baseline)
    second = samples(candidate)
    if len(first) != 600 * hz or len(second) != 600 * hz:
        raise ValueError("full comparison requires exactly 600 simulated seconds per run")
    outputs = {}
    for label, a, b in (("full", first, second), ("final_minute", first[-60 * hz:], second[-60 * hz:])):
        interval = bootstrap_ratio(a, b, hz, metric)
        interval["limit"] = limit
        interval["ratio_result"] = "within_limit" if interval["upper_95"] <= limit else "inconclusive_or_exceeds_limit"
        interval["qualification"] = "unpassed_without_activity_warmup_memory_and_environment_checks"
        outputs[label] = interval
    return outputs


def report(directory):
    root = Path(directory)
    evidence = json.loads((root / "evidence.json").read_text())
    results = []
    for item in evidence["results"]:
        if item["mode"] != "timing":
            continue
        rows = samples(root / item["raw"])
        warm = samples(root / item["warmup_raw"])
        count = manifest()["families"][item["family"]][item["size"]]
        absolute = 1e9 / item["hz"] / 4
        results.append({
            "scenario": ".".join((item["family"], item["variant"], item["size"], str(item["hz"]))),
            "activity": activity_status(rows, item["family"], item["variant"], count, item["hz"]),
            "warmup": warmup_status(warm, item["hz"]),
            "pilot_p99_ns": item["p99_step_ns"],
            "absolute_p99_limit_ns": absolute,
            "pilot_p99_under_absolute_limit": item["p99_step_ns"] * 4 * item["hz"] <= 1_000_000_000,
            "qualified": False,
        })
    plateau = None
    if "plateau" in evidence:
        value = evidence["plateau"]
        plateau = {"status": plateau_status(samples(root / value["raw"])),
                   "warmup": warmup_status(samples(root / value["warmup_raw"]),
                                            int(value["raw"].split(".")[3].removesuffix("hz")))}
    return {"qualification": "unpassed", "scenarios": results, "plateau": plateau,
            "validated_probe": evidence["probe"]["timer_min_positive_ns"] > 0 and evidence["probe"]["controlled_allocated_bytes"] >= evidence["probe"]["controlled_payload_bytes"],
            "memory_attribution": "unvalidated"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_directory", nargs="?")
    parser.add_argument("--baseline")
    parser.add_argument("--candidate")
    parser.add_argument("--hz", type=int, choices=(30, 60, 120))
    parser.add_argument("--metric", choices=("median", "p99", "total"), default="median")
    parser.add_argument("--limit", type=float)
    args = parser.parse_args()
    if args.baseline or args.candidate:
        if not all((args.baseline, args.candidate, args.hz, args.limit)):
            parser.error("comparison needs baseline, candidate, hz, and limit")
        output = compare_pair(args.baseline, args.candidate, args.hz, args.metric, args.limit)
    elif args.evidence_directory:
        output = report(args.evidence_directory)
    else:
        parser.error("give evidence directory or comparison inputs")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
