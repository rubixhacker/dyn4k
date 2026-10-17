import csv
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from candidate_pilot import STATE_FIELDS
from candidate_runner import ROOT
from measure import compile_harness, jar_path


class StagedCcdFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.java = os.environ.get("PERFORMANCE_STAGED_JAVA")
        cls.javac = os.environ.get("PERFORMANCE_STAGED_JAVAC")
        baseline = os.environ.get("PERFORMANCE_BASELINE_JAR")
        if not all((cls.java, cls.javac, baseline)):
            raise unittest.SkipTest("staged Java and pinned baseline JAR are required")
        cls.folder = tempfile.TemporaryDirectory(prefix="dyn4k-ccd-fixture-test-")
        cls.jar = jar_path(Path(cls.folder.name), baseline)
        cls.classes = compile_harness(cls.javac, cls.jar, Path(cls.folder.name))
        subprocess.run(
            [sys.executable, str(ROOT / "tools/performance/candidate_runner.py"),
             "prepare", cls.java, "HEAD"], check=True, capture_output=True, text=True,
        )

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "folder"):
            cls.folder.cleanup()

    def rows(self, route, mode, steps, warmup):
        args = ["ccd", "default", "small", "60", str(steps), mode, str(warmup)]
        if route == "baseline":
            command = [self.java, "-cp", f"{self.classes}:{self.jar}", "BaselinePilot", *args]
        else:
            command = [sys.executable, str(ROOT / "tools/performance/candidate_runner.py"),
                       *args, route]
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        return list(csv.DictReader(io.StringIO(completed.stdout)))

    def test_ccd_creation_identity_and_physical_inputs_agree(self):
        identities = {route: self.rows(route, "fixture_identity", 1, 0)
                      for route in ("baseline", "direct_kotlin", "compatibility")}
        expected_hashes = list(range(27))
        for route, rows in identities.items():
            self.assertEqual(len(rows), 27, route)
            self.assertEqual([int(row["creation_index"]) for row in rows], expected_hashes, route)
            self.assertEqual([int(row["hash_code"]) for row in rows], expected_hashes, route)
            self.assertEqual(rows[0]["world_center_x"], "-10.0")
            self.assertEqual(rows[1]["world_center_x"], "10.0")
            self.assertEqual(rows[2]["world_center_x"], "-8.0")
            self.assertEqual(rows[3]["world_center_x"], "8.0")
            self.assertEqual([row["bullet"] for row in rows], ["false", "false"] + ["true"] * 25)
        self.assertEqual(identities["baseline"], identities["direct_kotlin"])
        self.assertEqual(identities["baseline"], identities["compatibility"])

    def test_staged_ccd_routes_have_same_120_step_state_and_events(self):
        direct = self.rows("direct_kotlin", "timing", 120, 60)
        compatibility = self.rows("compatibility", "timing", 120, 60)
        self.assertEqual(len(direct), 120)
        self.assertEqual(len(compatibility), 120)
        for step, (left, right) in enumerate(zip(direct, compatibility)):
            self.assertEqual(tuple(left[field] for field in STATE_FIELDS),
                             tuple(right[field] for field in STATE_FIELDS), f"step {step}")


if __name__ == "__main__":
    unittest.main()
