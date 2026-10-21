import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import baseline_capture
from pulley_jdi_v1 import Rejected, inspect_bundle


CASE_ID = "P-JINT-Pulley-slack-transition-preparation-0"
NONCE = "a" * 64


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


class PulleyJdiV1Test(unittest.TestCase):
    def test_external_producer_keeps_frozen_source_setup_and_fixture_hash(self):
        root = Path(__file__).resolve().parent
        original = (root / "src/commonTest/kotlin/portable/PortableMatrixTest.kt").read_text()
        producer_path = root / "pulley-jdi-sidecar-v2/src/test/kotlin/portable/PulleyPreparationJdiV1Test.kt"
        self.assertTrue(producer_path.is_file())
        producer = producer_path.read_text()
        helper_start = "    private fun body(world: World<Body>"
        helper_end = "\n    @Test"
        self.assertEqual(original[original.index(helper_start):original.index(helper_end)],
                         producer[producer.index(helper_start):producer.index(helper_end)])
        setup_start = "        val pulleyWorld = World<Body>()"
        setup_end = "), pulleyWorld)"
        self.assertEqual(original[original.index(setup_start):
                                  original.index(setup_end, original.index(setup_start)) + len(setup_end)],
                         producer[producer.index(setup_start):
                                  producer.index(setup_end, producer.index(setup_start)) + len(setup_end)])
        self.assertEqual(producer.count("recorder.capture("), 1)
        self.assertEqual(producer.count("@Test"), 1)
        self.assertEqual(baseline_capture.fixture_source_sha256(),
                         "dd104a7e018b9d0bd77c9af14e929699d68f29fa4ac8179a5bd7d98bdc87d9ce")

    def fixture(self, root):
        root = Path(root)
        artifact = root / "artifact.jar"
        artifact.write_bytes(b"focused-candidate-artifact")
        case = root / "case.jsonl"
        case.write_bytes(b"".join(encode(row) for row in (
            {"kind": "inputs", "id": CASE_ID, "family": "joints-limits-motors",
             "profile": "frozen-weld-pulley", "hz": 60, "steps": 1,
             "startStep": 0, "input": {"jointType": "Pulley",
             "segment": "preparation-0", "sourceVelocity": [0.0, 0.0]}},
            {"kind": "state", "id": CASE_ID, "step": 1, "order": 0, "state": {}},
            {"kind": "case-end", "id": CASE_ID, "steps": 1, "events": 0})))
        worker = {
            "schema": "pulley-preparation-worker/1", "pid": 1234,
            "case_id": CASE_ID, "step": 1, "nonce": NONCE,
            "case_sha256": digest(case.read_bytes()),
            "artifact_sha256": digest(artifact.read_bytes()),
            "class_source_uri": artifact.resolve().as_uri(),
        }
        event = {
            "schema": "pulley-jdi-event/1", "sequence": 1, "pid": 1234,
            "case_id": CASE_ID, "step": 1,
            "class_name": "org.dyn4j.dynamics.joint.PulleyJoint",
            "method": "initializeConstraints", "source_name": "PulleyJoint.kt",
            "line": 101, "code_index": 275, "branch": True,
            "l1": 1.0, "l2": 0.5, "l": 1.5, "length": 1.5,
            "ratio": 1.0, "slack_enabled": False, "over_length": True,
        }
        paths = {name: root / name for name in
                 ("case.jsonl", "artifact.jar", "worker.json", "events.jsonl", "jdi.json")}
        self.seal(paths, worker, [event])
        return paths, worker, event

    def seal(self, paths, worker, events):
        paths["worker.json"].write_bytes(encode(worker))
        paths["events.jsonl"].write_bytes(b"".join(encode(value) for value in events))
        manifest = {
            "schema": "pulley-jdi/1", "profile": "candidate", "pid": 1234,
            "nonce": NONCE, "artifact_sha256": digest(paths["artifact.jar"].read_bytes()),
            "case_sha256": digest(paths["case.jsonl"].read_bytes()),
            "worker_receipt_sha256": digest(paths["worker.json"].read_bytes()),
            "events_sha256": digest(paths["events.jsonl"].read_bytes()),
            "class_source_name": "PulleyJoint.kt",
            "class_source_uri": paths["artifact.jar"].resolve().as_uri(),
            "debuggee_exit": 0,
        }
        paths["jdi.json"].write_bytes(encode(manifest))

    def inspect(self, paths):
        with patch("pulley_jdi_v1.inspect", return_value={"executed_cases": 1, "states": 1}):
            return inspect_bundle(paths["case.jsonl"], paths["worker.json"],
                                  paths["events.jsonl"], paths["jdi.json"],
                                  paths["artifact.jar"])

    def test_complete_shape_is_still_unpassed_without_independent_process_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, _, _ = self.fixture(directory)
            result = self.inspect(paths)
            self.assertEqual(result["status"], "UNPASSED_EXTERNAL_PROCESS_PROOF")
            self.assertEqual(result["observed_calls"], 1)

    def test_self_consistent_forged_local_values_cannot_become_a_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, worker, event = self.fixture(directory)
            self.seal(paths, worker, [{**event, "l1": 1.25, "l2": 0.25}])
            self.assertEqual(self.inspect(paths)["status"],
                             "UNPASSED_EXTERNAL_PROCESS_PROOF")

    def test_public_trace_inspection_rejects_a_self_sealed_incomplete_case(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, _, _ = self.fixture(directory)
            with self.assertRaises(Rejected):
                inspect_bundle(paths["case.jsonl"], paths["worker.json"],
                               paths["events.jsonl"], paths["jdi.json"],
                               paths["artifact.jar"])

    def test_missing_and_modified_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, _, _ = self.fixture(directory)
            paths["case.jsonl"].write_bytes(paths["case.jsonl"].read_bytes() + b" ")
            with self.assertRaises(Rejected):
                self.inspect(paths)
        with tempfile.TemporaryDirectory() as directory:
            paths, _, _ = self.fixture(directory)
            paths["events.jsonl"].unlink()
            with self.assertRaises(Rejected):
                self.inspect(paths)

    def test_resealed_wrong_pid_or_extra_call_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, worker, event = self.fixture(directory)
            changed = {**event, "pid": 1235}
            self.seal(paths, worker, [changed])
            with self.assertRaises(Rejected):
                self.inspect(paths)
        with tempfile.TemporaryDirectory() as directory:
            paths, worker, event = self.fixture(directory)
            self.seal(paths, worker, [event, {**event, "sequence": 2}])
            with self.assertRaises(Rejected):
                self.inspect(paths)

    def test_resealed_false_branch_and_wrong_class_source_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, worker, event = self.fixture(directory)
            self.seal(paths, worker, [{**event, "branch": False}])
            with self.assertRaises(Rejected):
                self.inspect(paths)
        with tempfile.TemporaryDirectory() as directory:
            paths, worker, event = self.fixture(directory)
            worker["class_source_uri"] = (Path(directory) / "other.jar").as_uri()
            self.seal(paths, worker, [event])
            with self.assertRaises(Rejected):
                self.inspect(paths)

    def test_case_step_and_declared_input_are_checked_before_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, worker, event = self.fixture(directory)
            raw = paths["case.jsonl"].read_bytes().replace(b'"step":1', b'"step":2')
            paths["case.jsonl"].write_bytes(raw)
            worker["case_sha256"] = digest(raw)
            self.seal(paths, worker, [event])
            with self.assertRaises(Rejected):
                self.inspect(paths)


if __name__ == "__main__":
    unittest.main()
