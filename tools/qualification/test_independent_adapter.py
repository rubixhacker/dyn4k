import copy
import contextlib
import hashlib
import io
import json
import os
import platform
import shutil
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
BROWSER_CANDIDATE = "2e3665ba110e18d9669f847eb714e31befa391ce"
BROWSER_PRODUCER = Path("/var/home/stewart/Workspace/dyn4k-port-full-browser-112")
BROWSER_ARCHIVES = {
    "js:Chromium:current:development": ("current-development-attempt3", "a7067184d035e40e844b3dbd537ad64e6bdd27a3c83117975d5adb51bbf84537"),
    "js:Chromium:current:production": ("current-production-final", "8a0a2987795dbce7d864fc03fc1e5642d61161935001a595f1f1b63cd1175a70"),
    "js:Chromium:minimum:development": ("minimum-development-final", "60cc34371865de0d0b65d83b41f97abc87bb90d21c208c05089c72080db638b6"),
    "js:Chromium:minimum:production": ("minimum-production-final", "7adba1140fae071fd796afc047c2be2a745a80a2a2f06b0da4a397961448beae"),
}
BROWSER_HASHES = {"dyn4k-core": "244d9e5e0cb914dbc5c336e2905a9f539f7081ca46a0d3d64af76ef27f8c3476",
                  "dyn4k": "2c22dfef7855937386f4403f2dfe921e039d5363facea670a3a8c15ba0887bb4"}
BROWSER_BUNDLES = {
    "development": {"core": "2bf653dfc4aedfa30f3398213adf957f2c587ccdc87319896fec34527a550899",
                    "facade": "b404d41656f68ccc36091474564abf6817c6f7774a5d7a01722f9d8979a4b23d"},
    "production": {"core": "c7df91efb09e18e9ca5e26d9f77d07e6ca53ebfd772e1671a056dc6d32e62b68",
                   "facade": "f8f0f58e8fe371df346371dd12840b57c6d6b27943d122d52de3e9851d8f927d"},
}


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

    def test_signed_synthetic_complete_schema_cannot_pass_without_mode_binding(self):
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
                    "full_suite_manifest.select_lane", return_value=selection), mock.patch(
                    "qualify.verify_audit_against_staging"), mock.patch.object(
                    independent_adapter, "_verify_full_jvm_staged_consumer") as replay:
                with self.assertRaisesRegex(ValueError, "candidate mode publication is unbound"):
                    independent_adapter.verify_lanes(
                        root, sha, suite, archives, audit_path, signature, public,
                        fingerprint, candidate_manifest=candidate, artifact_audit=audit)
            replay.assert_not_called()
            self.assertEqual("FAILED", result["status"])

    def test_signed_jvm_executable_hashes_control_public_replay(self):
        import full_jvm_consumer

        lane = full_jvm_consumer.LANE
        candidate = "a" * 40
        cases = [{"id": "first", "scope": "portable"},
                 {"id": "second", "scope": "portable"}]
        suite = {"cases": cases, "lanes": {lane: {
            "target": "jvm", "required_gates": ["staged-consumer"],
            "case_scopes": ["portable"], "configuration": "default"}},
            "global_gates": []}
        hashes = {"dyn4k-core": "b" * 64, "dyn4k": "c" * 64}
        java_hash, gradle_hash, runtime_java_hash = "d" * 64, "e" * 64, "9" * 64
        publication_digest = "8" * 64
        publication_path = "/independent/jvm-mode-publication"
        archive_digest = "f" * 64
        runtime = "audited Java 21 runtime"
        fake = self.fake_verifier()
        fake.APPROVED_MANIFEST_SHA256 = qualify.manifest_digest(suite)
        gate = {"status": "PASSED", "complete_selected_suite": True}

        def evaluate(manifest, sha, lane_id, archives, repository, *expectations):
            result = {"candidate_sha": sha, "lane": lane_id, "status": "NOT_RUN",
                      "gates": {"staged-consumer": gate}}
            return {**result, "result_sha256": qualify.manifest_digest(result)}

        fake.evaluate = evaluate
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "resealed-archive"
            archive.mkdir()
            archive_map = root / "archives.json"
            archive_map.write_text(json.dumps({"schema": 1, "candidate_sha": candidate,
                                               "lanes": {lane: {"staged-consumer": str(archive)}}}))
            signed = {"schema": 1, "candidate_sha": candidate,
                      "suite_manifest_sha256": qualify.manifest_digest(suite),
                      "lanes": {lane: {"expected_artifact_hashes": hashes,
                                       "expected_runtime_identity": runtime,
                                       "expected_archive_digests": {
                                           "staged-consumer": archive_digest},
                                       "expected_java_executable_sha256": java_hash,
                                       "expected_gradle_executable_sha256": gradle_hash,
                                       "expected_runtime_java_executable_sha256": runtime_java_hash}}}
            signed["lanes"][lane].update(
                expected_mode_publication_path=publication_path,
                expected_mode_publication_digest=publication_digest)
            all_hashes = {target: (hashes if target == "jvm" else
                                   {module: "f" * 64 for module in qualify.MODULES})
                          for target in {row["target"] for row in qualify.matrix()}}
            staging = {"candidate_sha": candidate, "status": "PASSED", "artifacts": [
                {"path": qualify.target_binary_path(module, target), "sha256": value}
                for target, pair in all_hashes.items() for module, value in pair.items()]}
            binding = {"candidate_sha": candidate, "lane": lane, "mode": "default",
                       "source": "compiler_modes.replay", "source_checkout": str(root),
                       "publication_archive": publication_path,
                       "archive_digest": publication_digest, "artifact_hashes": hashes}
            selected_candidate = {"candidate_sha": candidate,
                                  "suite_manifest_sha256": qualify.manifest_digest(suite),
                                  "audit_manifest_sha256": qualify.manifest_digest(staging),
                                  "lanes": {lane: {"runtime_identity": runtime,
                                                   "artifact_hashes": hashes,
                                                   "jvm_mode_publication": binding}}}
            signed.update(candidate_manifest_sha256=qualify.manifest_digest(selected_candidate),
                          staged_audit_sha256=qualify.manifest_digest(staging),
                          expected_all_target_hashes=all_hashes)
            selection = {"case_ids": [item["id"] for item in cases],
                         "required_gates": ["staged-consumer"], "global_gates": []}

            def verify(audit_input, public_result=gate):
                audit_path, signature, public, fingerprint = self.signed_inputs(root, audit_input)
                with mock.patch.dict(sys.modules, {"independent_gates": fake}), mock.patch(
                        "full_suite_manifest.select_lane", return_value=selection), mock.patch(
                        "full_jvm_consumer.selected_contract", return_value=(suite, {"cases": cases})), mock.patch(
                        "full_jvm_consumer.verify", return_value=public_result) as replay, mock.patch(
                        "qualify.verify_audit_against_staging"), mock.patch(
                        "qualify.verify_jvm_mode_publication", return_value=True):
                    result = independent_adapter.verify_lanes(
                        root, candidate, suite, archive_map, audit_path, signature,
                        public, fingerprint, candidate_manifest=selected_candidate,
                        artifact_audit=staging)
                return result, replay

            result, replay = verify(signed)
            self.assertEqual("PASSED", result[lane]["verification"]["gates"][
                "staged-consumer"]["status"])
            replay.assert_called_once_with(
                str(archive), root, candidate, hashes, runtime, archive_digest,
                java_hash, gradle_hash, runtime_java_hash, lane,
                publication_path, publication_digest)
            for field, value in (("expected_java_executable_sha256", None),
                                 ("expected_gradle_executable_sha256", "0" * 63),
                                 ("expected_runtime_java_executable_sha256", None)):
                changed = copy.deepcopy(signed)
                changed["lanes"][lane][field] = value
                with self.assertRaisesRegex(ValueError, "signed JVM executable"):
                    verify(changed)
            for field, value in (("expected_mode_publication_path", None),
                                 ("expected_mode_publication_digest", "0" * 63)):
                changed = copy.deepcopy(signed)
                changed["lanes"][lane][field] = value
                with self.assertRaisesRegex(ValueError, "signed JVM mode publication"):
                    verify(changed)
            with self.assertRaisesRegex(ValueError, "public JVM verifier differs"):
                verify(signed, {"status": "FAILED"})
            changed = copy.deepcopy(signed)
            changed["lanes"][lane]["expected_java_executable_sha256"] = "0" * 64
            audit_path, signature, public, fingerprint = self.signed_inputs(root, changed)
            with mock.patch.dict(sys.modules, {"independent_gates": fake}), mock.patch(
                    "full_suite_manifest.select_lane", return_value=selection), mock.patch(
                    "full_jvm_consumer.selected_contract", return_value=(suite, {"cases": cases})), mock.patch(
                    "qualify.verify_audit_against_staging"), mock.patch(
                    "qualify.verify_jvm_mode_publication", return_value=True), mock.patch(
                    "full_jvm_consumer.verify", side_effect=ValueError(
                        "independent Java or Gradle executable SHA-256 differs from receipt")):
                with self.assertRaisesRegex(ValueError, "differs from receipt"):
                    independent_adapter.verify_lanes(
                        root, candidate, suite, archive_map, audit_path, signature,
                        public, fingerprint, candidate_manifest=selected_candidate,
                        artifact_audit=staging)

    def test_signed_local_klib_and_android_dispatch_requires_staged_identity(self):
        import full_android_adapter
        import full_klib_consumer

        candidate_sha = "a" * 40
        routes = ([(lane, target, "full_klib_adapter.verify_staged_consumer")
                   for lane, (target, _) in full_klib_consumer.LOCAL_LANES.items()]
                  + [(lane, "android", "full_android_adapter.verify_full_android_staged_consumer")
                     for lane in full_android_adapter.ROUTES])
        for lane_id, target, public_name in routes:
            with self.subTest(lane=lane_id), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                hashes = {module: hashlib.sha256(
                    f"{target}:{module}".encode()).hexdigest() for module in qualify.MODULES}
                suite = {"lanes": {lane_id: {"target": target,
                                            "required_gates": ["staged-consumer"]}},
                         "global_gates": []}
                staging = {"candidate_sha": candidate_sha, "status": "PASSED",
                           "artifacts": [{"path": qualify.target_binary_path(module, target),
                                          "sha256": value}
                                         for module, value in hashes.items()]}
                candidate = {"candidate_sha": candidate_sha,
                             "suite_manifest_sha256": qualify.manifest_digest(suite),
                             "audit_manifest_sha256": qualify.manifest_digest(staging),
                             "lanes": {lane_id: {"artifact_hashes": hashes,
                                                 "runtime_identity": "audited runtime"}}}
                expected = {"expected_artifact_hashes": hashes,
                            "expected_runtime_identity": "audited runtime",
                            "expected_archive_digests": {"staged-consumer": "b" * 64}}
                signed = {"schema": 1, "candidate_sha": candidate_sha,
                          "suite_manifest_sha256": qualify.manifest_digest(suite),
                          "candidate_manifest_sha256": qualify.manifest_digest(candidate),
                          "staged_audit_sha256": qualify.manifest_digest(staging),
                          "lanes": {lane_id: expected}}
                archive = str(root / "transported")
                archive_map = root / "archive-map.json"
                archive_map.write_text(json.dumps({"schema": 1, "candidate_sha": candidate_sha,
                                                   "lanes": {lane_id: {
                                                       "staged-consumer": archive}}}))
                fake = self.fake_verifier()
                fake.APPROVED_MANIFEST_SHA256 = qualify.manifest_digest(suite)
                selected = {"case_ids": ["approved-case"],
                            "required_gates": ["staged-consumer"], "global_gates": []}
                gate = {"status": "PASSED", "complete_selected_suite": True}

                def evaluate(manifest, sha, lane, archives, repository, *expectations):
                    result = {"candidate_sha": sha, "lane": lane, "status": "NOT_RUN",
                              "gates": {"staged-consumer": gate}}
                    return {**result, "result_sha256": qualify.manifest_digest(result)}

                fake.evaluate = evaluate

                def verify(signed_input=signed, bind=True):
                    audit_path, signature, public, fingerprint = self.signed_inputs(
                        root, signed_input)
                    with mock.patch.dict(sys.modules, {"independent_gates": fake}), mock.patch(
                            "full_suite_manifest.select_lane", return_value=selected), mock.patch(
                            "qualify.verify_audit_against_staging"), mock.patch(
                            public_name) as replay:
                        result = independent_adapter.verify_lanes(
                            root, candidate_sha, suite, archive_map, audit_path,
                            signature, public, fingerprint,
                            candidate_manifest=candidate if bind else None,
                            artifact_audit=staging if bind else None)
                    return result, replay

                verified, replay = verify()
                self.assertTrue(verified[lane_id]["identities_bound"])
                if lane_id in full_klib_consumer.LOCAL_LANES:
                    replay.assert_called_once_with(
                        root, candidate_sha, lane_id, ["approved-case"], archive,
                        gate, expected, hashes)
                else:
                    replay.assert_called_once_with(
                        root, candidate_sha, lane_id, selected, archive, expected, gate)
                gate["status"] = "NOT_RUN"
                _, replay = verify()
                replay.assert_not_called()
                gate["status"] = "PASSED"
                with self.assertRaisesRegex(ValueError, "identities are unbound"):
                    verify(bind=False)
                wrong = copy.deepcopy(signed)
                wrong["lanes"][lane_id]["expected_artifact_hashes"] = {
                    **hashes, "dyn4k-core": "c" * 64}
                with self.assertRaisesRegex(ValueError, "target artifacts"):
                    verify(wrong)

    def test_public_jvm_guard_routes_each_approved_lane(self):
        import full_jvm_consumer

        hashes = {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64}
        expected = {"expected_artifact_hashes": hashes,
                    "expected_runtime_identity": "audited runtime",
                    "expected_archive_digests": {"staged-consumer": "c" * 64},
                    "expected_java_executable_sha256": "d" * 64,
                    "expected_gradle_executable_sha256": "e" * 64,
                    "expected_runtime_java_executable_sha256": "f" * 64}
        expected.update(expected_mode_publication_path="/independent/mode-publication",
                        expected_mode_publication_digest="1" * 64)
        cases = [{"id": "selected"}]
        selected = {"case_ids": ["selected"]}
        gate = {"status": "PASSED"}
        for lane in full_jvm_consumer.LANES:
            with self.subTest(lane=lane), mock.patch(
                    "full_jvm_consumer.selected_contract",
                    return_value=({}, {"cases": cases})) as contract, mock.patch(
                    "full_jvm_consumer.verify", return_value=gate) as replay:
                independent_adapter._verify_full_jvm_staged_consumer(
                    ROOT, "0" * 40, lane, selected,
                    {"staged-consumer": "/independent/archive"}, expected, gate)
                contract.assert_called_once_with(ROOT, lane)
                replay.assert_called_once_with(
                    "/independent/archive", ROOT, "0" * 40, hashes, "audited runtime",
                    "c" * 64, "d" * 64, "e" * 64, "f" * 64, lane,
                    "/independent/mode-publication", "1" * 64)
        with self.assertRaisesRegex(ValueError, "does not cover lane"):
            independent_adapter._verify_full_jvm_staged_consumer(
                ROOT, "0" * 40, "jvm:Java:minimum:equivalent", selected,
                {"staged-consumer": "/independent/archive"}, expected, gate)

    def test_retained_full_jvm_archive_requires_signed_executable_hashes(self):
        import full_jvm_consumer

        tar_path = os.environ.get("DYN4K_RETAINED_FULL_JVM_ARCHIVE")
        publication = os.environ.get("DYN4K_JVM_MODE_PUBLICATION")
        if not tar_path or not publication:
            self.skipTest("retained full JVM and mode archive paths were not supplied")
        candidate = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                            text=True).strip()
        lane = os.environ.get("DYN4K_FULL_JVM_LANE", full_jvm_consumer.LANE)
        suite = independent_gates.load_approved_manifest(ROOT)
        hashes = {module: hashlib.sha256(full_jvm_consumer.target_binary(
            Path(publication) / "staged", module).read_bytes()).hexdigest()
            for module in full_jvm_consumer.MODULES}
        publication_digest = independent_gates.archive_digest(publication)
        java_hash = "2a207f5e7d075afa01d97f8048389a64432a44c4a5af0f5e77d6e286ec5f401d"
        gradle_hash = "b88b6fc9f41fba7bf456a3f8255ee5b7c6c379202ca13f68c3feecebcbc7bd8b"
        runtime_home = Path("/tmp/dyn4k-tools/jdk8" if ":minimum:" in lane
                            else "/tmp/dyn4k-tools/jdk21")
        runtime_hash = hashlib.sha256((runtime_home / "bin/java").read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "original"
            original.mkdir()
            subprocess.run(["tar", "-xf", tar_path, "-C", str(original)],
                           check=True, capture_output=True)
            receipt = json.loads((original / "receipt.json").read_text())
            runtime = subprocess.check_output([str(runtime_home / "bin/java"), "-version"],
                                              stderr=subprocess.STDOUT, text=True).splitlines()[0]
            runtime += f" | {platform.system()} {platform.release()} {platform.machine()}"
            forged = root / "forged"
            shutil.copytree(original, forged)
            forged_receipt = copy.deepcopy(receipt)
            forged_receipt["toolchain"]["java_executable_sha256"] = "0" * 64
            forged_receipt["toolchain"]["gradle_executable_sha256"] = "1" * 64
            (forged / "receipt.json").write_text(json.dumps(forged_receipt))
            def check(path):
                digest = independent_gates.archive_digest(path)
                signed = {"schema": 1, "candidate_sha": candidate,
                          "suite_manifest_sha256": independent_gates.digest(suite),
                          "lanes": {lane: {
                              "expected_artifact_hashes": hashes,
                              "expected_runtime_identity": runtime,
                              "expected_archive_digests": {"staged-consumer": digest},
                              "expected_java_executable_sha256": java_hash,
                              "expected_gradle_executable_sha256": gradle_hash,
                              "expected_runtime_java_executable_sha256": runtime_hash}}}
                signed["lanes"][lane].update(
                    expected_mode_publication_path=str(Path(publication).resolve()),
                    expected_mode_publication_digest=publication_digest)
                audit_path, signature, public, fingerprint = self.signed_inputs(root, signed)
                generic = independent_gates.evaluate_gate(
                    "staged-consumer", path, candidate, lane, suite["lanes"][lane],
                    ROOT, hashes, runtime, digest, manifest=suite)
                self.assertEqual("PASSED", generic["status"])
                authenticated = independent_adapter._signed_audit(
                    audit_path, signature, public, fingerprint)
                cases = full_jvm_consumer.selected_contract(ROOT, lane)[1]["cases"]
                independent_adapter._verify_full_jvm_staged_consumer(
                    ROOT, candidate, lane,
                    {"case_ids": [item["id"] for item in cases]},
                    {"staged-consumer": str(path)}, authenticated["lanes"][lane], generic)
                return generic

            verified = check(original)
            self.assertEqual("PASSED", verified["status"])
            with mock.patch.object(independent_adapter, "_verify_full_jvm_staged_consumer"):
                unguarded = check(forged)
            self.assertEqual("PASSED", unguarded["status"])
            with self.assertRaisesRegex(ValueError, "executable SHA-256 differs"):
                check(forged)

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
        fake = self.fake_verifier(status="NOT_RUN")
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
                        "qualify.verify_audit_against_staging"), mock.patch.object(
                        independent_adapter, "_verify_full_jvm_staged_consumer"):
                    return independent_adapter.verify_lanes(
                        root, sha, suite, archives, audit_path, signature, public,
                        fingerprint, candidate_manifest=candidate_input,
                        artifact_audit=staging_input)

            self.assertFalse(verify(signed)[LANE]["identities_bound"])
            changed = copy.deepcopy(signed)
            changed["lanes"][LANE]["expected_artifact_hashes"] = {
                **hashes, "dyn4k-core": "c" * 64}
            with self.assertRaisesRegex(ValueError, "target artifacts"):
                verify(changed)
            changed["lanes"][LANE].update(
                expected_mode_publication_path="/independent/mode-publication",
                expected_mode_publication_digest="d" * 64)
            with self.assertRaisesRegex(ValueError, "require candidate mode publication"):
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

    def test_real_jvm_modes_bind_signed_candidate_publications(self):
        archive_root = Path(
            "/var/home/stewart/dyn4k-evidence/session-control/"
            "full-jvm-d50-p1-p2-sol-work/archive")
        source = Path(
            "/var/home/stewart/dyn4k-evidence/session-control/"
            "full-jvm-d50-p1-p2-sol-work/final-candidate")
        if not source.is_dir() or any(not (archive_root / f"jvm-{mode}-final").is_dir()
                                      for mode in ("default", "no-optimize")):
            self.skipTest("retained exact10e JVM mode publications are unavailable")
        sha = "10e78648d4b63083e89f6543896dd07794be7b87"
        for mode in ("default", "no-optimize"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                lane = f"jvm:Java:minimum:{mode}"
                publication = archive_root / f"jvm-{mode}-final"
                hashes = {module: hashlib.sha256(
                    (publication / "staged" / qualify.target_binary_path(module, "jvm"))
                    .read_bytes()).hexdigest() for module in qualify.MODULES}
                digest = independent_gates.archive_digest(publication)
                binding = {"candidate_sha": sha, "lane": lane, "mode": mode,
                           "source": "compiler_modes.replay",
                           "source_checkout": str(source),
                           "publication_archive": str(publication),
                           "archive_digest": digest, "artifact_hashes": hashes}
                suite = {"lanes": {lane: {"target": "jvm", "configuration": mode,
                                            "required_gates": ["staged-consumer"]}},
                         "global_gates": []}
                all_hashes = {target: {module: "f" * 64 for module in qualify.MODULES}
                              for target in {row["target"] for row in qualify.matrix()}}
                staged = {"candidate_sha": sha, "status": "PASSED", "artifacts": [
                    {"path": qualify.target_binary_path(module, target), "sha256": value}
                    for target, pair in all_hashes.items() for module, value in pair.items()]}
                candidate = {"candidate_sha": sha,
                             "suite_manifest_sha256": qualify.manifest_digest(suite),
                             "audit_manifest_sha256": qualify.manifest_digest(staged),
                             "lanes": {lane: {"runtime_identity": "audited JDK",
                                              "artifact_hashes": hashes,
                                              "jvm_mode_publication": binding}}}
                signed = {"schema": 1, "candidate_sha": sha,
                          "suite_manifest_sha256": qualify.manifest_digest(suite),
                          "candidate_manifest_sha256": qualify.manifest_digest(candidate),
                          "staged_audit_sha256": qualify.manifest_digest(staged),
                          "expected_all_target_hashes": all_hashes,
                          "lanes": {lane: {"expected_artifact_hashes": hashes,
                                           "expected_runtime_identity": "audited JDK",
                                           "expected_archive_digests": {},
                                           "expected_mode_publication_path": str(publication),
                                           "expected_mode_publication_digest": digest}}}
                archives = root / "archives.json"
                archives.write_text(json.dumps({"schema": 1, "candidate_sha": sha,
                                                "lanes": {lane: {}}}))
                gate = {"candidate_sha": sha, "lane": lane, "status": "NOT_RUN",
                        "gates": {"staged-consumer": {"status": "NOT_RUN"}}}
                gate["result_sha256"] = independent_gates.digest(gate)
                selected = {"case_ids": ["synthetic"],
                            "required_gates": ["staged-consumer"], "global_gates": []}

                def verify(signed_input=signed, candidate_input=candidate, bind=True):
                    audit_input = copy.deepcopy(signed_input)
                    audit_input["candidate_manifest_sha256"] = qualify.manifest_digest(
                        candidate_input)
                    audit_path, signature, public, fingerprint = self.signed_inputs(
                        root, audit_input)
                    with mock.patch.object(independent_gates, "APPROVED_MANIFEST_SHA256",
                                           qualify.manifest_digest(suite)), mock.patch.object(
                        independent_gates, "evaluate", return_value=gate), mock.patch(
                        "full_suite_manifest.select_lane", return_value=selected), mock.patch(
                        "qualify.verify_audit_against_staging") as staging_check:
                        result = independent_adapter.verify_lanes(
                            ROOT, sha, suite, archives, audit_path, signature,
                            public, fingerprint,
                            candidate_manifest=candidate_input if bind else None,
                            artifact_audit=staged if bind else None)
                    if bind:
                        staging_check.assert_called_once_with(staged, ROOT)
                    else:
                        staging_check.assert_not_called()
                    return result[lane]

                verified = verify()
                self.assertTrue(verified["identities_bound"])
                self.assertEqual("NOT_RUN", verified["verification"]["status"])
                self.assertFalse(verify(bind=False)["identities_bound"])
                self.assertNotEqual(hashes, qualify.target_binary_hashes(
                    staged["artifacts"])["jvm"])
                missing_map = copy.deepcopy(signed)
                missing_map.pop("expected_all_target_hashes")
                with self.assertRaisesRegex(ValueError, "21-target artifact hash map is required"):
                    verify(signed_input=missing_map)
                wrong_map = copy.deepcopy(signed)
                wrong_map["expected_all_target_hashes"]["jvm"] = hashes
                with self.assertRaisesRegex(ValueError, "differ from staged audit"):
                    verify(signed_input=wrong_map)

                if mode != "default":
                    continue
                for field, value in (
                    ("mode", "no-optimize"), ("lane", f"jvm:Java:current:{mode}"),
                    ("candidate_sha", "0" * 40), ("source_checkout", str(ROOT)),
                ):
                    changed = copy.deepcopy(candidate)
                    changed["lanes"][lane]["jvm_mode_publication"][field] = value
                    with self.assertRaisesRegex(ValueError, "JVM mode publication"):
                        verify(candidate_input=changed)
                changed = copy.deepcopy(candidate)
                changed["lanes"][lane].pop("jvm_mode_publication")
                with self.assertRaisesRegex(ValueError, "require candidate mode publication"):
                    verify(candidate_input=changed)
                for field, value in (
                    ("expected_mode_publication_path",
                     str(archive_root / "jvm-no-optimize-final")),
                    ("expected_mode_publication_digest", "0" * 64),
                    ("expected_artifact_hashes", {**hashes, "dyn4k-core": "0" * 64}),
                ):
                    changed = copy.deepcopy(signed)
                    changed["lanes"][lane][field] = value
                    with self.assertRaisesRegex(ValueError, "differs from candidate lane"):
                        verify(signed_input=changed)
                other_publication = archive_root / "jvm-no-optimize-final"
                alternate = copy.deepcopy(candidate)
                alternate_binding = alternate["lanes"][lane]["jvm_mode_publication"]
                alternate_binding["publication_archive"] = str(other_publication)
                alternate_binding["archive_digest"] = independent_gates.archive_digest(
                    other_publication)
                alternate_signed = copy.deepcopy(signed)
                alternate_signed["lanes"][lane].update(
                    expected_mode_publication_path=str(other_publication),
                    expected_mode_publication_digest=alternate_binding["archive_digest"])
                with self.assertRaisesRegex(ValueError, "receipt identity differs"):
                    verify(signed_input=alternate_signed, candidate_input=alternate)
                forged = copy.deepcopy(candidate)
                forged_pair = {**hashes, "dyn4k-core": "0" * 64}
                forged["lanes"][lane]["artifact_hashes"] = forged_pair
                forged["lanes"][lane]["jvm_mode_publication"]["artifact_hashes"] = forged_pair
                forged_signed = copy.deepcopy(signed)
                forged_signed["lanes"][lane]["expected_artifact_hashes"] = forged_pair
                with self.assertRaisesRegex(ValueError, "JVM mode publication dyn4k-core JAR differs"):
                    verify(signed_input=forged_signed, candidate_input=forged)

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

    def browser_signed_fixture(self, root, lanes, archive_override=None,
                               repository=BROWSER_PRODUCER, candidate_sha=BROWSER_CANDIDATE):
        suite = independent_gates.load_approved_manifest(repository)
        runtime = f"{platform.system()} {platform.release()} {platform.machine()}"
        staged = {"candidate_sha": candidate_sha, "status": "PASSED",
                  "artifacts": [{"path": qualify.target_binary_path(module, "js"),
                                 "sha256": value}
                                for module, value in BROWSER_HASHES.items()]}
        candidate = {"candidate_sha": candidate_sha,
                     "suite_manifest_sha256": independent_gates.digest(suite),
                     "audit_manifest_sha256": qualify.manifest_digest(staged),
                     "lanes": {lane: {"artifact_hashes": BROWSER_HASHES,
                                      "runtime_identity": runtime} for lane in lanes}}
        paths = {}
        expected = {}
        for lane in lanes:
            role, mode = lane.split(":")[2:]
            suffix, digest = BROWSER_ARCHIVES[lane]
            archive = (archive_override if archive_override is not None else
                       Path("/var/home/stewart/dyn4k-evidence/session-control") /
                       f"full-browser-f565-review-findings-sol-{suffix}")
            if archive_override is not None:
                digest = independent_gates.archive_digest(archive)
            major = 119 if role == "minimum" else 155
            version = ("119.0.6045.105" if major == 119 else "155.0.8059.84")
            toolchain = {
                "java_home": "/tmp/dyn4k-tools/jdk21",
                "java_version": 'openjdk version "21.0.12.1" 2026-08-18 LTS',
                "java_sha256": "2a207f5e7d075afa01d97f8048389a64432a44c4a5af0f5e77d6e286ec5f401d",
                "gradle": "/tmp/dyn4k-tools/gradle-9.5.0/bin/gradle",
                "gradle_sha256": "b88b6fc9f41fba7bf456a3f8255ee5b7c6c379202ca13f68c3feecebcbc7bd8b",
                "gradle_version": "9.5.0", "kgp_version": "2.4.20",
                "browser": f"/tmp/dyn4k-browser-wasi-tools/chrome-{major}/chrome-linux64/chrome",
                "browser_sha256": ("c81049295247b6892c802dcad33dcab0a0337fce31800f923f51bdb0c07e6d11"
                                   if major == 119 else
                                   "b866a2964538c825538c454de4867973b926650da57ec12dc3328807d768247b"),
                "browser_version": f"Google Chrome for Testing {version}",
                "gradle_user_home": "/var/home/stewart/.gradle",
            }
            paths[lane] = {"staged-consumer": str(archive)}
            expected[lane] = {"expected_artifact_hashes": BROWSER_HASHES,
                              "expected_runtime_identity": runtime,
                              "expected_archive_digests": {"staged-consumer": digest},
                              "expected_browser_toolchain": toolchain,
                              "expected_browser_bundles": BROWSER_BUNDLES[mode]}
        archive_map = root / "browser-archive-map.json"
        archive_map.write_text(json.dumps({"schema": 1, "candidate_sha": candidate_sha,
                                           "lanes": paths}))
        signed = {"schema": 1, "candidate_sha": candidate_sha,
                  "suite_manifest_sha256": independent_gates.digest(suite),
                  "candidate_manifest_sha256": qualify.manifest_digest(candidate),
                  "staged_audit_sha256": qualify.manifest_digest(staged),
                  "lanes": expected}
        return suite, candidate, staged, archive_map, signed

    def historical_browser_verifier_matches(self):
        import full_browser_consumer

        source = "tools/qualification/full_browser_consumer.py"
        return (Path(full_browser_consumer.__file__).read_bytes()
                == full_browser_consumer.original(BROWSER_PRODUCER, BROWSER_CANDIDATE,
                                                  source))

    def test_signed_browser_dispatch_uses_real_generic_gate_for_all_four_routes(self):
        import full_browser_adapter

        if not BROWSER_PRODUCER.is_dir():
            self.skipTest("retained browser producer checkout is unavailable")
        if not self.historical_browser_verifier_matches():
            self.skipTest("historical browser replay requires its exact verifier source")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite, candidate, staged, archive_map, signed = self.browser_signed_fixture(
                root, BROWSER_ARCHIVES)
            audit, signature, public, fingerprint = self.signed_inputs(root, signed)
            original = full_browser_adapter.verify_full_browser_staged_consumer
            with (mock.patch.object(qualify, "verify_audit_against_staging") as staging,
                  mock.patch.object(full_browser_adapter,
                                    "verify_full_browser_staged_consumer",
                                    side_effect=original) as replay):
                verified = independent_adapter.verify_lanes(
                    BROWSER_PRODUCER, BROWSER_CANDIDATE, suite, archive_map,
                    audit, signature, public, fingerprint,
                    candidate_manifest=candidate, artifact_audit=staged)
            staging.assert_called_once_with(staged, BROWSER_PRODUCER)
            self.assertEqual(4, replay.call_count)
            for call in replay.call_args_list:
                lane = call.args[2]
                gate = verified[lane]["verification"]["gates"]["staged-consumer"]
                self.assertIs(gate, call.args[6])
                self.assertEqual("PASSED", gate["status"])
                self.assertEqual(2523, gate["selected_cases"])
                self.assertTrue(verified[lane]["identities_bound"])
                self.assertEqual("NOT_RUN", verified[lane]["verification"]["status"])

    def test_signed_browser_expectations_and_generic_failure_control_dispatch(self):
        import full_browser_adapter

        if not BROWSER_PRODUCER.is_dir():
            self.skipTest("retained browser producer checkout is unavailable")
        if not self.historical_browser_verifier_matches():
            self.skipTest("historical browser replay requires its exact verifier source")
        lane = "js:Chromium:current:development"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite, candidate, staged, archive_map, signed = self.browser_signed_fixture(
                root, [lane])

            def check(audit_input, archive_map_path=archive_map):
                audit, signature, public, fingerprint = self.signed_inputs(root, audit_input)
                with mock.patch.object(qualify, "verify_audit_against_staging"):
                    return independent_adapter.verify_lanes(
                        BROWSER_PRODUCER, BROWSER_CANDIDATE, suite, archive_map_path,
                        audit, signature, public, fingerprint,
                        candidate_manifest=candidate, artifact_audit=staged)

            for field, value in (("expected_browser_bundles", {"core": "0" * 64,
                                                              "facade": BROWSER_BUNDLES["development"]["facade"]}),
                                 ("expected_browser_toolchain", {**signed["lanes"][lane][
                                     "expected_browser_toolchain"], "browser_sha256": "0" * 64}),
                                 ("expected_artifact_hashes", {**BROWSER_HASHES,
                                                               "dyn4k-core": "0" * 64}),
                                 ("expected_runtime_identity", "wrong runtime")):
                changed = copy.deepcopy(signed)
                changed["lanes"][lane][field] = value
                with self.subTest(field=field), self.assertRaises(ValueError):
                    check(changed)

            wrong_digest = copy.deepcopy(signed)
            wrong_digest["lanes"][lane]["expected_archive_digests"] = {
                "staged-consumer": "0" * 64}
            with mock.patch.object(full_browser_adapter,
                                   "verify_full_browser_staged_consumer",
                                   return_value={"status": "PASSED"}) as fabricated:
                verified = check(wrong_digest)
            self.assertEqual("FAILED", verified[lane]["verification"]["gates"][
                "staged-consumer"]["status"])
            fabricated.assert_not_called()

            generic_digest = signed["lanes"][lane]["expected_archive_digests"]["staged-consumer"]
            with mock.patch.object(full_browser_adapter,
                                   "verify_full_browser_staged_consumer",
                                   return_value={"status": "PASSED", "lane": lane,
                                                 "candidate_sha": BROWSER_CANDIDATE,
                                                 "archive_sha256": generic_digest,
                                                 "selected_cases": 0}):
                with self.assertRaisesRegex(ValueError, "differs from independent gate"):
                    check(signed)

            resealed = Path("/var/home/stewart/dyn4k-evidence/session-control/"
                            "full-browser-f565-review-findings-sol-control-resealed-selected")
            self.assertTrue(resealed.is_dir(), "retained resealed browser control is missing")
            _, _, _, bad_map, bad_signed = self.browser_signed_fixture(
                root, [lane], archive_override=resealed)
            with mock.patch.object(full_browser_adapter,
                                   "verify_full_browser_staged_consumer",
                                   return_value={"status": "PASSED"}) as fabricated:
                verified = check(bad_signed, bad_map)
            self.assertEqual("FAILED", verified[lane]["verification"]["gates"][
                "staged-consumer"]["status"])
            fabricated.assert_not_called()

    def test_historical_browser_archive_rejects_newer_public_verifier(self):
        import full_browser_adapter

        if not BROWSER_PRODUCER.is_dir():
            self.skipTest("retained browser producer checkout is unavailable")
        if self.historical_browser_verifier_matches():
            self.skipTest("historical verifier matches this checkout")
        lane = "js:Chromium:current:development"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite, candidate, staged, archive_map, signed = self.browser_signed_fixture(
                root, [lane])
            audit, signature, public, fingerprint = self.signed_inputs(root, signed)
            with (mock.patch.object(qualify, "verify_audit_against_staging"),
                  mock.patch.object(full_browser_adapter,
                                    "verify_full_browser_staged_consumer") as replay):
                verified = independent_adapter.verify_lanes(
                    BROWSER_PRODUCER, BROWSER_CANDIDATE, suite, archive_map,
                    audit, signature, public, fingerprint,
                    candidate_manifest=candidate, artifact_audit=staged)
            gate = verified[lane]["verification"]["gates"]["staged-consumer"]
            self.assertEqual("FAILED", gate["status"])
            self.assertIn("public Chromium verifier differs from exact candidate",
                          gate["reason"])
            replay.assert_not_called()

    def test_signed_schema3_chromium_adapter_handoff_and_wrong_module_map(self):
        import full_browser_adapter
        import full_signed_routes

        current = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        lanes = sorted(BROWSER_ARCHIVES)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite, candidate, staged, archive_map, signed = self.browser_signed_fixture(
                root, lanes, repository=ROOT, candidate_sha=current)
            mapped = json.loads(archive_map.read_text())
            signed_bundles = {}
            for index, lane in enumerate(lanes):
                archive = root / f"browser-{index}"
                archive.mkdir()
                (archive / "receipt.json").write_text(json.dumps({
                    "schema": 3, "candidate_sha": current, "lane": lane,
                    "status": "PASSED"}))
                mapped["lanes"][lane]["staged-consumer"] = str(archive)
                signed["lanes"][lane]["expected_archive_digests"][
                    "staged-consumer"] = independent_gates.archive_digest(archive)
                signed_bundles[lane] = {
                    short: {"karma_selected_js": "a" * 64,
                            "linked_executable_js": "b" * 64}
                    for short in ("core", "facade")}
                signed["lanes"][lane]["expected_browser_bundles"] = signed_bundles[lane]
            archive_map.write_text(json.dumps(mapped))
            wrong_public = set()

            def generic(manifest, sha, lane, archives, repository, *expectations):
                selected = [case["id"] for case in manifest["cases"]
                            if case["scope"] in manifest["lanes"][lane]["case_scopes"]]
                self.assertEqual(2523, len(selected))
                digest = signed["lanes"][lane]["expected_archive_digests"]["staged-consumer"]
                public_result = {"status": "PASSED", "candidate_sha": sha,
                                 "lane": lane, "archive_sha256": digest,
                                 "selected_cases": len(selected) - (lane in wrong_public)}
                gate_names = set(manifest["lanes"][lane]["required_gates"]
                                 + manifest["global_gates"])
                gates = {name: {"gate": name, "status": "NOT_RUN"} for name in gate_names}
                gates["staged-consumer"] = {
                    "gate": "staged-consumer", "status": "PASSED",
                    "complete_selected_suite": True, "selected_cases": len(selected),
                    "archive_sha256": digest, "public_verification": public_result}
                result = {"candidate_sha": sha, "lane": lane,
                          "status": "NOT_RUN", "gates": gates}
                result["result_sha256"] = independent_gates.digest(result)
                return result

            def replay(repository, sha, lane, archive, expected, hashes, runtime, digest):
                if expected["expected_browser_bundles"] != signed_bundles[lane]:
                    raise ValueError("signed browser module bundle map differs")
                self.assertEqual(ROOT, repository)
                self.assertEqual(current, sha)
                self.assertEqual(BROWSER_HASHES, hashes)
                self.assertEqual(digest, independent_gates.archive_digest(Path(archive)))
                return {"status": "PASSED", "candidate_sha": sha, "lane": lane,
                        "archive_sha256": digest, "selected_cases": 2523}

            def verify(audit_input):
                audit, signature, public, fingerprint = self.signed_inputs(root, audit_input)
                with (mock.patch.object(qualify, "verify_audit_against_staging"),
                      mock.patch("full_suite_manifest.validate_manifest"),
                      mock.patch.object(independent_gates, "evaluate", side_effect=generic),
                      mock.patch.object(full_signed_routes, "verify_browser",
                                        side_effect=replay) as signed_replay,
                      mock.patch.object(full_browser_adapter,
                                        "verify_full_browser_staged_consumer",
                                        wraps=full_browser_adapter.verify_full_browser_staged_consumer)
                      as legacy):
                    verified = independent_adapter.verify_lanes(
                        ROOT, current, suite, archive_map, audit, signature, public,
                        fingerprint, candidate_manifest=candidate, artifact_audit=staged)
                legacy.assert_not_called()
                return verified, signed_replay.call_args_list

            verified, calls = verify(signed)
            self.assertEqual(lanes, sorted(call.args[2] for call in calls))
            for lane in lanes:
                self.assertEqual("PASSED", verified[lane]["verification"]["gates"][
                    "staged-consumer"]["status"])
                self.assertTrue(verified[lane]["identities_bound"])
                self.assertEqual("NOT_RUN", verified[lane]["verification"]["status"])
            changed = copy.deepcopy(signed)
            changed["lanes"][lanes[0]]["expected_browser_bundles"]["core"][
                "linked_executable_js"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "signed browser module bundle map differs"):
                verify(changed)
            wrong_public.add(lanes[0])
            with self.assertRaisesRegex(ValueError, "signed browser public result differs"):
                verify(signed)

    def test_pinned_schema1_chromium_keeps_scalar_bundle_handoff(self):
        import full_browser_adapter
        import full_signed_routes

        lane = "js:Chromium:current:development"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite, candidate, staged, archive_map, signed = self.browser_signed_fixture(
                root, [lane])
            audit, signature, public, fingerprint = self.signed_inputs(root, signed)
            digest = signed["lanes"][lane]["expected_archive_digests"]["staged-consumer"]
            public_result = {"status": "PASSED", "candidate_sha": BROWSER_CANDIDATE,
                             "lane": lane, "archive_sha256": digest,
                             "selected_cases": 2523}
            gate_names = set(suite["lanes"][lane]["required_gates"]
                             + suite["global_gates"])
            gates = {name: {"gate": name, "status": "NOT_RUN"} for name in gate_names}
            gates["staged-consumer"] = {
                "gate": "staged-consumer", "status": "PASSED",
                "complete_selected_suite": True, "selected_cases": 2523,
                "archive_sha256": digest}
            generic = {"candidate_sha": BROWSER_CANDIDATE, "lane": lane,
                       "status": "NOT_RUN", "gates": gates}
            generic["result_sha256"] = independent_gates.digest(generic)
            with (mock.patch.object(qualify, "verify_audit_against_staging"),
                  mock.patch("full_suite_manifest.validate_manifest"),
                  mock.patch.object(independent_gates, "evaluate", return_value=generic),
                  mock.patch.object(full_browser_adapter,
                                    "verify_full_browser_staged_consumer",
                                    return_value=public_result) as legacy,
                  mock.patch.object(full_signed_routes, "verify_browser") as signed_replay):
                verified = independent_adapter.verify_lanes(
                    BROWSER_PRODUCER, BROWSER_CANDIDATE, suite, archive_map,
                    audit, signature, public, fingerprint,
                    candidate_manifest=candidate, artifact_audit=staged)
            self.assertEqual("PASSED", verified[lane]["verification"]["gates"][
                "staged-consumer"]["status"])
            legacy.assert_called_once()
            signed_replay.assert_not_called()


if __name__ == "__main__":
    unittest.main()
