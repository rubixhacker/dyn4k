#!/usr/bin/env python3
import argparse
import csv
import json
import math
import statistics
from pathlib import Path

from analyze import activity_status, plateau_status, warmup_status
from analyze_candidates import exploratory_intervals, summarize_pilot
from candidate_pilot import state_checksum
from manifest import manifest
from measure import PILOT, sha256, summary, validate_csv


REQUIRED_GROUPS = ("pilot", "noise", "memory", "plateau")
OPTIONAL_GROUPS = ("discovery-plateau-v0",)
SUMMARY_FIELDS = (
    "samples", "median_step_ns", "p95_step_ns", "p99_step_ns", "max_step_ns",
    "compute_seconds_per_simulated_second", "total_allocation_bytes", "max_lateness_ns",
    "overrun_steps", "last_contact_begins", "last_contact_ends", "last_toi_events",
    "last_awake", "last_linear_speed_sum_m_per_s", "last_angular_speed_sum_rad_per_s",
    "peak_broadphase_candidates", "peak_active_contact_pairs", "peak_active_contact_points",
    "peak_rss_delta_bytes", "event_only_full", "event_only_final_minute",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rows_at(path, fields, label):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == fields, f"{label} CSV header differs")
        rows = list(reader)
    require(rows and all(None not in row and all(value is not None for value in row.values())
                         for row in rows), f"{label} CSV row is incomplete")
    return rows


def warmup_rows(directory, item, plateau):
    fields = ["warmup_step", "elapsed_ns"] + ([] if plateau else ["rss_bytes"])
    rows = rows_at(directory / item["warmup_raw"], fields, "warm-up")
    require(len(rows) == item["warmup_steps"] and
            [int(row["warmup_step"]) for row in rows] == list(range(len(rows))) and
            all(int(row["elapsed_ns"]) > 0 for row in rows), "warm-up samples differ")
    if not plateau:
        if item["mode"] == "memory":
            require(all(int(row["rss_bytes"]) >= 0 for row in rows),
                    "warm-up RSS channel differs")
        else:
            require(all(int(row["rss_bytes"]) == -1 for row in rows),
                    "warm-up RSS channel differs")
    require(warmup_status(rows, 60 if plateau else item["hz"]) == item["warmup_status"],
            "warmup_status differs")
    return rows


def verify_step_result(directory, item):
    family, variant, size = item["family"], item["variant"], item["size"]
    hz, mode = item["hz"], item["mode"]
    require(item["workload_id"] == f"{family}.{variant}.{size}.{hz}hz.{item['api']}",
            "workload_id differs")
    require(any(case["family"] == family and case["variant"] == variant
                for case in manifest()["scenarios"]), "workload is not frozen")
    raw = directory / item["raw"]
    rows = validate_csv(raw, family, variant, size, hz, item["samples"], mode)
    require(all(int(row["rss_bytes"]) >= 0 and int(row["heap_used_bytes"]) >= 0 and
                int(row["rss_delta_bytes"]) == int(row["rss_bytes"]) - item["rss_empty_harness_bytes"]
                for row in rows), f"{item['raw']} measured memory channel differs")
    warm = warmup_rows(directory, item, False)
    derived = summary(rows, hz, mode)
    empty = item["rss_empty_harness_bytes"]
    constructed = item["rss_after_construction_bytes"]
    if empty >= 0:
        derived["peak_rss_delta_bytes"] = max(
            [derived["peak_rss_delta_bytes"], constructed - empty] +
            [int(row["rss_bytes"]) - empty for row in warm if int(row["rss_bytes"]) >= 0])
    for field in SUMMARY_FIELDS:
        require(item[field] == derived[field], f"{item['raw']} {field} differs")
    count = manifest()["families"][family][size]
    require(item["activity_status"] == activity_status(rows, family, variant, count, hz),
            f"{item['raw']} activity_status differs")
    require(item["activity_status"] != "invalid", f"{item['raw']} scene is inactive")
    require(item["state_checksum_sha256"] == state_checksum(raw),
            f"{item['raw']} state_checksum_sha256 differs")
    require(item["cold_first_step_ns"] == int(warm[0]["elapsed_ns"]),
            f"{item['raw']} cold_first_step_ns differs")
    if mode == "memory":
        require(item["retained_heap_world_alive_bytes"] >= 0 and
                item["retained_collection_count_delta"] > 0,
                f"{item['raw']} collection probe differs")
    else:
        require(item["retained_heap_world_alive_bytes"] == -1 and
                item["retained_collection_count_delta"] == -1,
                f"{item['raw']} collection probe differs")


def verify_plateau_result(directory, item):
    require(item["workload_id"] == f"lifecycle.replace.small.60hz.{item['api']}",
            "plateau workload differs")
    warmup_rows(directory, item, True)
    rows = rows_at(directory / item["raw"],
                   ["cycle", "heap_after_collection_bytes", "rss_after_collection_bytes",
                    "collection_count"], "plateau")
    require(len(rows) == item["cycles"] == 100 and
            [int(row["cycle"]) for row in rows] == list(range(100)),
            "plateau cycles differ")
    require(all(int(row["rss_after_collection_bytes"]) >= 0 for row in rows),
            "plateau RSS channel differs")
    early = statistics.median(int(row["heap_after_collection_bytes"]) for row in rows[20:40])
    late = statistics.median(int(row["heap_after_collection_bytes"]) for row in rows[80:100])
    drift = abs(late / early - 1.0) if early > 0 else math.inf
    require(item["plateau_status"] == plateau_status(rows) and drift <= 0.05,
            f"{item['raw']} plateau drift differs")
    if "heap_drift_fraction" in item:
        require(item["heap_drift_fraction"] == drift,
                f"{item['raw']} heap_drift_fraction differs")


def verify(root):
    root = Path(root)
    identity_file = root / "candidate-identity-at-pilot.json"
    identity = json.loads(identity_file.read_text())
    identity_hash = sha256(identity_file)
    counts = {}
    evidence_by_group = {}
    for name in REQUIRED_GROUPS + OPTIONAL_GROUPS:
        directory = root / name
        if name in OPTIONAL_GROUPS and not directory.exists():
            continue
        evidence = json.loads((directory / "evidence.json").read_text())
        evidence_by_group[name] = evidence
        require(evidence["candidate_identity_sha256"] == identity_hash,
                f"{name} uses a different candidate identity")
        require(evidence["candidate_identity"] == identity,
                f"{name} embedded identity differs")
        manifest_file = Path(__file__).resolve().parents[2] / "docs/research/performance-manifest-v1.json"
        require(evidence["qualification"] == "unpassed" and
                evidence["manifest_sha256"] == sha256(manifest_file),
                f"{name} manifest or qualification differs")
        if name not in OPTIONAL_GROUPS:
            require(len(evidence["results"]) == evidence["expected_runs"] and
                    not evidence["failures"], f"{name} has an incomplete or failed run")
            require(len({item["raw"] for item in evidence["results"]}) == len(evidence["results"]),
                    f"{name} repeats a raw record")
            routes = ("baseline", "direct_kotlin", "compatibility")
            if name == "pilot":
                expected = {(family, variant, api, mode) for family, variant in PILOT
                            for api in routes for mode in ("timing", "allocation")}
                observed = {(item["family"], item["variant"], item["api"], item["mode"])
                            for item in evidence["results"]}
                require(observed == expected and all(item["size"] == "small" and item["hz"] == 60 and
                            item["samples"] == 120 and item["warmup_steps"] == 60
                            for item in evidence["results"]), "pilot workload coverage differs")
            elif name in ("noise", "memory"):
                mode = "timing" if name == "noise" else "memory"
                seconds = 1800 if name == "noise" else 120
                warmup = 1800 if name == "noise" else 60
                require({item["api"] for item in evidence["results"]} == set(routes) and
                        all((item["family"], item["variant"], item["size"], item["hz"],
                             item["mode"], item["samples"], item["warmup_steps"]) ==
                            ("separated", "default", "small", 60, mode, seconds, warmup)
                            for item in evidence["results"]), f"{name} workload coverage differs")
            else:
                require({item["api"] for item in evidence["results"]} == set(routes) and
                        all(item["warmup_steps"] == 60 for item in evidence["results"]),
                        "plateau route coverage differs")
        for item in evidence["results"]:
            require(Path(item["raw"]).name == item["raw"] and
                    Path(item["warmup_raw"]).name == item["warmup_raw"],
                    f"{name} has an invalid raw path")
            require(sha256(directory / item["raw"]) == item["raw_sha256"],
                    f"{name} measured CSV checksum differs")
            require(sha256(directory / item["warmup_raw"]) == item["warmup_sha256"],
                    f"{name} warm-up CSV checksum differs")
            if name in ("pilot", "noise", "memory"):
                verify_step_result(directory, item)
            elif name == "plateau":
                verify_plateau_result(directory, item)
        counts[name] = len(evidence["results"])
    require(counts["pilot"] == 36 and counts["noise"] == 3 and
            counts["memory"] == 3 and counts["plateau"] == 3,
            "required route coverage differs")
    provider = json.loads((root / "provider-identity.json").read_text())
    require(provider["candidate_identity_sha256"] == identity_hash,
            "provider proof uses a different candidate identity")
    core = next(path for path in identity["sha256"] if path.endswith("/dyn4k-core-jvm-0.1.0-alpha.1.jar"))
    api = next(path for path in identity["sha256"] if path.endswith("/dyn4k-jvm-0.1.0-alpha.1.jar"))
    require(provider["routes"]["direct_kotlin"]["origin"]["core"] == core and
            provider["routes"]["direct_kotlin"]["origin"]["api"] == api and
            provider["routes"]["compatibility"]["origin"]["core"] == core and
            provider["routes"]["compatibility"]["origin"]["api"] == "unavailable",
            "provider origins differ from staged routes")
    controls_dir = root / "negative-controls"
    controls = json.loads((controls_dir / "negative-controls.json").read_text())
    require(controls["candidate_identity_sha256"] == identity_hash and
            len(controls["controls"]) == 6 and
            all(item["status"] == "rejected_as_expected" for item in controls["controls"].values()),
            "negative controls are incomplete")
    require(sha256(controls_dir / "synthetic-empty-scene.csv") == controls["synthetic_empty_sha256"] and
            sha256(controls_dir / "synthetic-inactive-scene.csv") == controls["synthetic_inactive_sha256"],
            "negative-control CSV checksum differs")
    analysis = json.loads((root / "analysis.json").read_text())
    require(analysis["qualification"] == "unpassed" and
            analysis["pilot_runs"] == counts["pilot"] and analysis["noise_runs"] == counts["noise"] and
            analysis["pilot"] == summarize_pilot(evidence_by_group["pilot"]) and
            analysis["short_window_intervals"] == exploratory_intervals(root / "noise", evidence_by_group["noise"]),
            "analysis index differs from raw records")
    return {"identity_sha256": identity_hash, "runs": counts,
            "negative_controls": len(controls["controls"]), "qualification": "unpassed"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive")
    args = parser.parse_args()
    print(json.dumps(verify(args.archive), sort_keys=True))


if __name__ == "__main__":
    main()
