import json
import math
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
from prospective_compare import verify_candidate_inventory
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
        (lane / "numeric-probe-receipt.json").write_text("{}\n")
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

    def test_compare_host_keeps_case_unpassed_without_target_probe_producer(self):
        lane, _, runtime, artifacts, _, _ = self.numeric_probe_fixture()
        baseline = self.root / "baseline"
        baseline.mkdir()
        (baseline / "verified.json").write_text(json.dumps({
            "baseline_jar_sha256": "jar", "trace_sha256": "trace",
            "fixture_source_sha256": "fixture", "case_sha256": {"one": "case"}}))
        (lane / "receipt.json").write_text(json.dumps({
            "artifact_sha256": {"target": digest(artifacts["target"])},
            "trace_sha256": "candidate-trace"}))
        (self.root / "publication.log").write_text("published\n")
        (self.root / "publication.json").write_text(json.dumps({
            "candidate_commit": "commit", "source_sha256": "source",
            "publication_log_sha256": digest(self.root / "publication.log"),
            "artifact_sha256": {"target.jar": digest(artifacts["target"])}}))
        case = {"id": "one", "steps": 1, "family": "free-motion"}
        numerical = {"id": "one", "status": "PASSED_NUMERICAL_POLICY",
                     "qualification": "UNPASSED", "different_numeric_values": 0}
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
            stack.enter_context(patch("baseline_capture.verify_case_slices"))
            stack.enter_context(patch("receipt.verify"))
            stack.enter_context(patch("run.HOST_TASKS", {"jvm": "jvmTest"}))
            stack.enter_context(patch("run.MATRIX_METHODS", tuple(str(i) for i in range(15))))
            stack.enter_context(patch("run.STAGED", self.root))
            stack.enter_context(patch("run.artifacts", return_value=artifacts))
            stack.enter_context(patch("run.clean_identity", return_value=("commit", "source")))
            stack.enter_context(patch("run.runtime", return_value=runtime))
            for archive_consistent in (False, True):
                with patch("prospective_compare.verify_numeric_probe",
                           return_value=archive_consistent):
                    result = compare_host(baseline, lane, set())
                self.assertEqual(result["passed_case_policy"], 0)
                self.assertEqual(result["results"][0]["qualification"], "UNPASSED")
                self.assertEqual(result["numeric_probe"],
                                 "UNPASSED_UNBOUND_PRODUCER" if archive_consistent else
                                 "UNPASSED_NOT_EXECUTED")

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

    def policy_result(self, reference, candidate, case, catalog):
        self.reference.write_text(''.join(json.dumps(row) + "\n" for row in reference))
        self.candidate.write_text(''.join(json.dumps(row) + "\n" for row in candidate))
        return compare_policy_case(self.reference, self.candidate, case, catalog)

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
