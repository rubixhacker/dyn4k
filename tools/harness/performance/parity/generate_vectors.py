#!/usr/bin/env python3
"""Regenerate the Kotlin parity fixtures for the performance port.

Provenance
----------
The recorded values were produced by the Python implementation in `tools/performance`
at git revision `df640f26be0a61d8db5c6e7624114595aebf379a` (the checkout used when this
port was made). Every value written here was printed by that Python code; nothing was
computed by the Kotlin port and copied back.

Output
------
`stdout` is JSON. Two Kotlin test fixtures are derived from it:

* `src/commonTest/.../PerformanceVectors.kt` holds the JSON itself, base64 encoded in
  chunks so no literal exceeds the JVM class-file constant-pool limit.
* `src/commonTest/.../CheckedInManifest.kt` and `CheckedInCcdFixture.kt` hold the
  checked-in `docs/research/*.json` bytes, so the frozen manifest digest can be replayed
  without filesystem access.

Usage
-----
    python3 tools/harness/performance/parity/generate_vectors.py > vectors.json

then base64 the text, split it at 60000 characters, and emit the chunks as a `listOf` in
`PerformanceVectors.kt`.

Re-running this script reproduces every recorded value. The absolute scratch paths it
records (staging roots and raw file names) come from a fresh `mkdtemp` each run, so two
runs differ only in that directory; normalise `/tmp/dyn4k-vectors-*` to compare them.
"""

import csv
import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path("/var/home/stewart/Workspace/dyn4k")
PERF = ROOT / "tools" / "performance"
sys.path.insert(0, str(PERF))

import analyze
import analyze_candidates
import candidate_pilot
import candidate_runner
import host_capacity_control
import manifest as manifest_module
import measure
import reference_study
import stress_monitor
import sustained_archive

TEMP = Path(tempfile.mkdtemp(prefix="dyn4k-vectors-"))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def csv_text(fields, rows):
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(fields)
    writer.writerows(rows)
    return stream.getvalue()


_counter = [0]


def temp_csv(fields, rows, name=None):
    _counter[0] += 1
    path = TEMP / (name or f"raw-{_counter[0]}.csv")
    path.write_text(csv_text(fields, rows))
    return path


def error_of(call):
    try:
        call()
    except Exception as exc:  # noqa: BLE001 - the vector records the message
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


STEP_FIELDS = list(sustained_archive.STEP_FIELDS)
ACTIVITY_FIELDS = ["contact_begins", "toi_events", "awake_count", "active_contact_pairs",
                   "active_contact_points", "linear_speed_sum_m_per_s", "joint_count",
                   "angular_speed_sum_rad_per_s"]
out = {}


def step_row(**overrides):
    row = {"step": 0, "elapsed_ns": 1000, "mutation_ns": 0, "lateness_ns": 0,
           "allocation_bytes": -1, "heap_used_bytes": 1000, "rss_bytes": 2000,
           "rss_delta_bytes": 100, "body_count": 100, "joint_count": 0,
           "awake_count": 95, "linear_speed_sum_m_per_s": 95,
           "angular_speed_sum_rad_per_s": 0, "contact_begins": 0, "contact_ends": 0,
           "toi_events": 0, "broadphase_candidates": 0, "active_contact_pairs": 0,
           "active_contact_points": 0}
    row.update(overrides)
    return row


def step_table(count, **overrides):
    rows = []
    for step in range(count):
        row = step_row()
        row["step"] = step
        row["elapsed_ns"] = 1000 + step
        row.update(overrides)
        rows.append([row[field] for field in STEP_FIELDS])
    return rows


# ================================================================ manifest
policy = manifest_module.manifest()
out["manifest"] = {
    "canonical_sha256": digest(policy),
    "version": policy["version"],
    "target_count": len(policy["targets"]),
    "targets": policy["targets"],
    "runtime_row_count": len(policy["runtime_rows"]),
    "family_count": len(policy["families"]),
    "rates_hz": policy["rates_hz"],
    "api_surfaces": policy["api_surfaces"],
    "scenario_count": len(policy["scenarios"]),
    "scenario_ids_sha256": hashlib.sha256(
        "\n".join(item["id"] for item in policy["scenarios"]).encode()).hexdigest(),
    "runtime_row_ids_sha256": hashlib.sha256(
        "\n".join(row["id"] for row in policy["runtime_rows"]).encode()).hexdigest(),
    "first_row": policy["runtime_rows"][0],
    "last_row": policy["runtime_rows"][-1],
    "budgets_sha256": digest(policy["budgets"]),
    "sustained_sha256": digest(policy["sustained"]),
    "measurement_method_sha256": digest(policy["measurement_method"]),
    "fixture_sha256": digest(policy["fixture"]),
    "families_sha256": digest(policy["families"]),
    "joint_modes_sha256": digest(policy["joint_modes"]),
    "joint_parameters_sha256": digest(policy["joint_parameters"]),
}

out["ccd_fixture_revision"] = manifest_module.ccd_fixture_revision()
out["ccd_fixture_revision_sha256"] = digest(manifest_module.ccd_fixture_revision())

validate_manifest = {}
for name, mutate in (
    ("generated", lambda value: None),
    ("missing_row", lambda value: value["runtime_rows"].pop()),
    ("changed_minimum", lambda value: value["runtime_rows"][0].update(
        minimum_policy="Java 11")),
    ("changed_scenarios", lambda value: value.update(scenarios=value["scenarios"][:-1])),
    ("version", lambda value: value.update(version=2)),
    ("reordered_rows", lambda value: value["runtime_rows"].reverse()),
    ("changed_budget", lambda value: value["budgets"]["jvm_vs_baseline"].update(
        median_ratio_max=2.0)),
    ("unknown_environment", lambda value: value["runtime_rows"][0].update(
        environment_status="provisional")),
    ("available_without_identity", lambda value: value["runtime_rows"][0].update(
        environment_status="available")),
    ("available_with_identity", lambda value: value["runtime_rows"][0].update(
        environment_status="available", representative_hardware="host",
        runtime_version="1.0", abi="x")),
    ("changed_targets", lambda value: value["targets"].pop()),
):
    candidate = json.loads(json.dumps(policy))
    mutate(candidate)
    validate_manifest[name] = error_of(lambda value=candidate: manifest_module.validate(value))
out["validate_manifest"] = validate_manifest

# ================================================================ analyze
out["percentile"] = {
    "values": [5, 1, 4, 2, 3],
    "results": {
        "0.5": analyze.percentile([5, 1, 4, 2, 3], 0.5),
        "0.99": analyze.percentile([5, 1, 4, 2, 3], 0.99),
        "0.025": analyze.percentile([5, 1, 4, 2, 3], 0.025),
        "0.975": analyze.percentile([5, 1, 4, 2, 3], 0.975),
        "1.0": analyze.percentile([5, 1, 4, 2, 3], 1.0),
        "0.0": analyze.percentile([5, 1, 4, 2, 3], 0.0),
        "single": analyze.percentile([42], 0.99),
    },
}

warm_cases = {
    "short": ([1000] * 60, 60),
    "converged": ([1000] * (30 * 60 * 4), 60),
    "drift": ([1000] * (30 * 60 * 3) + [2000] * (30 * 60 * 3), 60),
    "zero_center": ([0] * (30 * 60 * 4), 60),
    "noisy": ([1000 + (index % 7) * 40 for index in range(30 * 60 * 5)], 60),
    "hz_120": ([1000] * (30 * 120 * 4), 120),
    "hz_30_short": ([1000] * (30 * 30 * 3), 30),
}


def runs(values):
    """Compact run-length encoding of an integer sequence."""
    encoded = []
    for value in values:
        if encoded and encoded[-1][0] == value:
            encoded[-1][1] += 1
        else:
            encoded.append([value, 1])
    return encoded


out["warmup_status"] = {
    name: {"runs": runs(values), "length": len(values), "hz": hz,
           "status": analyze.warmup_status(
               [{"elapsed_ns": str(value)} for value in values], hz)}
    for name, (values, hz) in warm_cases.items()}

activity_cases = []


def activity(name, family, variant, count, hz, rows):
    dict_rows = [dict(zip(STEP_FIELDS, [str(value) for value in row])) for row in rows]
    watched = [STEP_FIELDS.index(field) for field in ACTIVITY_FIELDS]
    assert all([row[index] for index in watched] == [rows[0][index] for index in watched]
               for row in rows), name
    activity_cases.append({"name": name, "family": family, "variant": variant,
                           "count": count, "hz": hz, "row_count": len(rows),
                           "row": [str(rows[0][STEP_FIELDS.index(field)])
                                   for field in ACTIVITY_FIELDS],
                           "status": analyze.activity_status(dict_rows, family, variant,
                                                             count, hz)})


def one(**overrides):
    row = step_row(**overrides)
    return [[row[field] for field in STEP_FIELDS]]


activity("separated_valid", "separated", "default", 100, 60,
         one(linear_speed_sum_m_per_s=60, awake_count=90))
activity("separated_slow", "separated", "default", 100, 60,
         one(linear_speed_sum_m_per_s=59, awake_count=90))
activity("separated_contacts", "separated", "default", 100, 60,
         one(linear_speed_sum_m_per_s=60, contact_begins=1))
activity("pile_valid", "pile", "default", 100, 60,
         one(contact_begins=3, active_contact_pairs=4, active_contact_points=8))
activity("pile_no_pairs", "pile", "default", 100, 60,
         one(contact_begins=3, active_contact_pairs=0, active_contact_points=8))
activity("joint_valid", "joint", "mixed_all_types", 10, 60,
         one(awake_count=9, joint_count=10, angular_speed_sum_rad_per_s="0.02"))
activity("joint_at_threshold", "joint", "mixed_all_types", 10, 60,
         one(awake_count=9, joint_count=10, angular_speed_sum_rad_per_s="0.01"))
activity("ccd_valid", "ccd", "default", 27, 60,
         one(toi_events=2, contact_begins=1, active_contact_pairs=1))
activity("ccd_no_toi", "ccd", "default", 27, 60,
         one(toi_events=0, contact_begins=1, active_contact_pairs=1))
activity("lifecycle_settle_valid", "lifecycle", "settle", 1000, 60,
         step_table(30 * 60, awake_count=100))
activity("lifecycle_settle_short", "lifecycle", "settle", 1000, 60,
         step_table(30 * 60 - 1, awake_count=100))
activity("lifecycle_wake_valid", "lifecycle", "wake", 1000, 60,
         step_table(30 * 60, awake_count=5, contact_begins=1))
activity("lifecycle_replace_valid", "lifecycle", "replace", 1000, 60,
         step_table(2 * 60, contact_begins=1))
activity("lifecycle_replace_short", "lifecycle", "replace", 1000, 60,
         step_table(2 * 60 - 1, contact_begins=1))
activity("unknown_family", "nonsense", "default", 10, 60, one())
out["activity_status"] = {"fields": ACTIVITY_FIELDS, "cases": activity_cases}


def elapsed_series(count, base, step_mod=17):
    return [{"elapsed_ns": str(base + (index % step_mod))} for index in range(count)]


bootstrap = []


def bootstrap_case(name, a, b, hz, metric, draws, seed=17017):
    bootstrap.append({
        "name": name, "a": runs([int(row["elapsed_ns"]) for row in a]),
        "b": runs([int(row["elapsed_ns"]) for row in b]), "length": len(a),
        "hz": hz, "metric": metric, "draws": draws, "seed": seed,
        "result": analyze.bootstrap_ratio(a, b, hz, metric=metric, draws=draws, seed=seed)})


bootstrap_case("identical_median", elapsed_series(30 * 60, 1000),
               elapsed_series(30 * 60, 1000), 60, "median", 200)
bootstrap_case("identical_p99", elapsed_series(30 * 60, 1000),
               elapsed_series(30 * 60, 1000), 60, "p99", 200)
bootstrap_case("identical_total", elapsed_series(30 * 60, 1000),
               elapsed_series(30 * 60, 1000), 60, "total", 200)
bootstrap_case("double_median", elapsed_series(30 * 60, 1000),
               elapsed_series(30 * 60, 2000), 60, "median", 200)
bootstrap_case("noisy_median", elapsed_series(60 * 60, 1000, 31),
               elapsed_series(60 * 60, 1300, 47), 60, "median", 2000)
bootstrap_case("noisy_p99", elapsed_series(60 * 60, 1000, 31),
               elapsed_series(60 * 60, 1300, 47), 60, "p99", 2000)
bootstrap_case("noisy_total", elapsed_series(60 * 60, 1000, 31),
               elapsed_series(60 * 60, 1300, 47), 60, "total", 2000)
bootstrap_case("hz_120", elapsed_series(30 * 120, 500, 13),
               elapsed_series(30 * 120, 700, 29), 120, "median", 500)
bootstrap_case("three_blocks", elapsed_series(31 * 60, 700, 11),
               elapsed_series(31 * 60, 900, 23), 60, "p99", 250)
out["bootstrap_ratio"] = bootstrap

out["bootstrap_errors"] = {
    "short": error_of(lambda: analyze.bootstrap_ratio(
        elapsed_series(30, 1), elapsed_series(30, 1), 60)),
    "unequal": error_of(lambda: analyze.bootstrap_ratio(
        elapsed_series(31 * 60, 1), elapsed_series(31 * 60, 2), 60)),
    "partial_block": error_of(lambda: analyze.bootstrap_ratio(
        elapsed_series(30 * 60 + 1, 1), elapsed_series(30 * 60 + 1, 1), 60)),
    "unknown_metric": error_of(lambda: analyze.bootstrap_ratio(
        elapsed_series(30 * 60, 1), elapsed_series(30 * 60, 1), 60, metric="nope")),
    "nonpositive": error_of(lambda: analyze.bootstrap_ratio(
        elapsed_series(30 * 60, 0), elapsed_series(30 * 60, 1), 60)),
}

plateau_cases = {
    "growth": [{"heap_after_collection_bytes": str(1000 + cycle * 100),
                "collection_count": str(cycle)} for cycle in range(100)],
    "stable": [{"heap_after_collection_bytes": "1000", "collection_count": str(cycle)}
               for cycle in range(100)],
    "short": [{"heap_after_collection_bytes": "1000", "collection_count": str(cycle)}
              for cycle in range(99)],
    "negative_heap": [{"heap_after_collection_bytes": "-1", "collection_count": str(cycle)}
                      for cycle in range(100)],
    "no_collection": [{"heap_after_collection_bytes": "1000", "collection_count": "5"}
                      for cycle in range(100)],
    "zero_early": [{"heap_after_collection_bytes": "0", "collection_count": str(cycle)}
                   for cycle in range(100)],
    "drift_at_limit": [{"heap_after_collection_bytes": "1000" if cycle < 40 else "1050",
                        "collection_count": str(cycle)} for cycle in range(100)],
}
out["plateau_status"] = {
    name: {"heap": [int(row["heap_after_collection_bytes"]) for row in rows],
           "collections": [int(row["collection_count"]) for row in rows],
           "status": analyze.plateau_status(rows)}
    for name, rows in plateau_cases.items()}

# ================================================================ measure
out["balanced_orders"] = [list(order) for order in measure.balanced_orders()]
out["pilot"] = [list(item) for item in measure.PILOT]


def validate(fields, rows, family, variant, size, hz, steps, mode):
    path = temp_csv(fields, rows)
    return error_of(lambda: measure.validate_csv(path, family, variant, size, hz, steps, mode))


validate_cases = {}
for name, args in {
    "ok_timing": (STEP_FIELDS, step_table(60), "separated", "default", "small", 60, 60, "timing"),
    "ok_allocation": (STEP_FIELDS, step_table(60, allocation_bytes=128), "separated", "default",
                      "small", 60, 60, "allocation"),
    "short": (STEP_FIELDS, step_table(59), "separated", "default", "small", 60, 60, "timing"),
    "body_count": (STEP_FIELDS, step_table(60, body_count=99), "separated", "default", "small",
                   60, 60, "timing"),
    "nonpositive_elapsed": (STEP_FIELDS, step_table(60, elapsed_ns=0), "separated", "default",
                            "small", 60, 60, "timing"),
    "mutation_over_elapsed": (STEP_FIELDS, step_table(60, mutation_ns=10_000), "separated",
                              "default", "small", 60, 60, "timing"),
    "negative_lateness": (STEP_FIELDS, step_table(60, lateness_ns=-1), "separated", "default",
                          "small", 60, 60, "timing"),
    "timing_allocation": (STEP_FIELDS, step_table(60, allocation_bytes=5), "separated",
                          "default", "small", 60, 60, "timing"),
    "negative_allocation": (STEP_FIELDS, step_table(60, allocation_bytes=-5), "separated",
                            "default", "small", 60, 60, "allocation"),
    "awake_count": (STEP_FIELDS, step_table(60, awake_count=101), "separated", "default",
                    "small", 60, 60, "timing"),
    "negative_toi": (STEP_FIELDS, step_table(60, toi_events=-1), "separated", "default", "small",
                     60, 60, "timing"),
    "unsampled_pairs": (STEP_FIELDS, step_table(60, broadphase_candidates=3), "separated",
                        "default", "small", 60, 60, "timing"),
    "negative_speed": (STEP_FIELDS, step_table(60, linear_speed_sum_m_per_s=-1), "separated",
                       "default", "small", 60, 60, "timing"),
    "joint_topology": (STEP_FIELDS, step_table(60, joint_count=2), "joint", "mixed_all_types",
                       "small", 60, 60, "timing"),
    "pile_body_count": (STEP_FIELDS, step_table(60, body_count=101), "pile", "default", "small",
                        60, 60, "timing"),
    "missing_channel": (STEP_FIELDS[:-1], [row[:-1] for row in step_table(60)], "separated",
                        "default", "small", 60, 60, "timing"),
}.items():
    validate_cases[name] = {"text": csv_text(*args[:2]), "args": list(args[2:]),
                            "result": validate(*args)}
reordered = step_table(60)
reordered[0], reordered[1] = reordered[1], reordered[0]
validate_cases["reordered"] = {
    "text": csv_text(STEP_FIELDS, reordered), "args": ["separated", "default", "small", 60, 60,
                                                       "timing"],
    "result": validate(STEP_FIELDS, reordered, "separated", "default", "small", 60, 60, "timing")}
monotonic = step_table(60)
monotonic[0][STEP_FIELDS.index("contact_begins")] = 4
monotonic[10][STEP_FIELDS.index("contact_begins")] = 2
validate_cases["nonmonotonic_contacts"] = {
    "text": csv_text(STEP_FIELDS, monotonic),
    "args": ["separated", "default", "small", 60, 60, "timing"],
    "result": validate(STEP_FIELDS, monotonic, "separated", "default", "small", 60, 60,
                       "timing")}
sampled = step_table(60)
sampled[1][STEP_FIELDS.index("active_contact_pairs")] = 3
validate_cases["sampled_pairs_in_wrong_step"] = {
    "text": csv_text(STEP_FIELDS, sampled),
    "args": ["separated", "default", "small", 60, 60, "timing"],
    "result": validate(STEP_FIELDS, sampled, "separated", "default", "small", 60, 60,
                       "timing")}
out["validate_csv"] = {"fields": STEP_FIELDS, "cases": validate_cases}

summary_cases = []


def summary_case(name, rows, hz, mode):
    path = temp_csv(STEP_FIELDS, rows, f"summary-{name}.csv")
    with path.open(newline="") as stream:
        parsed = list(csv.DictReader(stream))
    summary_cases.append({"name": name, "hz": hz, "mode": mode,
                          "text": csv_text(STEP_FIELDS, rows),
                          "result": measure.summary(parsed, hz, mode),
                          "step_summary": sustained_archive.step_summary(parsed, mode, hz)})


rows_600 = step_table(600)
for index, row in enumerate(rows_600):
    row[STEP_FIELDS.index("lateness_ns")] = 100 + index % 3
    row[STEP_FIELDS.index("mutation_ns")] = 50 if index % 10 == 0 else 0
summary_case("timing_600", rows_600, 60, "timing")
summary_case("allocation_600", step_table(600, allocation_bytes=256), 60, "allocation")
summary_case("timing_short", step_table(30), 60, "timing")
summary_case("memory_600", step_table(600, allocation_bytes=0), 60, "memory")
event_rows = step_table(400)
for index, row in enumerate(event_rows):
    row[STEP_FIELDS.index("mutation_ns")] = 900 if index % 40 == 0 else 0
summary_case("event_only_partial", event_rows, 60, "timing")
overrun = step_table(120)
for index, row in enumerate(overrun):
    row[STEP_FIELDS.index("elapsed_ns")] = 20_000_000 if index % 5 == 0 else 1000
summary_case("overruns", overrun, 60, "timing")
out["summary"] = {"fields": STEP_FIELDS, "cases": summary_cases}

# ================================================================ candidate_runner
paths_text = ("direct_kotlin\t/root/stage/core.jar:/root/stage/api.jar\n"
              "compatibility\t/root/stage/core.jar\n")
paths_file = TEMP / "paths.tsv"
paths_file.write_text(paths_text)
out["read_paths"] = {
    "text": paths_text,
    "result": {route: [str(value) for value in values]
               for route, values in candidate_runner.read_paths(paths_file).items()},
}
out["read_paths_errors"] = {}
for name, text in (("one_row", "direct_kotlin\t/a\n"),
                   ("wrong_routes", "direct_kotlin\t/a\nbaseline\t/b\n"),
                   ("three_rows", "direct_kotlin\t/a\ncompatibility\t/b\nextra\t/c\n")):
    candidate = TEMP / f"paths-{name}.tsv"
    candidate.write_text(text)
    out["read_paths_errors"][name] = {"text": text,
                                      "result": error_of(
                                          lambda value=candidate:
                                          candidate_runner.read_paths(value))}

CORE = candidate_runner.CORE
API = candidate_runner.API


def route_case(root, route, paths):
    return error_of(lambda: candidate_runner.check_route(route, paths, root))


staging = TEMP / "staging"
(staging / CORE).parent.mkdir(parents=True, exist_ok=True)
(staging / API).parent.mkdir(parents=True, exist_ok=True)
(staging / CORE).write_bytes(b"core bytes")
(staging / API).write_bytes(b"api bytes")
core = staging / CORE
api = staging / API
upstream = staging / "dyn4j-6.0.0.jar"
upstream.write_bytes(b"upstream")
out["check_route"] = {
    "staging_root": str(staging),
    "core": str(core),
    "api": str(api),
    "cases": {
        "direct_ok": route_case(staging, "direct_kotlin", [str(api), str(core)]),
        "direct_missing_core": route_case(staging, "direct_kotlin", [str(core)]),
        "direct_duplicate_core": route_case(staging, "direct_kotlin",
                                            [str(core), str(core), str(api)]),
        "compatibility_ok": route_case(staging, "compatibility", [str(core)]),
        "compatibility_crossed": route_case(staging, "compatibility", [str(api), str(core)]),
        "unknown_route": route_case(staging, "baseline", [str(core)]),
        "outside_staging": route_case(staging, "compatibility",
                                      [str(core), "/elsewhere/core.jar"]),
        "upstream": route_case(staging, "compatibility", [str(core), str(upstream)]),
    },
}

expected = {str(core): hashlib.sha256(core.read_bytes()).hexdigest()}
verify_hashes = {"fresh": error_of(lambda: candidate_runner.verify_hashes(expected))}
core.write_bytes(b"changed")
verify_hashes["stale"] = error_of(lambda: candidate_runner.verify_hashes(expected))
core.write_bytes(b"core bytes")
verify_hashes["missing"] = error_of(
    lambda: candidate_runner.verify_hashes({str(TEMP / "absent.jar"): "0" * 64}))
out["verify_hashes"] = verify_hashes

# ================================================================ candidate_pilot
warmup_text = "#process_pid=42\n#route_marker=1\nwarmup_step,elapsed_ns\n0,5\n"
warmup_path = TEMP / "warmup.csv"
cleaned_cases = {}
for name, (api, pid) in {
    "candidate_ok": ("direct_kotlin", 42),
    "baseline_ok": ("baseline", 7),
    "wrong_pid": ("direct_kotlin", 43),
    "wrong_marker_route": ("compatibility", 42),
    "marker_on_baseline": ("baseline", 42),
}.items():
    warmup_path.write_text(warmup_text)
    try:
        metadata = candidate_pilot.clean_warmup(warmup_path, api, pid)
        cleaned_cases[name] = {"ok": True, "metadata": metadata,
                               "text": warmup_path.read_text()}
    except Exception as exc:  # noqa: BLE001
        cleaned_cases[name] = {"ok": False, "error": str(exc), "text": ""}
out["clean_warmup"] = {"input": warmup_text, "cases": cleaned_cases}

state_text = csv_text(list(candidate_pilot.STATE_FIELDS), [
    [99, 0, 95, 95, 0, 1, 1, 0, 3, 4, 8],
    [99, 0, 96, 96, 0, 2, 1, 0, 3, 4, 8],
])
state_path = TEMP / "state.csv"
state_path.write_text(state_text)
out["state_checksum"] = {"fields": list(candidate_pilot.STATE_FIELDS), "text": state_text,
                         "sha256": candidate_pilot.state_checksum(state_path)}

scenario_cases = {}
for name, names in (("default", []),
                    ("one", ["separated.default"]),
                    ("three", ["separated.default", "pile.default", "lifecycle.wake"]),
                    ("unknown", ["separated.nope"]),
                    ("ambiguous", ["default"])):
    try:
        scenario_cases[name] = {"names": names,
                                "value": [list(item) for item in
                                          candidate_pilot.select_scenarios(names)]}
    except Exception as exc:  # noqa: BLE001
        scenario_cases[name] = {"names": names, "error": str(exc)}
out["select_scenarios"] = scenario_cases

# ================================================================ analyze_candidates
pilot_evidence = {
    "results": [
        {"family": "separated", "variant": "default", "size": "small", "hz": 60,
         "mode": "timing", "api": api,
         "raw": f"separated.default.small.60hz.{api}.timing.r{repeat}.csv",
         "median_step_ns": 1000 + index, "p99_step_ns": 2000 + index,
         "total_allocation_bytes": None, "peak_rss_delta_bytes": 100,
         "activity_status": "valid", "warmup_status": "converged", "process_pid": 100 + index,
         "state_checksum_sha256": "a" * 64}
        for index, (api, repeat) in enumerate(
            [(api, repeat) for repeat in (1, 2) for api in
             ("baseline", "direct_kotlin", "compatibility")])
    ] + [
        {"family": "pile", "variant": "default", "size": "small", "hz": 60,
         "mode": "allocation", "api": "baseline",
         "raw": "pile.default.small.60hz.baseline.allocation.r1.csv",
         "median_step_ns": 5, "p99_step_ns": 9, "total_allocation_bytes": 256,
         "peak_rss_delta_bytes": 0, "activity_status": "valid",
         "warmup_status": "converged", "process_pid": 999,
         "state_checksum_sha256": "b" * 64},
    ],
}
out["summarize_pilot"] = {"evidence": pilot_evidence,
                          "result": analyze_candidates.summarize_pilot(pilot_evidence)}

# ================================================================ stress_monitor
out["stress_monitor_method"] = {
    system: stress_monitor.stress_monitor_method(system)
    for system in ("Linux", "Darwin", "Windows", "FreeBSD", "")
}
out["stress_monitor_errors"] = {
    "invalid_pids": [error_of(lambda pid=pid: stress_monitor.peak_rss_bytes(pid, "Linux"))
                     for pid in (0, -1, True, "123")],
    "unknown_system": error_of(lambda: stress_monitor.peak_rss_bytes(123, "FreeBSD")),
}

# ================================================================ sustained_archive
measurement_keys = sustained_archive.required_measurements(policy)
report_keys = sustained_archive.required_reports(policy)
noise_keys = sustained_archive.required_noise(policy)
plateau_keys = sustained_archive.required_plateaus(policy)
control_keys = sustained_archive.comparison_control_keys(policy)
out["required"] = {
    "measurement_count": len(measurement_keys),
    "measurement_sha256": hashlib.sha256(
        "\n".join(sorted("|".join(map(str, key)) for key in measurement_keys)).encode()).hexdigest(),
    "measurement_samples": ["|".join(map(str, key)) for key in
                            sorted(measurement_keys)[:2] + sorted(measurement_keys)[-2:]],
    "report_count": len(report_keys),
    "report_sha256": hashlib.sha256(
        "\n".join(sorted("|".join(map(str, key)) for key in report_keys)).encode()).hexdigest(),
    "report_samples": ["|".join(map(str, key)) for key in
                       sorted(report_keys)[:2] + sorted(report_keys)[-2:]],
    "noise_count": len(noise_keys),
    "noise_sha256": hashlib.sha256(
        "\n".join(sorted("|".join(map(str, key)) for key in noise_keys)).encode()).hexdigest(),
    "noise_samples": ["|".join(map(str, key)) for key in
                      sorted(noise_keys)[:2] + sorted(noise_keys)[-2:]],
    "plateau_count": len(plateau_keys),
    "plateau_sha256": hashlib.sha256(
        "\n".join(sorted("|".join(map(str, key)) for key in plateau_keys)).encode()).hexdigest(),
    "plateau_samples": ["|".join(map(str, key)) for key in
                        sorted(plateau_keys)[:2] + sorted(plateau_keys)[-2:]],
    "control_count": len(control_keys),
    "control_sha256": hashlib.sha256("\n".join(sorted(control_keys)).encode()).hexdigest(),
    "control_samples": sorted(control_keys)[:3] + sorted(control_keys)[-3:],
}

limits = {key: (1.05 if index % 2 else 1.10)
          for index, key in enumerate(sorted(control_keys))}
noise_lookup = sustained_archive.noise_limit_lookup(
    {"sustained_gate": {"noise_upper_ratio_max": limits}})
out["noise_limit_lookup"] = {
    "limits_sha256": hashlib.sha256(
        "\n".join(f"{key}={limits[key]}" for key in sorted(limits)).encode()).hexdigest(),
    "entry_count": len(noise_lookup),
    "sha256": hashlib.sha256("\n".join(
        f"{'|'.join(key)}={value}" for key, value in sorted(noise_lookup.items())
    ).encode()).hexdigest(),
    "samples": [{"key": list(key), "limit": value}
                for key, value in sorted(noise_lookup.items())[:3]],
}

out["command_prefix"] = {
    "tokens": {"runtime": "/r/java", "harness": "/h/harness.jar", "adapter": "/h/adapter.jar",
               "baseline": "/b/base.jar", "core": "/a/core.jar", "kotlin": "/a/kotlin.jar"},
    "template": ["{runtime}", "-Xmx256m", "-cp",
                 "{harness}:{adapter}:{baseline}:{core}:{kotlin}", "SyntheticHarness"],
    "result": [part.format_map({"runtime": "/r/java", "harness": "/h/harness.jar",
                                "adapter": "/h/adapter.jar", "baseline": "/b/base.jar",
                                "core": "/a/core.jar", "kotlin": "/a/kotlin.jar"})
               for part in ("{runtime}", "-Xmx256m", "-cp",
                            "{harness}:{adapter}:{baseline}:{core}:{kotlin}",
                            "SyntheticHarness")],
    "missing_token_template": ["{runtime}", "{unknown}"],
}

out["signature"] = {
    "key": b"trusted-test-key-for-synthetic-archive-12345".decode(),
    "record": {"b": 2, "a": [1, 2, {"z": None}], "nested": {"k": "v"}},
    "signature": sustained_archive.signature(
        {"b": 2, "a": [1, 2, {"z": None}], "nested": {"k": "v"}},
        b"trusted-test-key-for-synthetic-archive-12345"),
    "unsigned_signature": sustained_archive.signature(
        {"a": 1}, b"trusted-test-key-for-synthetic-archive-12345"),
}

interval_cases = []
for name, first, second, draws in (
        ("all_zero", [0, 0, 0], [0, 0, 0], 200),
        ("same", [100, 200, 300], [100, 200, 300], 200),
        ("double", [100, 200, 300], [200, 400, 600], 200),
        ("scaled", [5, 10, 15], [6, 11, 16], 2000)):
    interval_cases.append({"name": name, "first": first, "second": second, "draws": draws,
                           "result": sustained_archive.scalar_interval(first, second, draws)})
out["scalar_interval"] = interval_cases
out["scalar_interval_errors"] = {
    "length": error_of(lambda: sustained_archive.scalar_interval([1, 2], [1, 2], 10)),
    "negative": error_of(lambda: sustained_archive.scalar_interval([1, -2, 3], [1, 2, 3], 10)),
    "zero_baseline_positive": error_of(
        lambda: sustained_archive.scalar_interval([0, 0, 0], [1, 2, 3], 10)),
}

capture_items = [
    {"kind": "measure", "row_id": "jvm.java",
     "scenario_id": "separated.default.small.30hz.baseline", "mode": "timing", "repeat": 1},
    {"kind": "noise", "row_id": "js.node",
     "scenario_id": "separated.default.small.30hz.direct_kotlin", "mode": "memory",
     "repeat": 3, "side": "b"},
    {"kind": "plateau", "row_id": "jvm.java",
     "scenario_id": "lifecycle.replace.small.60hz.baseline"},
]
out["capture_key"] = [{"item": item, "key": list(sustained_archive.capture_key(item))}
                      for item in capture_items]
out["capture_key_unknown"] = error_of(
    lambda: sustained_archive.capture_key({"kind": "nonsense"}))

allocation_input = [{"elapsed_ns": "10", "allocation_bytes": "7"},
                    {"elapsed_ns": "20", "allocation_bytes": "9"}]
out["allocation_rows"] = {"input": allocation_input,
                          "result": sustained_archive.allocation_rows(allocation_input)}

# ================================================================ host_capacity_control
out["host_capacity"] = {
    "fields": sorted(host_capacity_control.FIELDS),
    "child_source": host_capacity_control.CHILD_SOURCE,
    "child_source_sha256": hashlib.sha256(
        host_capacity_control.CHILD_SOURCE.encode()).hexdigest(),
    "child_source_lines": len(host_capacity_control.CHILD_SOURCE.splitlines()),
    "signature": host_capacity_control.signature(
        {"pid": 1, "status": "observed"}, b"key-material-32-bytes-long-000000"),
    "encoding_exact": host_capacity_control.source_encoding(b"abc\n", b"abc\n"),
    "encoding_crlf": host_capacity_control.source_encoding(b"abc\r\ndef\r\n", b"abc\ndef\n"),
    "encoding_differs": error_of(
        lambda: host_capacity_control.source_encoding(b"zzz\n", b"abc\n")),
    "encoding_crlf_committed_has_crlf": error_of(
        lambda: host_capacity_control.source_encoding(b"abc\r\ndef\n", b"a\r\nb\n")),
}

# ================================================================ reference_study
out["reference_study"] = {
    "source_commit": reference_study.SOURCE_COMMIT,
    "version": reference_study.VERSION,
    "legacy_version": reference_study.LEGACY_VERSION,
    "phases": list(reference_study.PHASES),
    "identity_files": list(reference_study.IDENTITY_FILES),
    "raw_files": list(reference_study.RAW_FILES),
    "v3_raw_files": list(reference_study.V3_RAW_FILES),
    "pair_order": [list(item) for item in reference_study.PAIR_ORDER],
    "control_routes": reference_study.CONTROL_ROUTES,
    "control_keys": sorted(reference_study.CONTROL_KEYS),
    "capture_identity_keys": sorted(reference_study.CAPTURE_IDENTITY_KEYS),
    "capture_keys_v3": sorted(reference_study.capture_keys(reference_study.VERSION)),
    "capture_keys_v2": sorted(reference_study.capture_keys(reference_study.LEGACY_VERSION)),
    "raw_files_v3": list(reference_study.raw_files(reference_study.VERSION)),
    "raw_files_v2": list(reference_study.raw_files(reference_study.LEGACY_VERSION)),
    "raw_files_unknown": error_of(lambda: reference_study.raw_files("reference-study-v9")),
    "absolute_paths": {
        text: reference_study.absolute_source_path(text)
        for text in ("/abs/path", "rel/path", "", "C:\\perf\\probe.jar", "/", "a/../b",
                     "\\\\server\\share\\x")
    },
}
controls_for_digest = hashlib.sha256("\n".join(
    f"{key}={canonical(reference_study.controls_for(key))}"
    for key in sorted(control_keys)).encode()).hexdigest()
out["reference_study"]["controls_for_count"] = len(control_keys)
out["reference_study"]["controls_for_sha256"] = controls_for_digest
out["reference_study"]["controls_for_errors"] = {
    "jvm_outside_jvm": error_of(
        lambda: reference_study.controls_for(
            "jvm_vs_dyn4j|js.node|x|timing|median|full")),
    "unknown": error_of(
        lambda: reference_study.controls_for("nonsense|js.node|x|timing|median|full")),
}
out["reference_study"]["controls_for_samples"] = {
    key: reference_study.controls_for(key) for key in (
        "jvm_vs_dyn4j|jvm.java|separated.default.small.30hz.compatibility|timing|median|full",
        "shim_vs_direct|js.node|separated.default.small.30hz.compatibility|timing|median|full",
        "absolute_timing|js.node|separated.default.small.30hz.direct_kotlin|timing|p99|full",
        "absolute_memory|js.node|separated.default.small.30hz.direct_kotlin|memory|"
        "attributed_workload_peak_bytes|full",
    )
}

unique_cases = {}
for name, text in (("unique", '{"a": 1, "b": [1, {"c": null}]}'),
                   ("duplicate", '{"a": 1, "a": 2}'),
                   ("nested_duplicate", '{"a": {"b": 1, "b": 2}}')):
    unique_cases[name] = {"text": text,
                          "result": error_of(lambda text=text: json.loads(
                              text, object_pairs_hook=reference_study.unique_object))}
out["reference_study"]["unique_object"] = unique_cases

print(json.dumps(out, indent=1, sort_keys=True))
