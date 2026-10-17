import gzip
import json
import tempfile
import unittest
from pathlib import Path

from reference_diagnostic import strict_comparison, structural_differences, value_differences


class FrozenComparatorSeamTest(unittest.TestCase):
    def test_input_schema_gaps_are_reported_without_rewriting_values(self):
        differences = structural_differences(
            {"state": {"bodies": [{"id": "b0", "velocity": [0.0, 0.0]}]}},
            {"state": {"bodies": [{"id": "b0", "speed": 0.0}]}, "extra": True},
            "inputs")
        self.assertIn({"path": "inputs.state.bodies[0].velocity",
                       "difference": "missing_portable"}, differences)
        self.assertIn({"path": "inputs.state.bodies[0].speed",
                       "difference": "extra_portable"}, differences)
        self.assertIn({"path": "inputs.extra", "difference": "extra_portable"}, differences)
        self.assertEqual(value_differences({"x": [-0.0]}, {"x": [0.0]}, "inputs"),
                         [{"path": "inputs.x[0]", "reference": -0.0, "portable": 0.0}])

    def test_full_record_fields_signed_zero_and_order(self):
        fixture = {"exact_numeric": ["inputs.value"]}
        baseline = [{"kind": "inputs", "value": -0.0},
                    {"kind": "event", "name": "begin"},
                    {"kind": "event", "name": "end"}]
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "reference.jsonl.gz"
            candidate = Path(directory) / "candidate.jsonl"
            with gzip.open(reference, "wt") as output:
                for row in baseline:
                    output.write(json.dumps(row) + "\n")

            def check(rows):
                candidate.write_text("".join(json.dumps(row) + "\n" for row in rows))
                return strict_comparison(fixture, reference, candidate)

            self.assertEqual(check(baseline)["status"], "PASSED")
            self.assertEqual(check([{**baseline[0], "value": 0.0}, *baseline[1:]])["status"], "FAILED")
            self.assertEqual(check([{**baseline[0], "extra": 1}, *baseline[1:]])["status"], "FAILED")
            self.assertEqual(check([baseline[0], baseline[2], baseline[1]])["status"], "FAILED")
            self.assertEqual(check(baseline[:-1])["status"], "FAILED")
