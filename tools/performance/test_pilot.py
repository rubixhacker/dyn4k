import csv
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).parent

from measure import jar_path


class BaselinePilotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.download = tempfile.TemporaryDirectory(prefix="dyn4k-performance-test-")
        supplied = os.environ.get("DYN4K_BASELINE_JAR")
        cls.jar = jar_path(Path(cls.download.name), supplied)

    @classmethod
    def tearDownClass(cls):
        cls.download.cleanup()

    def test_public_harness_emits_one_raw_row_per_step(self):
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run(
                ["javac", "-cp", str(self.jar), "-d", folder, str(HERE / "BaselinePilot.java")],
                check=True,
                capture_output=True,
                text=True,
            )
            result = subprocess.run(
                ["java", "-cp", f"{folder}:{self.jar}", "BaselinePilot", "separated", "default", "small", "60", "12", "timing"],
                check=True,
                capture_output=True,
                text=True,
            )
        rows = list(csv.DictReader(result.stdout.splitlines()))
        self.assertEqual(12, len(rows))
        self.assertEqual(list(range(12)), [int(row["step"]) for row in rows])
        self.assertTrue(all(int(row["body_count"]) == 100 for row in rows))
        self.assertTrue(all(int(row["elapsed_ns"]) > 0 for row in rows))

    def test_every_joint_mode_and_family_runs_on_pinned_baseline(self):
        manifest = json.loads(subprocess.check_output(["python3", str(HERE / "manifest.py"), "emit"]))
        variants = [("joint", f"{kind.lower()}_{mode}") for kind, modes in manifest["joint_modes"].items() for mode in modes]
        variants += [("lifecycle", mode) for mode in ("settle", "wake", "replace")]
        variants += [(family, "default") for family in ("pile", "ccd")]
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run(["javac", "-cp", str(self.jar), "-d", folder, str(HERE / "BaselinePilot.java")], check=True, capture_output=True)
            for family, variant in variants:
                with self.subTest(family=family, variant=variant):
                    result = subprocess.run(
                        ["java", "-cp", f"{folder}:{self.jar}", "BaselinePilot", family, variant, "small", "60", "2", "allocation"],
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    rows = list(csv.DictReader(result.stdout.splitlines()))
                    self.assertEqual(2, len(rows))

    def test_pile_reports_real_full_candidates_and_contacts(self):
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run(["javac", "-cp", str(self.jar), "-d", folder, str(HERE / "BaselinePilot.java")], check=True, capture_output=True)
            result = subprocess.run(
                ["java", "-cp", f"{folder}:{self.jar}", "BaselinePilot", "pile", "default", "small", "60", "2", "timing"],
                check=True, capture_output=True, text=True,
            )
        rows = list(csv.DictReader(result.stdout.splitlines()))
        self.assertGreater(int(rows[-1]["broadphase_candidates"]), 0)
        self.assertGreater(int(rows[-1]["active_contact_pairs"]), 0)
        self.assertGreater(int(rows[-1]["active_contact_points"]), 0)

    def test_memory_run_accounts_for_construction_and_live_world(self):
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run(["javac", "-cp", str(self.jar), "-d", folder, str(HERE / "BaselinePilot.java")], check=True, capture_output=True)
            result = subprocess.run(
                ["java", "-cp", f"{folder}:{self.jar}", "BaselinePilot", "separated", "default", "small", "60", "2", "memory", "2"],
                check=True, capture_output=True, text=True,
            )
        metadata = dict(line[1:].split("=", 1) for line in result.stderr.splitlines() if line.startswith("#"))
        self.assertGreater(int(metadata["construction_allocated_bytes"]), 0)
        self.assertGreater(int(metadata["retained_heap_world_alive_bytes"]), 0)
        self.assertGreater(int(metadata["retained_collection_count_delta"]), 0)
        self.assertGreaterEqual(int(metadata["rss_after_construction_bytes"]), int(metadata["rss_empty_harness_bytes"]))


if __name__ == "__main__":
    unittest.main()
