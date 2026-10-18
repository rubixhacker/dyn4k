import copy
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare
import nominal_zero


class NominalPositiveZeroTest(unittest.TestCase):
    def setUp(self):
        self.body = {"force": [0.0, 0.0], "torque": 0.0,
                     "accumulatedForce": [0.0, 0.0], "accumulatedTorque": 0.0}

    def test_four_paths_reject_negative_zero_and_nonzero(self):
        self.assertEqual(nominal_zero.check_body(self.body), 6)
        for field, index in (("force", 0), ("torque", None),
                             ("accumulatedForce", 1), ("accumulatedTorque", None)):
            for bad in (-0.0, math.nan, math.inf, -math.inf, 1.0, 5e-324, 0):
                body = copy.deepcopy(self.body)
                if index is None: body[field] = bad
                else: body[field][index] = bad
                with self.subTest(field=field, bad=bad), self.assertRaises(compare.Rejected):
                    nominal_zero.check_body(body)
            body = copy.deepcopy(self.body)
            del body[field]
            with self.subTest(field=field, bad="missing"), self.assertRaises(compare.Rejected):
                nominal_zero.check_body(body)

    def test_nominal_rule_overlay_only_selects_four_frozen_paths(self):
        fixture = {"key": "nominal-free-motion", "rules": [{"path": "position", "absolute": 1e-10}],
                   "exact_numeric": ["inputs.*"]}
        selected = nominal_zero.with_rules(fixture)
        self.assertEqual(selected["zero_numeric"], [
            "state.state.bodies[].force[]", "state.state.bodies[].torque",
            "state.state.bodies[].accumulatedForce[]", "state.state.bodies[].accumulatedTorque"])
        self.assertEqual(selected["rules"], fixture["rules"])
        self.assertEqual(selected["exact_numeric"], fixture["exact_numeric"])
        self.assertNotIn("zero_numeric", fixture)
        self.assertEqual(nominal_zero.with_rules(selected), selected)
        with self.assertRaisesRegex(compare.Rejected, "scope"):
            nominal_zero.with_rules({**fixture, "zero_numeric": ["unapproved.path"]})

    def test_candidate_comparison_rejects_negative_zero_before_numeric_comparator(self):
        fixture = {"key": "nominal-free-motion", "counts": {"state": 1}}
        with tempfile.TemporaryDirectory() as root:
            reference = Path(root) / "reference.jsonl"
            candidate = Path(root) / "candidate.jsonl"
            row = {"kind": "state", "state": {"bodies": [self.body]}}
            reference.write_text(json.dumps(row) + "\n")
            row["state"]["bodies"][0]["force"][0] = -0.0
            candidate.write_text(json.dumps(row) + "\n")
            with patch.object(compare, "compare", return_value={"status": "PASSED"}) as numeric:
                with self.assertRaisesRegex(compare.Rejected, "positive binary64 zero"):
                    nominal_zero.compare_pair(fixture, reference, candidate, "receipt", "source",
                                              "artifact", "commit")
                numeric.assert_not_called()
                candidate.write_bytes(reference.read_bytes())
                result = nominal_zero.compare_pair(fixture, reference, candidate, "receipt",
                                                   "source", "artifact", "commit")
                self.assertEqual(result["nominal_positive_zero"]["candidate"]["positive_zero_checks"], 6)
                self.assertEqual(numeric.call_args.args[0]["zero_numeric"], nominal_zero.ZERO_PATHS)


if __name__ == "__main__":
    unittest.main()
