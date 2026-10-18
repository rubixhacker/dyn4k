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
        self.assertEqual(selected["exact_numeric"][:1], fixture["exact_numeric"])
        self.assertEqual(selected["exact_numeric"][1:], [
            "event.payload[].getDeltaTime", "event.payload[].getPrevousDeltaTime",
            "event.payload[].getInverseDeltaTime",
            "event.payload[].getPreviousInverseDeltaTime",
            "event.payload[].getDeltaTimeRatio"])
        self.assertNotIn("zero_numeric", fixture)
        self.assertEqual(nominal_zero.with_rules(selected), selected)
        with self.assertRaisesRegex(compare.Rejected, "scope"):
            nominal_zero.with_rules({**fixture, "zero_numeric": ["unapproved.path"]})

    def test_candidate_comparison_rejects_negative_zero_before_numeric_comparator(self):
        fixture = {"key": "nominal-free-motion", "counts": {"state": 1, "event": 0}}
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

    def test_every_nominal_callback_getter_has_approved_exact_binary64_value(self):
        values = {
            "getDeltaTime": float.fromhex("0x1.1111111111111p-6"),
            "getPrevousDeltaTime": float.fromhex("0x1.1111111111111p-6"),
            "getInverseDeltaTime": float.fromhex("0x1.e000000000000p+5"),
            "getPreviousInverseDeltaTime": float.fromhex("0x1.e000000000000p+5"),
            "getDeltaTimeRatio": float.fromhex("0x1.0000000000000p+0"),
        }
        with tempfile.TemporaryDirectory() as root:
            trace = Path(root) / "nominal.jsonl"
            for method in ("begin", "updatePerformed", "postSolve", "end"):
                row = {"kind": "event", "step": 1, "order": 0,
                       "listener": "StepListener",
                       "method": "public abstract void org.dyn4j.world.listener.StepListener."
                                 + method + "(org.dyn4j.dynamics.TimeStep,org.dyn4j.world.PhysicsWorld<T, ?>)",
                       "payload": [{**values, "type": "org.dyn4j.dynamics.TimeStep"},
                                   {"world": "L-free-s1.0-o0.0,0.0-hz60"}]}
                trace.write_text(json.dumps(row) + "\n")
                self.assertEqual(nominal_zero.audit_trace(trace, 0, 1)["exact_timestep_checks"], 5)
                integer_token = copy.deepcopy(row)
                integer_token["payload"][0]["getInverseDeltaTime"] = 60
                integer_token["payload"][0]["getPreviousInverseDeltaTime"] = 60
                integer_token["payload"][0]["getDeltaTimeRatio"] = 1
                trace.write_text(json.dumps(integer_token) + "\n")
                self.assertEqual(nominal_zero.audit_trace(trace, 0, 1)["exact_timestep_checks"], 5)
                for field, value in values.items():
                    changed = copy.deepcopy(row)
                    changed["payload"][0][field] = math.nextafter(value, math.inf)
                    trace.write_text(json.dumps(changed) + "\n")
                    with self.subTest(method=method, field=field), self.assertRaisesRegex(
                            compare.Rejected, "nominal timestep " + field):
                        nominal_zero.audit_trace(trace, 0, 1)
                for nonfinite in (math.nan, math.inf, -math.inf):
                    changed = copy.deepcopy(row)
                    changed["payload"][0]["getDeltaTime"] = nonfinite
                    trace.write_text(json.dumps(changed) + "\n")
                    with self.subTest(method=method, nonfinite=nonfinite), self.assertRaises(
                            compare.Rejected):
                        nominal_zero.audit_trace(trace, 0, 1)
                for wrong_type in (True, "0.016666666666666666"):
                    changed = copy.deepcopy(row)
                    changed["payload"][0]["getDeltaTime"] = wrong_type
                    trace.write_text(json.dumps(changed) + "\n")
                    with self.subTest(method=method, wrong_type=wrong_type), self.assertRaises(
                            compare.Rejected):
                        nominal_zero.audit_trace(trace, 0, 1)


if __name__ == "__main__":
    unittest.main()
