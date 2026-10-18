import copy
import gzip
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
import exact_consistency as exact
import receipt


TRACE = Path("/tmp/dyn4k-root-world-configured-f9920e9/baseline-trace/"
             "Q-sleep-wake-outer30-repeat1-0.jsonl.gz")


@unittest.skipUnless(TRACE.is_file(), "approved configured baseline trace unavailable")
class ExactConsistencyAdverseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = receipt.load_fixture("configured-30-r1", Path(__file__).resolve().parents[1] / "fixtures.json")
        cls.input = cls.first_event = cls.first_state = cls.endpoint = cls.endpoint_state = None
        cls.before = cls.after = cls.sleeping = cls.pre_action = None
        with gzip.open(TRACE, "rb") as stream:
            for line in stream:
                row = compare.parse(line)
                kind = row["kind"]
                if kind == "inputs": cls.input, cls.input_line = row, line
                elif kind == "event" and cls.first_event is None: cls.first_event = row
                elif kind == "state":
                    if cls.first_state is None: cls.first_state = row
                    if row["step"] == 4: cls.endpoint_state = row
                    if row["step"] == 36000: cls.pre_action = row
                    if cls.sleeping is None and row["state"]["bodies"][1]["atRest"]:
                        cls.sleeping = row
                elif kind == "outer-endpoint" and cls.endpoint is None: cls.endpoint = row
                elif kind == "instrumented-callback":
                    if row["event"] == "before-wake": cls.before = row["values"][0]
                    if row["event"] == "after-wake":
                        cls.after = row["values"][0]
                        break

    def reject_snapshot(self, row, phase, prior, field, value, reason):
        changed = copy.deepcopy(row)
        changed["bodies"][1 if field.startswith("moving") else 0]
        value(changed)
        with self.assertRaisesRegex(compare.Rejected, reason):
            exact.snapshot(changed, phase, prior)

    def audit_rows(self, rows):
        with tempfile.TemporaryDirectory() as root:
            trace = Path(root) / "trace.jsonl"
            trace.write_bytes(b"".join(rows))
            return exact.audit_trace(trace, self.fixture)

    def test_fixed_floor_group_rejects_pose_mutation(self):
        exact.numeric_vector([-0.0, -0.25], [0.0, -0.25], "floor pose")
        with self.assertRaisesRegex(compare.Rejected, "translation alias"):
            exact.exact([-0.0, -0.25], [0.0, -0.25], "translation alias")
        self.reject_snapshot(self.first_state["state"], "step", self.input["state"], "floor",
            lambda row: row["bodies"][0]["transform"]["getTranslation"].__setitem__(1, -0.24),
            "translation alias|floor pose")

    def test_zero_force_group_rejects_applied_force(self):
        self.reject_snapshot(self.first_state["state"], "step", self.input["state"], "moving",
            lambda row: row["bodies"][1]["force"].__setitem__(0, 0.001), "force zero")

    def test_snapshot_schema_rejects_text_numeric_and_boolean_indices(self):
        for field, value in (("velocity", ["0", 0.0]), ("angularVelocity", "0"),
                             ("rotationIncrementSum", "0"),
                             ("rotationStepBoundBelowPi", 1),
                             ("rotationTrackingScope", 1)):
            changed = copy.deepcopy(self.first_state["state"])
            changed["bodies"][1][field] = value
            with self.subTest(field=field), self.assertRaises(compare.Rejected):
                exact.snapshot(changed, "step", self.input["state"])
        event = copy.deepcopy(self.first_event)
        event["step"] = True
        with self.assertRaisesRegex(compare.Rejected, "record step schema"):
            self.audit_rows([self.input_line, (json.dumps(event) + "\n").encode()])

    def test_sleep_group_rejects_velocity_and_pose_drift(self):
        state = self.sleeping["state"]
        previous = copy.deepcopy(state)
        changed = copy.deepcopy(state)
        changed["bodies"][1]["velocity"][0] = 0.1
        with self.assertRaisesRegex(compare.Rejected, "sleep velocity"):
            exact.snapshot(changed, "step", previous)
        changed = copy.deepcopy(state)
        changed["bodies"][1]["transform"]["getTranslationX"] = 0.1
        with self.assertRaises(compare.Rejected):
            exact.snapshot(changed, "step", previous)

    def test_center_impulse_group_rejects_extra_change(self):
        exact.impulse(self.before, self.after)
        changed = copy.deepcopy(self.after)
        changed["bodies"][1]["torque"] = 1
        with self.assertRaisesRegex(compare.Rejected, "impulse unchanged fields"):
            exact.impulse(self.before, changed)

    def test_alias_duplicate_phase_and_signed_zero_group(self):
        exact.snapshot(self.before, "before", self.pre_action["state"])
        with self.assertRaisesRegex(compare.Rejected, "phase-correct previous copy"):
            exact.snapshot(self.first_state["state"], "step", self.first_state["state"])
        changed = copy.deepcopy(self.before)
        changed["bodies"][1]["properties"]["getForce"][0] = 1
        with self.assertRaisesRegex(compare.Rejected, "duplicate getForce"):
            exact.snapshot(changed, "before", self.pre_action["state"])
        changed = copy.deepcopy(self.before)
        changed["bodies"][1]["previousTransform"]["getTranslationX"] = 1
        with self.assertRaises(compare.Rejected):
            exact.snapshot(changed, "before", self.pre_action["state"])
        changed = copy.deepcopy(self.before)
        old = changed["bodies"][1]["force"][0]
        changed["bodies"][1]["force"][0] = -0.0 if math.copysign(1, old) > 0 else 0.0
        with self.assertRaisesRegex(compare.Rejected, "duplicate getForce"):
            exact.snapshot(changed, "before", self.pre_action["state"])
        endpoint = copy.deepcopy(self.endpoint)
        endpoint["state"]["bodies"][1]["force"][0] = -0.0
        with self.assertRaisesRegex(compare.Rejected, "endpoint numeric copy"):
            exact.endpoint(endpoint, self.endpoint_state, 30, 4)

    def test_timestep_group_rejects_metadata_mutation(self):
        step = self.first_event["payload"][0]
        exact.timestep(step, 120, 1)
        changed = dict(step, getPreviousInverseDeltaTime=120)
        with self.assertRaisesRegex(compare.Rejected, "timestep"):
            exact.timestep(changed, 120, 1)

    def test_fixed_floor_callback_velocity_is_exact_zero(self):
        payload = {"body1": "b0", "velocity1": [0.0, -0.0], "angularVelocity1": 0.0}
        exact.fixed_callback_payload(payload)
        payload["velocity1"][0] = 0.001
        with self.assertRaisesRegex(compare.Rejected, "fixed callback body velocity"):
            exact.fixed_callback_payload(payload)

    def test_unknown_method_is_rejected_before_count_check(self):
        event = copy.deepcopy(self.first_event)
        event["method"] = "public void org.dyn4j.world.listener.StepListener.bogus()"
        with self.assertRaisesRegex(compare.Rejected, "unrecognized listener method"):
            self.audit_rows([self.input_line, (json.dumps(event) + "\n").encode()])

    def test_missing_and_duplicate_records_fail_closed(self):
        with self.assertRaisesRegex(compare.Rejected, "incomplete counts"):
            self.audit_rows([self.input_line])
        with self.assertRaises(compare.Rejected):
            self.audit_rows([self.input_line] * 2)
        event = (json.dumps(self.first_event) + "\n").encode()
        with self.assertRaisesRegex(compare.Rejected, "record order"):
            self.audit_rows([self.input_line, event, event])

    def test_endpoint_does_not_advance_temporal_prior(self):
        rows = []
        with gzip.open(TRACE, "rb") as stream:
            for line in stream:
                row = compare.parse(line)
                rows.append((line, row))
                if row["kind"] == "state" and row["step"] == 5:
                    break
        fourth = next(row for _, row in rows if row["kind"] == "state" and row["step"] == 4)
        endpoint = next(row for _, row in rows if row["kind"] == "outer-endpoint")
        self.assertIsNot(fourth["state"], endpoint["state"])
        with patch.object(compare, "records", return_value=iter(rows)):
            with patch.object(exact, "snapshot", wraps=exact.snapshot) as checked:
                with self.assertRaisesRegex(compare.Rejected, "incomplete counts"):
                    exact.audit_trace(TRACE, self.fixture)
                self.assertIs(checked.call_args.args[2], fourth["state"])
                self.assertIsNot(checked.call_args.args[2], endpoint["state"])

    def test_wrong_runtime_source_artifact_and_archive_bindings_reject(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            artifact = root / "candidate.jar"
            binary = root / "java"
            trace = root / "trace.jsonl.gz"
            classes = root / "classes"
            classes.mkdir()
            (classes / "Recorder.class").write_bytes(b"bytecode")
            source = root / "Recorder.java"
            source.write_bytes(b"source")
            artifact.write_bytes(b"candidate")
            binary.write_bytes(b"process")
            trace.write_bytes(b"trace")
            stamp = {key: "known" for key in receipt.RUNTIME_FIELDS}
            stamp.update(process_command=str(binary), engine_location=artifact.as_uri(),
                         recorder_location=classes.as_uri())
            (root / "runtime.json").write_text(json.dumps(stamp))
            with patch.object(exact, "source_archive", return_value="source-hash"):
                bound = exact.identity(trace, artifact, "f" * 40, [source])
                exact.verify_binding(bound, bound)
                for field in ("source_commit", "source_archive_sha256", "artifact_sha256",
                              "process_sha256", "runtime_stamp_sha256", "trace_sha256",
                              "recorder_classes_sha256", "recorder_source_sha256"):
                    changed = dict(bound, **{field: "wrong"})
                    with self.subTest(field=field), self.assertRaisesRegex(compare.Rejected, "identity"):
                        exact.verify_binding(changed, bound)
                for path, field in ((artifact, "artifact_sha256"), (binary, "process_sha256"),
                                    (trace, "trace_sha256"), (source, "recorder_source_sha256"),
                                    (classes / "Recorder.class", "recorder_classes_sha256")):
                    original = path.read_bytes()
                    path.write_bytes(original + b"changed")
                    changed = exact.identity(trace, artifact, "f" * 40, [source])
                    with self.subTest(mutated=field), self.assertRaisesRegex(compare.Rejected, "identity"):
                        exact.verify_binding(bound, changed)
                    path.write_bytes(original)
                stamp["engine_location"] = (root / "other.jar").as_uri()
                (root / "runtime.json").write_text(json.dumps(stamp))
                with self.assertRaisesRegex(compare.Rejected, "loaded engine artifact path"):
                    exact.identity(trace, artifact, "f" * 40, [source])


if __name__ == "__main__":
    unittest.main()
