#!/usr/bin/env python3

import argparse
import copy
import csv
import ctypes
from ctypes import wintypes
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
from stress_monitor import (PROCESS_MEMORY_COUNTERS, darwin_wait4_peak_rss,
                            peak_rss_bytes, stress_monitor_method)


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
FROZEN_MANIFEST_SHA256 = "18cca97bbf1fc939eda669efe2344bbfe06c416a735ca8cc5184d5ba2519176a"


def wait4_peak_rss(pid, options, system):
    if system == "Darwin":
        return darwin_wait4_peak_rss(pid, options)
    require(system == "Linux" and type(pid) is int and pid > 0,
            "Linux terminal usage PID is invalid")
    observed_pid, status, usage = os.wait4(pid, options)
    if observed_pid == 0 and options & os.WNOHANG:
        return None
    require(observed_pid == pid and type(status) is int and usage is not None and
            type(usage.ru_maxrss) is int and usage.ru_maxrss > 0,
            "Linux terminal wait4 usage is invalid")
    return status, usage.ru_maxrss * 1024


def windows_peak_handle(pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.GetProcessId.argtypes = [ctypes.c_void_p]
    kernel.GetProcessId.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise OSError("Windows terminal peak process handle is unavailable")
    if kernel.GetProcessId(handle) != pid:
        kernel.CloseHandle(handle)
        raise ValueError("Windows terminal peak handle PID differs")
    return handle


def windows_terminal_peak(handle, pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetProcessId.argtypes = [ctypes.c_void_p]
    kernel.GetProcessId.restype = wintypes.DWORD
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p,
                                           ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
                                           wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    require(kernel.GetProcessId(handle) == pid, "Windows terminal peak handle PID differs")
    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        raise OSError("Windows terminal peak working set is unavailable")
    require(counters.PeakWorkingSetSize > 0, "Windows terminal peak working set is invalid")
    return counters.PeakWorkingSetSize


def close_windows_peak_handle(handle):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.CloseHandle(handle)


def frozen_policy():
    require(sha256(MANIFEST_FILE) == FROZEN_MANIFEST_SHA256,
            "independently frozen manifest digest differs")
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
        (row["id"], item["id"].rsplit(".", 1)[0] +
         (".baseline" if row["id"] == "jvm.java" else ".direct_kotlin"),
         mode, repeat, side)
        for row in policy["runtime_rows"]
        for item in policy["scenarios"]
        if item["size"] != "stress" and item["api"] == "baseline"
        for mode in MODES
        for repeat in (1, 2, 3)
        for side in ("a", "b")
    }


def comparison_control_keys(policy):
    keys = set()
    for row in policy["runtime_rows"]:
        row_id = row["id"]
        for scenario in policy["scenarios"]:
            if scenario["size"] == "stress" or scenario["api"] == "baseline":
                continue
            comparisons = []
            if row_id == "jvm.java":
                comparisons.append("jvm_vs_dyn4j")
            if scenario["api"] == "compatibility":
                comparisons.append("shim_vs_direct")
            if row["size_assignment"][scenario["size"]] != "report_only":
                for window in ("full", "final_minute"):
                    keys.add("|".join(("absolute_timing", row_id, scenario["id"],
                                       "timing", "p99", window)))
                    keys.add("|".join(("absolute_memory", row_id, scenario["id"],
                                       "memory", "attributed_workload_peak_bytes", window)))
            for comparison in comparisons:
                for mode, metrics in (("timing", ("median", "p99", "total")),
                                      ("allocation", ("total",)),
                                      ("memory", ("retained_heap_world_alive_bytes",))):
                    windows = ("full",) if mode == "memory" else ("full", "final_minute")
                    for metric in metrics:
                        for window in windows:
                            keys.add("|".join((comparison, row_id, scenario["id"],
                                               mode, metric, window)))
                keys.add("|".join((comparison, row_id, scenario["id"],
                                   "allocation", "construction_allocated_bytes", "full")))
    return keys


def noise_limit_lookup(policy):
    result = {}
    for assignment, limit in policy["sustained_gate"]["noise_upper_ratio_max"].items():
        _, row_id, scenario_id, mode, metric, window = assignment.split("|")
        stem = scenario_id.rsplit(".", 1)[0]
        key = (row_id, stem, mode, metric, window)
        result[key] = min(result.get(key, limit), limit)
    return result


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
    control_keys = comparison_control_keys(policy)
    controls = gate.get("noise_controls")
    assignments = gate.get("comparison_controls")
    limits = gate.get("noise_upper_ratio_max")
    require(isinstance(controls, dict) and set(controls) == rows and
            isinstance(assignments, dict) and set(assignments) == control_keys and
            isinstance(limits, dict) and set(limits) == control_keys and
            all(assignments[key] == key.split("|")[1] for key in control_keys) and
            all(type(limits[key]) in (int, float) and math.isfinite(limits[key]) and
                limits[key] >= 1 for key in control_keys),
            "unpassed policy: frozen comparison control map or noise limits are absent")
    stress_limits = gate.get("stress_limits")
    require(isinstance(gate.get("harnesses"), dict) and
            set(gate["harnesses"]) == rows and
            isinstance(stress_limits, dict) and set(stress_limits) == rows and
            all(isinstance(limit, dict) and set(limit) == {
                "row_id", "wall_stop_ns", "wall_max_ns", "rss_stop_bytes",
                "rss_max_bytes", "rss_metric_kind", "reference_overhead_sha256",
                "monitor_validation_sha256", "host_capacity_sha256"} and
                limit["row_id"] == row_id and
                limit["rss_metric_kind"] in ("peak_rss_bytes", "peak_working_set_bytes") and
                all(type(limit[name]) is int and limit[name] > 0 for name in
                    ("wall_stop_ns", "wall_max_ns", "rss_stop_bytes", "rss_max_bytes")) and
                limit["wall_stop_ns"] < limit["wall_max_ns"] and
                limit["rss_stop_bytes"] < limit["rss_max_bytes"] and
                all(isinstance(limit[name], str) and len(limit[name]) == 64 and
                    all(char in "0123456789abcdef" for char in limit[name]) for name in
                    ("reference_overhead_sha256", "monitor_validation_sha256",
                     "host_capacity_sha256")) for row_id, limit in stress_limits.items()),
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
                 harness.get("sidecar_protocol") in ("jvm-v2", "legacy-v1") and
                 "-cp" in prefix and all(any("{" + name + "}" in part for part in prefix)
                    for name in ("baseline", "core", "kotlin"))),
                f"unpassed policy: approved harness or fixture differs: {row_id}")
        control = controls[row_id]
        expected_kind = "dyn4j_6_0_0" if row_id == "jvm.java" else "same_target_port"
        require(control.get("kind") == expected_kind and
                control.get("optimized_build") == next(row for row in policy["runtime_rows"]
                    if row["id"] == row_id)["optimized_build"] and
                isinstance(control.get("source_commit"), str) and
                len(control["source_commit"]) == 40 and
                isinstance(control.get("artifact_sha256"), dict) and
                set(control["artifact_sha256"]) == {"core", "kotlin"} and
                isinstance(control["artifact_sha256"]["core"], str) and
                len(control["artifact_sha256"]["core"]) == 64 and
                ((control["artifact_sha256"]["kotlin"] == policy["baseline_jar_sha256"] and
                  control["artifact_sha256"]["core"] == policy["baseline_jar_sha256"])
                 if row_id == "jvm.java" else
                 isinstance(control["artifact_sha256"]["kotlin"], str) and
                 len(control["artifact_sha256"]["kotlin"]) == 64) and
                control.get("harness_sha256") == harness["sha256"] and
                control.get("adapter_sha256") == harness["adapter_sha256"] and
                isinstance(control.get("runtime_sha256"), str) and
                len(control["runtime_sha256"]) == 64 and
                isinstance(control.get("probe_sha256"), str) and
                len(control["probe_sha256"]) == 64 and
                (row_id == "jvm.java" or
                 isinstance(control.get("build_receipt_sha256"), str) and
                 len(control["build_receipt_sha256"]) == 64),
                f"unpassed policy: independently frozen noise control differs: {row_id}")
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
                policy["sustained_gate"]["harnesses"][row_id]["command_prefix"]]
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


def control_artifacts(root, index, policy):
    controls = policy["sustained_gate"]["noise_controls"]
    records = index.get("control_artifacts")
    require(isinstance(records, dict) and
            set(records) == {row_id for row_id in index["references"] if row_id != "jvm.java"},
            "independent noise control artifact inventory differs")
    receipts = index.get("control_build_receipts")
    require(isinstance(receipts, dict) and set(receipts) == set(records),
            "independent noise control build receipt inventory differs")
    result = {}
    for row_id in index["references"]:
        if row_id == "jvm.java":
            result[row_id] = {name: index["baseline"] for name in ("core", "kotlin")}
            continue
        modules = records[row_id]
        require(set(modules) == {"core", "kotlin"},
                f"independent noise control modules differ: {row_id}")
        for name, record in modules.items():
            checked_file(root, record, "archive_path", "sha256")
            staged = Path(record["staged_path"])
            local_host = index["references"][row_id]["host"] == observed_host()
            require(record["sha256"] == controls[row_id]["artifact_sha256"][name] and
                    record["sha256"] != index["artifacts"][row_id][name]["sha256"] and
                    staged.is_absolute() and
                    (not local_host or staged.is_file() and sha256(staged) == record["sha256"]),
                    f"independent optimized noise control bytes differ: {row_id}:{name}")
        receipt_record = receipts[row_id]
        require(receipt_record["sha256"] == controls[row_id]["build_receipt_sha256"],
                f"independent noise control build receipt digest differs: {row_id}")
        receipt = json.loads(checked_file(root, receipt_record, "archive_path",
                                          "sha256").read_text())
        require(receipt == {"source_commit": controls[row_id]["source_commit"],
                            "artifact_sha256": controls[row_id]["artifact_sha256"],
                            "build_configuration": controls[row_id]["optimized_build"],
                            "target": next(row["target"] for row in policy["runtime_rows"]
                                           if row["id"] == row_id),
                            "status": "built_from_frozen_control_source"},
                f"independent optimized noise control build receipt differs: {row_id}")
        result[row_id] = modules
    return result


def verify_references(root, index, policy, complete=True):
    gate = approved_gate(policy)
    rows = {item["id"]: item for item in policy["runtime_rows"]}
    references = index["references"]
    require((set(references) == set(rows) if complete else
             bool(references) and set(references).issubset(rows)),
            "reference environment rows differ")
    for row_id, reference in references.items():
        row = rows[row_id]
        control = gate["noise_controls"][row_id]
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
        require(control["runtime_sha256"] == runtime["sha256"] and
                control["harness_sha256"] == harness["sha256"] and
                control["adapter_sha256"] == adapter["sha256"] and
                control["probe_sha256"] == probe["timer_sha256"] and
                control["source_commit"] != index["source_commit"] and
                (row_id != "jvm.java" or
                 control["source_commit"] == policy["source_commit"]),
                f"independent optimized noise control identity differs: {row_id}")
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


def validate_steps(rows, scenario, mode, policy, partial=False):
    hz = scenario["rate_hz"]
    count = policy["families"][scenario["family"]][scenario["size"]]
    steps = (60 if scenario["size"] == "stress" else
             policy["sustained"]["measured_wall_seconds"]) * hz
    require((0 < len(rows) < steps if partial else len(rows) == steps) and
            [int(row["step"]) for row in rows] == list(range(len(rows))),
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
        sampled = position % hz == 0 or (not partial and position == steps - 1)
        for field in ("broadphase_candidates", "active_contact_pairs", "active_contact_points"):
            value = int(row[field])
            require(value >= 0 if sampled else value == -1,
                    f"missing or extra sampled {field} at step {position}")
        for field in ("linear_speed_sum_m_per_s", "angular_speed_sum_rad_per_s"):
            value = float(row[field])
            require(math.isfinite(value) and value >= 0, f"invalid {field} at step {position}")
    if not partial:
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
    limit = policy["sustained_gate"]["stress_limits"][item["row_id"]]
    system = item["host"]["system"]
    metric_kind = "peak_working_set_bytes" if system == "Windows" else "peak_rss_bytes"
    reason = item.get("termination_reason")
    limited = reason in ("wall_limit", "rss_limit")
    require(item.get("stress_monitor_method") ==
            stress_monitor_method(item["host"]["system"]) and
            not item["stress_monitor_method"].startswith("unsupported_"),
            "unpassed row: external peak RSS monitor is unvalidated")
    require(limit["rss_metric_kind"] == metric_kind and
            item["wall_ns"] <= limit["wall_max_ns"] and
            type(item.get("stress_peak_rss_bytes")) is int and
            item["stress_peak_rss_bytes"] <= limit["rss_max_bytes"],
            "stress wall, memory, or termination ceiling invalid")
    require((item["status"] == "capacity_limited" and type(item["exit_code"]) is int and
             item["exit_code"] != 0) if limited else
            (reason == "completed" and item["status"] == "complete" and
             item["exit_code"] == 0),
            "stress capacity stop or completed termination differs")
    rows = csv_rows(checked_file(root, item, "stress_monitor_path",
                                 "stress_monitor_sha256"), STRESS_MONITOR_FIELDS)
    elapsed = [int(row["elapsed_ns"]) for row in rows]
    rss = [int(row["rss_bytes"]) for row in rows]
    require(len(rows) >= (1 if limited else 2) and elapsed[0] >= 0 and
            item["started_ns"] + elapsed[0] >= image_receipt["observed_ns"] and
            elapsed == sorted(set(elapsed)) and
            elapsed[-1] <= item["wall_ns"] and
            all(0 < value <= limit["rss_max_bytes"] for value in rss) and
            (system == "Darwin" or rss == sorted(rss)) and
            max(rss) == item["stress_peak_rss_bytes"] and
            all(row["action"] == "running" for row in rows[:-1]) and
            rows[-1]["action"] == reason and
            ((elapsed[-1] >= limit["wall_stop_ns"] if reason == "wall_limit" else
              item["stress_peak_rss_bytes"] >= limit["rss_stop_bytes"])
             if limited else
             elapsed[-1] < limit["wall_stop_ns"] and
             item["stress_peak_rss_bytes"] < limit["rss_stop_bytes"]),
            "stress monitor stream or termination receipt invalid")
    receipt = json.loads(checked_file(root, item, "stress_monitor_receipt_path",
                                      "stress_monitor_receipt_sha256").read_text())
    terminal_fields = ({"metric_kind", "terminal_pid", "terminal_observed_ns"} |
                       ({"terminal_exit_code", "terminal_peak_working_set_bytes"}
                        if system == "Windows" else
                        {"terminal_wait_status", "terminal_ru_maxrss_bytes"}))
    stop_fields = {"stop_action", "stop_requested_ns", "stop_dispatched_ns"} if limited else set()
    terminal_peak_field = ("terminal_peak_working_set_bytes" if system == "Windows" else
                           "terminal_ru_maxrss_bytes")
    terminal_status_valid = (
        type(receipt.get("terminal_exit_code")) is int and
        receipt["terminal_exit_code"] == item["exit_code"] if system == "Windows" else
        type(receipt.get("terminal_wait_status")) is int and
        os.waitstatus_to_exitcode(receipt["terminal_wait_status"]) == item["exit_code"])
    stop_status_valid = (not limited or
        (receipt.get("stop_action") in ("terminate", "kill") and
         type(receipt.get("stop_requested_ns")) is int and
         type(receipt.get("stop_dispatched_ns")) is int and
         item["started_ns"] + elapsed[-1] <= receipt["stop_requested_ns"] <=
         receipt["stop_dispatched_ns"] <= receipt.get("terminal_observed_ns", -1) <=
         item["ended_ns"] and
         (item["exit_code"] == 1 if system == "Windows" else
          os.WIFSIGNALED(receipt["terminal_wait_status"]) and
          os.WTERMSIG(receipt["terminal_wait_status"]) ==
          (15 if receipt["stop_action"] == "terminate" else 9))))
    require(set(receipt) == {"pid", "method", "process_image_sha256",
                             "process_image_observed_ns", "started_ns", "ended_ns",
                             "sample_count", "peak_rss_bytes", "termination_reason",
                             "exit_code"} | terminal_fields | stop_fields and
            all(type(receipt[field]) is int for field in
                ("pid", "process_image_observed_ns", "started_ns", "ended_ns",
                 "sample_count", "peak_rss_bytes", "exit_code", "terminal_pid",
                 "terminal_observed_ns", terminal_peak_field)) and
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
                        **({"stop_action": receipt["stop_action"],
                            "stop_requested_ns": receipt["stop_requested_ns"],
                            "stop_dispatched_ns": receipt["stop_dispatched_ns"]}
                           if limited else {}),
                        "metric_kind": metric_kind,
                        "terminal_pid": item["pid"],
                        "terminal_observed_ns": receipt["terminal_observed_ns"],
                        terminal_peak_field: item["stress_peak_rss_bytes"],
                        **({"terminal_exit_code": receipt["terminal_exit_code"]}
                           if system == "Windows" else
                           {"terminal_wait_status": receipt["terminal_wait_status"]})} and
            terminal_status_valid and stop_status_valid and
            image_receipt["observed_ns"] <= receipt["terminal_observed_ns"] <= item["ended_ns"] and
            rss[-1] == receipt[terminal_peak_field] and
            all(value <= rss[-1] for value in rss[:-1]),
            "stress monitor receipt differs from process image or termination")
    return "capacity_limited" if limited else "completed"


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


def validate_v2_sidecars(root, item, scenario, source_commit, fixture_sha256,
                         provider_path, warm_clock, measured_clock, raw_rows, markers):
    def unique_object(pairs):
        result = {}
        for name, value in pairs:
            require(name not in result, "version 2 duplicate JSON key")
            result[name] = value
        return result

    stems = ("allocation_v2", "memory_v2", "plateau_v2")
    present = [stem for stem in stems if stem + "_path" in item or stem + "_sha256" in item]
    if not present:
        return None
    require(set(present) == set(stems), "version 2 process sidecars are partial")
    mode = item["mode"]
    require(mode in ("allocation", "memory", "plateau"),
            "version 2 sidecars claim an unsupported mode")
    streams = {}
    for stem in stems:
        path = checked_file(root, item, stem + "_path", stem + "_sha256")
        lines = path.read_text().splitlines()
        require(len(lines) <= 100000 and all(line.strip() for line in lines),
                "version 2 sidecar line inventory is invalid")
        streams[stem] = [json.loads(line, object_pairs_hook=unique_object) for line in lines]
        require(all(isinstance(row, dict) for row in streams[stem]),
                "version 2 sidecar row is invalid")
    allocation = streams["allocation_v2"]
    memory = streams["memory_v2"]
    plateau = streams["plateau_v2"]
    expected_steps = 1 if mode == "plateau" else len(raw_rows)
    shared = {"schema": 2, "pid": item["pid"], "nonce": item["clock_nonce"],
              "source_commit": source_commit, "provider_sha256": sha256(provider_path),
              "fixture_sha256": fixture_sha256, "clock_domain": "System.nanoTime",
              "memory_unit": "byte", "api": scenario["api"], "mode": mode,
              "family": scenario["family"], "variant": scenario["variant"],
              "size": scenario["size"], "rate_hz": scenario["rate_hz"],
              "measured_steps": expected_steps, "warmup_steps": len(warm_clock)}
    kind = {"allocation_v2": "thread_allocation", "memory_v2": "memory_observation",
            "plateau_v2": "create_use_dispose"}
    extensions = {
        "allocation_v2": {"phase", "step", "clock_ns", "thread_id",
                          "counter_before_bytes", "counter_after_bytes",
                          "allocation_bytes", "probe"},
        "memory_v2": {"phase", "step", "clock_ns", "heap_used_bytes",
                      "empty_heap_bytes", "managed_heap_delta_bytes",
                      "managed_post_collection", "collection_count_delta",
                      "buffer_pool_used_bytes", "rss_bytes", "native_workload_bytes",
                      "attributed_workload_bytes", "native_attribution",
                      "managed_provenance", "buffer_provenance", "qualification"},
        "plateau_v2": {"cycle", "clock_ns", "heap_after_collection_bytes",
                       "rss_after_collection_bytes", "collection_count",
                       "collection_count_before", "collection_count_after",
                       "collection_count_delta", "collection_count_unit",
                       "collection_probe", "collection_count_status",
                       "cycle_disposed_ns", "collection_before_sample_ns",
                       "gc_requested_ns", "collection_after_sample_ns",
                       "heap_sample_begin_ns", "heap_sample_end_ns",
                       "rss_sample_begin_ns", "rss_sample_end_ns",
                       "managed_heap_delta_bytes", "buffer_pool_used_bytes",
                       "native_workload_bytes", "attributed_workload_bytes",
                       "reserved_runtime_bytes", "native_attribution", "qualification"}}
    origin = json.loads(checked_file(root, item, "clock_origin_path",
                                     "clock_origin_sha256").read_text())
    receipt = json.loads(checked_file(root, item, "clock_origin_receipt_path",
                                      "clock_origin_receipt_sha256").read_text())
    low = receipt["host_before_ns"] - origin["runtime_ns"]
    high = receipt["host_after_ns"] - origin["runtime_ns"]
    for clock in [*warm_clock, *(measured_clock or ())]:
        low = max(low, item["started_ns"] - int(clock["begin_ns"]))
        high = min(high, item["ended_ns"] - int(clock["end_ns"]))
    for stem, rows in streams.items():
        previous = None
        for row in rows:
            require(set(row) == set(shared) | {"kind"} | extensions[stem] and
                    all(type(row.get(field)) is type(value) and row[field] == value
                        for field, value in {**shared, "kind": kind[stem]}.items()) and
                    type(row.get("clock_ns")) is int and
                    row["clock_ns"] >= origin["runtime_ns"] and
                    (previous is None or row["clock_ns"] > previous),
                    "version 2 process, provider, fixture, or clock binding differs")
            stamp = row["clock_ns"]
            low = max(low, item["started_ns"] - stamp)
            high = min(high, item["ended_ns"] - stamp)
            require(low <= high, "version 2 clock lies outside observed process interval")
            previous = stamp
    if mode == "plateau":
        expected_allocation = [("plateau", cycle) for cycle in range(100)]
        require(not memory and len(plateau) == 100 and
                [row.get("cycle") for row in plateau] == list(range(100)),
                "version 2 plateau cycle count or order differs")
    else:
        expected_allocation = ([('construction', 0)] +
                               [('warmup', step) for step in range(len(warm_clock))] +
                               [('measure', step) for step in range(len(raw_rows))])
        require(not plateau, "version 2 plateau stream in measurement mode")
    require([(row.get("phase"), row.get("step")) for row in allocation] ==
            expected_allocation, "version 2 allocation phases or count differ")
    previous_counter = None
    thread = None
    for row in allocation:
        before = row.get("counter_before_bytes")
        after = row.get("counter_after_bytes")
        require(type(before) is int and type(after) is int and 0 <= before <= after and
                (previous_counter is None or before >= previous_counter) and
                type(row.get("allocation_bytes")) is int and
                row["allocation_bytes"] == after - before and
                type(row.get("thread_id")) is int and row["thread_id"] > 0 and
                (thread is None or row["thread_id"] == thread) and
                row.get("probe") ==
                "com.sun.management.ThreadMXBean.getThreadAllocatedBytes",
                "version 2 allocation counter or thread differs")
        previous_counter = after
        thread = row["thread_id"]
    if mode != "plateau":
        require(all(allocation[1 + step]["clock_ns"] >= int(clock["end_ns"])
                    for step, clock in enumerate(warm_clock)) and
                all(allocation[1 + step]["clock_ns"] <
                    int(warm_clock[step + 1]["begin_ns"])
                    for step in range(len(warm_clock) - 1)) and
                all(allocation[1 + len(warm_clock) + step]["clock_ns"] >=
                    int(clock["end_ns"]) for step, clock in enumerate(measured_clock)) and
                all(allocation[1 + len(warm_clock) + step]["clock_ns"] <
                    int(measured_clock[step + 1]["begin_ns"])
                    for step in range(len(measured_clock) - 1)) and
                allocation[0]["clock_ns"] < int(warm_clock[0]["begin_ns"]) and
                allocation[0]["allocation_bytes"] ==
                    int(markers["construction_allocated_bytes"]) and
                all(allocation[1 + len(warm_clock) + step]["allocation_bytes"] ==
                    int(raw["allocation_bytes"]) for step, raw in enumerate(raw_rows)),
                "version 2 allocation clock or raw counter differs")
    else:
        require(allocation[0]["clock_ns"] >= int(warm_clock[-1]["end_ns"]),
                "version 2 plateau precedes warm-up")
    if mode == "memory":
        expected_memory = ([('empty', 0), ('construction', 0)] +
                           [('warmup', step) for step in range(len(warm_clock))] +
                           [('retained', 0)] +
                           [('measure', step) for step in range(len(raw_rows))])
        require([(row.get("phase"), row.get("step")) for row in memory] ==
                expected_memory, "version 2 memory phases or count differ")
        empty_heap = memory[0].get("heap_used_bytes")
        require(type(empty_heap) is int and empty_heap >= 0 and
                memory[0]["clock_ns"] < allocation[0]["clock_ns"] and
                memory[1]["clock_ns"] >= allocation[0]["clock_ns"] and
                memory[2 + len(warm_clock)]["clock_ns"] >=
                    int(warm_clock[-1]["end_ns"]) and
                memory[2 + len(warm_clock)]["clock_ns"] <
                    int(measured_clock[0]["begin_ns"]),
                "version 2 memory clock or empty baseline differs")
        for position, row in enumerate(memory):
            retained = row["phase"] == "retained"
            require(type(row.get("heap_used_bytes")) is int and
                    row["heap_used_bytes"] >= 0 and
                    row.get("empty_heap_bytes") == empty_heap and
                    row.get("managed_heap_delta_bytes") ==
                    row["heap_used_bytes"] - empty_heap and
                    row.get("managed_post_collection") is retained and
                    (type(row.get("collection_count_delta")) is int and
                     row["collection_count_delta"] > 0 and
                     row["collection_count_delta"] ==
                     int(markers["retained_collection_count_delta"]) if retained else
                     row.get("collection_count_delta") is None) and
                    row.get("native_workload_bytes") is None and
                    row.get("attributed_workload_bytes") is None and
                    row.get("native_attribution") == "unsupported" and
                    row.get("managed_provenance") ==
                    "Runtime.totalMemory minus freeMemory delta from empty same process; includes unrelated heap objects" and
                    row.get("buffer_provenance") ==
                    "BufferPoolMXBean process total; not workload attribution" and
                    row.get("qualification") == "unpassed" and
                    type(row.get("rss_bytes")) is int and row["rss_bytes"] >= -1 and
                    (row.get("buffer_pool_used_bytes") is None or
                     type(row["buffer_pool_used_bytes"]) is int and
                     row["buffer_pool_used_bytes"] >= 0),
                    "version 2 memory attribution or collection proof differs")
            if row["phase"] == "warmup":
                step = row["step"]
                next_begin = (warm_clock[step + 1]["begin_ns"] if step + 1 < len(warm_clock)
                              else measured_clock[0]["begin_ns"])
                require(row["clock_ns"] >= int(warm_clock[step]["end_ns"]) and
                        row["clock_ns"] >= allocation[1 + step]["clock_ns"] and
                        row["clock_ns"] < int(next_begin),
                        "version 2 warm-up memory clock differs")
            if row["phase"] == "measure":
                step = row["step"]
                require(row["clock_ns"] >= int(measured_clock[step]["end_ns"]) and
                        row["clock_ns"] >=
                        allocation[1 + len(warm_clock) + step]["clock_ns"] and
                        row["heap_used_bytes"] == int(raw_rows[step]["heap_used_bytes"]) and
                        row["rss_bytes"] == int(raw_rows[step]["rss_bytes"]),
                        "version 2 measured memory differs from raw step")
    else:
        require(not memory, "version 2 memory stream in wrong mode")
    if mode == "plateau":
        previous_count = None
        stamp_names = ("cycle_disposed_ns", "collection_before_sample_ns",
                       "gc_requested_ns", "collection_after_sample_ns",
                       "heap_sample_begin_ns", "heap_sample_end_ns",
                       "rss_sample_begin_ns", "rss_sample_end_ns", "clock_ns")
        for cycle, (record, allocated, raw) in enumerate(zip(plateau, allocation, raw_rows)):
            count = record.get("collection_count")
            before = record.get("collection_count_before")
            after = record.get("collection_count_after")
            delta = record.get("collection_count_delta")
            stamps = [record.get(name) for name in stamp_names]
            require(all(type(stamp) is int and stamp >= origin["runtime_ns"]
                        for stamp in stamps) and
                    all(first <= second for first, second in zip(stamps, stamps[1:])) and
                    stamps[0] > (plateau[cycle - 1]["clock_ns"] if cycle else
                                 int(warm_clock[-1]["end_ns"])) and
                    stamps[0] <= allocated["clock_ns"] <= stamps[1],
                    "version 2 plateau disposal, collection, or sample order differs")
            for stamp in stamps:
                low = max(low, item["started_ns"] - stamp)
                high = min(high, item["ended_ns"] - stamp)
                require(low <= high,
                        "version 2 plateau sample lies outside observed process interval")
            require(type(count) is int and count > 0 and
                    (previous_count is None or count > previous_count) and
                    type(before) is int and before >= 0 and
                    (previous_count is None or before >= previous_count) and
                    type(after) is int and after == count and after > before and
                    type(delta) is int and delta == after - before and
                    record.get("collection_count_unit") == "collections" and
                    record.get("collection_probe") ==
                    "sum of GarbageCollectorMXBean.getCollectionCount" and
                    record.get("collection_count_status") == "observed" and
                    type(record.get("heap_after_collection_bytes")) is int and
                    record["heap_after_collection_bytes"] >= 0 and
                    type(record.get("rss_after_collection_bytes")) is int and
                    record["rss_after_collection_bytes"] >= -1 and
                    type(record.get("managed_heap_delta_bytes")) is int and
                    type(record.get("buffer_pool_used_bytes")) is int and
                    record["buffer_pool_used_bytes"] >= 0 and
                    record["clock_ns"] >= allocated["clock_ns"] and
                    (cycle == 99 or record["clock_ns"] <
                     allocation[cycle + 1]["clock_ns"]) and
                    int(raw["cycle"]) == cycle and
                    int(raw["collection_count"]) == count and
                    int(raw["heap_after_collection_bytes"]) ==
                    record.get("heap_after_collection_bytes") and
                    int(raw["rss_after_collection_bytes"]) ==
                    record.get("rss_after_collection_bytes") and
                    all(int(raw[field]) == -1 for field in
                        ("managed_bytes", "native_bytes", "attributed_workload_bytes",
                         "reserved_runtime_bytes")) and
                    int(raw["wasm_linear_bytes"]) == 0 and
                    record.get("native_workload_bytes") is None and
                    record.get("attributed_workload_bytes") is None and
                    record.get("reserved_runtime_bytes") is None and
                    record.get("native_attribution") == "unsupported" and
                    record.get("qualification") == "unpassed",
                    "version 2 plateau collection, raw cycle, or attribution differs")
            previous_count = count
    return {"allocation_rows": len(allocation), "memory_rows": len(memory),
            "plateau_cycles": len(plateau), "memory_attribution": "unavailable",
            "qualification": "unpassed"}


def capture_key(item):
    kind = item["kind"]
    if kind in ("measure", "report"):
        return (item["row_id"], item["scenario_id"], item["mode"], item["repeat"])
    if kind == "noise":
        return (item["row_id"], item["scenario_id"], item["mode"],
                item["repeat"], item["side"])
    if kind == "plateau":
        return (item["row_id"], item["scenario_id"])
    raise ValueError("unknown capture kind")


def verify_capture(root, item, scenarios, references, artifact_hashes, policy, index):
    row_id = item["row_id"]
    gate = policy["sustained_gate"]
    jvm_v2 = gate["harnesses"][row_id].get("sidecar_protocol") == "jvm-v2"
    scenario = scenarios[item["scenario_id"]]
    reference = references[row_id]
    noise = item["kind"] == "noise"
    capacity = item["kind"] == "report" and item.get("status") == "capacity_limited"
    selected_artifacts = ({row_id: ({name: index["baseline"] for name in ("core", "kotlin")}
                         if row_id == "jvm.java" else index["control_artifacts"][row_id])}
                          if noise else index["artifacts"])
    expected_artifacts = (gate["noise_controls"][row_id]["artifact_sha256"] if noise else
                          artifact_hashes[row_id])
    executed_source = (gate["noise_controls"][row_id]["source_commit"] if noise else
                       item["source_commit"])
    require((item.get("noise_control_id") == row_id and
             item.get("executed_source_commit") == executed_source) if noise else
            "noise_control_id" not in item and "executed_source_commit" not in item,
            "executed independent noise control assignment differs")
    require(((item["status"] == "capacity_limited" and type(item.get("exit_code")) is int and
              item["exit_code"] != 0) if capacity else
             (item["status"] == "complete" and type(item.get("exit_code")) is int and
              item["exit_code"] == 0)) and
            item["artifacts"] == expected_artifacts,
            "capture source, artifact, or completion differs")
    require(item["host"] == reference["host"] and
            item["runtime_sha256"] == reference["runtime"]["sha256"] and
            item["process_image_sha256"] == reference["runtime"]["sha256"] and
            item["process_image_method"] == PROCESS_IMAGE_METHODS.get(
                reference["host"]["system"]) and
            item["probe_sha256"] == reference["probe"]["timer_sha256"] and
            item["ambient_environment"] ==
                gate["harnesses"][row_id]["environment"] and
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
            provider["source_commit"] == executed_source and
            provider["api"] == scenario["api"] and
            provider["artifact_sha256"] == expected_artifacts and
            provider["baseline_sha256"] == policy["baseline_jar_sha256"] and
            provider["loaded_core_sha256"] == (policy["baseline_jar_sha256"] if
                scenario["api"] == "baseline" else expected_artifacts["core"]) and
            provider["loaded_kotlin_sha256"] == (expected_artifacts["kotlin"] if
                scenario["api"] == "direct_kotlin" else None) and
            provider["loaded_harness_sha256"] == reference["harness"]["sha256"] and
            provider["loaded_adapter_sha256"] == reference["adapter"]["sha256"] and
            provider["loaded_fixture_sha256"] ==
                gate["harnesses"][row_id]["fixture_sha256"],
            "loaded provider or process identity differs")
    raw = checked_file(root, item, "raw_path", "raw_sha256")
    stderr = checked_file(root, item, "stderr_path", "stderr_sha256")
    warm, markers = warmup_rows(stderr, scenario["rate_hz"], item["kind"] == "plateau")
    warm_clock = checked_file(root, item, "warmup_clock_path", "warmup_clock_sha256")
    warm_clock_rows = csv_rows(warm_clock, WARMUP_CLOCK_FIELDS)
    validate_warmup_clock(warm_clock_rows, warm, scenario["rate_hz"])
    require(item["wall_ns"] >= (len(warm) / scenario["rate_hz"] +
                                (0 if capacity else duration)) * 1_000_000_000,
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
                                      selected_artifacts, index["baseline"]) + expected_tail,
            "executed command, classpath, JVM settings, or fixture differs")
    if item["kind"] == "plateau":
        validate_process_clock(root, item, warm_clock_rows, None,
                               image_receipt["observed_ns"])
        rows = csv_rows(raw, PLATEAU_FIELDS)
        audit = validate_v2_sidecars(root, item, scenario, executed_source,
                                     gate["harnesses"][row_id]["fixture_sha256"],
                                     checked_file(root, item, "provider_path", "provider_sha256"),
                                     warm_clock_rows, None, rows, markers)
        if jvm_v2:
            require(audit is not None, "version 2 process sidecars are required by approved JVM harness")
            require(audit["qualification"] == "passed",
                    "version 2 plateau attribution is unqualified")
        validate_plateau(rows, policy["sustained"]["create_use_dispose_cycles"])
        return rows, markers
    if item["kind"] == "report":
        require(validate_stress(root, item, policy, image_receipt) ==
                ("capacity_limited" if capacity else "completed"),
                "stress termination state differs")
    mode = item["mode"]
    require(item["mode"] == mode, "capture mode differs")
    rows = validate_steps(csv_rows(raw, STEP_FIELDS), scenario, mode, policy,
                          partial=capacity)
    clock = checked_file(root, item, "clock_path", "clock_sha256")
    clock_rows = csv_rows(clock, CLOCK_FIELDS)
    validate_clock(clock_rows, rows, hz, len(rows) / hz if capacity else duration)
    validate_process_clock(root, item, warm_clock_rows, clock_rows,
                           image_receipt["observed_ns"])
    if capacity:
        require(item["wall_ns"] >= (len(warm) + len(rows)) * 1_000_000_000 / hz and
                item["summary"] == step_summary(rows, mode, hz),
                "bounded capacity raw sample count or summary differs")
        for field, value in item.items():
            if field.endswith("_path") and field not in ("runner_path",):
                checked_file(root, item, field, field[:-5] + "_sha256")
        return rows, markers
    audit = validate_v2_sidecars(root, item, scenario, executed_source,
                                 gate["harnesses"][row_id]["fixture_sha256"],
                                 checked_file(root, item, "provider_path", "provider_sha256"),
                                 warm_clock_rows, clock_rows, rows, markers)
    if jvm_v2 and mode in ("allocation", "memory"):
        require(audit is not None, "version 2 process sidecars are required by approved JVM harness")
        if mode == "memory":
            require(audit["qualification"] == "passed",
                    "version 2 memory attribution is unqualified")
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
        cap = (None if noise or scenario["size"] == "stress" or scenario["api"] == "baseline" or
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
        if "jvm.java" not in assignments:
            break
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
    control_artifacts(root, index, policy)
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
    require(all(item["status"] == "complete" for item in groups["report"].values()),
            "capacity-limited stress reports cannot qualify sustained performance")
    require(set(groups["noise"]) == required_noise(policy),
            "unchanged baseline noise calibration matrix is partial or extra")
    require(set(groups["plateau"]) == required_plateaus(policy),
            "100-cycle plateau matrix is partial or extra")
    indexed_files = {item[field] for item in captures for field in
                     ("raw_path", "stderr_path", "provider_path", "clock_path",
                      "warmup_clock_path", "memory_path", "resource_path", "run_path",
                      "allocation_v2_path", "memory_v2_path", "plateau_v2_path",
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
            control_id = (scenario["id"] if row_id == "jvm.java" else
                          stem + ".direct_kotlin")
            latest_noise = max(groups["noise"][(row_id, control_id, mode, repeat, side)]["ended_ns"]
                               for mode in MODES for repeat in (1, 2, 3)
                               for side in ("a", "b"))
            earliest_candidate = min(groups["measure"][(row_id, f"{stem}.{api}", mode, repeat)]["started_ns"]
                                     for api in ROUTES[1:] for mode in MODES
                                     for repeat in (1, 2, 3))
            require(latest_noise < earliest_candidate,
                    "noise calibration was not completed before candidate runs")
    analysis_partial = root / "analysis.partial.jsonl"
    with analysis_partial.open("w") as analysis:
        calibration_intervals, maximum_noise_upper = analyze_noise_groups(
            root, groups, scenarios, references, artifacts, policy, index, analysis)
        inconclusive_event_tails = analyze_candidate_groups(
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


def analyze_noise_groups(root, groups, scenarios, references, artifacts, policy, index, analysis):
    calibration_intervals = 0
    maximum_noise_upper = 0.0
    limits = noise_limit_lookup(policy)
    for row in policy["runtime_rows"]:
        row_id = row["id"]
        for scenario in policy["scenarios"]:
            if scenario["api"] != "baseline":
                continue
            stem = scenario["id"].rsplit(".", 1)[0]
            if scenario["size"] == "stress":
                continue
            control_id = (scenario["id"] if row_id == "jvm.java" else
                          stem + ".direct_kotlin")
            for mode in MODES:
                retained_first = []
                retained_second = []
                construction_first = []
                construction_second = []
                workload_first = {"full": [], "final_minute": []}
                workload_second = {"full": [], "final_minute": []}
                for repeat in (1, 2, 3):
                    a = groups["noise"][(row_id, control_id, mode, repeat, "a")]
                    b = groups["noise"][(row_id, control_id, mode, repeat, "b")]
                    require(a["sequence"] != b["sequence"] and
                            (a["sequence"] < b["sequence"]) == (repeat != 2) and
                            (a["started_ns"] < b["started_ns"]) == (repeat != 2),
                            "noise calibration order is not balanced")
                    first, first_markers = verify_capture(root, a, scenarios, references,
                                                          artifacts, policy, index)
                    second, second_markers = verify_capture(root, b, scenarios, references,
                                                            artifacts, policy, index)
                    if mode == "memory":
                        retained_first.append(int(first_markers["retained_heap_world_alive_bytes"]))
                        retained_second.append(int(second_markers["retained_heap_world_alive_bytes"]))
                        for item, destination in ((a, workload_first), (b, workload_second)):
                            memory = csv_rows(checked_file(root, item, "memory_path",
                                                           "memory_sha256"), MEMORY_FIELDS)
                            measured = [row for row in memory if row["phase"] == "measure"]
                            destination["full"].append(max(int(row["attributed_workload_bytes"])
                                                           for row in memory[1:]))
                            destination["final_minute"].append(max(
                                int(row["attributed_workload_bytes"])
                                for row in measured[-60 * scenario["rate_hz"]:]))
                        continue
                    if mode == "allocation":
                        construction_first.append(int(first_markers["construction_allocated_bytes"]))
                        construction_second.append(int(second_markers["construction_allocated_bytes"]))
                    metrics = ("median", "p99", "total") if mode == "timing" else ("total",)
                    for window, window_a, window_b in (("full", first, second),
                        ("final_minute", first[-60 * scenario["rate_hz"]:],
                         second[-60 * scenario["rate_hz"]:])):
                        for metric in metrics:
                            left = allocation_rows(window_a) if mode == "allocation" else window_a
                            right = allocation_rows(window_b) if mode == "allocation" else window_b
                            if mode == "allocation" and all(int(row["elapsed_ns"]) == 0 for row in left):
                                require(all(int(row["elapsed_ns"]) == 0 for row in right),
                                        "positive A/A allocation against zero control")
                                value = {"lower_95": 1.0, "upper_95": 1.0,
                                         "draws": 2000, "zero_baseline": True}
                            else:
                                value = interval(left, right, scenario["rate_hz"], metric, 2000)
                            limit = limits.get((row_id, stem, mode, metric, window))
                            require(limit is not None,
                                    "noise comparison control assignment is missing")
                            analysis.write(json.dumps({"kind": "noise_interval", "row_id": row_id,
                                "scenario_id": control_id, "mode": mode, "repeat": repeat,
                                "window": window, "metric": metric, "limit": limit,
                                **value}, sort_keys=True) + "\n")
                            maximum_noise_upper = max(maximum_noise_upper, value["upper_95"])
                            calibration_intervals += 1
                            require(value["lower_95"] >= 1 / limit and
                                    value["upper_95"] <= limit,
                                    "unchanged-control noise calibration is inconclusive")
                if mode == "memory":
                    value = scalar_interval(retained_first, retained_second, 2000)
                    limit = limits.get((row_id, stem, mode,
                                        "retained_heap_world_alive_bytes", "full"))
                    require(limit is not None,
                            "memory noise comparison control assignment is missing")
                    analysis.write(json.dumps({"kind": "noise_interval", "row_id": row_id,
                        "scenario_id": control_id, "mode": mode, "repeat": 0,
                        "window": "full", "metric": "retained_heap_world_alive_bytes",
                        "limit": limit, **value}, sort_keys=True) + "\n")
                    maximum_noise_upper = max(maximum_noise_upper, value["upper_95"])
                    calibration_intervals += 1
                    require(value["lower_95"] >= 1 / limit and
                            value["upper_95"] <= limit,
                            "unchanged-control memory noise calibration is inconclusive")
                    for window in ("full", "final_minute"):
                        limit = limits.get((row_id, stem, mode,
                                            "attributed_workload_peak_bytes", window))
                        if limit is None:
                            continue
                        value = scalar_interval(workload_first[window],
                                                workload_second[window], 2000)
                        analysis.write(json.dumps({"kind": "noise_interval", "row_id": row_id,
                            "scenario_id": control_id, "mode": mode, "repeat": 0,
                            "window": window, "metric": "attributed_workload_peak_bytes",
                            "limit": limit, **value}, sort_keys=True) + "\n")
                        maximum_noise_upper = max(maximum_noise_upper, value["upper_95"])
                        calibration_intervals += 1
                        require(value["lower_95"] >= 1 / limit and
                                value["upper_95"] <= limit,
                                "unchanged-control workload memory noise is inconclusive")
                if mode == "allocation":
                    value = scalar_interval(construction_first, construction_second, 2000)
                    limit = limits.get((row_id, stem, mode,
                                        "construction_allocated_bytes", "full"))
                    require(limit is not None,
                            "construction noise comparison control assignment is missing")
                    analysis.write(json.dumps({"kind": "noise_interval", "row_id": row_id,
                        "scenario_id": control_id, "mode": mode, "repeat": 0,
                        "window": "full", "metric": "construction_allocated_bytes",
                        "limit": limit, **value}, sort_keys=True) + "\n")
                    maximum_noise_upper = max(maximum_noise_upper, value["upper_95"])
                    calibration_intervals += 1
                    require(value["lower_95"] >= 1 / limit and
                            value["upper_95"] <= limit,
                            "unchanged-control construction noise calibration is inconclusive")
    return calibration_intervals, maximum_noise_upper


def analyze_candidate_groups(root, groups, scenarios, references, artifacts, policy, index,
                             analysis):
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
    return inconclusive_event_tails


def verify_archive(root, key, expected_source_commit):
    return _verify_archive(root, key, expected_source_commit, frozen_policy())


def verify_capacity_report(root, key, expected_source_commit, capture_index):
    policy = frozen_policy()
    approved_gate(policy)
    root = Path(root).resolve()
    require(len(key) >= 32, "trusted key is too short")
    index = json.loads((root / "archive.json").read_text())
    require(index.get("schema") == 1 and index.get("route") == "sustained-raw-v1" and
            index.get("capture_tool_sha256") == sha256(Path(__file__)) and
            hmac.compare_digest(index.get("signature", ""), signature(index, key)),
            "capacity archive schema, tool, or signature differs")
    expected_hash = (sha256(MANIFEST_FILE) if policy == manifest() else
                     hashlib.sha256(canonical(policy)).hexdigest())
    require(index.get("manifest_sha256") == expected_hash and
            index.get("scenario_ids") == [item["id"] for item in policy["scenarios"]],
            "capacity archive frozen manifest differs")
    artifacts = verify_source_and_artifacts(root, index, expected_source_commit, policy)
    control_artifacts(root, index, policy)
    references = verify_references(root, index, policy, complete=False)
    require(type(capture_index) is int and 0 <= capture_index < len(index["captures"]),
            "capacity report index is absent")
    item = index["captures"][capture_index]
    require(item.get("kind") == "report" and item.get("status") == "capacity_limited" and
            item.get("source_commit") == index["source_commit"] and
            item.get("row_id") in references and
            capture_key(item) in required_reports(policy),
            "capacity report row, scenario, or state differs")
    scenarios = {scenario["id"]: scenario for scenario in policy["scenarios"]}
    rows, _ = verify_capture(root, item, scenarios, references, artifacts, policy, index)
    return {"qualification": "unpassed", "stress_completed": False,
            "small_medium_pass": False, "release_qualified": False,
            "source_commit": index["source_commit"],
            "capacity_report": {"status": "capacity_limited", "complete": True,
                                "row_id": item["row_id"],
                                "scenario_id": item["scenario_id"],
                                "mode": item["mode"],
                                "termination_reason": item["termination_reason"],
                                "sample_count": len(rows),
                                "wall_ns": item["wall_ns"],
                                "peak_rss_bytes": item["stress_peak_rss_bytes"],
                                "raw_sha256": item["raw_sha256"],
                                "monitor_sha256": item["stress_monitor_sha256"],
                                "receipt_sha256": item["stress_monitor_receipt_sha256"]}}


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
    control_records = {}
    control_receipts = {}
    non_jvm = set(config["references"]) - {"jvm.java"}
    require(set(config.get("control_artifact_paths", {})) == non_jvm,
            "independent noise control artifact paths differ")
    require(set(config.get("control_build_receipt_paths", {})) == non_jvm,
            "independent noise control build receipt paths differ")
    for row_id in non_jvm:
        control_records[row_id] = {}
        paths = config["control_artifact_paths"][row_id]
        require(set(paths) == {"core", "kotlin"},
                "independent noise control modules differ")
        for name, path_text in paths.items():
            path = Path(path_text).resolve(strict=True)
            target = root / "controls" / row_id / f"{name}{path.suffix}"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            control_records[row_id][name] = {"staged_path": str(path),
                                             "archive_path": str(target.relative_to(root)),
                                             "sha256": sha256(target)}
        receipt_path = Path(config["control_build_receipt_paths"][row_id]).resolve(strict=True)
        receipt_target = root / "controls" / row_id / "build-receipt.json"
        shutil.copyfile(receipt_path, receipt_target)
        control_receipts[row_id] = {"archive_path": str(receipt_target.relative_to(root)),
                                    "sha256": sha256(receipt_target)}
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
             "artifacts": artifacts, "control_artifacts": control_records,
             "control_build_receipts": control_receipts,
             "references": references, "captures": []}
    write_index(root, index, key)
    verify_source_and_artifacts(root, index, commit, policy)
    control_artifacts(root, index, policy)
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
    controls = control_artifacts(root, index, policy)
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
    selected_artifacts = controls if job["kind"] == "noise" else index["artifacts"]
    require(120 * hz <= warmup_steps <= 600 * hz and
            command == command_prefix(reference, policy, job["row_id"],
                                      selected_artifacts, index["baseline"]) + tail,
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
    v2_sidecars = {stem: folder / (stem.replace("_", "-") + ".jsonl") for stem in
                   ("allocation_v2", "memory_v2", "plateau_v2")}
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
    executed_hashes = (gate["noise_controls"][job["row_id"]]["artifact_sha256"]
                       if job["kind"] == "noise" else hashes[job["row_id"]])
    executed_source = (gate["noise_controls"][job["row_id"]]["source_commit"]
                       if job["kind"] == "noise" else index["source_commit"])
    environment.update({"DYN4K_PROVIDER_JSON": str(provider),
                        "DYN4K_MEMORY_CSV": str(memory),
                        "DYN4K_RESOURCE_CSV": str(resource),
                        "DYN4K_RUN_JSON": str(run_summary),
                        "DYN4K_CLOCK_CSV": str(clock),
                        "DYN4K_WARMUP_CLOCK_CSV": str(warmup_clock),
                        "DYN4K_CLOCK_ORIGIN_JSON": str(clock_origin),
                        "DYN4K_CLOCK_NONCE": clock_nonce,
                        "DYN4K_SOURCE_COMMIT": executed_source,
                        "DYN4K_ARTIFACT_HASHES_JSON": json.dumps(executed_hashes),
                        "DYN4K_BASELINE_SHA256": policy["baseline_jar_sha256"]})
    if job["mode"] in ("allocation", "memory", "plateau"):
        environment.update({"DYN4K_" + stem.upper() + "_JSONL": str(path)
                            for stem, path in v2_sidecars.items()})
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
        terminal_observed_ns = None
        stop_requested_ns = None
        stop_dispatched_ns = None
        stop_action = None
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
            system = platform.system()
            limit = gate["stress_limits"][job["row_id"]]
            peak = 0
            windows_handle = None
            if system == "Windows":
                try:
                    windows_handle = windows_peak_handle(pid)
                except (OSError, ValueError):
                    termination_reason = "monitor_unavailable"
            with stress_monitor.open("w", newline="") as monitor_stream:
                writer = csv.writer(monitor_stream)
                writer.writerow(STRESS_MONITOR_FIELDS)
                while termination_reason != "monitor_unavailable":
                    elapsed = time.monotonic_ns() - started
                    if system in ("Linux", "Darwin"):
                        try:
                            terminal_usage = wait4_peak_rss(pid, os.WNOHANG, system)
                        except (OSError, ValueError, ChildProcessError):
                            termination_reason = "monitor_unavailable"
                            break
                        running = terminal_usage is None
                    else:
                        running = process.poll() is None
                    if not running:
                        try:
                            if system == "Windows":
                                process.wait()
                                terminal_peak = windows_terminal_peak(windows_handle, pid)
                            else:
                                status, terminal_peak = terminal_usage
                                process.returncode = os.waitstatus_to_exitcode(status)
                        except (OSError, ValueError):
                            termination_reason = "monitor_unavailable"
                            break
                        terminal_observed_ns = time.monotonic_ns()
                        peak = max(peak, terminal_peak)
                        termination_reason = "completed"
                        writer.writerow((elapsed, terminal_peak, termination_reason))
                        break
                    try:
                        rss = peak_rss_bytes(pid, system)
                    except (OSError, ValueError, subprocess.TimeoutExpired):
                        if system in ("Linux", "Darwin"):
                            try:
                                terminal_usage = wait4_peak_rss(pid, os.WNOHANG, system)
                            except (OSError, ValueError, ChildProcessError):
                                terminal_usage = None
                        if terminal_usage is not None:
                            status, terminal_peak = terminal_usage
                            process.returncode = os.waitstatus_to_exitcode(status)
                            terminal_observed_ns = time.monotonic_ns()
                            peak = max(peak, terminal_peak)
                            termination_reason = "completed"
                            writer.writerow((elapsed, terminal_peak, termination_reason))
                        else:
                            termination_reason = "monitor_unavailable"
                        break
                    peak = max(peak, rss)
                    if elapsed >= limit["wall_stop_ns"]:
                        termination_reason = "wall_limit"
                    elif peak >= limit["rss_stop_bytes"]:
                        termination_reason = "rss_limit"
                    if termination_reason:
                        stop_requested_ns = time.monotonic_ns()
                        stop_action = "terminate"
                        try:
                            process.terminate()
                            stop_dispatched_ns = time.monotonic_ns()
                            if system in ("Linux", "Darwin"):
                                deadline = time.monotonic() + 5
                                while time.monotonic() < deadline and terminal_usage is None:
                                    terminal_usage = wait4_peak_rss(pid, os.WNOHANG, system)
                                    if terminal_usage is None:
                                        time.sleep(0.05)
                                if terminal_usage is None:
                                    stop_action = "kill"
                                    stop_requested_ns = time.monotonic_ns()
                                    process.kill()
                                    stop_dispatched_ns = time.monotonic_ns()
                                    terminal_usage = wait4_peak_rss(pid, 0, system)
                                status, terminal_peak = terminal_usage
                                process.returncode = os.waitstatus_to_exitcode(status)
                            else:
                                try:
                                    process.wait(timeout=5)
                                except subprocess.TimeoutExpired:
                                    stop_action = "kill"
                                    stop_requested_ns = time.monotonic_ns()
                                    process.kill()
                                    stop_dispatched_ns = time.monotonic_ns()
                                    process.wait()
                                terminal_peak = windows_terminal_peak(windows_handle, pid)
                            terminal_observed_ns = time.monotonic_ns()
                        except (OSError, ValueError, ChildProcessError):
                            termination_reason = "monitor_unavailable"
                            break
                        peak = max(peak, terminal_peak)
                        writer.writerow((elapsed, terminal_peak, termination_reason))
                        break
                    writer.writerow((elapsed, rss, "running"))
                    time.sleep(0.1)
            if windows_handle is not None:
                close_windows_peak_handle(windows_handle)
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
    capacity_limited = (job["kind"] == "report" and
                        termination_reason in ("wall_limit", "rss_limit") and
                        stop_dispatched_ns is not None and
                        terminal_observed_ns is not None and
                        (returncode == 1 if platform.system() == "Windows" else
                         returncode == (-15 if stop_action == "terminate" else -9)) and
                        ended - started <= gate["stress_limits"][job["row_id"]]["wall_max_ns"] and
                        stress_peak_rss is not None and
                        stress_peak_rss <= gate["stress_limits"][job["row_id"]]["rss_max_bytes"])
    item = {**job, "status": ("capacity_limited" if capacity_limited else
            "complete" if returncode == 0 and image_observation is not None and
            termination_reason in (None, "completed") else "failed"),
            "source_commit": index["source_commit"], "artifacts": executed_hashes,
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
    if job["kind"] == "noise":
        item.update(noise_control_id=job["row_id"],
                    executed_source_commit=executed_source)
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
                    **({"stop_action": stop_action,
                        "stop_requested_ns": stop_requested_ns,
                        "stop_dispatched_ns": stop_dispatched_ns}
                       if capacity_limited else {}),
                    **({"metric_kind": ("peak_working_set_bytes" if platform.system() == "Windows"
                                         else "peak_rss_bytes"),
                        "terminal_pid": pid, "terminal_observed_ns": terminal_observed_ns,
                        **({"terminal_exit_code": returncode,
                            "terminal_peak_working_set_bytes": terminal_peak}
                           if platform.system() == "Windows" else
                           {"terminal_wait_status": terminal_usage[0],
                            "terminal_ru_maxrss_bytes": terminal_usage[1]})}
                       if terminal_observed_ns is not None else {})}, sort_keys=True) + "\n")
                item.update(stress_monitor_receipt_path=str(stress_monitor_receipt.relative_to(root)),
                            stress_monitor_receipt_sha256=sha256(stress_monitor_receipt))
    if provider.is_file():
        item.update(provider_path=str(provider.relative_to(root)),
                    provider_sha256=sha256(provider))
    if memory.is_file():
        item.update(memory_path=str(memory.relative_to(root)),
                    memory_sha256=sha256(memory))
    for stem, path in v2_sidecars.items():
        if path.is_file():
            item[stem + "_path"] = str(path.relative_to(root))
            item[stem + "_sha256"] = sha256(path)
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
    if returncode == 0 or capacity_limited:
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
            merged.update(artifacts={}, control_artifacts={}, control_build_receipts={},
                          references={}, captures=[])
            copy_record(part, merged["baseline"], "archive_path", "sha256", "")
        else:
            for field in ("schema", "route", "capture_tool_sha256", "manifest_sha256", "scenario_ids",
                          "source_commit", "source_trees"):
                require(index[field] == merged[field], f"part {field} differs")
            require(index["baseline"]["sha256"] == merged["baseline"]["sha256"],
                    "part baseline artifact differs")
        verify_source_and_artifacts(part, index, merged["source_commit"], policy)
        control_artifacts(part, index, policy)
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
        if row_id != "jvm.java":
            controls = copy.deepcopy(index["control_artifacts"][row_id])
            for record in controls.values():
                copy_record(part, record, "archive_path", "sha256", prefix)
            merged["control_artifacts"][row_id] = controls
            receipt_record = copy.deepcopy(index["control_build_receipts"][row_id])
            copy_record(part, receipt_record, "archive_path", "sha256", prefix)
            merged["control_build_receipts"][row_id] = receipt_record
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
                                       ("allocation_v2_path", "allocation_v2_sha256"),
                                       ("memory_v2_path", "memory_v2_sha256"),
                                       ("plateau_v2_path", "plateau_v2_sha256"),
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
    parser.add_argument("command", choices=("init", "capture", "merge", "verify",
                                            "verify-capacity", "plan"))
    parser.add_argument("--archive")
    parser.add_argument("--config")
    parser.add_argument("--job")
    parser.add_argument("--part", action="append")
    parser.add_argument("--trusted-key")
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--capture-index", type=int)
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
            elif args.command == "verify-capacity":
                require(args.expected_source_commit and args.capture_index is not None,
                        "verify-capacity needs source commit and capture index")
                result = verify_capacity_report(args.archive, key, args.expected_source_commit,
                                                args.capture_index)
            else:
                require(args.expected_source_commit, "verify needs expected source commit")
                result = verify_archive(args.archive, key, args.expected_source_commit)
        print(json.dumps(result, indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"qualification": "unpassed", "reason": str(exc)}, sort_keys=True))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
