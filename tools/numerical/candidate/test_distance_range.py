import gzip
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
CASE = "P-J-Distance-limits-enabled-range-v2"


class DistanceRangeCaptureTest(unittest.TestCase):
    def test_valid_enabled_range_constrains_executed_trajectory(self):
        jar = os.environ.get("NUMERICAL_PROVIDER_JAR")
        java = os.environ.get("NUMERICAL_JAVA21", "/tmp/dyn4k-tools/jdk21")
        if not jar:
            self.skipTest("set NUMERICAL_PROVIDER_JAR to run the public staged JVM capture")
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            classes = root / "classes"
            classes.mkdir()
            sources = sorted((HERE / "calibration").glob("*.java"))
            sources.append(HERE / "runtime" / "RuntimeStamp.java")
            subprocess.run([f"{java}/bin/javac", "--release", "21", "-cp", jar,
                            "-d", str(classes), *(str(path) for path in sources)], check=True)
            output = root / "capture"
            output.mkdir()
            stdlib = os.environ.get("NUMERICAL_KOTLIN_STDLIB", "")
            cp = os.pathsep.join(filter(None, (str(classes), jar, stdlib)))
            subprocess.run([f"{java}/bin/java", "-cp", cp, "CandidateCases",
                            str(output), "joints", CASE], check=True, capture_output=True)
            summaries = [json.loads(line) for line in (output / "summary.jsonl").read_text().splitlines()]
            self.assertEqual([row["id"] for row in summaries], [CASE])
            self.assertEqual(summaries[0]["steps"], 600)
            with gzip.open(output / summaries[0]["file"], "rt") as stream:
                rows = [json.loads(line) for line in stream]
            self.assertEqual(rows[0]["id"], CASE)
            joint = rows[0]["state"]["joints"][0]
            self.assertEqual((joint["getLowerLimit"], joint["getUpperLimit"]), (1.0, 3.0))
            self.assertEqual((joint["isLowerLimitEnabled"], joint["isUpperLimitEnabled"]),
                             (True, True))
            distances = [abs(row["state"]["bodies"][1]["worldCenter"][1] -
                             row["state"]["bodies"][0]["worldCenter"][1])
                         for row in rows if row["kind"] == "state"]
            self.assertGreater(max(distances), 2.9)
            self.assertLessEqual(max(distances), 3.01)


if __name__ == "__main__":
    unittest.main()
