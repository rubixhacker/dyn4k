import gzip
import json
import math
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

import baseline_capture
from frozen_weld_pulley import (BOUNDS, certify_observed_math, compare_branches,
                               compare_case, compare_records,
                               policy, verify_baseline_producer,
                               verify_provider_chain, verify_temporal_state)
from receipt import records
from reference_diagnostic import projected_records, reference_records


ARCHIVE = Path("/var/tmp/dyn4k-portable-baseline-247e15eb/baseline-jvm/cases")
CHAIN_ARCHIVE = Path("/var/tmp/dyn4k-portable-baseline-weld-pulley-ab7be1a1")
FROZEN = Path("/tmp/dyn4k-weld-pulley-old-audit-current")
ATTESTATION = Path("/var/home/stewart/dyn4k-evidence/portable-706-review-fix/"
                   "attestations/ab7be1a1-current-verifier.json")


class FrozenWeldPulleySeamTest(unittest.TestCase):
    @unittest.skipUnless(CHAIN_ARCHIVE.is_dir() and FROZEN.is_dir() and
                         ATTESTATION.is_file(), "retained baseline evidence is unavailable")
    def test_public_frozen_consumer_rejects_sidecar_without_raw_archive(self):
        producer = CHAIN_ARCHIVE / "baseline-jvm/cases/P-JINT-Weld-enabled-equal.jsonl"
        reference = FROZEN / "P-JINT-Weld-enabled-equal-0.jsonl.gz"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            root.mkdir()
            for name in ("verified.json", "result.json"):
                (root / name).write_bytes((CHAIN_ARCHIVE / name).read_bytes())
            attestation = Path(directory) / "attestation.json"
            forged = json.loads(ATTESTATION.read_text())
            forged["archive_root"] = str(root.resolve())
            forged["verifier_source_sha256"] = baseline_capture.verifier_source_sha256()
            attestation.write_text(json.dumps(forged))
            result = compare_case("weld-enabled-equal", reference, producer,
                                  reference_producer=producer, baseline_root=root,
                                  baseline_attestation=attestation)
            self.assertEqual(result["status"], "UNPASSED_SOURCE_BINDING")
            self.assertIn("raw archive", result["reason"])

    def test_all_adopted_paths_have_a_rule_without_fallback(self):
        selected = policy()
        self.assertEqual(len(selected["state_event_paths"]), 89)
        self.assertEqual(len(selected["later_header_paths"]), 82)
        self.assertEqual(len(selected["header_extra_paths"]), 48)
        self.assertEqual({entry["rule"] for entry in selected["header_extra_paths"].values()},
                         {"EX", "AL", "MAT", "CP", "CA"})

    @unittest.skipUnless(ARCHIVE.is_dir() and FROZEN.is_dir(),
                         "pinned Weld/Pulley archive is unavailable")
    def test_old_archive_cannot_qualify_without_complete_chain(self):
        result = compare_case("pulley-preparation-1",
            FROZEN / "P-JINT-Pulley-slack-transition-preparation-1.jsonl.gz",
            ARCHIVE / "P-JINT-Pulley-slack-transition-preparation-1.jsonl",
            FROZEN / "P-JINT-Pulley-slack-transition-preparation-0.jsonl.gz",
            ARCHIVE / "P-JINT-Pulley-slack-transition-preparation-0.jsonl")
        self.assertEqual(result["status"], "UNPASSED_CHAINING")

    def test_exact_and_bounded_numeric_semantics_at_public_stream(self):
        fixture = "pulley-preparation-0"
        left = [{"kind": "event", "step": 1, "payload": [{
            "velocity1": [0.0, 0.0], "constraint": {"getTangentSpeed": 0.0}}]}]
        right = json.loads(json.dumps(left))
        right[0]["payload"][0]["constraint"]["getTangentSpeed"] = -0.0
        right[0]["payload"][0]["velocity1"][0] = 0.0005
        self.assertEqual(compare_records(fixture, left, right)["status"], "PASSED")
        right[0]["payload"][0]["velocity1"][0] = 0.0011
        self.assertEqual(compare_records(fixture, left, right)["status"], "FAILED")
        right[0]["payload"][0]["velocity1"][0] = 0.0
        right[0]["payload"][0]["constraint"]["getTangentSpeed"] = 5e-324
        self.assertEqual(compare_records(fixture, left, right)["status"], "FAILED")

    def test_every_scalar_limit_inside_at_and_beyond_at_public_stream(self):
        for rule, (limit, _) in BOUNDS.items():
            with self.subTest(rule=rule):
                selected = policy()
                name = "rotationIncrementSum" if rule == "A" else "scalar"
                path = f"event.payload[].{name}"
                selected["state_event_paths"][path] = {"mask": "YYYY", "rule": rule}
                base = 1.0 if rule in ("I", "MIX", "STIFF") else 0.0
                left = [{"kind": "event", "payload": [{name: base}]}]
                at = base + limit
                while Fraction.from_float(at) - Fraction.from_float(base) > \
                        Fraction.from_float(limit):
                    at = math.nextafter(at, base)
                beyond = math.nextafter(at, math.inf)
                while Fraction.from_float(beyond) - Fraction.from_float(base) <= \
                        Fraction.from_float(limit):
                    beyond = math.nextafter(beyond, math.inf)
                with patch("frozen_weld_pulley.policy", return_value=selected):
                    for value in (base + limit * 0.5, at):
                        right = [{"kind": "event", "payload": [{name: value}]}]
                        self.assertEqual(compare_records("pulley-preparation-0", left, right)
                                         ["status"], "PASSED")
                    right = [{"kind": "event", "payload": [{name: beyond}]}]
                    self.assertEqual(compare_records("pulley-preparation-0", left, right)
                                     ["status"], "FAILED")

    def test_case_rule_coverage_rejects_a_silently_unvisited_path(self):
        selected = policy()
        selected["state_event_paths"]["event.payload[].missingScalar"] = {
            "mask": "·Y··", "rule": "V"}
        row = [{"kind": "event", "payload": [{"scalar": 0.0}]}]
        with patch("frozen_weld_pulley.policy", return_value=selected):
            result = compare_records("pulley-preparation-0", row, row,
                                     require_coverage=True)
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("unvisited", result["reason"])

    def test_literal_shape_and_zero_formula_branches_are_exact(self):
        for shape, field, value in (("org.dyn4j.geometry.Rectangle", "getArea", 10.0),
                                    ("org.dyn4j.geometry.Circle", "getRadius", 0.5)):
            left = [{"kind": "event", "payload": [{"shape": {"type": shape,
                     field: value}}]}]
            right = json.loads(json.dumps(left))
            right[0]["payload"][0]["shape"][field] = math.nextafter(value, math.inf)
            self.assertEqual(compare_records("pulley-preparation-0", left, right)["status"],
                             "FAILED")
        for rule, value in (("MIX", 5e-324), ("STIFF", 5e-324)):
            selected = policy()
            selected["state_event_paths"]["event.payload[].scalar"] = {
                "mask": "·Y··", "rule": rule}
            left = [{"kind": "event", "payload": [{"scalar": 0.0}]}]
            right = [{"kind": "event", "payload": [{"scalar": value}]}]
            with patch("frozen_weld_pulley.policy", return_value=selected):
                self.assertEqual(compare_records("pulley-preparation-0", left, right)["status"],
                                 "FAILED")
        selected = policy()
        selected["state_event_paths"]["event.payload[].scalar"] = {
            "mask": "·Y··", "rule": "I"}
        with patch("frozen_weld_pulley.policy", return_value=selected):
            left = [{"kind": "event", "payload": [{"scalar": 0.0002}]}]
            right = [{"kind": "event", "payload": [{"scalar": -0.0002}]}]
            self.assertEqual(compare_records("pulley-preparation-0", left, right)["status"],
                             "FAILED")

    @unittest.skipUnless(FROZEN.is_dir(), "frozen Weld/Pulley capture is unavailable")
    def test_static_body_cannot_move_inside_a_dynamic_translation_bound(self):
        reference = next(row for row in reference_records(
            FROZEN / "P-JINT-Pulley-slack-transition-preparation-0.jsonl.gz")
            if row["kind"] == "state")
        changed = json.loads(json.dumps(reference))
        body = changed["state"]["bodies"][0]
        body["transform"]["getTranslationX"] += 5e-5
        body["transform"]["getTranslation"][0] += 5e-5
        body["transform"]["getValues"][2] += 5e-5
        body["worldCenter"][0] += 5e-5
        body["fixedOriginPosition"][0] += 5e-5
        self.assertEqual(compare_records("pulley-preparation-0", [reference],
                                         [changed])["status"], "FAILED")

    def test_frozen_nonzero_z_premise_is_not_a_positive_control(self):
        row = {"kind": "event", "payload": [{"separation": {
            "getDistance": 1.8575666560670945e-9}}]}
        result = compare_records("pulley-preparation-1", [row], [row])
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("separation type", result["reason"])

    def test_adopted_toi_output_accepts_epsilon_endpoint_only(self):
        from frozen_weld_pulley import PINNED_TOI_DISTANCE_EPSILON
        def row(distance):
            separation = {"type": "org.dyn4j.collision.narrowphase.Separation",
                          "getDistance": distance, "getNormal": [1.0, 0.0],
                          "getPoint1": [0.0, 0.0], "getPoint2": [distance, 0.0]}
            return {"kind": "event", "payload": [{"separation": separation}]}
        at = row(PINNED_TOI_DISTANCE_EPSILON)
        self.assertEqual(compare_records("pulley-preparation-1", [at], [at])
                         ["status"], "PASSED")
        signed = json.loads(json.dumps(at))
        signed["payload"][0]["separation"]["getPoint1"] = [-0.0, 0]
        self.assertEqual(compare_records("pulley-preparation-1", [at], [signed])
                         ["status"], "PASSED")
        beyond = row(math.nextafter(PINNED_TOI_DISTANCE_EPSILON, math.inf))
        self.assertEqual(compare_records("pulley-preparation-1", [beyond], [beyond])
                         ["status"], "FAILED")

    @unittest.skipUnless(FROZEN.is_dir(), "frozen Weld/Pulley capture is unavailable")
    def test_populated_toi_separation_has_adopted_output_formula(self):
        source = FROZEN / "P-JINT-Pulley-slack-transition-preparation-1.jsonl.gz"
        event = next(row for row in reference_records(source)
                     if row.get("kind") == "event" and row.get("step") == 2 and
                     "TimeOfImpact" in row.get("listener", "") and
                     any(isinstance(value, dict) and "separation" in value
                         for value in row.get("payload", [])))
        self.assertEqual(compare_records("pulley-preparation-1", [event], [event])
                         ["status"], "PASSED")
        def shifted(offset):
            moved = json.loads(json.dumps(event))
            separation = next(value["separation"] for value in moved["payload"]
                              if isinstance(value, dict) and "separation" in value)
            separation["getPoint1"][0] += offset
            separation["getPoint2"][0] += offset
            delta = [second - first for first, second in zip(
                separation["getPoint1"], separation["getPoint2"])]
            distance = math.sqrt(delta[0] * delta[0] + delta[1] * delta[1])
            separation["getDistance"] = distance
            separation["getNormal"] = [component * (1.0 / distance)
                                       for component in delta]
            return moved
        near = shifted(5e-5)
        self.assertEqual(compare_records("pulley-preparation-1", [event], [near])
                         ["status"], "PASSED")
        at = shifted(math.nextafter(1e-4, 0.0))
        self.assertEqual(compare_records("pulley-preparation-1", [event], [at])
                         ["status"], "PASSED")
        beyond = shifted(1.1e-4)
        self.assertEqual(compare_records("pulley-preparation-1", [event], [beyond])
                         ["status"], "FAILED")
        self.assertIn("numeric limit exceeded", compare_records(
            "pulley-preparation-1", [event], [beyond])["reason"])
        changed = json.loads(json.dumps(event))
        separation = next(value["separation"] for value in changed["payload"]
                          if isinstance(value, dict) and "separation" in value)
        separation["getDistance"] += 1.1e-4
        self.assertEqual(compare_records("pulley-preparation-1", [event], [changed])
                         ["status"], "FAILED")
        changed = json.loads(json.dumps(event))
        separation = next(value["separation"] for value in changed["payload"]
                          if isinstance(value, dict) and "separation" in value)
        separation["getPoint1"][0] += 1.1e-4
        self.assertEqual(compare_records("pulley-preparation-1", [event], [changed])
                         ["status"], "FAILED")
        changed = json.loads(json.dumps(event))
        separation = next(value["separation"] for value in changed["payload"]
                          if isinstance(value, dict) and "separation" in value)
        separation["getPoint1"] = [0.0, 0.0]
        separation["getPoint2"] = [0.0, 0.0]
        separation["getDistance"] = 0.0
        separation["getNormal"] = [0.0, 0.0]
        self.assertEqual(compare_records("pulley-preparation-1", [event], [changed])
                         ["status"], "FAILED")

    @unittest.skipUnless(FROZEN.is_dir(), "frozen Weld/Pulley capture is unavailable")
    def test_immutable_toi_callback_formula_ulps_epsilon_branch_and_limits(self):
        from frozen_weld_pulley import PINNED_TOI_DISTANCE_EPSILON
        source = FROZEN / "P-JINT-Pulley-slack-transition-preparation-1.jsonl.gz"
        frozen = next(row for row in reference_records(source)
                      if row.get("kind") == "event" and row.get("step") == 2 and
                      any(isinstance(value, dict) and "separation" in value
                          for value in row.get("payload", [])))
        def separation(row):
            return next(value["separation"] for value in row["payload"]
                        if isinstance(value, dict) and "separation" in value)
        def compare(changed):
            return compare_records("pulley-preparation-1", [frozen], [changed])["status"]
        self.assertEqual(compare(frozen), "PASSED")
        original = separation(frozen)
        for distance, expected in ((math.nextafter(PINNED_TOI_DISTANCE_EPSILON, 0.0),
                                    "PASSED"),
                                   (PINNED_TOI_DISTANCE_EPSILON, "PASSED"),
                                   (math.nextafter(PINNED_TOI_DISTANCE_EPSILON,
                                                   math.inf), "FAILED")):
            with self.subTest(immutable_epsilon=distance):
                changed = json.loads(json.dumps(frozen))
                value = separation(changed)
                value["getPoint2"] = [-0.9960937319426065, -0.5000048043598172]
                value["getDistance"] = distance
                delta = [b - a for a, b in zip(value["getPoint1"], value["getPoint2"])]
                value["getNormal"] = [component * (1.0 / distance)
                                      for component in delta]
                self.assertEqual(compare(changed), expected)
        for count, expected in ((4, "PASSED"), (8, "PASSED"), (9, "FAILED")):
            with self.subTest(formula="distance", ulps=count):
                changed = json.loads(json.dumps(frozen))
                separation(changed)["getDistance"] += count * math.ulp(
                    original["getDistance"])
                self.assertEqual(compare(changed), expected)
            with self.subTest(formula="normal", ulps=count):
                changed = json.loads(json.dumps(frozen))
                separation(changed)["getNormal"][0] += count * math.ulp(1.0)
                self.assertEqual(compare(changed), expected)
        for factor, expected in ((0.5, "PASSED"), (1.01, "FAILED")):
            with self.subTest(epsilon=factor):
                changed = json.loads(json.dumps(frozen))
                value = separation(changed)
                value["getPoint2"][1] = value["getPoint1"][1] - \
                    factor * PINNED_TOI_DISTANCE_EPSILON
                delta = [b - a for a, b in zip(value["getPoint1"], value["getPoint2"])]
                value["getDistance"] = math.sqrt(sum(component ** 2 for component in delta))
                value["getNormal"] = [component * (1.0 / value["getDistance"])
                                      for component in delta]
                self.assertEqual(compare(changed), expected)
        changed = json.loads(json.dumps(frozen))
        separation(changed)["getDistance"] = 0.0
        self.assertEqual(compare(changed), "FAILED")
        self.assertIn("output branch", compare_records("pulley-preparation-1",
            [frozen], [changed])["reason"])
        changed = json.loads(json.dumps(frozen))
        for point in ("getPoint1", "getPoint2"):
            separation(changed)[point][0] += 5e-5
        self.assertEqual(compare(changed), "PASSED")
        for point in ("getPoint1", "getPoint2"):
            separation(changed)[point][0] += 6e-5
        self.assertEqual(compare(changed), "FAILED")
        prior = None
        first_outside = None
        for ulps in range(1, 2600):
            changed = json.loads(json.dumps(frozen))
            value = separation(changed)
            value["getPoint2"][0] = original["getPoint2"][0] + \
                ulps * math.ulp(original["getPoint2"][0])
            delta = [b - a for a, b in zip(value["getPoint1"], value["getPoint2"])]
            value["getDistance"] = math.sqrt(sum(component ** 2 for component in delta))
            value["getNormal"] = [component * (1.0 / value["getDistance"])
                                  for component in delta]
            result = compare_records("pulley-preparation-1", [frozen], [changed])
            if result["status"] == "FAILED":
                first_outside = result
                break
            prior = result
        self.assertIsNotNone(prior)
        self.assertIsNotNone(first_outside)
        self.assertEqual(prior["status"], "PASSED")
        self.assertIn("direction angle", first_outside["reason"])
        changed = json.loads(json.dumps(frozen))
        separation(changed)["getPoint1"][0] = 16.0
        self.assertEqual(compare(changed), "FAILED")

    def test_scale_envelope_at_and_beyond_is_independent_of_frozen_point_limit(self):
        from frozen_weld_pulley import PINNED_TOI_DISTANCE_EPSILON
        def row(x):
            distance = PINNED_TOI_DISTANCE_EPSILON / 2
            return {"kind": "event", "payload": [{"separation": {
                "type": "org.dyn4j.collision.narrowphase.Separation",
                "getDistance": distance, "getNormal": [0.0, -1.0],
                "getPoint1": [x, 0.0], "getPoint2": [x, -distance]}}]}
        inside = row(15.0)
        self.assertEqual(compare_records("pulley-preparation-1", [inside], [inside])
                         ["status"], "PASSED")
        at = row(16.0)
        self.assertEqual(compare_records("pulley-preparation-1", [at], [at])["status"],
                         "PASSED")
        beyond = row(math.nextafter(16.0, math.inf))
        self.assertEqual(compare_records("pulley-preparation-1", [beyond], [beyond])
                         ["status"], "FAILED")

    @unittest.skipUnless(FROZEN.is_dir(), "frozen Weld/Pulley capture is unavailable")
    def test_toi_separation_formula_branch_and_placeholder_adversaries(self):
        source = FROZEN / "P-JINT-Pulley-slack-transition-preparation-1.jsonl.gz"
        populated = next(row for row in reference_records(source)
                         if row.get("kind") == "event" and any(
                            isinstance(value, dict) and "separation" in value
                            for value in row.get("payload", [])))
        def separation(row):
            return next(value["separation"] for value in row["payload"]
                        if isinstance(value, dict) and "separation" in value)
        for field, value in (("getDistance", 1e-7), ("getNormal", [0.0, -1.0]),
                             ("getPoint1", [0.0, 0.0]), ("getDistance", float("nan"))):
            with self.subTest(field=field, value=value):
                changed = json.loads(json.dumps(populated))
                separation(changed)[field] = value
                self.assertEqual(compare_records("pulley-preparation-1", [populated],
                                                 [changed])["status"], "FAILED")
        changed = json.loads(json.dumps(populated))
        del separation(changed)["getPoint2"]
        self.assertEqual(compare_records("pulley-preparation-1", [populated],
                                         [changed])["status"], "FAILED")

        main = FROZEN / "P-JINT-Pulley-slack-transition-0.jsonl.gz"
        placeholder = next(row for row in reference_records(main)
                           if row.get("kind") == "event" and any(
                               isinstance(value, dict) and "separation" in value
                               for value in row.get("payload", [])))
        self.assertEqual(compare_records("pulley-slack-transition", [placeholder],
                                         [placeholder])["status"], "PASSED")
        changed = json.loads(json.dumps(placeholder))
        separation(changed)["getPoint1"][0] = 5e-324
        self.assertEqual(compare_records("pulley-slack-transition", [placeholder],
                                         [changed])["status"], "FAILED")
        changed = json.loads(json.dumps(placeholder))
        separation(changed)["getNormal"][0] = False
        self.assertEqual(compare_records("pulley-slack-transition", [placeholder],
                                         [changed])["status"], "FAILED")

    @unittest.skipUnless(FROZEN.is_dir(), "frozen Weld/Pulley capture is unavailable")
    def test_later_header_checks_unnamed_field_and_own_provider_formulas(self):
        source = FROZEN / "P-JINT-Pulley-slack-transition-preparation-1.jsonl.gz"
        header = next(reference_records(source))
        body = header["state"]["bodies"][2]
        changed = json.loads(json.dumps(header))
        changed["state"]["bodies"][2]["properties"]["getAngularDamping"] = 5e-324
        self.assertEqual(compare_records("pulley-preparation-1", [header], [changed])["status"],
                         "FAILED")
        changed = json.loads(json.dumps(header))
        changed["state"]["bodies"][2]["transform"]["getTranslationX"] += 5e-5
        self.assertEqual(compare_records("pulley-preparation-1", [header], [changed])["status"],
                         "FAILED")
        changed = json.loads(json.dumps(header))
        changed["state"]["bodies"][2]["properties"]["getChangeInPosition"][0] = 1e-5
        self.assertEqual(compare_records("pulley-preparation-1", [header], [changed])["status"],
                         "FAILED")
        changed = json.loads(json.dumps(header))
        changed["state"]["bodies"][2]["properties"]["unknownNumber"] = 0.0
        self.assertEqual(compare_records("pulley-preparation-1", [header], [changed])["status"],
                         "FAILED")

    @unittest.skipUnless(FROZEN.is_dir(), "frozen Weld/Pulley capture is unavailable")
    def test_computed_matrix_zero_sign_and_integer_index_schema(self):
        header = next(reference_records(
            FROZEN / "P-JINT-Pulley-slack-transition-preparation-1.jsonl.gz"))
        changed = json.loads(json.dumps(header))
        changed["state"]["bodies"][0]["transform"]["getValues"][1] = 0.0
        changed["state"]["bodies"][0]["properties"]["getTransform"]["getValues"][1] = 0.0
        self.assertEqual(compare_records("pulley-preparation-1", [header], [changed])["status"],
                         "PASSED")
        changed = json.loads(json.dumps(header))
        changed["steps"] = 2.0
        self.assertEqual(compare_records("pulley-preparation-1", [header], [changed])["status"],
                         "FAILED")

    def test_all_declared_discrete_numeric_getters_keep_integer_tokens(self):
        names = ("getSpringMode", "getPositionConstraintSolverIterations",
                 "getVelocityConstraintSolverIterations",
                 "getMaxDetectIterations", "getMaxDistanceIterations",
                 "getMaxRaycastIterations", "getMaxIterations")
        for name in names:
            with self.subTest(name=name):
                left = [{"kind": "event", "payload": [{name: 4}]}]
                right = [{"kind": "event", "payload": [{name: 4.0}]}]
                self.assertEqual(compare_records("pulley-preparation-0", left, right)
                                 ["status"], "FAILED")
        left = [{"kind": "inputs", "world": {"tree": {"getHeight": 4}}}]
        right = [{"kind": "inputs", "world": {"tree": {"getHeight": 4.0}}}]
        self.assertEqual(compare_records("pulley-preparation-0", left, right)["status"],
                         "FAILED")

    @unittest.skipUnless(FROZEN.is_dir(), "frozen Weld/Pulley capture is unavailable")
    def test_later_header_requires_the_complete_82_path_catalog(self):
        header = next(reference_records(
            FROZEN / "P-JINT-Pulley-slack-transition-preparation-1.jsonl.gz"))
        selected = policy()
        selected["later_header_paths"].pop(
            "inputs.state.bodies[].properties.getAngularDamping")
        with patch("frozen_weld_pulley.policy", return_value=selected):
            result = compare_records("pulley-preparation-1", [header], [header])
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("catalog", result["reason"])

    def test_pre_step_pulley_branch_is_strict_even_within_length_limit(self):
        row = {"kind": "state", "step": 201, "frozenBranch": {
            "currentLength": 1.49995, "targetLength": 1.5,
            "length1": 0.75, "length2": 0.74995, "ratio": 1.0,
            "anchor1": [0.0, 0.25], "anchor2": [1.0, 0.25005],
            "pulleyAnchor1": [0.0, 1.0], "pulleyAnchor2": [1.0, 1.0],
            "slackEnabled": True, "overLength": False}}
        changed = json.loads(json.dumps(row))
        changed["frozenBranch"]["currentLength"] = 1.50005
        changed["frozenBranch"]["length2"] = 0.75005
        changed["frozenBranch"]["anchor2"][1] = 0.24995
        changed["frozenBranch"]["overLength"] = True
        self.assertEqual(compare_branches("pulley-slack-transition", [row], [changed])["status"],
                         "FAILED")
        self.assertEqual(compare_branches("pulley-slack-transition", [row], [row])["status"],
                         "PASSED")
        at = json.loads(json.dumps(row))
        at["frozenBranch"]["currentLength"] = 1.5
        at["frozenBranch"]["length2"] = 0.75
        at["frozenBranch"]["anchor2"][1] = 0.25
        self.assertEqual(compare_branches("pulley-slack-transition", [at], [at])["status"],
                         "PASSED")
        at["step"] = 1
        at["frozenBranch"]["slackEnabled"] = False
        at["frozenBranch"]["overLength"] = True
        self.assertEqual(compare_branches("pulley-slack-transition", [at], [at])["status"],
                         "PASSED")

    def test_direction_magnitude_angle_and_tangent_boundary_controls(self):
        left = [{"kind": "event", "payload": [{"constraint": {
            "getNormal": [1.0, 0.0], "getTangent": [0.0, -1.0]}}]}]
        near = json.loads(json.dumps(left))
        near[0]["payload"][0]["constraint"]["getNormal"] = [
            math.cos(0.00005), math.sin(0.00005)]
        near[0]["payload"][0]["constraint"]["getTangent"] = [
            math.sin(0.00005), -math.cos(0.00005)]
        self.assertEqual(compare_records("pulley-preparation-0", left, near)["status"],
                         "PASSED")
        far = json.loads(json.dumps(near))
        far[0]["payload"][0]["constraint"]["getNormal"] = [
            math.cos(0.0002), math.sin(0.0002)]
        far[0]["payload"][0]["constraint"]["getTangent"] = [
            math.sin(0.0002), -math.cos(0.0002)]
        self.assertEqual(compare_records("pulley-preparation-0", left, far)["status"],
                         "FAILED")
        flipped = json.loads(json.dumps(left))
        flipped[0]["payload"][0]["constraint"]["getNormal"] = [-1.0, 0.0]
        self.assertEqual(compare_records("pulley-preparation-0", left, flipped)["status"],
                         "FAILED")
        skewed = json.loads(json.dumps(left))
        skewed[0]["payload"][0]["constraint"]["getTangent"] = [2e-6, -1.0]
        self.assertEqual(compare_records("pulley-preparation-0", left, skewed)["status"],
                         "FAILED")

    @unittest.skipUnless(FROZEN.is_dir(), "frozen Weld/Pulley capture is unavailable")
    def test_complete_post_action_header_must_match_actual_predecessor(self):
        header = next(reference_records(
            FROZEN / "P-JINT-Pulley-slack-transition-preparation-1.jsonl.gz"))
        before = json.loads(json.dumps(header["state"]))
        before["bodies"][2]["velocity"] = [0.0, 0.0]
        before["bodies"][2]["properties"]["getLinearVelocity"] = [0.0, 0.0]
        compact = json.loads(json.dumps(before))
        for body in compact["bodies"]:
            body.pop("fixtures")
            body.pop("properties")
        prior = [{"kind": "state", "frozenState": compact},
                 {"kind": "case-end", "frozenEndState": before}]
        next_row = {"kind": "inputs", "frozenInput": header,
                    "frozenChain": {"previousCaseId":
                        "P-JINT-Pulley-slack-transition-preparation-0",
                        "operation": "body2.setLinearVelocity(0,10) before source step2",
                        "previousEnd": before, "preAction": before,
                        "postAction": header["state"]}}
        self.assertEqual(verify_provider_chain("pulley-preparation-1", [next_row], prior)["status"],
                         "PASSED")
        forged = json.loads(json.dumps(next_row))
        forged["frozenInput"]["state"]["bodies"][2]["transform"]["getTranslationX"] += 5e-5
        with self.assertRaisesRegex(ValueError, "header differs"):
            verify_provider_chain("pulley-preparation-1", [forged], prior)
        forged["frozenChain"]["postAction"] = forged["frozenInput"]["state"]
        with self.assertRaisesRegex(ValueError, "exact source action"):
            verify_provider_chain("pulley-preparation-1", [forged], prior)

    @unittest.skipUnless(ARCHIVE.is_dir(), "pinned baseline archive is unavailable")
    def test_chain_rejects_a_predecessor_outside_pinned_producer_receipt(self):
        root = ARCHIVE.parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            duplicate = Path(temporary)
            verified = json.loads((root / "verified.json").read_text())
            verified["case_sha256"]["P-JINT-Pulley-slack-transition-preparation-0"] = "0" * 64
            (duplicate / "verified.json").write_text(json.dumps(verified))
            (duplicate / "dyn4j-6.0.0.jar").symlink_to(root / "dyn4j-6.0.0.jar")
            (duplicate / "baseline-jvm").mkdir()
            (duplicate / "baseline-jvm/cases").symlink_to(ARCHIVE, target_is_directory=True)
            with patch("baseline_capture.verify_attestation",
                       return_value={"method_processes_verified": 15}):
                with self.assertRaisesRegex(ValueError, "predecessor case hash"):
                    verify_baseline_producer(duplicate, "pulley-preparation-1",
                                             duplicate / "external-attestation.json")

    @unittest.skipUnless(ARCHIVE.is_dir(), "pinned baseline archive is unavailable")
    def test_historical_seal_without_current_attestation_is_unpassed(self):
        with self.assertRaisesRegex(ValueError, "attestation is absent"):
            verify_baseline_producer(ARCHIVE.parents[1], "weld-enabled-equal")

    @unittest.skipUnless(CHAIN_ARCHIVE.is_dir() and FROZEN.is_dir(),
                         "pinned Weld baseline producer is unavailable")
    def test_frozen_projection_cannot_pass_on_python_math_surrogate(self):
        reference = FROZEN / "P-JINT-Weld-enabled-equal-0.jsonl.gz"
        producer = CHAIN_ARCHIVE / "baseline-jvm/cases/P-JINT-Weld-enabled-equal.jsonl"
        with patch("frozen_weld_pulley.verify_baseline_producer",
                   return_value={"case_sha256": "diagnostic"}):
            result = compare_case("weld-enabled-equal", reference, producer,
                                  reference_producer=producer,
                                  baseline_root=CHAIN_ARCHIVE,
                                  baseline_attestation="diagnostic")
        self.assertEqual(result["status"], "UNPASSED_TARGET_MATH_EVIDENCE")
        self.assertEqual(result["surrogate_math"]["reference"]["surrogate_status"],
                         "CONSISTENT")
        self.assertEqual(result["qualification"], "UNPASSED")

    @unittest.skipUnless(ARCHIVE.is_dir(), "pinned baseline archive is unavailable")
    def test_target_anchor_formula_requires_same_provider_geometry(self):
        rows = list(records(ARCHIVE /
            "P-JINT-Pulley-slack-transition-preparation-0.jsonl"))
        self.assertEqual(certify_observed_math("pulley-preparation-0", rows)["status"],
                         "UNPASSED_TARGET_MATH_EVIDENCE")
        changed = json.loads(json.dumps(rows))
        state = next(row for row in changed if row["kind"] == "state")
        state["frozenState"]["joints"][0]["getAnchor1"][0] += 1e-5
        result = certify_observed_math("pulley-preparation-0", changed)
        self.assertEqual(result["status"], "UNPASSED_PREMISE")
        self.assertIn("anchor", result["reason"])

    @unittest.skipUnless(ARCHIVE.is_dir(), "pinned baseline archive is unavailable")
    def test_temporal_previous_transform_includes_step_201_translation(self):
        rows = list(records(ARCHIVE / "P-JINT-Pulley-slack-transition-main.jsonl"))
        self.assertEqual(verify_temporal_state("pulley-slack-transition", rows)["status"],
                         "PASSED")
        changed = json.loads(json.dumps(rows))
        step = next(row for row in changed if row["kind"] == "state" and row["step"] == 201)
        previous = step["frozenState"]["bodies"][2]["previousTransform"]
        previous["getTranslationY"] += 1e-5
        previous["getTranslation"][1] += 1e-5
        previous["getValues"][5] += 1e-5
        self.assertEqual(verify_temporal_state("pulley-slack-transition", changed)["status"],
                         "FAILED")

    def test_event_action_placeholder_nonfinite_and_empty_controls(self):
        baseline = [{"kind": "event", "step": 2, "order": 0,
                     "method": "preSolve", "payload": [{"constraint": {
                         "getNormal": [0.0, 0.0]}}]},
                    {"kind": "action", "step": 201, "order": 0,
                     "description": "body2.setLinearVelocity(0,10)"}]
        self.assertEqual(compare_records("pulley-preparation-1", baseline, baseline)["status"],
                         "PASSED")
        for changed in (baseline[:-1], baseline + [baseline[-1]],
                        [{**baseline[0], "method": "postSolve"}, baseline[1]],
                        [baseline[0], {**baseline[1], "description": "different"}]):
            self.assertEqual(compare_records("pulley-preparation-1", baseline, changed)["status"],
                             "FAILED")
        changed = json.loads(json.dumps(baseline))
        changed[0]["payload"][0]["constraint"]["getNormal"] = [1.0, 0.0]
        self.assertEqual(compare_records("pulley-preparation-1", baseline, changed)["status"],
                         "FAILED")
        changed = json.loads(json.dumps(baseline))
        changed[0]["payload"][0]["constraint"]["getNormal"][0] = math.nan
        self.assertEqual(compare_records("pulley-preparation-1", baseline, changed)["status"],
                         "FAILED")
        self.assertEqual(compare_records("pulley-preparation-1", [], [])["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
