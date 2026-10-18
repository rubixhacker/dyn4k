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
import default_policy
import receipt


class DefaultPolicyTest(unittest.TestCase):
    def test_all_adopted_paths_have_exactly_one_rule(self):
        fixture = default_policy.with_rules(compare.load_fixture("default-sleep-30"))
        self.assertEqual(default_policy.coverage(fixture),
                         {"APPROVED_LIMIT": 61, "EXACT_IDENTITY": 50,
                          "EXACT_ZERO": 12, "DERIVED_FORMULA": 14})
        with patch.object(default_policy, "PATHS", {"changed.path": "EXACT_IDENTITY"}), \
                self.assertRaisesRegex(compare.Rejected, "policy source"):
            default_policy.with_rules(compare.load_fixture("default-sleep-30"))

    def test_all_default_callback_values_are_exact_at_each_frequency(self):
        for hz, delta, inverse, first_ratio in (
                (30, "0x1.1111111111111p-5", "0x1.e000000000000p+4", 2.0),
                (60, "0x1.1111111111111p-6", "0x1.e000000000000p+5", 1.0),
                (120, "0x1.1111111111111p-7", "0x1.e000000000000p+6", 0.5)):
            for step_number, method in ((1, "begin"), (1, "updatePerformed"),
                                        (2, "postSolve"), (hz * 300 + 1, "end")):
                initial = step_number == 1
                payload = {"type": "org.dyn4j.dynamics.TimeStep",
                           "getDeltaTime": float.fromhex(delta),
                           "getInverseDeltaTime": float.fromhex(inverse),
                           "getPrevousDeltaTime": float.fromhex(
                               "0x1.1111111111111p-6" if initial else delta),
                           "getPreviousInverseDeltaTime": float.fromhex(
                               "0x1.e000000000000p+5" if initial else inverse),
                           "getDeltaTimeRatio": first_ratio if initial else 1.0}
                row = {"kind": "event", "step": step_number, "listener": "StepListener",
                       "method": "org.dyn4j.world.listener.StepListener." + method + "(",
                       "payload": [payload, {"world": "frozen"}]}
                self.assertEqual(default_policy.check_timestep(row, hz), 5)
                integer_token = copy.deepcopy(row)
                integer_token["payload"][0]["getInverseDeltaTime"] = hz
                integer_token["payload"][0]["getPreviousInverseDeltaTime"] = 60 if initial else hz
                integer_token["payload"][0]["getDeltaTimeRatio"] = int(first_ratio) if initial else 1
                if not initial or first_ratio in (1.0, 2.0):
                    self.assertEqual(default_policy.check_timestep(integer_token, hz), 5)
                for field in default_policy.TIMESTEP_FIELDS:
                    changed = copy.deepcopy(row)
                    changed["payload"][0][field] = math.nextafter(payload[field], math.inf)
                    with self.subTest(hz=hz, step=step_number, field=field), \
                            self.assertRaises(compare.Rejected):
                        default_policy.check_timestep(changed, hz)
                for bad in (math.nan, math.inf, -math.inf, 0):
                    changed = copy.deepcopy(row)
                    changed["payload"][0]["getDeltaTime"] = bad
                    with self.subTest(hz=hz, step=step_number, bad=bad), \
                            self.assertRaises(compare.Rejected):
                        default_policy.check_timestep(changed, hz)
                for bad in (True, "0.03333333333333333"):
                    changed = copy.deepcopy(row)
                    changed["payload"][0]["getDeltaTime"] = bad
                    with self.subTest(hz=hz, step=step_number, bad=bad), \
                            self.assertRaises(compare.Rejected):
                        default_policy.check_timestep(changed, hz)
                changed = copy.deepcopy(row)
                del changed["payload"][0]["getDeltaTimeRatio"]
                with self.assertRaises(compare.Rejected):
                    default_policy.check_timestep(changed, hz)
                if method == "updatePerformed":
                    changed = copy.deepcopy(row)
                    changed["step"] = 2
                    with self.assertRaises(compare.Rejected):
                        default_policy.check_timestep(changed, hz)

    def test_selected_limits_reject_values_just_outside_each_scalar_and_angle_cap(self):
        fixture = default_policy.with_rules(compare.load_fixture("default-sleep-30"))
        examples = (
            ("state.state.bodies[].transform.getTranslationX", 1e-4),
            ("state.state.bodies[].velocity[]", 1e-3),
            ("state.state.bodies[].angularVelocity", 1e-3),
            ("state.state.bodies[].transform.getRotationAngle", 1e-4),
            ("event.payload[].getNormalImpulse", 1e-3),
            ("event.payload[].getTime", 1e-6),
        )
        for path, cap in examples:
            for value, expected in ((math.nextafter(cap, 0.0), "PASSED"),
                                    (math.nextafter(cap, math.inf), "FAILED")):
                result = {"numeric_checks": 0, "exact_numeric_checks": 0,
                          "derived_checks": 0, "unpassed_channels": set()}
                with self.subTest(path=path, value=value):
                    if expected == "FAILED":
                        with self.assertRaises(compare.Rejected):
                            compare.compare_value(fixture, 0.0, value, path, result)
                    else:
                        compare.compare_value(fixture, 0.0, value, path, result)
                        self.assertEqual(result["unpassed_channels"], set())

    def test_direction_angle_norm_and_zero_placeholder(self):
        fixture = default_policy.with_rules(compare.load_fixture("default-sleep-30"))
        path = "event.payload[].constraint.getNormal"
        for vector, rejected in (([math.sin(9e-5), math.cos(9e-5)], False),
                                 ([math.sin(1.1e-4), math.cos(1.1e-4)], True),
                                 ([0.0, 1.0 + 0.9e-6], False),
                                 ([0.0, 1.0000011], True), ([0.0, 0.0], True)):
            result = {"numeric_checks": 0, "unpassed_channels": set()}
            with self.subTest(vector=vector):
                if rejected:
                    with self.assertRaises(compare.Rejected):
                        compare.compare_value(fixture, [0.0, 1.0], vector, path, result)
                else:
                    compare.compare_value(fixture, [0.0, 1.0], vector, path, result)
                    self.assertEqual(result["unpassed_channels"], set())
        result = {"numeric_checks": 0, "unpassed_channels": set()}
        compare.compare_value(fixture, [0.0, 0.0], [0.0, 0.0], path, result)

    def test_immutable_feature_and_material_fields_have_no_allowance(self):
        fixture = default_policy.with_rules(compare.load_fixture("default-sleep-30"))
        paths = ("event.payload[].manifoldId.getReferenceEdgeIndex",
                 "event.payload[].constraint.getFriction",
                 "instrumented-callback.values[].bodies[].fixtures[].shape.getWidth")
        for path in paths:
            result = {"numeric_checks": 0, "exact_numeric_checks": 0,
                      "derived_checks": 0, "unpassed_channels": set()}
            with self.subTest(path=path), self.assertRaises(compare.Rejected):
                compare.compare_value(fixture, 1.0, math.nextafter(1.0, math.inf), path, result)

    def test_derived_subtraction_wrap_cosine_and_norm_reject_broken_values(self):
        fixture = default_policy.with_rules(compare.load_fixture("default-sleep-30"))
        transform = {"getCost": 1.0, "getSint": 0.0, "getRotationAngle": 0.0,
                     "getTranslation": [0.0, 0.0]}
        body = {"transform": transform, "previousTransform": copy.deepcopy(transform),
                "angularVelocity": 0.0,
                "properties": {"getChangeInPosition": [0.0, 0.0],
                               "getChangeInOrientation": 0.0}}
        broken = copy.deepcopy(body)
        broken["properties"]["getChangeInPosition"][0] = 0.01
        result = {"numeric_checks": 0, "exact_numeric_checks": 0,
                  "derived_checks": 0, "unpassed_channels": set()}
        with self.assertRaisesRegex(compare.Rejected, "change in position formula"):
            compare.check_body_getters(broken)
        broken = copy.deepcopy(body)
        broken["properties"]["getChangeInOrientation"] = 0.01
        with self.assertRaisesRegex(compare.Rejected, "change in orientation"):
            compare.check_derived_pair(fixture, body, broken,
                                       "instrumented-callback.values[].bodies[]", result)
        wrapped_left = copy.deepcopy(body)
        wrapped_left["previousTransform"]["getRotationAngle"] = 3.1
        wrapped_left["transform"]["getRotationAngle"] = -3.1
        wrapped_left["angularVelocity"] = 1.0
        wrapped_right = copy.deepcopy(wrapped_left)
        wrapped_right["angularVelocity"] = -1.0
        with self.assertRaisesRegex(compare.Rejected, "branch differs"):
            compare.check_derived_pair(fixture, wrapped_left, wrapped_right,
                                       "instrumented-callback.values[].bodies[]", result)
        broken_transform = copy.deepcopy(transform)
        broken_transform["getCost"] = 0.9
        with self.assertRaisesRegex(compare.Rejected, "cosine"):
            compare.check_cost_pair(fixture, transform, broken_transform,
                                    "state.state.bodies[].transform", result)
        broken_transform = copy.deepcopy(transform)
        broken_transform["getSint"] = 0.01
        with self.assertRaisesRegex(compare.Rejected, "norm"):
            compare.check_sine_pair(fixture, transform, broken_transform,
                                    "state.state.bodies[].transform", result)
        broken_fixture = copy.deepcopy(fixture)
        broken_fixture["derived_rules"]["stored_sine"]["max_rotations_per_step"] = 10**9
        with self.assertRaisesRegex(compare.Rejected, "operation enclosure"):
            compare.check_sine_pair(broken_fixture, transform, transform,
                                    "state.state.bodies[].transform", result)

    def test_process_receipt_rejects_changed_source_artifact_trace_and_runtime(self):
        fixture = compare.load_fixture("default-sleep-30")
        runtime = {key: "known" for key in receipt.RUNTIME_FIELDS}
        sealed = {key: "known" for key in receipt.RECEIPT_FIELDS}
        sealed.update(artifact_path="/tmp/candidate.jar", trace_sha256="trace",
                      build_config_sha256="build",
                      runtime={**runtime, "process_command_sha256": "process",
                               "runtime_stamp_sha256": "stamp"})
        observed = {"source_archive_sha256": "source", "artifact_sha256": "artifact",
                    "trace_sha256": "trace", "process_sha256": "process",
                    "runtime_stamp_sha256": "stamp", "runtime": runtime}
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "receipt.json"
            with patch.object(default_policy.exact_consistency, "identity",
                              return_value=observed), \
                 patch.object(default_policy.receipt_module, "build_config_hash",
                              return_value="build"):
                path.write_text(json.dumps(sealed))
                self.assertEqual(default_policy.bind_process(
                    fixture, "trace", path, "source", "artifact", "a" * 40), observed)
                for field, value in (("source", "different"), ("artifact", "different")):
                    args = {"source": "source", "artifact": "artifact"}
                    args[field] = value
                    with self.subTest(field=field), self.assertRaises(compare.Rejected):
                        default_policy.bind_process(fixture, "trace", path,
                                                    args["source"], args["artifact"], "a" * 40)
                for field, key in (("trace_sha256", "trace_sha256"),
                                   ("process_command_sha256", "runtime"),
                                   ("runtime_stamp_sha256", "runtime"),
                                   ("build_config_sha256", "build_config_sha256")):
                    changed = copy.deepcopy(sealed)
                    if key == "runtime":
                        changed[key][field] = "different"
                    else:
                        changed[key] = "different"
                    path.write_text(json.dumps(changed))
                    with self.subTest(field=field), self.assertRaises(compare.Rejected):
                        default_policy.bind_process(fixture, "trace", path,
                                                    "source", "artifact", "a" * 40)

    def test_unproved_rotation_scope_names_exact_unpassed_coefficient_paths(self):
        fixture = default_policy.with_rules(compare.load_fixture("default-sleep-30"))
        transform = {"getCost": 1.0, "getSint": 0.0, "getRotationAngle": 0.0}
        body = {"rotationStepBoundBelowPi": True,
                "rotationTrackingScope": "segment-only; unrecorded transform mutations invalidate",
                "transform": transform, "previousTransform": transform}

        def rows(bad_cosine=False):
            yield b"", {"kind": "inputs", "settings": {
                "getMaximumRotation": 1.5707963267948966,
                "getPositionConstraintSolverIterations": 2,
                "getVelocityConstraintSolverIterations": 6}}
            for step_number in range(1, 18001):
                timestep = {"type": "org.dyn4j.dynamics.TimeStep",
                            "getDeltaTime": default_policy.DELTAS[30],
                            "getInverseDeltaTime": default_policy.INVERSES[30],
                            "getPrevousDeltaTime": default_policy.DELTAS[60] if step_number == 1
                            else default_policy.DELTAS[30],
                            "getPreviousInverseDeltaTime": default_policy.INVERSES[60]
                            if step_number == 1 else default_policy.INVERSES[30],
                            "getDeltaTimeRatio": 2.0 if step_number == 1 else 1.0}
                methods = ("begin", "updatePerformed", "postSolve", "end") \
                          if step_number == 1 else ("begin", "postSolve", "end")
                for method in methods:
                    yield b"", {"kind": "event", "step": step_number,
                                "listener": "StepListener",
                                "method": "org.dyn4j.world.listener.StepListener." + method + "(",
                                "payload": [timestep, {"world": "frozen"}]}
                changed = ({**body, "transform": {"getCost": 0.9,
                                                    "getSint": math.sqrt(0.19),
                                                    "getRotationAngle": 0.0}}
                           if bad_cosine and step_number == 2 else
                           {**body, "rotationStepBoundBelowPi": False}
                           if step_number == 2 else body)
                yield b"", {"kind": "state", "state": {"bodies": [body, changed]}}

        with patch.object(compare, "records", side_effect=lambda _: rows()):
            audit = default_policy.audit_math_and_timestep("generated", fixture)
        self.assertEqual(audit["exact_timestep_checks"], 270005)
        self.assertEqual(audit["unpassed_premise_paths"], sorted({
            "state.state.bodies[].transform.getCost",
            "state.state.bodies[].transform.getSint",
            "state.state.bodies[].previousTransform.getCost",
            "state.state.bodies[].previousTransform.getSint"}))
        with patch.object(compare, "records", side_effect=lambda _: rows(bad_cosine=True)):
            cosine_audit = default_policy.audit_math_and_timestep("generated", fixture)
        self.assertIn("state.state.bodies[].transform.getCost",
                      cosine_audit["unpassed_premise_paths"])


if __name__ == "__main__":
    unittest.main()
