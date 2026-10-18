import json
import tempfile
import unittest
from pathlib import Path

from prospective_compare import (compare_case, verify_baseline_manifest,
                                 verify_baseline_bytes, verify_reference_case,
                                 load_policy_catalog, verify_policy_catalog,
                                 reference_path_inventory, verify_reference_inventory)
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
        catalog = load_policy_catalog()
        cases = declared_cases()
        frozen = {case["id"] for case in cases if case["require_frozen_projection"]}
        manifest = self.policy_manifest(catalog, frozen)
        verify_policy_catalog(catalog, manifest, cases, frozen)
        self.assertEqual(len(catalog["cases"]), 318)
        self.assertEqual(catalog["baseline_trace_sha256"],
                         "f31dc4a0a63e96a7212a58df02c7f1be539756532603e5f5b51e528dd7b84d07")
        self.assertTrue(all(catalog["paths"][index]["rule"]
                            for schema in catalog["path_sets"] for index in schema))

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
        altered = json.loads(json.dumps(catalog))
        altered["cases"][next(iter(altered["cases"]))]["sha256"] = "0" * 64
        with self.assertRaisesRegex(Exception, "case binding"):
            verify_policy_catalog(altered, manifest, cases, frozen)
        altered = json.loads(json.dumps(catalog))
        altered["paths"][0]["rule"] = "bounded_scalar"
        with self.assertRaisesRegex(Exception, "unclassified"):
            verify_policy_catalog(altered, manifest, cases, frozen)
        altered = json.loads(json.dumps(catalog))
        altered["qualification"] = "PASSED"
        with self.assertRaisesRegex(Exception, "unratified"):
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
