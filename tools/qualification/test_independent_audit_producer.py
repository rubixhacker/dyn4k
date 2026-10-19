import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import independent_adapter
import independent_audit_producer as producer
import independent_gates
import qualify


ROOT = Path(__file__).resolve().parents[2]


class IndependentAuditProducerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.candidate = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
        self.suite = independent_gates.load_approved_manifest(ROOT)
        self.hashes = {target: {module: hashlib.sha256(
            f"fixture:{target}:{module}".encode()).hexdigest()
            for module in qualify.MODULES} for target in qualify.matrix_targets()}
        self.staged = {"candidate_sha": self.candidate, "status": "PASSED",
                       "artifacts": [{"path": qualify.target_binary_path(module, target),
                                      "sha256": value}
                                     for target, modules in self.hashes.items()
                                     for module, value in modules.items()]}
        self.candidate_manifest = {
            "candidate_sha": self.candidate,
            "suite_manifest_sha256": independent_gates.digest(self.suite),
            "audit_manifest_sha256": qualify.manifest_digest(self.staged),
            "lanes": {lane: {"artifact_hashes": copy.deepcopy(self.hashes[spec["target"]]),
                             "runtime_identity": f"fixture:{lane}"}
                      for lane, spec in self.suite["lanes"].items()}}
        self.observations = {"schema": 1, "candidate_sha": self.candidate,
                             "lanes": {lane: {"archives": {}, "signed_fields": {}}
                                       for lane in self.suite["lanes"]}}
        self.candidate_path = self.root / "candidate.json"
        self.stage_path = self.root / "staged.json"
        self.observations_path = self.root / "observations.json"
        self.private = self.root / "test-only-private.pem"
        self.public = self.root / "public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out",
                        str(self.private)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(self.private), "-pubout", "-out",
                        str(self.public)], check=True, capture_output=True)
        der = subprocess.check_output(["openssl", "pkey", "-pubin", "-in",
                                       str(self.public), "-outform", "DER"])
        self.fingerprint = hashlib.sha256(der).hexdigest()
        self.write_inputs()

    def write_inputs(self):
        self.candidate_path.write_text(json.dumps(self.candidate_manifest))
        self.stage_path.write_text(json.dumps(self.staged))
        self.observations_path.write_text(json.dumps(self.observations))

    def prepare(self, output=None):
        with mock.patch("qualify.verify_audit_against_staging"), mock.patch(
                "qualify.require_clean_checkout"):
            return producer.prepare(ROOT, self.candidate, self.candidate_path,
                                    self.stage_path, self.observations_path,
                                    output or self.root / "prepared", self.fingerprint)

    def sign(self, prepared):
        signature = self.root / "audit.sig"
        subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(self.private),
                        "-rawin", "-in", str(prepared / "audit.json"), "-out",
                        str(signature)], check=True, capture_output=True)
        return signature, self.public, self.fingerprint

    def test_complete_empty_map_detached_signature_and_public_assembly(self):
        prepared = self.prepare()
        archive_map = json.loads((prepared / "archive-map.json").read_bytes())
        self.assertEqual(set(self.suite["lanes"]), set(archive_map["lanes"]))
        self.assertTrue(all(not paths for paths in archive_map["lanes"].values()))
        self.assertEqual((prepared / "audit.json").read_bytes(),
                         producer.canonical_json(json.loads((prepared / "audit.json").read_bytes())))
        signature, public, fingerprint = self.sign(prepared)
        with mock.patch("qualify.verify_audit_against_staging"), mock.patch(
                "qualify.require_clean_checkout"):
            result = producer.finalize(ROOT, self.candidate, prepared, self.candidate_path,
                                       self.stage_path, signature, public, fingerprint,
                                       self.observations_path)
        self.assertEqual(112, result["counts"]["NOT_RUN"])
        self.assertEqual(0, result["counts"]["PASSED"])
        self.assertEqual("NOT_RUN", result["status"])

    def test_wrong_candidate_stage_and_signature_controls(self):
        prepared = self.prepare()
        signature, public, fingerprint = self.sign(prepared)
        with self.assertRaisesRegex(ValueError, "candidate"):
            producer.prepare(ROOT, "0" * 40, self.candidate_path, self.stage_path,
                             self.observations_path, self.root / "wrong", self.fingerprint)
        changed = copy.deepcopy(self.staged)
        changed["artifacts"][0]["sha256"] = "0" * 64
        self.stage_path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, "staged audit bytes"):
            producer.finalize(ROOT, self.candidate, prepared, self.candidate_path,
                              self.stage_path, signature, public, fingerprint,
                              self.observations_path)
        self.stage_path.write_text(json.dumps(self.staged))
        for bad_signature, bad_key, bad_fingerprint, reason in (
                (None, public, fingerprint, "signature"),
                (signature, None, fingerprint, "public key"),
                (signature, public, "0" * 64, "fingerprint")):
            with self.assertRaisesRegex(ValueError, reason):
                producer.finalize(ROOT, self.candidate, prepared, self.candidate_path,
                                  self.stage_path, bad_signature, bad_key, bad_fingerprint,
                                  self.observations_path)
        (prepared / "audit.json").write_bytes((prepared / "audit.json").read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "audit bytes"):
            producer.finalize(ROOT, self.candidate, prepared, self.candidate_path,
                              self.stage_path, signature, public, fingerprint,
                              self.observations_path)

    def test_self_reported_green_and_changed_archive_fail_preflight(self):
        lane = next(iter(self.suite["lanes"]))
        archive = self.root / "attempt"
        archive.mkdir()
        (archive / "receipt.json").write_text(json.dumps({"status": "PASSED"}))
        self.observations["lanes"][lane]["archives"]["staged-consumer"] = str(archive)
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "signed route fields are incomplete"):
            self.prepare()
        self.observations["lanes"][lane]["signed_fields"] = {
            field: "0" * 64 for field in producer.ROUTE_FIELDS["jvm"]}
        self.write_inputs()
        rejected_green = self.prepare(self.root / "prepared-rejected-green")
        green_audit = json.loads((rejected_green / "audit.json").read_bytes())
        self.assertEqual("FAILED", green_audit["preflight_results"][lane]["gates"]["staged-consumer"])
        self.observations["lanes"][lane]["signed_fields"].clear()
        self.write_inputs()
        (archive / "receipt.json").write_text(json.dumps({"status": "FAILED"}))
        malformed = self.prepare()
        failed = json.loads((malformed / "audit.json").read_bytes())
        self.assertEqual("FAILED", failed["preflight_results"][lane]["gates"]["staged-consumer"])
        signature, public, fingerprint = self.sign(malformed)
        (archive / "receipt.json").write_text(json.dumps({"status": "FAILED", "changed": True}))
        with self.assertRaisesRegex(ValueError, "archive bytes or timestamps changed"):
            producer.finalize(ROOT, self.candidate, malformed, self.candidate_path,
                              self.stage_path, signature, public, fingerprint,
                              self.observations_path)
        self.observations["lanes"][lane]["archives"].clear()
        self.write_inputs()
        prepared = self.prepare(self.root / "prepared-empty")
        signature, public, fingerprint = self.sign(prepared)
        self.observations["lanes"][lane]["archives"]["staged-consumer"] = str(archive)
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "observation bytes"):
            producer.finalize(ROOT, self.candidate, prepared, self.candidate_path,
                              self.stage_path, signature, public, fingerprint,
                              self.observations_path)

    def test_rejects_wrong_lane_identity_and_unsigned_replacement(self):
        lane = next(iter(self.suite["lanes"]))
        self.candidate_manifest["lanes"][lane]["runtime_identity"] = ""
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "candidate lane artifact or runtime"):
            self.prepare()
        self.candidate_manifest["lanes"][lane]["runtime_identity"] = f"fixture:{lane}"
        self.candidate_manifest["lanes"][lane]["artifact_hashes"]["dyn4k-core"] = "0" * 64
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "candidate lane artifact or runtime"):
            self.prepare()
        self.candidate_manifest["lanes"][lane]["artifact_hashes"] = self.hashes[
            self.suite["lanes"][lane]["target"]]
        self.write_inputs()
        missing = self.staged["artifacts"].pop()
        self.candidate_manifest["audit_manifest_sha256"] = qualify.manifest_digest(self.staged)
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "21 target binary hashes"):
            self.prepare()
        self.staged["artifacts"].append(missing)
        self.candidate_manifest["audit_manifest_sha256"] = qualify.manifest_digest(self.staged)
        self.write_inputs()
        prepared = self.prepare()
        signature, public, fingerprint = self.sign(prepared)
        audit_path = prepared / "audit.json"
        request_path = prepared / "signing-request.json"
        replacement = json.loads(audit_path.read_bytes())
        replacement["lanes"][lane]["expected_runtime_identity"] = "forged runner"
        audit_path.write_bytes(producer.canonical_json(replacement))
        request = json.loads(request_path.read_bytes())
        request["audit_sha256"] = hashlib.sha256(audit_path.read_bytes()).hexdigest()
        request_path.write_bytes(producer.canonical_json(request))
        with self.assertRaisesRegex(ValueError, "signature is unverified"):
            producer.finalize(ROOT, self.candidate, prepared, self.candidate_path,
                              self.stage_path, signature, public, fingerprint,
                              self.observations_path)


if __name__ == "__main__":
    unittest.main()
