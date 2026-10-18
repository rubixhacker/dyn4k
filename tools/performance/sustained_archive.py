#!/usr/bin/env python3

import argparse
import copy
import csv
import hashlib
import hmac
import json
import math
import os
import platform
import random
import secrets
import shutil
import statistics
import subprocess
import time
from pathlib import Path

from analyze import activity_status, bootstrap_ratio, plateau_status, warmup_status
from candidate_runner import ROOT, source_trees
from manifest import manifest, validate
from measure import MANIFEST_FILE, balanced_orders, sha256, summary as pilot_summary
from stress_monitor import darwin_wait4_peak_rss, peak_rss_bytes, stress_monitor_method


MODES = ("timing", "allocation", "memory")
ROUTES = ("baseline", "direct_kotlin", "compatibility")
STEP_FIELDS = ("step", "elapsed_ns", "mutation_ns", "lateness_ns", "allocation_bytes",
               "heap_used_bytes", "rss_bytes", "rss_delta_bytes", "body_count", "joint_count",
               "awake_count", "linear_speed_sum_m_per_s", "angular_speed_sum_rad_per_s",
               "contact_begins", "contact_ends", "toi_events", "broadphase_candidates",
               "active_contact_pairs", "active_contact_points")
MEMORY_FIELDS = ("phase", "step", "managed_bytes", "native_bytes", "wasm_linear_bytes",
                 "attributed_workload_bytes")
RESOURCE_FIELDS = ("phase", "step", "heap_used_bytes", "rss_bytes", "allocation_bytes")
CLOCK_FIELDS = ("step", "begin_ns", "end_ns")
WARMUP_CLOCK_FIELDS = ("warmup_step", "begin_ns", "end_ns")
PLATEAU_FIELDS = ("cycle", "heap_after_collection_bytes", "rss_after_collection_bytes",
                  "collection_count", "managed_bytes", "native_bytes",
                  "wasm_linear_bytes", "attributed_workload_bytes",
                  "reserved_runtime_bytes")
STRESS_MONITOR_FIELDS = ("elapsed_ns", "rss_bytes", "action")
PROCESS_IMAGE_METHODS = {"Linux": "os_procfs", "Darwin": "macos_libproc",
                         "Windows": "windows_query_image"}


def frozen_policy():
    generated = manifest()
    checked_in = json.loads(MANIFEST_FILE.read_text())
    validate(generated)
    validate(checked_in)
    require(generated == checked_in, "checked-in performance manifest differs from generator")
    return generated


def required_measurements(policy):
    scenarios = [item for item in policy["scenarios"] if item["size"] != "stress"]
    repetitions = range(1, policy["sustained"]["fresh_process_repetitions"] + 1)
    return {
        (row["id"], item["id"], mode, repeat)
        for row in policy["runtime_rows"]
        for item in scenarios
        if item["api"] != "baseline" or row["id"] == "jvm.java"
        for mode in MODES
        for repeat in repetitions
    }


def required_reports(policy):
    return {
        (row["id"], item["id"], mode, 1)
        for row in policy["runtime_rows"]
        for item in policy["scenarios"]
        if item["size"] == "stress" and
        (item["api"] != "baseline" or row["id"] == "jvm.java")
        for mode in MODES
    }


def required_noise(policy):
    return {
        (row["id"], item["id"], repeat, side)
        for row in policy["runtime_rows"]
        for item in policy["scenarios"]
        if item["size"] != "stress" and item["api"] == "baseline"
        for repeat in (1, 2, 3)
        for side in ("a", "b")
    }


def required_plateaus(policy):
    return {
        (row["id"], item["id"])
        for row in policy["runtime_rows"]
        for item in policy["scenarios"]
        if item["size"] != "stress" and
        (item["api"] != "baseline" or row["id"] == "jvm.java")
    }


def require(condition, message):
    if not condition:
        raise ValueError(message)


def approved_gate(policy):
    gate = policy.get("sustained_gate")
    require(isinstance(gate, dict),
            "unpassed policy: approved sustained harness, noise, and stress decisions are absent")
    rows = {row["id"] for row in policy["runtime_rows"]}
    require(isinstance(gate.get("harnesses"), dict) and
            set(gate["harnesses"]) == rows and
            isinstance(gate.get("noise_upper_ratio_max"), (int, float)) and
            not isinstance(gate["noise_upper_ratio_max"], bool) and
            math.isfinite(gate["noise_upper_ratio_max"]) and
            gate["noise_upper_ratio_max"] >= 1 and
            all(type(gate.get(name)) is int and gate[name] > 0 for name in
                ("stress_wall_ns_max", "stress_rss_bytes_max")),
            "unpassed policy: approved noise or stress ceiling is absent or invalid")
    fixture_hash = hashlib.sha256(canonical({"fixture": policy["fixture"],
                    "joint_parameters": policy["joint_parameters"]})).hexdigest()
    for row_id, harness in gate["harnesses"].items():
        prefix = harness.get("command_prefix")
        ambient = harness.get("environment")
        require(isinstance(harness.get("sha256"), str) and
                len(harness["sha256"]) == 64 and
                isinstance(harness.get("adapter_sha256"), str) and
                len(harness["adapter_sha256"]) == 64 and
                harness.get("fixture_sha256") == fixture_hash and
                isinstance(prefix, list) and prefix and prefix[0] == "{runtime}" and
                isinstance(ambient, dict) and all(isinstance(name, str) and name and
                    not name.startswith("DYN4K_") and isinstance(value, str)
                    for name, value in ambient.items()) and
                all(isinstance(part, str) and part for part in prefix) and
                all(any("{" + name + "}" in part for part in prefix)
                    for name in ("harness", "adapter")) and
                (row_id != "jvm.java" or
                 "-cp" in prefix and all(any("{" + name + "}" in part for part in prefix)
                    for name in ("baseline", "core", "kotlin"))),
                f"unpassed policy: approved harness or fixture differs: {row_id}")
    return gate


def command_prefix(reference, policy, row_id, artifacts, baseline):
    tokens = {"runtime": reference["runtime"]["path"],
              "harness": reference["harness"]["path"],
              "adapter": reference["adapter"]["path"],
              "baseline": baseline["staged_path"],
              "core": artifacts[row_id]["core"]["staged_path"],
              "kotlin": artifacts[row_id]["kotlin"]["staged_path"]}
    try:
        return [part.format_map(tokens) for part in
                approved_gate(policy)["harnesses"][row_id]["command_prefix"]]
    except (KeyError, ValueError) as exc:
        raise ValueError("approved complete command template is invalid") from exc


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def signature(index, key):
    unsigned = {name: value for name, value in index.items() if name != "signature"}
    return hmac.new(key, canonical(unsigned), hashlib.sha256).hexdigest()


def write_index(root, index, key):
    index["signature"] = signature(index, key)
    target = root / "archive.json"
    temporary = root / "archive.json.tmp"
    temporary.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    temporary.replace(target)


def checked_file(root, record, path_key, hash_key):
    name = record[path_key]
    require(isinstance(name, str) and name and not Path(name).is_absolute() and
            ".." not in Path(name).parts, f"unsafe {path_key}")
    path = (root / name).resolve()
    require(path.is_relative_to(root.resolve()) and path.is_file(), f"missing {path_key}: {name}")
    require(sha256(path) == record[hash_key], f"{path_key} bytes differ: {name}")
    return path


def observed_host():
    return {"hostname": platform.node(), "machine": platform.machine(),
            "system": platform.system(), "release": platform.release()}


def observe_process_image(pid):
    system = platform.system()
    require(system in PROCESS_IMAGE_METHODS, "independent OS process image probe unavailable")
    if system == "Linux":
        executable = Path(f"/proc/{pid}/exe")
        path = os.readlink(executable)
        observed_ns = time.monotonic_ns()
        digest = sha256(executable)
    elif system == "Darwin":
        import ctypes
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib")
        libproc.proc_pidpath.argtypes = (ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32)
        libproc.proc_pidpath.restype = ctypes.c_int
        image = ctypes.create_string_buffer(4096)
        require(libproc.proc_pidpath(pid, image, len(image)) > 0,
                "macOS process image path unavailable")
        path = os.fsdecode(image.value)
        observed_ns = time.monotonic_ns()
        digest = sha256(path)
    else:
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.QueryFullProcessImageNameW.argtypes = (ctypes.c_void_p, ctypes.c_ulong,
                                                     ctypes.c_void_p, ctypes.c_void_p)
        kernel.QueryFullProcessImageNameW.restype = ctypes.c_int
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel.CloseHandle.restype = ctypes.c_int
        handle = kernel.OpenProcess(0x1000, False, pid)
        require(handle, "Windows process image handle unavailable")
        try:
            image = ctypes.create_unicode_buffer(32768)
            length = ctypes.c_ulong(len(image))
            require(kernel.QueryFullProcessImageNameW(handle, 0, image,
                    ctypes.byref(length)), "Windows process image path unavailable")
            path = image.value
            observed_ns = time.monotonic_ns()
            digest = sha256(path)
        finally:
            kernel.CloseHandle(handle)
    return {"pid": pid, "observed_ns": observed_ns,
            "method": PROCESS_IMAGE_METHODS[system],
            "executable_path": path, "sha256": digest}


def require_external_key(key_path, archive_paths):
    key_path = Path(key_path)
    lexical_key = Path(os.path.abspath(key_path))
    resolved_key = key_path.resolve(strict=True)
    key_stat = resolved_key.stat()
    for archive_text in archive_paths:
        archive = Path(archive_text)
        lexical_archive = Path(os.path.abspath(archive))
        resolved_archive = archive.resolve()
        require(not lexical_key.is_relative_to(lexical_archive) and
                not lexical_key.is_relative_to(resolved_archive) and
                not resolved_key.is_relative_to(lexical_archive) and
                not resolved_key.is_relative_to(resolved_archive),
                "trusted key must stay outside every archive")
        if key_stat.st_nlink > 1 and resolved_archive.is_dir():
            for candidate in resolved_archive.rglob("*"):
                if candidate.is_file():
                    stat = candidate.stat()
                    require((stat.st_dev, stat.st_ino) != (key_stat.st_dev, key_stat.st_ino),
                            "trusted key must stay outside every archive")


def verify_source_and_artifacts(root, index, expected_source_commit, policy):
    commit = index["source_commit"]
    require(commit == expected_source_commit and len(commit) == 40,
            "candidate source commit differs")
    require(index["source_trees"] == source_trees(commit), "candidate source trees differ")
    artifacts = index["artifacts"]
    checked_file(root, index["baseline"], "archive_path", "sha256")
    require(index["baseline"]["sha256"] == policy["baseline_jar_sha256"],
            "baseline binary differs from frozen release")
    require(set(artifacts) == set(index["references"]), "staged artifact runtime rows differ")
    hashes = {}
    for row_id, modules in artifacts.items():
        require(set(modules) == {"core", "kotlin"}, f"staged artifact modules differ: {row_id}")
        hashes[row_id] = {}
        for name, record in modules.items():
            copy = checked_file(root, record, "archive_path", "sha256")
            staged = Path(record["staged_path"])
            local_host = index["references"][row_id]["host"] == observed_host()
            require(staged.is_absolute() and
                    (not local_host or staged.is_file() and sha256(staged) == record["sha256"]),
                    f"staged {row_id} {name} bytes differ")
            require(copy.stat().st_size > 0, f"empty staged {row_id} {name} artifact")
            hashes[row_id][name] = record["sha256"]
        require(hashes[row_id]["core"] != hashes[row_id]["kotlin"] and
                hashes[row_id]["core"] != policy["baseline_jar_sha256"],
                f"staged artifact identity differs: {row_id}")
        reference = index["references"][row_id]
        receipt = json.loads(checked_file(root, reference["build_receipt"],
                                          "archive_path", "sha256").read_text())
        require(receipt["source_commit"] == commit and
                receipt["source_trees"] == index["source_trees"] and
                receipt["artifact_sha256"] == hashes[row_id] and
                receipt["build_configuration"] == reference["build_configuration"] and
                receipt["build_configuration"] == next(row for row in policy["runtime_rows"]
                    if row["id"] == row_id)["optimized_build"] and
                receipt["target"] == reference["target"] and
                receipt["status"] == "built_from_exact_source",
                f"staged artifact build receipt differs: {row_id}")
    return hashes


def verify_references(root, index, policy, complete=True):
    gate = approved_gate(policy)
    rows = {item["id"]: item for item in policy["runtime_rows"]}
    references = index["references"]
    require((set(references) == set(rows) if complete else
             bool(references) and set(references).issubset(rows)),
            "reference environment rows differ")
    for row_id, reference in references.items():
        row = rows[row_id]
        require(reference["target"] == row["target"] and
                reference["runtime_family"] == row["runtime_family"] and
                reference["minimum_policy"] == row["minimum_policy"] and
                reference["size_assignment"] == row["size_assignment"] and
                reference["optimized_build"] == row["optimized_build"] and
                reference["development_build"] == row["development_build"] and
                reference["support_verification"] == "passed" and
                reference["status"] == "validated" and
                reference["probe_status"] == "validated", f"reference row unvalidated: {row_id}")
        for field in ("representative_hardware", "runtime_version", "abi", "build_configuration"):
            value = reference.get(field)
            require(isinstance(value, str) and value.strip() and
                    value.lower() not in {"unknown", "unavailable", "none", "unvalidated"},
                    f"reference {field} unavailable: {row_id}")
        require(reference["build_configuration"] == row["optimized_build"],
                f"reference build configuration differs: {row_id}")
        host = reference["host"]
        require(isinstance(host, dict) and all(isinstance(host.get(field), str) and
                host[field].strip() for field in observed_host()),
                f"reference host identity unavailable: {row_id}")
        controls = reference["host_control"]
        require(controls["status"] == "validated" and
                all(isinstance(controls.get(field), str) and controls[field].strip() and
                    controls[field].lower() not in {"unknown", "unavailable", "unvalidated"}
                    for field in ("power_mode", "thermal_state", "load_window")),
                f"reference host control unavailable: {row_id}")
        runtime = reference["runtime"]
        path = Path(runtime["path"])
        archived_runtime = checked_file(root, runtime, "archive_path", "sha256")
        local_host = reference["host"] == observed_host()
        require(path.is_absolute() and archived_runtime.stat().st_size > 0 and
                (not local_host or path.is_file() and sha256(path) == runtime["sha256"]) and
                runtime["version"] == reference["runtime_version"],
                f"reference runtime identity differs: {row_id}")
        harness = reference["harness"]
        harness_path = Path(harness["path"])
        archived_harness = checked_file(root, harness, "archive_path", "sha256")
        require(harness_path.is_absolute() and archived_harness.stat().st_size > 0 and
                harness["sha256"] == gate["harnesses"][row_id]["sha256"] and
                (not local_host or harness_path.is_file() and
                 sha256(harness_path) == harness["sha256"]),
                f"approved harness bytes differ: {row_id}")
        adapter = reference["adapter"]
        adapter_path = Path(adapter["path"])
        archived_adapter = checked_file(root, adapter, "archive_path", "sha256")
        require(adapter_path.is_absolute() and archived_adapter.stat().st_size > 0 and
                adapter["sha256"] == gate["harnesses"][row_id]["adapter_sha256"] and
                (not local_host or adapter_path.is_file() and
                 sha256(adapter_path) == adapter["sha256"]),
                f"approved adapter bytes differ: {row_id}")
        probe = reference["probe"]
        timer = checked_file(root, probe, "timer_raw", "timer_sha256")
        with timer.open(newline="") as stream:
            reader = csv.DictReader(stream)
            require(reader.fieldnames == ["elapsed_ns"], f"timer probe header differs: {row_id}")
            values = [int(item["elapsed_ns"]) for item in reader]
        require(len(values) == 10000 and all(value > 0 for value in values) and
                min(values) == probe["timer_min_positive_ns"] and
                statistics.median(values) == probe["timer_median_ns"] and
                sorted(values)[9899] == probe["timer_p99_ns"],
                f"timer probe invalid: {row_id}")
        require(probe["controlled_payload_bytes"] >= 1048576 and
                probe["controlled_allocated_bytes"] >= probe["controlled_payload_bytes"] and
                probe["retained_collection_count_delta"] > 0 and
                probe["memory_attribution"] == "validated" and
                set(probe["memory_components"]) == {"managed", "native", "wasm_linear"} and
                len(set(probe["memory_components"])) == 3,
                f"allocation or memory probe invalid: {row_id}")
        allocation = csv_rows(checked_file(root, probe, "allocation_raw", "allocation_sha256"),
                              ("payload_bytes", "allocated_bytes", "collection_count_delta"))
        require(len(allocation) == 1 and
                int(allocation[0]["payload_bytes"]) == probe["controlled_payload_bytes"] and
                int(allocation[0]["allocated_bytes"]) == probe["controlled_allocated_bytes"] and
                int(allocation[0]["collection_count_delta"]) ==
                probe["retained_collection_count_delta"],
                f"controlled allocation raw probe differs: {row_id}")
    return references


def csv_rows(path, fields):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        require(tuple(reader.fieldnames or ()) == fields, f"raw CSV header differs: {path.name}")
        rows = list(reader)
    require(rows and all(None not in row and all(value is not None and value != ""
            for value in row.values()) for row in rows), f"raw CSV incomplete: {path.name}")
    return rows


def warmup_rows(path, hz, plateau=False):
    lines = path.read_text().splitlines()
    markers = {}
    csv_lines = []
    for line in lines:
        if line.startswith("#"):
            key, separator, value = line[1:].partition("=")
            require(separator and key not in markers, "duplicate or malformed stderr marker")
            markers[key] = value
        else:
            csv_lines.append(line)
    reader = csv.DictReader(csv_lines)
    fields = (("warmup_step", "elapsed_ns") if plateau else
              ("warmup_step", "elapsed_ns", "rss_bytes"))
    require(tuple(reader.fieldnames or ()) == fields,
            "warm-up CSV header differs")
    rows = list(reader)
    require(120 * hz <= len(rows) <= 600 * hz and
            [int(row["warmup_step"]) for row in rows] == list(range(len(rows))) and
            all(int(row["elapsed_ns"]) > 0 and
                (plateau or int(row["rss_bytes"]) >= -1) for row in rows) and
            warmup_status(rows, hz) == "converged", "warm-up duration or convergence invalid")
    required = ("construction_ns", "construction_allocated_bytes", "rss_empty_harness_bytes",
                "rss_after_construction_bytes", "retained_heap_world_alive_bytes",
                "retained_collection_count_delta")
    if plateau:
        return rows, markers
    require(all(key in markers and markers[key].lstrip("-").isdigit() for key in required),
            "construction or retained-memory marker missing")
    require(all(int(markers[key]) >= 0 for key in required[:-1]) and
            int(markers[required[-1]]) > 0, "construction or retained-memory probe invalid")
    require(markers.get("fixture_reset_after_warmup") == "1",
            "fixture reset after converged warm-up is unproven")
    return rows, markers


def validate_steps(rows, scenario, mode, policy):
    hz = scenario["rate_hz"]
    count = policy["families"][scenario["family"]][scenario["size"]]
    steps = (60 if scenario["size"] == "stress" else
             policy["sustained"]["measured_wall_seconds"]) * hz
    require(len(rows) == steps and [int(row["step"]) for row in rows] == list(range(steps)),
            "raw step duration, count, or order differs")
    static = (1 if scenario["family"] in ("pile", "lifecycle") else
              2 if scenario["family"] == "ccd" else count if scenario["family"] == "joint" else 0)
    joints = (count if scenario["family"] == "joint" else
              (count + 9) // 10 if scenario["family"] == "lifecycle" else 0)
    for position, row in enumerate(rows):
        elapsed = int(row["elapsed_ns"])
        mutation = int(row["mutation_ns"])
        allocated = int(row["allocation_bytes"])
        require(elapsed > 0 and 0 <= mutation <= elapsed and int(row["lateness_ns"]) >= 0 and
                (allocated == -1 if mode == "timing" else allocated >= 0) and
                int(row["heap_used_bytes"]) >= 0 and int(row["rss_bytes"]) >= 0 and
                int(row["rss_delta_bytes"]) >= 0 and
                int(row["body_count"]) == count + static and
                int(row["joint_count"]) == joints and
                0 <= int(row["awake_count"]) <= count,
                f"invalid timing, allocation, memory, or topology at step {position}")
        for field in ("contact_begins", "contact_ends", "toi_events"):
            require(int(row[field]) >= 0 and
                    (position == 0 or int(row[field]) >= int(rows[position - 1][field])),
                    f"nonmonotonic {field} at step {position}")
        sampled = position % hz == 0 or position == steps - 1
        for field in ("broadphase_candidates", "active_contact_pairs", "active_contact_points"):
            value = int(row[field])
            require(value >= 0 if sampled else value == -1,
                    f"missing or extra sampled {field} at step {position}")
        for field in ("linear_speed_sum_m_per_s", "angular_speed_sum_rad_per_s"):
            value = float(row[field])
            require(math.isfinite(value) and value >= 0, f"invalid {field} at step {position}")
    require(activity_status(rows, scenario["family"], scenario["variant"], count, hz) == "valid",
            "scenario activity invalid")
    return rows


def validate_memory(rows, warmup_count, step_count, cap_bytes):
    expected = ([('empty', 0), ('construction', 0)] +
                [('warmup', index) for index in range(warmup_count)] +
                [('measure', index) for index in range(step_count)])
    require([(row["phase"], int(row["step"])) for row in rows] == expected,
            "attributed memory stream is incomplete or reordered")
    values = []
    for row in rows:
        managed, native, wasm, workload = (int(row[field]) for field in MEMORY_FIELDS[2:])
        require(min(managed, native, wasm, workload) >= 0 and
                workload == managed + native + wasm,
                "attributed memory components overlap or differ")
        values.append(workload)
    require(values[0] == 0 and (cap_bytes is None or max(values) <= cap_bytes),
            "incremental workload memory budget exceeded")
    return max(values)


def validate_plateau(rows, cycles):
    require(len(rows) == cycles and
            [int(row["cycle"]) for row in rows] == list(range(cycles)) and
            plateau_status(rows) == "stable", "plateau cycle count or heap drift invalid")
    for before, after in zip(rows, rows[1:]):
        require(int(after["collection_count"]) >= int(before["collection_count"]),
                "plateau collection count regressed")
    channels = ("managed_bytes", "native_bytes", "wasm_linear_bytes",
                "attributed_workload_bytes")
    residual = []
    for row in rows:
        values = [int(row[field]) for field in channels]
        reserved = int(row["reserved_runtime_bytes"])
        rss = int(row["rss_after_collection_bytes"])
        require(min(*values, reserved, rss) >= 0 and values[3] == sum(values[:3]) and
                rss >= values[3] + reserved,
                "plateau attribution, reserved memory, or RSS invalid")
        residual.append(rss - values[3] - reserved)
    for field in channels:
        values = [int(row[field]) for row in rows]
        early = statistics.median(values[20:40])
        late = statistics.median(values[80:100])
        require(late <= early * 1.05,
                f"plateau attributable {field} cycle retention is inconclusive")
    require(statistics.median(residual[80:100]) <=
            statistics.median(residual[20:40]) * 1.05,
            "plateau unexplained RSS growth is inconclusive")


def validate_stress(root, item, policy, image_receipt):
    gate = approved_gate(policy)
    require(item.get("stress_monitor_method") ==
            stress_monitor_method(item["host"]["system"]) and
            not item["stress_monitor_method"].startswith("unsupported_"),
            "unpassed row: external peak RSS monitor is unvalidated")
    require(item["wall_ns"] <= gate["stress_wall_ns_max"] and
            item.get("termination_reason") == "completed" and
            type(item.get("stress_peak_rss_bytes")) is int and
            item["stress_peak_rss_bytes"] <= gate["stress_rss_bytes_max"],
            "stress wall, memory, or termination ceiling invalid")
    rows = csv_rows(checked_file(root, item, "stress_monitor_path",
                                 "stress_monitor_sha256"), STRESS_MONITOR_FIELDS)
    elapsed = [int(row["elapsed_ns"]) for row in rows]
    rss = [int(row["rss_bytes"]) for row in rows]
    require(len(rows) >= 2 and elapsed[0] >= 0 and
            item["started_ns"] + elapsed[0] >= image_receipt["observed_ns"] and
            elapsed == sorted(set(elapsed)) and
            elapsed[-1] <= item["wall_ns"] and
            all(0 < value <= gate["stress_rss_bytes_max"] for value in rss) and
            (item["host"]["system"] == "Darwin" or rss == sorted(rss)) and
            max(rss) == item["stress_peak_rss_bytes"] and
            all(row["action"] == "running" for row in rows[:-1]) and
            rows[-1]["action"] == item["termination_reason"],
            "stress monitor stream or termination receipt invalid")
    receipt = json.loads(checked_file(root, item, "stress_monitor_receipt_path",
                                      "stress_monitor_receipt_sha256").read_text())
    terminal_fields = ({"metric_kind", "terminal_pid", "terminal_wait_status",
                        "terminal_ru_maxrss_bytes"} if item["host"]["system"] == "Darwin"
                       else set())
    require(set(receipt) == {"pid", "method", "process_image_sha256",
                             "process_image_observed_ns", "started_ns", "ended_ns",
                             "sample_count", "peak_rss_bytes", "termination_reason",
                             "exit_code"} | terminal_fields and
            all(type(receipt[field]) is int for field in
                ("pid", "process_image_observed_ns", "started_ns", "ended_ns",
                 "sample_count", "peak_rss_bytes", "exit_code")) and
            receipt == {"pid": item["pid"],
                        "method": item["stress_monitor_method"],
                        "process_image_sha256": image_receipt["sha256"],
                        "process_image_observed_ns": image_receipt["observed_ns"],
                        "started_ns": item["started_ns"],
                        "ended_ns": item["ended_ns"],
                        "sample_count": len(rows),
                        "peak_rss_bytes": item["stress_peak_rss_bytes"],
                        "termination_reason": item["termination_reason"],
                        "exit_code": item["exit_code"],
                        **({"metric_kind": "peak_rss_bytes",
                            "terminal_pid": item["pid"], "terminal_wait_status": 0,
                            "terminal_ru_maxrss_bytes": item["stress_peak_rss_bytes"]}
                           if terminal_fields else {})} and
            (not terminal_fields or
             rss[-1] == receipt["terminal_ru_maxrss_bytes"] and
             all(value <= rss[-1] for value in rss[:-1])),
            "stress monitor receipt differs from process image or termination")


def validate_clock(clock, measured, hz, duration_seconds):
    require(len(clock) == len(measured) and
            [int(row["step"]) for row in clock] == list(range(len(measured))),
            "monotonic clock stream is incomplete")
    first = int(clock[0]["begin_ns"])
    previous = first - 1
    previous_end = first
    for index, (stamp, sample) in enumerate(zip(clock, measured)):
        begin = int(stamp["begin_ns"])
        end = int(stamp["end_ns"])
        deadline = first + (index * 1_000_000_000 + hz // 2) // hz
        require(begin > previous and begin >= previous_end and
                end - begin == int(sample["elapsed_ns"]) and
                begin - deadline == int(sample["lateness_ns"]),
                f"step {index} monotonic pacing or elapsed time differs")
        previous = begin
        previous_end = end
    require(previous - first + math.ceil(1_000_000_000 / hz) >=
            duration_seconds * 1_000_000_000,
            "measured clock span is shorter than required duration")


def validate_warmup_clock(clock, warmup, hz):
    require(len(clock) == len(warmup) and
            [int(row["warmup_step"]) for row in clock] == list(range(len(warmup))),
            "warm-up clock stream is incomplete")
    first = int(clock[0]["begin_ns"])
    previous_end = first
    for index, (stamp, sample) in enumerate(zip(clock, warmup)):
        begin = int(stamp["begin_ns"])
        end = int(stamp["end_ns"])
        deadline = first + (index * 1_000_000_000 + hz // 2) // hz
        require(begin >= previous_end and begin >= deadline and
                end - begin == int(sample["elapsed_ns"]),
                f"warm-up step {index} pacing or elapsed time differs")
        previous_end = end
    require(int(clock[-1]["begin_ns"]) - first + math.ceil(1_000_000_000 / hz) >=
            len(warmup) * 1_000_000_000 / hz,
            "warm-up clock span is shorter than required duration")


def validate_process_clock(root, item, warm_clock, measured_clock, image_observed_ns):
    origin = json.loads(checked_file(root, item, "clock_origin_path",
                                     "clock_origin_sha256").read_text())
    receipt = json.loads(checked_file(root, item, "clock_origin_receipt_path",
                                      "clock_origin_receipt_sha256").read_text())
    require(set(origin) == {"pid", "runtime_ns", "nonce"} and
            set(receipt) == {"pid", "runtime_ns", "nonce", "method",
                             "host_before_ns", "host_after_ns"} and
            type(origin["pid"]) is int and origin["pid"] == item["pid"] and
            type(origin["runtime_ns"]) is int and
            isinstance(origin["nonce"], str) and origin["nonce"] and
            origin["nonce"] == item["clock_nonce"] and
            receipt["pid"] == origin["pid"] and
            receipt["runtime_ns"] == origin["runtime_ns"] and
            receipt["nonce"] == origin["nonce"] and
            receipt["method"] == "host_file_bracket_v1" and
            type(receipt["host_before_ns"]) is int and
            type(receipt["host_after_ns"]) is int and
            receipt["host_before_ns"] == item["started_ns"] and
            image_observed_ns <= receipt["host_after_ns"] <= item["ended_ns"] and
            receipt["host_before_ns"] <= receipt["host_after_ns"],
            "process-bound clock origin receipt differs")
    offset_low = receipt["host_before_ns"] - origin["runtime_ns"]
    offset_high = receipt["host_after_ns"] - origin["runtime_ns"]
    require(bool(warm_clock), "warm-up process-bound clock is empty")
    rows = [*warm_clock, *(measured_clock or ())]
    previous_end = None
    feasible_low = offset_low
    feasible_high = offset_high
    for row in rows:
        begin = int(row["begin_ns"])
        end = int(row["end_ns"])
        require(begin >= origin["runtime_ns"] and end > begin and
                (previous_end is None or begin >= previous_end),
                "process-bound clock sequence is invalid")
        feasible_low = max(feasible_low, item["started_ns"] - begin)
        feasible_high = min(feasible_high, item["ended_ns"] - end)
        require(feasible_low <= feasible_high,
                "process-bound clock lies outside observed interval")
        previous_end = end


def capture_key(item):
    kind = item["kind"]
    if kind in ("measure", "report"):
        return (item["row_id"], item["scenario_id"], item["mode"], item["repeat"])
    if kind == "noise":
        return (item["row_id"], item["scenario_id"], item["repeat"], item["side"])
    if kind == "plateau":
        return (item["row_id"], item["scenario_id"])
    raise ValueError("unknown capture kind")


def verify_capture(root, item, scenarios, references, artifact_hashes, policy, index):
    row_id = item["row_id"]
    scenario = scenarios[item["scenario_id"]]
    reference = references[row_id]
    require(item["status"] == "complete" and type(item.get("exit_code")) is int and
            item["exit_code"] == 0 and
            item["artifacts"] == artifact_hashes[row_id],
            "capture source, artifact, or completion differs")
    require(item["host"] == reference["host"] and
            item["runtime_sha256"] == reference["runtime"]["sha256"] and
            item["process_image_sha256"] == reference["runtime"]["sha256"] and
            item["process_image_method"] == PROCESS_IMAGE_METHODS.get(
                reference["host"]["system"]) and
            item["probe_sha256"] == reference["probe"]["timer_sha256"] and
            item["ambient_environment"] ==
                approved_gate(policy)["harnesses"][row_id]["environment"] and
            item["build_configuration"] == reference["build_configuration"] and
            item["build_configuration"] == next(row for row in policy["runtime_rows"]
                if row["id"] == row_id)["optimized_build"],
            "executed host, runtime, or build differs")
    require(isinstance(item["pid"], int) and item["pid"] > 0 and
            item["ended_ns"] > item["started_ns"] > 0 and
            item["wall_ns"] == item["ended_ns"] - item["started_ns"],
            "executed process identity or monotonic duration invalid")
    image_receipt = json.loads(checked_file(root, item, "process_image_receipt_path",
                                            "process_image_receipt_sha256").read_text())
    require(set(image_receipt) == {"pid", "observed_ns", "method", "executable_path",
                                   "sha256"} and
            image_receipt["pid"] == item["pid"] and
            type(image_receipt["observed_ns"]) is int and
            item["started_ns"] <= image_receipt["observed_ns"] <= item["ended_ns"] and
            image_receipt["method"] == item["process_image_method"] and
            image_receipt["executable_path"] == reference["runtime"]["path"] and
            image_receipt["sha256"] == item["process_image_sha256"],
            "independent OS process image receipt differs")
    duration = 60 if item["kind"] == "report" else policy["sustained"]["measured_wall_seconds"]
    if item["kind"] == "plateau":
        require(item["mode"] == "plateau", "plateau mode differs")
        duration = 0
    command = item["command"]
    require(isinstance(command, list) and command and all(isinstance(part, str) and part for part in command),
            "executed command missing")
    runner = Path(item["runner_path"])
    local_host = reference["host"] == observed_host()
    require(runner.is_absolute() and command[0] == str(runner) and
            str(runner) == reference["runtime"]["path"] and
            item["runner_sha256"] == reference["runtime"]["sha256"] and
            (not local_host or runner.is_file() and
             sha256(runner) == item["runner_sha256"]),
            "executed runner identity differs")
    provider = json.loads(checked_file(root, item, "provider_path", "provider_sha256").read_text())
    require(provider["pid"] == item["pid"] and
            provider["runtime_sha256"] == item["runtime_sha256"] and
            provider["source_commit"] == item["source_commit"] and
            provider["api"] == scenario["api"] and
            provider["artifact_sha256"] == artifact_hashes[row_id] and
            provider["baseline_sha256"] == policy["baseline_jar_sha256"] and
            provider["loaded_core_sha256"] == (policy["baseline_jar_sha256"] if
                scenario["api"] == "baseline" else artifact_hashes[row_id]["core"]) and
            provider["loaded_kotlin_sha256"] == (artifact_hashes[row_id]["kotlin"] if
                scenario["api"] == "direct_kotlin" else None) and
            provider["loaded_harness_sha256"] == reference["harness"]["sha256"] and
            provider["loaded_adapter_sha256"] == reference["adapter"]["sha256"] and
            provider["loaded_fixture_sha256"] ==
                approved_gate(policy)["harnesses"][row_id]["fixture_sha256"],
            "loaded provider or process identity differs")
    raw = checked_file(root, item, "raw_path", "raw_sha256")
    stderr = checked_file(root, item, "stderr_path", "stderr_sha256")
    warm, markers = warmup_rows(stderr, scenario["rate_hz"], item["kind"] == "plateau")
    warm_clock = checked_file(root, item, "warmup_clock_path", "warmup_clock_sha256")
    warm_clock_rows = csv_rows(warm_clock, WARMUP_CLOCK_FIELDS)
    validate_warmup_clock(warm_clock_rows, warm, scenario["rate_hz"])
    require(item["wall_ns"] >= (len(warm) / scenario["rate_hz"] + duration) * 1_000_000_000,
            "executed process shorter than warm-up plus required duration")
    require(int(markers.get("process_pid", item["pid"])) == item["pid"] and
            int(markers.get("route_marker", {"baseline": 0, "direct_kotlin": 1,
                                             "compatibility": 2}[scenario["api"]])) ==
            {"baseline": 0, "direct_kotlin": 1, "compatibility": 2}[scenario["api"]],
            "runner process or route marker differs")
    hz = scenario["rate_hz"]
    warmup_steps = len(warm)
    steps = (60 if item["kind"] == "report" else
             policy["sustained"]["measured_wall_seconds"]) * hz
    expected_tail = [scenario["family"], scenario["variant"], scenario["size"], str(hz),
                     str(1 if item["kind"] == "plateau" else steps),
                     "plateau" if item["kind"] == "plateau" else item["mode"], str(warmup_steps)]
    if scenario["api"] != "baseline":
        expected_tail.append(scenario["api"])
    require(command == command_prefix(reference, policy, row_id,
                                      index["artifacts"], index["baseline"]) + expected_tail,
            "executed command, classpath, JVM settings, or fixture differs")
    if item["kind"] == "plateau":
        validate_process_clock(root, item, warm_clock_rows, None,
                               image_receipt["observed_ns"])
        rows = csv_rows(raw, PLATEAU_FIELDS)
        validate_plateau(rows, policy["sustained"]["create_use_dispose_cycles"])
        return rows, markers
    if item["kind"] == "report":
        validate_stress(root, item, policy, image_receipt)
    mode = "timing" if item["kind"] == "noise" else item["mode"]
    require(item["mode"] == mode, "capture mode differs")
    rows = validate_steps(csv_rows(raw, STEP_FIELDS), scenario, mode, policy)
    clock = checked_file(root, item, "clock_path", "clock_sha256")
    clock_rows = csv_rows(clock, CLOCK_FIELDS)
    validate_clock(clock_rows, rows, hz, duration)
    validate_process_clock(root, item, warm_clock_rows, clock_rows,
                           image_receipt["observed_ns"])
    if "resource_path" in item or "run_path" in item:
        require("resource_path" in item and "run_path" in item,
                "versioned resource or run sidecar is partial")
        resource = csv_rows(checked_file(root, item, "resource_path", "resource_sha256"),
                            RESOURCE_FIELDS)
        expected = ([('empty', 0), ('construction', 0)] +
                    [('warmup', step) for step in range(warmup_steps)] +
                    [('measure', step) for step in range(len(rows))])
        require([(entry["phase"], int(entry["step"])) for entry in resource] == expected and
                all(int(entry["heap_used_bytes"]) >= 0 and
                    int(entry["rss_bytes"]) >= -1 for entry in resource),
                "versioned resource stream differs")
        measured_resource = resource[2 + warmup_steps:]
        require(all(int(resource_row["heap_used_bytes"]) == int(raw_row["heap_used_bytes"]) and
                    int(resource_row["rss_bytes"]) == int(raw_row["rss_bytes"]) and
                    int(resource_row["allocation_bytes"]) == int(raw_row["allocation_bytes"])
                    for resource_row, raw_row in zip(measured_resource, rows)),
                "versioned resource and raw samples differ")
        run = json.loads(checked_file(root, item, "run_path", "run_sha256").read_text())
        require(run["api"] == scenario["api"] and run["mode"] == mode and
                run["status"] == "complete" and run["sample_count"] == len(rows) and
                run["warmup_count"] == warmup_steps and
                run["active_steps"] == sum(int(row["awake_count"]) > 0 for row in rows) and
                run["measured_wall_ns"] >= duration * 1_000_000_000 -
                    math.ceil(1_000_000_000 / hz) and
                run["measured_wall_ns"] <= item["wall_ns"] and
                run["peak_heap_used_bytes"] ==
                    max(int(entry["heap_used_bytes"]) for entry in resource) and
                run["peak_rss_bytes"] == max(int(entry["rss_bytes"]) for entry in resource),
                "versioned run sample, duration, activity, or resource summary differs")
    if mode == "memory":
        memory = checked_file(root, item, "memory_path", "memory_sha256")
        assignment = next(row for row in policy["runtime_rows"] if row["id"] == row_id)
        cap = (None if scenario["size"] == "stress" or scenario["api"] == "baseline" or
               assignment["size_assignment"][scenario["size"]] == "report_only" else
               policy["budgets"]["incremental_peak_mib"][scenario["size"]] *
               policy["budgets"]["mib_bytes"])
        validate_memory(csv_rows(memory, MEMORY_FIELDS), warmup_steps, len(rows), cap)
    else:
        require("memory_path" not in item, "memory attribution claimed in wrong mode")
    if item["kind"] != "noise":
        require(item["summary"] == step_summary(rows, mode, hz),
                "indexed analysis differs from raw stream")
    return rows, markers


def step_summary(rows, mode, hz):
    times = sorted(int(row["elapsed_ns"]) for row in rows)
    event_summaries = pilot_summary(rows, hz, mode)
    return {"samples": len(rows), "median_ns": statistics.median(times),
            "p99_ns": times[math.ceil(len(times) * 0.99) - 1],
            "total_ns": sum(times),
            "allocation_bytes": None if mode == "timing" else
            sum(int(row["allocation_bytes"]) for row in rows),
            "peak_rss_delta_bytes": max(int(row["rss_delta_bytes"]) for row in rows),
            "event_only_full": event_summaries["event_only_full"],
            "event_only_final_minute": event_summaries["event_only_final_minute"]}


def interval(a, b, hz, metric, draws):
    return bootstrap_ratio(a, b, hz, metric=metric, draws=draws, seed=17017)


def upper_within(a, b, hz, metric, limit, label, draws, report=None):
    for window, first, second in (("full", a, b),
                                  ("final_minute", a[-60 * hz:], b[-60 * hz:])):
        if metric == "total" and all(int(row["elapsed_ns"]) == 0 for row in first):
            require(all(int(row["elapsed_ns"]) == 0 for row in second),
                    f"{label} {window} positive allocation against zero baseline")
            result = {"lower_95": 1.0, "upper_95": 1.0, "draws": draws,
                      "zero_baseline": True}
        else:
            result = interval(first, second, hz, metric, draws)
        if report is not None:
            report.write(json.dumps({"kind": "budget_interval", "label": label,
                                     "window": window, "metric": metric, "limit": limit,
                                     **result}, sort_keys=True) + "\n")
        require(result["upper_95"] <= limit,
                f"{label} {window} 95% upper bound exceeds {limit}")


def allocation_rows(rows):
    return [{"elapsed_ns": row["allocation_bytes"]} for row in rows]


def scalar_interval(first, second, draws):
    require(len(first) == len(second) == 3 and
            all(value >= 0 for value in first + second),
            "scalar comparison needs three nonnegative matched processes")
    if all(value == 0 for value in first):
        require(all(value == 0 for value in second),
                "positive allocation against zero baseline")
        return {"lower_95": 1.0, "upper_95": 1.0, "draws": draws,
                "zero_baseline": True}
    rng = random.Random(17017)
    ratios = []
    for _ in range(draws):
        picks = [rng.randrange(3) for _ in range(3)]
        require(sum(first[index] for index in picks) > 0,
                "scalar baseline resample has zero denominator")
        ratios.append(sum(second[index] for index in picks) /
                      sum(first[index] for index in picks))
    ordered = sorted(ratios)
    return {"lower_95": ordered[math.ceil(0.025 * len(ordered)) - 1],
            "upper_95": ordered[math.ceil(0.975 * len(ordered)) - 1],
            "draws": draws}


def check_budgets(captures, scenarios, policy, draws, report=None):
    budgets = policy["budgets"]
    assignments = {row["id"]: row["size_assignment"] for row in policy["runtime_rows"]}
    measured = {capture_key(item): (item, rows, markers)
                for item, rows, markers in captures if item["kind"] == "measure"}
    for key, (item, rows, markers) in measured.items():
        row_id, scenario_id, mode, repeat = key
        scenario = scenarios[scenario_id]
        if (scenario["api"] == "baseline" or
                assignments[row_id][scenario["size"]] == "report_only"):
            continue
        hz = scenario["rate_hz"]
        direct_id = scenario_id.rsplit(".", 1)[0] + ".direct_kotlin"
        base_id = scenario_id.rsplit(".", 1)[0] + ".baseline"
        if mode == "timing":
            limit = 1_000_000_000 / (4 * hz)
            for series in (rows, rows[-60 * hz:]):
                times = sorted(int(row["elapsed_ns"]) for row in series)
                require(times[math.ceil(0.99 * len(times)) - 1] <= limit,
                        "absolute p99 timestep/4 budget exceeded")
        if row_id == "jvm.java":
            baseline = measured[(row_id, base_id, mode, repeat)]
            before = baseline[1]
            if mode == "timing":
                for metric, limit_name in (("median", "median_ratio_max"),
                                           ("p99", "p99_ratio_max"),
                                           ("total", "compute_per_simulated_second_ratio_max")):
                    upper_within(before, rows, hz, metric,
                                 budgets["jvm_vs_baseline"][limit_name],
                                 f"{row_id}:{scenario_id}:r{repeat}:JVM {limit_name}",
                                 draws, report)
            elif mode == "allocation":
                upper_within(allocation_rows(before), allocation_rows(rows), hz, "total",
                             budgets["jvm_vs_baseline"]["steady_allocation_ratio_max"],
                             f"{row_id}:{scenario_id}:r{repeat}:JVM steady allocation",
                             draws, report)
                require(int(markers["construction_allocated_bytes"]) <=
                        int(baseline[2]["construction_allocated_bytes"]) *
                        budgets["jvm_vs_baseline"]["construction_or_replacement_allocation_ratio_max"],
                        "JVM construction allocation budget exceeded")
                if scenario["family"] == "lifecycle" and scenario["variant"] == "replace":
                    events_before = [row for row in before if int(row["mutation_ns"]) > 0]
                    events_after = [row for row in rows if int(row["mutation_ns"]) > 0]
                    require(events_before and len(events_before) == len(events_after),
                            "replacement allocation events differ")
                    upper_within(allocation_rows(events_before), allocation_rows(events_after),
                                 1, "total",
                                 budgets["jvm_vs_baseline"]["construction_or_replacement_allocation_ratio_max"],
                                 f"{row_id}:{scenario_id}:r{repeat}:JVM replacement allocation",
                                 draws, report)
            elif mode == "memory":
                require(int(markers["retained_heap_world_alive_bytes"]) <=
                        int(baseline[2]["retained_heap_world_alive_bytes"]) *
                        budgets["jvm_vs_baseline"]["retained_heap_ratio_max"],
                        "JVM retained heap budget exceeded")
        if scenario["api"] == "compatibility":
            direct = measured[(row_id, direct_id, mode, repeat)]
            before = direct[1]
            if mode == "timing":
                for metric, limit_name in (("median", "median_ratio_max"),
                                           ("p99", "p99_ratio_max"),
                                           ("total", "total_compute_ratio_max")):
                    upper_within(before, rows, hz, metric,
                                 budgets["shim_vs_direct"][limit_name],
                                 f"{row_id}:{scenario_id}:r{repeat}:shim {limit_name}",
                                 draws, report)
            elif mode == "allocation":
                require(sum(int(row["allocation_bytes"]) for row in rows) -
                        sum(int(row["allocation_bytes"]) for row in before) <=
                        budgets["shim_vs_direct"]["adaptation_allocation_bytes_max"],
                        "shim adaptation allocation budget exceeded")
    for mode, marker, limit_name in (("allocation", "construction_allocated_bytes",
                                      "construction_or_replacement_allocation_ratio_max"),
                                     ("memory", "retained_heap_world_alive_bytes",
                                      "retained_heap_ratio_max")):
        for scenario in scenarios.values():
            if (scenario["api"] == "baseline" or scenario["size"] == "stress" or
                    assignments["jvm.java"][scenario["size"]] == "report_only"):
                continue
            row_id = "jvm.java"
            if (row_id, scenario["id"], mode, 1) not in measured:
                continue
            base_id = scenario["id"].rsplit(".", 1)[0] + ".baseline"
            before = [int(measured[(row_id, base_id, mode, repeat)][2][marker])
                      for repeat in (1, 2, 3)]
            after = [int(measured[(row_id, scenario["id"], mode, repeat)][2][marker])
                     for repeat in (1, 2, 3)]
            scalar = scalar_interval(before, after, draws)
            if report is not None:
                report.write(json.dumps({"kind": "scalar_budget_interval",
                                         "scenario_id": scenario["id"],
                                         "metric": limit_name, **scalar,
                                         "limit": budgets["jvm_vs_baseline"][limit_name]},
                                        sort_keys=True) + "\n")
            require(scalar["upper_95"] <= budgets["jvm_vs_baseline"][limit_name],
                    f"JVM {limit_name} 95% upper bound exceeded")


def _verify_archive(root, key, expected_source_commit, policy):
    root = Path(root).resolve()
    approved_gate(policy)
    require(len(key) >= 32, "trusted key is too short")
    index = json.loads((root / "archive.json").read_text())
    require(index.get("schema") == 1 and index.get("route") == "sustained-raw-v1",
            "sustained archive schema differs")
    require(index.get("capture_tool_sha256") == sha256(Path(__file__)),
            "sustained capture tool source differs")
    require(hmac.compare_digest(index.get("signature", ""), signature(index, key)),
            "archive signature differs from trusted key")
    manifest_hash = (sha256(MANIFEST_FILE) if policy == manifest() else
                     hashlib.sha256(canonical(policy)).hexdigest())
    require(index["manifest_sha256"] == manifest_hash and
            index["scenario_ids"] == [item["id"] for item in policy["scenarios"]] and
            len(index["scenario_ids"]) == len(set(index["scenario_ids"])),
            "frozen manifest or scenario inventory differs")
    artifacts = verify_source_and_artifacts(root, index, expected_source_commit, policy)
    references = verify_references(root, index, policy)
    scenarios = {item["id"]: item for item in policy["scenarios"]}
    captures = index["captures"]
    groups = {name: {} for name in ("measure", "report", "noise", "plateau")}
    process_keys = set()
    raw_hashes = set()
    for item in captures:
        require(item["row_id"] in references and item["scenario_id"] in scenarios and
                item["source_commit"] == index["source_commit"],
                "capture row, scenario, or source differs")
        key_id = capture_key(item)
        group = groups[item["kind"]]
        require(key_id not in group, "duplicate capture key")
        process_key = (item["host"]["hostname"], item["pid"], item["started_ns"])
        require(process_key not in process_keys, "fresh process identity reused")
        process_keys.add(process_key)
        require(item["raw_sha256"] not in raw_hashes, "raw stream reused across fresh processes")
        raw_hashes.add(item["raw_sha256"])
        group[key_id] = item
    require(set(groups["measure"]) == required_measurements(policy),
            "required sustained measurement matrix is partial or extra")
    require(set(groups["report"]) == required_reports(policy),
            "stress report matrix is partial or extra")
    require(set(groups["noise"]) == required_noise(policy),
            "unchanged baseline noise calibration matrix is partial or extra")
    require(set(groups["plateau"]) == required_plateaus(policy),
            "100-cycle plateau matrix is partial or extra")
    indexed_files = {item[field] for item in captures for field in
                     ("raw_path", "stderr_path", "provider_path", "clock_path",
                      "warmup_clock_path", "memory_path", "resource_path", "run_path",
                      "stress_monitor_path", "stress_monitor_receipt_path", "clock_origin_path",
                      "clock_origin_receipt_path", "process_image_receipt_path")
                     if field in item}
    actual_files = {str(path.relative_to(root)) for base in
                    ((root / "runs"), (root / "parts")) for path in base.rglob("*")
                    if path.is_file() and "runs" in path.relative_to(root).parts}
    require(indexed_files == actual_files, "unindexed or missing raw process file")
    for row in policy["runtime_rows"]:
        row_id = row["id"]
        for scenario in policy["scenarios"]:
            if scenario["size"] == "stress" or scenario["api"] != "baseline":
                continue
            stem = scenario["id"].rsplit(".", 1)[0]
            for mode in MODES:
                previous_end = -1
                for repeat, order in enumerate(balanced_orders(), 1):
                    selected = [api for api in order if api != "baseline" or row_id == "jvm.java"]
                    items = [groups["measure"][(row_id, f"{stem}.{api}", mode, repeat)]
                             for api in selected]
                    require([item["sequence"] for item in items] == list(range(1, len(items) + 1)) and
                            [item["started_ns"] for item in items] ==
                            sorted(item["started_ns"] for item in items) and
                            previous_end < items[0]["started_ns"] and
                            all(first["ended_ns"] < second["started_ns"]
                                for first, second in zip(items, items[1:])),
                            "fresh measurement process order differs from balanced policy")
                    previous_end = items[-1]["ended_ns"]
            latest_noise = max(groups["noise"][(row_id, scenario["id"], repeat, side)]["ended_ns"]
                               for repeat in (1, 2, 3) for side in ("a", "b"))
            earliest_candidate = min(groups["measure"][(row_id, f"{stem}.{api}", mode, repeat)]["started_ns"]
                                     for api in ROUTES[1:] for mode in MODES
                                     for repeat in (1, 2, 3))
            require(latest_noise < earliest_candidate,
                    "noise calibration was not completed before candidate runs")
    analysis_partial = root / "analysis.partial.jsonl"
    with analysis_partial.open("w") as analysis:
        calibration_intervals, maximum_noise_upper, inconclusive_event_tails = analyze_groups(
            root, groups, scenarios, references, artifacts, policy, index, analysis)
    analysis_path = root / "analysis.jsonl"
    analysis_partial.replace(analysis_path)
    return {"qualification": "passed", "source_commit": index["source_commit"],
            "reference_rows": len(references), "scenario_ids": len(scenarios),
            "measurements": len(groups["measure"]), "stress_reports": len(groups["report"]),
            "noise_runs": len(groups["noise"]), "noise_intervals": calibration_intervals,
            "maximum_noise_upper_95": maximum_noise_upper,
            "inconclusive_event_tails": inconclusive_event_tails,
            "analysis_path": str(analysis_path), "analysis_sha256": sha256(analysis_path),
            "plateaus": len(groups["plateau"])}


def analyze_groups(root, groups, scenarios, references, artifacts, policy, index, analysis):
    calibration_intervals = 0
    maximum_noise_upper = 0.0
    inconclusive_event_tails = 0
    for row in policy["runtime_rows"]:
        row_id = row["id"]
        for scenario in policy["scenarios"]:
            if scenario["api"] != "baseline":
                continue
            stem = scenario["id"].rsplit(".", 1)[0]
            selected_apis = ROUTES if row_id == "jvm.java" else ROUTES[1:]
            if scenario["size"] == "stress":
                for api in selected_apis:
                    for mode in MODES:
                        item = groups["report"][(row_id, f"{stem}.{api}", mode, 1)]
                        verify_capture(root, item, scenarios, references, artifacts, policy, index)
                continue
            local_scenarios = {f"{stem}.{api}": scenarios[f"{stem}.{api}"]
                               for api in selected_apis}
            for repeat in (1, 2, 3):
                a = groups["noise"][(row_id, scenario["id"], repeat, "a")]
                b = groups["noise"][(row_id, scenario["id"], repeat, "b")]
                require(a["sequence"] != b["sequence"] and
                        (a["sequence"] < b["sequence"]) == (repeat != 2) and
                        (a["started_ns"] < b["started_ns"]) == (repeat != 2),
                        "noise calibration order is not balanced")
                first, _ = verify_capture(root, a, scenarios, references, artifacts, policy, index)
                second, _ = verify_capture(root, b, scenarios, references, artifacts, policy, index)
                for window_a, window_b in ((first, second),
                                           (first[-60 * scenario["rate_hz"]:],
                                            second[-60 * scenario["rate_hz"]:])):
                    for metric in ("median", "p99", "total"):
                        value = interval(window_a, window_b, scenario["rate_hz"], metric, 2000)
                        analysis.write(json.dumps({"kind": "noise_interval", "row_id": row_id,
                                                   "scenario_id": scenario["id"],
                                                   "repeat": repeat,
                                                   "window": "full" if window_a is first else "final_minute",
                                                   "metric": metric, **value}, sort_keys=True) + "\n")
                        maximum_noise_upper = max(maximum_noise_upper, value["upper_95"])
                        calibration_intervals += 1
                        limit = approved_gate(policy)["noise_upper_ratio_max"]
                        require(value["lower_95"] >= 1 / limit and
                                value["upper_95"] <= limit,
                                "unchanged-baseline noise calibration is inconclusive")
            for mode in MODES:
                local = []
                for repeat in (1, 2, 3):
                    for api in selected_apis:
                        item = groups["measure"][(row_id, f"{stem}.{api}", mode, repeat)]
                        rows, markers = verify_capture(root, item, scenarios, references,
                                                       artifacts, policy, index)
                        if item["summary"]["event_only_final_minute"]["tail_status"] == "insufficient_samples":
                            inconclusive_event_tails += 1
                        local.append((item, rows, markers))
                check_budgets(local, local_scenarios, policy, 2000, analysis)
            for api in selected_apis:
                item = groups["plateau"][(row_id, f"{stem}.{api}")]
                verify_capture(root, item, scenarios, references, artifacts, policy, index)
    return calibration_intervals, maximum_noise_upper, inconclusive_event_tails


def verify_archive(root, key, expected_source_commit):
    return _verify_archive(root, key, expected_source_commit, frozen_policy())


def initialize_archive(root, config, key):
    root = Path(root).resolve()
    policy = frozen_policy()
    approved_gate(policy)
    require(not root.exists() or not any(root.iterdir()), "archive directory is not empty")
    root.mkdir(parents=True, exist_ok=True)
    require(len(key) >= 32, "trusted key is too short")
    require(len(config["references"]) == 1 and
            set(config["artifacts"]) == set(config["references"]),
            "capture part must describe exactly one reference environment")
    commit = config["source_commit"]
    require(commit == subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                              text=True).strip(), "candidate source is not HEAD")
    require(not subprocess.check_output(["git", "status", "--porcelain", "--",
                                         "dyn4k", "dyn4k-core"], cwd=ROOT),
            "candidate engine source has uncommitted edits")
    artifacts = {}
    for row_id, modules in config["artifacts"].items():
        artifacts[row_id] = {}
        for name, path_text in modules.items():
            path = Path(path_text).resolve(strict=True)
            target = root / "artifacts" / row_id / f"{name}{path.suffix}"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            artifacts[row_id][name] = {"staged_path": str(path),
                                        "archive_path": str(target.relative_to(root)),
                                        "sha256": sha256(target)}
    baseline_path = Path(config["baseline_path"]).resolve(strict=True)
    baseline_target = root / "artifacts" / baseline_path.name
    shutil.copyfile(baseline_path, baseline_target)
    references = config["references"]
    for row_id, reference in references.items():
        require(reference["build_configuration"] == next(row for row in policy["runtime_rows"]
                if row["id"] == row_id)["optimized_build"],
                f"reference build configuration differs: {row_id}")
        receipt_source = Path(reference["build_receipt"].pop("source_path")).resolve(strict=True)
        receipt_target = root / "receipts" / f"{row_id}.build.json"
        receipt_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(receipt_source, receipt_target)
        reference["build_receipt"]["archive_path"] = str(receipt_target.relative_to(root))
        reference["build_receipt"]["sha256"] = sha256(receipt_target)
        probe = reference["probe"]
        source = Path(probe.pop("timer_source_path")).resolve(strict=True)
        target = root / "probes" / f"{row_id}.timer.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        probe["timer_raw"] = str(target.relative_to(root))
        probe["timer_sha256"] = sha256(target)
        allocation_source = Path(probe.pop("allocation_source_path")).resolve(strict=True)
        allocation_target = root / "probes" / f"{row_id}.allocation.csv"
        shutil.copyfile(allocation_source, allocation_target)
        probe["allocation_raw"] = str(allocation_target.relative_to(root))
        probe["allocation_sha256"] = sha256(allocation_target)
        runtime = reference["runtime"]
        executable = Path(runtime["path"]).resolve(strict=True)
        runtime_target = root / "runtimes" / row_id / executable.name
        runtime_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(executable, runtime_target)
        runtime["archive_path"] = str(runtime_target.relative_to(root))
        runtime["sha256"] = sha256(runtime_target)
        harness = reference["harness"]
        harness_source = Path(harness["path"]).resolve(strict=True)
        harness_target = root / "harnesses" / row_id / harness_source.name
        harness_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(harness_source, harness_target)
        harness["archive_path"] = str(harness_target.relative_to(root))
        harness["sha256"] = sha256(harness_target)
        adapter = reference["adapter"]
        adapter_source = Path(adapter["path"]).resolve(strict=True)
        adapter_target = root / "adapters" / row_id / adapter_source.name
        adapter_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(adapter_source, adapter_target)
        adapter["archive_path"] = str(adapter_target.relative_to(root))
        adapter["sha256"] = sha256(adapter_target)
    index = {"schema": 1, "route": "sustained-raw-v1",
             "capture_tool_sha256": sha256(Path(__file__)),
             "manifest_sha256": sha256(MANIFEST_FILE),
             "scenario_ids": [item["id"] for item in policy["scenarios"]],
             "source_commit": commit, "source_trees": source_trees(commit),
             "baseline": {"staged_path": str(baseline_path),
                          "archive_path": str(baseline_target.relative_to(root)),
                          "sha256": sha256(baseline_target)},
             "artifacts": artifacts, "references": references, "captures": []}
    write_index(root, index, key)
    verify_source_and_artifacts(root, index, commit, policy)
    verify_references(root, index, policy, complete=False)
    return index


def capture_one(root, job, key):
    root = Path(root).resolve()
    require(len(key) >= 32, "trusted key is too short")
    index = json.loads((root / "archive.json").read_text())
    require(hmac.compare_digest(index.get("signature", ""), signature(index, key)),
            "archive signature differs from trusted key")
    require(index.get("capture_tool_sha256") == sha256(Path(__file__)),
            "sustained capture tool source differs")
    expected_fields = {"kind", "row_id", "scenario_id", "mode", "repeat",
                       "sequence", "command"}
    if job.get("kind") == "noise":
        expected_fields.add("side")
    require(set(job) == expected_fields, "capture job fields differ")
    policy = frozen_policy()
    gate = approved_gate(policy)
    scenarios = {item["id"]: item for item in policy["scenarios"]}
    references = verify_references(root, index, policy, complete=False)
    hashes = verify_source_and_artifacts(root, index, index["source_commit"], policy)
    require(job["row_id"] in references and job["scenario_id"] in scenarios,
            "job row or scenario absent from manifest")
    identity = capture_key(job)
    required = {"measure": required_measurements, "report": required_reports,
                "noise": required_noise, "plateau": required_plateaus}
    require(job["kind"] in required and identity in required[job["kind"]](policy),
            "job is not required by frozen protocol")
    require(identity not in {capture_key(item) for item in index["captures"]
                             if item["kind"] == job["kind"]}, "job already captured")
    reference = references[job["row_id"]]
    require(observed_host() == reference["host"], "observed host differs from reference")
    command = job["command"]
    scenario = scenarios[job["scenario_id"]]
    hz = scenario["rate_hz"]
    tail_size = 8 if scenario["api"] != "baseline" else 7
    require(isinstance(command, list) and len(command) >= tail_size and
            all(isinstance(part, str) and part for part in command),
            "capture command is incomplete")
    warmup_steps = int(command[-2] if scenario["api"] != "baseline" else command[-1])
    steps = (1 if job["kind"] == "plateau" else
             (60 if job["kind"] == "report" else policy["sustained"]["measured_wall_seconds"]) * hz)
    tail = [scenario["family"], scenario["variant"], scenario["size"], str(hz),
            str(steps), "plateau" if job["kind"] == "plateau" else job["mode"],
            str(warmup_steps)]
    if scenario["api"] != "baseline":
        tail.append(scenario["api"])
    require(120 * hz <= warmup_steps <= 600 * hz and
            command == command_prefix(reference, policy, job["row_id"],
                                      index["artifacts"], index["baseline"]) + tail,
            "capture command, JVM settings, or fixture differs from approved policy")
    require(job["kind"] != "report" or
            not stress_monitor_method(platform.system()).startswith("unsupported_"),
            "unpassed row: external peak RSS monitor is unvalidated")
    runner = Path(command[0]).resolve(strict=True)
    require(str(runner) == command[0] and runner.is_file(), "runner path is not exact")
    serial = len(index["captures"])
    folder = root / "runs" / f"{serial:06d}"
    folder.mkdir(parents=True)
    raw = folder / "steps.csv"
    stderr = folder / "stderr.raw"
    provider = folder / "provider.json"
    image_receipt_path = folder / "process-image.json"
    memory = folder / "memory.csv"
    resource = folder / "resource.csv"
    run_summary = folder / "run.json"
    clock = folder / "clock.csv"
    warmup_clock = folder / "warmup-clock.csv"
    clock_origin = folder / "clock-origin.json"
    clock_origin_receipt = folder / "clock-origin-receipt.json"
    clock_nonce = secrets.token_hex(16)
    stress_monitor = folder / "stress-monitor.csv"
    stress_monitor_receipt = folder / "stress-receipt.json"
    environment = dict(gate["harnesses"][job["row_id"]]["environment"])
    environment.update({"DYN4K_PROVIDER_JSON": str(provider),
                        "DYN4K_MEMORY_CSV": str(memory),
                        "DYN4K_RESOURCE_CSV": str(resource),
                        "DYN4K_RUN_JSON": str(run_summary),
                        "DYN4K_CLOCK_CSV": str(clock),
                        "DYN4K_WARMUP_CLOCK_CSV": str(warmup_clock),
                        "DYN4K_CLOCK_ORIGIN_JSON": str(clock_origin),
                        "DYN4K_CLOCK_NONCE": clock_nonce,
                        "DYN4K_SOURCE_COMMIT": index["source_commit"],
                        "DYN4K_ARTIFACT_HASHES_JSON": json.dumps(hashes[job["row_id"]]),
                        "DYN4K_BASELINE_SHA256": policy["baseline_jar_sha256"]})
    started = time.monotonic_ns()
    with raw.open("wb") as stdout, stderr.open("wb") as error:
        process = subprocess.Popen(command, stdout=stdout, stderr=error, env=environment)
        pid = process.pid
        image_observation = None
        for _ in range(100):
            if process.poll() is not None:
                break
            try:
                observed = observe_process_image(pid)
            except (OSError, ValueError):
                pass
            else:
                if (observed["sha256"] == reference["runtime"]["sha256"] and
                        observed["executable_path"] == reference["runtime"]["path"]):
                    image_observation = observed
                    image_receipt_path.write_text(json.dumps(observed, sort_keys=True) + "\n")
                    break
            time.sleep(0.01)
        termination_reason = None
        stress_peak_rss = None
        terminal_usage = None
        if image_observation is None and process.poll() is None:
            termination_reason = "image_probe_unavailable"
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if image_observation is not None:
            origin = None
            for _ in range(500):
                if clock_origin.is_file():
                    try:
                        origin = json.loads(clock_origin.read_text())
                    except (OSError, ValueError):
                        pass
                    else:
                        if (set(origin) == {"pid", "runtime_ns", "nonce"} and
                                origin["pid"] == pid and
                                type(origin["runtime_ns"]) is int and
                                origin["nonce"] == clock_nonce):
                            break
                        origin = None
                if process.poll() is not None:
                    break
                time.sleep(0.01)
            if origin is None:
                termination_reason = "clock_origin_unavailable"
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            else:
                clock_origin_receipt.write_text(json.dumps({**origin,
                    "method": "host_file_bracket_v1", "host_before_ns": started,
                    "host_after_ns": time.monotonic_ns()}, sort_keys=True) + "\n")
        if job["kind"] == "report" and image_observation is not None and origin is not None:
            peak = 0
            with stress_monitor.open("w", newline="") as monitor_stream:
                writer = csv.writer(monitor_stream)
                writer.writerow(STRESS_MONITOR_FIELDS)
                while True:
                    elapsed = time.monotonic_ns() - started
                    if platform.system() == "Darwin":
                        try:
                            terminal_usage = darwin_wait4_peak_rss(pid, os.WNOHANG)
                        except (OSError, ValueError, ChildProcessError):
                            termination_reason = "monitor_unavailable"
                            break
                        running = terminal_usage is None
                    else:
                        running = process.poll() is None
                    if running:
                        try:
                            rss = peak_rss_bytes(pid, platform.system())
                        except (OSError, ValueError, subprocess.TimeoutExpired):
                            if platform.system() == "Darwin":
                                try:
                                    terminal_usage = darwin_wait4_peak_rss(pid, os.WNOHANG)
                                except (OSError, ValueError, ChildProcessError):
                                    terminal_usage = None
                            if terminal_usage is None:
                                termination_reason = "monitor_unavailable"
                                rss = peak
                            else:
                                running = False
                        if not running:
                            status, terminal_peak = terminal_usage
                            process.returncode = os.waitstatus_to_exitcode(status)
                            peak = max(peak, terminal_peak)
                            termination_reason = "completed"
                            writer.writerow((elapsed, terminal_peak, termination_reason))
                            break
                        peak = max(peak, rss)
                        if elapsed > gate["stress_wall_ns_max"]:
                            termination_reason = "wall_limit"
                        elif peak > gate["stress_rss_bytes_max"]:
                            termination_reason = "rss_limit"
                        writer.writerow((elapsed, rss,
                                         termination_reason or "running"))
                        if termination_reason:
                            process.terminate()
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait()
                            break
                        time.sleep(0.1)
                    else:
                        if platform.system() == "Darwin":
                            status, terminal_peak = terminal_usage
                            process.returncode = os.waitstatus_to_exitcode(status)
                            peak = max(peak, terminal_peak)
                        else:
                            terminal_peak = peak
                        termination_reason = "completed"
                        writer.writerow((elapsed, terminal_peak, termination_reason))
                        break
            stress_peak_rss = peak
            if termination_reason == "monitor_unavailable" and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        returncode = process.wait()
    ended = time.monotonic_ns()
    item = {**job, "status": "complete" if returncode == 0 and
            image_observation is not None and
            termination_reason in (None, "completed") else "failed",
            "source_commit": index["source_commit"], "artifacts": hashes[job["row_id"]],
            "host": observed_host(), "runtime_sha256": reference["runtime"]["sha256"],
            "process_image_sha256": image_observation["sha256"] if image_observation else None,
            "process_image_method": PROCESS_IMAGE_METHODS.get(platform.system()),
            "probe_sha256": reference["probe"]["timer_sha256"],
            "ambient_environment": gate["harnesses"][job["row_id"]]["environment"],
            "build_configuration": reference["build_configuration"],
            "pid": pid, "started_ns": started, "ended_ns": ended,
            "wall_ns": ended - started, "runner_path": str(runner),
            "runner_sha256": sha256(runner), "raw_path": str(raw.relative_to(root)),
            "raw_sha256": sha256(raw), "stderr_path": str(stderr.relative_to(root)),
            "stderr_sha256": sha256(stderr), "exit_code": returncode}
    if image_observation is not None:
        item.update(process_image_receipt_path=str(image_receipt_path.relative_to(root)),
                    process_image_receipt_sha256=sha256(image_receipt_path))
    item["clock_nonce"] = clock_nonce
    for stem, path in (("clock_origin", clock_origin),
                       ("clock_origin_receipt", clock_origin_receipt)):
        if path.is_file():
            item[stem + "_path"] = str(path.relative_to(root))
            item[stem + "_sha256"] = sha256(path)
    if job["kind"] == "report":
        item.update(stress_peak_rss_bytes=stress_peak_rss,
                    termination_reason=termination_reason,
                    stress_monitor_method=stress_monitor_method(platform.system()))
        if stress_monitor.is_file():
            item.update(stress_monitor_path=str(stress_monitor.relative_to(root)),
                        stress_monitor_sha256=sha256(stress_monitor))
            if image_observation is not None:
                with stress_monitor.open(newline="") as stream:
                    sample_count = sum(1 for _ in csv.DictReader(stream))
                stress_monitor_receipt.write_text(json.dumps({
                    "pid": pid, "method": item["stress_monitor_method"],
                    "process_image_sha256": image_observation["sha256"],
                    "process_image_observed_ns": image_observation["observed_ns"],
                    "started_ns": started, "ended_ns": ended,
                    "sample_count": sample_count, "peak_rss_bytes": stress_peak_rss,
                    "termination_reason": termination_reason,
                    "exit_code": returncode,
                    **({"metric_kind": "peak_rss_bytes", "terminal_pid": pid,
                        "terminal_wait_status": terminal_usage[0],
                        "terminal_ru_maxrss_bytes": terminal_usage[1]}
                       if platform.system() == "Darwin" and terminal_usage is not None
                       else {})}, sort_keys=True) + "\n")
                item.update(stress_monitor_receipt_path=str(stress_monitor_receipt.relative_to(root)),
                            stress_monitor_receipt_sha256=sha256(stress_monitor_receipt))
    if provider.is_file():
        item.update(provider_path=str(provider.relative_to(root)),
                    provider_sha256=sha256(provider))
    if memory.is_file():
        item.update(memory_path=str(memory.relative_to(root)),
                    memory_sha256=sha256(memory))
    if resource.is_file():
        item.update(resource_path=str(resource.relative_to(root)),
                    resource_sha256=sha256(resource))
    if run_summary.is_file():
        item.update(run_path=str(run_summary.relative_to(root)),
                    run_sha256=sha256(run_summary))
    if clock.is_file():
        item.update(clock_path=str(clock.relative_to(root)),
                    clock_sha256=sha256(clock))
    if warmup_clock.is_file():
        item.update(warmup_clock_path=str(warmup_clock.relative_to(root)),
                    warmup_clock_sha256=sha256(warmup_clock))
    if returncode == 0:
        try:
            if job["kind"] not in ("noise", "plateau"):
                scenario = next(value for value in policy["scenarios"]
                                if value["id"] == job["scenario_id"])
                item["summary"] = step_summary(csv_rows(raw, STEP_FIELDS), job["mode"],
                                               scenario["rate_hz"])
            scenarios = {scenario["id"]: scenario for scenario in policy["scenarios"]}
            verify_capture(root, item, scenarios, references, hashes, policy, index)
        except (KeyError, OSError, ValueError) as exc:
            item["status"] = "invalid_raw"
            item["error"] = str(exc)
    index["captures"].append(item)
    write_index(root, index, key)
    return {"capture": serial, "status": item["status"], "exit_code": returncode,
            "archive": str(root)}


def merge_parts(output, parts, key, policy=None):
    require(len(key) >= 32, "trusted key is too short")
    policy = frozen_policy() if policy is None else policy
    output = Path(output).resolve()
    require(not output.exists() or not any(output.iterdir()), "merged archive is not empty")
    require(parts, "no reference environment parts were supplied")
    output.mkdir(parents=True, exist_ok=True)
    merged = None

    def copy_record(part, record, path_key, hash_key, prefix):
        source = checked_file(part, record, path_key, hash_key)
        destination = output / prefix / record[path_key]
        destination.parent.mkdir(parents=True, exist_ok=True)
        require(not destination.exists(), "duplicate merged raw path")
        shutil.copyfile(source, destination)
        record[path_key] = str(destination.relative_to(output))

    for part_text in parts:
        part = Path(part_text).resolve()
        index = json.loads((part / "archive.json").read_text())
        require(hmac.compare_digest(index.get("signature", ""), signature(index, key)),
                "part signature differs from trusted key")
        if merged is None:
            merged = {name: copy.deepcopy(index[name]) for name in
                      ("schema", "route", "capture_tool_sha256", "manifest_sha256", "scenario_ids",
                       "source_commit", "source_trees", "baseline")}
            merged.update(artifacts={}, references={}, captures=[])
            copy_record(part, merged["baseline"], "archive_path", "sha256", "")
        else:
            for field in ("schema", "route", "capture_tool_sha256", "manifest_sha256", "scenario_ids",
                          "source_commit", "source_trees"):
                require(index[field] == merged[field], f"part {field} differs")
            require(index["baseline"]["sha256"] == merged["baseline"]["sha256"],
                    "part baseline artifact differs")
        verify_source_and_artifacts(part, index, merged["source_commit"], policy)
        references = verify_references(part, index, policy, complete=False)
        require(len(references) == 1, "each capture part must own one reference row")
        row_id = next(iter(references))
        require(row_id not in merged["references"], "duplicate reference row in merge")
        prefix = Path("parts") / row_id
        reference = copy.deepcopy(references[row_id])
        copy_record(part, reference["probe"], "timer_raw", "timer_sha256", prefix)
        copy_record(part, reference["probe"], "allocation_raw", "allocation_sha256", prefix)
        copy_record(part, reference["runtime"], "archive_path", "sha256", prefix)
        copy_record(part, reference["harness"], "archive_path", "sha256", prefix)
        copy_record(part, reference["adapter"], "archive_path", "sha256", prefix)
        copy_record(part, reference["build_receipt"], "archive_path", "sha256", prefix)
        merged["references"][row_id] = reference
        modules = copy.deepcopy(index["artifacts"][row_id])
        for record in modules.values():
            copy_record(part, record, "archive_path", "sha256", prefix)
        merged["artifacts"][row_id] = modules
        for source_item in index["captures"]:
            require(source_item["row_id"] == row_id, "capture part crosses reference rows")
            item = copy.deepcopy(source_item)
            for path_key, hash_key in (("raw_path", "raw_sha256"),
                                       ("stderr_path", "stderr_sha256"),
                                       ("provider_path", "provider_sha256"),
                                       ("process_image_receipt_path", "process_image_receipt_sha256"),
                                       ("clock_path", "clock_sha256"),
                                       ("warmup_clock_path", "warmup_clock_sha256"),
                                       ("memory_path", "memory_sha256"),
                                       ("resource_path", "resource_sha256"),
                                       ("run_path", "run_sha256"),
                                       ("stress_monitor_path", "stress_monitor_sha256"),
                                       ("stress_monitor_receipt_path", "stress_monitor_receipt_sha256"),
                                       ("clock_origin_path", "clock_origin_sha256"),
                                       ("clock_origin_receipt_path", "clock_origin_receipt_sha256")):
                if path_key in item:
                    copy_record(part, item, path_key, hash_key, prefix)
            merged["captures"].append(item)
    require(set(merged["references"]) == {row["id"] for row in policy["runtime_rows"]},
            "merged reference environment rows are partial")
    write_index(output, merged, key)
    if policy == manifest():
        return verify_archive(output, key, merged["source_commit"])
    return _verify_archive(output, key, merged["source_commit"], policy)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("init", "capture", "merge", "verify", "plan"))
    parser.add_argument("--archive")
    parser.add_argument("--config")
    parser.add_argument("--job")
    parser.add_argument("--part", action="append")
    parser.add_argument("--trusted-key")
    parser.add_argument("--expected-source-commit")
    args = parser.parse_args()
    try:
        if args.command == "plan":
            policy = frozen_policy()
            result = {"scenario_ids": len(policy["scenarios"]),
                      "runtime_rows": len(policy["runtime_rows"]),
                      "measurements": len(required_measurements(policy)),
                      "stress_reports": len(required_reports(policy)),
                      "noise_runs": len(required_noise(policy)),
                      "plateaus": len(required_plateaus(policy))}
        else:
            require(args.archive and args.trusted_key, "archive and trusted key are required")
            require_external_key(args.trusted_key, [args.archive, *(args.part or [])])
            key = Path(args.trusted_key).read_bytes()
            require(len(key) >= 32, "trusted key is too short")
            if args.command == "init":
                require(args.config, "init needs a reference config")
                result = initialize_archive(args.archive, json.loads(Path(args.config).read_text()), key)
                result = {"archive": str(args.archive), "reference_rows": len(result["references"])}
            elif args.command == "capture":
                require(args.job, "capture needs a job")
                result = capture_one(args.archive, json.loads(Path(args.job).read_text()), key)
            elif args.command == "merge":
                result = merge_parts(args.archive, args.part or [], key)
            else:
                require(args.expected_source_commit, "verify needs expected source commit")
                result = verify_archive(args.archive, key, args.expected_source_commit)
        print(json.dumps(result, indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"qualification": "unpassed", "reason": str(exc)}, sort_keys=True))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
