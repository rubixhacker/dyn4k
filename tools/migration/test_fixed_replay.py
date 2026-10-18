import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fixed_replay import repeatability_difference


SCRIPT = Path(__file__).with_name("fixed_replay.py")


class FixedReplayComparisonTest(unittest.TestCase):
    def compare(self, baseline, candidate):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, rows in (("baseline", baseline), ("candidate", candidate)):
                (root / f"{name}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
            result = subprocess.run([
                sys.executable, str(SCRIPT), "compare", "--baseline", str(root / "baseline.jsonl"),
                "--candidate", str(root / "candidate.jsonl"), "--output", str(root / "comparison.json"),
                "--baseline-sha256", "a" * 64, "--candidate-sha256", "b" * 64,
            ], text=True, capture_output=True)
            report = json.loads((root / "comparison.json").read_text()) if (root / "comparison.json").exists() else None
            return result, report

    def rows(self):
        identity = {"sample_revision": "2c6b318e929baab77e9753ae78a4965eee74a30a",
                    "source_manifest_sha256": "15ce636ac8eec34b24e73bc96270b49a44c94318850050b1e9bc0d930a9c8d58",
                    "power": 0.3, "angle": 0.05, "dt": 1 / 60, "prelude_steps": 120, "steps": 2,
                    "ccd": "ALL", "observation_stride": 1, "cue_velocity": [2.99, 0.15],
                    "jvm_identity_hash_mode": 2, "jvm_identity_hash_probe": 1,
                    "jvm_input_arguments": ["-XX:+UnlockExperimentalVMOptions", "-XX:hashCode=2"]}
        base = [{"kind": "input", "provider": "baseline", "artifact_sha256": "a" * 64,
                 "world_code_source": "file:/work/lib/dyn4j-6.0.0.jar",
                 "java_home": "/jdk", "java_version": "21.0.12.1", **identity},
                {"kind": "step", "step": 0, "body_count": 1, "joint_count": 0,
                 "gravity": [0.0, 0.0], "bodies": [
                    {"i": 0, "x": 0.0, "y": 0.0, "vx": 3.0, "vy": 0.0, "angle": 0.0,
                     "omega": 0.0, "rest": False, "bullet": True, "fixtures": 1,
                     "mass": 1.0, "inertia": 1.0, "linear_damping": 0.8, "angular_damping": 0.8,
                     "identity_hash": 1, "fixture_identity_hashes": [1]}],
                 "ccd_pairs": [], "ccd_candidates": [], "contacts": [], "toi_events": [], "contact_begin": 0, "contact_persist": 0, "contact_end": 0,
                 "toi_calls": 0, "toi_hits": 0, "toi_listener_hits": 0}]
        base[1]["body_count"] = 2
        second_body = json.loads(json.dumps(base[1]["bodies"][0]))
        second_body["i"] = 1
        base[1]["bodies"].append(second_body)
        base.append({**base[1], "step": 1})
        base.append({**base[1], "step": 2, "contact_begin": 1, "toi_hits": 1,
                     "toi_listener_hits": 1,
                     "contacts": [{"kind": "begin", "a": 0, "b": 1, "x": 0.0,
                                   "y": 0.0, "depth": 0.0}],
                     "toi_events": [{"a": 0, "b": 1, "time": 0.5}]})
        base[0]["reset_state"] = json.loads(json.dumps({**base[1], "step": -120}))
        base[0]["prelude_state"] = json.loads(json.dumps({**base[1], "step": -1}))
        base[0]["prelude_pairs"] = [[] for _ in range(120)]
        candidate = json.loads(json.dumps(base))
        candidate[0]["provider"] = "candidate"
        candidate[0]["artifact_sha256"] = "b" * 64
        candidate[0]["world_code_source"] = "file:/work/lib/dyn4k-core-jvm-0.1.0-alpha.1.jar"
        return base, candidate

    def test_matching_fixed_streams_pass(self):
        baseline, candidate = self.rows()
        result, report = self.compare(baseline, candidate)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("PASSED", report["status"])
        self.assertEqual(3, report["compared_observations"])

    def test_changed_cue_action_fails_identity(self):
        baseline, candidate = self.rows()
        candidate[0]["power"] = 0.31
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("input.power", report["first_divergence"]["path"])

    def test_missing_hash_mode_fails_even_when_both_streams_omit_it(self):
        baseline, candidate = self.rows()
        del baseline[0]["jvm_identity_hash_mode"]
        del candidate[0]["jvm_identity_hash_mode"]
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("baseline.input.jvm_identity_hash_mode", report["first_divergence"]["path"])

    def test_changed_hash_mode_fails_even_when_both_claim_same_wrong_mode(self):
        baseline, candidate = self.rows()
        baseline[0]["jvm_identity_hash_mode"] = 3
        candidate[0]["jvm_identity_hash_mode"] = 3
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("baseline.input.jvm_identity_hash_mode", report["first_divergence"]["path"])

    def test_claimed_mode_requires_actual_jvm_argument_and_probe(self):
        baseline, candidate = self.rows()
        baseline[0]["jvm_input_arguments"][-1] = "-XX:hashCode=3"
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("baseline.input.jvm_input_arguments", report["first_divergence"]["path"])
        baseline, candidate = self.rows()
        baseline[0]["jvm_identity_hash_probe"] = 2
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("baseline.input.jvm_identity_hash_probe", report["first_divergence"]["path"])

    def test_loaded_engine_code_source_is_required(self):
        baseline, candidate = self.rows()
        candidate[0]["world_code_source"] = baseline[0]["world_code_source"]
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("candidate.input.world_code_source", report["first_divergence"]["path"])

    def test_reset_state_is_required_and_compared(self):
        baseline, candidate = self.rows()
        del baseline[0]["reset_state"]
        del candidate[0]["reset_state"]
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("baseline.input.reset_state", report["first_divergence"]["path"])
        baseline, candidate = self.rows()
        candidate[0]["reset_state"]["bodies"][0]["x"] = 0.01
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("input.reset_state.bodies[0].x", report["first_divergence"]["path"])

    def test_both_streams_missing_reset_contacts_fail(self):
        baseline, candidate = self.rows()
        for rows in (baseline, candidate):
            del rows[0]["reset_state"]["contacts"]
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("baseline.input.reset_state.contacts", report["first_divergence"]["path"])

    def test_both_streams_missing_prelude_toi_hits_fail(self):
        baseline, candidate = self.rows()
        for rows in (baseline, candidate):
            del rows[0]["prelude_state"]["toi_hits"]
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("baseline.input.prelude_state.toi_hits", report["first_divergence"]["path"])

    def test_both_streams_missing_prelude_toi_events_fail(self):
        baseline, candidate = self.rows()
        for rows in (baseline, candidate):
            del rows[0]["prelude_state"]["toi_events"]
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("baseline.input.prelude_state.toi_events", report["first_divergence"]["path"])

    def test_initial_state_gravity_and_pair_channels_are_required(self):
        for state, field in (("reset_state", "gravity"), ("prelude_state", "ccd_pairs")):
            with self.subTest(state=state, field=field):
                baseline, candidate = self.rows()
                for rows in (baseline, candidate):
                    del rows[0][state][field]
                result, report = self.compare(baseline, candidate)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(f"baseline.input.{state}.{field}", report["first_divergence"]["path"])

    def test_initial_state_event_payloads_are_complete(self):
        for state, field, counter, event in (
            ("reset_state", "contacts", "contact_begin", {"kind": "begin", "a": 0, "b": 1}),
            ("prelude_state", "toi_events", "toi_listener_hits", {"a": 0, "b": 1}),
        ):
            with self.subTest(state=state, field=field):
                baseline, candidate = self.rows()
                for rows in (baseline, candidate):
                    rows[0][state][field] = [event]
                    rows[0][state][counter] = 1
                result, report = self.compare(baseline, candidate)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(f"baseline.input.{state}.{field}", report["first_divergence"]["path"])

    def test_initial_state_event_counters_match_payloads(self):
        for state, counter, channel in (
            ("reset_state", "contact_begin", "contacts"),
            ("prelude_state", "toi_listener_hits", "toi_events"),
        ):
            with self.subTest(state=state):
                baseline, candidate = self.rows()
                for rows in (baseline, candidate):
                    rows[0][state][counter] = 1
                result, report = self.compare(baseline, candidate)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(f"baseline.input.{state}.{channel}", report["first_divergence"]["path"])

    def test_one_sided_initial_state_omission_fails(self):
        for provider, state, field in (
            ("candidate", "reset_state", "gravity"),
            ("baseline", "prelude_state", "toi_hits"),
        ):
            with self.subTest(provider=provider, state=state, field=field):
                baseline, candidate = self.rows()
                rows = baseline if provider == "baseline" else candidate
                del rows[0][state][field]
                result, report = self.compare(baseline, candidate)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(f"{provider}.input.{state}.{field}", report["first_divergence"]["path"])

    def test_prelude_pair_order_is_required_and_compared(self):
        baseline, candidate = self.rows()
        del baseline[0]["prelude_pairs"]
        del candidate[0]["prelude_pairs"]
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("baseline.input.prelude_pairs", report["first_divergence"]["path"])
        baseline, candidate = self.rows()
        baseline[0]["prelude_pairs"][10] = [[0, 0]]
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("input.prelude_pairs[10].length", report["first_divergence"]["path"])
        self.assertEqual("FAILED", report["ordering_identity"]["status"])

    def test_pair_order_differs_before_physics_outcomes(self):
        baseline, candidate = self.rows()
        for rows in (baseline, candidate):
            rows[2]["body_count"] = 3
            rows[2]["bodies"] = json.loads(json.dumps(rows[2]["bodies"]))
            for index in (2,):
                body = json.loads(json.dumps(rows[2]["bodies"][0]))
                body["i"] = index
                rows[2]["bodies"].append(body)
        baseline[2]["ccd_pairs"] = [[0, 1], [0, 2]]
        candidate[2]["ccd_pairs"] = [[0, 2], [0, 1]]
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("step[1].ccd_pairs[0][1]", report["first_divergence"]["path"])

    def test_earlier_outcome_precedes_later_pair_order_difference(self):
        baseline, candidate = self.rows()
        candidate[1]["bodies"][0]["x"] = 0.02
        baseline[3]["ccd_candidates"] = [[0, 0]]
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("step[0].bodies[0].x", report["first_divergence"]["path"])
        self.assertEqual("step[2].ccd_candidates.length", report["ordering_identity"]["first_divergence"]["path"])

    def test_missing_pair_channel_fails_even_if_both_omit_it(self):
        baseline, candidate = self.rows()
        del baseline[1]["ccd_pairs"]
        del candidate[1]["ccd_pairs"]
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("baseline.step[0].ccd_pairs", report["first_divergence"]["path"])

    def test_body_identity_hash_differs_before_physics_outcomes(self):
        baseline, candidate = self.rows()
        candidate[1]["bodies"][0]["identity_hash"] = 2
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("candidate.step[0].bodies[0].identity_hash", report["first_divergence"]["path"])

    def test_changed_cue_angle_fails_identity(self):
        baseline, candidate = self.rows()
        candidate[0]["angle"] = 0.06
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("input.angle", report["first_divergence"]["path"])

    def test_omitted_step_fails_before_outcome_comparison(self):
        baseline, candidate = self.rows()
        del candidate[2]
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("step.sequence", report["first_divergence"]["path"])

    def test_changed_artifact_fails_identity(self):
        baseline, candidate = self.rows()
        candidate[0]["artifact_sha256"] = "c" * 64
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("input.artifact_sha256", report["first_divergence"]["path"])

    def test_changed_body_outcome_fails_finite_metric(self):
        baseline, candidate = self.rows()
        candidate[2]["bodies"][0]["x"] = 0.02
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("step[1].bodies[0].x", report["first_divergence"]["path"])

    def test_missing_contact_channel_fails_even_if_both_omit_it(self):
        baseline, candidate = self.rows()
        for row in baseline[1:] + candidate[1:]:
            del row["contacts"]
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("baseline.step[0].contacts", report["first_divergence"]["path"])

    def test_nonfinite_body_value_fails(self):
        baseline, candidate = self.rows()
        candidate[1]["bodies"][0]["x"] = float("nan")
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("candidate.nonfinite", report["first_divergence"]["path"])

    def test_matching_streams_without_ccd_activity_fail(self):
        baseline, candidate = self.rows()
        for rows in (baseline, candidate):
            rows[-1]["toi_hits"] = 0
            rows[-1]["toi_listener_hits"] = 0
            rows[-1]["toi_events"] = []
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("baseline.ccd_activity", report["first_divergence"]["path"])

    def test_missing_initial_mass_fails_even_if_both_omit_it(self):
        baseline, candidate = self.rows()
        del baseline[1]["bodies"][0]["mass"]
        del candidate[1]["bodies"][0]["mass"]
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("baseline.step[0].bodies[0].mass", report["first_divergence"]["path"])

    def test_repeatability_detects_first_changed_step(self):
        baseline, _ = self.rows()
        repeat = json.loads(json.dumps(baseline))
        repeat[2]["bodies"][0]["x"] = 0.00001
        difference = repeatability_difference(baseline, repeat)
        self.assertEqual("step[1].bodies[0].x", difference["path"])
        self.assertIsNone(repeatability_difference(baseline, baseline))

    def test_missing_toi_event_payload_fails_despite_counter(self):
        baseline, candidate = self.rows()
        baseline[-1]["toi_events"] = []
        candidate[-1]["toi_events"] = []
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("baseline.step[2].toi_events", report["first_divergence"]["path"])

    def test_missing_contact_event_payload_fails_despite_counter(self):
        baseline, candidate = self.rows()
        baseline[-1]["contacts"] = []
        candidate[-1]["contacts"] = []
        result, report = self.compare(baseline, candidate)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("baseline.step[2].contacts", report["first_divergence"]["path"])


if __name__ == "__main__":
    unittest.main()
