import csv
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from candidate_runner import ROOT
from measure import sha256


JDK = Path("/tmp/dyn4k-tools/jdk21")
BASELINE = Path("/tmp/dyn4k-performance-dyn4j-6.0.0.jar")
SOURCE = ROOT / "tools/performance/sustained_jvm"


class SustainedJvmHarnessTest(unittest.TestCase):
    def test_versioned_baseline_harness_emits_loaded_and_raw_sidecars(self):
        if not JDK.is_dir() or not BASELINE.is_file():
            self.skipTest("pinned JVM inputs unavailable")
        with tempfile.TemporaryDirectory(dir=Path.home()) as folder:
            work = Path(folder)
            classes = work / "classes"
            classes.mkdir()
            subprocess.run([str(JDK / "bin/javac"), "--release", "21", "-cp",
                            str(BASELINE), "-d", str(classes),
                            str(SOURCE / "SustainedSidecars.java"),
                            str(SOURCE / "SustainedPilot.java")], check=True,
                           capture_output=True)
            harness = work / "sustained-harness.jar"
            subprocess.run([str(JDK / "bin/jar"), "--create", "--file", str(harness),
                            "-C", str(classes), "."], check=True, capture_output=True)
            output = {name: work / name for name in
                      ("clock.csv", "warmup-clock.csv", "resource.csv", "provider.json", "run.json")}
            env = {**os.environ,
                   "DYN4K_CLOCK_CSV": str(output["clock.csv"]),
                   "DYN4K_WARMUP_CLOCK_CSV": str(output["warmup-clock.csv"]),
                   "DYN4K_RESOURCE_CSV": str(output["resource.csv"]),
                   "DYN4K_PROVIDER_JSON": str(output["provider.json"]),
                   "DYN4K_RUN_JSON": str(output["run.json"]),
                   "DYN4K_SOURCE_COMMIT": "a" * 40,
                   "DYN4K_ARTIFACT_HASHES_JSON": json.dumps({"core": "b" * 64,
                                                               "kotlin": "c" * 64}),
                   "DYN4K_BASELINE_SHA256": sha256(BASELINE)}
            result = subprocess.run([str(JDK / "bin/java"), "-cp",
                                     os.pathsep.join((str(harness), str(BASELINE))),
                                     "SustainedPilot", "separated", "default", "small",
                                     "30", "30", "timing", "30", "baseline"],
                                    env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("#fixture_reset_after_warmup=1", result.stderr)
            for name, count in (("clock.csv", 30), ("warmup-clock.csv", 30)):
                with output[name].open(newline="") as stream:
                    rows = list(csv.DictReader(stream))
                self.assertEqual(count, len(rows))
                self.assertTrue(all(int(row["end_ns"]) > int(row["begin_ns"])
                                    for row in rows))
            provider = json.loads(output["provider.json"].read_text())
            self.assertEqual(sha256(BASELINE), provider["loaded_core_sha256"])
            self.assertEqual(sha256(harness), provider["loaded_harness_sha256"])
            self.assertEqual(sha256(harness), provider["loaded_adapter_sha256"])
            self.assertEqual("baseline", provider["api"])
            run = json.loads(output["run.json"].read_text())
            self.assertEqual(30, run["sample_count"])
            self.assertEqual(30, run["warmup_count"])
            self.assertGreater(run["measured_wall_ns"], 0)
            self.assertGreater(run["active_steps"], 0)
            with output["resource.csv"].open(newline="") as stream:
                resource = list(csv.DictReader(stream))
            self.assertIn("construction", {row["phase"] for row in resource})
            self.assertEqual(30, sum(row["phase"] == "measure" for row in resource))


if __name__ == "__main__":
    unittest.main()
