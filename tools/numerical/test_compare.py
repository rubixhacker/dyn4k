import gzip
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

from compare import audit_reference, compare, load_fixture
from inventory import classify_reference
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
            {"kind": "event", "step": 1, "order": 0, "listener": "StepListener", "method": "begin", "payload": [{"velocity": [1.0, -2.0], "getPoint": [0.0, 0.0], "getDepth": 0.1, "getNormalImpulse": 0.25}]},
            {"kind": "state", "step": 1, "state": {"position": [2.0, 3.0], "normal": [1.0, 0.0], "angle": 3.141592653589793, "sum": 9.0}},
        ]
        self.fixture = {
            "id": "sample", "reference": {"file": "reference.jsonl.gz"},
            "source_sha256": "a" * 64, "artifact_sha256": "b" * 64,
            "baseline_source_revision": "f" * 40, "baseline_jar_sha256": "e" * 64,
            "counts": {"inputs": 1, "event": 1, "state": 1},
            "rules": [
                {"path": "event.payload[].velocity[]", "metric": "scalar", "absolute": 0.1, "relative": 0, "unit": "m/s"},
                {"path": "event.payload[].getPoint[]", "metric": "scalar", "absolute": 0.01, "relative": 0, "unit": "m"},
                {"path": "event.payload[].getDepth", "metric": "scalar", "absolute": 0.01, "relative": 0, "unit": "m"},
                {"path": "event.payload[].getNormalImpulse", "metric": "scalar", "absolute": 0.01, "relative": 0, "unit": "N s"},
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

    def test_equal_nonunit_normal_still_fails(self):
        rows = json.loads(json.dumps(self.rows))
        rows[2]["state"]["normal"] = [1.002, 0.0]
        self.write_reference(rows)
        self.write_candidate(rows)
        self.assertEqual("FAILED", self.result()["status"])

    def test_direct_callback_channels_use_their_approved_units(self):
        for name, value in (("getPoint", [0.02, 0.0]),
                            ("getDepth", 0.12), ("getNormalImpulse", 0.27)):
            with self.subTest(name=name):
                rows = json.loads(json.dumps(self.rows))
                rows[1]["payload"][0][name] = value
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

    def test_swapped_callbacks_fail_even_when_counts_match(self):
        rows = json.loads(json.dumps(self.rows))
        second = json.loads(json.dumps(rows[1]))
        second["order"] = 1
        second["method"] = "end"
        rows.insert(2, second)
        self.fixture["counts"]["event"] = 2
        self.write_reference(rows)
        candidate = json.loads(json.dumps(rows))
        candidate[1], candidate[2] = candidate[2], candidate[1]
        self.write_candidate(candidate)
        self.assertEqual("FAILED", self.result()["status"])
        candidate[1]["order"], candidate[2]["order"] = 0, 1
        self.write_candidate(candidate)
        self.assertEqual("FAILED", self.result()["status"])

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

    def test_identical_reference_bytes_need_a_candidate_receipt(self):
        self.write_candidate(self.rows)
        self.assertEqual("PASSED", self.result()["status"])
        (self.root / "receipt.json").unlink()
        result = self.result()
        self.assertEqual("FAILED", result["status"])
        self.assertIn("No such file", result["reason"])

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

    def test_configured_toi_fields_use_selected_limits(self):
        selected = load_fixture("configured-30-r1")
        self.fixture["rules"] = [rule for rule in selected["rules"]
                                 if rule["path"].startswith("event.payload[].getTime")
                                 or rule["path"].startswith("event.payload[].separation.")]
        self.fixture["exact_numeric"] = ["inputs.dt", "event.step", "event.order", "state.step"]
        toi = {"getTime": 0.5, "separation": {"getDistance": 0.2,
               "getPoint1": [1.0, 2.0], "getPoint2": [3.0, 4.0],
               "getNormal": [1.0, 0.0]}}
        rows = json.loads(json.dumps(self.rows))
        rows[1]["payload"] = [toi]
        rows[2]["state"] = {"bodies": []}
        self.write_reference(rows)
        self.write_candidate(rows)
        self.assertEqual("PASSED", self.result()["status"])
        for field, value in (("getTime", 0.500002),
                             ("getDistance", 0.2002),
                             ("getPoint1", [1.0002, 2.0]),
                             ("getPoint2", [3.0, 4.0002]),
                             ("getNormal", [-1.0, 0.0]),
                             ("getNormal", [1.000003, 0.0]),
                             ("getNormal", [0.0, 0.0])):
            with self.subTest(field=field):
                altered = json.loads(json.dumps(rows))
                target = altered[1]["payload"][0]
                if field != "getTime":
                    target = target["separation"]
                target[field] = value
                self.write_candidate(altered)
                self.assertEqual("FAILED", self.result()["status"])

    def test_fixed_floor_callback_velocities_remain_zero(self):
        selected = load_fixture("configured-30-r1")
        self.fixture["callback_fixed_body_id"] = "b0"
        self.fixture["rules"] = [rule for rule in selected["rules"]
                                 if rule["path"].startswith("event.payload[].velocity")
                                 or rule["path"].startswith("event.payload[].angularVelocity")]
        rows = json.loads(json.dumps(self.rows))
        rows[1]["payload"] = [{"body1": "b0", "body2": "b1", "velocity1": [0.0, 0.0],
                                "velocity2": [0.0, 0.0], "angularVelocity1": 0.0,
                                "angularVelocity2": 0.0}]
        rows[2]["state"] = {"bodies": []}
        self.write_reference(rows)
        self.write_candidate(rows)
        self.assertEqual("PASSED", self.result()["status"])
        for field, value in (("velocity1", [0.0005, 0.0]), ("angularVelocity1", 0.0005)):
            with self.subTest(field=field):
                altered = json.loads(json.dumps(rows))
                altered[1]["payload"][0][field] = value
                self.write_candidate(altered)
                result = self.result()
                self.assertEqual("FAILED", result["status"])
                self.assertIn("fixed callback body velocity", result["reason"])

    def test_outer_endpoint_uses_inner_state_budget(self):
        rows = json.loads(json.dumps(self.rows))
        rows[2]["state"] = {"position": [2.0, 3.0]}
        rows.append({"kind": "outer-endpoint", "step": 1, "outerStep": 1,
                     "state": {"position": [2.0, 3.0]}})
        self.fixture["counts"]["outer-endpoint"] = 1
        self.fixture["inner_per_outer"] = 1
        self.fixture["exact_numeric"].append("outer-endpoint.step")
        self.fixture["exact_numeric"].append("outer-endpoint.outerStep")
        self.write_reference(rows)
        altered = json.loads(json.dumps(rows))
        altered[2]["state"]["position"][0] = 2.05
        altered[3]["state"]["position"][0] = 2.05
        self.write_candidate(altered)
        self.assertEqual("PASSED", self.result()["status"])
        altered[2]["state"]["position"][0] = 2.2
        altered[3]["state"]["position"][0] = 2.2
        self.write_candidate(altered)
        self.assertEqual("FAILED", self.result()["status"])

    def test_static_fixture_values_are_exact_and_force_is_zero(self):
        selected = load_fixture("configured-30-r1")
        self.fixture["exact_numeric"] = selected["exact_numeric"] + ["inputs.dt"]
        self.fixture["zero_numeric"] = selected["zero_numeric"]
        rows = json.loads(json.dumps(self.rows))
        rows[1]["payload"] = [{"getFriction": 0.5, "shape": {"getRadius": 0.7071067811865476}}]
        rows[2]["state"] = {"bodies": [{"id": "b1", "force": [0.0, 0.0], "torque": 0.0}]}
        self.write_reference(rows)
        self.write_candidate(rows)
        self.assertEqual("PASSED", self.result()["status"])
        for section, field, value in (("event", "getFriction", 0.6),
                                      ("event", "getRadius", 0.8),
                                      ("state", "force", [0.01, 0.0]),
                                      ("state", "torque", 0.01)):
            with self.subTest(field=field):
                altered = json.loads(json.dumps(rows))
                if section == "state":
                    altered[2]["state"]["bodies"][0][field] = value
                else:
                    target = altered[1]["payload"][0]
                    (target["shape"] if field == "getRadius" else target)[field] = value
                self.write_candidate(altered)
                self.assertEqual("FAILED", self.result()["status"])

    def test_previous_transform_and_wake_snapshot_inherit_primary_limits(self):
        selected = load_fixture("configured-30-r1")
        self.fixture["rules"] = selected["rules"]
        self.fixture["exact_numeric"] = ["inputs.dt", "event.step", "event.order", "state.step",
                                         "instrumented-callback.step", "instrumented-callback.order"]
        body = {"id": "b1", "transform": {"getTranslation": [1.0, 2.0],
                "getRotationAngle": 0.1}, "previousTransform": {
                "getTranslation": [0.9, 2.0], "getRotationAngle": 0.09},
                "velocity": [0.0, 0.0], "angularVelocity": 0.0}
        rows = json.loads(json.dumps(self.rows))
        rows[1]["payload"] = []
        rows[2]["state"] = {"bodies": [body]}
        rows.append({"kind": "instrumented-callback", "step": 1, "order": 0,
                     "event": "before-wake", "values": [{"bodies": [body]}]})
        self.fixture["counts"]["instrumented-callback"] = 1
        self.write_reference(rows)
        altered = json.loads(json.dumps(rows))
        for snapshot in (altered[2]["state"], altered[3]["values"][0]):
            body = snapshot["bodies"][0]
            body["previousTransform"]["getTranslation"][0] += 0.00005
            body["previousTransform"]["getRotationAngle"] += 0.00005
        self.write_candidate(altered)
        self.assertEqual("PASSED", self.result()["status"])
        altered[3]["values"][0]["bodies"][0]["previousTransform"]["getTranslation"][0] = 0.9002
        self.write_candidate(altered)
        self.assertEqual("FAILED", self.result()["status"])

    def test_matrix_getter_uses_component_limits_and_aliases(self):
        selected = load_fixture("configured-30-r1")
        self.fixture["rules"] = selected["rules"]
        self.fixture["check_translation_aliases"] = True
        rows = json.loads(json.dumps(self.rows))
        rows[1]["payload"] = []
        rows[2]["state"] = {"bodies": [{"id": "b1", "transform": {
            "getCost": 1.0, "getSint": 0.0, "getTranslation": [1.0, 2.0],
            "getTranslationX": 1.0, "getTranslationY": 2.0,
            "getValues": [1.0, -0.0, 1.0, 0.0, 1.0, 2.0]}}]}
        self.write_reference(rows)
        altered = json.loads(json.dumps(rows))
        matrix = altered[2]["state"]["bodies"][0]["transform"]
        matrix["getTranslation"] = [1.00005, 2.0]
        matrix["getTranslationX"] = 1.00005
        matrix["getValues"][2] = 1.00005
        self.write_candidate(altered)
        result = self.result()
        self.assertEqual("UNPASSED", result["status"])
        self.assertNotIn("state.state.bodies[].transform.getValues[]", result["unpassed_channels"])
        matrix["getValues"][2] = 1.02
        self.write_candidate(altered)
        self.assertEqual("FAILED", self.result()["status"])

    def test_wake_getter_formula_rejects_changed_subtraction(self):
        selected = load_fixture("configured-30-r1")
        self.fixture["rules"] = selected["rules"]
        self.fixture["derived_rules"] = selected["derived_rules"]
        self.fixture["check_translation_aliases"] = True
        self.fixture["exact_numeric"] = ["inputs.dt", "event.step", "event.order", "state.step",
                                         "instrumented-callback.step", "instrumented-callback.order"]
        body = {"id": "b1", "transform": {"getTranslation": [1.0, 2.0],
                "getTranslationX": 1.0, "getTranslationY": 2.0,
                "getRotationAngle": 0.2}, "previousTransform": {
                "getTranslation": [0.9, 2.0], "getTranslationX": 0.9,
                "getTranslationY": 2.0, "getRotationAngle": 0.1},
                "angularVelocity": 1.0,
                "properties": {"getChangeInPosition": [1.0 - 0.9, 0.0],
                               "getChangeInOrientation": 0.2 - 0.1}}
        rows = json.loads(json.dumps(self.rows))
        rows[1]["payload"] = []
        rows[2]["state"] = {"bodies": []}
        rows.append({"kind": "instrumented-callback", "step": 1, "order": 0,
                     "event": "before-wake", "values": [{"bodies": [body]}]})
        self.fixture["counts"]["instrumented-callback"] = 1
        self.write_reference(rows)
        self.write_candidate(rows)
        self.assertEqual("PASSED", self.result()["status"])
        altered = json.loads(json.dumps(rows))
        altered[3]["values"][0]["bodies"][0]["properties"]["getChangeInPosition"][0] += 0.00001
        self.write_candidate(altered)
        self.assertEqual("FAILED", self.result()["status"])
        altered = json.loads(json.dumps(rows))
        altered[3]["values"][0]["bodies"][0]["properties"]["getChangeInOrientation"] += 0.00001
        self.write_candidate(altered)
        self.assertEqual("FAILED", self.result()["status"])
        altered = json.loads(json.dumps(rows))
        altered[3]["values"][0]["bodies"][0]["properties"]["getChangeInPosition"][0] += 0.00001
        self.write_reference(altered)
        self.assertEqual("FAILED", audit_reference(self.fixture, self.root / "reference.jsonl.gz")["status"])

    def test_inventory_requires_a_reason_for_every_legacy_numeric_path(self):
        classification = classify_reference(self.fixture, self.root / "reference.jsonl.gz",
                                            ["state.state.position[]", "state.state.sum"])
        self.assertEqual(2, classification["legacy_count"])
        self.assertEqual("APPROVED_LIMIT", classification["legacy_paths"]["state.state.position[]"]["status"])
        self.assertEqual("APPROVED_LIMIT", classification["legacy_paths"]["state.state.sum"]["status"])
        with self.assertRaisesRegex(ValueError, "missing legacy path"):
            classify_reference(self.fixture, self.root / "reference.jsonl.gz", ["state.state.absent"])
        with self.assertRaisesRegex(ValueError, "duplicate legacy path"):
            classify_reference(self.fixture, self.root / "reference.jsonl.gz",
                               ["state.state.sum", "state.state.sum"])

    def test_inventory_classifies_sine_and_matrix_aliases(self):
        selected = load_fixture("configured-30-r1")
        self.fixture["rules"] = selected["rules"]
        self.fixture["derived_rules"] = selected["derived_rules"]
        rows = json.loads(json.dumps(self.rows))
        rows[1]["payload"] = []
        rows[2]["state"] = {"bodies": [{"id": "b1", "transform": {
            "getCost": 1.0, "getSint": 0.0, "getRotationAngle": 0.0,
            "getTranslation": [0.0, 0.0], "getTranslationX": 0.0,
            "getTranslationY": 0.0, "getValues": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]}}]}
        self.write_reference(rows)
        paths = ["state.state.bodies[].transform.getSint",
                 "state.state.bodies[].transform.getValues[]"]
        classified = classify_reference(self.fixture, self.root / "reference.jsonl.gz", paths)
        self.assertEqual("DERIVED_FORMULA", classified["legacy_paths"][paths[0]]["status"])
        self.assertEqual("EXACT_ALIAS", classified["legacy_paths"][paths[1]]["status"])

    def test_wake_snapshot_static_fields_keep_exact_identity(self):
        selected = load_fixture("configured-30-r1")
        self.fixture["exact_numeric"] = selected["exact_numeric"]
        rows = json.loads(json.dumps(self.rows))
        rows.append({"kind": "instrumented-callback", "step": 1, "order": 0,
                     "event": "before-wake", "values": [{"bodies": [{"id": "b1",
                     "fixtures": [{"getDensity": 1.0, "shape": {"getRadius": 0.7071067811865476}}],
                     "properties": {"getMass": {"getInertia": 1.0 / 6.0}}}]}]})
        self.fixture["counts"]["instrumented-callback"] = 1
        self.write_reference(rows)
        self.write_candidate(rows)
        self.assertEqual("PASSED", self.result()["status"])
        altered = json.loads(json.dumps(rows))
        altered[-1]["values"][0]["bodies"][0]["properties"]["getMass"]["getInertia"] += 0.00001
        self.write_candidate(altered)
        self.assertEqual("FAILED", self.result()["status"])

    def test_wake_orientation_branch_change_fails_closed(self):
        selected = load_fixture("configured-30-r1")
        self.fixture["rules"] = selected["rules"]
        self.fixture["derived_rules"] = selected["derived_rules"]
        self.fixture["exact_numeric"] = ["inputs.dt", "event.step", "event.order", "state.step",
                                         "instrumented-callback.step", "instrumented-callback.order"]
        self.fixture["check_translation_aliases"] = True
        body = {"id": "b1", "transform": {"getTranslation": [0.0, 0.0],
                "getTranslationX": 0.0, "getTranslationY": 0.0,
                "getRotationAngle": 0.2}, "previousTransform": {
                "getTranslation": [0.0, 0.0], "getTranslationX": 0.0,
                "getTranslationY": 0.0, "getRotationAngle": -0.00004},
                "angularVelocity": 1.0, "properties": {
                "getChangeInPosition": [0.0, 0.0],
                "getChangeInOrientation": (0.2 - (-0.00004 + 2 * math.pi)) + 2 * math.pi}}
        rows = json.loads(json.dumps(self.rows))
        rows[1]["payload"] = []
        rows[2]["state"] = {"bodies": []}
        rows.append({"kind": "instrumented-callback", "step": 1, "order": 0,
                     "event": "before-wake", "values": [{"bodies": [body]}]})
        self.fixture["counts"]["instrumented-callback"] = 1
        self.write_reference(rows)
        altered = json.loads(json.dumps(rows))
        changed = altered[-1]["values"][0]["bodies"][0]
        changed["previousTransform"]["getRotationAngle"] = 0.00004
        changed["properties"]["getChangeInOrientation"] = 0.2 - 0.00004
        self.write_candidate(altered)
        self.assertIn("branch differs", self.result()["reason"])

    def test_stored_sine_requires_norm_and_component_enclosures(self):
        selected = load_fixture("configured-30-r1")
        self.fixture["rules"] = selected["rules"]
        self.fixture["derived_rules"] = selected["derived_rules"]
        rows = json.loads(json.dumps(self.rows))
        rows[1]["payload"] = []
        rows[2]["state"] = {"bodies": [{"id": "b1", "transform": {
            "getCost": 1.0, "getSint": 0.0, "getRotationAngle": 0.0}}]}
        self.write_reference(rows)
        self.write_candidate(rows)
        result = self.result()
        self.assertEqual("PASSED", result["status"])
        self.assertEqual([], result["unpassed_channels"])
        self.assertNotIn("state.state.bodies[].transform.getCost", result["unpassed_channels"])
        altered = json.loads(json.dumps(rows))
        altered[2]["state"]["bodies"][0]["transform"]["getSint"] = 0.00005
        self.write_candidate(altered)
        self.assertEqual("PASSED", self.result()["status"])
        altered = json.loads(json.dumps(rows))
        altered[2]["state"]["bodies"][0]["transform"]["getCost"] = 0.999
        self.write_candidate(altered)
        self.assertEqual("FAILED", self.result()["status"])
        altered = json.loads(json.dumps(rows))
        altered[2]["state"]["bodies"][0]["transform"]["getSint"] = 0.9
        self.write_candidate(altered)
        self.assertEqual("FAILED", self.result()["status"])
        self.assertIn("norm", self.result()["reason"])

    def test_sine_and_matrix_reject_out_of_bound_or_invalid_values(self):
        selected = load_fixture("configured-30-r1")
        self.fixture["rules"] = selected["rules"]
        self.fixture["derived_rules"] = selected["derived_rules"]
        self.fixture["check_translation_aliases"] = True
        rows = json.loads(json.dumps(self.rows))
        rows[1]["payload"] = []
        rows[2]["state"] = {"bodies": [{"id": "b1", "transform": {
            "getCost": 1.0, "getSint": 0.0, "getRotationAngle": 0.0,
            "getTranslation": [1.0, 2.0], "getTranslationX": 1.0,
            "getTranslationY": 2.0, "getValues": [1.0, -0.0, 1.0, 0.0, 1.0, 2.0]}}]}
        self.write_reference(rows)
        self.write_candidate(rows)
        self.assertEqual("PASSED", self.result()["status"])
        for value in (0.001, float("inf"), float("nan")):
            with self.subTest(value=value):
                altered = json.loads(json.dumps(rows))
                transform = altered[2]["state"]["bodies"][0]["transform"]
                transform["getSint"] = value
                transform["getValues"][1] = -value
                transform["getValues"][3] = value
                self.write_candidate(altered)
                self.assertEqual("FAILED", self.result()["status"])
        altered = json.loads(json.dumps(rows))
        altered[2]["state"]["bodies"][0]["transform"]["getValues"][3] = 0.00005
        self.write_candidate(altered)
        self.assertEqual("FAILED", self.result()["status"])
        self.assertIn("matrix getter alias", self.result()["reason"])

    def test_matrix_alias_preserves_signed_zero(self):
        selected = load_fixture("configured-30-r1")
        self.fixture["rules"] = selected["rules"]
        self.fixture["derived_rules"] = selected["derived_rules"]
        self.fixture["exact_numeric"] = selected["exact_numeric"]
        self.fixture["zero_numeric"] = selected["zero_numeric"]
        self.fixture["check_translation_aliases"] = True
        rows = json.loads(json.dumps(self.rows))
        rows[1]["payload"] = []
        rows[2]["state"] = {"bodies": [{"id": "b1", "transform": {
            "getCost": 1.0, "getSint": 0.0, "getRotationAngle": 0.0,
            "getTranslation": [1.0, 2.0],
            "getTranslationX": 1.0, "getTranslationY": 2.0,
            "getValues": [1.0, -0.0, 1.0, 0.0, 1.0, 2.0]}}]}
        self.write_reference(rows)
        self.write_candidate(rows)
        self.assertEqual("PASSED", self.result()["status"])
        altered = json.loads(json.dumps(rows))
        altered[2]["state"]["bodies"][0]["transform"]["getValues"][1] = 0.0
        self.write_candidate(altered)
        self.assertEqual("FAILED", self.result()["status"])
        self.assertIn("matrix getter alias", self.result()["reason"])

    def test_explicit_nominal_cosine_cap_keeps_precedence(self):
        self.fixture["rules"] = [
            {"path": "state.state.bodies[].transform.getCost", "metric": "scalar",
             "absolute": 1e-10, "relative": 0, "unit": "dimensionless"},
            {"path": "state.state.bodies[].transform.getRotationAngle", "metric": "orientation",
             "absolute": 1e-7, "relative": 0, "unit": "rad"}]
        rows = json.loads(json.dumps(self.rows))
        rows[1]["payload"] = []
        rows[2]["state"] = {"bodies": [{"id": "b1", "transform": {
            "getCost": math.cos(0.3), "getRotationAngle": 0.3}}]}
        self.write_reference(rows)
        altered = json.loads(json.dumps(rows))
        altered[2]["state"]["bodies"][0]["transform"] = {
            "getCost": math.cos(0.30000001), "getRotationAngle": 0.30000001}
        self.write_candidate(altered)
        self.assertEqual("FAILED", self.result()["status"])


if __name__ == "__main__":
    unittest.main()
