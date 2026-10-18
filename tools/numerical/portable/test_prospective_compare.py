import json
import tempfile
import unittest
from pathlib import Path

from prospective_compare import (compare_case, verify_baseline_manifest,
                                 verify_reference_case)
from receipt import digest


class ProspectiveComparisonTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.reference = self.root / "reference.jsonl"
        self.candidate = self.root / "candidate.jsonl"
        self.case = {"id": "one", "steps": 1}
        self.rows = [
            {"kind": "inputs", "id": "one", "input": {"signedZero": -0.0}},
            {"kind": "event", "id": "one", "step": 1, "order": 0,
             "name": "step.begin", "payload": 1.0},
            {"kind": "event", "id": "one", "step": 1, "order": 1,
             "name": "step.end", "payload": 1.0},
            {"kind": "state", "id": "one", "step": 1, "order": 2,
             "state": {"bodies": [{"id": "b0", "position": [1.0, 0.0]}]}},
            {"kind": "case-end", "id": "one", "steps": 1, "events": 2},
        ]

    def compare(self, candidate=None, reference=None):
        self.reference.write_text("".join(json.dumps(row) + "\n"
                                              for row in (self.rows if reference is None else reference)))
        self.candidate.write_text("".join(json.dumps(row) + "\n"
                                              for row in (self.rows if candidate is None else candidate)))
        return compare_case(self.reference, self.candidate, self.case)

    def test_exact_diagnostic_and_numeric_difference_stays_unpassed(self):
        exact = self.compare()
        self.assertEqual(exact["status"], "EXACT_DIAGNOSTIC")
        self.assertEqual(exact["records"], 5)
        changed = json.loads(json.dumps(self.rows))
        changed[3]["state"]["bodies"][0]["position"][0] = 1.0001
        result = self.compare(changed)
        self.assertEqual(result["status"], "UNPASSED_NUMERICAL_POLICY")
        self.assertEqual(result["different_numeric_values"], 1)

    def test_input_signed_zero_event_order_and_missing_records_fail(self):
        changed = json.loads(json.dumps(self.rows))
        changed[0]["input"]["signedZero"] = 0.0
        input_result = self.compare(changed)
        self.assertEqual(input_result["status"], "FAILED_INPUT")
        self.assertEqual(input_result["input_differences"][0]["path"],
                         "inputs.input.signedZero")
        changed = json.loads(json.dumps(self.rows))
        changed[3]["state"]["bodies"][0]["position"][1] = -0.0
        self.assertEqual(self.compare(changed)["status"], "FAILED_SIGNED_ZERO")
        changed = json.loads(json.dumps(self.rows))
        changed[1], changed[2] = changed[2], changed[1]
        self.assertEqual(self.compare(changed)["status"], "FAILED_STRUCTURE")
        self.assertEqual(self.compare(self.rows[:-1])["status"], "FAILED_COVERAGE")

    def test_nonfinite_and_empty_case_cannot_pass(self):
        changed = json.loads(json.dumps(self.rows))
        changed[3]["state"]["bodies"][0]["position"][0] = {"nonfinite": "Infinity"}
        self.assertEqual(self.compare(changed)["status"], "FAILED_NONFINITE")
        self.assertEqual(self.compare([], [])["status"], "FAILED_COVERAGE")

    def test_manifest_rejects_stale_reference_bytes_and_missing_case(self):
        case = self.root / "one.jsonl"
        case.write_text("reference\n")
        manifest = {"status": "CAPTURED_WITH_FAILED_ANGLE_PHYSICAL",
                    "baseline_jar_sha256": "fixed", "fixture_source_sha256": "fixture",
                    "case_sha256": {"one": digest(case)},
                    "inventory": {"cases": 1, "states": 1}}
        verify_baseline_manifest(manifest, {"one"}, "fixed", "fixture")
        case.write_text("stale\n")
        with self.assertRaisesRegex(Exception, "hash differs"):
            verify_reference_case(case, manifest["case_sha256"]["one"])
        with self.assertRaisesRegex(Exception, "case identity"):
            verify_baseline_manifest(manifest, {"one", "two"}, "fixed", "fixture")
        with self.assertRaisesRegex(Exception, "JAR"):
            verify_baseline_manifest(manifest, {"one"}, "changed", "fixture")


if __name__ == "__main__":
    unittest.main()
