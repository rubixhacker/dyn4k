import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import receipt


CASES = [{"id": "motion", "family": "free-motion", "profile": "default", "hz": 60, "steps": 2}]
HEADER = {"kind": "inputs", "id": "motion", "family": "free-motion", "profile": "default", "hz": 60, "steps": 2, "dt": 1 / 60, "input": {"velocity": [-0.0, 1.0]}}
STATE = {"kind": "state", "id": "motion", "step": 1, "order": 0, "state": {"x": -0.0}}


def sample():
    return [HEADER, STATE, {"kind": "event", "id": "motion", "step": 2, "order": 0, "name": "wake"},
            {"kind": "state", "id": "motion", "step": 2, "order": 1, "state": {"x": 1.0}},
            {"kind": "case-end", "id": "motion", "steps": 2, "events": 1}]


class ReceiptContractTest(unittest.TestCase):
    def write(self, folder, name, records):
        path = folder / name
        path.write_text("".join(json.dumps(row, allow_nan=False) + "\n" for row in records))
        return path

    def test_exact_case_and_step_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = self.write(folder, "trace.jsonl", sample())
            self.assertEqual(receipt.inspect(path, CASES)["executed_cases"], 1)
            for changed in (sample()[:-1], sample()[:2] + sample()[3:], sample()[1:]):
                with self.subTest(changed=changed):
                    self.assertRaises(receipt.Rejected, receipt.inspect, self.write(folder, "bad.jsonl", changed), CASES)
            self.assertRaises(receipt.Rejected, receipt.inspect, path, CASES + [{**CASES[0], "id": "omitted"}])
            self.assertRaises(receipt.Rejected, receipt.inspect, path, [])
            self.assertEqual(receipt.inspect(path, [{**CASES[0], "input": HEADER["input"]}])["executed_cases"], 1)
            self.assertRaises(receipt.Rejected, receipt.inspect, path,
                              [{**CASES[0], "input": {"velocity": [0.0, 1.0]}}])

    def test_continuation_case_preserves_absolute_step(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = copy.deepcopy(sample())
            rows[0]["startStep"] = 1
            rows[1]["step"] = 2
            rows[2]["step"] = 3
            rows[3]["step"] = 3
            path = self.write(Path(directory), "continuation.jsonl", rows)
            continuation = [{**CASES[0], "start_step": 1}]
            self.assertEqual(receipt.inspect(path, continuation)["states"], 2)
            self.assertRaises(receipt.Rejected, receipt.inspect, path, CASES)

    def test_frozen_projection_cannot_disappear_from_a_case(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            case = [{**CASES[0], "require_frozen_projection": True,
                     "frozen_id": "baseline", "frozen_origin": [0.0, 0.0],
                     "frozen_scale": 1.0}]
            rows = copy.deepcopy(sample())
            self.assertRaises(receipt.Rejected, receipt.inspect,
                              self.write(folder, "missing.jsonl", rows), case)
            rows[0]["frozenConfiguration"] = {key: {} for key in ("settings", "world", "state")}
            rows[0]["frozenInput"] = {"kind": "inputs", "dt": rows[0]["dt"],
                "steps": rows[0]["steps"], "id": "baseline", "origin": [0.0, 0.0],
                "scale": 1.0, "settings": {}, "world": {}, "state": {}}
            for row in rows:
                if row["kind"] == "state":
                    row["frozenState"] = {"bodies": [], "joints": []}
            complete = self.write(folder, "complete.jsonl", rows)
            self.assertEqual(receipt.inspect(complete, case)["executed_cases"], 1)
            rows[1].pop("frozenState")
            self.assertRaises(receipt.Rejected, receipt.inspect,
                              self.write(folder, "omitted-state.jsonl", rows), case)
            rows = copy.deepcopy(sample())
            rows[0]["frozenConfiguration"] = {key: {} for key in ("settings", "world", "state")}
            rows[0]["frozenInput"] = {"kind": "inputs", "dt": rows[0]["dt"],
                "steps": rows[0]["steps"], "id": "baseline", "origin": [0.0, 0.0],
                "scale": 1.0, "settings": {}, "world": {}, "state": {}}
            rows[0]["frozenInput"]["dt"] *= 2
            self.assertRaises(receipt.Rejected, receipt.inspect,
                              self.write(folder, "altered-envelope.jsonl", rows), case)
            rows[0]["frozenInput"]["dt"] = rows[0]["dt"]
            rows[0]["frozenInput"]["id"] = "other"
            self.assertRaises(receipt.Rejected, receipt.inspect,
                              self.write(folder, "altered-frozen-id.jsonl", rows), case)

    def test_required_instrumented_callback_cannot_be_omitted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), "missing-binding.jsonl", sample())
            cases = [{**CASES[0], "expected_instrumented_callbacks": [1]}]
            self.assertRaises(receipt.Rejected, receipt.inspect, path, cases)

    def test_required_input_setup_cannot_be_omitted_or_relabelled(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(Path(tmp), "trace.jsonl", sample())
            self.assertRaises(receipt.Rejected, receipt.inspect, path,
                              [{**CASES[0], "require_setup": True}])
        keys = ("gravity", "stepFrequency", "maximumTranslation", "maximumRotation",
                "atRestDetectionEnabled", "maximumAtRestLinearVelocity",
                "maximumAtRestAngularVelocity", "minimumAtRestTime", "velocityIterations",
                "positionIterations", "warmStartingEnabled", "maximumWarmStartDistance",
                "linearTolerance", "angularTolerance", "maximumLinearCorrection",
                "maximumAngularCorrection", "baumgarte", "continuousDetectionMode", "narrowphase")
        settings = {key: 0 for key in keys}
        settings["timeOfImpact"] = {"distanceEpsilon": 4.806217383937352e-6}
        def body(index, x, radius):
            return {"id": f"b{index}", "transform": {"getTranslation": [x, 0.0]},
                    "massType": "NORMAL", "mass": 1.0, "inertia": 1.0,
                    "massCenter": [0.0, 0.0], "linearDamping": 0.0,
                    "angularDamping": 0.0, "initialVelocity": [0.0, 0.0],
                    "initialAngularVelocity": 0.0, "atRestDetectionEnabled": True,
                    "bullet": False, "fixtures": [{"id": f"b{index}f0", "density": 1.0,
                    "friction": 0.2, "restitution": 0.0, "restitutionVelocity": 1.0,
                    "sensor": False, "filter": "DEFAULT_FILTER",
                    "shape": {"type": "Circle", "radius": radius}}]}
        header = {"settings": settings, "setup": {"bodies": [body(0, 0.0, 1.0),
                                                               body(1, 1.5, 0.5)], "joints": []}}
        case = {"family": "geometry-collision", "input": {"scale": 1.0,
                "origin": [0.0, 0.0], "delta": 0.0}}
        receipt.validate_setup(header, case)
        header["setup"]["bodies"][1]["fixtures"][0]["shape"]["radius"] = 0.75
        self.assertRaises(receipt.Rejected, receipt.validate_setup, header, case)

    def test_boolean_joint_mode_input_must_match_captured_mode(self):
        settings = {key: 0 for key in ("gravity", "stepFrequency", "maximumTranslation",
                    "maximumRotation", "atRestDetectionEnabled", "maximumAtRestLinearVelocity",
                    "maximumAtRestAngularVelocity", "minimumAtRestTime", "velocityIterations",
                    "positionIterations", "warmStartingEnabled", "maximumWarmStartDistance",
                    "linearTolerance", "angularTolerance", "maximumLinearCorrection",
                    "maximumAngularCorrection", "baumgarte", "continuousDetectionMode", "narrowphase")}
        settings["gravity"] = [0.0, 0.0]
        settings["timeOfImpact"] = {"distanceEpsilon": 4.806217383937352e-6}
        def body(index):
            return {"id": f"b{index}", "transform": {"getTranslation": [0.0, float(index)]},
                    "massType": "NORMAL", "mass": 1.0, "inertia": 1.0,
                    "massCenter": [0.0, 0.0], "linearDamping": 0.0,
                    "angularDamping": 0.0, "initialVelocity": [0.0, 0.0],
                    "initialAngularVelocity": 0.0, "atRestDetectionEnabled": True,
                    "bullet": False, "fixtures": [{"id": f"b{index}f0", "density": 1.0,
                    "friction": 0.2, "restitution": 0.0, "restitutionVelocity": 1.0,
                    "sensor": False, "filter": "DEFAULT_FILTER", "shape": {"type": "Circle"}}]}
        header = {"settings": settings, "setup": {"bodies": [body(0), body(1)],
                  "joints": [{"id": "j0", "bodies": [0, 1],
                              "mode": {"type": "Angle", "limitsEnabled": False}}]}}
        case = {"id": "joint-Angle-LimitsEnabled-false", "family": "joints-limits-motors",
                "input": {"jointType": "Angle", "field": "LimitsEnabled", "initialValue": False}}
        receipt.validate_setup(header, case)
        header["setup"]["joints"][0]["mode"]["limitsEnabled"] = True
        self.assertRaises(receipt.Rejected, receipt.validate_setup, header, case)

        mode = header["setup"]["joints"][0]["mode"]
        mode["ratio"] = 2.0
        numeric = {**case, "id": "joint-Angle-Ratio-2.0",
                   "input": {"jointType": "Angle", "field": "Ratio", "initialValue": 2.0}}
        receipt.validate_setup(header, numeric)
        mode["ratio"] = 1.0
        self.assertRaises(receipt.Rejected, receipt.validate_setup, header, numeric)

        mode["lowerLimit"], mode["upperLimit"] = -0.5, 0.5
        mode["limitsEnabled"] = True
        limits = {**case, "id": "joint-Angle-limits-range",
                  "input": {"jointType": "Angle", "limits": "range",
                            "lowerLimit": -0.5, "upperLimit": 0.5}}
        receipt.validate_setup(header, limits)
        mode["upperLimit"] = 0.0
        self.assertRaises(receipt.Rejected, receipt.validate_setup, header, limits)

    def test_input_signed_zero_and_event_order_are_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            original = self.write(folder, "original.jsonl", sample())
            for change in (lambda rows: rows[0]["input"]["velocity"].__setitem__(0, 0.0),
                           lambda rows: rows[1]["state"].__setitem__("x", 0.0),
                           lambda rows: rows[2].__setitem__("order", 1),
                           lambda rows: rows[0]["input"].__setitem__("velocity", [2.0, 1.0])):
                altered = copy.deepcopy(sample())
                change(altered)
                changed = self.write(folder, "changed.jsonl", altered)
                self.assertRaises(receipt.Rejected, receipt.compare_exact, original, changed, CASES)

    def test_nonfinite_and_zero_case_run_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / "nonfinite.jsonl"
            path.write_text(json.dumps(HEADER) + "\n" + '{"kind":"state","id":"motion","step":1,"order":0,"state":{"x":Infinity}}\n')
            self.assertRaises(receipt.Rejected, receipt.inspect, path, CASES)
            tagged = copy.deepcopy(sample())
            tagged[1]["state"]["x"] = {"nonfinite": "-Infinity"}
            tagged_path = self.write(folder, "tagged.jsonl", tagged)
            self.assertRaises(receipt.Rejected, receipt.inspect, tagged_path, CASES)
            self.assertEqual(list(receipt.records(tagged_path, allow_tagged_nonfinite=True))[1]
                             ["state"]["x"], {"nonfinite": "-Infinity"})
            self.assertRaises(receipt.Rejected, receipt.inspect, self.write(folder, "empty.jsonl", []), CASES)

    def test_configured_endpoints_do_not_advance_temporal_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            cases = [{**CASES[0], "outer_group": 2}]
            rows = sample()
            rows[-1] = {**rows[-1], "endpoints": 1}
            rows.insert(-1, {"kind": "endpoint", "id": "motion", "step": 2, "order": 2, "state": {"x": 1.0}})
            self.assertEqual(receipt.inspect(self.write(folder, "good.jsonl", rows), cases)["endpoints"], 1)
            self.assertRaises(receipt.Rejected, receipt.inspect, self.write(folder, "bad.jsonl", rows[:-2] + rows[-1:]), cases)

    def test_missing_callback_or_action_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            rows = sample()
            rows.insert(1, {"kind": "event", "id": "motion", "step": 1, "order": 0, "name": "step.begin"})
            rows[2]["order"] = 1
            rows[-1]["events"] = 2
            expected = [{**CASES[0], "min_step_events": 1, "expected_actions": [2]}]
            self.assertRaises(receipt.Rejected, receipt.inspect, self.write(folder, "missing-action.jsonl", rows), expected)
            rows.insert(-2, {"kind": "action", "id": "motion", "step": 2, "order": 1, "name": "impulse"})
            rows[-2]["order"] = 2
            rows[-1]["events"] = 3
            self.assertEqual(receipt.inspect(self.write(folder, "complete.jsonl", rows), expected)["executed_cases"], 1)

    def test_stale_artifact_and_altered_trace_fail_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            trace = self.write(folder, "trace.jsonl", sample())
            artifact = folder / "artifact.jar"
            artifact.write_bytes(b"staged artifact")
            identity = receipt.Identity("a" * 40, "b" * 64, {"jvm": hashlib.sha256(artifact.read_bytes()).hexdigest()}, "jvm-test")
            sealed = receipt.seal(trace, CASES, identity, {"jvm": artifact})
            self.assertEqual(sealed["reference_source_revision"], "058bf6d982a0fb89b54050f929f6ea9dae53b714")
            self.assertEqual(sealed["expected_counts"]["cases"], 1)
            receipt.verify(sealed, trace, CASES, identity, {"jvm": artifact})
            artifact.write_bytes(b"different")
            self.assertRaises(receipt.Rejected, receipt.verify, sealed, trace, CASES, identity, {"jvm": artifact})
            artifact.write_bytes(b"staged artifact")
            trace.write_text(trace.read_text() + "{}\n")
            self.assertRaises(receipt.Rejected, receipt.verify, sealed, trace, CASES, identity, {"jvm": artifact})


if __name__ == "__main__":
    unittest.main()
