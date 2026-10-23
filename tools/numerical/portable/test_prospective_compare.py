import hashlib
import json
import math
import os
import struct
import tempfile
import unittest
from copy import deepcopy
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from prospective_compare import (compare_case, verify_baseline_manifest,
                                 verify_baseline_bytes, verify_reference_case,
                                 load_policy_catalog, verify_policy_catalog,
                                 reference_path_inventory, verify_reference_inventory,
                                 compare_policy_case, verify_candidate_identity)
from prospective_compare import verify_arithmetic_captures, verify_candidate_inventory
from prospective_compare import verify_numeric_probe, compare_host
from receipt import digest


class ProspectiveComparisonTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.reference = self.root / "reference.jsonl"
        self.candidate = self.root / "candidate.jsonl"
        self.case = {"id": "one", "steps": 1}
        self.rows = [
            {"kind": "inputs", "id": "one", "input": {"signedZero": -0.0}},
            {"kind": "event", "id": "one", "step": 1, "order": 0,
             "name": "step.begin", "payload": 1.0},
            {"kind": "event", "id": "one", "step": 1, "order": 1,
             "name": "step.end", "payload": 1.0},
            {"kind": "state", "id": "one", "step": 1, "order": 2,
             "state": {"bodies": [{"id": "b0", "position": [1.0, 0.0]}]}},
            {"kind": "case-end", "id": "one", "steps": 1, "events": 2},
        ]

    def compare(self, candidate=None, reference=None):
        self.reference.write_text("".join(json.dumps(row) + "\n"
                                              for row in (self.rows if reference is None else reference)))
        self.candidate.write_text("".join(json.dumps(row) + "\n"
                                              for row in (self.rows if candidate is None else candidate)))
        return compare_case(self.reference, self.candidate, self.case)

    def test_exact_diagnostic_and_numeric_difference_stays_unpassed(self):
        exact = self.compare()
        self.assertEqual(exact["status"], "EXACT_DIAGNOSTIC")
        self.assertEqual(exact["records"], 5)
        changed = json.loads(json.dumps(self.rows))
        changed[3]["state"]["bodies"][0]["position"][0] = 1.0001
        result = self.compare(changed)
        self.assertEqual(result["status"], "UNPASSED_NUMERICAL_POLICY")
        self.assertEqual(result["different_numeric_values"], 1)

    def test_input_signed_zero_event_order_and_missing_records_fail(self):
        changed = json.loads(json.dumps(self.rows))
        changed[0]["input"]["signedZero"] = 0.0
        input_result = self.compare(changed)
        self.assertEqual(input_result["status"], "FAILED_INPUT")
        self.assertEqual(input_result["input_differences"][0]["path"],
                         "inputs.input.signedZero")
        changed = json.loads(json.dumps(self.rows))
        changed[3]["state"]["bodies"][0]["position"][1] = -0.0
        self.assertEqual(self.compare(changed)["status"], "FAILED_SIGNED_ZERO")
        changed = json.loads(json.dumps(self.rows))
        changed[1], changed[2] = changed[2], changed[1]
        self.assertEqual(self.compare(changed)["status"], "FAILED_STRUCTURE")
        self.assertEqual(self.compare(self.rows[:-1])["status"], "FAILED_COVERAGE")

    def test_nonfinite_and_empty_case_cannot_pass(self):
        changed = json.loads(json.dumps(self.rows))
        changed[3]["state"]["bodies"][0]["position"][0] = {"nonfinite": "Infinity"}
        result = self.compare(changed)
        self.assertEqual(result["status"], "FAILED_NONFINITE")
        self.assertEqual(result["failed_step"], 1)
        self.assertEqual(self.compare([], [])["status"], "FAILED_COVERAGE")

    def test_manifest_rejects_stale_reference_bytes_and_missing_case(self):
        case = self.root / "one.jsonl"
        case.write_text("reference\n")
        manifest = {"status": "CAPTURED_WITH_FAILED_ANGLE_PHYSICAL",
                    "baseline_jar_sha256": "fixed", "fixture_source_sha256": "fixture",
                    "case_sha256": {"one": digest(case)},
                    "inventory": {"cases": 1, "states": 1}}
        verify_baseline_manifest(manifest, {"one"}, "fixed", "fixture")
        case.write_text("stale\n")
        with self.assertRaisesRegex(Exception, "hash differs"):
            verify_reference_case(case, manifest["case_sha256"]["one"])
        with self.assertRaisesRegex(Exception, "case identity"):
            verify_baseline_manifest(manifest, {"one", "two"}, "fixed", "fixture")
        with self.assertRaisesRegex(Exception, "JAR"):
            verify_baseline_manifest(manifest, {"one"}, "changed", "fixture")

    def test_archive_bytes_must_match_verified_jar_and_trace(self):
        jar = self.root / "dyn4j-6.0.0.jar"
        trace = self.root / "baseline-jvm/trace.jsonl"
        trace.parent.mkdir()
        jar.write_bytes(b"jar")
        trace.write_text("trace\n")
        manifest = {"baseline_jar_sha256": digest(jar), "trace_sha256": digest(trace)}
        verify_baseline_bytes(self.root, manifest)
        trace.write_text("stale\n")
        with self.assertRaisesRegex(Exception, "trace hash"):
            verify_baseline_bytes(self.root, manifest)

    def test_policy_catalog_covers_every_prospective_case_and_path(self):
        from cases import declared_cases
        from orthogonality import orthogonality_ulps, source_rotation_cap
        catalog = load_policy_catalog()
        cases = declared_cases()
        frozen = {case["id"] for case in cases if case["require_frozen_projection"]}
        manifest = self.policy_manifest(catalog, frozen)
        verify_policy_catalog(catalog, manifest, cases, frozen)
        self.assertEqual(catalog["orthogonality_policy"], "fixed-32-ulps/1")
        self.assertEqual(catalog["conditional_orthogonality_policy"],
                         "source-derived-u-n/1")
        self.assertEqual(len(catalog["cases"]), 318)
        self.assertEqual(len(catalog["rotation_caps"]), 318)
        self.assertEqual({cap: list(catalog["rotation_caps"].values()).count(cap)
                          for cap in (1, 5, 7, 9, 11)},
                         {1: 1, 5: 140, 7: 92, 9: 61, 11: 24})
        self.assertTrue(all(catalog["rotation_caps"][case["id"]] == source_rotation_cap(case)
                            for case in cases if case["id"] in catalog["cases"]))
        self.assertEqual([(n, orthogonality_ulps(n)) for n in
                          (0, 1, 2, 5, 150, 300, 600, 1200, 1500, 3000,
                           4200, 5400, 6000, 6600)],
                         [(0, 2), (1, 9), (2, 16), (5, 37), (150, 1063),
                          (300, 2123), (600, 4245), (1200, 8487), (1500, 10609),
                          (3000, 21215), (4200, 29700), (5400, 38186),
                          (6000, 42428), (6600, 46671)])
        self.assertEqual(catalog["baseline_trace_sha256"],
                         "5d0a8c37f3cc20a55aad0765c66cb46389264538a1cca887919b85fbd3307801")
        self.assertEqual(catalog["baseline_fixture_source_sha256"],
                         "dd104a7e018b9d0bd77c9af14e929699d68f29fa4ac8179a5bd7d98bdc87d9ce")
        self.assertTrue(all(catalog["paths"][index]["rule"]
                            for schema in catalog["path_sets"] for index in schema))

    def test_complete_manifest_rebind_accepts_current_and_rejects_stale_bindings(self):
        from cases import declared_cases
        current_path = os.environ.get("DYN4K_PROSPECTIVE_CURRENT_MANIFEST")
        historical_path = os.environ.get("DYN4K_PROSPECTIVE_HISTORICAL_MANIFEST")
        if current_path is None and historical_path is None:
            self.skipTest("set both verified-manifest paths for the archive control")
        self.assertIsNotNone(current_path)
        self.assertIsNotNone(historical_path)
        current = json.loads(Path(current_path).read_text())
        historical = json.loads(Path(historical_path).read_text())
        catalog = load_policy_catalog()
        cases = declared_cases()
        frozen = {case["id"] for case in cases if case["require_frozen_projection"]}
        self.assertEqual(len(frozen), 14)
        self.assertTrue({
            "P-JINT-Weld-enabled-equal",
            "P-JINT-Pulley-slack-transition-preparation-0",
            "P-JINT-Pulley-slack-transition-preparation-1",
            "P-JINT-Pulley-slack-transition-main",
        } <= frozen)
        self.assertFalse(frozen & set(catalog["cases"]))

        self.assertEqual(len(current["case_sha256"]), 332)
        self.assertEqual(set(current["case_sha256"]), set(historical["case_sha256"]))
        changed = {case_id for case_id in current["case_sha256"]
                   if current["case_sha256"][case_id] != historical["case_sha256"][case_id]}
        self.assertEqual(changed, set())
        self.assertEqual(changed & set(catalog["cases"]), set())
        self.assertEqual(current["trace_sha256"], historical["trace_sha256"])
        self.assertEqual(current["baseline_source_revision"],
                         historical["baseline_source_revision"])
        self.assertEqual(current["baseline_jar_sha256"], historical["baseline_jar_sha256"])
        self.assertEqual(historical["fixture_source_sha256"],
                         "6c12edda1bde1f1f8556ea7c8dadc4543d69a1c4f4e6f9c64ffe38d47cbf7d3d")
        self.assertEqual(current["fixture_source_sha256"],
                         "dd104a7e018b9d0bd77c9af14e929699d68f29fa4ac8179a5bd7d98bdc87d9ce")
        self.assertEqual({case_id: current["case_sha256"][case_id]
                          for case_id in catalog["cases"]},
                         {case_id: historical["case_sha256"][case_id]
                          for case_id in catalog["cases"]})
        verify_policy_catalog(catalog, current, cases, frozen)

        with self.assertRaisesRegex(Exception, "baseline identity"):
            verify_policy_catalog(catalog, historical, cases, frozen)
        changed_case = deepcopy(current)
        case_id = next(iter(catalog["cases"]))
        changed_case["case_sha256"][case_id] = "0" * 64
        with self.assertRaisesRegex(Exception, "case binding"):
            verify_policy_catalog(catalog, changed_case, cases, frozen)
        for field, reason in (("trace_sha256", "baseline trace"),
                              ("fixture_source_sha256", "baseline identity")):
            stale = deepcopy(current)
            stale[field] = "0" * 64
            with self.assertRaisesRegex(Exception, reason):
                verify_policy_catalog(catalog, stale, cases, frozen)

    def test_policy_catalog_rejects_missing_case_path_and_stale_baseline(self):
        from cases import declared_cases
        catalog = load_policy_catalog()
        cases = declared_cases()
        frozen = {case["id"] for case in cases if case["require_frozen_projection"]}
        manifest = self.policy_manifest(catalog, frozen)
        altered = json.loads(json.dumps(catalog))
        altered["cases"].pop(next(iter(altered["cases"])))
        with self.assertRaisesRegex(Exception, "case identity"):
            verify_policy_catalog(altered, manifest, cases, frozen)
        altered = json.loads(json.dumps(catalog))
        altered["path_sets"][altered["cases"][next(iter(altered["cases"]))]["path_set"]] = []
        with self.assertRaisesRegex(Exception, "path set"):
            verify_policy_catalog(altered, manifest, cases, frozen)
        altered = json.loads(json.dumps(catalog))
        altered["baseline_trace_sha256"] = "0" * 64
        with self.assertRaisesRegex(Exception, "baseline trace"):
            verify_policy_catalog(altered, manifest, cases, frozen)
        for field, message in (("baseline_source_revision", "source"),
                               ("baseline_jar_sha256", "identity"),
                               ("baseline_fixture_source_sha256", "identity")):
            altered = json.loads(json.dumps(catalog))
            altered[field] = "0" * 64
            with self.assertRaisesRegex(Exception, message):
                verify_policy_catalog(altered, manifest, cases, frozen)
        altered = json.loads(json.dumps(catalog))
        altered["cases"][next(iter(altered["cases"]))]["sha256"] = "0" * 64
        with self.assertRaisesRegex(Exception, "case binding"):
            verify_policy_catalog(altered, manifest, cases, frozen)
        altered = json.loads(json.dumps(catalog))
        altered["paths"][0]["rule"] = "bounded_scalar"
        with self.assertRaisesRegex(Exception, "unclassified"):
            verify_policy_catalog(altered, manifest, cases, frozen)
        altered = json.loads(json.dumps(catalog))
        altered["rule_proposals"]["unexpected"] = {"kind": "exact"}
        with self.assertRaisesRegex(Exception, "rule set"):
            verify_policy_catalog(altered, manifest, cases, frozen)
        altered = json.loads(json.dumps(catalog))
        altered["rule_proposals"]["bounded_position"]["limit_m"] *= 2
        with self.assertRaisesRegex(Exception, "adopted rule"):
            verify_policy_catalog(altered, manifest, cases, frozen)
        altered = json.loads(json.dumps(catalog))
        altered["paths"][0]["rule"] = "exact_input"
        with self.assertRaisesRegex(Exception, "adopted path"):
            verify_policy_catalog(altered, manifest, cases, frozen)
        altered = json.loads(json.dumps(catalog))
        altered["path_sets"].append(altered["path_sets"][0])
        with self.assertRaisesRegex(Exception, "unreferenced"):
            verify_policy_catalog(altered, manifest, cases, frozen)
        altered = json.loads(json.dumps(catalog))
        altered["qualification"] = "PASSED"
        with self.assertRaisesRegex(Exception, "qualification"):
            verify_policy_catalog(altered, manifest, cases, frozen)
        for mutate in (lambda value: value.pop("motion-forces-60"),
                       lambda value: value.update({"motion-forces-60": 5}),
                       lambda value: value.update({"motion-forces-60": True})):
            altered = deepcopy(catalog)
            mutate(altered["rotation_caps"])
            with self.assertRaisesRegex(Exception, "rotation cap"):
                verify_policy_catalog(altered, manifest, cases, frozen)
        altered = deepcopy(catalog)
        altered["decision"] = altered["conditional_decision"]
        with self.assertRaisesRegex(Exception, "adoption"):
            verify_policy_catalog(altered, manifest, cases, frozen)

    def test_reference_path_inventory_rejects_an_added_channel(self):
        self.reference.write_text(''.join(json.dumps(row) + "\n" for row in self.rows))
        observed = reference_path_inventory(self.reference)
        names = sorted(observed)
        catalog = {"cases": {"one": {"sha256": digest(self.reference), "path_set": 0}},
                   "paths": [{"path": name, "types": observed[name], "rule": "exact"}
                             for name in names],
                   "path_sets": [list(range(len(names)))]}
        verify_reference_inventory(self.reference, "one", catalog)
        catalog["paths"].append({"path": "state.unexpected", "types": ["float"],
                                 "rule": "exact"})
        catalog["path_sets"][0].append(len(names))
        with self.assertRaisesRegex(Exception, "path set"):
            verify_reference_inventory(self.reference, "one", catalog)

    def test_approved_position_bound_is_inclusive_and_over_bound_fails(self):
        rows = [
            {"kind": "inputs", "id": "one", "family": "joints-limits-motors",
             "profile": "default", "hz": 60, "steps": 1,
             "dt": 1 / 60, "input": {"signedZero": -0.0},
             "setup": {"bodies": [{"id": "b0", "mass": 1.0, "inertia": 1.0}],
                       "joints": []}},
            {"kind": "event", "id": "one", "step": 1, "order": 0,
             "name": "step.begin", "payload": 1 / 60},
            {"kind": "state", "id": "one", "step": 1, "order": 1,
             "state": {"bodies": [{"id": "b0", "position": [0.0, 0.0]}],
                       "joints": []}},
            {"kind": "case-end", "id": "one", "steps": 1, "events": 1},
        ]
        catalog = self.small_policy(rows, {"state.state.bodies[].position[]": "bounded_position",
                                           "event.step.begin.payload": "exact_step"})
        case = {"id": "one", "family": "joints-limits-motors", "profile": "default", "hz": 60,
                "steps": 1, "input": {"signedZero": -0.0}}
        self.reference.write_text(''.join(json.dumps(row) + "\n" for row in rows))

        def compare_at(value):
            candidate = json.loads(json.dumps(rows))
            candidate[2]["state"]["bodies"][0]["position"][0] = value
            self.candidate.write_text(''.join(json.dumps(row) + "\n" for row in candidate))
            return compare_policy_case(self.reference, self.candidate, case, catalog)

        self.assertEqual(compare_at(0.0)["status"], "PASSED_NUMERICAL_POLICY")
        self.assertEqual(compare_at(5e-6)["status"], "PASSED_NUMERICAL_POLICY")
        self.assertEqual(compare_at(5.000001e-6)["status"], "FAILED_NUMERICAL_POLICY")

    def test_candidate_identity_rejects_stale_source_artifact_runtime_and_receipt(self):
        artifact = self.root / "target.jar"
        runtime = self.root / "java"
        artifact.write_bytes(b"artifact")
        runtime.write_bytes(b"runtime")
        artifacts = {"target": artifact}
        runtime_proof = {"host": "jvm", "executable": str(runtime),
                         "executable_sha256": digest(runtime), "version": "test",
                         "method_executions": 15}
        publication = {"candidate_commit": "commit", "source_sha256": "source",
                       "artifact_sha256": {"target": digest(artifact)}}
        receipt = {"schema": "portable-numerical-receipt/1",
                   "candidate_commit": "commit", "source_sha256": "source",
                   "artifact_sha256": {"target": digest(artifact)},
                   "artifact_paths": {"target": str(artifact)}, "runtime": runtime_proof}
        verify_candidate_identity(receipt, publication, "commit", "source",
                                  artifacts, runtime_proof)
        for field, value in (("source_sha256", "other"), ("artifact_sha256", {}),
                             ("runtime", {}), ("schema", "wrong")):
            changed = json.loads(json.dumps(receipt))
            changed[field] = value
            with self.assertRaises(Exception):
                verify_candidate_identity(changed, publication, "commit", "source",
                                          artifacts, runtime_proof)
        runtime.write_bytes(b"different runtime")
        with self.assertRaisesRegex(Exception, "runtime"):
            verify_candidate_identity(receipt, publication, "commit", "source",
                                      artifacts, runtime_proof)

    def test_candidate_inventory_rejects_extra_case_producer_and_receipt(self):
        lane = self.root / "jvm"
        cases = lane / "cases"
        cases.mkdir(parents=True)
        (cases / "one.jsonl").write_text("case\n")
        (lane / "receipt.json").write_text("{}\n")
        verify_candidate_inventory(lane, {"one"}, {"jvm", "linux-x64"})
        (cases / "extra.jsonl").write_text("extra\n")
        with self.assertRaisesRegex(Exception, "case file"):
            verify_candidate_inventory(lane, {"one"}, {"jvm", "linux-x64"})
        (cases / "extra.jsonl").unlink()
        (lane / "receipt-copy.json").write_text("{}\n")
        with self.assertRaisesRegex(Exception, "receipt"):
            verify_candidate_inventory(lane, {"one"}, {"jvm", "linux-x64"})
        (lane / "receipt-copy.json").unlink()
        (lane / "numeric-probe-receipt.json").write_text(
            json.dumps({"schema": "portable-binary64-probe-receipt/1"}))
        verify_candidate_inventory(lane, {"one"}, {"jvm", "linux-x64"})
        (lane / "numeric-probe-copy-receipt.json").write_text("{}\n")
        with self.assertRaisesRegex(Exception, "receipt"):
            verify_candidate_inventory(lane, {"one"}, {"jvm", "linux-x64"})
        (lane / "numeric-probe-copy-receipt.json").unlink()
        rogue = self.root / "unexpected"
        rogue.mkdir()
        (rogue / "receipt.json").write_text("{}\n")
        with self.assertRaisesRegex(Exception, "producer"):
            verify_candidate_inventory(lane, {"one"}, {"jvm", "linux-x64"})

    def test_compare_host_admits_declared_absent_receipts_during_capture(self):
        from run import HOST_TASKS, other_lane_status

        lane = self.root / "candidate" / "jvm"
        (lane / "cases").mkdir(parents=True)
        (lane / "cases" / "one.jsonl").write_text("case\n")
        (lane / "receipt.json").write_text("{}\n")
        baseline = self.root / "baseline"
        baseline.mkdir()
        (baseline / "verified.json").write_text("{}\n")
        attestation = self.root / "attestation.json"
        attestation.write_text("{}\n")
        outer = lane.parent / "android-device"
        outer.mkdir()
        status, reason = other_lane_status(outer.name)
        receipt = {"host": outer.name, "status": status, "reason": reason,
                   "candidate_commit": "commit", "source_sha256": "source",
                   "expected_cases": 1, "executed_cases": 0, "skipped": 0,
                   "qualification": "UNPASSED"}
        (outer / "receipt.json").write_text(json.dumps(receipt))
        sibling = lane.parent / "jvm8"
        sibling.mkdir()
        (sibling / "receipt.json").write_text(json.dumps({
            **receipt, "host": sibling.name, "reason":
            "Host task was not selected for this invocation"}))
        captured = lane.parent / "node-js"
        (captured / "cases").mkdir(parents=True)
        (captured / "cases" / "one.jsonl").write_text("captured case\n")
        (captured / "trace.jsonl").write_text("captured trace\n")
        (captured / "receipt.json").write_text(json.dumps({
            "schema": "portable-numerical-receipt/1",
            "candidate_commit": "commit", "source_sha256": "source"}))

        class InventoryAccepted(Exception):
            pass

        with patch("baseline_capture.verify_attestation", return_value={}), \
                patch("prospective_compare.declared_cases", return_value=[{"id": "one"}]), \
                patch("run.clean_identity", return_value=("commit", "source")), \
                patch("prospective_compare.verify_baseline_manifest",
                      side_effect=InventoryAccepted):
            with self.assertRaises(InventoryAccepted):
                compare_host(baseline, lane, set(), attestation)

        verify_candidate_inventory(lane, {"one"}, HOST_TASKS, "commit", "source")
        captured_receipt = captured / "receipt.json"
        forged = json.loads(captured_receipt.read_text())
        forged["status"] = "PASSED"
        captured_receipt.write_text(json.dumps(forged))
        with self.assertRaises(Exception):
            verify_candidate_inventory(lane, {"one"}, HOST_TASKS, "commit", "source")
        del forged["status"]
        captured_receipt.write_text(json.dumps(forged))
        trace = captured / "trace.jsonl"
        trace.unlink()
        trace.symlink_to(lane / "cases" / "one.jsonl")
        with self.assertRaises(Exception):
            verify_candidate_inventory(lane, {"one"}, HOST_TASKS, "commit", "source")

    def test_numeric_sidecar_directory_and_receipt_are_coupled(self):
        lane = self.root / "jvm"
        (lane / "cases").mkdir(parents=True)
        (lane / "cases" / "one.jsonl").write_text("case\n")
        (lane / "receipt.json").write_text("{}\n")
        receipt = lane / "numeric-probe-receipt.json"
        sidecar = lane / "numeric-probe"

        sidecar.mkdir()
        (sidecar / "undeclared.bin").write_bytes(b"raw")
        with self.assertRaisesRegex(Exception, "numeric.*probe|sidecar"):
            verify_candidate_inventory(lane, {"one"}, {"jvm"})
        with self.assertRaisesRegex(Exception, "numeric.*probe|sidecar"):
            verify_numeric_probe(lane, "commit", "source", "trace", {}, {})
        receipt.write_text(json.dumps({"schema": "portable-binary64-probe-receipt/1"}))
        with self.assertRaisesRegex(Exception, "numeric.*probe|sidecar"):
            verify_candidate_inventory(lane, {"one"}, {"jvm"})
        receipt.write_text(json.dumps({"schema": "portable-binary64-probe-receipt/2",
                                       "files": {}}))
        with self.assertRaisesRegex(Exception, "numeric.*probe|sidecar"):
            verify_candidate_inventory(lane, {"one"}, {"jvm"})
        (sidecar / "undeclared.bin").unlink()
        verify_candidate_inventory(lane, {"one"}, {"jvm"})
        (sidecar / "linked.bin").symlink_to(lane / "receipt.json")
        with self.assertRaisesRegex(Exception, "numeric.*probe|sidecar"):
            verify_candidate_inventory(lane, {"one"}, {"jvm"})
        (sidecar / "linked.bin").unlink()
        receipt.write_text(json.dumps({"schema": "portable-binary64-probe-receipt/1"}))
        with self.assertRaisesRegex(Exception, "numeric.*probe|sidecar"):
            verify_candidate_inventory(lane, {"one"}, {"jvm"})
        receipt.write_text(json.dumps({"schema": "portable-binary64-probe-receipt/2",
                                       "files": {}}))
        sidecar.rmdir()
        with self.assertRaisesRegex(Exception, "numeric.*probe|sidecar"):
            verify_candidate_inventory(lane, {"one"}, {"jvm"})
        sidecar.write_bytes(b"raw")
        with self.assertRaisesRegex(Exception, "numeric.*probe|sidecar"):
            verify_candidate_inventory(lane, {"one"}, {"jvm"})
        sidecar.unlink()
        sidecar.symlink_to(lane / "cases", target_is_directory=True)
        with self.assertRaisesRegex(Exception, "numeric.*probe|sidecar"):
            verify_candidate_inventory(lane, {"one"}, {"jvm"})
        sidecar.unlink()
        receipt.write_text(json.dumps({"schema": "unknown"}))
        with self.assertRaisesRegex(Exception, "numeric.*probe|sidecar"):
            verify_candidate_inventory(lane, {"one"}, {"jvm"})

    def test_declared_sibling_receipt_requires_its_raw_directory(self):
        lane = self.root / "linux-x64"
        (lane / "cases").mkdir(parents=True)
        (lane / "cases" / "one.jsonl").write_text("case\n")
        (lane / "receipt.json").write_text("{}\n")
        sibling = self.root / "jvm"
        sibling.mkdir()
        (sibling / "cases").mkdir()
        (sibling / "cases" / "one.jsonl").write_text("case\n")
        (sibling / "trace.jsonl").write_text("trace\n")
        (sibling / "receipt.json").write_text(json.dumps({
            "schema": "portable-numerical-receipt/1",
            "candidate_commit": "commit", "source_sha256": "source"}))
        receipt = sibling / "numeric-probe-receipt.json"
        receipt.write_text(json.dumps({"schema": "portable-binary64-probe-receipt/1"}))
        verify_candidate_inventory(lane, {"one"}, {"linux-x64", "jvm"},
                                   "commit", "source")
        receipt.write_text(json.dumps({"schema": "portable-binary64-probe-receipt/2",
                                       "files": {}}))
        with self.assertRaisesRegex(Exception, "numeric.*probe|sidecar"):
            verify_candidate_inventory(lane, {"one"}, {"linux-x64", "jvm"},
                                       "commit", "source")

    def test_numeric_sidecar_inventory_rejects_extra_empty_directory(self):
        lane = self.root / "jvm"
        (lane / "cases").mkdir(parents=True)
        (lane / "cases" / "one.jsonl").write_text("case\n")
        (lane / "receipt.json").write_text("{}\n")
        (lane / "numeric-probe-receipt.json").write_text(json.dumps({
            "schema": "portable-binary64-probe-receipt/2", "files": {}}))
        sidecar = lane / "numeric-probe"
        sidecar.mkdir()
        verify_candidate_inventory(lane, {"one"}, {"jvm"})
        (sidecar / "extra").mkdir()
        with self.assertRaisesRegex(Exception, "numeric.*probe|sidecar"):
            verify_candidate_inventory(lane, {"one"}, {"jvm"})
        (sidecar / "extra").rmdir()
        process = sidecar / "process"
        process.mkdir()
        trace = process / "trace.1"
        trace.write_bytes(b"trace")
        (lane / "numeric-probe-receipt.json").write_text(json.dumps({
            "schema": "portable-binary64-probe-receipt/2",
            "files": {"process/trace.1": {"size": 5, "sha256": digest(trace)}}}))
        verify_candidate_inventory(lane, {"one"}, {"jvm"})
        (process / "extra").mkdir()
        with self.assertRaisesRegex(Exception, "numeric.*probe|sidecar"):
            verify_candidate_inventory(lane, {"one"}, {"jvm"})

    def test_declared_absent_receipts_reject_forgery_and_extra_evidence(self):
        from run import HOST_TASKS, other_lane_status

        lane = self.root / "jvm"
        (lane / "cases").mkdir(parents=True)
        (lane / "cases" / "one.jsonl").write_text("case\n")
        (lane / "receipt.json").write_text("{}\n")
        outer = self.root / "linux-arm64"
        outer.mkdir()
        status, reason = other_lane_status(outer.name)
        receipt = {"host": outer.name, "status": status, "reason": reason,
                   "candidate_commit": "commit", "source_sha256": "source",
                   "expected_cases": 1, "executed_cases": 0, "skipped": 0,
                   "qualification": "UNPASSED"}
        path = outer / "receipt.json"
        path.write_text(json.dumps(receipt))

        def check():
            verify_candidate_inventory(lane, {"one"}, HOST_TASKS, "commit", "source")

        check()
        with self.assertRaises(Exception):
            verify_candidate_inventory(lane, {"one"}, HOST_TASKS)
        path.write_text(json.dumps({**receipt, "candidate_commit": None,
                                    "source_sha256": None}))
        with self.assertRaises(Exception):
            verify_candidate_inventory(lane, {"one"}, HOST_TASKS)
        path.write_text(json.dumps(receipt))
        for change in ({"host": "unknown"}, {"status": "PASSED"},
                       {"status": "NOT_RUN"}, {"reason": "unbound"},
                       {"candidate_commit": "stale"}, {"source_sha256": "stale"},
                       {"expected_cases": 0}, {"expected_cases": True},
                       {"executed_cases": 1}, {"skipped": 1},
                       {"qualification": "PASSED"},
                       {"schema": "portable-numerical-receipt/1"}):
            with self.subTest(change=change):
                path.write_text(json.dumps({**receipt, **change}))
                with self.assertRaises(Exception):
                    check()
        path.write_text(json.dumps(receipt))
        partial = dict(receipt)
        del partial["reason"]
        path.write_text(json.dumps(partial))
        with self.assertRaises(Exception):
            check()
        path.write_text(json.dumps(receipt))
        for name in ("cases", "numeric-probe-receipt.json", "trace.jsonl"):
            with self.subTest(extra=name):
                extra = outer / name
                if name == "cases":
                    extra.mkdir()
                else:
                    extra.write_text("forged\n")
                with self.assertRaises(Exception):
                    check()
                if name == "cases":
                    extra.rmdir()
                else:
                    extra.unlink()
        rogue = self.root / "unknown"
        rogue.mkdir()
        (rogue / "receipt.json").write_text(json.dumps(receipt))
        with self.assertRaises(Exception):
            check()
        (rogue / "receipt.json").unlink()
        rogue.rmdir()
        rogue.write_text("unknown producer\n")
        with self.assertRaises(Exception):
            check()
        rogue.unlink()
        path.unlink()
        path.symlink_to(lane / "receipt.json")
        with self.assertRaises(Exception):
            check()

    def test_numeric_sidecar_inventory_limits_members_during_walk(self):
        from numeric_producer import MAX_MEMBERS

        lane = self.root / "jvm"
        (lane / "cases").mkdir(parents=True)
        (lane / "cases" / "one.jsonl").write_text("case\n")
        (lane / "receipt.json").write_text("{}\n")
        (lane / "numeric-probe-receipt.json").write_text(json.dumps({
            "schema": "portable-binary64-probe-receipt/2", "files": {}}))
        sidecar = lane / "numeric-probe"
        sidecar.mkdir()
        for index in range(MAX_MEMBERS + 1):
            (sidecar / f"extra-{index}").touch()
        original_iterdir = Path.iterdir

        def bounded_iterdir(path):
            if path == sidecar:
                raise AssertionError("materialized directory entries")
            return original_iterdir(path)

        with patch.object(Path, "rglob", side_effect=AssertionError("unbounded walk")), \
                patch.object(Path, "iterdir", bounded_iterdir):
            with self.assertRaisesRegex(Exception, "numeric.*budget"):
                verify_candidate_inventory(lane, {"one"}, {"jvm"})

    def numeric_probe_fixture(self):
        lane = self.root / "jvm"
        (lane / "xml").mkdir(parents=True)
        executable = self.root / "java"
        artifact = self.root / "target.jar"
        executable.write_bytes(b"target runtime")
        artifact.write_bytes(b"target artifact")
        runtime = {"host": "jvm", "executable": str(executable),
                   "executable_sha256": digest(executable), "version": "test",
                   "method_executions": 15}
        proof = {"schema": "portable-binary64-probe/1",
                 "ulpOneBits": "3cb0000000000000",
                 "nextUpOneBits": "3ff0000000000001",
                 "nextDownOneBits": "3fefffffffffffff",
                 "negativeZeroBits": "8000000000000000",
                 "positiveZeroBits": "0000000000000000",
                 "negativeZeroReciprocalBits": "fff0000000000000",
                 "ulpMillionBits": "3de0000000000000",
                 "boundaryOriginZeroGapBits": "3d71980000000000",
                 "boundaryPositiveMillionGapBits": "0000000000000000",
                 "boundaryNegativeMillionGapBits": "0000000000000000",
                 "maximumFinite": True, "positiveInfinityFinite": False,
                 "nanFinite": False}
        payload = json.dumps(proof, separators=(",", ":"), sort_keys=True)
        method = "geometryCollisionBoundaryAndScale"
        xml = lane / "xml" / f"{method}.xml"
        xml.write_text('<testsuite tests="1" skipped="0" failures="0" errors="0">'
                       '<testcase classname="portable.PortableMatrixTest" name="' + method + '"/>'
                       '<system-out><![CDATA[NUMERICAL_PROBE_JSON ' + payload + '\n'
                       'NUMERICAL_JSON {"kind":"inputs","id":"geometry-boundary-s1-o3-d3",'
                       '"input":{"signedZero":-0.0}}\n'
                       ']]></system-out></testsuite>')
        log = lane / f"gradle-{method}.log"
        log.write_text("Starting process target runtime\n")
        receipt = {"schema": "portable-binary64-probe-receipt/1",
                   "candidate_commit": "commit", "source_sha256": "source",
                   "trace_sha256": "trace",
                   "artifact_sha256": {"target": digest(artifact)},
                   "runtime": runtime, "method": method,
                   "xml_sha256": digest(xml), "gradle_log_sha256": digest(log),
                   "probe": proof}
        path = lane / "numeric-probe-receipt.json"
        path.write_text(json.dumps(receipt))
        return lane, receipt, runtime, {"target": artifact}, xml, log

    def test_target_comparator_requires_exact_runtime_probe_before_case_pass(self):
        lane, _, runtime, artifacts, _, _ = self.numeric_probe_fixture()
        self.assertTrue(verify_numeric_probe(lane, "commit", "source", "trace",
                                             artifacts, runtime))
        (lane / "numeric-probe-receipt.json").unlink()
        self.assertFalse(verify_numeric_probe(lane, "commit", "source", "trace",
                                              artifacts, runtime))

    def test_compare_host_keeps_case_unpassed_without_bound_probe_producer(self):
        lane, probe_receipt, runtime, artifacts, _, _ = self.numeric_probe_fixture()
        probe_receipt["runtime"] = {
            **runtime, "dependency_sha256": digest(artifacts["target"]),
            "method_process_sha256": hashlib.sha256(json.dumps(
                [runtime] * 15, sort_keys=True).encode()).hexdigest()}
        (lane / "numeric-probe-receipt.json").write_text(json.dumps(probe_receipt))
        baseline = self.root / "baseline"
        baseline.mkdir()
        (baseline / "verified.json").write_text(json.dumps({
            "baseline_jar_sha256": "jar", "trace_sha256": "trace",
            "fixture_source_sha256": "fixture", "case_sha256": {"one": "case"}}))
        sidecar = self.root / "external-attestation.json"
        sidecar.write_text("{}")
        (lane / "receipt.json").write_text(json.dumps({
            "artifact_sha256": {"target": digest(artifacts["target"])},
            "trace_sha256": "trace"}))
        (self.root / "publication.log").write_text("published\n")
        (self.root / "publication.json").write_text(json.dumps({
            "candidate_commit": "commit", "source_sha256": "source",
            "publication_log_sha256": digest(self.root / "publication.log"),
            "artifact_sha256": {"target.jar": digest(artifacts["target"])}}))
        case = {"id": "one", "steps": 1, "family": "free-motion"}
        numerical = {"id": "one", "status": "PASSED_NUMERICAL_POLICY",
                     "qualification": "UNPASSED", "different_numeric_values": 0,
                     "target_arithmetic": "UNPASSED_UNBOUND_AUDIT",
                     "target_premises": {name: "UNPASSED" for name in
                                         ("producer", "trig", "rounding", "subnormal",
                                          "zero_product", "fma")},
                     "rotation_audit": "UNPASSED_NOT_EXECUTED"}
        with ExitStack() as stack:
            for name in ("verify_candidate_inventory", "verify_baseline_manifest",
                         "verify_baseline_bytes", "verify_policy_catalog",
                         "verify_candidate_identity", "verify_reference_inventory"):
                stack.enter_context(patch("prospective_compare." + name))
            stack.enter_context(patch("prospective_compare.declared_cases", return_value=[case]))
            stack.enter_context(patch("prospective_compare.load_policy_catalog", return_value={}))
            stack.enter_context(patch("prospective_compare.compare_policy_case",
                                      return_value=numerical))
            stack.enter_context(patch("baseline_capture.fixture_source_sha256",
                                      return_value="fixture"))
            attested = {"case_map_sha256": "case-map", "source_sha256": "baseline-source"}
            verify_attestation = stack.enter_context(patch(
                "baseline_capture.verify_attestation", return_value=attested))
            stack.enter_context(patch("baseline_capture.verify_case_slices"))
            stack.enter_context(patch("receipt.verify"))
            stack.enter_context(patch("run.HOST_TASKS", {"jvm": "jvmTest"}))
            stack.enter_context(patch("run.MATRIX_METHODS", tuple(str(i) for i in range(15))))
            stack.enter_context(patch("run.STAGED", self.root))
            stack.enter_context(patch("run.artifacts", return_value=artifacts))
            stack.enter_context(patch("run.clean_identity", return_value=("commit", "source")))
            stack.enter_context(patch("run.runtime", return_value=runtime))
            with self.assertRaisesRegex(Exception, "external baseline attestation"):
                compare_host(baseline, lane, set())
            consistent = compare_host(baseline, lane, set(), sidecar)
            self.assertEqual(consistent["status"], "UNPASSED")
            self.assertEqual(consistent["passed_case_policy"], 0)
            self.assertEqual(consistent["results"][0]["qualification"], "UNPASSED")
            self.assertEqual(consistent["numeric_probe"], "UNPASSED_UNBOUND_PRODUCER")
            self.assertEqual(consistent["numeric_probe_receipt_sha256"],
                             digest(lane / "numeric-probe-receipt.json"))
            self.assertEqual(consistent["operation_binding"], "UNPASSED_NOT_EXECUTED")
            (lane / "numeric-probe-receipt.json").unlink()
            absent = compare_host(baseline, lane, set(), sidecar)
            self.assertEqual(absent["status"], "UNPASSED")
            self.assertEqual(absent["passed_case_policy"], 0)
            self.assertEqual(absent["numeric_probe"], "UNPASSED_NOT_EXECUTED")
            self.assertIsNone(absent["numeric_probe_receipt_sha256"])
            verify_attestation.assert_called_with(baseline, sidecar)
            with patch("actual_arithmetic.expected_case_ids",
                       return_value={"captureGeometry": ["one"]}), \
                    patch("prospective_compare.verify_arithmetic_captures",
                          return_value={"captureGeometry": {"receipt_sha256": "proof"}}):
                for present in (False, True):
                    if present:
                        (lane / "numeric-probe-receipt.json").write_text(
                            json.dumps(probe_receipt))
                    result = compare_host(baseline, lane, set(), sidecar,
                                          self.root / "arithmetic")
                    self.assertEqual(result["status"], "UNPASSED")
                    self.assertEqual(result["passed_case_policy"], 0)
                    self.assertEqual(result["results"][0]["qualification"], "UNPASSED")
                    self.assertEqual(result["numeric_probe"],
                                     "UNPASSED_UNBOUND_PRODUCER" if present else
                                     "UNPASSED_NOT_EXECUTED")
                    self.assertEqual(result["operation_binding"],
                                     "VERIFIED_ARITHMETIC_BINDING")
                    self.assertEqual(result["operation_evidence"]["captureGeometry"]
                                     ["receipt_sha256"], "proof")
                    self.assertEqual(result["results"][0]["operation_method"],
                                     "captureGeometry")
                    self.assertEqual(result["results"][0]["operation_receipt_sha256"],
                                     "proof")
                    self.assertEqual(result["results"][0]["target_arithmetic"],
                                     "PASSED_BOUND_OPERATION_EVIDENCE")
                    self.assertEqual(result["results"][0]["rotation_audit"],
                                     "PASSED_BOUND_OPERATION_TRACE")
                    self.assertEqual(result["results"][0]["target_premises"],
                                     numerical["target_premises"])
                stale = {**probe_receipt, "candidate_commit": "stale"}
                (lane / "numeric-probe-receipt.json").write_text(json.dumps(stale))
                with self.assertRaisesRegex(Exception, "numeric probe source identity"):
                    compare_host(baseline, lane, set(), sidecar,
                                 self.root / "arithmetic")
                contradictory = deepcopy(probe_receipt)
                contradictory["probe"]["nextUpOneBits"] = "3ff0000000000002"
                (lane / "numeric-probe-receipt.json").write_text(
                    json.dumps(contradictory))
                with self.assertRaisesRegex(Exception, "numeric probe target arithmetic"):
                    compare_host(baseline, lane, set(), sidecar,
                                 self.root / "arithmetic")
            # Simulate the verifier boundary. This control does not prove producer execution.
            with patch("prospective_compare.verify_numeric_probe", return_value={
                    "status": "PASSED_BOUND_PRODUCER", "proof": {}}):
                bound = compare_host(baseline, lane, set(), sidecar)
                self.assertEqual(bound["numeric_probe"], "PASSED_BOUND_PRODUCER")
                self.assertEqual(bound["status"], "UNPASSED")
                self.assertEqual(bound["passed_case_policy"], 0)
                self.assertEqual(bound["results"][0]["target_premises"], numerical["target_premises"])
                self.assertEqual(bound["operation_binding"], "UNPASSED_NOT_EXECUTED")
            self.assertEqual(consistent["baseline_attestation_sha256"], digest(sidecar))
            with patch("baseline_capture.verify_attestation", side_effect=ValueError(
                    "wrong sidecar")):
                with self.assertRaisesRegex(ValueError, "wrong sidecar"):
                    compare_host(baseline, lane, set(), sidecar)

    def test_schema_two_cannot_assert_its_own_success(self):
        lane, receipt, runtime, artifacts, _, _ = self.numeric_probe_fixture()
        receipt["schema"] = "portable-binary64-probe-receipt/2"
        receipt["status"] = "PASSED_BOUND_PRODUCER"
        receipt["files"] = {}
        (lane / "numeric-probe").mkdir()
        (lane / "numeric-probe-receipt.json").write_text(json.dumps(receipt))
        with self.assertRaisesRegex(Exception, "numeric producer receipt schema"):
            verify_numeric_probe(lane, "commit", "source", "trace", artifacts, runtime)

    def test_public_schema_two_dispatches_jvm8_to_bound_raw_verifier(self):
        from numeric_producer import KEYS
        lane, _, runtime, artifacts, _, _ = self.numeric_probe_fixture()
        target = lane.parent / "jvm8"
        lane.rename(target)
        receipt = {key: None for key in KEYS}
        receipt.update({"schema": "portable-binary64-probe-receipt/2",
                        "candidate_commit": "wrong", "files": {}})
        (target / "numeric-probe").mkdir()
        (target / "numeric-probe-receipt.json").write_text(json.dumps(receipt))
        with self.assertRaisesRegex(Exception, "numeric producer source identity differs"):
            verify_numeric_probe(target, "commit", "source", "trace", artifacts, runtime)

    def test_arithmetic_bridge_rejects_unbound_and_checks_matrix_case(self):
        from actual_arithmetic import (CaptureRejected, make_capture_receipt,
                                       verify_capture_receipt as verify_raw_receipt)
        from test_actual_arithmetic import fixture, xml_for
        from test_actual_capture_receipt import CaptureReceiptTest

        commit = "a" * 40
        method = "captureGeometry"
        case_id = "geometry-boundary-s0-o0-d0"
        with patch("actual_arithmetic._source_archive", return_value=b"source"), \
                patch("actual_arithmetic._check_local_binaries"), \
                patch("actual_arithmetic._inspect_worker_classpath",
                      return_value=[{"path": "staged", "sha256": "0" * 64}]), \
                patch("actual_arithmetic.expected_case_ids",
                      return_value={method: [case_id]}):
            receipt, files, _ = CaptureReceiptTest().fixture()
            root = self.root / "arithmetic"
            directory = root / method
            directory.mkdir(parents=True)
            names = {"xml": "capture.xml", "stage_log": "stage.log",
                     "gradle_log": "gradle.log", "execve_log": "execve.log",
                     "artifact": "artifact.jar", "runtime": "runtime-java",
                     "source": "source.tar", "worker_classpath": "worker-classpath.txt",
                     "portable_classes": "portable-classes.zip",
                     "worker_class_load": "worker-class-load-123.log"}
            for key, name in names.items():
                (directory / name).write_bytes(files[key])
            receipt_path = directory / "receipt.json"
            receipt_path.write_text(json.dumps(receipt))
            lane = self.root / "jvm"
            cases = lane / "cases"
            cases.mkdir(parents=True)
            trace = "".join(line.split(" ", 1)[1] + "\n" for line in fixture()
                            if line.startswith("NUMERICAL_JSON "))
            (cases / f"{case_id}.jsonl").write_text(trace)

            def verify():
                return verify_arithmetic_captures(
                    root, lane, commit, digest(directory / "source.tar"),
                    digest(directory / "artifact.jar"))

            with self.assertRaisesRegex(Exception, "arithmetic source, artifact, or premise differs"):
                verify()

            def assumed_bound_witness(*args):
                summary = verify_raw_receipt(*args)
                self.assertEqual(summary["status"], "UNPASSED_DYNAMIC_CLASS_LOAD")
                return {**summary, "status": "VERIFIED_ARITHMETIC_BINDING"}

            witness_stub = patch("actual_arithmetic.verify_capture_receipt",
                                 side_effect=assumed_bound_witness)
            witness_stub.start()
            self.addCleanup(witness_stub.stop)
            result = verify()
            self.assertEqual(result[method]["operations_verified"], 1)
            self.assertEqual(result[method]["trace_sha256"],
                             receipt["summary"]["trace_sha256"])
            with patch("actual_arithmetic.expected_case_ids",
                       return_value={method: [case_id], "captureJoints": []}):
                with self.assertRaisesRegex(Exception, "method inventory"):
                    verify()
            duplicate = directory / "duplicate-receipt.json"
            duplicate.write_text("{}")
            with self.assertRaisesRegex(Exception, "receipt or class-load inventory"):
                verify()
            duplicate.unlink()
            changed = deepcopy(receipt)
            changed["method"] = "captureJoints"
            receipt_path.write_text(json.dumps(changed))
            with self.assertRaisesRegex(Exception, "method or source"):
                verify()
            receipt_path.write_text(json.dumps(receipt))
            load = directory / names["worker_class_load"]
            original_load = load.read_bytes()
            load.write_bytes(original_load.replace(b"[123]", b"[124]"))
            with self.assertRaisesRegex(Exception, "arithmetic capture differs"):
                verify()
            load.write_bytes(original_load)
            xml = directory / "capture.xml"
            original_xml = xml.read_bytes()
            xml.write_bytes(original_xml.replace(b'"body_id": "b0"',
                                                 b'"body_id": "b1"'))
            with self.assertRaisesRegex(Exception, "arithmetic capture differs"):
                verify()
            changed_files = {**files, "xml": xml.read_bytes()}
            with self.assertRaises(CaptureRejected):
                make_capture_receipt(changed_files, method, commit, [case_id],
                                     "/tmp/dyn4k-tools/jdk21/bin/java")
            xml.write_bytes(original_xml)
            candidate = cases / f"{case_id}.jsonl"
            candidate.write_text(trace.replace('"step": 1', '"step": 2', 1))
            with self.assertRaisesRegex(Exception, "target output differs"):
                verify()
            candidate.write_text(trace)
            (directory / "source.tar").write_bytes(b"old source")
            with self.assertRaisesRegex(Exception, "arithmetic capture differs"):
                verify()

    def test_target_probe_rejects_stale_identity_output_and_nonfinite(self):
        lane, original, runtime, artifacts, xml, log = self.numeric_probe_fixture()
        path = lane / "numeric-probe-receipt.json"
        for field, value in (("candidate_commit", "stale"), ("source_sha256", "stale"),
                             ("trace_sha256", "stale"),
                             ("artifact_sha256", {}), ("runtime", {}),
                             ("xml_sha256", "0" * 64), ("gradle_log_sha256", "0" * 64),
                             ("method", "other"), ("schema", "other")):
            changed = deepcopy(original)
            changed[field] = value
            path.write_text(json.dumps(changed))
            with self.subTest(field=field), self.assertRaises(Exception):
                verify_numeric_probe(lane, "commit", "source", "trace", artifacts, runtime)
        for field, value in (("ulpOneBits", "3cb0000000000001"),
                             ("nextUpOneBits", "3ff0000000000002"),
                             ("nextDownOneBits", "3feffffffffffffe"),
                             ("negativeZeroBits", "0000000000000000"),
                             ("positiveZeroBits", "8000000000000000"),
                             ("negativeZeroReciprocalBits", "7ff0000000000000"),
                             ("ulpMillionBits", "3de0000000000001"),
                             ("boundaryOriginZeroGapBits", "3d71980000000001"),
                             ("boundaryPositiveMillionGapBits", "3d71980000000000"),
                             ("boundaryNegativeMillionGapBits", "3d71980000000000"),
                             ("maximumFinite", False),
                             ("positiveInfinityFinite", True), ("nanFinite", True)):
            changed = deepcopy(original)
            changed["probe"][field] = value
            path.write_text(json.dumps(changed))
            with self.subTest(field=field), self.assertRaises(Exception):
                verify_numeric_probe(lane, "commit", "source", "trace", artifacts, runtime)
        path.write_text(json.dumps(original))
        text = xml.read_text()
        for changed in (text.replace("NUMERICAL_PROBE_JSON", "MISSING_PROBE"),
                        text.replace("NUMERICAL_PROBE_JSON", "NUMERICAL_PROBE_JSON NaN\nNUMERICAL_PROBE_JSON"),
                        text.replace("NUMERICAL_PROBE_JSON", "NUMERICAL_PROBE_JSON {}\nNUMERICAL_PROBE_JSON"),
                        text.replace("3ff0000000000001", "3ff0000000000002"),
                        text.replace('failures="0"', 'failures="1"'),
                        text.replace('signedZero":-0.0', 'signedZero":0.0'),
                        text.replace('signedZero":-0.0', 'signedZero":-1.0')):
            xml.write_text(changed)
            altered = deepcopy(original)
            altered["xml_sha256"] = digest(xml)
            path.write_text(json.dumps(altered))
            with self.assertRaises(Exception):
                verify_numeric_probe(lane, "commit", "source", "trace", artifacts, runtime)
        changed = deepcopy(original)
        changed["probe"]["nextUpOneBits"] = "3ff0000000000002"
        xml.write_text(text.replace("3ff0000000000001", "3ff0000000000002"))
        changed["xml_sha256"] = digest(xml)
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(Exception, "arithmetic"):
            verify_numeric_probe(lane, "commit", "source", "trace", artifacts, runtime)
        xml.write_text(text)
        path.write_text(json.dumps(original))
        log.write_text("stale process\n")
        with self.assertRaises(Exception):
            verify_numeric_probe(lane, "commit", "source", "trace", artifacts, runtime)
        log.write_text("Starting process target runtime\n")
        runtime_file = Path(runtime["executable"])
        runtime_file.write_bytes(b"different runtime")
        with self.assertRaisesRegex(Exception, "runtime"):
            verify_numeric_probe(lane, "commit", "source", "trace", artifacts, runtime)

    def test_target_probe_boolean_fields_require_json_booleans_in_output_and_receipt(self):
        lane, original, runtime, artifacts, xml, _ = self.numeric_probe_fixture()
        path = lane / "numeric-probe-receipt.json"
        target_output = xml.read_text()
        original_marker = json.dumps(original["probe"], separators=(",", ":"),
                                     sort_keys=True)
        for field in ("maximumFinite", "positiveInfinityFinite", "nanFinite"):
            for number in (1, 0, 1.0, 0.0):
                for location in ("marker", "receipt", "both"):
                    with self.subTest(field=field, number=repr(number), location=location):
                        altered = deepcopy(original)
                        raw = deepcopy(original["probe"])
                        if location in ("marker", "both"):
                            raw[field] = number
                        if location in ("receipt", "both"):
                            altered["probe"][field] = number
                        marker = json.dumps(raw, separators=(",", ":"), sort_keys=True)
                        xml.write_text(target_output.replace(original_marker, marker))
                        altered["xml_sha256"] = digest(xml)
                        path.write_text(json.dumps(altered))
                        with self.assertRaisesRegex(Exception, "Boolean"):
                            verify_numeric_probe(lane, "commit", "source", "trace",
                                                 artifacts, runtime)

    def test_policy_seam_requires_case_envelope_and_complete_paths(self):
        rows, case, catalog = self.policy_rows()
        self.assertEqual(self.policy_result(rows, rows, case, catalog)["status"],
                         "PASSED_NUMERICAL_POLICY")
        self.assertEqual(self.policy_result(rows, rows, case, catalog)["qualification"],
                         "UNPASSED")
        for changed_index, mutator, status in (
                (0, lambda row: row["input"].update(signedZero=0.0), "FAILED_INPUT"),
                (0, lambda row: row.update(profile="other"), "FAILED_INPUT"),
                (2, lambda row: row["state"]["bodies"][0]["position"].append(0.0),
                 "FAILED_STRUCTURE"),
                (2, lambda row: row["state"].update(extra=0.0), "FAILED_STRUCTURE"),
                (1, lambda row: row.update(name="other"), "FAILED_STRUCTURE"),
                (1, lambda row: row.update(order=2), "FAILED_STRUCTURE"),
                (3, lambda row: row.update(events=2), "FAILED_COVERAGE")):
            changed = json.loads(json.dumps(rows))
            mutator(changed[changed_index])
            self.assertEqual(self.policy_result(rows, changed, case, catalog)["status"], status)
        for changed in (rows[:-1], rows[1:], [*rows, rows[-1]]):
            self.assertIn(self.policy_result(rows, changed, case, catalog)["status"],
                          ("FAILED_COVERAGE", "FAILED_STRUCTURE"))
        changed = json.loads(json.dumps(rows))
        changed[2]["state"]["bodies"][0]["position"][1] = -0.0
        self.assertEqual(self.policy_result(rows, changed, case, catalog)["status"],
                         "PASSED_NUMERICAL_POLICY")
        changed = json.loads(json.dumps(rows))
        changed[0]["hz"] = 60.0
        self.assertEqual(self.policy_result(rows, changed, case, catalog)["status"],
                         "PASSED_NUMERICAL_POLICY")
        with_number = json.loads(json.dumps(rows))
        with_number[2]["state"]["configValue"] = 60
        number_catalog = self.small_policy(with_number, {
            "state.state.bodies[].position[]": "bounded_position",
            "event.step.begin.payload": "exact_step"})
        changed = json.loads(json.dumps(with_number))
        changed[2]["state"]["configValue"] = 60.0
        self.assertEqual(self.policy_result(with_number, changed, case, number_catalog)["status"],
                         "PASSED_NUMERICAL_POLICY")
        changed = json.loads(json.dumps(rows))
        changed[1]["payload"] = {"nonfinite": "NaN"}
        self.assertEqual(self.policy_result(rows, changed, case, catalog)["status"],
                         "FAILED_NONFINITE")
        for value in (float("nan"), float("inf"), -float("inf")):
            changed = json.loads(json.dumps(rows))
            changed[1]["payload"] = value
            self.assertEqual(self.policy_result(rows, changed, case, catalog)["status"],
                             "FAILED_NONFINITE")
        invalid = json.loads(json.dumps(rows))
        invalid[0]["dt"] = 0.0
        self.assertEqual(self.policy_result(invalid, invalid, case,
                                            self.small_policy(invalid, {
                                                "state.state.bodies[].position[]": "bounded_position",
                                                "event.step.begin.payload": "exact_step"}))["status"],
                         "UNPASSED_PREMISE")

    def test_each_approved_numeric_bound_has_inside_at_and_over_controls(self):
        fields = (
            ("bounded_position", "position", 0, "state.state.bodies[].position[]", 5e-6),
            ("bounded_velocity", "velocity", 0, "state.state.bodies[].velocity[]", 5e-6 * 60),
            ("bounded_angular_velocity", "angularVelocity", None,
             "state.state.bodies[].angularVelocity", 3.490658503988659e-5 * 60),
            ("bounded_contact_depth", "depth", None, "state.state.bodies[].depth", 5e-6),
            ("bounded_geometry_distance", "distance", None,
             "state.state.bodies[].distance", 1.0536712127723509e-8),
            ("bounded_impulse", "impulse", None, "state.state.bodies[].impulse", 5e-6 * 60),
            ("bounded_force", "force", 0, "state.state.bodies[].force[]", 5e-6 * 60 * 60),
            ("bounded_torque", "torque", None, "state.state.bodies[].torque",
             3.490658503988659e-5 * 60 * 60),
            ("bounded_toi_distance", "toiDistance", None,
             "state.state.bodies[].toiDistance", 4.806217383937352e-6),
            ("bounded_toi_time", "toiTime", None, "state.state.bodies[].toiTime",
             4.806217383937352e-6 / 2),
            ("derived_rotation", "rotationIncrementSum", None,
             "state.state.bodies[].rotationIncrementSum", 3.490658503988659e-5),
            ("derived_transform", "rotationAngle", None,
             "state.state.bodies[].rotationAngle", 3.490658503988659e-5),
            ("derived_momentum", "linearMomentum", 0,
             "state.state.bodies[].linearMomentum[]", 5e-6 * 60 + 32 * 2.220446049250313e-16),
            ("derived_momentum", "angularMomentumCenter", None,
             "state.state.bodies[].angularMomentumCenter",
             3.490658503988659e-5 * 60 + 32 * 2.220446049250313e-16),
            ("derived_energy", "kineticEnergy", None,
             "state.state.bodies[].kineticEnergy",
             (5e-6 * 60) ** 2 + (3.490658503988659e-5 * 60) ** 2 / 2 +
             32 * 2.220446049250313e-16),
        )
        for rule, key, index, path, limit in fields:
            with self.subTest(rule=rule):
                rows, case, _ = self.policy_rows()
                body = rows[2]["state"]["bodies"][0]
                body["velocity"] = [0.0, 0.0]
                body["angularVelocity"] = 0.0
                base = -limit if rule in ("bounded_force", "bounded_torque") else 0.0
                body[key] = [base, 0.0] if index is not None else base
                catalog = self.small_policy(rows, {path: rule,
                                                   "event.step.begin.payload": "exact_step"})
                for factor, expected in ((0.5, "PASSED_NUMERICAL_POLICY"),
                                         (1.0, "PASSED_NUMERICAL_POLICY"),
                                         (1.000001, "FAILED_NUMERICAL_POLICY")):
                    changed = json.loads(json.dumps(rows))
                    value = base + factor * limit
                    if index is None:
                        changed[2]["state"]["bodies"][0][key] = value
                    else:
                        changed[2]["state"]["bodies"][0][key][index] = value
                    result = self.policy_result(rows, changed, case, catalog)
                    self.assertEqual(result["status"], expected, (rule, factor, result))

    def test_state_configuration_is_bound_to_setup_and_action(self):
        rows, case, _ = self.policy_rows()
        case["input"] = {"jointType": "Angle", "mode": "toggle"}
        rows[0]["input"] = case["input"]
        rows[0]["setup"]["joints"] = [{"id": "j0", "mode": {"type": "Angle",
                                                          "limitsEnabled": True}}]
        rows[0]["settings"] = {"gravity": [0.0, 0.0]}
        rows[1] = {"kind": "action", "id": "one", "step": 1, "order": 0,
                   "name": "setLimitsEnabled(false)"}
        rows[2]["state"]["gravity"] = [0.0, 0.0]
        rows[2]["state"]["joints"] = [{"id": "j0", "mode": {"type": "Angle",
                                                             "limitsEnabled": False}}]
        catalog = self.small_policy(rows, {"state.state.gravity[]": "exact_configuration"})
        self.assertEqual(self.policy_result(rows, rows, case, catalog)["status"],
                         "PASSED_NUMERICAL_POLICY")
        bad = json.loads(json.dumps(rows))
        bad[2]["state"]["joints"][0]["mode"]["limitsEnabled"] = True
        self.assertEqual(self.policy_result(rows, bad, case, catalog)["status"],
                         "FAILED_DERIVED")
        bad = json.loads(json.dumps(rows))
        bad[2]["state"]["gravity"][1] = 0.1
        self.assertEqual(self.policy_result(rows, bad, case, catalog)["status"],
                         "FAILED_DERIVED")

    def test_public_policy_transform_negative_zero_angle_and_alias_controls(self):
        observed = {
            "getCost": -1.0, "getSint": -0.0, "getRotationAngle": math.pi,
            "getTranslation": [0.0, 0.0], "getTranslationX": 0.0,
            "getTranslationY": 0.0,
            "getValues": [-1.0, 0.0, 0.0, -0.0, -1.0, 0.0],
        }
        rows, case, _ = self.policy_rows()
        rows[0]["initial"]["bodies"] = [{"transform": deepcopy(observed)}]
        rows[0]["setup"]["bodies"][0]["transform"] = deepcopy(observed)
        rows[2]["state"]["bodies"][0].update(
            transform=deepcopy(observed), previousTransform=deepcopy(observed),
            velocity=[0.0, 0.0], angularVelocity=0.0,
            linearMomentum=[0.0, 0.0], angularMomentumCenter=0.0,
            kineticEnergy=0.0)
        catalog = self.small_policy(rows, {
            "state.state.bodies[].transform.getRotationAngle": "derived_transform",
            "event.step.begin.payload": "exact_step"})

        def compare(source, candidate_state=None):
            reference = deepcopy(rows)
            candidate = deepcopy(rows)
            for target in (reference, candidate):
                target[0]["initial"]["bodies"][0]["transform"] = deepcopy(source)
                target[0]["setup"]["bodies"][0]["transform"] = deepcopy(source)
                target[2]["state"]["bodies"][0]["transform"] = deepcopy(source)
                target[2]["state"]["bodies"][0]["previousTransform"] = deepcopy(source)
            if candidate_state is not None:
                candidate[2]["state"]["bodies"][0]["transform"] = deepcopy(candidate_state)
            return self.policy_result(reference, candidate, case, catalog)

        positive_zero = deepcopy(observed)
        positive_zero["getSint"] = 0.0
        positive_zero["getValues"][1] = -0.0
        positive_zero["getValues"][3] = 0.0
        negative_angle = deepcopy(observed)
        negative_angle["getRotationAngle"] = -math.pi
        nearby_negative = deepcopy(observed)
        nearby_negative["getSint"] = -math.ulp(1.0)
        nearby_negative["getValues"][1] = math.ulp(1.0)
        nearby_negative["getValues"][3] = -math.ulp(1.0)
        nearby_negative["getRotationAngle"] = -math.pi
        adverse_angle = deepcopy(positive_zero)
        adverse_angle["getRotationAngle"] = -math.pi
        alias_sign = deepcopy(positive_zero)
        alias_sign["getValues"][1] = 0.0
        alias_value = deepcopy(positive_zero)
        alias_value["getValues"][1] = 1e-9

        controls = (
            ("retained Java negative zero", observed, None, "PASSED_NUMERICAL_POLICY"),
            ("positive zero", positive_zero, None, "PASSED_NUMERICAL_POLICY"),
            ("negative zero wrong angle", negative_angle, None, "FAILED_DERIVED"),
            ("nearby negative sine", nearby_negative, None, "PASSED_NUMERICAL_POLICY"),
            ("wrong positive-zero angle", positive_zero, adverse_angle, "FAILED_DERIVED"),
            ("signed-zero alias is numerically equal", positive_zero, alias_sign,
             "PASSED_NUMERICAL_POLICY"),
            ("wrong alias value", positive_zero, alias_value, "FAILED_DERIVED"),
        )
        for name, source, candidate_state, expected in controls:
            with self.subTest(name=name):
                self.assertEqual(compare(source, candidate_state)["status"], expected)

    def test_same_run_transform_momentum_energy_and_normal_controls(self):
        rows, case, _ = self.policy_rows()

        def transform(c=1.0, s=0.0, x=0.0, y=0.0, angle=0.0):
            return {"getCost": c, "getSint": s, "getRotationAngle": angle,
                    "getTranslation": [x, y], "getTranslationX": x,
                    "getTranslationY": y, "getValues": [c, -s, x, s, c, y]}

        rows[0]["initial"]["bodies"] = [{"transform": transform()}]
        rows[0]["setup"]["bodies"][0]["transform"] = transform()
        body = rows[2]["state"]["bodies"][0]
        body.update({"transform": transform(), "previousTransform": transform(),
                     "velocity": [0.0, 0.0], "angularVelocity": 0.0,
                     "linearMomentum": [0.0, 0.0], "angularMomentumCenter": 0.0,
                     "kineticEnergy": 0.0, "rotationIncrementSum": 0.0})
        rows[0]["initial"]["bodies"][0]["rotationIncrementSum"] = 0.0
        rows[2]["state"]["observations"] = {"gjk": {"normal": [1.0, 0.0],
                                                       "detected": True}}
        catalog = self.small_policy(rows, {
            "state.state.observations.gjk.normal[]": "bounded_direction",
            "state.state.bodies[].position[]": "bounded_position",
            "state.state.bodies[].transform.getCost": "derived_transform",
            "state.state.bodies[].transform.getTranslation[]": "derived_transform",
            "state.state.bodies[].transform.getTranslationX": "derived_transform",
            "state.state.bodies[].transform.getValues[]": "derived_transform",
            "state.state.bodies[].transform.getRotationAngle": "derived_transform",
            "state.state.bodies[].rotationIncrementSum": "derived_rotation",
            "event.step.begin.payload": "exact_step"})
        self.assertEqual(self.policy_result(rows, rows, case, catalog)["status"],
                         "PASSED_NUMERICAL_POLICY")
        controls = (
            (lambda b, s: b["transform"]["getValues"].__setitem__(1, 0.01),
             "FAILED_DERIVED"),
            (lambda b, s: b["transform"].update(transform(c=1.0001)),
             "FAILED_DERIVED"),
            (lambda b, s: b["transform"].update(transform(angle=0.01)),
             "FAILED_DERIVED"),
            (lambda b, s: b["previousTransform"].update(transform(x=1.0)),
             "FAILED_DERIVED"),
            (lambda b, s: b.update(kineticEnergy=1.0), "FAILED_DERIVED"),
            (lambda b, s: b.update(rotationIncrementSum=0.01), "FAILED_DERIVED"),
            (lambda b, s: s["observations"]["gjk"]["normal"].__setitem__(0, -1.0),
             "FAILED_NUMERICAL_POLICY"),
            (lambda b, s: s["observations"]["gjk"]["normal"].__setitem__(1, 1e-6),
             "FAILED_DERIVED"),
            (lambda b, s: s["observations"]["gjk"].update(detected=False),
             "FAILED_STRUCTURE"),
        )
        for mutate, status in controls:
            with self.subTest(status=status, mutate=str(mutate)):
                candidate = json.loads(json.dumps(rows))
                state = candidate[2]["state"]
                mutate(state["bodies"][0], state)
                self.assertEqual(self.policy_result(rows, candidate, case, catalog)["status"],
                                 status)
        for factor, expected in ((0.5, "PASSED_NUMERICAL_POLICY"),
                                 (1.0, "PASSED_NUMERICAL_POLICY"),
                                 (1.000001, "FAILED_NUMERICAL_POLICY")):
            candidate = json.loads(json.dumps(rows))
            angle = factor * 3.490658503988659e-5
            candidate[2]["state"]["observations"]["gjk"]["normal"] = [
                math.cos(angle), math.sin(angle)]
            self.assertEqual(self.policy_result(rows, candidate, case, catalog)["status"],
                             expected)
        direction_limit = 3.490658503988659e-5
        x = 1.0 - direction_limit * direction_limit / 2
        y = math.nextafter(math.sqrt(direction_limit * direction_limit - (x - 1) ** 2),
                           math.inf)
        self.assertEqual(math.hypot(x - 1.0, y), direction_limit)
        for ordinate, expected in ((y, "PASSED_NUMERICAL_POLICY"),
                                   (math.nextafter(y, math.inf), "FAILED_NUMERICAL_POLICY")):
            candidate = json.loads(json.dumps(rows))
            candidate[2]["state"]["observations"]["gjk"]["normal"] = [x, ordinate]
            self.assertEqual(self.policy_result(rows, candidate, case, catalog)["status"],
                             expected)
        for ulps, expected in ((16, "PASSED_NUMERICAL_POLICY"),
                               (32, "PASSED_NUMERICAL_POLICY"),
                               (33, "FAILED_DERIVED")):
            same = json.loads(json.dumps(rows))
            same[2]["state"]["observations"]["gjk"]["normal"] = [
                1.0 + ulps * math.ulp(1.0), 0.0]
            self.assertEqual(self.policy_result(same, same, case, catalog)["status"],
                             expected)
        for ulps, expected in ((16, "PASSED_NUMERICAL_POLICY"),
                               (17, "FAILED_DERIVED")):
            candidate = json.loads(json.dumps(rows))
            body = candidate[2]["state"]["bodies"][0]
            body["transform"].update(transform(c=1.0 + ulps * math.ulp(1.0)))
            self.assertEqual(self.policy_result(rows, candidate, case, catalog)["status"],
                             expected)
        for ulps, expected in ((32, "PASSED_NUMERICAL_POLICY"),
                               (33, "FAILED_DERIVED")):
            candidate = json.loads(json.dumps(rows))
            body = candidate[2]["state"]["bodies"][0]
            body["transform"]["getRotationAngle"] = ulps * math.ulp(math.pi)
            body["rotationIncrementSum"] = ulps * math.ulp(math.pi)
            self.assertEqual(self.policy_result(rows, candidate, case, catalog)["status"],
                             expected)
        candidate = json.loads(json.dumps(rows))
        candidate[2]["state"]["bodies"][0]["transform"]["getValues"][1] = 0.0
        self.assertEqual(self.policy_result(rows, candidate, case, catalog)["status"],
                         "PASSED_NUMERICAL_POLICY")
        for factor, expected in ((0.5, "PASSED_NUMERICAL_POLICY"),
                                 (1.0, "PASSED_NUMERICAL_POLICY"),
                                 (1.000001, "FAILED_NUMERICAL_POLICY")):
            candidate = json.loads(json.dumps(rows))
            candidate[2]["state"]["bodies"][0]["transform"].update(
                transform(x=factor * 5e-6))
            self.assertEqual(self.policy_result(rows, candidate, case, catalog)["status"],
                             expected)

    def test_conditional_orthogonality_uses_two_step_source_cap(self):
        rows, case, _ = self.policy_rows()
        case.update(id="motion-forces-60", family="free-motion", steps=2,
                    expected_actions=[])
        for row in rows:
            row["id"] = case["id"]
        rows[0].update(family=case["family"], steps=2)

        def transform(c=1.0, s=0.0):
            return {"getCost": c, "getSint": s,
                    "getRotationAngle": math.copysign(math.acos(c), s),
                    "getTranslation": [0.0, 0.0], "getTranslationX": 0.0,
                    "getTranslationY": 0.0, "getValues": [c, -s, 0.0, s, c, 0.0]}

        rows[0]["initial"]["bodies"] = [rows[0]["initial"]["bodies"][0]]
        rows[0]["initial"]["bodies"][0]["transform"] = transform()
        rows[0]["setup"]["bodies"][0]["transform"] = transform()
        body = rows[2]["state"]["bodies"][0]
        body.update(transform=transform(), previousTransform=transform(),
                    velocity=[0.0, 0.0], angularVelocity=0.0,
                    linearMomentum=[0.0, 0.0], angularMomentumCenter=0.0,
                    kineticEnergy=0.0)
        second_event = deepcopy(rows[1])
        second_event["step"] = 2
        second_state = deepcopy(rows[2])
        second_state["step"] = 2
        rows[3:3] = [second_event, second_state]
        rows[-1].update(steps=2, events=2)
        catalog = self.small_policy(rows, {
            "state.state.bodies[].transform.getCost": "derived_transform",
            "state.state.bodies[].transform.getValues[]": "derived_transform",
            "event.step.begin.payload": "exact_step"})
        catalog["cases"] = {case["id"]: {"path_set": 0}}
        catalog["rotation_caps"] = {case["id"]: 1}
        q = math.ulp(1.0)
        for error_ulps, status in ((14, "CONDITIONAL_DIAGNOSTIC_WITHIN"),
                                   (16, "CONDITIONAL_DIAGNOSTIC_WITHIN"),
                                   (18, "FAILED_DERIVED")):
            with self.subTest(error_ulps=error_ulps):
                same = deepcopy(rows)
                same[4]["state"]["bodies"][0]["transform"] = transform(
                    s=math.sqrt(error_ulps * q))
                self.assertEqual(self.policy_result(same, same, case, catalog,
                                                    conditional_diagnostic=True)["status"],
                                 status)
        for component_ulps, status in ((7, "CONDITIONAL_DIAGNOSTIC_WITHIN"),
                                       (8, "CONDITIONAL_DIAGNOSTIC_WITHIN"),
                                       (9, "FAILED_DERIVED")):
            with self.subTest(negative_component_ulps=component_ulps):
                same = deepcopy(rows)
                same[4]["state"]["bodies"][0]["transform"] = transform(
                    c=1.0 - component_ulps * q)
                self.assertEqual(self.policy_result(same, same, case, catalog,
                                                    conditional_diagnostic=True)["status"],
                                 status)
        same = deepcopy(rows)
        same[2]["state"]["bodies"][0]["transform"] = transform(s=2 ** -24)
        self.assertEqual(self.policy_result(same, same, case, catalog,
                                            conditional_diagnostic=True)["status"],
                         "FAILED_DERIVED")
        for initial, status in ((transform(), "CONDITIONAL_DIAGNOSTIC_WITHIN"),
                                (transform(s=math.sqrt(2 * q)),
                                 "CONDITIONAL_DIAGNOSTIC_WITHIN"),
                                (transform(s=math.sqrt(3 * q)), "FAILED_DERIVED"),
                                (transform(c=1.0 - q), "CONDITIONAL_DIAGNOSTIC_WITHIN"),
                                (transform(c=1.0 - 2 * q), "FAILED_DERIVED")):
            with self.subTest(zero_rotation_initial=initial["getValues"]):
                same = deepcopy(rows)
                same[0]["initial"]["bodies"][0]["transform"] = initial
                same[2]["state"]["bodies"][0]["previousTransform"] = initial
                self.assertEqual(self.policy_result(same, same, case, catalog,
                                                    conditional_diagnostic=True)["status"],
                                 status)

    def test_policy_case_requires_declared_action_steps_even_in_identical_runs(self):
        rows, case, _ = self.policy_rows()
        case["expected_actions"] = [1]
        catalog = self.small_policy(rows, {"event.step.begin.payload": "exact_step"})
        self.assertEqual(self.policy_result(rows, rows, case, catalog)["status"],
                         "FAILED_COVERAGE")
        extra = deepcopy(rows)
        extra.insert(2, {"kind": "action", "id": "one", "step": 1, "order": 1,
                         "name": "force-and-torque", "payload": 0.0})
        extra[3]["order"] = 2
        extra[-1]["events"] = 2
        case["expected_actions"] = []
        extra_catalog = self.small_policy(extra, {"event.step.begin.payload": "exact_step"})
        self.assertEqual(self.policy_result(extra, extra, case, extra_catalog)["status"],
                         "FAILED_COVERAGE")
        case["expected_actions"] = [1]
        reordered = deepcopy(extra)
        reordered[1], reordered[2] = reordered[2], reordered[1]
        reordered_catalog = self.small_policy(reordered,
                                              {"event.step.begin.payload": "exact_step"})
        self.assertEqual(self.policy_result(reordered, reordered, case,
                                            reordered_catalog)["status"],
                         "FAILED_COVERAGE")

    def test_public_case_seam_uses_high_precision_4200_rotation_ceiling(self):
        rows, case, _ = self.policy_rows()
        case.update(id="joint-Angle-initial", steps=600, expected_actions=[])
        case["input"] = {"jointType": "Angle", "mode": "initial"}
        rows[0].update(id=case["id"], steps=600, input=case["input"])

        def transform(s=0.0):
            return {"getCost": 1.0, "getSint": s, "getRotationAngle": 0.0,
                    "getTranslation": [0.0, 0.0], "getTranslationX": 0.0,
                    "getTranslationY": 0.0,
                    "getValues": [1.0, -s, 0.0, s, 1.0, 0.0]}

        rows[0]["initial"]["bodies"] = [{"transform": transform()}]
        rows[0]["setup"]["bodies"][0]["transform"] = transform()
        state = rows[2]["state"]["bodies"][0]
        state.update(transform=transform(), previousTransform=transform(),
                     velocity=[0.0, 0.0], angularVelocity=0.0,
                     linearMomentum=[0.0, 0.0], angularMomentumCenter=0.0,
                     kineticEnergy=0.0)
        rows = [rows[0]] + [record for step in range(1, 601)
                            for record in ({**deepcopy(rows[1]), "step": step},
                                           {**deepcopy(rows[2]), "step": step})] + [
                                {"kind": "case-end", "id": case["id"],
                                 "steps": 600, "events": 600}]
        for row in rows[1:-1]:
            row["id"] = case["id"]
        catalog = self.small_policy(rows, {"event.step.begin.payload": "exact_step"})
        catalog["cases"] = {case["id"]: {"path_set": 0}}
        catalog["rotation_caps"] = {case["id"]: 7}
        q = math.ulp(1.0)
        for error_ulps, status in ((29699, "CONDITIONAL_DIAGNOSTIC_WITHIN"),
                                   (29700, "CONDITIONAL_DIAGNOSTIC_WITHIN"),
                                   (29701, "FAILED_DERIVED")):
            with self.subTest(error_ulps=error_ulps):
                same = deepcopy(rows)
                last = same[-2]["state"]["bodies"][0]
                last["transform"] = transform(math.sqrt(error_ulps * q))
                self.assertEqual(self.policy_result(same, same, case, catalog,
                                                    conditional_diagnostic=True)["status"],
                                 status)
                active = self.policy_result(same, same, case, catalog)
                self.assertEqual(active["status"], "FAILED_DERIVED")
                self.assertEqual(active["orthogonality_assessment"],
                                 "ACTIVE_FIXED_32_ULPS")

    def test_rotation_audit_signed_zero_raw_and_post_direct_controls(self):
        from orthogonality import _validate_rotate

        def bits(value):
            return struct.pack(">d", value).hex()

        minus_zero = bits(-0.0)
        plus_zero = bits(0.0)
        one = bits(1.0)
        call = {"sequence": 0, "step": 1, "body_id": "b0", "kind": "rotate",
                "branch": "integrate", "input_kind": "angle",
                "angle_bits": minus_zero, "pre": [one, minus_zero],
                "trig": [one, minus_zero], "raw": [one, minus_zero],
                "post": [one, minus_zero], "clamp": [False, False]}
        _validate_rotate(call, (1.0, -0.0), (1.0, -0.0), (1.0, -0.0))
        changed = deepcopy(call)
        changed["post"][1] = plus_zero
        with self.assertRaisesRegex(ValueError, "clamp result"):
            _validate_rotate(changed, (1.0, -0.0), (1.0, -0.0), (1.0, 0.0))
        changed = deepcopy(call)
        changed["raw"][1] = plus_zero
        changed["post"][1] = plus_zero
        with self.assertRaisesRegex(ValueError, "signed zero"):
            _validate_rotate(changed, (1.0, -0.0), (1.0, -0.0), (1.0, 0.0))
        changed = deepcopy(call)
        changed["angle_bits"] = bits(3.0)
        with self.assertRaisesRegex(ValueError, "trig pair"):
            _validate_rotate(changed, (1.0, -0.0), (1.0, -0.0), (1.0, -0.0))

    def test_rotation_audit_direct_lerp_source_relationship_controls(self):
        from orthogonality import _validate_reset

        def bits(value):
            return struct.pack(">d", value).hex()

        one = [bits(1.0), bits(0.0)]
        call = {"sequence": 0, "step": 1, "body_id": "b0",
                "kind": "lerp-reset", "branch": "toi", "pre": one,
                "end_rotation": one, "trig": one, "post": one,
                "alpha_bits": bits(0.0), "start_angle_bits": bits(0.0),
                "end_angle_bits": bits(0.0), "diff_bits": bits(0.0),
                "angle_bits": bits(0.0)}
        for alpha in (0.0, 0.5, 1.0):
            valid = deepcopy(call)
            valid["alpha_bits"] = bits(alpha)
            _validate_reset(valid, (1.0, 0.0), (1.0, 0.0))
        nonorthogonal_end = deepcopy(call)
        nonorthogonal_end["end_rotation"] = [bits(1.0), bits(1.0)]
        with self.assertRaisesRegex(ValueError, "end orientation"):
            _validate_reset(nonorthogonal_end, (1.0, 0.0), (1.0, 0.0))
        for key, value in (("alpha_bits", bits(math.nextafter(0.0, -math.inf))),
                           ("alpha_bits", bits(math.nextafter(1.0, math.inf))),
                           ("alpha_bits", bits(-1.0)),
                           ("alpha_bits", bits(2.0)),
                           ("start_angle_bits", bits(1.0)),
                           ("end_angle_bits", bits(1.0)),
                           ("diff_bits", bits(2.0)),
                           ("angle_bits", bits(3.0))):
            with self.subTest(key=key, value=value):
                changed = deepcopy(call)
                changed[key] = value
                with self.assertRaises(ValueError):
                    _validate_reset(changed, (1.0, 0.0), (1.0, 0.0))
        changed = deepcopy(call)
        changed["trig"] = [bits(1.0), bits(0.5)]
        with self.assertRaisesRegex(ValueError, "trig pair"):
            _validate_reset(changed, (1.0, 0.5), (1.0, 0.5))
        changed = deepcopy(call)
        changed["start_angle_bits"] = bits(-0.0)
        with self.assertRaisesRegex(ValueError, "source angle"):
            _validate_reset(changed, (1.0, 0.0), (1.0, 0.0))

    def test_rotation_audit_direct_valid_clamp_and_boundary(self):
        from orthogonality import _validate_rotate

        def bits(value):
            return struct.pack(">d", value).hex()

        small = math.sqrt(math.ulp(1.0))
        pre = (1.0, -small)
        trig = (1.0, small)
        raw = (1.0 + math.ulp(1.0), 0.0)
        post = (1.0, 0.0)
        call = {"sequence": 0, "step": 1, "body_id": "b0", "kind": "rotate",
                "branch": "integrate", "input_kind": "pair",
                "rotation_input": [bits(value) for value in trig],
                "pre": [bits(value) for value in pre],
                "trig": [bits(value) for value in trig],
                "raw": [bits(value) for value in raw],
                "post": [bits(value) for value in post],
                "clamp": [True, False]}
        _validate_rotate(call, pre, trig, post)
        changed = deepcopy(call)
        changed["clamp"][0] = False
        with self.assertRaisesRegex(ValueError, "clamp result"):
            _validate_rotate(changed, pre, trig, post)

    def test_rotation_audit_direct_lerp_wraps_both_sides(self):
        from orthogonality import _validate_reset

        def bits(value):
            return struct.pack(">d", value).hex()

        for start_angle, end_angle in ((3.0, -3.0), (-3.0, 3.0)):
            with self.subTest(start=start_angle, end=end_angle):
                start_pair = (math.cos(start_angle), math.sin(start_angle))
                end_pair = (math.cos(end_angle), math.sin(end_angle))
                start = math.copysign(math.acos(start_pair[0]), start_pair[1])
                end = math.copysign(math.acos(end_pair[0]), end_pair[1])
                unwrapped = end - start
                diff = unwrapped
                if diff < -math.pi:
                    diff += 2.0 * math.pi
                if diff > math.pi:
                    diff -= 2.0 * math.pi
                angle = diff * 0.5 + start
                trig = (math.cos(angle), math.sin(angle))
                call = {"sequence": 0, "step": 1, "body_id": "b0",
                        "kind": "lerp-reset", "branch": "toi",
                        "pre": [bits(value) for value in start_pair],
                        "end_rotation": [bits(value) for value in end_pair],
                        "trig": [bits(value) for value in trig],
                        "post": [bits(value) for value in trig],
                        "alpha_bits": bits(0.5), "start_angle_bits": bits(start),
                        "end_angle_bits": bits(end), "diff_bits": bits(diff),
                        "angle_bits": bits(angle)}
                _validate_reset(call, trig, trig)
                call["diff_bits"] = bits(unwrapped)
                with self.assertRaisesRegex(ValueError, "angle arithmetic"):
                    _validate_reset(call, trig, trig)

    def test_rotation_audit_public_lerp_start_angle_cannot_exceed_pi(self):
        rows, case, _ = self.policy_rows()

        def bits(value):
            return struct.pack(">d", value).hex()

        def transform(c, s):
            return {"getCost": c, "getSint": s,
                    "getRotationAngle": math.copysign(math.acos(c), s),
                    "getTranslation": [0.0, 0.0], "getTranslationX": 0.0,
                    "getTranslationY": 0.0,
                    "getValues": [c, -s, 0.0, s, c, 0.0]}

        start_pair = [-1.0, 0.0]
        start = math.pi + 8 * math.ulp(math.pi)
        end = math.pi
        diff = end - start
        trig = [math.cos(start), math.sin(start)]
        rows[0]["initial"]["bodies"] = [rows[0]["initial"]["bodies"][0]]
        rows[0]["initial"]["bodies"][0]["transform"] = transform(*start_pair)
        rows[0]["setup"]["bodies"][0]["transform"] = transform(*start_pair)
        rows[2]["state"]["bodies"][0].update(
            transform=transform(*trig), previousTransform=transform(*start_pair),
            velocity=[0.0, 0.0], angularVelocity=0.0,
            linearMomentum=[0.0, 0.0], angularMomentumCenter=0.0,
            kineticEnergy=0.0)
        catalog = self.small_policy(rows, {"event.step.begin.payload": "exact_step"})
        call = {"sequence": 0, "step": 1, "body_id": "b0", "kind": "lerp-reset",
                "branch": "toi", "pre": [bits(value) for value in start_pair],
                "end_rotation": [bits(value) for value in start_pair],
                "trig": [bits(value) for value in trig],
                "post": [bits(value) for value in trig],
                "alpha_bits": bits(0.0), "start_angle_bits": bits(start),
                "end_angle_bits": bits(end), "diff_bits": bits(diff),
                "angle_bits": bits(start)}
        audit = {"schema": "portable-rotation-audit/2", "case_id": "one",
                 "operation_model_revision": "058bf6d982a0fb89b54050f929f6ea9dae53b714",
                 "declared_calls": 1, "accepted_toi_resets": [[1, "b0"]],
                 "calls": [call]}
        self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                            rotation_audit=audit)["status"],
                         "UNPASSED_PREMISE")

    def test_rotation_audit_structure_clamp_reset_and_count_controls(self):
        rows, case, _ = self.policy_rows()

        def transform(c=1.0, s=0.0):
            return {"getCost": c, "getSint": s, "getRotationAngle": 0.0,
                    "getTranslation": [0.0, 0.0], "getTranslationX": 0.0,
                    "getTranslationY": 0.0, "getValues": [c, -s, 0.0, s, c, 0.0]}

        def bits(value):
            return struct.pack(">d", value).hex()

        rows[0]["initial"]["bodies"] = [rows[0]["initial"]["bodies"][0]]
        rows[0]["initial"]["bodies"][0]["transform"] = transform()
        rows[0]["setup"]["bodies"][0]["transform"] = transform()
        rows[2]["state"]["bodies"][0].update(
            transform=transform(), previousTransform=transform(),
            velocity=[0.0, 0.0], angularVelocity=0.0,
            linearMomentum=[0.0, 0.0], angularMomentumCenter=0.0,
            kineticEnergy=0.0)
        catalog = self.small_policy(rows, {"event.step.begin.payload": "exact_step"})
        one = [bits(1.0), bits(0.0)]
        call = {"sequence": 0, "step": 1, "body_id": "b0", "kind": "rotate",
                "branch": "integrate", "input_kind": "angle", "angle_bits": bits(0.0),
                "pre": one, "trig": one, "raw": one, "post": one,
                "clamp": [False, False]}
        audit = {"schema": "portable-rotation-audit/2", "case_id": "one",
                 "operation_model_revision": "058bf6d982a0fb89b54050f929f6ea9dae53b714",
                 "declared_calls": 1, "accepted_toi_resets": [], "calls": [call]}
        result = self.policy_result(rows, rows, case, catalog, rotation_audit=audit)
        self.assertEqual(result["status"], "PASSED_NUMERICAL_POLICY", result)
        self.assertEqual(result["target_arithmetic"], "UNPASSED_UNBOUND_AUDIT")
        tiny_cos = deepcopy(audit)
        excess_cos = 1.0 + 2 * math.ulp(1.0)
        tiny_cos["calls"][0].update(angle_bits=bits(1e-16),
                                      trig=[bits(excess_cos), bits(0.0)],
                                      raw=[bits(excess_cos), bits(0.0)],
                                      clamp=[True, False])
        self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                            rotation_audit=tiny_cos)["status"],
                         "UNPASSED_PREMISE")
        wrong_sign_rows = deepcopy(rows)
        wrong_sign_rows[2]["state"]["bodies"][0]["transform"] = transform(
            s=-math.ulp(1.0))
        wrong_sign = deepcopy(audit)
        wrong_sign["calls"][0].update(
            angle_bits=bits(1e-16),
            trig=[bits(1.0), bits(-math.ulp(1.0))],
            raw=[bits(1.0), bits(-math.ulp(1.0))],
            post=[bits(1.0), bits(-math.ulp(1.0))])
        self.assertEqual(self.policy_result(wrong_sign_rows, wrong_sign_rows, case,
                                            catalog, rotation_audit=wrong_sign)["status"],
                         "UNPASSED_PREMISE")
        near_limit = 1e-16 - math.ulp(1.0)
        for sine, status in ((-1e-16, "PASSED_NUMERICAL_POLICY"),
                             (near_limit, "PASSED_NUMERICAL_POLICY"),
                             (math.nextafter(near_limit, -math.inf),
                              "UNPASSED_PREMISE")):
            with self.subTest(tiny_angle_sine=sine):
                near_rows = deepcopy(rows)
                near_rows[2]["state"]["bodies"][0]["transform"] = transform(s=sine)
                near_audit = deepcopy(audit)
                near_audit["calls"][0].update(
                    angle_bits=bits(1e-16), trig=[bits(1.0), bits(sine)],
                    raw=[bits(1.0), bits(sine)], post=[bits(1.0), bits(sine)])
                self.assertEqual(self.policy_result(near_rows, near_rows, case,
                                                    catalog, rotation_audit=near_audit)["status"],
                                 status)
        self.assertEqual(result["target_premises"], {
            name: "UNPASSED" for name in
            ("producer", "trig", "rounding", "subnormal", "zero_product", "fma")})
        pair_input = deepcopy(audit)
        pair_call = pair_input["calls"][0]
        pair_call["input_kind"] = "pair"
        pair_call["rotation_input"] = one
        pair_call.pop("angle_bits")
        self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                            rotation_audit=pair_input)["status"],
                         "PASSED_NUMERICAL_POLICY")
        pair_call["rotation_input"] = [bits(-1.0), bits(0.0)]
        self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                            rotation_audit=pair_input)["status"],
                         "UNPASSED_PREMISE")

        mutations = []
        missing = deepcopy(audit)
        missing["calls"] = []
        mutations.append(missing)
        extra = deepcopy(audit)
        extra["declared_calls"] = 2
        extra["calls"].append({**deepcopy(call), "sequence": 1})
        mutations.append(extra)
        reordered = deepcopy(audit)
        reordered["calls"][0]["sequence"] = 1
        mutations.append(reordered)
        malformed = deepcopy(audit)
        malformed["calls"] = [None]
        mutations.append(malformed)
        zero_product = deepcopy(audit)
        zero_product["calls"][0]["raw"][1] = bits(math.ulp(1.0))
        mutations.append(zero_product)
        signed_zero = deepcopy(audit)
        signed_zero["calls"][0]["pre"][1] = bits(-0.0)
        mutations.append(signed_zero)
        bad_clamp = deepcopy(audit)
        bad_clamp["calls"][0].update(trig=[bits(1.0 + math.ulp(1.0)), bits(0.0)],
                                      raw=[bits(1.0 + math.ulp(1.0)), bits(0.0)],
                                      clamp=[True, False],
                                      post=[bits(1.0 + math.ulp(1.0)), bits(0.0)])
        mutations.append(bad_clamp)
        missing_reset = deepcopy(audit)
        missing_reset["accepted_toi_resets"] = [[1, "b0"]]
        mutations.append(missing_reset)
        nonfinite = deepcopy(audit)
        nonfinite["calls"][0]["angle_bits"] = bits(math.inf)
        mutations.append(nonfinite)
        subnormal = deepcopy(audit)
        subnormal["calls"][0]["trig"][1] = bits(math.ulp(0.0))
        mutations.append(subnormal)
        for index, changed in enumerate(mutations):
            with self.subTest(mutation=index):
                self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                                    rotation_audit=changed)["status"],
                                 "UNPASSED_PREMISE")

        clamped = deepcopy(audit)
        clamped["calls"][0].update(trig=[bits(1.0 + math.ulp(1.0)), bits(0.0)],
                                     raw=[bits(1.0 + math.ulp(1.0)), bits(0.0)],
                                     clamp=[True, False])
        self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                            rotation_audit=clamped)["status"],
                         "UNPASSED_PREMISE")
        reset = deepcopy(audit)
        reset["accepted_toi_resets"] = [[1, "b0"]]
        reset["calls"][0] = {"sequence": 0, "step": 1, "body_id": "b0",
                             "kind": "lerp-reset", "branch": "toi",
                             "alpha_bits": bits(0.0), "start_angle_bits": bits(0.0),
                             "end_angle_bits": bits(0.0), "diff_bits": bits(0.0),
                             "angle_bits": bits(0.0), "pre": one,
                             "end_rotation": one, "trig": one,
                             "post": one}
        self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                            rotation_audit=reset)["status"],
                         "PASSED_NUMERICAL_POLICY")
        nonorthogonal_end = deepcopy(reset)
        nonorthogonal_end["calls"][0]["end_rotation"] = [bits(1.0), bits(1.0)]
        self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                            rotation_audit=nonorthogonal_end)["status"],
                         "UNPASSED_PREMISE")
        unbound_end = deepcopy(reset)
        unbound_end["calls"][0].update(
            end_rotation=[bits(0.0), bits(1.0)],
            end_angle_bits=bits(math.pi / 2), diff_bits=bits(math.pi / 2))
        self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                            rotation_audit=unbound_end)["status"],
                         "UNPASSED_PREMISE")
        rotation = [bits(math.cos(math.pi / 2)), bits(math.sin(math.pi / 2))]
        rotate_then_reset = deepcopy(reset)
        rotate_then_reset["declared_calls"] = 2
        rotate_call = deepcopy(call)
        rotate_call.update(angle_bits=bits(math.pi / 2), trig=rotation,
                           raw=rotation, post=rotation)
        rotate_then_reset["calls"].insert(0, rotate_call)
        end_angle = math.acos(math.cos(math.pi / 2))
        rotate_then_reset["calls"][1].update(
            sequence=1, end_rotation=rotation,
            end_angle_bits=bits(end_angle), diff_bits=bits(end_angle))
        self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                            rotation_audit=rotate_then_reset)["status"],
                         "PASSED_NUMERICAL_POLICY")
        wrong_end_origin = deepcopy(rotate_then_reset)
        wrong_end_origin["calls"][1].update(
            end_rotation=one, end_angle_bits=bits(0.0), diff_bits=bits(0.0))
        self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                            rotation_audit=wrong_end_origin)["status"],
                         "UNPASSED_PREMISE")
        old_schema = deepcopy(reset)
        old_schema["schema"] = "portable-rotation-audit/1"
        self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                            rotation_audit=old_schema)["status"],
                         "UNPASSED_PREMISE")
        missing_end = deepcopy(reset)
        missing_end["calls"][0].pop("end_rotation")
        self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                            rotation_audit=missing_end)["status"],
                         "UNPASSED_PREMISE")
        for key, value in (("alpha_bits", bits(-1.0)),
                           ("alpha_bits", bits(2.0)),
                           ("start_angle_bits", bits(1.0)),
                           ("end_angle_bits", bits(1.0)),
                           ("diff_bits", bits(2.0)),
                           ("angle_bits", bits(3.0))):
            with self.subTest(inconsistent_lerp=key, bits=value):
                changed = deepcopy(reset)
                changed["calls"][0][key] = value
                self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                                    rotation_audit=changed)["status"],
                                 "UNPASSED_PREMISE")
        wrong_trig = deepcopy(reset)
        wrong_trig["calls"][0]["angle_bits"] = bits(3.0)
        self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                            rotation_audit=wrong_trig)["status"],
                         "UNPASSED_PREMISE")
        wrong_rotate_angle = deepcopy(audit)
        wrong_rotate_angle["calls"][0]["angle_bits"] = bits(3.0)
        self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                            rotation_audit=wrong_rotate_angle)["status"],
                         "UNPASSED_PREMISE")
        wrong_raw_zero = deepcopy(audit)
        wrong_raw_zero["calls"][0]["raw"][1] = bits(-0.0)
        wrong_raw_zero["calls"][0]["post"][1] = bits(-0.0)
        self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                            rotation_audit=wrong_raw_zero)["status"],
                         "UNPASSED_PREMISE")
        signed_rows = deepcopy(rows)
        signed_rows[0]["initial"]["bodies"][0]["transform"] = transform(s=-0.0)
        signed_rows[0]["setup"]["bodies"][0]["transform"] = transform(s=-0.0)
        signed_post = deepcopy(audit)
        signed_post["calls"][0].update(
            angle_bits=bits(-0.0), pre=[bits(1.0), bits(-0.0)],
            trig=[bits(1.0), bits(-0.0)], raw=[bits(1.0), bits(-0.0)])
        signed_post["calls"][0]["post"] = one
        self.assertEqual(self.policy_result(signed_rows, signed_rows, case, catalog,
                                            rotation_audit=signed_post)["status"],
                         "UNPASSED_PREMISE")
        signed_post["calls"][0]["post"] = [bits(1.0), bits(-0.0)]
        signed_rows[2]["state"]["bodies"][0]["transform"] = transform(s=-0.0)
        self.assertEqual(self.policy_result(signed_rows, signed_rows, case, catalog,
                                            rotation_audit=signed_post)["status"],
                         "PASSED_NUMERICAL_POLICY")
        for error_ulps, status in ((3, "UNPASSED_PREMISE"),
                                   (5, "UNPASSED_PREMISE"),
                                   (7, "UNPASSED_PREMISE")):
            with self.subTest(direct_reset_ulps=error_ulps):
                same = deepcopy(rows)
                changed = deepcopy(reset)
                s = math.sqrt(error_ulps * math.ulp(1.0))
                same[2]["state"]["bodies"][0]["transform"] = transform(s=s)
                changed["calls"][0]["trig"] = [bits(1.0), bits(s)]
                changed["calls"][0]["post"] = [bits(1.0), bits(s)]
                self.assertEqual(self.policy_result(same, same, case, catalog,
                                                    rotation_audit=changed)["status"], status)
        extra_reset = deepcopy(reset)
        extra_reset["declared_calls"] = 2
        extra_reset["calls"].append({**deepcopy(reset["calls"][0]), "sequence": 1})
        self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                            rotation_audit=extra_reset)["status"],
                         "UNPASSED_PREMISE")
        reset["calls"][0]["kind"] = "rotate"
        self.assertEqual(self.policy_result(rows, rows, case, catalog,
                                            rotation_audit=reset)["status"],
                         "UNPASSED_PREMISE")

    def test_ccd_toi_reset_requires_the_accepted_source_branch(self):
        from cases import declared_cases
        case = next(row for row in declared_cases() if row["id"] == "ccd-circle-ALL-30")
        rows, _, _ = self.policy_rows()

        def transform():
            return {"getCost": 1.0, "getSint": 0.0, "getRotationAngle": 0.0,
                    "getTranslation": [0.0, 0.0], "getTranslationX": 0.0,
                    "getTranslationY": 0.0,
                    "getValues": [1.0, -0.0, 0.0, 0.0, 1.0, 0.0]}

        rows[0].update(id=case["id"], family=case["family"], profile=case["profile"],
                       hz=case["hz"], steps=case["steps"], input=case["input"],
                       dt=1 / case["hz"])
        rows[0]["initial"]["bodies"] = [{"transform": transform()}]
        rows[0]["setup"]["bodies"][0]["transform"] = transform()
        rows[1]["payload"] = 1 / case["hz"]
        rows[2]["state"]["bodies"][0].update(
            transform=transform(), previousTransform=transform(),
            velocity=[0.0, 0.0], angularVelocity=0.0,
            linearMomentum=[0.0, 0.0], angularMomentumCenter=0.0,
            kineticEnergy=0.0)
        stream = [rows[0]]
        for step in range(1, case["steps"] + 1):
            event = deepcopy(rows[1])
            state = deepcopy(rows[2])
            event.update(id=case["id"], step=step)
            state.update(id=case["id"], step=step)
            stream.append(event)
            if step == 1:
                stream.append({"kind": "event", "id": case["id"], "step": 1,
                               "order": 1, "name": "toi.payload.bodies", "payload": 0.5})
                state["order"] = 2
            stream.append(state)
        stream.append({"kind": "case-end", "id": case["id"],
                       "steps": case["steps"], "events": case["steps"] + 1})
        catalog = self.small_policy(stream, {"event.step.begin.payload": "exact_step"})
        catalog["cases"] = {case["id"]: {"path_set": 0}}
        catalog["rotation_caps"] = {case["id"]: 5}
        one = ["3ff0000000000000", "0000000000000000"]
        reset_call = {"sequence": 0, "step": 1, "body_id": "b0",
                      "kind": "lerp-reset", "branch": "toi",
                      "alpha_bits": one[1], "start_angle_bits": one[1],
                      "end_angle_bits": one[1], "diff_bits": one[1],
                      "angle_bits": one[1], "pre": one,
                      "end_rotation": one, "trig": one, "post": one}
        audit = {"schema": "portable-rotation-audit/2", "case_id": case["id"],
                 "operation_model_revision": "058bf6d982a0fb89b54050f929f6ea9dae53b714",
                 "declared_calls": 1, "accepted_toi_resets": [[1, "b0"]],
                 "calls": [reset_call]}
        self.assertEqual(self.policy_result(stream, stream, case, catalog,
                                            rotation_audit=audit)["status"],
                         "PASSED_NUMERICAL_POLICY")
        for changed in (dict(audit, calls=[], declared_calls=0),
                        dict(audit, calls=[dict(reset_call, kind="rotate")])):
            self.assertEqual(self.policy_result(stream, stream, case, catalog,
                                                rotation_audit=changed)["status"],
                             "UNPASSED_PREMISE")
        vetoed = dict(audit, accepted_toi_resets=[], calls=[], declared_calls=0)
        self.assertEqual(self.policy_result(stream, stream, case, catalog,
                                            rotation_audit=vetoed)["status"],
                         "PASSED_NUMERICAL_POLICY")

    def test_geometry_represented_gap_and_toi_range_premises(self):
        rows, case, _ = self.policy_rows()
        case["family"] = rows[0]["family"] = "geometry-collision"
        case["input"] = rows[0]["input"] = {"delta": 2e-15, "origin": [0.0, 0.0],
                                            "scale": 1.0, "signedZero": -0.0}
        rows[0]["setup"]["bodies"] = [
            {"id": "b0", "mass": 0.0, "inertia": 0.0, "transform": {
                "getTranslationX": 0.0, "getTranslationY": 0.0}},
            {"id": "b1", "mass": 1.0, "inertia": 1.0, "transform": {
                "getTranslationX": 1.5 + 2e-15, "getTranslationY": 0.0}}]
        catalog = self.small_policy(rows, {"state.state.bodies[].position[]": "bounded_position",
                                           "event.step.begin.payload": "exact_step"})
        gap = (1.5 + 2e-15) - 1.5
        limit = min(8 * math.ulp(1.5 + 2e-15), gap / 4)
        for factor, expected in ((0.5, "PASSED_NUMERICAL_POLICY"),
                                 (1.0, "PASSED_NUMERICAL_POLICY"),
                                 (1.000001, "FAILED_NUMERICAL_POLICY")):
            candidate = json.loads(json.dumps(rows))
            candidate[2]["state"]["bodies"][0]["position"][0] = factor * limit
            self.assertEqual(self.policy_result(rows, candidate, case, catalog)["status"],
                             expected)
        rounded = json.loads(json.dumps(rows))
        rounded[0]["input"]["delta"] = 1e-12
        case["input"] = rounded[0]["input"]
        rounded[0]["setup"]["bodies"][1]["transform"]["getTranslationX"] = 1.5
        catalog = self.small_policy(rounded, {"state.state.bodies[].position[]": "bounded_position",
                                              "event.step.begin.payload": "exact_step"})
        self.assertEqual(self.policy_result(rounded, rounded, case, catalog)["status"],
                         "UNPASSED_PREMISE")
        mismatched = json.loads(json.dumps(rows))
        case["input"] = mismatched[0]["input"]
        mismatched[0]["setup"]["bodies"][0]["transform"]["getTranslationX"] = 0.1
        catalog = self.small_policy(mismatched, {
            "state.state.bodies[].position[]": "bounded_position",
            "event.step.begin.payload": "exact_step"})
        self.assertEqual(self.policy_result(mismatched, mismatched, case, catalog)["status"],
                         "UNPASSED_PREMISE")
        rows, case, _ = self.policy_rows()
        body = rows[2]["state"]["bodies"][0]
        body["toiTime"] = 1.0
        catalog = self.small_policy(rows, {
            "state.state.bodies[].toiTime": "bounded_toi_time",
            "event.step.begin.payload": "exact_step"})
        bad = json.loads(json.dumps(rows))
        bad[2]["state"]["bodies"][0]["toiTime"] = 1.000001
        self.assertEqual(self.policy_result(rows, bad, case, catalog)["status"],
                         "FAILED_NUMERICAL_POLICY")
        rows[0]["input"]["speed"] = case["input"]["speed"] = 0.0
        catalog = self.small_policy(rows, {
            "state.state.bodies[].toiTime": "bounded_toi_time",
            "event.step.begin.payload": "exact_step"})
        self.assertEqual(self.policy_result(rows, rows, case, catalog)["status"],
                         "UNPASSED_PREMISE")
        rows[0]["input"]["speed"] = case["input"]["speed"] = -0.1
        rows[2]["state"]["bodies"][0]["toiTime"] = 0.0
        catalog = self.small_policy(rows, {
            "state.state.bodies[].toiTime": "bounded_toi_time",
            "event.step.begin.payload": "exact_step"})
        for value, expected in ((0.0005, "PASSED_NUMERICAL_POLICY"),
                                (0.001, "PASSED_NUMERICAL_POLICY"),
                                (0.001000001, "FAILED_NUMERICAL_POLICY")):
            candidate = json.loads(json.dumps(rows))
            candidate[2]["state"]["bodies"][0]["toiTime"] = value
            self.assertEqual(self.policy_result(rows, candidate, case, catalog)["status"],
                             expected)

    def test_indexed_geometry_delta_premises_and_input_identity(self):
        from cases import declared_cases

        archive = os.environ.get("DYN4K_GEOMETRY_BASELINE")
        if archive is None:
            self.skipTest("set DYN4K_GEOMETRY_BASELINE for indexed geometry controls")
        archive = Path(archive)
        manifest = json.loads((archive / "verified.json").read_text())
        self.assertEqual(manifest["fixture_source_sha256"],
                         "dd104a7e018b9d0bd77c9af14e929699d68f29fa4ac8179a5bd7d98bdc87d9ce")
        self.assertEqual(manifest["baseline_jar_sha256"],
                         "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e")
        cases = {case["id"]: case for case in declared_cases()}
        catalog = load_policy_catalog()

        def compare_indexed(case_id):
            source = archive / "baseline-jvm/cases" / f"{case_id}.jsonl"
            self.assertEqual(digest(source), manifest["case_sha256"][case_id])
            return compare_policy_case(source, source, cases[case_id], catalog)

        for origin in range(1, 5):
            for delta in (1, 3):
                case_id = f"geometry-boundary-s0-o{origin}-d{delta}"
                with self.subTest(lost_delta=case_id):
                    result = compare_indexed(case_id)
                    self.assertEqual(result["status"], "UNPASSED_PREMISE")
                    self.assertEqual(result["reason"], "boundary delta rounds away")
                    self.assertEqual(result["qualification"], "UNPASSED")

        for origin in (3, 4):
            for delta in (1, 3):
                case_id = f"geometry-boundary-s1-o{origin}-d{delta}"
                with self.subTest(existing_zero_gap=case_id):
                    result = compare_indexed(case_id)
                    self.assertEqual(result["status"], "UNPASSED_PREMISE")
                    self.assertEqual(result["reason"], "boundary delta rounds away")

        for delta, sign in ((0, -1), (4, 1)):
            case_id = f"geometry-boundary-s0-o1-d{delta}"
            source = archive / "baseline-jvm/cases" / f"{case_id}.jsonl"
            with self.subTest(represented_neighbor=case_id):
                with source.open(encoding="utf-8") as stream:
                    header = json.loads(stream.readline())
                values = header["input"]
                center = header["setup"]["bodies"][1]["transform"]["getTranslationX"]
                neutral = values["origin"][0] + values["scale"] * 1.5
                gap = (center - values["origin"][0]) - values["scale"] * 1.5
                self.assertNotEqual(center, neutral)
                self.assertEqual(math.copysign(1.0, gap), sign)
                self.assertEqual(compare_indexed(case_id)["status"],
                                 "PASSED_NUMERICAL_POLICY")

        case_id = "geometry-boundary-s0-o1-d1"
        source = archive / "baseline-jvm/cases" / f"{case_id}.jsonl"
        rows = source.read_text().splitlines()
        header = json.loads(rows[0])
        header["input"]["delta"] = -1e-8
        self.candidate.write_text(json.dumps(header) + "\n" + "\n".join(rows[1:]) + "\n")
        self.assertEqual(compare_policy_case(source, self.candidate, cases[case_id],
                                             catalog)["status"], "FAILED_INPUT")

    def test_free_motion_caps_and_computed_zero_are_target_specific(self):
        for rule, field, limit in (
                ("bounded_position", "position", 2e-9),
                ("bounded_velocity", "velocity", 2e-9 * 60),
                ("bounded_angular_velocity", "angularVelocity", 2e-7 * 60),
                ("derived_rotation", "rotationIncrementSum", 2e-7)):
            with self.subTest(rule=rule):
                rows, case, _ = self.policy_rows()
                case["family"] = rows[0]["family"] = "free-motion"
                body = rows[2]["state"]["bodies"][0]
                if field not in body:
                    body[field] = [0.0, 0.0] if field == "velocity" else 0.0
                path = f"state.state.bodies[].{field}" + ("[]" if isinstance(body[field], list) else "")
                catalog = self.small_policy(rows, {path: rule,
                                                   "event.step.begin.payload": "exact_step"})
                for factor, expected in ((0.5, "PASSED_NUMERICAL_POLICY"),
                                         (1.0, "PASSED_NUMERICAL_POLICY"),
                                         (1.000001, "FAILED_NUMERICAL_POLICY")):
                    candidate = json.loads(json.dumps(rows))
                    value = factor * limit
                    if isinstance(body[field], list):
                        candidate[2]["state"]["bodies"][0][field][0] = value
                    else:
                        candidate[2]["state"]["bodies"][0][field] = value
                    self.assertEqual(self.policy_result(rows, candidate, case, catalog)["status"],
                                     expected)
        rows, case, _ = self.policy_rows()
        body = rows[2]["state"]["bodies"][0]
        body["force"] = [0.0, 0.0]
        body["torque"] = 0.0
        catalog = self.small_policy(rows, {
            "state.state.bodies[].force[]": "bounded_force",
            "state.state.bodies[].torque": "bounded_torque",
            "event.step.begin.payload": "exact_step"})
        candidate = json.loads(json.dumps(rows))
        candidate[2]["state"]["bodies"][0]["force"][0] = -0.0
        candidate[2]["state"]["bodies"][0]["torque"] = -0.0
        self.assertEqual(self.policy_result(rows, candidate, case, catalog)["status"],
                         "PASSED_NUMERICAL_POLICY")
        for field, value in (("force", 1e-12), ("torque", 1e-12)):
            candidate = json.loads(json.dumps(rows))
            if field == "force":
                candidate[2]["state"]["bodies"][0][field][0] = value
            else:
                candidate[2]["state"]["bodies"][0][field] = value
            self.assertEqual(self.policy_result(rows, candidate, case, catalog)["status"],
                             "FAILED_NUMERICAL_POLICY")
        rows, case, _ = self.policy_rows()
        case["input"] = rows[0]["input"] = {"jointType": "Angle"}
        rows[0]["setup"]["joints"] = [{"id": "j0", "mode": {"type": "Angle"}}]
        rows[2]["state"]["joints"] = [{"id": "j0", "mode": {"type": "Angle"},
                                         "reactionForce": [0.0, 0.0]}]
        catalog = self.small_policy(rows, {
            "state.state.joints[].reactionForce[]": "bounded_force",
            "event.step.begin.payload": "exact_step"})
        candidate = json.loads(json.dumps(rows))
        candidate[2]["state"]["joints"][0]["reactionForce"][0] = 1e-12
        self.assertEqual(self.policy_result(rows, candidate, case, catalog)["status"],
                         "FAILED_NUMERICAL_POLICY")

    def test_energy_bound_propagates_two_component_velocity_units(self):
        rows, case, _ = self.policy_rows()
        body = rows[2]["state"]["bodies"][0]
        body["velocity"] = [1.0, 1.0]
        body["angularVelocity"] = 0.0
        body["kineticEnergy"] = 1.0
        catalog = self.small_policy(rows, {
            "state.state.bodies[].velocity[]": "bounded_velocity",
            "state.state.bodies[].kineticEnergy": "derived_energy",
            "event.step.begin.payload": "exact_step"})
        ev = 5e-6 * 60
        energy_limit = 2 * ev + ev * ev + (3.490658503988659e-5 * 60) ** 2 / 2
        energy_limit += 32 * math.ulp(1.0 + energy_limit)
        for factor, expected in ((0.5, "PASSED_NUMERICAL_POLICY"),
                                 (1.0, "PASSED_NUMERICAL_POLICY"),
                                 (1.000001, "FAILED_NUMERICAL_POLICY")):
            candidate = json.loads(json.dumps(rows))
            candidate[2]["state"]["bodies"][0]["velocity"] = [1.0 + ev, 1.0 + ev]
            candidate[2]["state"]["bodies"][0]["kineticEnergy"] = 1.0 + factor * energy_limit
            self.assertEqual(self.policy_result(rows, candidate, case, catalog)["status"],
                             expected)

    def test_known_angle_nonfinite_stays_failed_physical(self):
        rows, case, _ = self.policy_rows()
        case_id = "P-J-Angle-ratio-limits-off--1.0"
        case["id"] = case_id
        for row in rows:
            row["id"] = case_id
        rows[2]["state"]["bodies"][0]["kineticEnergy"] = {"nonfinite": "Infinity"}
        catalog = self.small_policy(rows, {"event.step.begin.payload": "exact_step"})
        catalog["cases"] = {case_id: catalog["cases"].pop("one")}
        catalog["rotation_caps"] = {case_id: 7}
        self.assertEqual(self.policy_result(rows, rows, case, catalog)["status"],
                         "FAILED_PHYSICAL")
    def policy_rows(self):
        case = {"id": "one", "family": "joints-limits-motors", "profile": "default",
                "hz": 60, "steps": 1, "input": {"signedZero": -0.0, "speed": -120.0}}
        rows = [
            {"kind": "inputs", "id": "one", "family": case["family"],
             "profile": "default", "hz": 60, "steps": 1, "dt": 1 / 60,
             "input": case["input"],
             "initial": {"bodies": [{"velocity": [0.0, 0.0]},
                                    {"velocity": [-120.0, 0.0]}]},
             "setup": {"bodies": [{"id": "b0", "mass": 1.0, "inertia": 1.0}],
                       "joints": []}},
            {"kind": "event", "id": "one", "step": 1, "order": 0,
             "name": "step.begin", "payload": 1 / 60},
            {"kind": "state", "id": "one", "step": 1, "order": 1,
             "state": {"bodies": [{"id": "b0", "position": [0.0, 0.0]}],
                       "joints": []}},
            {"kind": "case-end", "id": "one", "steps": 1, "events": 1},
        ]
        return rows, case, self.small_policy(rows, {
            "state.state.bodies[].position[]": "bounded_position",
            "event.step.begin.payload": "exact_step"})

    def policy_result(self, reference, candidate, case, catalog, rotation_audit=None,
                      conditional_diagnostic=False):
        self.reference.write_text(''.join(json.dumps(row) + "\n" for row in reference))
        self.candidate.write_text(''.join(json.dumps(row) + "\n" for row in candidate))
        return compare_policy_case(self.reference, self.candidate, case, catalog,
                                   rotation_audit=rotation_audit,
                                   conditional_diagnostic=conditional_diagnostic)

    @staticmethod
    def small_policy(rows, rules):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "case.jsonl"
            source.write_text(''.join(json.dumps(row) + "\n" for row in rows))
            observed = reference_path_inventory(source)
        paths = [{"path": name, "types": types,
                  "rule": rules.get(name, "exact_structure" if name.startswith("case-end.")
                                or name.endswith((".id", ".kind", ".name", ".order", ".step"))
                                else "exact_input" if name.startswith("inputs.")
                                else "exact_configuration")}
                 for name, types in sorted(observed.items())]
        return {"cases": {"one": {"path_set": 0}}, "paths": paths,
                "path_sets": [list(range(len(paths)))],
                "rotation_caps": {"one": 1},
                "rule_proposals": load_policy_catalog()["rule_proposals"]}

    @staticmethod
    def policy_manifest(catalog, frozen):
        return {"trace_sha256": catalog["baseline_trace_sha256"],
                "baseline_source_revision": catalog["baseline_source_revision"],
                "baseline_jar_sha256": catalog["baseline_jar_sha256"],
                "fixture_source_sha256": catalog["baseline_fixture_source_sha256"],
                "case_sha256": {**{case_id: "frozen" for case_id in frozen},
                                **{case_id: row["sha256"]
                                   for case_id, row in catalog["cases"].items()}}}


if __name__ == "__main__":
    unittest.main()
