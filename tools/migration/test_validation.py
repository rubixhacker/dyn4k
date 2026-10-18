import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


VALIDATOR = Path(__file__).with_name("validate_scene.py")


class SceneEvidenceTest(unittest.TestCase):
    def validate(self, scene, log, inputs):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "observer.log").write_text(log)
            (folder / "inputs.log").write_text(inputs)
            result = subprocess.run(
                [sys.executable, str(VALIDATOR), scene, str(folder / "observer.log"),
                 str(folder / "inputs.log"), str(folder / "result.json")],
                capture_output=True, text=True, check=False,
            )
            return result, json.loads((folder / "result.json").read_text())

    def test_headless_exception_cannot_pass_tracking(self):
        result, report = self.validate("Tracking", "java.awt.HeadlessException\n", "scene=Tracking\nkey c\n")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(0, report["samples"])
        self.assertGreater(report["failed_checks"] + report["unexecuted_checks"], 0)

    def test_billiards_requires_observed_ccd_hit(self):
        bodies = [{"i": i, "x": float(i), "y": 0.0, "vx": 0.0, "vy": 0.0, "rest": True}
                  for i in range(21)]
        records = []
        for index in range(2):
            records.append({"scene": "Billiards", "threadId": 2, "nanos": index + 1,
                            "bodyCount": 21, "jointCount": 0, "resets": 0, "ccdMode": "ALL",
                            "begin": 1, "persist": 1, "end": 1, "toiCalls": 5,
                            "toiHits": 0, "toiListenerHits": 0, "bodies": bodies, "joints": []})
        log = "\n".join("OBS_JSON " + json.dumps(record) for record in records)
        result, report = self.validate("Billiards", log, "scene=Billiards\nkeydown plus\nkeydown s\nkeyup s\n")
        self.assertNotEqual(0, result.returncode)
        failed = {check["id"] for check in report["checks"] if check["status"] == "failed"}
        self.assertIn("ccd_detector_hits", failed)
        self.assertIn("ccd_listener_hits", failed)

    def test_capture_time_without_engine_steps_is_rejected(self):
        bodies = [{"i": i, "x": float(i), "y": 0.0, "vx": 0.0, "vy": 0.0, "rest": False}
                  for i in range(9)]
        records = [{"scene": "Tracking", "threadId": 2, "nanos": index + 1,
                    "bodyCount": 9, "jointCount": 0, "resets": 0, "ccdMode": "ALL",
                    "begin": 1, "persist": 1, "end": 1, "toiCalls": 0,
                    "toiHits": 0, "toiListenerHits": 0, "steps": 0,
                    "stepDt": 0.0, "bodies": bodies, "joints": []}
                   for index in range(2)]
        log = "BEGIN: 1\nEND: 1\nOBSERVER_SHUTDOWN joined=true disposed=true\n" + "\n".join(
            "OBS_JSON " + json.dumps(record) for record in records)
        result, report = self.validate("Tracking", log, "scene=Tracking\nkey c\n")
        self.assertNotEqual(0, result.returncode)
        failed = {check["id"] for check in report["checks"] if check["status"] == "failed"}
        self.assertIn("steps_progressed", failed)


if __name__ == "__main__":
    unittest.main()
