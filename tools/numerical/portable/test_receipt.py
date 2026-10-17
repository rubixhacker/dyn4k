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
            self.assertRaises(receipt.Rejected, receipt.inspect,
                              self.write(folder, "tagged.jsonl", tagged), CASES)
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
