#!/usr/bin/env python3
"""Regenerate the Kotlin parity fixtures (requires the deleted Python sources, see commit 9da52538^) for `warmup_probe.py`, `calibrate.py`, and
`ccd_route_trace.py`.

Provenance
----------
Each recorded report is written by the Python implementation itself. The scripts are driven
through `main()` / `capture()` with their host adapters patched (`run_scenario`, `jar_path`,
`compile_harness`, `host_identity`, `git`, `prepare`, `run_capture`, `verify_identity`), so
every value a test compares was computed by Python code, not transcribed.

`calibrate.bootstrap_ratio` is patched to `analyze.bootstrap_ratio` with 20 draws instead of
2000. That is the same function the tool calls; the smaller draw count only keeps the
generator fast. The noise bound is calibrate's own arithmetic over those intervals.

`tools/performance` is unchanged at git revision
`233edd085db9427e7feb19fd150d504b5d43be1b`.

Output
------
JSON on stdout, which becomes `LeafVectors.kt` in `src/commonTest`: base64 the text, split it
at 60000 characters, and emit the chunks as a `listOf`.
"""
import contextlib
import csv
import hashlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path("/var/home/stewart/Workspace/dyn4k")
PERF = ROOT / "tools" / "performance"
sys.path.insert(0, str(PERF))

import analyze
import calibrate
import candidate_pilot
import ccd_route_trace
import manifest as manifest_module
import sustained_archive
import warmup_probe

TEMP = Path(tempfile.mkdtemp(prefix="dyn4k-leaf-vectors-"))
STEP_FIELDS = list(sustained_archive.STEP_FIELDS)
STATE_FIELDS = list(candidate_pilot.STATE_FIELDS)
ROUTES = ("baseline", "direct_kotlin", "compatibility")

MANIFEST_SHA256 = hashlib.sha256((ROOT / "docs/research/performance-manifest-v1.json").read_bytes()).hexdigest()
HARNESS_SHA256 = hashlib.sha256((PERF / "BaselinePilot.java").read_bytes()).hexdigest()
JAR_TEXT = "synthetic pinned baseline jar"
BASELINE_JAR_SHA256 = hashlib.sha256(JAR_TEXT.encode()).hexdigest()
HOST = {"hostname": "synthetic-host", "machine": "x86_64", "system": "Linux",
        "release": "6.0.0-test", "os_version": "ID=test", "product_name": "Synthetic",
        "product_version": "1.0", "cpu_model": "Synthetic CPU", "ram_kib": 33554432,
        "java_version": "openjdk version \"21\"", "power_mode": None,
        "charging_state": None, "temperature_c": None, "throttling": None}

JAR = TEMP / "baseline.jar"
JAR.write_bytes(JAR_TEXT.encode())
CLASSES = TEMP / "classes"
CLASSES.mkdir()

out = {}


def csv_text(fields, rows):
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(fields)
    writer.writerows(rows)
    return stream.getvalue()


def digest_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def write_csv(path, fields, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(csv_text(fields, rows))


def step_row(step, hz, count, **overrides):
    sampled = step % hz == 0 or step == count - 1
    row = {"step": step, "elapsed_ns": 1000 + step % 23, "mutation_ns": 0, "lateness_ns": 0,
           "allocation_bytes": -1, "heap_used_bytes": 1000, "rss_bytes": -1,
           "rss_delta_bytes": 0, "body_count": 100, "joint_count": 0, "awake_count": 95,
           "linear_speed_sum_m_per_s": 95, "angular_speed_sum_rad_per_s": 0,
           "contact_begins": 0, "contact_ends": 0, "toi_events": 0,
           "broadphase_candidates": 7 if sampled else -1,
           "active_contact_pairs": 3 if sampled else -1,
           "active_contact_points": 5 if sampled else -1}
    row.update(overrides)
    return [row[field] for field in STEP_FIELDS]


def step_table(count, hz, elapsed_base=1000, elapsed_modulo=23, **overrides):
    rows = []
    for step in range(count):
        row = step_row(step, hz, count, **overrides)
        row[STEP_FIELDS.index("elapsed_ns")] = elapsed_base + step % elapsed_modulo
        row[STEP_FIELDS.index("contact_begins")] = step // hz
        rows.append(row)
    return rows


def warm_text(count, modulo=13, base=1000):
    lines = ["warmup_step,elapsed_ns,rss_bytes"]
    for step in range(count):
        lines.append(f"{step},{base + step % modulo},-1")
    return "\n".join(lines) + "\n"


def captured_error(prog, script, argv):
    """Runs a CLI with bad arguments and records the usage block and message `argparse` reports.

    `argv[0]` is the bare program name, which is what a real invocation supplies and what
    `argparse` derives its `prog` from.
    """
    stream = io.StringIO()
    with contextlib.redirect_stderr(stream):
        try:
            with mock.patch.object(sys, "argv", [prog] + argv):
                script.main()
        except SystemExit as exc:
            code = exc.code
        else:
            code = 0
    text = stream.getvalue()
    message = text.rsplit("error: ", 1)[-1].strip() if "error: " in text else text.strip()
    return {"exit_code": code, "stderr": text, "message": message}


out["calibrate_arguments"] = {
    "short_warmup": captured_error("calibrate.py", calibrate, ["--output", str(TEMP / "c1"), "--family", "pile",
                                               "--variant", "default", "--size", "small",
                                               "--hz", "60", "--warmup-seconds", "10"]),
    "short_measurement": captured_error("calibrate.py", calibrate, ["--output", str(TEMP / "c2"),
                                                    "--family", "pile", "--variant", "default",
                                                    "--size", "small", "--hz", "60",
                                                    "--measurement-seconds", "29"]),
    "unknown_variant": captured_error("calibrate.py", calibrate, ["--output", str(TEMP / "c3"),
                                                  "--family", "pile", "--variant", "nope",
                                                  "--size", "small", "--hz", "60"]),
}
out["warmup_probe_arguments"] = {
    "too_short": captured_error("warmup_probe.py", warmup_probe, ["--output", str(TEMP / "w1"), "--family", "pile",
                                               "--variant", "default", "--size", "small",
                                               "--hz", "60", "--warmup-seconds", "119"]),
    "too_long": captured_error("warmup_probe.py", warmup_probe, ["--output", str(TEMP / "w2"), "--family", "pile",
                                              "--variant", "default", "--size", "small",
                                              "--hz", "60", "--warmup-seconds", "601"]),
    "unknown_variant": captured_error("warmup_probe.py", warmup_probe, ["--output", str(TEMP / "w3"),
                                                     "--family", "pile", "--variant", "nope",
                                                     "--size", "small", "--hz", "60"]),
}

# ------------------------------------------------------------------ warmup_probe
WARMUP_COUNT = 120 * 60 + 37
MEASURED_COUNT = 30 * 60
WARMUP_TEXT = warm_text(WARMUP_COUNT, modulo=2)
MEASURED_TEXT = csv_text(STEP_FIELDS, step_table(MEASURED_COUNT, 60))
RESULT_RECORD = {
    "samples": MEASURED_COUNT, "median_step_ns": 1000, "p95_step_ns": 1020,
    "p99_step_ns": 1022, "max_step_ns": 1022,
    "compute_seconds_per_simulated_second": 16.666, "total_allocation_bytes": None,
    "max_lateness_ns": 0, "overrun_steps": 0, "last_contact_begins": MEASURED_COUNT // 60, "last_contact_ends": 0,
    "last_toi_events": 0, "last_awake": 95, "last_linear_speed_sum_m_per_s": 95.0,
    "last_angular_speed_sum_rad_per_s": 0.0, "peak_broadphase_candidates": 7,
    "peak_active_contact_pairs": 3, "peak_active_contact_points": 5,
    "peak_rss_delta_bytes": 0,
    "event_only_full": {"count": 0, "median_ns": None, "p99_ns": None, "max_ns": None,
                        "tail_status": "no_events"},
    "event_only_final_minute": {"count": 0, "median_ns": None, "p99_ns": None, "max_ns": None,
                                "tail_status": "no_events"},
    "activity_status": "valid", "family": "pile", "variant": "default", "size": "small",
    "hz": 60, "mode": "timing", "api": "baseline", "warmup_steps": 7200,
    "warmup_raw": "pile.default.small.60hz.baseline.timing.r1.warmup.csv",
    "warmup_sha256": digest_text(WARMUP_TEXT),
    "stderr_raw": "pile.default.small.60hz.baseline.timing.r1.stderr.raw",
    "stderr_sha256": digest_text(WARMUP_TEXT),
    "cold_construction_ns": 100, "cold_construction_allocated_bytes": 100,
    "rss_empty_harness_bytes": 1000, "rss_after_construction_bytes": 2000,
    "retained_heap_world_alive_bytes": -1, "retained_collection_count_delta": -1,
    "cold_first_step_ns": 1000, "cold_process_initialization_ns": None,
    "raw": "pile.default.small.60hz.baseline.timing.r1.csv",
    "raw_sha256": digest_text(MEASURED_TEXT), "process_pid": 4242, "status": "pilot_only",
}

warmup_out = TEMP / "warmup-out"
warmup_out.mkdir()
def warmup_run_scenario(java, classes, jar, out_dir, family, variant, size, hz, steps, mode,
                        warmup, repeat, *rest):
    Path(out_dir, RESULT_RECORD["raw"]).write_text(MEASURED_TEXT)
    Path(out_dir, RESULT_RECORD["warmup_raw"]).write_text(WARMUP_TEXT)
    return dict(RESULT_RECORD)


with mock.patch.object(warmup_probe, "run_scenario", side_effect=warmup_run_scenario), \
     mock.patch.object(warmup_probe, "jar_path", return_value=JAR), \
     mock.patch.object(warmup_probe, "compile_harness", return_value=CLASSES), \
     mock.patch.object(warmup_probe, "host_identity", return_value=HOST):
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        with mock.patch.object(sys, "argv", [
            "warmup_probe.py", "--output", str(warmup_out), "--family", "pile",
            "--variant", "default", "--size", "small", "--hz", "60", "--warmup-seconds", "120",
        ]):
            warmup_probe.main()
out["warmup_probe"] = {
    "report": json.loads((warmup_out / "warmup-probe.json").read_text()),
    "report_text": (warmup_out / "warmup-probe.json").read_text(),
    "stdout": json.loads(printed.getvalue()),
    "stdout_text": printed.getvalue(),
    "warmup_csv": WARMUP_TEXT,
    "measured_csv": MEASURED_TEXT,
    "hz": 60,
    "family": "pile",
    "variant": "default",
    "size": "small",
    "body_count": 100,
    "result": RESULT_RECORD,
    "host": HOST,
    "baseline_jar_sha256": BASELINE_JAR_SHA256,
    "manifest_sha256": MANIFEST_SHA256,
    "harness_sha256": HARNESS_SHA256,
}

# ------------------------------------------------------------------ calibrate
calibrate_out = TEMP / "calibrate-out"
calibrate_out.mkdir()
CAL_TRIALS = []
for repeat in range(1, 7):
    name = f"pile.default.small.60hz.baseline.timing.r{repeat}"
    write_csv(calibrate_out / f"{name}.csv", STEP_FIELDS,
              step_table(30 * 60, 60, elapsed_base=1000 + 10 * repeat))
    warm = warm_text(120 * 60, modulo=11 + repeat)
    (calibrate_out / f"{name}.warmup.csv").write_text(warm)
    CAL_TRIALS.append({"raw": f"{name}.csv", "warmup_raw": f"{name}.warmup.csv"})


def calibration_run_scenario(java, classes, jar, out_dir, family, variant, size, hz, steps,
                             mode, warmup, repeat, *rest):
    return dict(CAL_TRIALS[repeat - 1])


with mock.patch.object(calibrate, "run_scenario", side_effect=calibration_run_scenario), \
     mock.patch.object(calibrate, "jar_path", return_value=JAR), \
     mock.patch.object(calibrate, "compile_harness", return_value=CLASSES), \
     mock.patch.object(calibrate, "host_identity", return_value=HOST):
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        with mock.patch.object(sys, "argv", [
            "calibrate.py", "--output", str(calibrate_out), "--family", "pile",
            "--variant", "default", "--size", "small", "--hz", "60",
            "--warmup-seconds", "120", "--measurement-seconds", "30",
        ]):
            calibrate.main()
CALIBRATION = json.loads((calibrate_out / "calibration.json").read_text())


def elapsed_series(name):
    with (calibrate_out / name).open(newline="") as stream:
        return [int(row["elapsed_ns"]) for row in csv.DictReader(stream)]


FIRST_PAIR = CALIBRATION["unchanged_baseline_pairs"][0]
out["calibrate_first_pair"] = {
    "a": FIRST_PAIR["a"],
    "b": FIRST_PAIR["b"],
    "hz": 60,
    "left": elapsed_series(FIRST_PAIR["a"]),
    "right": elapsed_series(FIRST_PAIR["b"]),
    "recorded": FIRST_PAIR,
}
out["calibrate"] = {
    "report": CALIBRATION,
    "report_text": (calibrate_out / "calibration.json").read_text(),
    "stdout_text": printed.getvalue(),
    "pairs": CALIBRATION["unchanged_baseline_pairs"],
    "noise_bound": CALIBRATION["noise_bound"],
    "trials": CALIBRATION["trials"],
    "warmup_status": CALIBRATION["warmup_status"],
    "activity_status": CALIBRATION["activity_status"],
    "stdout": json.loads(printed.getvalue()),
    "host": HOST,
    "source_commit": manifest_module.manifest()["source_commit"],
    "baseline_jar_sha256": BASELINE_JAR_SHA256,
    "manifest_sha256": MANIFEST_SHA256,
    "harness_sha256": HARNESS_SHA256,
    "family": "pile",
    "variant": "default",
    "size": "small",
    "hz": 60,
}

# ------------------------------------------------------------------ ccd_route_trace
trace_root = TEMP / "trace-root"
(trace_root / "docs/research").mkdir(parents=True)
(trace_root / "tools/performance").mkdir(parents=True)
shutil.copyfile(ROOT / "docs/research/performance-manifest-v1.json",
                trace_root / "docs/research/performance-manifest-v1.json")
shutil.copyfile(PERF / "ccd_route_trace.py", trace_root / "tools/performance/ccd_route_trace.py")
IDENTITY_FILE = TEMP / "candidate-identity.json"
IDENTITY_FILE.write_text(json.dumps({"schema": 1, "qualification": "unpassed"}))


def identity_csv(hash_codes=None):
    codes = hash_codes or list(range(27))
    return csv_text(["creation_index", "hash_code", "world_center_x", "world_center_y",
                     "bullet"],
                    [[index, codes[index] if index < len(codes) else index,
                      -10.0 if index == 0 else 10.0, 0.5, index >= 2] for index in range(27)])


def trace_csv(count, mutate=None):
    rows = []
    for step in range(count):
        row = {field: 0 for field in STATE_FIELDS}
        row["body_count"] = 25
        row["awake_count"] = 95
        row["linear_speed_sum_m_per_s"] = 25
        if mutate and mutate[0] == step:
            row[mutate[1]] = mutate[2]
        rows.append([row[field] for field in STATE_FIELDS])
    return csv_text(STATE_FIELDS, rows)


def run_trace(name, traces, identity_texts=None):
    out_dir = TEMP / name
    out_dir.mkdir()
    pid = [100]
    identities = identity_texts or {route: identity_csv() for route in ROUTES}

    def fake_run_capture(command, output, stderr_path=None):
        pid[0] += 1
        Path(output).write_text(identities[Path(output).name.split(".")[0]])
        if stderr_path is not None:
            Path(stderr_path).write_text("")
        return "", pid[0]

    def fake_run_scenario(java, classes, jar, target, family, variant, size, hz, steps, mode,
                          warmup, repeat, api="baseline", runner=None):
        file_name = f"{family}.{variant}.{size}.{hz}hz.{api}.{mode}.r{repeat}.csv"
        Path(target, file_name).write_text(traces[api])
        return {"raw": file_name, "api": api}

    failure = None
    exit_message = None
    printed = io.StringIO()
    with mock.patch.object(ccd_route_trace, "git", return_value="a" * 40), \
         mock.patch.object(ccd_route_trace, "prepare", return_value=None), \
         mock.patch.object(ccd_route_trace, "verify_identity", return_value=None), \
         mock.patch.object(ccd_route_trace, "IDENTITY", IDENTITY_FILE), \
         mock.patch.object(ccd_route_trace, "ROOT", trace_root), \
         mock.patch.object(ccd_route_trace, "jar_path", return_value=JAR), \
         mock.patch.object(ccd_route_trace, "compile_harness", return_value=CLASSES), \
         mock.patch.object(ccd_route_trace, "host_identity", return_value=HOST), \
         mock.patch.object(ccd_route_trace, "run_capture", side_effect=fake_run_capture), \
         mock.patch.object(ccd_route_trace, "run_scenario", side_effect=fake_run_scenario):
        with contextlib.redirect_stdout(printed):
            try:
                ccd_route_trace.capture(out_dir, "java", "javac", JAR)
            except SystemExit as exc:
                exit_message = str(exc)
            except ValueError as exc:
                failure = str(exc)
    result_file = out_dir / "result.json"
    return {
        "result": json.loads(result_file.read_text()) if result_file.is_file() else None,
        "result_text": result_file.read_text() if result_file.is_file() else None,
        "stdout": json.loads(printed.getvalue()) if printed.getvalue() else None,
        "stdout_text": printed.getvalue(),
        "exit_message": exit_message,
        "failure": failure,
    }


SAME = {route: trace_csv(120) for route in ROUTES}
out["ccd_agreeing"] = run_trace("trace-agree", SAME)
DIFFERING = dict(SAME)
DIFFERING["compatibility"] = trace_csv(120, mutate=(7, "awake_count", 1))
out["ccd_differing"] = run_trace("trace-differ", DIFFERING)
SHORT = dict(SAME)
SHORT["compatibility"] = trace_csv(119)
out["ccd_row_count"] = run_trace("trace-short", SHORT)
out["ccd_bad_hash"] = run_trace(
    "trace-bad-hash",
    SAME,
    {route: identity_csv([index + 1 for index in range(27)]) for route in ROUTES},
)
out["ccd_divergent_identity"] = run_trace(
    "trace-divergent-identity",
    SAME,
    {"baseline": identity_csv(),
     "direct_kotlin": identity_csv(),
     "compatibility": identity_csv().replace(",0.5,", ",0.6,")},
)
out["ccd_short_identity"] = run_trace(
    "trace-short-identity",
    SAME,
    {route: csv_text(["creation_index", "hash_code", "world_center_x", "world_center_y",
                      "bullet"],
                     [[index, index, 0.0, 0.0, False] for index in range(26)])
     for route in ROUTES},
)


def first_difference_case(name, left, right):
    def rows_of(rows):
        return [{field: row[field] for field in STATE_FIELDS} for row in rows]

    left_rows = [{field: "0" for field in STATE_FIELDS} for _ in range(left[0])]
    right_rows = [{field: "0" for field in STATE_FIELDS} for _ in range(right[0])]
    for step, channel, value in left[1]:
        left_rows[step][channel] = str(value)
    for step, channel, value in right[1]:
        right_rows[step][channel] = str(value)
    return {"name": name,
            "left": left_rows,
            "right": right_rows,
            "result": ccd_route_trace.first_difference(left_rows, right_rows)}


out["first_difference"] = [
    first_difference_case("equal", (4, []), (4, [])),
    first_difference_case("awake_at_step_two", (4, []), (4, [(2, "awake_count", 3)])),
    first_difference_case("body_count_is_first_channel", (4, []),
                          (4, [(1, "body_count", 26)])),
    first_difference_case("later_channel_beats_earlier_step", (4, [(1, "toi_events", 1)]),
                          (4, [(3, "body_count", 26)])),
    first_difference_case("row_count", (4, []), (3, [])),
]

out["ccd_constants"] = {
    "purpose": "CCD fixture and staged-route diagnostic; performance qualification unpassed",
    "fixture_hash_scheme": "Per fixture, hashCode equals zero-based creation index; "
                           "two walls then 25 bullet circles",
    "warmup_steps": 60,
    "measured_steps": 120,
    "routes": [route for route in ROUTES],
    "workloads": {route: f"ccd.default.small.60hz.{route}" for route in ROUTES},
    "state_fields": STATE_FIELDS,
    "pinned_baseline_sha256": manifest_module.manifest()["baseline_jar_sha256"],
}

# ------------------------------------------------------------------ host identity parsing
CPUINFO = ("processor\t: 0\nmodel name\t: Synthetic 9000 32-Core Processor\n"
           "cpu MHz\t\t: 3200.000\n\nprocessor\t: 1\nmodel name\t: Synthetic 9000 32-Core Processor\n")
CPUINFO_NO_MODEL = "processor\t: 0\ncpu MHz\t\t: 3200.000\n"
MEMINFO = "MemTotal:       33554432 kB\nMemFree:         1024 kB\nMemAvailable:    2048 kB\n"
MEMINFO_BAD = "MemFree:         1024 kB\n"
# Record the results the way `measure.host_identity` derives them.
def cpu_model(cpuinfo):
    return next((line.split(":", 1)[1].strip() for line in (cpuinfo or "").splitlines()
                 if line.startswith("model name")), None)


def mem_total_kib(meminfo):
    value = next((line.split()[1] for line in (meminfo or "").splitlines()
                  if line.startswith("MemTotal:")), None)
    return int(value) if value else None


out["host_identity"] = {
    "cases": [
        {"name": "cpu_model", "input": CPUINFO, "result": cpu_model(CPUINFO)},
        {"name": "cpu_model_none", "input": CPUINFO_NO_MODEL, "result": cpu_model(CPUINFO_NO_MODEL)},
        {"name": "cpu_model_absent", "input": None, "result": cpu_model(None)},
        {"name": "mem_total", "input": MEMINFO, "result": mem_total_kib(MEMINFO)},
        {"name": "mem_total_absent", "input": MEMINFO_BAD, "result": mem_total_kib(MEMINFO_BAD)},
        {"name": "mem_total_none", "input": None, "result": mem_total_kib(None)},
    ],
}

print(json.dumps(out, indent=1, sort_keys=True))
