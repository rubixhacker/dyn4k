import gzip
import json
import math
import tempfile
import unittest
from pathlib import Path

from reference_diagnostic import (strict_comparison, structural_differences,
                                  value_differences, zero_sign_differences,
                                  step_event_diagnostic, frozen_event_diagnostic,
                                  projected_records, auxiliary_record_diagnostic)
from reference_diagnostic import nominal_zero_diagnostic
from reference_diagnostic import (fixture_with_nominal_timestep_rule,
                                  nominal_timestep_diagnostic)
from reference_diagnostic import (fixture_with_default_sleep_rules,
                                  default_timestep_diagnostic,
                                  default_rotation_premise_diagnostic)
from reference_diagnostic import projected_comparison
from reference_diagnostic import compare_stream
import compare as approved


class FrozenComparatorSeamTest(unittest.TestCase):
    def test_adopted_default_rules_keep_input_and_exact_fields_strict(self):
        frozen = approved.load_fixture("default-sleep-30")
        self.assertEqual(frozen["rules"], [])
        fixture = fixture_with_default_sleep_rules(frozen)
        configured = approved.load_fixture("configured-30-r1")
        self.assertEqual(fixture["rules"], configured["rules"])
        self.assertEqual(fixture["zero_numeric"], configured["zero_numeric"])
        self.assertEqual(fixture["derived_rules"], configured["derived_rules"])
        self.assertEqual(fixture["counts"], frozen["counts"])
        state = {"kind": "state", "step": 1, "state": {"bodies": [{"id": "b1",
            "force": [0.0, 0.0], "transform": {"getTranslation": [0.0, 0.0]}}]}}
        changed = json.loads(json.dumps(state))
        changed["state"]["bodies"][0]["force"][0] = -0.0
        changed["state"]["bodies"][0]["transform"]["getTranslation"][0] = 0.00009
        self.assertEqual(compare_stream(fixture, [state], [changed])["status"], "PASSED")
        changed["state"]["bodies"][0]["transform"]["getTranslation"][0] = 0.00011
        self.assertEqual(compare_stream(fixture, [state], [changed])["status"], "FAILED")
        changed["state"]["bodies"][0]["transform"]["getTranslation"][0] = 0.0
        changed["state"]["bodies"][0]["force"][0] = 0.001
        self.assertEqual(compare_stream(fixture, [state], [changed])["status"], "FAILED")
        snapshot = {"kind": "instrumented-callback", "values": [{"bodies": [{"id": "b1",
            "properties": {"getForce": [0.0, 0.0]}}]}]}
        changed_snapshot = json.loads(json.dumps(snapshot))
        changed_snapshot["values"][0]["bodies"][0]["properties"]["getForce"][0] = -0.0
        self.assertEqual(compare_stream(fixture, [snapshot], [changed_snapshot])["status"],
                         "PASSED")
        exact_event = {"kind": "event", "payload": [{"shape": {"getArea": 1.0}}]}
        altered_event = {"kind": "event", "payload": [{"shape": {"getArea": math.nextafter(1.0, 2.0)}}]}
        self.assertEqual(compare_stream(fixture, [exact_event], [altered_event])["status"], "FAILED")
        normal = {"kind": "event", "payload": [{"constraint": {"getNormal": [1.0, 0.0]}}]}
        tilted = {"kind": "event", "payload": [{"constraint": {"getNormal":
            [math.cos(0.0002), math.sin(0.0002)]}}]}
        self.assertEqual(compare_stream(fixture, [normal], [tilted])["status"], "FAILED")
        input_row = {"kind": "inputs", "id": "fixed", "value": -0.0}
        self.assertEqual(compare_stream(fixture, [input_row], [{**input_row, "value": 0.0}])["status"],
                         "FAILED")

    def test_default_timestep_checks_each_callback_and_initial_previous_step(self):
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "reference.jsonl.gz"
            candidate = Path(directory) / "candidate.jsonl"
            for hz in (30, 60, 120):
                rows = []
                for step in (1, 2):
                    dt = 1 / hz
                    values = {"getDeltaTime": dt, "getInverseDeltaTime": float(hz),
                              "getPrevousDeltaTime": 1 / 60 if step == 1 else dt,
                              "getPreviousInverseDeltaTime": 60.0 if step == 1 else float(hz),
                              "getDeltaTimeRatio": 60 / hz if step == 1 else 1.0}
                    for order, method in enumerate(("begin", "postSolve", "end")):
                        rows.append({"kind": "event", "listener": "StepListener", "step": step,
                                     "order": order, "method": method, "payload": [values]})
                rows.append({"kind": "event", "listener": "StepListener", "step": 2,
                             "order": 3, "method": "updatePerformed", "payload": [values]})
                with gzip.open(reference, "wt") as output:
                    for row in rows:
                        output.write(json.dumps(row) + "\n")

                def check(events):
                    candidate.write_text("".join(json.dumps({"kind": "event", "name": "step.callback",
                        "frozenEvent": row}) + "\n" for row in events))
                    return default_timestep_diagnostic(reference, candidate, hz,
                                                       expected_callbacks=7)

                self.assertEqual(check(rows)["status"], "PASSED")
                self.assertEqual(check(rows)["value_checks"], 35)
                for index, field in ((0, "getDeltaTime"), (4, "getDeltaTimeRatio"),
                                     (6, "getPreviousInverseDeltaTime")):
                    changed = json.loads(json.dumps(rows))
                    value = changed[index]["payload"][0][field]
                    changed[index]["payload"][0][field] = math.nextafter(value, math.inf)
                    self.assertEqual(check(changed)["status"], "FAILED")
                changed = json.loads(json.dumps(rows))
                changed[0]["payload"][0]["getInverseDeltaTime"] = {"nonfinite": "Infinity"}
                self.assertEqual(check(changed)["status"], "FAILED")
                changed[0]["payload"][0]["getInverseDeltaTime"] = True
                self.assertEqual(check(changed)["status"], "FAILED")
                self.assertEqual(check(rows[:-1])["status"], "FAILED")
                changed = json.loads(json.dumps(rows))
                changed[0]["payload"][0]["getInverseDeltaTime"] = hz
                self.assertEqual(check(changed)["status"], "PASSED")

    def test_default_bounds_and_direction_controls(self):
        fixture = fixture_with_default_sleep_rules(approved.load_fixture("default-sleep-30"))
        bounds = (
            ("state.state.bodies[].transform.getTranslation[]", 0.0, 0.00005, 0.00011),
            ("state.state.bodies[].velocity[]", 0.0, 0.0005, 0.0011),
            ("state.state.bodies[].angularVelocity", 0.0, 0.0005, 0.0011),
            ("state.state.bodies[].transform.getRotationAngle", 0.0, 0.00005, 0.00011),
            ("event.payload[].getDepth", 0.0, 0.00005, 0.00011),
            ("event.payload[].getNormalImpulse", 0.0, 0.0005, 0.0011),
            ("event.payload[].getTime", 0.5, 0.5000005, 0.5000011),
        )
        for path, baseline, inside, outside in bounds:
            with self.subTest(path=path):
                approved.compare_value(fixture, baseline, inside, path,
                                       {"unpassed_channels": set(), "numeric_checks": 0})
                with self.assertRaises(approved.Rejected):
                    approved.compare_value(fixture, baseline, outside, path,
                                           {"unpassed_channels": set(), "numeric_checks": 0})
        path = "event.payload[].constraint.getNormal"
        approved.compare_value(fixture, [1.0, 0.0],
                               [math.cos(0.00005), math.sin(0.00005)], path,
                               {"unpassed_channels": set(), "numeric_checks": 0})
        for changed in ([math.cos(0.0002), math.sin(0.0002)], [1.000002, 0.0], [0.0, 0.0]):
            with self.assertRaises(approved.Rejected):
                approved.compare_value(fixture, [1.0, 0.0], changed, path,
                                       {"unpassed_channels": set(), "numeric_checks": 0})

    def test_default_rotation_premise_checks_both_providers(self):
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "reference.jsonl.gz"
            candidate = Path(directory) / "candidate.jsonl"
            transform = {"getCost": 1.0, "getSint": 0.0, "getRotationAngle": 0.0}
            body = {"rotationStepBoundBelowPi": True,
                    "rotationTrackingScope": "segment-only; unrecorded transform mutations invalidate",
                    "transform": transform, "previousTransform": transform}
            state = {"kind": "state", "step": 1, "state": {"bodies": [body]}}

            def check(baseline, projected):
                with gzip.open(reference, "wt") as output:
                    output.write(json.dumps(baseline) + "\n")
                candidate.write_text(json.dumps({"kind": "state", "step": 1,
                    "frozenState": projected["state"]}) + "\n")
                return default_rotation_premise_diagnostic(reference, candidate, 30,
                                                           expected_states=1)

            self.assertEqual(check(state, state)["status"], "PASSED")
            changed = json.loads(json.dumps(state))
            changed["state"]["bodies"][0]["rotationStepBoundBelowPi"] = False
            self.assertEqual(check(state, changed)["status"], "FAILED")
            changed = json.loads(json.dumps(state))
            changed["state"]["bodies"][0]["rotationTrackingScope"] = "unknown"
            self.assertEqual(check(state, changed)["status"], "FAILED")
            changed = json.loads(json.dumps(state))
            changed["state"]["bodies"][0]["transform"]["getCost"] = 0.9
            self.assertEqual(check(state, changed)["status"], "FAILED")
            changed = json.loads(json.dumps(state))
            changed["state"]["bodies"][0]["transform"]["getSint"] = 0.1
            self.assertEqual(check(state, changed)["status"], "FAILED")
            changed = json.loads(json.dumps(state))
            changed["state"]["bodies"][0]["rotationStepBoundBelowPi"] = False
            self.assertEqual(check(changed, state)["status"], "FAILED")
            candidate.write_text("")
            self.assertEqual(default_rotation_premise_diagnostic(reference, candidate, 30,
                             expected_states=1)["status"], "FAILED")

    def test_default_derived_change_and_wrap_controls(self):
        transform = {"getTranslation": [0.0, 0.0], "getRotationAngle": 0.0,
                     "getCost": 1.0, "getSint": 0.0}
        body = {"rotationStepBoundBelowPi": True,
                "rotationTrackingScope": "segment-only; unrecorded transform mutations invalidate",
                "transform": transform, "previousTransform": transform,
                "angularVelocity": 0.0,
                "properties": {"getChangeInPosition": [0.0, 0.0],
                               "getChangeInOrientation": 0.0}}
        baseline = [{"kind": "state", "step": 1, "state": {"bodies": [body]}},
                    {"kind": "instrumented-callback", "values": [{"bodies": [body]}]}]
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "reference.jsonl.gz"
            candidate = Path(directory) / "candidate.jsonl"
            with gzip.open(reference, "wt") as output:
                for row in baseline:
                    output.write(json.dumps(row) + "\n")

            def check(projected_body):
                candidate.write_text("".join(json.dumps(row) + "\n" for row in [
                    {"kind": "state", "step": 1, "frozenState": {"bodies": [body]}},
                    {"kind": "instrumented-callback", "frozenRecord":
                        {"kind": "instrumented-callback", "values":
                            [{"bodies": [projected_body]}]}}]))
                return default_rotation_premise_diagnostic(reference, candidate, 30,
                                                           expected_states=1)

            self.assertEqual(check(body)["status"], "PASSED")
            changed = json.loads(json.dumps(body))
            changed["transform"]["getTranslation"][0] = 0.0001
            changed["properties"]["getChangeInPosition"][0] = 0.001
            self.assertIn("change in position", check(changed)["reason"])
            changed = json.loads(json.dumps(body))
            changed["properties"]["getChangeInOrientation"] = 0.0001
            self.assertIn("change in orientation", check(changed)["reason"])

    def test_adopted_nominal_timestep_rule_and_adverse_getters(self):
        fixture = fixture_with_nominal_timestep_rule(approved.load_fixture("nominal-free-motion"))
        zeros = {"force": [0.0, 0.0], "torque": 0.0,
                 "accumulatedForce": [0.0, 0.0], "accumulatedTorque": 0.0}
        state = {"kind": "state", "step": 1, "state": {"bodies": [zeros]}}
        self.assertEqual(compare_stream(fixture, [state], [state])["status"], "PASSED")
        changed_state = json.loads(json.dumps(state))
        changed_state["state"]["bodies"][0]["force"][0] = -0.0
        self.assertEqual(compare_stream(fixture, [state], [changed_state])["status"], "FAILED")
        values = {"getDeltaTime": 1 / 60, "getPrevousDeltaTime": 1 / 60,
                  "getInverseDeltaTime": 60.0, "getPreviousInverseDeltaTime": 60.0,
                  "getDeltaTimeRatio": 1.0}
        event = {"kind": "event", "listener": "StepListener", "step": 1, "order": 0,
                 "method": "StepListener.begin(TimeStep)", "payload": [values]}
        self.assertEqual(compare_stream(fixture, [event], [event])["status"], "PASSED")
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "reference.jsonl.gz"
            candidate = Path(directory) / "candidate.jsonl"
            rows = [event, {**event, "order": 1,
                            "method": "StepListener.updatePerformed(TimeStep)"}]
            with gzip.open(reference, "wt") as stream:
                for row in rows:
                    stream.write(json.dumps(row) + "\n")

            def check(events):
                candidate.write_text("".join(json.dumps({"kind": "event", "name": "step.callback",
                    "frozenEvent": row}) + "\n" for row in events))
                return nominal_timestep_diagnostic(reference, candidate, expected_callbacks=2)

            self.assertEqual(check(rows)["status"], "PASSED")
            self.assertEqual(check(rows)["value_checks"], 10)
            changed = json.loads(json.dumps(rows))
            changed[0]["payload"][0]["getInverseDeltaTime"] = 60
            self.assertEqual(check(changed)["status"], "PASSED")
            changed[0]["payload"][0]["getInverseDeltaTime"] = 59.0
            self.assertEqual(check(changed)["status"], "FAILED")
            changed[0]["payload"][0]["getInverseDeltaTime"] = {"nonfinite": "Infinity"}
            self.assertEqual(check(changed)["status"], "FAILED")
            self.assertEqual(check(rows[:1])["status"], "FAILED")

    def test_nominal_timestep_metadata_remains_unpassed_without_a_rule(self):
        fixture = approved.load_fixture("nominal-free-motion")
        values = {"getDeltaTime": 1 / 60, "getPrevousDeltaTime": 1 / 60,
                  "getInverseDeltaTime": 60.0,
                  "getPreviousInverseDeltaTime": 60.0,
                  "getDeltaTimeRatio": 1.0}
        reference = {"kind": "event", "payload": [values]}
        result = compare_stream(fixture, [reference], [reference])
        self.assertEqual(result["status"], "UNPASSED")
        self.assertEqual(result["unpassed_channels"],
                         sorted(f"event.payload[].{name}" for name in values))

    def test_projected_stream_requires_every_frozen_record(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate.jsonl"
            rows = [
                {"kind": "inputs", "frozenInput": {"kind": "inputs", "id": "fixed"}},
                {"kind": "event", "frozenEvent": {"kind": "event", "order": 0}},
                {"kind": "state", "step": 1, "frozenState": {"bodies": []}},
                {"kind": "case-end"},
            ]
            candidate.write_text("".join(json.dumps(row) + "\n" for row in rows))
            self.assertEqual(list(projected_records(candidate)), [
                {"kind": "inputs", "id": "fixed"}, {"kind": "event", "order": 0},
                {"kind": "state", "step": 1, "state": {"bodies": []}}])
            rows[1].pop("frozenEvent")
            candidate.write_text("".join(json.dumps(row) + "\n" for row in rows))
            with self.assertRaisesRegex(Exception, "event projection is absent"):
                list(projected_records(candidate))

    def test_complete_projected_stream_can_pass_approved_comparator(self):
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "reference.jsonl.gz"
            candidate = Path(directory) / "candidate.jsonl"
            baseline = [{"kind": "inputs", "value": 1.0},
                        {"kind": "event", "step": 1, "order": 0, "method": "begin"},
                        {"kind": "state", "step": 1, "state": {"value": -0.0}}]
            with gzip.open(reference, "wt") as output:
                for row in baseline:
                    output.write(json.dumps(row) + "\n")
            def check(rows):
                candidate.write_text("".join(json.dumps(row) + "\n" for row in rows))
                return projected_comparison({"exact_numeric": ["inputs.value",
                    "event.step", "event.order", "state.step", "state.state.value"]},
                    reference, candidate)
            rows = [{"kind": "inputs", "frozenInput": baseline[0]},
                    {"kind": "event", "frozenEvent": baseline[1]},
                    {"kind": "state", "step": 1, "frozenState": baseline[2]["state"]},
                    {"kind": "case-end"}]
            self.assertEqual(check(rows)["status"], "PASSED")
            rows[2] = {"kind": "state", "step": 1, "frozenState": {"value": 0.0}}
            self.assertEqual(check(rows)["status"], "FAILED")

    def test_auxiliary_projection_detects_missing_action(self):
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "reference.jsonl.gz"
            candidate = Path(directory) / "candidate.jsonl"
            baseline = {"kind": "action", "id": "fixed", "step": 3,
                        "order": 0, "description": "wake"}
            with gzip.open(reference, "wt") as output:
                output.write(json.dumps(baseline) + "\n")
            candidate.write_text(json.dumps({"kind": "action",
                "frozenRecords": [baseline]}) + "\n")
            self.assertEqual(auxiliary_record_diagnostic(reference, candidate)["status"], "PASSED")
            candidate.write_text(json.dumps({"kind": "action"}) + "\n")
            self.assertEqual(auxiliary_record_diagnostic(reference, candidate)["differing_records"], 1)

    def test_approved_nominal_zero_rejects_nonzero_and_negative_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "reference.jsonl.gz"
            candidate = Path(directory) / "candidate.jsonl"
            body = {"force": [0.0, 0.0], "torque": 0.0,
                    "accumulatedForce": [0.0, 0.0], "accumulatedTorque": 0.0}
            with gzip.open(reference, "wt") as output:
                output.write(json.dumps({"kind": "state", "step": 1,
                    "state": {"bodies": [body]}}) + "\n")
            def check(projected):
                candidate.write_text(json.dumps({"kind": "state", "step": 1,
                    "frozenState": {"bodies": [projected]}}) + "\n")
                return nominal_zero_diagnostic(reference, candidate)
            self.assertEqual(check(body)["status"], "PASSED")
            self.assertEqual(check({**body, "force": [-0.0, 0.0]})["status"], "FAILED")
            self.assertEqual(check({**body, "force": [-0.0, 0.0]})["failed_values"], 1)
            self.assertEqual(check({**body, "torque": 0.001})["status"], "FAILED")
            self.assertEqual(check({**body, "torque": 0.001})["failed_values"], 1)

    def test_step_event_projection_detects_order_and_omission(self):
        baseline = [
            {"kind": "event", "listener": "StepListener", "step": 1,
             "order": 0, "method": "begin", "payload": [-0.0]},
            {"kind": "event", "listener": "StepListener", "step": 1,
             "order": 1, "method": "end", "payload": [0.0]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "reference.jsonl.gz"
            candidate = Path(directory) / "candidate.jsonl"
            with gzip.open(reference, "wt") as output:
                for row in baseline:
                    output.write(json.dumps(row) + "\n")

            def check(rows):
                candidate.write_text("".join(json.dumps({"kind": "event",
                    "name": "step." + row["method"], "frozenEvent": row}) + "\n"
                    for row in rows))
                return step_event_diagnostic(reference, candidate)

            self.assertEqual(check(baseline)["status"], "PASSED")
            self.assertEqual(frozen_event_diagnostic(reference, candidate)["status"], "PASSED")
            self.assertEqual(check(baseline[::-1])["differing_events"], 2)
            self.assertEqual(frozen_event_diagnostic(reference, candidate)["differing_events"], 2)
            self.assertEqual(check(baseline[:1])["differing_events"], 1)
            self.assertEqual(frozen_event_diagnostic(reference, candidate)["differing_events"], 1)
            altered = [{**baseline[0], "payload": [0.0]}, baseline[1]]
            self.assertEqual(check(altered)["differing_events"], 1)

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
        self.assertEqual(zero_sign_differences({"x": [-0.0]}, {"x": [0.0]}, "state.state"),
                         ["state.state.x[0]"])

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
