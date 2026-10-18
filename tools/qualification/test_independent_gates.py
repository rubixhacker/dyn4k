import json
import hashlib
import gzip
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import independent_gates
import qualify

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migration"))
import journeys
sys.path.pop(0)


ROOT = Path(__file__).resolve().parents[2]
BASE = "e35e3f1ec357b1c44b6d2b742e0d88bc2e91f767"
MANIFEST_REV = "fa5a5d98fc5f85e27f1e30d2b0565caec9f8b3b9"
OLD_MANIFEST_REV = "6f983ad3a36bdc549c32f5d0883b0a47b28e1963"
MANIFEST_SHA256 = "bf94699fb2b7bc5f68070b2baa67a24747a7891c6c6d6e864ed7a17aa9a51240"
OLD_MANIFEST_SHA256 = "60e91e7cab9dcf1c1ccb41eb25fefd6c1579ad147996bb40d94f7fcba91017a3"
LANE = "jvm:Java:minimum:no-optimize"


class IndependentGateSeamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(subprocess.check_output(
            ["git", "show", f"{MANIFEST_REV}:tools/qualification/full-suite-manifest.json"],
            cwd=ROOT))

    def test_approved_manifest_pin_is_reviewed_world_revision(self):
        self.assertEqual(MANIFEST_REV, independent_gates.APPROVED_MANIFEST_REVISION)
        self.assertEqual(MANIFEST_SHA256, independent_gates.APPROVED_MANIFEST_SHA256)
        self.assertEqual(MANIFEST_SHA256, independent_gates.digest(self.manifest))
        self.assertEqual(self.manifest, independent_gates.load_approved_manifest(ROOT))

    def test_public_cli_rejects_old_altered_and_wrong_revision_manifests(self):
        old = json.loads(subprocess.check_output(
            ["git", "show", f"{OLD_MANIFEST_REV}:tools/qualification/full-suite-manifest.json"],
            cwd=ROOT))
        self.assertEqual(OLD_MANIFEST_SHA256, independent_gates.digest(old))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            for label, manifest in (("old", old),
                                    ("altered", {**self.manifest, "id": "altered"})):
                path.write_text(json.dumps(manifest))
                with self.subTest(manifest=label), self.assertRaisesRegex(
                        ValueError, "manifest differs from independently approved complete suite"):
                    independent_gates.main(["--candidate-sha", BASE, "--lane", LANE,
                                            "--manifest", str(path)])
        with mock.patch.object(independent_gates, "APPROVED_MANIFEST_REVISION",
                               OLD_MANIFEST_REV):
            with self.assertRaisesRegex(ValueError, "approved complete-suite manifest changed"):
                independent_gates.main(["--candidate-sha", BASE, "--lane", LANE])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(1, independent_gates.main(
                ["--candidate-sha", BASE, "--lane", LANE]))
        result = json.loads(output.getvalue())
        self.assertEqual(MANIFEST_SHA256, result["manifest_sha256"])
        self.assertEqual("NOT_RUN", result["status"])

    def test_reviewed_manifest_selection_and_source_bindings(self):
        self.assertEqual(21, len(self.manifest["targets"]))
        self.assertEqual(28, len({(lane["target"], lane["runtime"])
                                  for lane in self.manifest["lanes"].values()}))
        self.assertEqual(112, len(self.manifest["lanes"]))
        self.assertEqual(2515, len(self.manifest["cases"]))
        corpus = json.loads((ROOT / "tools/qualification/full-common-corpus.json").read_text())
        self.assertEqual(2385, len(corpus["original_mappings"]))
        self.assertEqual(199, len(corpus["source_files"]))
        self.assertEqual(2512, sum(case["scope"] == "portable" for case in self.manifest["cases"]))
        self.assertEqual(3, sum(case["scope"] == "jvm-only" for case in self.manifest["cases"]))

    def test_missing_archives_keep_every_declared_route_unpassed(self):
        result = independent_gates.evaluate(
            self.manifest, BASE, LANE, {}, ROOT)
        expected = set(self.manifest["lanes"][LANE]["required_gates"])
        expected.update(self.manifest["global_gates"])
        self.assertEqual(expected, set(result["gates"]))
        self.assertEqual({"NOT_RUN"}, {gate["status"] for gate in result["gates"].values()})
        self.assertEqual("NOT_RUN", result["status"])
        self.assertEqual(64, len(result["result_sha256"]))

    def test_reported_pass_needs_independent_archive_pin(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "receipt.json").write_text(json.dumps({"status": "PASSED"}))
            result = independent_gates.evaluate(
                self.manifest, BASE, LANE, {"duplicate-provider": root}, ROOT)
            self.assertEqual("FAILED", result["gates"]["duplicate-provider"]["status"])
            self.assertIn("independent archive", result["gates"]["duplicate-provider"]["reason"])

    def test_every_approved_lane_has_a_consumer_contract(self):
        self.assertEqual(112, len(self.manifest["lanes"]))
        for lane_id, lane in self.manifest["lanes"].items():
            with self.subTest(lane=lane_id):
                contract = independent_gates.consumer_contract(self.manifest, lane_id)
                self.assertEqual(lane["target"], contract["target"])
                self.assertTrue(contract["cases"])

    def test_approved_comparator_accepts_reviewed_blob_and_rejects_stale_pin(self):
        current = "6e9abe839c74ac9be1e8507e4a693b0414e70063f878481c94ab136c7ec89f4f"
        path = "tools/numerical/compare.py"
        self.assertEqual(current, independent_gates.APPROVED_POLICY[path])
        self.assertEqual(current, hashlib.sha256((ROOT / path).read_bytes()).hexdigest())
        self.assertEqual(current, hashlib.sha256(subprocess.check_output(
            ["git", "show", f"8a5c4681838aa1eb1f08ebfb7aa54d6616bb3977:{path}"],
            cwd=ROOT)).hexdigest())
        approved = independent_gates._policy_binding(
            ROOT, "cd21a4bd7d6731a096597f97966db9e02b9de448")
        self.assertEqual(current, approved[path])
        for path, approved in independent_gates.APPROVED_POLICY.items():
            committed = subprocess.check_output(["git", "show", f"{BASE}:{path}"],
                                                cwd=ROOT)
            if path != "tools/numerical/compare.py":
                self.assertEqual(approved, hashlib.sha256(committed).hexdigest())
        with self.assertRaisesRegex(ValueError,
                                    "approved policy/checker blob differs: tools/numerical/compare.py"):
            independent_gates._policy_binding(ROOT, BASE)
        with mock.patch.dict(independent_gates.APPROVED_POLICY,
                             {"tools/numerical/compare.py":
                              "4310fe9ddad700bd591b7708cc1a61e9b307029ca97f5240b608a61fe0430fa3"}):
            with self.assertRaisesRegex(ValueError, "approved policy/checker blob differs"):
                independent_gates._policy_binding(
                    ROOT, "cd21a4bd7d6731a096597f97966db9e02b9de448")

    def test_producer_scope_requires_independently_pinned_raw_manifest(self):
        scope = {"candidate_sha": BASE, "target": "jvm", "runtime": "Java",
                 "runtime_identity": "reviewed JVM runner",
                 "artifact_hashes": {"dyn4k-core": "a" * 64}}
        with self.assertRaisesRegex(ValueError, "producer manifest"):
            independent_gates._producer_scope("migration-journeys", BASE,
                                              {"migration-journeys": scope})

    def test_historical_numerical_source_adapter_matches_producer_git_archive(self):
        candidate = "cd21a4bd7d6731a096597f97966db9e02b9de448"
        self.assertEqual(
            "7958113412c14be8e106706a77871eba4dc8c4e1335c38fd01c7b9e18d26e12d",
            independent_gates.verified_numerical_source_sha256(ROOT, candidate))

    def test_prospective_and_joint_obligations_are_separate_when_unexecuted(self):
        gates = independent_gates.evaluate(self.manifest, BASE, LANE, {}, ROOT)["gates"]
        self.assertEqual(318, gates["numerical-parity"]["subgates"]["prospective-rule-arithmetic"]["required_cases"])
        self.assertEqual("NOT_RUN", gates["numerical-parity"]["subgates"]["prospective-rule-arithmetic"]["status"])
        cases = gates["numerical-parity"]["subgates"]["prospective-rule-arithmetic"]["cases"]
        self.assertEqual(318, len(cases))
        self.assertEqual({"NOT_RUN"}, {item["status"] for item in cases.values()})
        self.assertIn("P-J-Angle-ratio-limits-off--1.0", cases)
        joint = gates["physical-correctness"]["profiles"]["weld-pulley"]
        self.assertEqual(2, joint["required_cases"])
        self.assertEqual(36000, joint["steps_per_case"])
        self.assertEqual("NOT_RUN", joint["candidate_status"])
        self.assertEqual("NOT_RUN", gates["physical-correctness"]["profiles"]["nominal"]["candidate_status"])

    def test_nominal_route_needs_36000_step_capture_and_all_profiles_to_pass(self):
        with self.assertRaisesRegex(ValueError, "nominal"):
            independent_gates.verify_nominal_physical_case(
                Path("/tmp"), {"nominal_physical_case": {"key": "wrong"}},
                "cd21a4bd7d6731a096597f97966db9e02b9de448",
                {"dyn4k-core": "a" * 64}, "b" * 64, ROOT)
        self.assertEqual("NOT_RUN", independent_gates.verify_nominal_physical_case(
            Path("/tmp"), {}, "cd21a4bd7d6731a096597f97966db9e02b9de448",
            {"dyn4k-core": "a" * 64}, "b" * 64, ROOT)["candidate_status"])
        passed = {name: {"candidate_status": "PASSED"} for name in
                  ("default-sleep-wake", "configured-sleep-wake", "weld-pulley", "nominal")}
        self.assertEqual("PASSED", independent_gates.physical_status(passed))
        passed["nominal"]["candidate_status"] = "NOT_RUN"
        self.assertEqual("NOT_RUN", independent_gates.physical_status(passed))
        passed["nominal"]["candidate_status"] = "FAILED"
        self.assertEqual("FAILED", independent_gates.physical_status(passed))

    @unittest.skipUnless(
        Path("/tmp/dyn4k-candidate-current-nominal/L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz").is_file(),
        "retained candidate nominal capture is absent")
    def test_retained_real_nominal_capture_replays_all_zero_and_timestep_checks(self):
        capture = Path("/tmp/dyn4k-candidate-current-nominal")
        receipt = json.loads((capture / "receipt.json").read_text())
        self.assertEqual("1a2b3b5174a5b7a438475628e95f376950fc4e4e",
                         receipt["candidate_commit"])
        self.assertEqual(independent_gates.verified_numerical_source_sha256(
            ROOT, receipt["candidate_commit"]), receipt["source_sha256"])
        trace = capture / "L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz"
        self.assertEqual(hashlib.sha256(trace.read_bytes()).hexdigest(),
                         receipt["trace_sha256"])
        nominal = independent_gates._nominal_module(ROOT / "tools/numerical")
        self.assertEqual({"states": 36000, "positive_zero_checks": 216000,
                          "timestep_callbacks": 108001, "exact_timestep_checks": 540005},
                         nominal.audit_trace(trace, 36000, 108001))
        self.assertEqual("FAILED", json.loads((capture / "comparison.json").read_text())["status"])

    @unittest.skipUnless(
        Path("/tmp/dyn4k-restored-nominal/trace/L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz").is_file(),
        "retained frozen nominal reference is absent")
    def test_nominal_route_replays_full_synthetic_positive_and_wrong_artifact(self):
        candidate = "cd21a4bd7d6731a096597f97966db9e02b9de448"
        source_sha = independent_gates.verified_numerical_source_sha256(ROOT, candidate)
        artifact_hash = "a" * 64
        fixture = independent_gates._nominal_module(ROOT / "tools/numerical").compare.load_fixture(
            "nominal-free-motion")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / fixture["reference"]["file"]
            shutil.copy2(Path("/tmp/dyn4k-restored-nominal/trace") / reference.name,
                         reference)
            candidate_trace = root / "candidate.jsonl.gz"
            shutil.copy2(reference, candidate_trace)
            capture = root / "capture.json"
            capture.write_text(json.dumps({
                "candidate_commit": candidate, "source_sha256": source_sha,
                "artifact_sha256": artifact_hash,
                "reference_source_revision": fixture["baseline_source_revision"],
                "reference_artifact_sha256": fixture["baseline_jar_sha256"],
                "reference_trace_sha256": fixture["reference"]["gzip_sha256"],
                "trace_sha256": hashlib.sha256(candidate_trace.read_bytes()).hexdigest(),
                "expected_counts": fixture["counts"],
                "executed_counts": fixture["counts"], "skipped": 0}))
            receipt = {"nominal_physical_case": {"key": "nominal-free-motion",
                       "reference": reference.name, "candidate": candidate_trace.name,
                       "capture_receipt": capture.name}}
            outcome = independent_gates.verify_nominal_physical_case(
                root, receipt, candidate, {"dyn4k-core": artifact_hash}, source_sha, ROOT)
            self.assertEqual("PASSED", outcome["candidate_status"], outcome)
            outcome = independent_gates.verify_nominal_physical_case(
                root, receipt, candidate, {"dyn4k-core": "b" * 64}, source_sha, ROOT)
            self.assertEqual("FAILED", outcome["candidate_status"])

    def test_assembly_requires_every_selected_lane_and_digest_bound_results(self):
        candidate = "a17d7cfce8b8abb8cdc4c5f5f31285f74c9b7149"
        with self.assertRaisesRegex(ValueError, "112"):
            independent_gates.evaluate_assembly(self.manifest, candidate, {}, ROOT)
        selections = {lane: {"archives": {}} for lane in self.manifest["lanes"]}
        assembled = independent_gates.evaluate_assembly(self.manifest, candidate,
                                                         selections, ROOT)
        self.assertEqual(112, assembled["required_lanes"])
        self.assertEqual("NOT_RUN", assembled["status"])
        self.assertEqual(2515, assembled["selected_cases"][LANE])
        self.assertEqual(assembled["result_sha256"], independent_gates.digest(
            {key: value for key, value in assembled.items() if key != "result_sha256"}))
        with tempfile.TemporaryDirectory() as temporary:
            inputs = Path(temporary) / "assembly.json"
            inputs.write_text(json.dumps(selections))
            cli = subprocess.run([
                sys.executable, str(ROOT / "tools/qualification/independent_gates.py"),
                "--repository", str(ROOT), "--candidate-sha", candidate,
                "--assembly", str(inputs)], capture_output=True, text=True)
            self.assertEqual(1, cli.returncode)
            self.assertEqual("NOT_RUN", json.loads(cli.stdout)["status"])
        selections[LANE]["expected_artifact_hashes"] = {"dyn4k-core": "wrong"}
        with self.assertRaisesRegex(ValueError, "artifact"):
            independent_gates.evaluate_assembly(self.manifest, candidate,
                                                 selections, ROOT)

    def test_assembly_adapter_emits_selected_cases_only_from_verified_full_routes(self):
        candidate = "a17d7cfce8b8abb8cdc4c5f5f31285f74c9b7149"
        selections = {lane: {"archives": {}} for lane in self.manifest["lanes"]}
        def verified(_manifest, _candidate, lane_id, *_args):
            names = self.manifest["lanes"][lane_id]["required_gates"] + self.manifest["global_gates"]
            result = {"candidate_sha": candidate, "lane": lane_id,
                      "expected_archive_digests": {name: "a" * 64 for name in names},
                      "gates": {name: {"status": "PASSED", "archive_sha256": "b" * 64,
                                       "complete_selected_suite": name == "staged-consumer"}
                                for name in names}, "status": "PASSED"}
            result["result_sha256"] = independent_gates.digest(result)
            return result
        with mock.patch.object(independent_gates, "evaluate", side_effect=verified):
            assembled = independent_gates.evaluate_assembly(
                self.manifest, candidate, selections, ROOT)
        self.assertEqual("PASSED", assembled["status"])
        self.assertEqual(112, len(assembled["qualify_adapter"]))
        self.assertEqual(2515, len(assembled["qualify_adapter"][LANE]["case_results"]))
        self.assertEqual({"PASSED"}, {row["status"] for row in
                                        assembled["qualify_adapter"][LANE]["case_results"]})
        def incomplete(*args):
            result = verified(*args)
            result["gates"]["staged-consumer"]["complete_selected_suite"] = False
            result["result_sha256"] = independent_gates.digest(
                {key: value for key, value in result.items() if key != "result_sha256"})
            return result
        with mock.patch.object(independent_gates, "evaluate", side_effect=incomplete):
            with self.assertRaisesRegex(ValueError, "complete selected-suite"):
                independent_gates.evaluate_assembly(self.manifest, candidate,
                                                     selections, ROOT)

    def test_sustained_adapter_requires_external_key_and_reviewed_producer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "evidence").mkdir()
            (root / "evidence/archive.json").write_text(json.dumps({
                "schema": 1, "route": "sustained-raw-v1", "source_commit": BASE,
                "artifacts": {"jvm.java": {"core": {"sha256": "a" * 64},
                                            "kotlin": {"sha256": "b" * 64}}}}))
            scope = {"producer_manifest_hashes": {"evidence/archive.json":
                     hashlib.sha256((root / "evidence/archive.json").read_bytes()).hexdigest()},
                     "verifier_sha256": "c" * 64}
            with self.assertRaisesRegex(independent_gates.IncompleteEvidence,
                                        "trusted key"):
                independent_gates._performance_resource(
                    root, BASE, {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64},
                    scope, ROOT)
            with tempfile.TemporaryDirectory() as key_temporary:
                key = Path(key_temporary) / "trusted.key"
                key.write_bytes(b"independent-archive-key-1234567890")
                with self.assertRaisesRegex(independent_gates.IncompleteEvidence,
                                            "not assembled"):
                    independent_gates._performance_resource(
                        root, BASE, {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64},
                        scope, ROOT, key)
                with self.assertRaisesRegex(ValueError, "dyn4k-core JAR differs"):
                    independent_gates._performance_resource(
                        root, BASE, {"dyn4k-core": "e" * 64, "dyn4k": "b" * 64},
                        scope, ROOT, key)
            full_scope = {"candidate_sha": BASE, "target": "jvm", "runtime": "Java",
                          "runtime_identity": "reference host", "artifact_hashes": {
                              "dyn4k-core": "a" * 64, "dyn4k": "b" * 64}, **scope}
            with self.assertRaisesRegex(ValueError, "policy pin"):
                independent_gates._producer_scope("performance-resource", BASE,
                                                  {"performance-resource": full_scope})

    def test_producer_scope_is_part_of_digest_bound_public_result(self):
        scope = {"candidate_sha": BASE, "target": "jvm", "runtime": "Java",
                 "runtime_identity": "reviewed JVM runner",
                 "artifact_hashes": {"dyn4k-core": "a" * 64}}
        result = independent_gates.evaluate(
            self.manifest, BASE, LANE, {}, ROOT,
            expected_producer_scopes={"migration-journeys": scope})
        self.assertEqual(scope, result["expected_producer_scopes"]["migration-journeys"])
        self.assertEqual("NOT_RUN", result["gates"]["migration-journeys"]["status"])

    def test_prospective_adapter_rejects_a_reported_pass_without_318_raw_cases(self):
        source_sha = independent_gates.verified_numerical_source_sha256(ROOT, BASE)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = {"status": "PASSED", "prospective_cases": [],
                       "prospective_catalog_sha256": independent_gates.PROSPECTIVE_POLICY_SHA256}
            with self.assertRaisesRegex(ValueError, "318 prospective"):
                independent_gates.verify_prospective_case_subgates(
                    root, receipt, ROOT, BASE, {"dyn4k-core": "a" * 64}, source_sha)

    def test_prospective_adapter_loads_pinned_checker_then_demands_raw_case_bytes(self):
        candidate = independent_gates.PROSPECTIVE_POLICY_REVISION
        identities = independent_gates.approved_prospective_cases(str(ROOT))
        receipt = {"status": "PASSED",
                   "prospective_catalog_sha256": independent_gates.PROSPECTIVE_POLICY_SHA256,
                   "prospective_cases": [
                       {"id": case, "reference": "missing.jsonl", "candidate": "missing.jsonl",
                        "capture_receipt": "missing.json", "arithmetic_audit": "missing-audit.json"}
                       for case in identities]}
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "raw archive file is missing"):
                independent_gates.verify_prospective_case_subgates(
                    Path(temporary), receipt, ROOT, candidate,
                    {"dyn4k-core": "a" * 64},
                    independent_gates.verified_numerical_source_sha256(ROOT, candidate))

    def test_prospective_arithmetic_requires_raw_target_process_and_oracle_pin(self):
        case = "geometry-boundary-s0-o0-d0"
        candidate = independent_gates.PROSPECTIVE_POLICY_REVISION
        source_sha = independent_gates.verified_numerical_source_sha256(ROOT, candidate)
        identity = {"case_id": case, "candidate_commit": candidate,
                    "source_sha256": source_sha, "artifact_sha256": "a" * 64,
                    "trace_sha256": "b" * 64}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "arithmetic producer manifest"):
                independent_gates._target_arithmetic_evidence(root, identity, identity, ROOT)
            payload = root / "target-payload.json"
            payload.write_text(json.dumps({"case_id": case, "runtime": "Java 21",
                                           "operations": [{"kind": "binary64", "value": "0"}]}))
            output = root / "target-stdout.txt"
            output.write_text(f"ARITHMETIC_CASE={case}\n")
            process = root / "target-process.json"
            process.write_text(json.dumps({"command": ["java", "CandidateArithmetic"],
                                           "exit_code": 0, "started_ns": 1,
                                           "finished_ns": 2, "stdout": output.name,
                                           "stdout_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}))
            audit = {**identity, "schema": "target-arithmetic-evidence/1",
                     "oracle_revision": independent_gates.ROTATION_ORACLE_REVISION,
                     "oracle_sha256": independent_gates.ROTATION_ORACLE_SHA256,
                     "target_payload": payload.name,
                     "target_payload_sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
                     "process_receipt": process.name,
                     "process_receipt_sha256": hashlib.sha256(process.read_bytes()).hexdigest()}
            self.assertEqual("NOT_RUN", independent_gates._target_arithmetic_evidence(
                root, audit, identity, ROOT))
            audit["oracle_sha256"] = "f" * 64
            with self.assertRaisesRegex(ValueError, "approved arithmetic oracle"):
                independent_gates._target_arithmetic_evidence(root, audit, identity, ROOT)
            audit["oracle_sha256"] = independent_gates.ROTATION_ORACLE_SHA256
            audit["oracle"] = {"binding": "missing.json"}
            with self.assertRaisesRegex(ValueError, "oracle raw contract"):
                independent_gates._target_arithmetic_evidence(root, audit, identity, ROOT)
            files = {"binding": "binding.json", "receipt": "producer.json",
                     "target_source": "source.kt", "artifact": "core.jar"}
            for name in files.values():
                (root / name).write_bytes(b"raw arithmetic producer bytes")
            audit["oracle"] = {"target_source_git_path": "README.md"}
            for key, name in files.items():
                audit["oracle"][key] = name
                audit["oracle"][key + "_sha256"] = hashlib.sha256(
                    (root / name).read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "artifact differs"):
                independent_gates._target_arithmetic_evidence(root, audit, identity, ROOT)
            audit["oracle"]["binding_sha256"] = "e" * 64
            with self.assertRaisesRegex(ValueError, "oracle binding differs"):
                independent_gates._target_arithmetic_evidence(root, audit, identity, ROOT)
            oracle = independent_gates._rotation_oracle_module(str(ROOT))
            self.assertEqual("UNPASSED", oracle.verify_rotation_arithmetic(
                {}, {"id": case}, {}, {}, 0)["status"])

    def test_joint_adapter_rejects_reported_pass_without_both_raw_cases(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "36,000-step candidate Weld and Pulley"):
                independent_gates.verify_joint_physical_cases(
                    Path(temporary), {"status": "PASSED"}, BASE,
                    {"dyn4k-core": "a" * 64},
                    independent_gates.verified_numerical_source_sha256(ROOT, BASE))

    def test_performance_global_scope_binds_own_jvm_binaries_before_raw_audit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            started = time.time_ns() - 1_000_000
            (root / "stdout.txt").write_text("performance runner started\n")
            os.utime(root / "stdout.txt", ns=(started + 1, started + 1))
            scope = {"candidate_sha": BASE, "target": "jvm", "runtime": "Java",
                     "runtime_identity": "JDK 21 benchmark host",
                     "artifact_hashes": {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64},
                     "producer_manifest_hashes": {
                         "evidence/candidate-identity-at-pilot.json": "f" * 64}}
            receipt = {"schema": 1, "status": "PASSED", "candidate_sha": BASE,
                       "source_tree": subprocess.check_output(
                           ["git", "rev-parse", f"{BASE}^{{tree}}"], cwd=ROOT, text=True).strip(),
                       "lane": None, "runtime_identity": scope["runtime_identity"],
                       "artifact_hashes": scope["artifact_hashes"], "producer_scope": scope,
                       "process": {"command": ["python3", "tools/performance/verify_candidate_archive.py"],
                                   "exit_code": 0, "started_ns": started,
                                   "finished_ns": started + 2_000_000, "stdout": "stdout.txt"},
                       "files": [{"path": "stdout.txt",
                                  "sha256": hashlib.sha256((root / "stdout.txt").read_bytes()).hexdigest(),
                                  "mtime_ns": started + 1}]}
            (root / "receipt.json").write_text(json.dumps(receipt))
            pin = independent_gates.archive_digest(root)

            def checked(selected):
                return independent_gates.evaluate(
                    self.manifest, BASE, "linuxX64:Linux x64:minimum:debug-g",
                    {"performance-resource": root}, ROOT,
                    {"dyn4k-core": "c" * 64, "dyn4k": "d" * 64},
                    "native runner", {"performance-resource": pin},
                    expected_producer_scopes={"performance-resource": selected})[
                        "gates"]["performance-resource"]

            self.assertEqual("FAILED", checked(scope)["status"])
            self.assertIn("evidence", checked(scope)["reason"])
            wrong = {**scope, "artifact_hashes": {"dyn4k-core": "e" * 64,
                                                      "dyn4k": "b" * 64}}
            self.assertIn("producing artifact/runtime scope",
                          checked(wrong)["reason"])
            wrong_sha = {**scope, "candidate_sha": "f" * 40}
            self.assertIn("producing source commit", checked(wrong_sha)["reason"])

    @unittest.skipUnless(
        Path("/tmp/dyn4k-candidate-exact-weld-physical.jsonl").is_file()
        and Path("/tmp/dyn4k-candidate-exact-pulley-physical.jsonl").is_file(),
        "retained real candidate Weld/Pulley traces are absent")
    def test_joint_physical_adapter_replays_real_36000_step_captures(self):
        candidate = "c390dd9208988b523d5fd886c6eb9c28dd7a5362"
        source_sha = independent_gates.verified_numerical_source_sha256(ROOT, candidate)
        artifact = "b6986afbab28c9410ad471abdde038103a9acd6d161750d601f4a61de8efbd4d"
        rows = [{"case": case, "candidate": f"dyn4k-candidate-exact-{name}-physical.jsonl",
                 "capture_receipt": f"dyn4k-candidate-exact-{name}-physical-receipt.json"}
                for case, name in (("weld-spring-equal", "weld"), ("pulley-taut", "pulley"))]
        verified = independent_gates.verify_joint_physical_cases(
            Path("/tmp"), {"joint_physical_cases": rows}, candidate,
            {"dyn4k-core": artifact}, source_sha)
        self.assertEqual("PASSED", verified["candidate_status"])
        self.assertEqual({"anchor_gap_m": 0, "angular_error_rad": 0},
                         verified["failures"]["weld-spring-equal"])
        self.assertEqual({"absolute_rope_error_m": 0},
                         verified["failures"]["pulley-taut"])
        with self.assertRaisesRegex(ValueError, "candidate physical capture identity"):
            independent_gates.verify_joint_physical_cases(
                Path("/tmp"), {"joint_physical_cases": rows}, candidate,
                {"dyn4k-core": "e" * 64}, source_sha)
        with tempfile.TemporaryDirectory() as temporary:
            altered_root = Path(temporary)
            for row in rows:
                for field in ("candidate", "capture_receipt"):
                    shutil.copy2(Path("/tmp") / row[field], altered_root / row[field])
            weld = altered_root / rows[0]["candidate"]
            raw = weld.read_bytes()
            header, remainder = raw.split(b"\n", 1)
            changed = json.loads(header)
            changed["source_revision"] = BASE
            weld.write_bytes(json.dumps(changed).encode() + b"\n" + remainder)
            capture = altered_root / rows[0]["capture_receipt"]
            resealed = json.loads(capture.read_text())
            resealed["trace_sha256"] = hashlib.sha256(weld.read_bytes()).hexdigest()
            capture.write_text(json.dumps(resealed))
            with self.assertRaisesRegex(ValueError, "candidate physical input or source identity"):
                independent_gates.verify_joint_physical_cases(
                    altered_root, {"joint_physical_cases": rows}, candidate,
                    {"dyn4k-core": artifact}, source_sha)

    def test_physical_gate_keeps_default_reference_failure_and_port_gap_separate(self):
        physical = independent_gates.evaluate(
            self.manifest, BASE, LANE, {}, ROOT)["gates"]["physical-correctness"]
        self.assertEqual("NOT_RUN", physical["status"])
        self.assertEqual("FAILED_125847_OF_126000",
                         physical["profiles"]["default-sleep-wake"]["approved_reference_status"])
        for profile in ("default-sleep-wake", "configured-sleep-wake",
                        "weld-pulley", "nominal"):
            self.assertEqual("NOT_RUN", physical["profiles"][profile]["candidate_status"])

    def test_publication_audit_requires_all_21_target_binary_hashes(self):
        targets = {row["target"] for row in qualify.matrix()}
        self.assertEqual(21, len(targets))
        hashes = {target: {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64}
                  for target in targets}
        self.assertEqual(hashes, independent_gates._validated_all_target_hashes(hashes))
        del hashes[next(target for target in targets if target != "jvm")]
        with self.assertRaisesRegex(ValueError, "21-target"):
            independent_gates._validated_all_target_hashes(hashes)

    def test_publication_compares_unselected_target_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / "staged"
            staging.mkdir()
            hashes = {}
            targets = {row["target"] for row in qualify.matrix()}
            for target in targets:
                hashes[target] = {}
                for module in qualify.MODULES:
                    path = staging / qualify.target_binary_path(module, target)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(f"{target}/{module}".encode())
                    hashes[target][module] = hashlib.sha256(path.read_bytes()).hexdigest()
            lane = self.manifest["lanes"][LANE]
            with mock.patch.object(qualify, "audit_staging", return_value={"status": "PASSED", "artifacts": []}):
                self.assertIn("full staged audit verified",
                              independent_gates._staged_publication(
                                  root, BASE, lane, hashes["jvm"], ROOT, hashes))
                target = next(target for target in targets if target != "jvm")
                (staging / qualify.target_binary_path("dyn4k-core", target)).write_bytes(b"mutated")
                with self.assertRaisesRegex(ValueError, "independent audit"):
                    independent_gates._staged_publication(
                        root, BASE, lane, hashes["jvm"], ROOT, hashes)

    def test_duplicate_provider_requires_raw_graph_and_diagnostic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            graph = "org.dyn4j:dyn4j:6.0.0\nio.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1\n"
            (root / "graph.txt").write_text(graph)
            (root / "stderr.txt").write_text(
                "duplicate org.dyn4j provider: exclude org.dyn4j:dyn4j\n")
            (root / "stdout.txt").write_text(
                f"QUALIFICATION_LANE={LANE}\n> Task :diagnoseDuplicateProviders\nBUILD FAILED\n"
                f"QUALIFICATION_PROVIDER_GRAPH_SHA256={hashlib.sha256((root / 'graph.txt').read_bytes()).hexdigest()}\n")
            started = time.time_ns() - 1_000_000
            finished = time.time_ns() + 1_000_000
            artifact_hashes = {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64}
            receipt = {
                "schema": 1, "status": "PASSED", "candidate_sha": BASE,
                "source_tree": subprocess.check_output(
                    ["git", "rev-parse", f"{BASE}^{{tree}}"], cwd=ROOT, text=True).strip(),
                "lane": LANE, "target": "jvm", "runtime": "Java",
                "version": "minimum", "configuration": "no-optimize",
                "runtime_identity": "OpenJDK 8 test fixture", "artifact_hashes": dict(artifact_hashes),
                "process": {"command": ["./gradlew", "diagnoseDuplicateProviders"],
                            "exit_code": 1, "started_ns": started,
                            "finished_ns": finished, "stderr": "stderr.txt",
                            "stdout": "stdout.txt"},
                "provider_graph": "graph.txt",
                "files": [{"path": name,
                           "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
                           "mtime_ns": started + 1}
                          for name in ("graph.txt", "stderr.txt", "stdout.txt")],
            }
            for name in ("graph.txt", "stderr.txt", "stdout.txt"):
                os.utime(root / name, ns=(started + 1, started + 1))
            (root / "receipt.json").write_text(json.dumps(receipt))

            def status():
                try:
                    pin = independent_gates.archive_digest(root)
                except ValueError:
                    pin = "0" * 64
                return independent_gates.evaluate(
                    self.manifest, BASE, LANE, {"duplicate-provider": root}, ROOT,
                    artifact_hashes, "OpenJDK 8 test fixture",
                    {"duplicate-provider": pin})["gates"]["duplicate-provider"]

            self.assertEqual("PASSED", status()["status"])
            receipt["process"]["command"] = ["echo", "diagnoseDuplicateProviders"]
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", status()["status"])
            with tempfile.TemporaryDirectory() as audit_temporary:
                audit = Path(audit_temporary)
                (audit / "hashes.json").write_text(json.dumps(artifact_hashes))
                (audit / "digests.json").write_text(json.dumps({
                    "duplicate-provider": independent_gates.archive_digest(root)}))
                cli = subprocess.run([
                    sys.executable, str(ROOT / "tools/qualification/independent_gates.py"),
                    "--repository", str(ROOT), "--candidate-sha", BASE,
                    "--lane", LANE, "--expected-artifacts", str(audit / "hashes.json"),
                    "--expected-archive-digests", str(audit / "digests.json"),
                    "--expected-runtime-identity", "OpenJDK 8 test fixture",
                    "--archive", f"duplicate-provider={root}"], capture_output=True, text=True)
                self.assertEqual(1, cli.returncode)
                self.assertIn("execution launcher",
                              json.loads(cli.stdout)["gates"]["duplicate-provider"]["reason"])
            receipt["process"]["command"] = ["./gradlew", "diagnoseDuplicateProviders"]
            (root / "receipt.json").write_text(json.dumps(receipt))
            receipt["artifact_hashes"]["dyn4k-core"] = "0" * 64
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", status()["status"])
            receipt["artifact_hashes"]["dyn4k-core"] = "a" * 64
            receipt["source_tree"] = "0" * 40
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", status()["status"])
            receipt["source_tree"] = subprocess.check_output(
                ["git", "rev-parse", f"{BASE}^{{tree}}"], cwd=ROOT, text=True).strip()
            (root / "graph.txt").write_text("org.dyn4j:dyn4j:6.0.0\n")
            self.assertEqual("FAILED", status()["status"])
            (root / "graph.txt").write_text(graph)
            receipt["files"][0]["mtime_ns"] = finished + 1
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", status()["status"])
            receipt["files"][0]["mtime_ns"] = started + 1
            receipt["files"].append(dict(receipt["files"][0]))
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", status()["status"])
            receipt["files"].pop()
            (root / "link.txt").symlink_to(root / "graph.txt")
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", status()["status"])
            (root / "link.txt").unlink()
            receipt["lane"] = "jvm:Java:minimum:default"
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", status()["status"])
            receipt["lane"] = LANE
            receipt["candidate_sha"] = "f" * 40
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", status()["status"])
            receipt["candidate_sha"] = BASE
            receipt["files"][0]["path"] = "../graph.txt"
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", status()["status"])

    def test_every_route_rejects_reported_green_without_raw_contract(self):
        names = (set(self.manifest["lanes"][LANE]["required_gates"])
                 | set(self.manifest["global_gates"]))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "receipt.json").write_text(json.dumps({"status": "PASSED"}))
            for gate in names:
                with self.subTest(gate=gate):
                    observed = independent_gates.evaluate(
                        self.manifest, BASE, LANE, {gate: root}, ROOT,
                        expected_archive_digests={gate: independent_gates.archive_digest(root)})
                    self.assertEqual("FAILED", observed["gates"][gate]["status"])

    def test_every_route_rejects_wrong_lane_and_candidate(self):
        names = (set(self.manifest["lanes"][LANE]["required_gates"])
                 | set(self.manifest["global_gates"]))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "stdout.txt").write_text("execution\n")
            started = time.time_ns() - 1_000_000
            os.utime(root / "stdout.txt", ns=(started + 1, started + 1))
            receipt = {
                "schema": 1, "status": "PASSED", "candidate_sha": BASE,
                "source_tree": subprocess.check_output(
                    ["git", "rev-parse", f"{BASE}^{{tree}}"], cwd=ROOT, text=True).strip(),
                "lane": LANE, "target": "jvm", "runtime": "Java",
                "version": "minimum", "configuration": "no-optimize",
                "runtime_identity": "OpenJDK 8", "artifact_hashes":
                    {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64},
                "process": {"command": ["./gradlew", "check"], "exit_code": 0,
                            "started_ns": started, "finished_ns": started + 2_000_000,
                            "stdout": "stdout.txt"},
                "files": [{"path": "stdout.txt",
                           "sha256": hashlib.sha256((root / "stdout.txt").read_bytes()).hexdigest(),
                           "mtime_ns": started + 1}],
            }
            for field, wrong in (("candidate_sha", "f" * 40), ("lane", "other")):
                receipt[field] = wrong
                (root / "receipt.json").write_text(json.dumps(receipt))
                for gate in names:
                    with self.subTest(gate=gate, field=field):
                        result = independent_gates.evaluate(
                            self.manifest, BASE, LANE, {gate: root}, ROOT,
                            receipt["artifact_hashes"], "OpenJDK 8",
                            {gate: independent_gates.archive_digest(root)})["gates"][gate]
                        self.assertEqual("FAILED", result["status"])
                        self.assertIn("candidate" if field == "candidate_sha" else "lane",
                                      result["reason"])
                receipt[field] = BASE if field == "candidate_sha" else LANE
            (root / "receipt.json").write_text(json.dumps(receipt))
            for gate in names:
                with self.subTest(gate=gate, missing="producer raw"):
                    result = independent_gates.evaluate(
                        self.manifest, BASE, LANE, {gate: root}, ROOT,
                        receipt["artifact_hashes"], "OpenJDK 8",
                        {gate: independent_gates.archive_digest(root)})["gates"][gate]
                    self.assertEqual("FAILED", result["status"])

    def test_external_unavailability_needs_bound_observation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = {"schema": 1, "status": "UNAVAILABLE", "candidate_sha": BASE,
                       "lane": LANE, "reason": "no physical device attached",
                       "observed_by": "device-lab", "observed_at_ns": time.time_ns()}
            (root / "receipt.json").write_text(json.dumps(receipt))
            def result():
                return independent_gates.evaluate(
                    self.manifest, BASE, LANE,
                    {"physical-correctness": root}, ROOT)["gates"]["physical-correctness"]
            self.assertEqual("UNAVAILABLE", result()["status"])
            receipt["lane"] = "other"
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", result()["status"])
            self.assertEqual("FAILED", independent_gates.evaluate(
                self.manifest, BASE, LANE, {"migration-journeys": root}, ROOT
            )["gates"]["migration-journeys"]["status"])

    def test_review_requires_two_distinct_raw_sol_sessions_and_resolved_findings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            started = time.time_ns() - 1_000_000
            finished = time.time_ns() + 1_000_000
            hashes = {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64}
            scope = {"candidate_sha": BASE, "target": "source", "runtime": "codex",
                     "runtime_identity": "review CLI", "artifact_hashes": {},
                     "producer_manifest_hashes": {}}
            receipt = {
                "schema": 1, "status": "PASSED", "candidate_sha": BASE,
                "source_tree": subprocess.check_output(
                    ["git", "rev-parse", f"{BASE}^{{tree}}"], cwd=ROOT, text=True).strip(),
                "lane": LANE, "target": "jvm", "runtime": "Java",
                "version": "minimum", "configuration": "no-optimize",
                "runtime_identity": "review CLI", "artifact_hashes": {},
                "producer_scope": scope,
                "process": {"command": ["codex", "exec", "review"], "exit_code": 0,
                            "started_ns": started, "finished_ns": finished},
            }

            def write():
                files = [file for file in root.iterdir() if file.name != "receipt.json"]
                scope["producer_manifest_hashes"] = {
                    f"{kind}.json": hashlib.sha256((root / f"{kind}.json").read_bytes()).hexdigest()
                    for kind in ("standards", "spec") if (root / f"{kind}.json").is_file()}
                for file in files:
                    os.utime(file, ns=(started + 1, started + 1))
                receipt["files"] = [{"path": file.name,
                                     "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                                     "mtime_ns": started + 1} for file in files]
                (root / "receipt.json").write_text(json.dumps(receipt))

            def status():
                return independent_gates.evaluate(
                    self.manifest, BASE, LANE, {"independent-review": root}, ROOT,
                    hashes, "review CLI",
                    {"independent-review": independent_gates.archive_digest(root)},
                    expected_producer_scopes={"independent-review": scope})["gates"]["independent-review"]["status"]

            def write_session(kind, session_id, findings):
                reviewed = (["AGENTS.md", "docs/agents/writing.md"] if kind == "standards"
                            else ["docs/specs/complete-port.md",
                                  "docs/planning/acceptance-implementation.md"])
                assessment = "Reviewed the exact final head against the required source and acceptance obligations."
                report = {"review_kind": kind, "candidate_sha": BASE,
                          "model": "gpt-6-sol", "session_id": session_id,
                          "verdict": "PASSED", "findings": findings,
                          "assessment": assessment, "reviewed_paths": reviewed}
                (root / f"{kind}.json").write_text(json.dumps(report))
                raw = {"kind": "independent-review-result", "review_kind": kind,
                       "candidate_sha": BASE, "verdict": "PASSED", "findings": findings,
                       "assessment": assessment, "reviewed_paths": reviewed}
                messages = (
                    {"type": "session_meta", "payload": {"id": session_id}},
                    {"type": "turn_context", "payload": {"model": "gpt-6-sol"}},
                    {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                                                      "content": [{"type": "output_text", "text": json.dumps(raw)}]}},
                )
                (root / f"{kind}.jsonl").write_text(
                    "\n".join(json.dumps(item) for item in messages) + "\n")

            for kind, session_id in (("standards", "session-a"), ("spec", "session-b")):
                write_session(kind, session_id, [])
                write()
                self.assertEqual("FAILED" if kind == "standards" else "PASSED", status())
            with (root / "spec.jsonl").open("a") as stream:
                stream.write(json.dumps({"type": "response_item", "payload": {
                    "findings": [{"id": "hidden-p1", "severity": "P1"}]}}) + "\n")
            write()
            self.assertEqual("FAILED", status())
            write_session("spec", "session-b", [])
            finding = {"id": "finding-1", "severity": "P1", "description": "resolve a defect"}
            write_session("spec", "session-b", [finding])
            write()
            self.assertEqual("FAILED", status())
            finding["resolution"] = {
                "status": "RESOLVED", "candidate_sha": BASE, "evidence": "README.md",
                "evidence_sha256": hashlib.sha256(subprocess.check_output(
                    ["git", "show", f"{BASE}:README.md"], cwd=ROOT)).hexdigest()}
            write_session("spec", "session-b", [finding])
            write()
            self.assertEqual("PASSED", status())
            receipt["lane"] = None
            write()
            native = "linuxX64:Linux x64:minimum:debug-g"
            native_hashes = {"dyn4k-core": "c" * 64, "dyn4k": "d" * 64}
            native_result = independent_gates.evaluate(
                self.manifest, BASE, native, {"independent-review": root}, ROOT,
                native_hashes, "native runner",
                {"independent-review": independent_gates.archive_digest(root)},
                expected_producer_scopes={"independent-review": scope})
            self.assertEqual("PASSED", native_result["gates"]["independent-review"]["status"])
            wrong_manifest_scope = {**scope, "producer_manifest_hashes": {
                **scope["producer_manifest_hashes"], "spec.json": "e" * 64}}
            rejected_manifest = independent_gates.evaluate(
                self.manifest, BASE, native, {"independent-review": root}, ROOT,
                native_hashes, "native runner",
                {"independent-review": independent_gates.archive_digest(root)},
                expected_producer_scopes={"independent-review": wrong_manifest_scope})
            self.assertEqual("FAILED", rejected_manifest["gates"]["independent-review"]["status"])
            receipt["lane"] = LANE
            write()
            wrong_scope = {**scope, "target": "jvm"}
            rejected = independent_gates.evaluate(
                self.manifest, BASE, LANE, {"independent-review": root}, ROOT,
                hashes, "review CLI",
                {"independent-review": independent_gates.archive_digest(root)},
                expected_producer_scopes={"independent-review": wrong_scope})[
                    "gates"]["independent-review"]
            self.assertEqual("FAILED", rejected["status"])
            (root / "spec.json").write_text(json.dumps({"review_kind": "spec", "candidate_sha": BASE,
                "model": "gpt-6-sol", "session_id": "session-b", "verdict": "PASSED", "findings": []}))
            write()
            self.assertEqual("FAILED", status())

    def test_staged_consumer_checks_frozen_raw_xml_and_resolved_binary_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = json.loads(subprocess.check_output(
                ["git", "show", f"{BASE}:tools/qualification/foundation-probes.json"],
                cwd=ROOT))
            group = next(item for item in manifest["groups"] if item["id"] == "consumer-jvm")
            expected = qualify.expected_probe_cases(manifest, group)
            suite = ET.Element("testsuite", tests=str(len(expected)), failures="0",
                               errors="0", skipped="0", time="0.1")
            for classname, name in expected:
                ET.SubElement(suite, "testcase", classname=classname, name=name, time="0.1")
            (root / "consumer.xml").write_bytes(ET.tostring(suite))
            (root / "graph.txt").write_text(
                "io.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1\n"
                "io.github.rubixhacker:dyn4k-jvm:0.1.0-alpha.1\n")
            (root / "core.bin").write_bytes(b"core")
            (root / "api.bin").write_bytes(b"api")
            (root / "stdout.txt").write_text(
                f"QUALIFICATION_LANE={LANE}\n> Task :consumers:qualification:jvmTest\nBUILD SUCCESSFUL\n"
                + "".join(f"QUALIFICATION_{label}_SHA256={hashlib.sha256((root / name).read_bytes()).hexdigest()}\n"
                          for label, name in (("PROVIDER_GRAPH", "graph.txt"),
                                              ("CONSUMER_XML", "consumer.xml"),
                                              ("RESOLVED_DYN4K_CORE", "core.bin"),
                                              ("RESOLVED_DYN4K", "api.bin"))))
            hashes = {"dyn4k-core": hashlib.sha256(b"core").hexdigest(),
                      "dyn4k": hashlib.sha256(b"api").hexdigest()}
            started = time.time_ns() - 1_000_000
            receipt = {
                "schema": 1, "status": "PASSED", "candidate_sha": BASE,
                "source_tree": subprocess.check_output(
                    ["git", "rev-parse", f"{BASE}^{{tree}}"], cwd=ROOT, text=True).strip(),
                "lane": LANE, "target": "jvm", "runtime": "Java",
                "version": "minimum", "configuration": "no-optimize",
                "runtime_identity": "OpenJDK 8", "artifact_hashes": hashes,
                "process": {"command": ["./gradlew", ":consumers:qualification:jvmTest"],
                            "exit_code": 0, "stdout": "stdout.txt",
                            "started_ns": started, "finished_ns": started + 2_000_000},
                "consumer_group": "consumer-jvm", "consumer_xml": ["consumer.xml"],
                "provider_graph": "graph.txt",
                "resolved_artifacts": {"dyn4k-core": "core.bin", "dyn4k": "api.bin"},
            }

            def write():
                for file in root.iterdir():
                    if file.name != "receipt.json":
                        os.utime(file, ns=(started + 1, started + 1))
                receipt["files"] = [{"path": file.name,
                                     "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                                     "mtime_ns": started + 1}
                                    for file in root.iterdir() if file.name != "receipt.json"]
                (root / "receipt.json").write_text(json.dumps(receipt))

            def status():
                return independent_gates.evaluate(
                    self.manifest, BASE, LANE, {"staged-consumer": root},
                    ROOT, hashes, "OpenJDK 8",
                    {"staged-consumer": independent_gates.archive_digest(root)})["gates"]["staged-consumer"]

            write()
            self.assertEqual("NOT_RUN", status()["status"])
            receipt["process"]["command"] = ["echo", "jvmTest"]
            write()
            self.assertEqual("FAILED", status()["status"])
            with tempfile.TemporaryDirectory() as audit_temporary:
                audit = Path(audit_temporary)
                (audit / "hashes.json").write_text(json.dumps(hashes))
                (audit / "digests.json").write_text(json.dumps({
                    "staged-consumer": independent_gates.archive_digest(root)}))
                cli = subprocess.run([
                    sys.executable, str(ROOT / "tools/qualification/independent_gates.py"),
                    "--repository", str(ROOT), "--candidate-sha", BASE,
                    "--lane", LANE, "--expected-artifacts", str(audit / "hashes.json"),
                    "--expected-archive-digests", str(audit / "digests.json"),
                    "--expected-runtime-identity", "OpenJDK 8",
                    "--archive", f"staged-consumer={root}"], capture_output=True, text=True)
                self.assertEqual(1, cli.returncode)
                self.assertIn("execution launcher",
                              json.loads(cli.stdout)["gates"]["staged-consumer"]["reason"])
            receipt["process"]["command"] = ["./gradlew", ":consumers:qualification:jvmTest"]
            write()
            os.utime(root / "consumer.xml", ns=(1, 1))
            self.assertEqual("FAILED", status()["status"])
            (root / "graph.txt").write_text(
                "io.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1\n")
            write()
            self.assertEqual("FAILED", status()["status"])
            (root / "graph.txt").write_text(
                "io.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1\n"
                "io.github.rubixhacker:dyn4k-jvm:0.1.0-alpha.1\n")
            suite.find("testcase").set("name", "other")
            (root / "consumer.xml").write_bytes(ET.tostring(suite))
            write()
            self.assertEqual("FAILED", status()["status"])

    def test_full_suite_consumer_route_accepts_approved_foundation_lane_case_set(self):
        lane_id = LANE
        lane = self.manifest["lanes"][lane_id]
        contract = independent_gates.consumer_contract(self.manifest, lane_id)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite = ET.Element("testsuite", tests=str(len(contract["cases"])),
                               failures="0", errors="0", skipped="0", time="1")
            for case in contract["cases"]:
                ET.SubElement(suite, "testcase", id=case["id"], time="0.001")
            (root / "consumer.xml").write_bytes(ET.tostring(suite))
            (root / "graph.txt").write_text("".join(
                f"io.github.rubixhacker:{qualify.target_publication_name(module, lane['target'])}:0.1.0-alpha.1\n"
                for module in qualify.MODULES))
            (root / "core.bin").write_bytes(b"native core fixture")
            (root / "api.bin").write_bytes(b"native facade fixture")
            (root / "stdout.txt").write_text(
                f"QUALIFICATION_LANE={lane_id}\n> Task :consumerJvm\nBUILD SUCCESSFUL\n"
                + "".join(f"QUALIFICATION_{label}_SHA256={hashlib.sha256((root / name).read_bytes()).hexdigest()}\n"
                          for label, name in (("PROVIDER_GRAPH", "graph.txt"),
                                              ("CONSUMER_XML", "consumer.xml"),
                                              ("RESOLVED_DYN4K_CORE", "core.bin"),
                                              ("RESOLVED_DYN4K", "api.bin"))))
            hashes = {"dyn4k-core": hashlib.sha256((root / "core.bin").read_bytes()).hexdigest(),
                      "dyn4k": hashlib.sha256((root / "api.bin").read_bytes()).hexdigest()}
            started = time.time_ns() - 1_000_000
            files = [file for file in root.iterdir()]
            for file in files:
                os.utime(file, ns=(started + 1, started + 1))
            receipt = {"schema": 1, "status": "PASSED", "candidate_sha": BASE,
                       "source_tree": subprocess.check_output(
                           ["git", "rev-parse", f"{BASE}^{{tree}}"], cwd=ROOT, text=True).strip(),
                       "lane": lane_id, **{key: lane[key] for key in
                                           ("target", "runtime", "version", "configuration")},
                       "runtime_identity": "selected device fixture", "artifact_hashes": hashes,
                       "process": {"command": ["./gradlew", ":consumerJvm", lane_id],
                                   "exit_code": 0, "started_ns": started,
                                   "finished_ns": started + 2_000_000, "stdout": "stdout.txt"},
                       "consumer_group": "full-suite",
                       "consumer_contract_sha256": independent_gates.digest(contract),
                       "consumer_xml": ["consumer.xml"], "provider_graph": "graph.txt",
                       "resolved_artifacts": {"dyn4k-core": "core.bin", "dyn4k": "api.bin"},
                       "files": [{"path": file.name,
                                  "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                                  "mtime_ns": started + 1} for file in files]}
            (root / "receipt.json").write_text(json.dumps(receipt))
            def result():
                return independent_gates.evaluate(
                    self.manifest, BASE, lane_id, {"staged-consumer": root}, ROOT,
                    hashes, "selected device fixture",
                    {"staged-consumer": independent_gates.archive_digest(root)})["gates"]["staged-consumer"]
            self.assertEqual("PASSED", result()["status"], result()["reason"])
            suite.find("testcase").set("id", "invented:case")
            (root / "consumer.xml").write_bytes(ET.tostring(suite))
            os.utime(root / "consumer.xml", ns=(started + 1, started + 1))
            receipt["files"][0]["sha256"] = hashlib.sha256((root / "consumer.xml").read_bytes()).hexdigest()
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual("FAILED", result()["status"])

    def test_java_source_rejects_legacy_case_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "reviewed full_ci raw archive contract"):
                independent_gates._java_full_ci(
                    Path(temporary), {"producer": "legacy-case-manifest"},
                    "java-source-compatibility", BASE, ROOT,
                    {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64})

    @unittest.skipUnless(Path("/tmp/dyn4k-archive-relocation-copy-7032/lane-manifest.json").is_file(),
                         "reviewed local full_ci archive is absent")
    def test_reviewed_full_ci_archive_replays_unchanged_and_strict_java_gates(self):
        source = Path("/tmp/dyn4k-archive-relocation-copy-7032")
        candidate = "7032b41c780a08c850226eb2c984fb15af444a23"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(source, root / "full-ci")
            (root / "facade.bin").write_bytes(b"separate facade fixture")
            evidence = json.loads((root / "full-ci/result.json").read_text())
            hashes = {"dyn4k-core": evidence["archives"]["staged_jvm_jar"],
                      "dyn4k": hashlib.sha256((root / "facade.bin").read_bytes()).hexdigest()}
            scope = {"candidate_sha": candidate, "target": "jvm", "runtime": "Java",
                     "runtime_identity": "reviewed local archive", "artifact_hashes": hashes,
                     "producer_manifest_hashes": {"full-ci/lane-manifest.json":
                         hashlib.sha256((root / "full-ci/lane-manifest.json").read_bytes()).hexdigest()}}
            started = time.time_ns() - 1_000_000_000
            finished = time.time_ns() + 1_000_000_000
            receipt = {"schema": 1, "status": "PASSED", "candidate_sha": candidate,
                       "source_tree": subprocess.check_output(
                           ["git", "rev-parse", f"{candidate}^{{tree}}"], cwd=ROOT, text=True).strip(),
                       "lane": LANE, "target": "jvm", "runtime": "Java",
                       "version": "minimum", "configuration": "no-optimize",
                       "runtime_identity": "reviewed local archive", "artifact_hashes": hashes,
                       "producer_scope": scope,
                       "process": {"command": ["python3", "tools/compatibility/full_ci.py", "verify"],
                                   "exit_code": 0, "started_ns": started, "finished_ns": finished},
                       "producer": "reviewed-full-ci", "full_ci_archive": "full-ci",
                       "full_ci_manifest_sha256": hashlib.sha256(
                           (root / "full-ci/lane-manifest.json").read_bytes()).hexdigest(),
                       "resolved_artifacts": {
                           "dyn4k-core": "full-ci/archives/dyn4k-core-jvm-0.1.0-alpha.1.jar",
                           "dyn4k": "facade.bin"}}
            files = [path for path in root.rglob("*") if path.is_file()]
            for path in files:
                os.utime(path, ns=(started + 1, started + 1))
            receipt["files"] = [{"path": path.relative_to(root).as_posix(),
                                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                 "mtime_ns": started + 1} for path in files]
            (root / "receipt.json").write_text(json.dumps(receipt))
            pin = independent_gates.archive_digest(root)
            corpus = evidence["corpus"]
            routes = [name for name in corpus if name.startswith(("baseline-javac", "candidate-javac",
                                                                  "android-javac")) and name.count("-java") == 2]
            self.assertEqual(12, len(routes))
            self.assertEqual({2385}, {corpus[name]["cases"] for name in routes})
            for gate in ("unchanged-java-corpus", "java-source-compatibility"):
                with self.subTest(gate=gate):
                    result = independent_gates.evaluate(
                        self.manifest, candidate, LANE, {gate: root}, ROOT, hashes,
                        "reviewed local archive", {gate: pin},
                        expected_producer_scopes={gate: scope})["gates"][gate]
                    self.assertEqual("PASSED", result["status"], result["reason"])
            wrong_manifest_scope = {**scope, "producer_manifest_hashes": {
                "full-ci/lane-manifest.json": "e" * 64}}
            rejected_manifest = independent_gates.evaluate(
                self.manifest, candidate, LANE, {"unchanged-java-corpus": root}, ROOT,
                hashes, "reviewed local archive", {"unchanged-java-corpus": pin},
                expected_producer_scopes={"unchanged-java-corpus": wrong_manifest_scope})
            self.assertEqual("FAILED", rejected_manifest["gates"]["unchanged-java-corpus"]["status"])
            with tempfile.TemporaryDirectory() as audit_temporary:
                audit = Path(audit_temporary)
                (audit / "hashes.json").write_text(json.dumps(hashes))
                (audit / "scopes.json").write_text(json.dumps({"unchanged-java-corpus": scope}))
                (audit / "digests.json").write_text(json.dumps({"unchanged-java-corpus": pin}))
                cli = subprocess.run([
                    sys.executable, str(ROOT / "tools/qualification/independent_gates.py"),
                    "--repository", str(ROOT), "--candidate-sha", candidate,
                    "--lane", LANE, "--expected-artifacts", str(audit / "hashes.json"),
                    "--expected-producer-scopes", str(audit / "scopes.json"),
                    "--expected-archive-digests", str(audit / "digests.json"),
                    "--expected-runtime-identity", "reviewed local archive",
                    "--archive", f"unchanged-java-corpus={root}"],
                    capture_output=True, text=True)
                self.assertEqual("PASSED", json.loads(cli.stdout)["gates"]["unchanged-java-corpus"]["status"])
            (root / "full-ci/logs/run-candidate-javac8-java8.log").write_text("mutated\n")
            result = independent_gates.evaluate(
                self.manifest, candidate, LANE, {"unchanged-java-corpus": root}, ROOT,
                hashes, "reviewed local archive", {"unchanged-java-corpus": pin},
                expected_producer_scopes={"unchanged-java-corpus": scope})
            self.assertEqual("FAILED", result["gates"]["unchanged-java-corpus"]["status"])

    @unittest.skipUnless(
        Path("/tmp/dyn4k-merge-complete-corpus-rotation-migration-journeys-0681a8cd/summary.json").is_file()
        and Path("/tmp/dyn4k-merge-complete-corpus-rotation-gate-wave/build/staging-repository/"
                 "io/github/rubixhacker/dyn4k-core-jvm/0.1.0-alpha.1/"
                 "dyn4k-core-jvm-0.1.0-alpha.1.jar").is_file(),
        "reviewed local migration archive or same-commit staged JVM JAR is absent")
    def test_historical_migration_raw_scenes_replay_and_input_mutation_fails(self):
        source = Path("/tmp/dyn4k-merge-complete-corpus-rotation-migration-journeys-0681a8cd")
        samples = Path("/tmp/dyn4k-migration-preflight/samples")
        if not samples.is_dir():
            self.skipTest("pinned unchanged sample checkout is absent")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "evidence"
            shutil.copytree(source, evidence)
            report = json.loads((evidence / "summary.json").read_text())
            paths = subprocess.check_output(
                ["git", "-C", str(samples), "ls-files", "--", "*.java"], text=True).splitlines()
            rows = []
            for relative in paths:
                original = samples / relative
                copied = evidence / "sources" / relative
                copied.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, copied)
                rows.append(f"{hashlib.sha256(original.read_bytes()).hexdigest()}  {relative}\n")
            (evidence / "sources.sha256").write_text("".join(rows))
            producer_worktree = Path("/tmp/dyn4k-merge-complete-corpus-rotation-gate-wave")
            self.assertEqual(report["candidate_commit"], subprocess.check_output(
                ["git", "-C", str(producer_worktree), "rev-parse", "HEAD"], text=True).strip())
            candidate_jar = (producer_worktree / "build/staging-repository/io/github/rubixhacker/"
                             "dyn4k-core-jvm/0.1.0-alpha.1/dyn4k-core-jvm-0.1.0-alpha.1.jar")
            pinned_lib = Path("/tmp/dyn4k-migration-preflight/lib")
            full_ci = Path("/tmp/dyn4k-archive-relocation-copy-7032")
            for provider in journeys.PROVIDERS:
                destination = evidence / "resolved" / provider
                destination.mkdir(parents=True)
                for name in ("gluegen-rt-2.3.2.jar", "jogl-all-2.3.2.jar"):
                    shutil.copy2(pinned_lib / name, destination / name)
                if provider == "baseline":
                    shutil.copy2(pinned_lib / "dyn4j-6.0.0.jar", destination / "dyn4j-6.0.0.jar")
                else:
                    shutil.copy2(candidate_jar, destination / journeys.CANDIDATE_JAR)
                    for name in independent_gates.MIGRATION_DEPENDENCIES:
                        shutil.copy2(full_ci / "deps" / name, destination / name)
            (evidence / "instrumentation").mkdir()
            shutil.copy2(pinned_lib / "javassist-3.30.2-GA.jar",
                         evidence / "instrumentation/javassist-3.30.2-GA.jar")
            journeys.write_summary(evidence, report)
            hashes = {"dyn4k-core": hashlib.sha256(candidate_jar.read_bytes()).hexdigest()}
            self.assertIn("ten pinned migration journeys",
                          independent_gates._migration_journeys(root, report["candidate_commit"], hashes))
            (root / "facade.bin").write_bytes(b"separate facade fixture")
            hashes["dyn4k"] = hashlib.sha256((root / "facade.bin").read_bytes()).hexdigest()
            scope = {"candidate_sha": report["candidate_commit"], "target": "jvm",
                     "runtime": "Java", "runtime_identity": "historical migration archive",
                     "artifact_hashes": {"dyn4k-core": hashes["dyn4k-core"]},
                     "producer_manifest_hashes": {"evidence/summary.json":
                         hashlib.sha256((evidence / "summary.json").read_bytes()).hexdigest()}}
            started = time.time_ns() - 1_000_000_000
            finished = time.time_ns() + 1_000_000_000
            files = [path for path in root.rglob("*") if path.is_file()]
            for path in files:
                os.utime(path, ns=(started + 1, started + 1))
            receipt = {"schema": 1, "status": "PASSED",
                       "candidate_sha": report["candidate_commit"],
                       "source_tree": subprocess.check_output(
                           ["git", "rev-parse", f"{report['candidate_commit']}^{{tree}}"],
                           cwd=ROOT, text=True).strip(),
                       "lane": LANE, "target": "jvm", "runtime": "Java",
                       "version": "minimum", "configuration": "no-optimize",
                       "runtime_identity": "historical migration archive",
                       "artifact_hashes": scope["artifact_hashes"], "producer_scope": scope,
                       "process": {"command": ["python3", "tools/migration/journeys.py", "run"],
                                   "exit_code": 0, "started_ns": started, "finished_ns": finished},
                       "files": [{"path": path.relative_to(root).as_posix(),
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                  "mtime_ns": started + 1} for path in files]}
            (root / "receipt.json").write_text(json.dumps(receipt))
            pin = independent_gates.archive_digest(root)
            selected = independent_gates.evaluate(
                self.manifest, report["candidate_commit"], LANE,
                {"migration-journeys": root}, ROOT, hashes,
                "historical migration archive", {"migration-journeys": pin},
                expected_producer_scopes={"migration-journeys": scope})
            self.assertEqual("PASSED", selected["gates"]["migration-journeys"]["status"])
            native_lane = "linuxX64:Linux x64:minimum:debug-g"
            receipt["lane"] = None
            (root / "receipt.json").write_text(json.dumps(receipt))
            native_pin = independent_gates.archive_digest(root)
            native_hashes = {"dyn4k-core": "c" * 64, "dyn4k": "d" * 64}
            native = independent_gates.evaluate(
                self.manifest, report["candidate_commit"], native_lane,
                {"migration-journeys": root}, ROOT, native_hashes,
                "native runner", {"migration-journeys": native_pin},
                expected_producer_scopes={"migration-journeys": scope})
            self.assertEqual("PASSED", native["gates"]["migration-journeys"]["status"])
            wrong_manifest_scope = {**scope, "producer_manifest_hashes": {
                "evidence/summary.json": "e" * 64}}
            wrong_manifest = independent_gates.evaluate(
                self.manifest, report["candidate_commit"], native_lane,
                {"migration-journeys": root}, ROOT, native_hashes,
                "native runner", {"migration-journeys": native_pin},
                expected_producer_scopes={"migration-journeys": wrong_manifest_scope})
            self.assertEqual("FAILED", wrong_manifest["gates"]["migration-journeys"]["status"])
            with tempfile.TemporaryDirectory() as audit_temporary:
                audit = Path(audit_temporary)
                (audit / "hashes.json").write_text(json.dumps(native_hashes))
                (audit / "scopes.json").write_text(json.dumps({"migration-journeys": scope}))
                (audit / "digests.json").write_text(json.dumps({"migration-journeys": native_pin}))
                cli = subprocess.run([
                    sys.executable, str(ROOT / "tools/qualification/independent_gates.py"),
                    "--repository", str(ROOT), "--candidate-sha", report["candidate_commit"],
                    "--lane", native_lane, "--expected-artifacts", str(audit / "hashes.json"),
                    "--expected-producer-scopes", str(audit / "scopes.json"),
                    "--expected-archive-digests", str(audit / "digests.json"),
                    "--expected-runtime-identity", "native runner",
                    "--archive", f"migration-journeys={root}"],
                    capture_output=True, text=True)
                self.assertEqual("PASSED", json.loads(cli.stdout)["gates"]["migration-journeys"]["status"])
            wrong_scope = {**scope, "artifact_hashes": {"dyn4k-core": "e" * 64}}
            wrong = independent_gates.evaluate(
                self.manifest, report["candidate_commit"], native_lane,
                {"migration-journeys": root}, ROOT, native_hashes,
                "native runner", {"migration-journeys": native_pin},
                expected_producer_scopes={"migration-journeys": wrong_scope})
            self.assertEqual("FAILED", wrong["gates"]["migration-journeys"]["status"])
            class_file = next((evidence / "candidate/compile/classes").rglob("*.class"))
            class_relative = class_file.relative_to(evidence)
            class_file.write_bytes(b"fake class")
            journeys.write_summary(evidence, report)
            with self.assertRaisesRegex(ValueError, "compiled class outputs differ"):
                independent_gates._migration_journeys(root, report["candidate_commit"], hashes)
            shutil.copy2(source / class_relative, class_file)
            source_file = evidence / "sources" / paths[0]
            source_file.write_bytes(b"class Invented {}\n")
            journeys.write_summary(evidence, report)
            with self.assertRaisesRegex(ValueError, "unchanged Java source bytes differ"):
                independent_gates._migration_journeys(root, report["candidate_commit"], hashes)
            shutil.copy2(samples / paths[0], source_file)
            input_log = evidence / "candidate/Billiards/observed/evidence/Billiards/inputs.log"
            input_log.write_text("scene=Billiards\n")
            journeys.write_summary(evidence, report)
            with self.assertRaisesRegex(ValueError, "raw scene, input, physics, or CCD evidence differs"):
                independent_gates._migration_journeys(root, report["candidate_commit"], hashes)
