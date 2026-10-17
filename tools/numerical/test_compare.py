import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from compare import audit_reference, compare
from physical import audit_physical


def encoded(rows):
    return b"".join(json.dumps(row, separators=(",", ":"), sort_keys=True).encode() + b"\n" for row in rows)


class ComparatorSeamTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rows = [
            {"kind": "inputs", "id": "sample", "dt": 0.5},
            {"kind": "event", "step": 1, "order": 0, "listener": "StepListener", "method": "begin", "payload": [{"velocity": [1.0, -2.0]}]},
            {"kind": "state", "step": 1, "state": {"position": [2.0, 3.0], "normal": [1.0, 0.0], "angle": 3.141592653589793, "sum": 9.0}},
        ]
        self.fixture = {
            "id": "sample", "reference": {"file": "reference.jsonl.gz"},
            "source_sha256": "a" * 64, "artifact_sha256": "b" * 64,
            "baseline_source_revision": "f" * 40, "baseline_jar_sha256": "e" * 64,
            "counts": {"inputs": 1, "event": 1, "state": 1},
            "rules": [
                {"path": "event.payload[].velocity[]", "metric": "scalar", "absolute": 0.1, "relative": 0, "unit": "m/s"},
                {"path": "state.state.position[]", "metric": "scalar", "absolute": 0.1, "relative": 0.01, "unit": "m"},
                {"path": "state.state.normal", "metric": "direction", "absolute": 0.01, "relative": 0, "magnitude_absolute": 0.001, "unit_deviation": 0.001, "unit": "rad"},
                {"path": "state.state.angle", "metric": "orientation", "absolute": 0.01, "relative": 0, "unit": "rad"},
                {"path": "state.state.sum", "metric": "scalar", "absolute": 0.01, "relative": 0, "unit": "rad"},
            ],
            "exact_numeric": ["inputs.dt", "event.step", "event.order", "state.step"],
        }
        self.write_reference(self.rows)
        self.write_candidate(self.rows)

    def write_reference(self, rows):
        data = encoded(rows)
        path = self.root / "reference.jsonl.gz"
        path.write_bytes(gzip.compress(data, mtime=0))
        self.fixture["reference"].update({
            "gzip_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "stream_sha256": hashlib.sha256(data).hexdigest(),
            "input_sha256": hashlib.sha256(data.splitlines()[0]).hexdigest(),
        })

    def write_candidate(self, rows, *, source=None, artifact=None, counts=None):
        data = encoded(rows)
        path = self.root / "candidate.jsonl"
        path.write_bytes(data)
        (self.root / "receipt.json").write_text(json.dumps({
            "source_sha256": source or "c" * 64,
            "artifact_sha256": artifact or "d" * 64,
            "candidate_commit": "1" * 40,
            "trace_sha256": hashlib.sha256(data).hexdigest(),
            "reference_source_revision": self.fixture["baseline_source_revision"],
            "reference_artifact_sha256": self.fixture["baseline_jar_sha256"],
            "reference_trace_sha256": self.fixture["reference"]["gzip_sha256"],
            "expected_counts": counts or self.fixture["counts"],
            "executed_counts": counts or self.fixture["counts"],
            "skipped": 0,
        }))

    def result(self):
        return compare(self.fixture, self.root / "reference.jsonl.gz", self.root / "candidate.jsonl",
                       self.root / "receipt.json", "c" * 64, "d" * 64, "1" * 40)

    def test_approved_components_and_wrap_pass_at_inclusive_limit(self):
        rows = json.loads(json.dumps(self.rows))
        rows[1]["payload"][0]["velocity"] = [1.05, -2.05]
        rows[2]["state"]["position"] = [2.11, 3.12]
        rows[2]["state"]["normal"] = [0.9999875000260416, 0.004999979166692708]
        rows[2]["state"]["angle"] = -3.141592653589793
        self.write_candidate(rows)
        self.assertEqual("PASSED", self.result()["status"])

    def test_scalar_vector_and_unwrapped_limit_fail(self):
        for path, value in [("position", [2.0, 3.14]), ("sum", 9.02),
                            ("normal", [-1.0, 0.0]), ("normal", [1.002, 0.0]),
                            ("normal", [0.9998, 0.02])]:
            with self.subTest(path=path):
                rows = json.loads(json.dumps(self.rows))
                rows[2]["state"][path] = value
                self.write_candidate(rows)
                self.assertEqual("FAILED", self.result()["status"])

    def test_missing_nonfinite_unknown_and_order_fail_closed(self):
        mutations = [
            lambda r: r[2]["state"].pop("sum"),
            lambda r: r[2]["state"].update(sum=float("nan")),
            lambda r: r[2]["state"].update(unknown=1.0),
            lambda r: r[1].update(method="end"),
            lambda r: r.pop(1),
        ]
        for mutate in mutations:
            rows = json.loads(json.dumps(self.rows))
            mutate(rows)
            self.write_candidate(rows)
            self.assertNotEqual("PASSED", self.result()["status"])

    def test_identity_counts_and_skips_fail_closed(self):
        self.write_candidate(self.rows, counts={"inputs": 1, "event": 1, "state": 2})
        self.assertEqual("FAILED", self.result()["status"])
        self.write_candidate(self.rows)
        receipt = self.root / "receipt.json"
        data = json.loads(receipt.read_text())
        for key, value in [("source_sha256", "e" * 64), ("artifact_sha256", "e" * 64),
                           ("candidate_commit", "0" * 40),
                           ("reference_source_revision", "0" * 40),
                           ("reference_artifact_sha256", "0" * 64),
                           ("reference_trace_sha256", "0" * 64), ("skipped", 1)]:
            altered = dict(data, **{key: value})
            receipt.write_text(json.dumps(altered))
            self.assertEqual("FAILED", self.result()["status"])
        self.write_candidate(self.rows)

    def test_reference_hash_and_empty_suite_fail_closed(self):
        self.assertEqual("PASSED", audit_reference(self.fixture, self.root / "reference.jsonl.gz")["status"])
        bad = self.root / "bad.jsonl.gz"
        bad.write_bytes(self.root.joinpath("reference.jsonl.gz").read_bytes() + b"x")
        self.assertEqual("FAILED", audit_reference(self.fixture, bad)["status"])
        rows = [self.rows[0]]
        self.write_reference(rows)
        self.assertEqual("FAILED", audit_reference(self.fixture, self.root / "reference.jsonl.gz")["status"])
        self.fixture["counts"] = {"inputs": 1}
        self.write_candidate(rows)
        self.assertEqual("FAILED", self.result()["status"])

    def test_outer_endpoint_must_copy_the_matching_inner_state(self):
        rows = json.loads(json.dumps(self.rows))
        rows.append({"kind": "outer-endpoint", "step": 1, "outerStep": 1,
                     "state": json.loads(json.dumps(rows[2]["state"]))})
        self.fixture["counts"]["outer-endpoint"] = 1
        self.fixture["inner_per_outer"] = 1
        self.write_reference(rows)
        self.assertEqual("PASSED", audit_reference(self.fixture, self.root / "reference.jsonl.gz")["status"])
        rows[-1]["state"]["position"][0] = 999.0
        self.write_reference(rows)
        self.assertEqual("FAILED", audit_reference(self.fixture, self.root / "reference.jsonl.gz")["status"])

    def test_exact_represented_geometry_uses_phase_ceiling(self):
        self.fixture["physical_phase_ceilings_m"] = {"rest-before": 0.001}
        self.fixture["physical_phases_steps"] = [["rest-before", 1, 1]]
        rows = [self.rows[0], {"kind": "state", "step": 1, "state": {"bodies": [
            {"id": "b0", "transform": {"getCost": 1.0, "getSint": 0.0, "getTranslation": [0.0, -0.25]}},
            {"id": "b1", "transform": {"getCost": 1.0, "getSint": 0.0, "getTranslation": [0.0, 0.5]}}
        ]}}]
        self.fixture["counts"] = {"inputs": 1, "state": 1}
        self.write_reference(rows)
        self.assertEqual("PHYSICAL_PASSED", audit_physical(self.fixture, self.root / "reference.jsonl.gz")["status"])
        rows[1]["state"]["bodies"][1]["transform"]["getTranslation"][1] = 0.49
        self.write_reference(rows)
        self.assertEqual("PHYSICAL_FAILED", audit_physical(self.fixture, self.root / "reference.jsonl.gz")["status"])

    def test_translation_alias_must_match_same_run(self):
        rows = json.loads(json.dumps(self.rows))
        self.fixture["family"] = "free-motion"
        self.fixture["check_translation_aliases"] = True
        rows[2]["state"] = {"bodies": [{"id": "b0", "transform": {
            "getTranslation": [2.0, 3.0], "getTranslationX": 2.0, "getTranslationY": 3.0}}]}
        self.write_reference(rows)
        self.assertEqual("PASSED", audit_reference(self.fixture, self.root / "reference.jsonl.gz")["status"])
        rows[2]["state"]["bodies"][0]["transform"]["getTranslationX"] = 2.01
        self.write_reference(rows)
        self.assertEqual("FAILED", audit_reference(self.fixture, self.root / "reference.jsonl.gz")["status"])


if __name__ == "__main__":
    unittest.main()
