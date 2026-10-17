import json
import tempfile
import unittest
from pathlib import Path

import physical


class PhysicalDiagnosticTest(unittest.TestCase):
    def test_nominal_position_limit_is_checked_per_component(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "trace.jsonl"
            record = {"kind": "state", "id": "long-free-60", "step": 1,
                      "state": {"bodies": [{"worldCenter": [0.25 / 60, -0.125 / 60],
                                            "velocity": [0.25, -0.125],
                                            "angularVelocity": 0.5,
                                            "rotationIncrementSum": 0.5 / 60,
                                            "kineticEnergy": 1.0,
                                            "linearMomentum": [0.25, -0.125],
                                            "angularMomentumCenter": 0.5}]}}
            trace.write_text(json.dumps(record) + "\n")
            self.assertEqual(physical.nominal_free(trace)["status"], "PASSED")
            record["state"]["bodies"][0]["worldCenter"][1] += 2e-10
            trace.write_text(json.dumps(record) + "\n")
            self.assertEqual(physical.nominal_free(trace)["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
