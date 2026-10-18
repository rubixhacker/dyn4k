import copy
import contextlib
import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from manifest import manifest
from sustained_archive import (CLOCK_FIELDS, MEMORY_FIELDS, PLATEAU_FIELDS, STEP_FIELDS,
                               WARMUP_CLOCK_FIELDS, canonical,
                               capture_one, merge_parts,
                               initialize_archive,
                               observed_host, required_measurements, required_noise,
                               required_plateaus, required_reports, signature, step_summary,
                               _verify_archive, main)
from candidate_runner import ROOT, source_trees
from measure import sha256
from measure import balanced_orders
from analyze import bootstrap_ratio


class SustainedArchiveContractTest(unittest.TestCase):
    def test_frozen_matrix_has_every_gate_case_and_no_stress_gate(self):
        plan = required_measurements(manifest())
        self.assertEqual(999, len(manifest()["scenarios"]))
        self.assertEqual(28, len(manifest()["runtime_rows"]))
        self.assertEqual(21, len(manifest()["targets"]))
        self.assertTrue(any(key[0] == "jvm.java" and
                            key[1] == "separated.default.small.30hz.baseline" and
                            key[2:] == ("timing", 1) for key in plan))
        self.assertTrue(any(key[0] == "jvm.java" and
                            key[1] == "separated.default.medium.30hz.direct_kotlin" and
                            key[2:] == ("memory", 3) for key in plan))
        self.assertFalse(any(".stress." in key[1] for key in plan))
        self.assertFalse(any(key[1].endswith(".baseline") and
                             key[0] != "jvm.java" for key in plan))


def write_csv(path, fields, rows):
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        writer.writerows(rows)


class SyntheticSustainedArchiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(dir=Path.home())
        cls.root = Path(cls.folder.name) / "archive"
        cls.root.mkdir()
        cls.key = b"trusted-test-key-for-synthetic-archive-12345"
        cls.policy = copy.deepcopy(manifest())
        cls.policy["runtime_rows"] = [cls.policy["runtime_rows"][0]]
        cls.policy["targets"] = ["jvm"]
        cls.policy["scenarios"] = [item for item in cls.policy["scenarios"]
                                   if item["family"] == "separated" and
                                   item["variant"] == "default" and item["rate_hz"] == 30 and
                                   item["size"] in ("small", "stress")]
        cls.policy["sustained"]["measured_wall_seconds"] = 60
        cls.commit = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                             cwd=ROOT, text=True).strip()
        cls.build_archive()

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    @classmethod
    def build_archive(cls):
        row = cls.policy["runtime_rows"][0]
        row_id = row["id"]
        artifacts = {}
        hashes = {}
        for name in ("core", "kotlin"):
            staged = cls.root / f"staged-{name}.jar"
            staged.write_bytes(f"synthetic {name} artifact".encode())
            copied = cls.root / f"artifact-{name}.jar"
            shutil.copyfile(staged, copied)
            digest = sha256(copied)
            artifacts[name] = {"staged_path": str(staged), "archive_path": copied.name,
                               "sha256": digest}
            hashes[name] = digest
        baseline = cls.root / "staged-baseline.jar"
        baseline.write_bytes(b"synthetic pinned baseline")
        baseline_copy = cls.root / "artifact-baseline.jar"
        shutil.copyfile(baseline, baseline_copy)
        cls.policy["baseline_jar_sha256"] = sha256(baseline)
        timer = cls.root / "timer.csv"
        write_csv(timer, ("elapsed_ns",), ((10,) for _ in range(10000)))
        allocation = cls.root / "allocation.csv"
        write_csv(allocation, ("payload_bytes", "allocated_bytes", "collection_count_delta"),
                  ((1048576, 1048576, 1),))
        runtime = Path(sys.executable).resolve()
        runtime_copy = cls.root / "runtime.bin"
        shutil.copyfile(runtime, runtime_copy)
        harness = cls.root / "harness.bin"
        harness.write_bytes(b"independently approved synthetic harness and adapter")
        adapter = cls.root / "adapter.bin"
        adapter.write_bytes(b"independently approved synthetic adapter")
        fixture_sha = hashlib.sha256(canonical({"fixture": cls.policy["fixture"],
                                                "joint_parameters": cls.policy["joint_parameters"]})).hexdigest()
        cls.policy["sustained_gate"] = {
            "harnesses": {row_id: {"sha256": sha256(harness),
                                   "adapter_sha256": sha256(adapter),
                                   "fixture_sha256": fixture_sha,
                                   "environment": {},
                                   "command_prefix": ["{runtime}", "-Xmx256m", "-cp",
                                                      "{harness}:{adapter}:{baseline}:{core}:{kotlin}",
                                                      "SyntheticHarness"]}},
            "noise_upper_ratio_max": 1.05,
            "stress_wall_ns_max": 200_000_000_000,
            "stress_rss_bytes_max": 3 * 1024 ** 3}
        receipt = cls.root / "build-receipt.json"
        receipt.write_text(json.dumps({"source_commit": cls.commit,
                                       "source_trees": source_trees(cls.commit),
                                       "artifact_sha256": hashes,
                                       "build_configuration": row["optimized_build"],
                                       "target": row["target"],
                                       "status": "built_from_exact_source"}))
        reference = {"target": row["target"], "runtime_family": row["runtime_family"],
                     "minimum_policy": row["minimum_policy"],
                     "size_assignment": row["size_assignment"],
                     "optimized_build": row["optimized_build"],
                     "development_build": row["development_build"],
                     "support_verification": "passed",
                     "status": "validated", "probe_status": "validated",
                     "representative_hardware": "synthetic test host",
                     "runtime_version": "test-runtime-1", "abi": "jvm-bytecode",
                     "build_configuration": row["optimized_build"],
                     "host": observed_host(),
                     "build_receipt": {"archive_path": receipt.name,
                                       "sha256": sha256(receipt)},
                     "host_control": {"status": "validated", "power_mode": "fixed test",
                                      "thermal_state": "fixed test", "load_window": "fixed test"},
                     "runtime": {"path": str(runtime), "archive_path": runtime_copy.name,
                                 "sha256": sha256(runtime),
                                 "version": "test-runtime-1"},
                     "harness": {"path": str(harness), "archive_path": harness.name,
                                 "sha256": sha256(harness)},
                     "adapter": {"path": str(adapter), "archive_path": adapter.name,
                                 "sha256": sha256(adapter)},
                     "probe": {"timer_raw": timer.name, "timer_sha256": sha256(timer),
                               "allocation_raw": allocation.name,
                               "allocation_sha256": sha256(allocation),
                               "timer_min_positive_ns": 10, "timer_median_ns": 10,
                               "timer_p99_ns": 10,
                               "controlled_payload_bytes": 1048576,
                               "controlled_allocated_bytes": 1048576,
                               "retained_collection_count_delta": 1,
                               "memory_attribution": "validated",
                               "memory_components": ["managed", "native", "wasm_linear"]}}
        index = {"schema": 1, "route": "sustained-raw-v1",
                 "capture_tool_sha256": sha256(Path(__file__).with_name("sustained_archive.py")),
                 "manifest_sha256": hashlib.sha256(canonical(cls.policy)).hexdigest(),
                 "scenario_ids": [item["id"] for item in cls.policy["scenarios"]],
                 "source_commit": cls.commit, "source_trees": source_trees(cls.commit),
                 "baseline": {"staged_path": str(baseline),
                              "archive_path": baseline_copy.name,
                              "sha256": sha256(baseline_copy)},
                 "artifacts": {row_id: artifacts}, "references": {row_id: reference},
                 "captures": []}
        scenarios = {item["id"]: item for item in cls.policy["scenarios"]}
        jobs = []
        measure_keys = sorted(required_measurements(cls.policy),
                              key=lambda key: (key[0], key[1].rsplit(".", 1)[0], key[2],
                                               key[3], balanced_orders()[key[3] - 1].index(
                                                   key[1].rsplit(".", 1)[1])))
        noise_keys = sorted(required_noise(cls.policy),
                            key=lambda key: (key[0], key[1], key[2],
                                             0 if (key[3] == "a") == (key[2] != 2) else 1))
        jobs.extend(("noise", key) for key in noise_keys)
        jobs.extend(("measure", key) for key in measure_keys)
        jobs.extend(("report", key) for key in sorted(required_reports(cls.policy)))
        jobs.extend(("plateau", key) for key in sorted(required_plateaus(cls.policy)))
        for serial, (kind, key) in enumerate(jobs, 1):
            scenario_id = key[1]
            scenario = scenarios[scenario_id]
            mode = (key[2] if kind in ("measure", "report") else
                    "timing" if kind == "noise" else "plateau")
            repeat = key[2] if kind == "noise" else key[3] if kind in ("measure", "report") else 1
            folder = cls.root / "runs" / f"run-{serial:03d}"
            folder.mkdir(parents=True)
            raw = folder / "raw.csv"
            stderr = folder / "stderr.raw"
            provider = folder / "provider.json"
            image_receipt = folder / "process-image.json"
            clock_origin = folder / "clock-origin.json"
            clock_origin_receipt = folder / "clock-origin-receipt.json"
            memory = folder / "memory.csv"
            clock = folder / "clock.csv"
            warmup_clock = folder / "warmup-clock.csv"
            stress_monitor = folder / "stress-monitor.csv"
            stress_receipt = folder / "stress-receipt.json"
            hz = scenario["rate_hz"]
            steps = (1 if kind == "plateau" else 60 * hz)
            if kind == "plateau":
                write_csv(raw, PLATEAU_FIELDS,
                          ((cycle, 1000 + serial, 2000 + serial, cycle,
                            100, 0, 0, 100, 1000)
                           for cycle in range(100)))
                warmup = "warmup_step,elapsed_ns\n" + "".join(
                    f"{step},100\n" for step in range(120 * hz))
            else:
                elapsed = 1000 + serial
                rows = [{"step": step, "elapsed_ns": elapsed, "mutation_ns": 0,
                         "lateness_ns": 0, "allocation_bytes": -1 if mode == "timing" else 100,
                         "heap_used_bytes": 1000, "rss_bytes": 2000,
                         "rss_delta_bytes": 100, "body_count": scenario["dynamic_bodies"],
                         "joint_count": 0, "awake_count": scenario["dynamic_bodies"],
                         "linear_speed_sum_m_per_s": scenario["dynamic_bodies"],
                         "angular_speed_sum_rad_per_s": 0, "contact_begins": 0,
                         "contact_ends": 0, "toi_events": 0,
                         "broadphase_candidates": 0 if step % hz == 0 or step == steps - 1 else -1,
                         "active_contact_pairs": 0 if step % hz == 0 or step == steps - 1 else -1,
                         "active_contact_points": 0 if step % hz == 0 or step == steps - 1 else -1}
                        for step in range(steps)]
                write_csv(raw, STEP_FIELDS, ([row[field] for field in STEP_FIELDS] for row in rows))
                write_csv(clock, CLOCK_FIELDS,
                          ((step, 120_000_000_000 + (step * 1_000_000_000 + hz // 2) // hz,
                            120_000_000_000 + (step * 1_000_000_000 + hz // 2) // hz + elapsed)
                           for step in range(steps)))
                warmup = "warmup_step,elapsed_ns,rss_bytes\n" + "".join(
                    f"{step},100,2000\n" for step in range(120 * hz))
                warmup += ("#construction_ns=100\n#construction_allocated_bytes=100\n"
                           "#rss_empty_harness_bytes=1000\n#rss_after_construction_bytes=2000\n"
                           "#retained_heap_world_alive_bytes=1000000\n"
                           "#retained_collection_count_delta=1\n"
                           "#fixture_reset_after_warmup=1\n")
                if mode == "memory":
                    phases = [("empty", 0, 0), ("construction", 0, 100)]
                    phases += [("warmup", step, 100) for step in range(120 * hz)]
                    phases += [("measure", step, 100) for step in range(steps)]
                    write_csv(memory, MEMORY_FIELDS,
                              ((phase, step, amount, 0, 0, amount)
                               for phase, step, amount in phases))
            stderr.write_text(warmup)
            write_csv(warmup_clock, WARMUP_CLOCK_FIELDS,
                      ((step, (step * 1_000_000_000 + hz // 2) // hz,
                        (step * 1_000_000_000 + hz // 2) // hz + 100)
                       for step in range(120 * hz)))
            api = scenario["api"]
            pid = 1000 + serial
            host_start = 1000000000000 + serial * 200000000000
            nonce = f"synthetic-origin-{serial}"
            clock_origin.write_text(json.dumps({"pid": pid, "runtime_ns": 0,
                                                "nonce": nonce}))
            clock_origin_receipt.write_text(json.dumps({"pid": pid,
                                                        "method": "host_file_bracket_v1",
                                                        "runtime_ns": 0, "nonce": nonce,
                                                        "host_before_ns": host_start,
                                                        "host_after_ns": host_start + 1_000_000}))
            provider.write_text(json.dumps({"pid": pid, "runtime_sha256": sha256(runtime),
                                            "source_commit": cls.commit, "api": api,
                                            "artifact_sha256": hashes,
                                            "baseline_sha256": sha256(baseline),
                                            "loaded_core_sha256": sha256(baseline) if api == "baseline"
                                            else hashes["core"],
                                            "loaded_kotlin_sha256": hashes["kotlin"] if
                                            api == "direct_kotlin" else None,
                                            "loaded_harness_sha256": sha256(harness),
                                            "loaded_adapter_sha256": sha256(adapter),
                                            "loaded_fixture_sha256": fixture_sha}))
            image_receipt.write_text(json.dumps({"pid": pid,
                                                 "observed_ns": 1000000000000 + serial * 200000000000 + 1,
                                                 "method": "os_procfs" if sys.platform.startswith("linux")
                                                 else "os_process_api",
                                                 "executable_path": str(runtime),
                                                 "sha256": sha256(runtime)}))
            tail = [scenario["family"], scenario["variant"], scenario["size"], str(hz),
                    str(steps), mode, str(120 * hz)]
            if api != "baseline":
                tail.append(api)
            item = {"kind": kind, "row_id": row_id, "scenario_id": scenario_id,
                    "mode": mode, "repeat": repeat,
                    "sequence": (1 if repeat != 2 else 2) if kind == "noise" and key[3] == "a"
                    else (2 if repeat != 2 else 1) if kind == "noise" else
                    balanced_orders()[repeat - 1].index(api) + 1 if kind == "measure"
                    else serial,
                    "status": "complete", "source_commit": cls.commit,
                    "artifacts": hashes, "host": observed_host(),
                    "runtime_sha256": sha256(runtime),
                    "process_image_sha256": sha256(runtime),
                    "process_image_method": "os_procfs" if sys.platform.startswith("linux")
                    else "os_process_api",
                    "probe_sha256": sha256(timer),
                    "ambient_environment": {},
                    "build_configuration": row["optimized_build"], "pid": pid,
                    "started_ns": host_start,
                    "ended_ns": host_start + 180000000000,
                    "wall_ns": 180000000000,
                    "command": [str(runtime), "-Xmx256m", "-cp",
                                ":".join((str(harness), str(adapter), str(baseline),
                                          str(cls.root / "staged-core.jar"),
                                          str(cls.root / "staged-kotlin.jar"))),
                                "SyntheticHarness", *tail], "runner_path": str(runtime),
                    "runner_sha256": sha256(runtime),
                    "raw_path": str(raw.relative_to(cls.root)), "raw_sha256": sha256(raw),
                    "stderr_path": str(stderr.relative_to(cls.root)),
                    "stderr_sha256": sha256(stderr),
                    "warmup_clock_path": str(warmup_clock.relative_to(cls.root)),
                    "warmup_clock_sha256": sha256(warmup_clock),
                    "provider_path": str(provider.relative_to(cls.root)),
                    "provider_sha256": sha256(provider),
                    "process_image_receipt_path": str(image_receipt.relative_to(cls.root)),
                    "process_image_receipt_sha256": sha256(image_receipt),
                    "clock_origin_path": str(clock_origin.relative_to(cls.root)),
                    "clock_origin_sha256": sha256(clock_origin),
                    "clock_origin_receipt_path": str(clock_origin_receipt.relative_to(cls.root)),
                    "clock_origin_receipt_sha256": sha256(clock_origin_receipt),
                    "clock_nonce": nonce}
            item["exit_code"] = 0
            if kind == "report":
                write_csv(stress_monitor, ("elapsed_ns", "rss_bytes", "action"),
                          ((1_000_000, 2000, "running"),
                           (180_000_000_000, 2000, "completed")))
                item.update(stress_monitor_path=str(stress_monitor.relative_to(cls.root)),
                            stress_monitor_sha256=sha256(stress_monitor),
                            stress_monitor_method="linux_proc_vmhwm_v1",
                            stress_peak_rss_bytes=2000,
                            termination_reason="completed")
                stress_receipt.write_text(json.dumps({
                    "pid": pid, "method": "linux_proc_vmhwm_v1",
                    "process_image_sha256": sha256(runtime),
                    "process_image_observed_ns": host_start + 1,
                    "started_ns": item["started_ns"], "ended_ns": item["ended_ns"],
                    "sample_count": 2, "peak_rss_bytes": 2000,
                    "termination_reason": "completed", "exit_code": 0}))
                item.update(stress_monitor_receipt_path=str(stress_receipt.relative_to(cls.root)),
                            stress_monitor_receipt_sha256=sha256(stress_receipt))
            if mode == "memory":
                item.update(memory_path=str(memory.relative_to(cls.root)),
                            memory_sha256=sha256(memory))
            if kind != "plateau":
                item.update(clock_path=str(clock.relative_to(cls.root)),
                            clock_sha256=sha256(clock))
            if kind in ("measure", "report"):
                item["summary"] = step_summary(rows, mode, hz)
            if kind == "noise":
                item["side"] = key[3]
            index["captures"].append(item)
        index["signature"] = signature(index, cls.key)
        (cls.root / "archive.json").write_text(json.dumps(index))

    def verify(self, root=None, policy=None):
        def fast_interval(first, second, hz, metric, draws):
            self.assertEqual(2000, draws)
            return bootstrap_ratio(first, second, hz, metric=metric, draws=8, seed=17017)
        with patch("sustained_archive.interval", side_effect=fast_interval):
            return _verify_archive(root or self.root, self.key, self.commit,
                                   policy or self.policy)

    def cli_verify(self, root=None, policy=None, fast=True, trusted_key_path=None):
        key_path = Path(trusted_key_path) if trusted_key_path else Path(self.folder.name) / "operator.key"
        args = ["sustained_archive.py", "verify", "--archive", str(root or self.root),
                "--trusted-key", str(key_path),
                "--expected-source-commit", self.commit]
        if trusted_key_path is None:
            key_path.write_bytes(self.key)
        output = io.StringIO()
        def fast_interval(first, second, hz, metric, draws):
            self.assertEqual(2000, draws)
            return bootstrap_ratio(first, second, hz, metric=metric, draws=8, seed=17017)
        with patch.object(sys, "argv", args), patch("sustained_archive.frozen_policy",
                                                   return_value=policy or self.policy), \
             contextlib.redirect_stdout(output):
            with patch("sustained_archive.interval", side_effect=fast_interval) if fast else contextlib.nullcontext():
                try:
                    main()
                    status = 0
                except SystemExit as exc:
                    status = exc.code
        return status, json.loads(output.getvalue())

    def changed_archive(self, mutation):
        if hasattr(type(self), "_mutation_root"):
            shutil.rmtree(type(self)._mutation_root)
        copy_root = Path(self.folder.name) / f"mutation-{mutation}"
        shutil.copytree(self.root, copy_root)
        type(self)._mutation_root = copy_root
        index_path = copy_root / "archive.json"
        index = json.loads(index_path.read_text())
        return copy_root, index_path, index

    def reseal(self, index_path, index):
        index["signature"] = signature(index, self.key)
        index_path.write_text(json.dumps(index))

    def increase_compatibility_timing(self, root, index):
        item = next(item for item in index["captures"] if item["kind"] == "measure" and
                    item["mode"] == "timing" and
                    item["scenario_id"].endswith("compatibility"))
        raw = root / item["raw_path"]
        clock = root / item["clock_path"]
        with raw.open() as stream:
            rows = list(csv.DictReader(stream))
        with clock.open() as stream:
            stamps = list(csv.DictReader(stream))
        for row, stamp in zip(rows, stamps):
            row["elapsed_ns"] = "9000000"
            stamp["end_ns"] = str(int(stamp["begin_ns"]) + 9000000)
        write_csv(raw, STEP_FIELDS, ([row[field] for field in STEP_FIELDS] for row in rows))
        write_csv(clock, CLOCK_FIELDS,
                  ([stamp[field] for field in CLOCK_FIELDS] for stamp in stamps))
        item["raw_sha256"] = sha256(raw)
        item["clock_sha256"] = sha256(clock)
        item["summary"] = step_summary(rows, "timing", 30)

    def test_complete_synthetic_raw_archive_passes_protocol(self):
        result = self.verify()
        self.assertEqual("passed", result["qualification"])
        self.assertEqual(27, result["measurements"])
        self.assertEqual(9, result["stress_reports"])
        self.assertEqual(6, result["noise_runs"])
        self.assertEqual(3, result["plateaus"])
        analysis = Path(result["analysis_path"])
        self.assertEqual(sha256(analysis), result["analysis_sha256"])
        records = [json.loads(line) for line in analysis.read_text().splitlines()]
        self.assertEqual(18, sum(item["kind"] == "noise_interval" for item in records))
        self.assertTrue(any(item["kind"] == "budget_interval" for item in records))

    def test_public_verify_accepts_complete_signed_archive_with_full_intervals(self):
        status, result = self.cli_verify(fast=False)
        self.assertEqual(0, status)
        self.assertEqual("passed", result["qualification"])
        self.assertEqual(18, result["noise_intervals"])

    def test_public_verify_checks_optional_versioned_host_resource_and_run_sidecars(self):
        root, index_path, index = self.changed_archive("versioned-sidecars")
        item = next(record for record in index["captures"] if record["kind"] == "measure" and
                    record["mode"] == "timing" and record["scenario_id"].endswith("baseline"))
        with (root / item["raw_path"]).open() as stream:
            raw = list(csv.DictReader(stream))
        warm = 120 * 30
        resource = root / Path(item["raw_path"]).parent / "resource.csv"
        fields = ("phase", "step", "heap_used_bytes", "rss_bytes", "allocation_bytes")
        rows = [("empty", 0, 1000, 2000, -1), ("construction", 0, 1000, 2000, -1)]
        rows.extend(("warmup", step, 1000, 2000, -1) for step in range(warm))
        rows.extend(("measure", step, 1000, 2000, -1) for step in range(len(raw)))
        write_csv(resource, fields, rows)
        run = resource.with_name("run.json")
        run.write_text(json.dumps({"api": "baseline", "mode": "timing", "sample_count": len(raw),
                                   "warmup_count": warm, "measured_wall_ns": 60_000_000_000,
                                   "active_steps": len(raw), "peak_heap_used_bytes": 1000,
                                   "peak_rss_bytes": 2000, "memory_attribution": "unvalidated",
                                   "status": "complete"}))
        item.update(resource_path=str(resource.relative_to(root)), resource_sha256=sha256(resource),
                    run_path=str(run.relative_to(root)), run_sha256=sha256(run))
        self.reseal(index_path, index)
        status, result = self.cli_verify(root)
        self.assertEqual(0, status, result)
        rows[-1] = ("measure", len(raw) - 1, 1001, 2000, -1)
        write_csv(resource, fields, rows)
        item["resource_sha256"] = sha256(resource)
        self.reseal(index_path, index)
        status, result = self.cli_verify(root)
        self.assertNotEqual(0, status)
        self.assertIn("resource", result["reason"])

    def test_public_verify_rejects_resealed_clocks_outside_claimed_process(self):
        root, index_path, index = self.changed_archive("outside-process-clocks")
        item = next(record for record in index["captures"] if record["kind"] == "measure" and
                    record["mode"] == "timing" and record["scenario_id"].endswith("baseline"))
        for stem in ("warmup_clock", "clock"):
            path = root / item[stem + "_path"]
            with path.open(newline="") as stream:
                reader = csv.DictReader(stream)
                fields = reader.fieldnames
                rows = list(reader)
            for row in rows:
                row["begin_ns"] = str(int(row["begin_ns"]) + 1_000_000_000_000)
                row["end_ns"] = str(int(row["end_ns"]) + 1_000_000_000_000)
            write_csv(path, fields, ([row[field] for field in fields] for row in rows))
            item[stem + "_sha256"] = sha256(path)
        self.reseal(index_path, index)
        status, result = self.cli_verify(root)
        self.assertNotEqual(0, status)
        self.assertIn("process-bound clock", result["reason"])

    def test_public_verify_rejects_resealed_clock_origin_and_stress_method(self):
        root, index_path, index = self.changed_archive("clock-origin-receipt")
        item = index["captures"][0]
        path = root / item["clock_origin_receipt_path"]
        receipt = json.loads(path.read_text())
        receipt["host_after_ns"] = item["ended_ns"] + 1
        path.write_text(json.dumps(receipt))
        item["clock_origin_receipt_sha256"] = sha256(path)
        self.reseal(index_path, index)
        status, result = self.cli_verify(root)
        self.assertNotEqual(0, status)
        self.assertIn("process-bound clock origin", result["reason"])

        root, index_path, index = self.changed_archive("stress-method")
        item = next(record for record in index["captures"] if record["kind"] == "report")
        item["stress_monitor_method"] = "unsupported_windows_external_peak_v1"
        self.reseal(index_path, index)
        status, result = self.cli_verify(root)
        self.assertNotEqual(0, status)
        self.assertIn("external peak RSS monitor is unvalidated", result["reason"])

    def test_public_verify_reports_missing_approved_noise_and_stress_policy(self):
        for field in ("noise_upper_ratio_max", "stress_wall_ns_max",
                      "stress_rss_bytes_max"):
            with self.subTest(field=field):
                policy = copy.deepcopy(self.policy)
                policy["sustained_gate"].pop(field)
                status, result = self.cli_verify(policy=policy)
                self.assertNotEqual(0, status)
                self.assertEqual("unpassed", result["qualification"])
                self.assertIn("unpassed policy", result["reason"])

    def remote_sources(self, root, index, system="Linux"):
        reference = index["references"]["jvm.java"]
        host = {**reference["host"], "hostname": "unavailable-source-host",
                "system": system}
        reference["host"] = host
        old_runtime = reference["runtime"]["path"]
        old_harness = reference["harness"]["path"]
        new_runtime = "/unavailable-source-host/runtime/java"
        new_harness = "/unavailable-source-host/harness/harness.bin"
        reference["runtime"]["path"] = new_runtime
        reference["harness"]["path"] = new_harness
        for item in index["captures"]:
            item["host"] = host
            item["runner_path"] = new_runtime
            item["command"][0] = new_runtime
            item["command"][3] = item["command"][3].replace(old_harness, new_harness)
            item["process_image_method"] = {"Linux": "os_procfs",
                                            "Darwin": "macos_libproc",
                                            "Windows": "windows_query_image"}[system]
            receipt_path = root / item["process_image_receipt_path"]
            receipt = json.loads(receipt_path.read_text())
            receipt["method"] = item["process_image_method"]
            receipt["executable_path"] = new_runtime
            receipt_path.write_text(json.dumps(receipt))
            item["process_image_receipt_sha256"] = sha256(receipt_path)
        self.assertFalse(Path(new_runtime).exists())
        self.assertFalse(Path(new_harness).exists())

    def add_stress_receipts(self, root, index, system):
        method = {"Linux": "linux_proc_vmhwm_v1",
                  "Darwin": "macos_wait4_maxrss_v1",
                  "Windows": "windows_psapi_peak_working_set_v1"}[system]
        for item in index["captures"]:
            if item["kind"] != "report":
                continue
            item["stress_monitor_method"] = method
            image = json.loads((root / item["process_image_receipt_path"]).read_text())
            monitor = list(csv.DictReader((root / item["stress_monitor_path"]).read_text().splitlines()))
            if system == "Darwin":
                monitor[-1]["rss_bytes"] = "4096"
                monitor_path = root / item["stress_monitor_path"]
                write_csv(monitor_path, ("elapsed_ns", "rss_bytes", "action"),
                          ([row[field] for field in ("elapsed_ns", "rss_bytes", "action")]
                           for row in monitor))
                item["stress_monitor_sha256"] = sha256(monitor_path)
                item["stress_peak_rss_bytes"] = 4096
            receipt = {"pid": item["pid"], "method": method,
                       "process_image_sha256": image["sha256"],
                       "process_image_observed_ns": image["observed_ns"],
                       "started_ns": item["started_ns"], "ended_ns": item["ended_ns"],
                       "sample_count": len(monitor),
                       "peak_rss_bytes": item["stress_peak_rss_bytes"],
                       "termination_reason": "completed", "exit_code": 0}
            if system == "Darwin":
                receipt.update(metric_kind="peak_rss_bytes", terminal_pid=item["pid"],
                               terminal_wait_status=0, terminal_ru_maxrss_bytes=4096)
            path = root / Path(item["stress_monitor_path"]).with_name("stress-receipt.json")
            path.write_text(json.dumps(receipt))
            item["stress_monitor_receipt_path"] = str(path.relative_to(root))
            item["stress_monitor_receipt_sha256"] = sha256(path)

    def test_public_verify_accepts_signed_mac_and_windows_external_monitor_receipts(self):
        for system in ("Darwin", "Windows"):
            with self.subTest(system=system):
                root, index_path, index = self.changed_archive(system.lower() + "-monitor")
                self.remote_sources(root, index, system=system)
                self.add_stress_receipts(root, index, system)
                self.reseal(index_path, index)
                status, result = self.cli_verify(root)
                self.assertEqual(0, status, result)
                self.assertEqual("passed", result["qualification"])
                item = next(row for row in index["captures"] if row["kind"] == "report")
                receipt_path = root / item["stress_monitor_receipt_path"]
                original = json.loads(receipt_path.read_text())
                for field, value in (("process_image_sha256", "0" * 64),
                                     ("process_image_observed_ns", item["ended_ns"] + 1),
                                     ("pid", item["pid"] + 1),
                                     ("method", "unbound_method"),
                                     ("sample_count", 1),
                                     ("termination_reason", "wall_limit")):
                    with self.subTest(system=system, field=field):
                        receipt = {**original, field: value}
                        receipt_path.write_text(json.dumps(receipt))
                        item["stress_monitor_receipt_sha256"] = sha256(receipt_path)
                        self.reseal(index_path, index)
                        status, result = self.cli_verify(root)
                        self.assertNotEqual(0, status)
                        self.assertIn("stress monitor receipt", result["reason"])

    def test_public_verify_rejects_resealed_darwin_terminal_high_water_attacks(self):
        root, index_path, index = self.changed_archive("darwin-terminal-high-water")
        self.remote_sources(root, index, system="Darwin")
        self.add_stress_receipts(root, index, "Darwin")
        self.reseal(index_path, index)
        status, result = self.cli_verify(root)
        self.assertEqual(0, status, result)
        item = next(row for row in index["captures"] if row["kind"] == "report")
        receipt_path = root / item["stress_monitor_receipt_path"]
        original = json.loads(receipt_path.read_text())
        for field, value in (("terminal_pid", item["pid"] + 1),
                             ("metric_kind", "physical_footprint_bytes"),
                             ("terminal_wait_status", 256),
                             ("terminal_ru_maxrss_bytes", 1),
                             ("terminal_ru_maxrss_bytes", 3 * 1024 ** 3 + 1)):
            with self.subTest(field=field, value=value):
                receipt_path.write_text(json.dumps({**original, field: value}))
                item["stress_monitor_receipt_sha256"] = sha256(receipt_path)
                self.reseal(index_path, index)
                status, result = self.cli_verify(root)
                self.assertNotEqual(0, status)
        receipt_path.write_text(json.dumps({key: value for key, value in original.items()
                                            if key != "terminal_ru_maxrss_bytes"}))
        item["stress_monitor_receipt_sha256"] = sha256(receipt_path)
        self.reseal(index_path, index)
        status, result = self.cli_verify(root)
        self.assertNotEqual(0, status)

    def test_public_verify_rejects_darwin_spike_missed_by_samples(self):
        root, index_path, index = self.changed_archive("darwin-missed-spike")
        self.remote_sources(root, index, system="Darwin")
        self.add_stress_receipts(root, index, "Darwin")
        item = next(row for row in index["captures"] if row["kind"] == "report")
        high_water = 3 * 1024 ** 3 + 1024
        monitor_path = root / item["stress_monitor_path"]
        monitor = list(csv.DictReader(monitor_path.read_text().splitlines()))
        self.assertEqual("2000", monitor[0]["rss_bytes"])
        monitor[-1]["rss_bytes"] = str(high_water)
        write_csv(monitor_path, ("elapsed_ns", "rss_bytes", "action"),
                  ([row[field] for field in ("elapsed_ns", "rss_bytes", "action")]
                   for row in monitor))
        item["stress_monitor_sha256"] = sha256(monitor_path)
        item["stress_peak_rss_bytes"] = high_water
        receipt_path = root / item["stress_monitor_receipt_path"]
        receipt = json.loads(receipt_path.read_text())
        receipt["peak_rss_bytes"] = high_water
        receipt["terminal_ru_maxrss_bytes"] = high_water
        receipt_path.write_text(json.dumps(receipt))
        item["stress_monitor_receipt_sha256"] = sha256(receipt_path)
        self.reseal(index_path, index)
        status, result = self.cli_verify(root)
        self.assertNotEqual(0, status)
        self.assertIn("stress wall, memory", result["reason"])

    def test_public_verify_rejects_signed_stress_sample_before_image_observation(self):
        root, index_path, index = self.changed_archive("preimage-stress-sample")
        item = next(row for row in index["captures"] if row["kind"] == "report")
        path = root / item["stress_monitor_path"]
        rows = list(csv.DictReader(path.read_text().splitlines()))
        rows[0]["elapsed_ns"] = "0"
        write_csv(path, ("elapsed_ns", "rss_bytes", "action"),
                  ([row[field] for field in ("elapsed_ns", "rss_bytes", "action")]
                   for row in rows))
        item["stress_monitor_sha256"] = sha256(path)
        self.reseal(index_path, index)
        status, result = self.cli_verify(root)
        self.assertNotEqual(0, status)
        self.assertIn("stress monitor stream", result["reason"])

    def test_public_verify_rejects_signed_decreasing_os_peak_stream(self):
        root, index_path, index = self.changed_archive("decreasing-os-peak")
        item = next(row for row in index["captures"] if row["kind"] == "report")
        path = root / item["stress_monitor_path"]
        rows = list(csv.DictReader(path.read_text().splitlines()))
        rows[-1]["rss_bytes"] = "1999"
        write_csv(path, ("elapsed_ns", "rss_bytes", "action"),
                  ([row[field] for field in ("elapsed_ns", "rss_bytes", "action")]
                   for row in rows))
        item["stress_monitor_sha256"] = sha256(path)
        self.reseal(index_path, index)
        status, result = self.cli_verify(root)
        self.assertNotEqual(0, status)
        self.assertIn("stress monitor stream", result["reason"])

    def test_public_full_verifier_rejects_partial_version_two_process_stream(self):
        root, index_path, index = self.changed_archive("partial-version-two-stream")
        item = next(record for record in index["captures"]
                    if record["kind"] == "measure" and record["mode"] == "allocation")
        path = root / Path(item["raw_path"]).with_name("allocation-v2.jsonl")
        path.write_text("{}\n")
        item["allocation_v2_path"] = str(path.relative_to(root))
        item["allocation_v2_sha256"] = sha256(path)
        self.reseal(index_path, index)
        status, result = self.cli_verify(root)
        self.assertNotEqual(0, status)
        self.assertIn("version 2 process sidecars are partial", result["reason"])

    def test_public_verify_accepts_off_host_runner_and_harness_archive_bytes(self):
        root, path, index = self.changed_archive("remote-runner")
        self.remote_sources(root, index)
        self.reseal(path, index)
        status, result = self.cli_verify(root)
        self.assertEqual(0, status, result)
        self.assertEqual("passed", result["qualification"])
        item = index["captures"][0]
        item["runner_sha256"] = "0" * 64
        self.reseal(path, index)
        status, result = self.cli_verify(root)
        self.assertNotEqual(0, status)
        self.assertIn("runner identity", result["reason"])

    def test_public_verify_checks_nonlinux_os_receipt_not_provider_self_report(self):
        root, path, index = self.changed_archive("nonlinux-receipt")
        self.remote_sources(root, index, system="Darwin")
        self.reseal(path, index)
        status, result = self.cli_verify(root)
        self.assertNotEqual(0, status)
        self.assertIn("external peak RSS monitor is unvalidated", result["reason"])
        item = index["captures"][0]
        provider_path = root / item["provider_path"]
        provider = json.loads(provider_path.read_text())
        provider["process_image_sha256"] = item["runtime_sha256"]
        provider_path.write_text(json.dumps(provider))
        item["provider_sha256"] = sha256(provider_path)
        receipt_path = root / item["process_image_receipt_path"]
        receipt = json.loads(receipt_path.read_text())
        receipt["sha256"] = "0" * 64
        receipt_path.write_text(json.dumps(receipt))
        item["process_image_receipt_sha256"] = sha256(receipt_path)
        self.reseal(path, index)
        status, result = self.cli_verify(root)
        self.assertNotEqual(0, status)
        self.assertIn("OS process image", result["reason"])
        receipt["sha256"] = item["runtime_sha256"]
        receipt["observed_ns"] = item["ended_ns"] + 1
        receipt_path.write_text(json.dumps(receipt))
        item["process_image_receipt_sha256"] = sha256(receipt_path)
        self.reseal(path, index)
        status, result = self.cli_verify(root)
        self.assertNotEqual(0, status)
        self.assertIn("OS process image", result["reason"])

    def test_public_verify_rejects_archive_key_and_symlink_and_hardlink_aliases(self):
        external = Path(self.folder.name) / "external-operator.key"
        external.write_bytes(self.key)
        root, _, _ = self.changed_archive("key-custody")
        internal = root / "operator.key"
        internal.write_bytes(self.key)
        aliases = [("direct", internal)]
        symlink = root / "key-symlink"
        symlink.symlink_to(external)
        aliases.append(("symlink", symlink))
        outside_alias = Path(self.folder.name) / "outside-to-inside.key"
        outside_alias.symlink_to(internal)
        aliases.append(("outside-alias", outside_alias))
        hardlink = root / "key-hardlink"
        hardlink.hardlink_to(external)
        aliases.append(("hardlink", external))
        for name, key_path in aliases:
            with self.subTest(name=name):
                status, result = self.cli_verify(root, trusted_key_path=key_path)
                self.assertNotEqual(0, status)
                self.assertIn("trusted key must stay outside", result["reason"])

    def test_public_verify_rejects_signed_harness_command_and_build_mutations(self):
        for name, mutate in (
            ("unbound-flag", lambda index: next(item for item in index["captures"]
                if item["kind"] == "measure")["command"].insert(1, "--unbound-harness")),
            ("classpath", lambda index: next(item for item in index["captures"]
                if item["kind"] == "measure")["command"].__setitem__(
                    3, index["captures"][0]["command"][3] + ":/tmp/unapproved.jar")),
            ("jvm-option", lambda index: next(item for item in index["captures"]
                if item["kind"] == "measure")["command"].__setitem__(1, "-Xmx512m")),
            ("environment", lambda index: next(item for item in index["captures"]
                if item["kind"] == "measure")["ambient_environment"].update(
                    JAVA_TOOL_OPTIONS="-Xmx512m")),
            ("development", lambda index: self._development_build(index)),
            ("wrong-harness", lambda index: index["references"]["jvm.java"]["harness"].update(
                sha256="0" * 64)),
            ("wrong-adapter", lambda index: index["references"]["jvm.java"]["adapter"].update(
                sha256="0" * 64)),
            ("wrong-fixture", lambda index: self._mutate_provider(index, "loaded_fixture_sha256",
                                                                  "0" * 64))):
            with self.subTest(name=name):
                root, path, index = self.changed_archive("review-command-" + name)
                mutate(index)
                self.reseal(path, index)
                status, result = self.cli_verify(root)
                self.assertNotEqual(0, status)
                self.assertEqual("unpassed", result["qualification"])

    def _development_build(self, index):
        reference = index["references"]["jvm.java"]
        reference["build_configuration"] = reference["development_build"]
        changed = self._mutation_root / reference["build_receipt"]["archive_path"]
        record = json.loads(changed.read_text())
        record["build_configuration"] = reference["development_build"]
        changed.write_text(json.dumps(record))
        reference["build_receipt"]["sha256"] = sha256(changed)
        for item in index["captures"]:
            item["build_configuration"] = reference["development_build"]

    def _mutate_provider(self, index, field, value):
        item = next(item for item in index["captures"] if item["kind"] == "measure")
        provider = self._mutation_root / item["provider_path"]
        record = json.loads(provider.read_text())
        record[field] = value
        provider.write_text(json.dumps(record))
        item["provider_sha256"] = sha256(provider)

    def test_public_verify_rejects_signed_cycle_rss_noise_exit_and_stress_mutations(self):
        for name in ("cycle-native", "cycle-rss", "noise", "exit", "exit-malformed",
                     "stress-wall", "stress-rss", "stress-reason", "stress-monitor"):
            with self.subTest(name=name):
                root, path, index = self.changed_archive("review-control-" + name)
                if name.startswith("cycle"):
                    item = next(item for item in index["captures"] if item["kind"] == "plateau")
                    raw = root / item["raw_path"]
                    rows = list(csv.DictReader(raw.read_text().splitlines()))
                    for cycle, row in enumerate(rows):
                        if name == "cycle-native":
                            row["native_bytes"] = str(cycle * 1_000_000)
                            row["attributed_workload_bytes"] = str(100 + cycle * 1_000_000)
                            row["rss_after_collection_bytes"] = str(2000 + cycle * 1_000_000)
                        else:
                            row["rss_after_collection_bytes"] = str(2000 + cycle * 1_000_000)
                    write_csv(raw, PLATEAU_FIELDS,
                              ([row[field] for field in PLATEAU_FIELDS] for row in rows))
                    item["raw_sha256"] = sha256(raw)
                elif name == "noise":
                    item = next(item for item in index["captures"] if item["kind"] == "noise"
                                and item["side"] == "b")
                    raw = root / item["raw_path"]
                    clock = root / item["clock_path"]
                    rows = list(csv.DictReader(raw.read_text().splitlines()))
                    stamps = list(csv.DictReader(clock.read_text().splitlines()))
                    for row, stamp in zip(rows, stamps):
                        row["elapsed_ns"] = str(int(row["elapsed_ns"]) * 100)
                        stamp["end_ns"] = str(int(stamp["begin_ns"]) + int(row["elapsed_ns"]))
                    write_csv(raw, STEP_FIELDS,
                              ([row[field] for field in STEP_FIELDS] for row in rows))
                    write_csv(clock, CLOCK_FIELDS,
                              ([row[field] for field in CLOCK_FIELDS] for row in stamps))
                    item["raw_sha256"] = sha256(raw)
                    item["clock_sha256"] = sha256(clock)
                elif name.startswith("exit"):
                    item = next(item for item in index["captures"] if item["kind"] == "measure")
                    item["exit_code"] = 7 if name == "exit" else "0"
                else:
                    item = next(item for item in index["captures"] if item["kind"] == "report")
                    if name == "stress-wall":
                        item["wall_ns"] = 201_000_000_000
                        item["ended_ns"] = item["started_ns"] + item["wall_ns"]
                    elif name == "stress-rss":
                        item["stress_peak_rss_bytes"] = 3 * 1024 ** 3 + 1
                    elif name == "stress-monitor":
                        monitor = root / item["stress_monitor_path"]
                        rows = list(csv.DictReader(monitor.read_text().splitlines()))
                        rows[0]["rss_bytes"] = str(3 * 1024 ** 3 + 1)
                        write_csv(monitor, ("elapsed_ns", "rss_bytes", "action"),
                                  ([row[field] for field in ("elapsed_ns", "rss_bytes", "action")]
                                   for row in rows))
                        item["stress_monitor_sha256"] = sha256(monitor)
                    else:
                        item["termination_reason"] = "unknown"
                self.reseal(path, index)
                status, result = self.cli_verify(root)
                self.assertNotEqual(0, status)
                self.assertEqual("unpassed", result["qualification"])
                if name == "noise":
                    self.assertIn("noise calibration is inconclusive", result["reason"])
                if name == "cycle-native":
                    self.assertIn("attributable native_bytes", result["reason"])
                if name == "cycle-rss":
                    self.assertIn("unexplained RSS growth", result["reason"])
                if name == "stress-monitor":
                    self.assertIn("stress monitor stream", result["reason"])

    def test_zero_allocation_baseline_and_candidate_pass_but_positive_candidate_fails(self):
        root, path, index = self.changed_archive("zero-allocation")
        for item in index["captures"]:
            if item["kind"] != "measure" or item["mode"] != "allocation":
                continue
            raw = root / item["raw_path"]
            rows = list(csv.DictReader(raw.read_text().splitlines()))
            for row in rows:
                row["allocation_bytes"] = "0"
            write_csv(raw, STEP_FIELDS,
                      ([row[field] for field in STEP_FIELDS] for row in rows))
            item["raw_sha256"] = sha256(raw)
            item["summary"] = step_summary(rows, "allocation", 30)
            stderr = root / item["stderr_path"]
            stderr.write_text(stderr.read_text().replace("#construction_allocated_bytes=100",
                                                         "#construction_allocated_bytes=0"))
            item["stderr_sha256"] = sha256(stderr)
        self.reseal(path, index)
        status, result = self.cli_verify(root)
        self.assertEqual(0, status, result)
        item = next(item for item in index["captures"] if item["kind"] == "measure" and
                    item["mode"] == "allocation" and
                    item["scenario_id"].endswith("direct_kotlin"))
        raw = root / item["raw_path"]
        rows = list(csv.DictReader(raw.read_text().splitlines()))
        rows[0]["allocation_bytes"] = "1"
        write_csv(raw, STEP_FIELDS,
                  ([row[field] for field in STEP_FIELDS] for row in rows))
        item["raw_sha256"] = sha256(raw)
        item["summary"] = step_summary(rows, "allocation", 30)
        self.reseal(path, index)
        status, result = self.cli_verify(root)
        self.assertNotEqual(0, status)
        self.assertEqual("unpassed", result["qualification"])

    def test_stress_timing_remains_report_only(self):
        root, path, index = self.changed_archive("slow-stress-report")
        item = next(item for item in index["captures"] if item["kind"] == "report" and
                    item["mode"] == "timing" and
                    item["scenario_id"].endswith("direct_kotlin"))
        raw = root / item["raw_path"]
        clock = root / item["clock_path"]
        rows = list(csv.DictReader(raw.read_text().splitlines()))
        stamps = list(csv.DictReader(clock.read_text().splitlines()))
        for row, stamp in zip(rows, stamps):
            row["elapsed_ns"] = "20000000"
            stamp["end_ns"] = str(int(stamp["begin_ns"]) + 20_000_000)
        write_csv(raw, STEP_FIELDS, ([row[field] for field in STEP_FIELDS] for row in rows))
        write_csv(clock, CLOCK_FIELDS,
                  ([stamp[field] for field in CLOCK_FIELDS] for stamp in stamps))
        item["raw_sha256"] = sha256(raw)
        item["clock_sha256"] = sha256(clock)
        item["summary"] = step_summary(rows, "timing", 30)
        self.reseal(path, index)
        status, result = self.cli_verify(root)
        self.assertEqual(0, status, result)
        self.assertEqual("passed", result["qualification"])

    def test_signed_host_part_merges_into_verifiable_archive(self):
        destination = Path(self.folder.name) / "merged"
        result = merge_parts(destination, [self.root], self.key, policy=self.policy)
        self.assertEqual("passed", result["qualification"])
        self.assertEqual(1, result["reference_rows"])

    def test_producer_rejects_unapproved_runner_and_signs_failed_process(self):
        root, path, index = self.changed_archive("producer")
        removed = index["captures"].pop()
        self.reseal(path, index)
        runner = root / "short-runner.py"
        runner.write_text("#!/usr/bin/env python3\n"
                          "import sys\n"
                          "print('cycle,heap_after_collection_bytes,rss_after_collection_bytes,collection_count')\n"
                          "print('0,100,100,1')\n"
                          "print('warmup_step,elapsed_ns', file=sys.stderr)\n")
        os.chmod(runner, 0o755)
        job = {name: removed[name] for name in
               ("kind", "row_id", "scenario_id", "mode", "repeat", "sequence")}
        job["command"] = [str(runner.resolve()), "separated", "default", "small",
                          "30", "1", "plateau", "3600", "compatibility"]
        with patch("sustained_archive.frozen_policy", return_value=self.policy):
            with self.assertRaisesRegex(ValueError, "capture command"):
                capture_one(root, job, self.key)
            job["command"] = removed["command"]
            result = capture_one(root, job, self.key)
        self.assertIn(result["status"], ("failed", "invalid_raw"))
        saved = json.loads(path.read_text())
        self.assertEqual(saved["signature"], signature(saved, self.key))
        self.assertEqual(len(index["captures"]) + 1, len(saved["captures"]))
        captured = saved["captures"][-1]
        self.assertEqual(sha256(root / captured["raw_path"]), captured["raw_sha256"])

    def test_initializer_requires_optimized_build_and_copies_approved_binaries(self):
        index = json.loads((self.root / "archive.json").read_text())
        reference = copy.deepcopy(index["references"]["jvm.java"])
        reference["build_receipt"]["source_path"] = str(
            self.root / reference["build_receipt"]["archive_path"])
        reference["probe"]["timer_source_path"] = str(
            self.root / reference["probe"]["timer_raw"])
        reference["probe"]["allocation_source_path"] = str(
            self.root / reference["probe"]["allocation_raw"])
        config = {"source_commit": self.commit,
                  "baseline_path": index["baseline"]["staged_path"],
                  "artifacts": {"jvm.java": {name: record["staged_path"] for name, record in
                                               index["artifacts"]["jvm.java"].items()}},
                  "references": {"jvm.java": reference}}
        bad = copy.deepcopy(config)
        bad["references"]["jvm.java"]["build_configuration"] = \
            reference["development_build"]
        with patch("sustained_archive.frozen_policy", return_value=self.policy):
            with self.assertRaisesRegex(ValueError, "build configuration differs"):
                initialize_archive(Path(self.folder.name) / "init-development", bad, self.key)
            initialized = initialize_archive(Path(self.folder.name) / "init-optimized",
                                             config, self.key)
        self.assertEqual(self.policy["sustained_gate"]["harnesses"]["jvm.java"]["sha256"],
                         initialized["references"]["jvm.java"]["harness"]["sha256"])
        self.assertEqual(self.policy["sustained_gate"]["harnesses"]["jvm.java"]["adapter_sha256"],
                         initialized["references"]["jvm.java"]["adapter"]["sha256"])

    def test_unsigned_rehash_and_signed_semantic_mutation_fail(self):
        root, path, index = self.changed_archive("forged")
        index["captures"][0]["raw_sha256"] = "0" * 64
        path.write_text(json.dumps(index))
        with self.assertRaisesRegex(ValueError, "signature"):
            self.verify(root)
        self.reseal(path, index)
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            self.verify(root)

    def test_missing_case_and_short_process_fail(self):
        root, path, index = self.changed_archive("missing")
        index["captures"].pop()
        self.reseal(path, index)
        with self.assertRaisesRegex(ValueError, "matrix is partial"):
            self.verify(root)
        root, path, index = self.changed_archive("short")
        item = index["captures"][0]
        item["ended_ns"] = item["started_ns"] + 1
        item["wall_ns"] = 1
        self.reseal(path, index)
        with self.assertRaisesRegex(ValueError, "shorter than warm-up"):
            self.verify(root)

    def test_rehashed_memory_budget_violation_fails(self):
        root, path, index = self.changed_archive("memory")
        item = next(item for item in index["captures"] if item["mode"] == "memory" and
                    item["kind"] == "measure" and
                    item["scenario_id"].endswith("direct_kotlin"))
        memory = root / item["memory_path"]
        with memory.open() as stream:
            rows = list(csv.DictReader(stream))
        rows[-1]["managed_bytes"] = str(16 * 1048576 + 1)
        rows[-1]["attributed_workload_bytes"] = rows[-1]["managed_bytes"]
        write_csv(memory, MEMORY_FIELDS,
                  ([row[field] for field in MEMORY_FIELDS] for row in rows))
        item["memory_sha256"] = sha256(memory)
        self.reseal(path, index)
        with self.assertRaisesRegex(ValueError, "memory budget exceeded"):
            self.verify(root)

    def test_rehashed_wrong_environment_and_probe_fail(self):
        root, path, index = self.changed_archive("environment")
        index["references"]["jvm.java"]["runtime"]["sha256"] = "0" * 64
        self.reseal(path, index)
        with self.assertRaisesRegex(ValueError, "archive_path bytes differ"):
            self.verify(root)
        root, path, index = self.changed_archive("probe")
        index["references"]["jvm.java"]["probe"]["timer_p99_ns"] = 11
        self.reseal(path, index)
        with self.assertRaisesRegex(ValueError, "timer probe invalid"):
            self.verify(root)

    def test_wrong_clock_count_and_extra_scenario_fail(self):
        root, path, index = self.changed_archive("clock")
        item = next(item for item in index["captures"] if item["kind"] == "measure")
        clock = root / item["clock_path"]
        clock.write_text("\n".join(clock.read_text().splitlines()[:-1]) + "\n")
        item["clock_sha256"] = sha256(clock)
        self.reseal(path, index)
        with self.assertRaisesRegex(ValueError, "clock stream is incomplete"):
            self.verify(root)
        root, path, index = self.changed_archive("warmup-clock")
        item = next(item for item in index["captures"] if item["kind"] == "measure")
        clock = root / item["warmup_clock_path"]
        clock.write_text("\n".join(clock.read_text().splitlines()[:-1]) + "\n")
        item["warmup_clock_sha256"] = sha256(clock)
        self.reseal(path, index)
        with self.assertRaisesRegex(ValueError, "warm-up clock stream is incomplete"):
            self.verify(root)
        root, path, index = self.changed_archive("scenario")
        index["scenario_ids"].append("unexpected.default.small.30hz.direct_kotlin")
        self.reseal(path, index)
        with self.assertRaisesRegex(ValueError, "scenario inventory differs"):
            self.verify(root)

    def test_stale_source_artifact_and_process_identity_fail(self):
        with self.assertRaisesRegex(ValueError, "candidate source commit differs"):
            with patch("sustained_archive.interval", return_value={"upper_95": 1.0}):
                _verify_archive(self.root, self.key, "0" * 40, self.policy)
        root, path, index = self.changed_archive("artifact")
        artifact = root / index["artifacts"]["jvm.java"]["core"]["archive_path"]
        artifact.write_bytes(b"changed artifact")
        with self.assertRaisesRegex(ValueError, "archive_path bytes differ"):
            self.verify(root)
        root, path, index = self.changed_archive("process")
        index["captures"][0]["process_image_sha256"] = "0" * 64
        self.reseal(path, index)
        with self.assertRaisesRegex(ValueError, "executed host, runtime, or build differs"):
            self.verify(root)

    def test_missing_noise_pair_and_wrong_provider_fail(self):
        root, path, index = self.changed_archive("noise")
        index["captures"] = [item for item in index["captures"]
                             if not (item["kind"] == "noise" and item["repeat"] == 3 and
                                     item["side"] == "b")]
        self.reseal(path, index)
        with self.assertRaisesRegex(ValueError, "noise calibration matrix is partial"):
            self.verify(root)
        root, path, index = self.changed_archive("provider")
        item = next(item for item in index["captures"] if item["kind"] == "measure" and
                    item["scenario_id"].endswith("direct_kotlin"))
        provider = root / item["provider_path"]
        record = json.loads(provider.read_text())
        record["loaded_core_sha256"] = self.policy["baseline_jar_sha256"]
        provider.write_text(json.dumps(record))
        item["provider_sha256"] = sha256(provider)
        self.reseal(path, index)
        with self.assertRaisesRegex(ValueError, "loaded provider"):
            self.verify(root)

    def test_signed_timing_budget_violation_fails(self):
        root, path, index = self.changed_archive("timing")
        self.increase_compatibility_timing(root, index)
        self.reseal(path, index)
        with self.assertRaisesRegex(ValueError, "absolute p99"):
            self.verify(root)

    def test_report_only_assignment_retains_raw_run_without_budget_gate(self):
        root, path, index = self.changed_archive("report-only")
        policy = copy.deepcopy(self.policy)
        policy["runtime_rows"][0]["size_assignment"]["small"] = "report_only"
        index["references"]["jvm.java"]["size_assignment"]["small"] = "report_only"
        index["manifest_sha256"] = hashlib.sha256(canonical(policy)).hexdigest()
        self.increase_compatibility_timing(root, index)
        self.reseal(path, index)
        result = self.verify(root, policy=policy)
        self.assertEqual("passed", result["qualification"])
        self.assertEqual(27, result["measurements"])


if __name__ == "__main__":
    unittest.main()
