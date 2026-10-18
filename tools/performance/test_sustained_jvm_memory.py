import copy
import csv
import hashlib
import json
import os
import subprocess
import unittest
from pathlib import Path

from candidate_runner import ROOT


JDK = Path("/tmp/dyn4k-tools/jdk21")
BASELINE = Path("/tmp/dyn4k-performance-dyn4j-6.0.0.jar")
SOURCE = ROOT / "tools/performance/sustained_jvm"
RAW = Path(os.environ.get("DYN4K_JVM_CONTROL_ROOT",
                          Path.home() / "dyn4k-evidence/jvm-memory-plateau-p2-controls"))


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def validate_binding(records, provider, nonce, mode):
    assert records
    digest = hashlib.sha256(provider.read_bytes()).hexdigest()
    receipt = json.loads(provider.read_text())
    for row in records:
        assert row["schema"] == 2
        assert row["pid"] == receipt["pid"]
        assert row["provider_sha256"] == digest
        assert row["nonce"] == nonce
        assert row["source_commit"] == receipt["source_commit"]
        assert row["api"] == receipt["api"]
        assert row["fixture_sha256"] == receipt["loaded_fixture_sha256"]
        assert row["family"] == "separated" and row["variant"] == "default"
        assert row["size"] == "small" and row["rate_hz"] == 30
        assert row["mode"] == mode
        assert row["clock_ns"] > 0
        assert row["clock_domain"] == "System.nanoTime" and row["memory_unit"] == "byte"


def validate_allocation(records, raw):
    assert [(row["phase"], row["step"]) for row in records] == [
        ("construction", 0), ("warmup", 0), ("measure", 0)]
    for row in records:
        assert row["thread_id"] > 0
        assert row["counter_after_bytes"] >= row["counter_before_bytes"] >= 0
        assert row["allocation_bytes"] == row["counter_after_bytes"] - row["counter_before_bytes"]
        assert row["probe"] == "com.sun.management.ThreadMXBean.getThreadAllocatedBytes"
    with raw.open(newline="") as stream:
        measured = list(csv.DictReader(stream))
    assert len(measured) == 1
    assert int(measured[0]["allocation_bytes"]) == records[-1]["allocation_bytes"]


def validate_plateau(records, raw):
    assert len(records) == 100
    assert [row["cycle"] for row in records] == list(range(100))
    assert all(row["collection_count"] > 0 for row in records)
    assert all(b["collection_count"] > a["collection_count"]
               for a, b in zip(records, records[1:]))
    for row in records:
        assert row["collection_count_before"] >= 0
        assert row["collection_count_after"] == row["collection_count"]
        assert row["collection_count_after"] > row["collection_count_before"]
        assert row["collection_count_delta"] == (row["collection_count_after"] -
                                                  row["collection_count_before"])
        assert row["collection_count_unit"] == "collections"
        assert row["collection_probe"] == "sum of GarbageCollectorMXBean.getCollectionCount"
        assert row["collection_count_status"] == "observed"
        assert (0 < row["cycle_disposed_ns"] <= row["collection_before_sample_ns"] <=
                row["gc_requested_ns"] <= row["collection_after_sample_ns"] <=
                row["heap_sample_begin_ns"] <= row["heap_sample_end_ns"] <=
                row["rss_sample_begin_ns"] <= row["rss_sample_end_ns"] <= row["clock_ns"])
    assert all(a["collection_after_sample_ns"] < b["cycle_disposed_ns"]
               for a, b in zip(records, records[1:]))
    assert all(row["native_workload_bytes"] is None and
               row["attributed_workload_bytes"] is None and
               row["qualification"] == "unpassed" for row in records)
    with raw.open(newline="") as stream:
        legacy = list(csv.DictReader(stream))
    assert len(legacy) == 100
    for record, row in zip(records, legacy):
        assert record["cycle"] == int(row["cycle"])
        assert record["heap_after_collection_bytes"] == int(row["heap_after_collection_bytes"])
        assert record["collection_count"] == int(row["collection_count"])
        assert int(row["native_bytes"]) == -1


def validate_warmup_clock(clock, stderr, origin):
    with clock.open(newline="") as stream:
        stamps = list(csv.DictReader(stream))
    with stderr.open() as stream:
        lines = stream.read().splitlines()
    warmup = [line for line in lines if line.startswith("0,")]
    assert len(stamps) == 1 and len(warmup) == 1
    stamp = stamps[0]
    assert int(stamp["warmup_step"]) == 0
    assert int(stamp["begin_ns"]) >= json.loads(origin.read_text())["runtime_ns"]
    assert int(stamp["end_ns"]) > int(stamp["begin_ns"])
    assert int(stamp["end_ns"]) - int(stamp["begin_ns"]) == int(warmup[0].split(",")[1])


class SustainedJvmMemoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert JDK.is_dir() and BASELINE.is_file()
        RAW.mkdir(parents=True, exist_ok=True)
        classes = RAW / "classes"
        classes.mkdir(exist_ok=True)
        subprocess.run([str(JDK / "bin/javac"), "--release", "21", "-cp", str(BASELINE),
                        "-d", str(classes), str(SOURCE / "SustainedSidecars.java"),
                        str(SOURCE / "SustainedPilot.java"),
                        str(SOURCE / "SustainedAllocationProbeControl.java")], check=True)
        cls.harness = RAW / "sustained-harness.jar"
        subprocess.run([str(JDK / "bin/jar"), "--create", "--file", str(cls.harness),
                        "-C", str(classes), "."], check=True)

    def execute(self, mode, extra_flags=(), label=None):
        folder = RAW / (label or mode)
        folder.mkdir(exist_ok=True)
        outputs = {name: folder / name for name in
                   ("provider.json", "clock-origin.json", "warmup-clock.csv", "memory-v2.jsonl",
                    "allocation-v2.jsonl", "plateau-v2.jsonl", "steps.csv", "stderr.raw",
                    "process-result.json")}
        env = {**os.environ,
               "JAVA_HOME": str(JDK),
               "TMPDIR": str(Path.home() / "dyn4k-performance-tmp"),
               "DYN4K_PROVIDER_JSON": str(outputs["provider.json"]),
               "DYN4K_CLOCK_ORIGIN_JSON": str(outputs["clock-origin.json"]),
               "DYN4K_WARMUP_CLOCK_CSV": str(outputs["warmup-clock.csv"]),
               "DYN4K_CLOCK_NONCE": "short-control-nonce",
               "DYN4K_MEMORY_V2_JSONL": str(outputs["memory-v2.jsonl"]),
               "DYN4K_ALLOCATION_V2_JSONL": str(outputs["allocation-v2.jsonl"]),
               "DYN4K_PLATEAU_V2_JSONL": str(outputs["plateau-v2.jsonl"]),
               "DYN4K_SOURCE_COMMIT": subprocess.check_output(
                   ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "DYN4K_ARTIFACT_HASHES_JSON": json.dumps({"core": "b" * 64, "kotlin": "c" * 64}),
               "DYN4K_BASELINE_SHA256": hashlib.sha256(BASELINE.read_bytes()).hexdigest(),
               "JAVA_TOOL_OPTIONS": f"-Djava.io.tmpdir={Path.home() / 'dyn4k-performance-tmp'}"}
        Path(env["TMPDIR"]).mkdir(exist_ok=True)
        command = [str(JDK / "bin/java"), *extra_flags, "-cp",
                   os.pathsep.join((str(self.harness), str(BASELINE))),
                   "SustainedPilot", "separated", "default", "small", "30", "1",
                   mode if mode != "unsupported" else "plateau", "1", "baseline"]
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=90)
        outputs["steps.csv"].write_text(result.stdout)
        outputs["stderr.raw"].write_text(result.stderr)
        outputs["process-result.json"].write_text(json.dumps(
            {"command": command, "exit_code": result.returncode,
             "source_commit": env["DYN4K_SOURCE_COMMIT"],
             "nonce": env["DYN4K_CLOCK_NONCE"]}, indent=2) + "\n")
        return result, outputs

    def test_real_memory_and_allocation_controls(self):
        result, files = self.execute("memory")
        self.assertEqual(result.returncode, 0, result.stderr)
        allocation = rows(files["allocation-v2.jsonl"])
        memory = rows(files["memory-v2.jsonl"])
        validate_binding(allocation, files["provider.json"], "short-control-nonce", "memory")
        validate_binding(memory, files["provider.json"], "short-control-nonce", "memory")
        validate_allocation(allocation, files["steps.csv"])
        self.assertEqual(["empty", "construction", "warmup", "retained", "measure"],
                         [row["phase"] for row in memory])
        self.assertTrue(memory[3]["managed_post_collection"])
        self.assertGreater(memory[3]["collection_count_delta"], 0)
        validate_warmup_clock(files["warmup-clock.csv"], files["stderr.raw"],
                              files["clock-origin.json"])
        self.assertTrue(all(row["native_workload_bytes"] is None and
                            row["attributed_workload_bytes"] is None and
                            row["native_attribution"] == "unsupported" and
                            row["qualification"] == "unpassed" for row in memory))
        with self.assertRaises(AssertionError):
            validate_allocation(allocation[:-1], files["steps.csv"])
        fabricated = copy.deepcopy(allocation)
        fabricated[-1]["allocation_bytes"] += 1
        with self.assertRaises(AssertionError):
            validate_allocation(fabricated, files["steps.csv"])
        wrong_provider = copy.deepcopy(memory)
        wrong_provider[0]["provider_sha256"] = "0" * 64
        with self.assertRaises(AssertionError):
            validate_binding(wrong_provider, files["provider.json"], "short-control-nonce", "memory")

    def test_real_plateau_and_adverse_sequence(self):
        result, files = self.execute("plateau")
        self.assertEqual(result.returncode, 0, result.stderr)
        plateau = rows(files["plateau-v2.jsonl"])
        cycle_allocation = rows(files["allocation-v2.jsonl"])
        validate_binding(plateau, files["provider.json"], "short-control-nonce", "plateau")
        validate_binding(cycle_allocation, files["provider.json"], "short-control-nonce", "plateau")
        self.assertEqual([("plateau", cycle) for cycle in range(100)],
                         [(row["phase"], row["step"]) for row in cycle_allocation])
        self.assertTrue(all(row["allocation_bytes"] ==
                            row["counter_after_bytes"] - row["counter_before_bytes"]
                            for row in cycle_allocation))
        validate_plateau(plateau, files["steps.csv"])
        validate_warmup_clock(files["warmup-clock.csv"], files["stderr.raw"],
                              files["clock-origin.json"])
        with self.assertRaises(AssertionError):
            validate_plateau(plateau[:-1], files["steps.csv"])
        implausible = copy.deepcopy(plateau)
        implausible[75]["cycle"] = 20
        with self.assertRaises(AssertionError):
            validate_plateau(implausible, files["steps.csv"])
        no_new_collection = copy.deepcopy(plateau)
        no_new_collection[75]["collection_count_before"] = no_new_collection[75]["collection_count_after"]
        no_new_collection[75]["collection_count_delta"] = 0
        self.assertGreater(no_new_collection[76]["collection_count"],
                           no_new_collection[75]["collection_count"])
        with self.assertRaises(AssertionError):
            validate_plateau(no_new_collection, files["steps.csv"])
        unknown_collection = copy.deepcopy(plateau)
        unknown_collection[75]["collection_count_before"] = -1
        with self.assertRaises(AssertionError):
            validate_plateau(unknown_collection, files["steps.csv"])
        wrong_order = copy.deepcopy(plateau)
        wrong_order[75]["collection_before_sample_ns"] = wrong_order[75]["cycle_disposed_ns"] - 1
        with self.assertRaises(AssertionError):
            validate_plateau(wrong_order, files["steps.csv"])
        premature_heap = copy.deepcopy(plateau)
        premature_heap[75]["heap_sample_begin_ns"] = premature_heap[75]["collection_after_sample_ns"] - 1
        with self.assertRaises(AssertionError):
            validate_plateau(premature_heap, files["steps.csv"])
        premature_rss = copy.deepcopy(plateau)
        premature_rss[75]["rss_sample_begin_ns"] = premature_rss[75]["heap_sample_end_ns"] - 1
        with self.assertRaises(AssertionError):
            validate_plateau(premature_rss, files["steps.csv"])

    def test_disabled_collection_probe_fails_closed(self):
        result, files = self.execute("unsupported", ("-XX:+DisableExplicitGC",))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("post-collection plateau probe unsupported", result.stderr)
        self.assertEqual([], rows(files["plateau-v2.jsonl"]))

    def test_disabled_memory_collection_fails_closed(self):
        result, files = self.execute("memory", ("-XX:+DisableExplicitGC",),
                                     "memory-disabled-gc-java")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("#retained_collection_count_delta=0", result.stderr)
        self.assertIn("retained post-collection probe unsupported", result.stderr)
        self.assertEqual(["empty", "construction", "warmup"],
                         [row["phase"] for row in rows(files["memory-v2.jsonl"])])

    def test_unsupported_and_negative_allocation_probe_fail_closed(self):
        for kind in ("unsupported", "negative"):
            with self.subTest(kind=kind):
                result = subprocess.run([str(JDK / "bin/java"), "-cp", str(self.harness),
                                         "performance.SustainedAllocationProbeControl", kind],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("allocation", result.stdout)


if __name__ == "__main__":
    unittest.main()
