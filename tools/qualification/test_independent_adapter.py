import copy
import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import independent_adapter
import independent_gates
import qualify


LANE = "jvm:Java:minimum:no-optimize"
ROOT = Path(__file__).resolve().parents[2]


class IndependentAdapterTests(unittest.TestCase):
    def test_public_assembly_accounts_for_every_lane_without_raw_archives(self):
        candidate = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                            cwd=ROOT, text=True).strip()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "assembly.json"
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = independent_adapter.main([
                    "assemble", "--candidate-sha", candidate,
                    "--repository", str(ROOT), "--output", str(output)])
            self.assertEqual(1, exit_code)
            assembled = json.loads(output.read_text())
            self.assertEqual(candidate, assembled["candidate_sha"])
            self.assertEqual(112, len(assembled["lanes"]))
            self.assertEqual({"PASSED": 0, "FAILED": 0, "UNAVAILABLE": 0,
                              "NOT_RUN": 112}, assembled["counts"])
            self.assertEqual("NOT_RUN", assembled["status"])
            self.assertEqual("NOT_RUN", assembled["lanes"][LANE]["status"])
            self.assertEqual("NOT_RUN", assembled["independent_gates"][LANE]["status"])
            self.assertEqual(2526, assembled["selected_cases"][LANE])
            self.assertIsNone(assembled["signed_audit_sha256"])
            self.assertEqual(assembled["result_sha256"], independent_gates.digest(
                {key: value for key, value in assembled.items() if key != "result_sha256"}))

    def test_public_assembly_rejects_unsigned_or_partial_archive_map(self):
        candidate = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                            cwd=ROOT, text=True).strip()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_map = root / "archives.json"
            output = root / "assembly.json"
            archive_map.write_text(json.dumps({"schema": 1, "candidate_sha": candidate,
                                               "lanes": {LANE: {}}}))
            with self.assertRaisesRegex(ValueError, "all 112"):
                independent_adapter.assemble_lanes(
                    ROOT, candidate, archive_map_path=archive_map)
            archive_map.write_text(json.dumps({"schema": 1, "candidate_sha": candidate,
                                               "lanes": {lane: {} for lane in
                                                         independent_gates.load_approved_manifest(ROOT)["lanes"]}}))
            with self.assertRaisesRegex(ValueError, "signed audit"):
                independent_adapter.assemble_lanes(
                    ROOT, candidate, archive_map_path=archive_map)
            cli = subprocess.run([
                sys.executable, str(ROOT / "tools/qualification/independent_adapter.py"),
                "assemble", "--repository", str(ROOT), "--candidate-sha", candidate,
                "--archive-map", str(archive_map), "--output", str(output)],
                capture_output=True, text=True)
            self.assertEqual(2, cli.returncode)
            self.assertIn("requires signed audit", cli.stderr)
            self.assertNotIn("Traceback", cli.stderr)
            archive_map.write_text(json.dumps({"schema": 1, "candidate_sha": "f" * 40,
                                               "lanes": {lane: {} for lane in
                                                         independent_gates.load_approved_manifest(ROOT)["lanes"]}}))
            with self.assertRaisesRegex(ValueError, "exact candidate"):
                independent_adapter.assemble_lanes(
                    ROOT, candidate, archive_map_path=archive_map)
            self.assertFalse(output.exists())

    def test_signed_112_lane_assembly_records_missing_and_failed_raw_archives(self):
        candidate = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                            cwd=ROOT, text=True).strip()
        suite = independent_gates.load_approved_manifest(ROOT)
        targets = {row["target"] for row in qualify.matrix()}
        hashes = {target: {module: hashlib.sha256(
            f"synthetic:{target}:{module}".encode()).hexdigest()
            for module in qualify.MODULES} for target in targets}
        staged = {"candidate_sha": candidate, "status": "PASSED", "artifacts": [
            {"path": qualify.target_binary_path(module, target), "sha256": value}
            for target, modules in hashes.items() for module, value in modules.items()]}
        selected = {lane: {"runtime_identity": f"synthetic:{lane}",
                           "artifact_hashes": hashes[details["target"]],
                           "runtime_version": "synthetic", "configuration": details["configuration"],
                           "suite_id": suite["id"]}
                    for lane, details in suite["lanes"].items()}
        candidate_manifest = {"schema": 1, "candidate_sha": candidate,
                              "suite_manifest_sha256": qualify.manifest_digest(suite),
                              "audit_manifest_sha256": qualify.manifest_digest(staged),
                              "lanes": selected}
        signed = {"schema": 1, "candidate_sha": candidate,
                  "suite_manifest_sha256": qualify.manifest_digest(suite),
                  "candidate_manifest_sha256": qualify.manifest_digest(candidate_manifest),
                  "staged_audit_sha256": qualify.manifest_digest(staged),
                  "expected_all_target_hashes": hashes,
                  "lanes": {lane: {"expected_artifact_hashes": hashes[details["target"]],
                                     "expected_runtime_identity": f"synthetic:{lane}",
                                     "expected_archive_digests": {}}
                            for lane, details in suite["lanes"].items()}}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_map = root / "archive-map.json"
            paths = {lane: {} for lane in suite["lanes"]}
            archive_map.write_text(json.dumps({"schema": 1, "candidate_sha": candidate,
                                               "lanes": paths}))
            candidate_path = root / "candidate.json"
            candidate_path.write_text(json.dumps(candidate_manifest))
            staged_path = root / "staged.json"
            staged_path.write_text(json.dumps(staged))
            audit_path, signature, public, fingerprint = self.signed_inputs(root, signed)
            evidence_path = root / "lane-evidence.json"

            def assemble(with_evidence=False):
                with mock.patch("qualify.require_clean_checkout"), mock.patch(
                        "qualify.verify_audit_against_staging"):
                    return independent_adapter.assemble_lanes(
                        ROOT, candidate, archive_map, audit_path, signature, public,
                        fingerprint, candidate_path, staged_path,
                        evidence_path if with_evidence else None)

            report = assemble()
            self.assertEqual(112, report["required_lanes"])
            self.assertEqual(112, report["counts"]["NOT_RUN"])
            self.assertEqual(0, report["counts"]["PASSED"])
            self.assertEqual(hashlib.sha256(archive_map.read_bytes()).hexdigest(),
                             report["archive_map_sha256"])
            audit_bytes = audit_path.read_bytes()
            original_verify = independent_adapter.verify_lanes

            def change_audit_after_verification(*args, **kwargs):
                checked = original_verify(*args, **kwargs)
                audit_path.write_bytes(audit_bytes + b" ")
                return checked

            with mock.patch.object(independent_adapter, "verify_lanes",
                                   side_effect=change_audit_after_verification):
                report = assemble()
            self.assertEqual(hashlib.sha256(audit_bytes).hexdigest(),
                             report["signed_audit_sha256"])
            audit_path.write_bytes(audit_bytes)
            lane = next(case for case in qualify.expand(qualify.matrix())
                        if case["id"] == LANE)
            case_ids = [case["id"] for case in suite["cases"]
                        if case["scope"] in suite["lanes"][LANE]["case_scopes"]]
            gate_names = suite["lanes"][LANE]["required_gates"] + suite["global_gates"]
            claimed = {
                **lane, "candidate_sha": candidate, "runtime_identity": f"synthetic:{LANE}",
                "runtime_version": "synthetic", "expected": len(case_ids),
                "executed": len(case_ids), "failures": 0, "skipped": 0,
                "consumer": "PASSED", "suite_id": suite["id"],
                "artifact_hashes": hashes["jvm"], "invocation_id": "a" * 32,
                "exit_code": 0, "command": ["synthetic"],
                "candidate_manifest_sha256": qualify.manifest_digest(candidate_manifest),
                "suite_manifest_sha256": qualify.manifest_digest(suite),
                "audit_manifest_sha256": qualify.manifest_digest(staged),
                "case_results": [{"id": name, "status": "PASSED"} for name in case_ids],
                "gate_results": {name: {"status": "PASSED", "receipt_sha256": "b" * 64}
                                 for name in gate_names},
            }
            self.assertEqual("PASSED", qualify.evaluate(
                lane, claimed, candidate, candidate_manifest, suite, staged)["status"])
            evidence_path.write_text(json.dumps({LANE: claimed}))
            report = assemble(with_evidence=True)
            self.assertEqual("NOT_RUN", report["lanes"][LANE]["status"])
            self.assertEqual(0, report["counts"]["PASSED"])
            paths[LANE] = {"staged-consumer": str(root / "missing-raw-archive")}
            archive_map.write_text(json.dumps({"schema": 1, "candidate_sha": candidate,
                                               "lanes": paths}))
            report = assemble()
            self.assertEqual(1, report["counts"]["FAILED"])
            self.assertEqual(111, report["counts"]["NOT_RUN"])
            self.assertIn("missing", report["independent_gates"][LANE]["gates"][
                "staged-consumer"]["reason"])
            audit_path.write_text(audit_path.read_text() + " ")
            with self.assertRaisesRegex(ValueError, "signature"):
                assemble()

    def signed_inputs(self, root, audit):
        key = root / "signing.pem"
        public = root / "trusted.pem"
        audit_path = root / "audit.json"
        signature = root / "audit.sig"
        subprocess.run(["openssl", "genpkey", "-algorithm", "ed25519", "-out", str(key)],
                       check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(key), "-pubout", "-out",
                        str(public)], check=True, capture_output=True)
        audit_path.write_text(json.dumps(audit))
        subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(key),
                        "-rawin", "-in", str(audit_path), "-out", str(signature)],
                       check=True, capture_output=True)
        der = subprocess.check_output(["openssl", "pkey", "-pubin", "-in",
                                       str(public), "-outform", "DER"])
        return audit_path, signature, public, hashlib.sha256(der).hexdigest()

    def fake_verifier(self, status="PASSED", complete=True):
        def digest(value):
            return qualify.manifest_digest(value)

        def evaluate(manifest, sha, lane, archives, repository, *expectations):
            names = (manifest["lanes"][lane]["required_gates"]
                     + manifest["global_gates"])
            gates = {name: {"status": status} for name in names}
            gates["staged-consumer"]["complete_selected_suite"] = complete
            result = {"candidate_sha": sha, "lane": lane, "status": status,
                      "expected_archive_digests": expectations[2],
                      "expected_producer_scopes": expectations[4],
                      "gates": gates}
            return {**result, "result_sha256": digest(result)}

        return types.SimpleNamespace(digest=digest,
                                     APPROVED_MANIFEST_SHA256=digest({"fixture": True}),
                                     evaluate=evaluate)

    def test_signed_synthetic_complete_schema_reaches_pass(self):
        sha = "a" * 40
        case = next(row for row in qualify.expand(qualify.matrix()) if row["id"] == LANE)
        areas = ("geometry", "collision", "dynamics", "joints", "compatibility")
        suite = {"schema": 1, "kind": "complete-port", "id": "synthetic-schema-control",
                 "areas": list(areas),
                 "cases": [{"id": area, "area": area, "scope": "portable"} for area in areas],
                 "lanes": {LANE: {"target": "jvm", "runtime": "Java",
                                    "version": "minimum", "configuration": "no-optimize",
                                    "case_scopes": ["portable"],
                                    "required_gates": ["staged-consumer"]}},
                 "global_gates": ["publication-contract"]}
        hashes = {module: "b" * 64 for module in qualify.MODULES}
        audit = {"candidate_sha": sha, "status": "PASSED", "artifacts": [
            {"path": qualify.target_binary_path(module, "jvm"), "sha256": value}
            for module, value in hashes.items()]}
        candidate = {"schema": 1, "candidate_sha": sha,
                     "suite_manifest_sha256": qualify.manifest_digest(suite),
                     "audit_manifest_sha256": qualify.manifest_digest(audit),
                     "lanes": {LANE: {"runtime_identity": "synthetic-runner",
                                      "runtime_version": "21", "configuration": "no-optimize",
                                      "suite_id": suite["id"], "artifact_hashes": hashes}}}
        gate_receipts = {name: {"status": "PASSED", "receipt_sha256": "c" * 64}
                         for name in ("staged-consumer", "publication-contract")}
        signed_digests = {name: "c" * 64 for name in gate_receipts}
        evidence = {**case, "candidate_sha": sha, "runtime_identity": "synthetic-runner",
                    "runtime_version": "21", "expected": 5, "executed": 5,
                    "failures": 0, "skipped": 0, "consumer": "PASSED",
                    "suite_id": suite["id"], "artifact_hashes": hashes,
                    "invocation_id": "d" * 32, "exit_code": 0, "command": ["synthetic"],
                    "candidate_manifest_sha256": qualify.manifest_digest(candidate),
                    "suite_manifest_sha256": qualify.manifest_digest(suite),
                    "audit_manifest_sha256": qualify.manifest_digest(audit),
                    "case_results": [{"id": area, "status": "PASSED"} for area in areas]}
        result = qualify.evaluate(case, evidence, sha, candidate, suite, audit)
        self.assertEqual("FAILED", result["status"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archives = root / "archives.json"
            archives.write_text(json.dumps({"schema": 1, "candidate_sha": sha,
                                            "lanes": {LANE: {}}}))
            signed = {"schema": 1, "candidate_sha": sha,
                      "suite_manifest_sha256": qualify.manifest_digest(suite),
                      "candidate_manifest_sha256": qualify.manifest_digest(candidate),
                      "staged_audit_sha256": qualify.manifest_digest(audit),
                      "lanes": {LANE: {"expected_archive_digests": signed_digests}}}
            signed["lanes"][LANE].update(expected_artifact_hashes=hashes,
                                          expected_runtime_identity="synthetic-runner")
            audit_path, signature, public, fingerprint = self.signed_inputs(root, signed)
            fake = self.fake_verifier()
            fake.APPROVED_MANIFEST_SHA256 = qualify.manifest_digest(suite)
            selection = {"case_ids": list(areas),
                         "required_gates": ["staged-consumer"],
                         "global_gates": ["publication-contract"]}
            with mock.patch.dict(sys.modules, {"independent_gates": fake}), mock.patch(
                    "full_suite_manifest.select_lane", return_value=selection) as selected, mock.patch(
                    "qualify.verify_audit_against_staging"):
                verified = independent_adapter.verify_lanes(
                    root, sha, suite, archives, audit_path, signature, public, fingerprint,
                    candidate_manifest=candidate, artifact_audit=audit)
            selected.assert_called_once_with(suite, LANE, root)
            independent_adapter.apply(
                [result], {LANE: evidence}, verified,
                lambda lane_id, observed: qualify.evaluate(
                    case, observed, sha, candidate, suite, audit))
            self.assertEqual("PASSED", result["status"])
            self.assertIn("signed raw gate archives", result["reason"])
            self.assertEqual(5, len(verified[LANE]["selected_case_ids"]))

    def test_signature_and_key_mismatch_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audit, signature, public, fingerprint = self.signed_inputs(root, {"schema": 1})
            self.assertEqual({"schema": 1}, independent_adapter._signed_audit(
                audit, signature, public, fingerprint))
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                independent_adapter._signed_audit(audit, signature, public, "0" * 64)
            audit.write_text('{"schema":2}')
            with self.assertRaisesRegex(ValueError, "signature"):
                independent_adapter._signed_audit(audit, signature, public, fingerprint)
            audit.write_text('{"schema":1,"schema":1}')
            subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(root / "signing.pem"),
                            "-rawin", "-in", str(audit), "-out", str(signature)],
                           check=True, capture_output=True)
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                independent_adapter._signed_audit(audit, signature, public, fingerprint)

    def test_missing_archive_failed_gate_and_duplicate_cases_never_pass(self):
        selected = ["a", "b"]
        passed = {"id": LANE, "status": "PASSED", "reason": "self-reported"}
        independent_adapter.apply([passed], {}, {})
        self.assertEqual("FAILED", passed["status"])
        for status in ("FAILED", "NOT_RUN", "UNAVAILABLE"):
            result = {"id": LANE, "status": "PASSED"}
            gates = ({"physical-correctness": {"status": "UNAVAILABLE",
                                                "observation_sha256": "f" * 64}}
                     if status == "UNAVAILABLE" else {})
            verified = {LANE: {"verification": {"status": status,
                                                 "result_sha256": "e" * 64,
                                                 "gates": gates},
                               "selected_case_ids": selected}}
            independent_adapter.apply([result], {}, verified)
            self.assertEqual(status, result["status"])
        verification = {"status": "PASSED", "result_sha256": "e" * 64,
                        "expected_archive_digests": {"staged-consumer": "c" * 64},
                        "gates": {"staged-consumer": {"complete_selected_suite": True}}}
        for cases in ([{"id": "a", "status": "PASSED"}] * 2,
                      [{"id": "a", "status": "PASSED"}],
                      [{"id": "a", "status": "PASSED"},
                       {"id": "b", "status": "FAILED"}]):
            result = {"id": LANE, "status": "PASSED"}
            independent_adapter.apply([result], {LANE: {"case_results": cases,
                                                        "gate_results": {"staged-consumer": {
                                                            "status": "PASSED",
                                                            "receipt_sha256": "c" * 64}}}},
                                      {LANE: {"verification": verification,
                                              "selected_case_ids": selected,
                                              "identities_bound": True}})
            self.assertEqual("FAILED", result["status"])
        result = {"id": LANE, "status": "PASSED"}
        independent_adapter.apply([result], {LANE: {
            "case_results": [{"id": name, "status": "PASSED"} for name in selected],
            "gate_results": {"staged-consumer": {"status": "PASSED",
                                                 "receipt_sha256": "f" * 64}}}},
            {LANE: {"verification": verification, "selected_case_ids": selected,
                    "identities_bound": True}})
        self.assertEqual("FAILED", result["status"])

    def test_signed_candidate_staging_and_producer_identity_must_agree(self):
        sha = "a" * 40
        hashes = {module: "b" * 64 for module in qualify.MODULES}
        suite = {"lanes": {LANE: {"target": "jvm",
                                  "required_gates": ["staged-consumer"]}},
                 "global_gates": ["migration-journeys"]}
        audit = {"candidate_sha": sha, "status": "PASSED", "artifacts": [
            {"path": qualify.target_binary_path(module, "jvm"), "sha256": value}
            for module, value in hashes.items()]}
        candidate = {"candidate_sha": sha,
                     "suite_manifest_sha256": qualify.manifest_digest(suite),
                     "audit_manifest_sha256": qualify.manifest_digest(audit),
                     "lanes": {LANE: {"runtime_identity": "audited runner",
                                      "artifact_hashes": hashes}}}
        signed = {"schema": 1, "candidate_sha": sha,
                  "suite_manifest_sha256": qualify.manifest_digest(suite),
                  "candidate_manifest_sha256": qualify.manifest_digest(candidate),
                  "staged_audit_sha256": qualify.manifest_digest(audit),
                  "lanes": {LANE: {"expected_archive_digests": {},
                                   "expected_artifact_hashes": hashes,
                                   "expected_runtime_identity": "audited runner"}}}
        fake = self.fake_verifier()
        fake.APPROVED_MANIFEST_SHA256 = qualify.manifest_digest(suite)
        selection = {"case_ids": ["synthetic"],
                     "required_gates": ["staged-consumer"],
                     "global_gates": ["migration-journeys"]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archives = root / "archives.json"
            archives.write_text(json.dumps({"schema": 1, "candidate_sha": sha,
                                            "lanes": {LANE: {}}}))

            def verify(audit_input, candidate_input=candidate, staging_input=audit):
                audit_path, signature, public, fingerprint = self.signed_inputs(root, audit_input)
                with mock.patch.dict(sys.modules, {"independent_gates": fake}), mock.patch(
                        "full_suite_manifest.select_lane", return_value=selection), mock.patch(
                        "qualify.verify_audit_against_staging"):
                    return independent_adapter.verify_lanes(
                        root, sha, suite, archives, audit_path, signature, public,
                        fingerprint, candidate_manifest=candidate_input,
                        artifact_audit=staging_input)

            self.assertTrue(verify(signed)[LANE]["identities_bound"])
            changed = copy.deepcopy(signed)
            changed["lanes"][LANE]["expected_artifact_hashes"] = {
                **hashes, "dyn4k-core": "c" * 64}
            with self.assertRaisesRegex(ValueError, "target artifacts"):
                verify(changed)
            changed = copy.deepcopy(signed)
            changed["lanes"][LANE]["expected_runtime_identity"] = "other runner"
            with self.assertRaisesRegex(ValueError, "runtime"):
                verify(changed)
            changed = copy.deepcopy(signed)
            changed["staged_audit_sha256"] = "d" * 64
            with self.assertRaisesRegex(ValueError, "signed audit differs"):
                verify(changed)
            changed = copy.deepcopy(signed)
            changed["candidate_manifest_sha256"] = "d" * 64
            with self.assertRaisesRegex(ValueError, "signed audit differs"):
                verify(changed)
            changed = copy.deepcopy(signed)
            changed["lanes"][LANE]["expected_producer_scopes"] = {
                "migration-journeys": {"target": "jvm",
                                       "artifact_hashes": {"dyn4k-core": "c" * 64}}}
            with self.assertRaisesRegex(ValueError, "JVM producer"):
                verify(changed)
            altered_candidate = copy.deepcopy(candidate)
            altered_candidate["lanes"][LANE]["artifact_hashes"] = {
                **hashes, "dyn4k-core": "c" * 64}
            with self.assertRaisesRegex(ValueError, "signed audit differs"):
                verify(signed, candidate_input=altered_candidate)

    def test_all_112_lanes_reject_distinct_global_archive_or_scope(self):
        lanes = [case["id"] for case in qualify.expand(qualify.matrix())]
        self.assertEqual(112, len(lanes))
        suite = {"global_gates": ["migration-journeys"]}

        def verified():
            return {lane: {"verification": {
                "status": "PASSED", "result_sha256": "a" * 64,
                "expected_archive_digests": {"migration-journeys": "b" * 64},
                "expected_producer_scopes": {"migration-journeys": {
                    "runtime_identity": "producer A", "artifact_hashes": {"dyn4k-core": "c" * 64}}},
                "gates": {"migration-journeys": {"status": "PASSED",
                                                 "archive_sha256": "d" * 64}}},
                "selected_case_ids": ["synthetic"], "identities_bound": True}
                for lane in lanes}

        identical = verified()
        independent_adapter._check_global_consistency(identical, suite)
        self.assertFalse(any("global_consistency_error" in item for item in identical.values()))
        for mutation in (
            lambda item: item["verification"]["expected_archive_digests"].update(
                {"migration-journeys": "e" * 64}),
            lambda item: item["verification"]["gates"]["migration-journeys"].update(
                {"archive_sha256": "e" * 64}),
            lambda item: item["verification"]["gates"]["migration-journeys"].pop(
                "archive_sha256"),
            lambda item: item["verification"]["expected_producer_scopes"][
                "migration-journeys"].update(runtime_identity="producer B"),
        ):
            rows = verified()
            mutation(rows[lanes[-1]])
            independent_adapter._check_global_consistency(rows, suite)
            results = [{"id": lane, "status": "PASSED"} for lane in lanes]
            independent_adapter.apply(results, {}, rows)
            self.assertEqual({"FAILED"}, {row["status"] for row in results})
            self.assertTrue(all("global gate differs" in row["reason"] for row in results))

    def test_legacy_unavailability_is_labeled_unverified(self):
        unavailable = {"id": LANE, "status": "UNAVAILABLE", "reason": "no device"}
        missing = {"id": "missing", "status": "NOT_RUN", "reason": "no evidence supplied"}
        independent_adapter.apply([unavailable, missing], {}, {})
        self.assertEqual("UNAVAILABLE", unavailable["status"])
        self.assertEqual("UNVERIFIED", unavailable["availability_audit_status"])
        self.assertIn("unaudited", unavailable["reason"])
        self.assertEqual("NOT_RUN", missing["status"])
        self.assertNotIn("availability_audit_status", missing)
        for observation in (None, "f" * 64):
            result = {"id": LANE, "status": "UNAVAILABLE", "reason": "no device"}
            gate = {"status": "UNAVAILABLE"}
            if observation:
                gate["observation_sha256"] = observation
            independent_adapter.apply([result], {}, {LANE: {"verification": {
                "status": "UNAVAILABLE", "result_sha256": "e" * 64,
                "gates": {"physical-correctness": gate}}}})
            self.assertEqual("UNAVAILABLE" if observation else "FAILED", result["status"])
            if observation:
                self.assertEqual("VERIFIED", result["availability_audit_status"])


if __name__ == "__main__":
    unittest.main()
