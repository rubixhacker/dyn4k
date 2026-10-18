import copy
import gzip
import hashlib
import json
import math
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nominal_quality


class NominalQualityTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixture = {
            "id": "L-free-s1.0-o0.0,0.0-hz60",
            "counts": {"inputs": 1, "event": 4, "state": 1},
            "analytic_limits": {"position_component_m": 1e-10,
                                "cosine_or_sine": 7e-11,
                                "wrapped_angle_rad": 5e-8,
                                "unwrapped_rotation_rad": 6e-8},
            "reference": {},
        }
        dt = 1.0 / 60.0
        self.header = {"kind": "inputs", "id": self.fixture["id"], "steps": 1, "dt": dt,
                       "state": {"bodies": [{"transform": {"getCost": 1.0, "getSint": 0.0,
                                                          "getRotationAngle": 0.0,
                                                          "getTranslation": [0.0, 0.0]}}]}}
        token = (json.dumps(self.header, sort_keys=True) + "\n").encode()
        self.fixture["reference"]["input_sha256"] = hashlib.sha256(token[:-1]).hexdigest()
        angle = dt / 2
        current = {"getCost": math.cos(angle), "getSint": math.sin(angle),
                   "getRotationAngle": angle, "getTranslation": [0.25 * dt, -0.125 * dt]}
        previous = copy.deepcopy(self.header["state"]["bodies"][0]["transform"])
        body = {"id": "b0", "transform": current, "previousTransform": previous,
                "worldCenter": current["getTranslation"],
                "fixedOriginPosition": current["getTranslation"],
                "velocity": [0.25, -0.125], "angularVelocity": 0.5,
                "force": [0.0, 0.0], "torque": 0.0,
                "accumulatedForce": [0.0, 0.0], "accumulatedTorque": 0.0,
                "rotationIncrementSum": angle}
        step_values = {"getDeltaTime": dt, "getPrevousDeltaTime": dt,
                       "getInverseDeltaTime": 60.0, "getPreviousInverseDeltaTime": 60.0,
                       "getDeltaTimeRatio": 1.0, "type": "org.dyn4j.dynamics.TimeStep"}
        self.rows = [self.header] + [
            {"kind": "event", "step": 1, "order": order, "listener": "StepListener",
             "method": "org.dyn4j.world.listener.StepListener." + method + "(",
             "payload": [step_values, {"world": self.fixture["id"]}]}
            for order, method in enumerate(("begin", "updatePerformed", "postSolve", "end"))
        ] + [{"kind": "state", "step": 1, "state": {"bodies": [body], "joints": []}}]

    def audit(self, change=None):
        self.sequence = getattr(self, "sequence", 0) + 1
        reference = self.root / "reference.jsonl.gz"
        candidate = self.root / "candidate.jsonl.gz"
        baseline = copy.deepcopy(self.rows)
        observed = copy.deepcopy(self.rows)
        if change:
            change(observed)
        for path, rows in ((reference, baseline), (candidate, observed)):
            with gzip.open(path, "wt") as stream:
                for row in rows:
                    stream.write(json.dumps(row, sort_keys=True) + "\n")
        return nominal_quality.audit_pair(self.fixture, reference, candidate,
                                          self.root / f"per-step-{self.sequence}.jsonl.gz")

    def test_real_shape_per_step_checks_are_conditional_on_rotation_premises(self):
        result = self.audit()
        self.assertEqual(result["status"], "UNPASSED_PREMISE")
        self.assertEqual(result["counts"], self.fixture["counts"])
        self.assertEqual(result["position"]["analytic_checks"], 4)
        self.assertEqual(result["rotation"]["analytic_checks"], 8)
        self.assertEqual(result["positive_zero_checks"], {"reference": 6, "candidate": 6})
        with gzip.open(self.root / "per-step-1.jsonl.gz", "rt") as evidence:
            step = json.loads(next(evidence))
            self.assertEqual(step["position_differential"],
                             [{"axis": 0, "error": "0", "cap": "1/5000000000", "verdict": "PASS"},
                              {"axis": 1, "error": "0", "cap": "1/5000000000", "verdict": "PASS"}])
            self.assertEqual(step["velocity_differential"],
                             [{"axis": axis, "error": "0", "cap": "0", "verdict": "PASS"}
                              for axis in range(3)])

    def test_position_velocity_and_positive_zero_mutants_reject(self):
        def move(rows):
            body = rows[-1]["state"]["bodies"][0]
            for name in ("worldCenter", "fixedOriginPosition"):
                body[name][0] = 0.1
            body["transform"]["getTranslation"][0] = 0.1

        for change in (move, lambda rows: rows[-1]["state"]["bodies"][0]["velocity"].__setitem__(0, 0.26)):
            with self.subTest(change=change):
                self.assertEqual(self.audit(change)["status"], "PHYSICAL_FAILED")
        with self.assertRaises(nominal_quality.Invalid):
            self.audit(lambda rows: rows[-1]["state"]["bodies"][0]["force"].__setitem__(0, -0.0))

    def test_missing_event_and_changed_input_reject(self):
        for change in (lambda rows: rows.pop(2),
                       lambda rows: rows[0].__setitem__("dt", 0.02)):
            with self.subTest(change=change), self.assertRaises(nominal_quality.Invalid):
                self.audit(change)

    def test_rotation_cap_and_callback_order_are_checked(self):
        result = self.audit(lambda rows: rows[-1]["state"]["bodies"][0]["transform"].__setitem__(
            "getCost", 0.99))
        self.assertEqual(result["status"], "PHYSICAL_FAILED")
        self.assertEqual(result["rotation"]["first_failure"]["step"], 1)
        for change in (lambda rows: rows[1].__setitem__("order", 1),
                       lambda rows: rows.insert(2, copy.deepcopy(rows[1])),
                       lambda rows: rows[-1]["state"]["bodies"][0].__setitem__("rotationIncrementSum", math.nan)):
            with self.subTest(change=change), self.assertRaises(nominal_quality.Invalid):
                self.audit(change)

    @unittest.skipUnless(os.environ.get("NOMINAL_PHYSICAL_DIAGNOSTIC"),
                         "retained source-bound JVM capture is not selected")
    def test_retained_diagnostic_rejects_source_artifact_process_and_trace_mutations(self):
        root = Path(os.environ["NOMINAL_PHYSICAL_DIAGNOSTIC"])
        diagnostic = json.loads((root / "comparison/result.json").read_text())
        bound = json.loads((root / "comparison/receipt.json").read_text())
        identity = diagnostic["identity"]
        trace = root / "capture/L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz"
        reference = Path(os.environ["NOMINAL_PHYSICAL_REFERENCE"])
        changes = (
            ("source", "receipt", lambda row: row.__setitem__("source_sha256", "0" * 64)),
            ("artifact", "receipt", lambda row: row.__setitem__("artifact_sha256", "0" * 64)),
            ("process", "receipt", lambda row: row["runtime"].__setitem__("process_id", "0")),
            ("trace", "result", lambda row: row["identity"].__setitem__("trace_sha256", "0" * 64)),
        )
        for name, target, change in changes:
            with self.subTest(name=name):
                observed = copy.deepcopy(bound if target == "receipt" else diagnostic)
                change(observed)
                mutant = self.root / (name + ".json")
                mutant.write_text(json.dumps(observed))
                args = types.SimpleNamespace(
                    fixture="nominal-free-motion", trace=trace,
                    receipt=mutant if target == "receipt" else root / "comparison/receipt.json",
                    reference=reference, jdk_home=identity["runtime"]["java_home"],
                    output=self.root / (name + "-output"),
                    diagnostic_result=mutant if target == "result" else root / "comparison/result.json",
                    artifact=identity["artifact_path"], source_commit=identity["source_commit"])
                with self.assertRaises(nominal_quality.Invalid):
                    nominal_quality.verify(args)


if __name__ == "__main__":
    unittest.main()
