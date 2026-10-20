from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import common_corpus_receipt


ROOT = Path(__file__).resolve().parents[2]
ORIGIN = Path("/tmp/dyn4k-merge-complete-corpus-rotation-gate-wave")
UPSTREAM = Path("/tmp/dyn4k-named-module-baseline-source-058bf6d")
RESULT = Path("/tmp/dyn4k-full-common-corpus-rotation-gate-result.json")
BINDING = Path("/tmp/dyn4k-full-common-corpus-rotation-gate-binding.json")


class CommonCorpusReceiptCountControls(unittest.TestCase):
    def verify_synthetic_manifest(self, total, receipt_total=None, mutate=None,
                                  report_status="PASSED"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin = root / "origin"
            origin.mkdir()
            artifact_sha256 = "c" * 64
            source = {"revision": "a" * 40, "tree": "b" * 40,
                      "artifact": common_corpus_receipt.ARTIFACT,
                      "artifact_sha256": artifact_sha256}
            ledger = {"candidate_source": source}
            artifact_path = origin / source["artifact"]
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_bytes(b"synthetic artifact")
            manifest_path = origin / common_corpus_receipt.full_corpus.MANIFEST_PATH
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            cases = []
            for index in range(total):
                group = common_corpus_receipt.full_corpus.GROUPS[index % 12]
                cases.append({"module": group["module"], "classname": f"C{index}",
                              "method": f"m{index}", "hosts": [group["host"]]})
            manifest = {"kind": "full-common-corpus", "schema": 1, "cases": cases}
            manifest_path.write_text(json.dumps(manifest))
            mapping_path = origin / common_corpus_receipt.full_corpus.MAP_PATH
            mapping_path.write_text("original\tdisposition\n")
            result_path = root / "result.json"
            result_path.write_text("{}")
            binding_path = root / "binding.json"
            binding_path.write_text(json.dumps({"environment": {
                "java_home": "", "android_home": "", "executables": {}}}))
            group_rows = []
            for group in common_corpus_receipt.full_corpus.GROUPS:
                count = len(common_corpus_receipt.full_corpus.expected_cases(manifest, group))
                group_rows.append({"id": group["id"], "expected": count,
                                   "reported": count})
            observed = {"status": report_status, "groups": group_rows}
            result_path.write_text(json.dumps(observed))
            with patch.object(common_corpus_receipt.full_corpus, "verify_reports",
                              return_value=observed), patch.object(
                                  common_corpus_receipt.candidate_coverage, "git",
                                  side_effect=[source["revision"], source["tree"]]):
                receipt = {"schema_version": 1, "kind": "full-common-corpus",
                           "candidate_revision": source["revision"],
                           "candidate_tree": source["tree"],
                           "candidate_artifact": source["artifact"],
                           "candidate_artifact_sha256": source["artifact_sha256"],
                           "origin": str(origin), "upstream": str(root),
                           "result_path": str(result_path),
                           "result_sha256": common_corpus_receipt.digest(result_path),
                           "binding_path": str(binding_path),
                           "binding_sha256": common_corpus_receipt.digest(binding_path),
                           "manifest_sha256": common_corpus_receipt.digest(manifest_path),
                           "map_sha256": common_corpus_receipt.digest(mapping_path),
                           "total_cases": total if receipt_total is None else receipt_total,
                           "groups": group_rows}
                if mutate:
                    mutate(receipt)
                actual_digest = common_corpus_receipt.digest
                def fixture_digest(path):
                    path = Path(path)
                    if path in (ROOT / source["artifact"], artifact_path):
                        return artifact_sha256
                    return actual_digest(path)
                with patch.object(common_corpus_receipt, "digest", side_effect=fixture_digest):
                    return common_corpus_receipt.verify(receipt, ledger, ROOT), receipt

    def test_current_manifest_total_15141_and_wrong_total_rejected(self):
        error, receipt = self.verify_synthetic_manifest(15141)
        self.assertIsNone(error)
        error, _ = self.verify_synthetic_manifest(15141, receipt_total=15075)
        self.assertIn("counts", error)

    def test_historical_manifest_total_15075_remains_valid(self):
        error, _ = self.verify_synthetic_manifest(15075)
        self.assertIsNone(error)

    def test_missing_or_extra_group_is_rejected(self):
        for mutate in (lambda receipt: receipt["groups"].pop(),
                       lambda receipt: receipt["groups"].append(receipt["groups"][0])):
            error, _ = self.verify_synthetic_manifest(15141, mutate=mutate)
            self.assertIsNotNone(error)

    def test_failed_report_replay_cannot_be_replaced_by_group_sum(self):
        error, _ = self.verify_synthetic_manifest(15141, report_status="UNPASSED")
        self.assertIn("differs from replay", error)

    def test_changed_candidate_and_binding_identity_are_rejected(self):
        error, _ = self.verify_synthetic_manifest(
            15141, mutate=lambda receipt: receipt.update(candidate_artifact_sha256="0" * 64))
        self.assertIn("source or artifact", error)
        error, _ = self.verify_synthetic_manifest(
            15141, mutate=lambda receipt: receipt.update(binding_sha256="0" * 64))
        self.assertIn("binding", error)

@unittest.skipUnless(all(path.exists() for path in (ORIGIN, UPSTREAM, RESULT, BINDING,
                                                   ROOT / common_corpus_receipt.ARTIFACT)),
                     "full common corpus raw evidence unavailable")
class CommonCorpusReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads((ROOT / "tools/compatibility/declaration-ledger.json").read_text())
        cls.receipt = common_corpus_receipt.capture(cls.ledger, ROOT, ORIGIN,
                                                    UPSTREAM, RESULT, BINDING)

    def test_exact_twelve_host_receipt_replays(self):
        self.assertIsNone(common_corpus_receipt.verify(self.receipt, self.ledger, ROOT))
        self.assertEqual(self.receipt["total_cases"], 15075)
        self.assertEqual(len(self.receipt["groups"]), 12)

    def test_changed_candidate_source_or_artifact_fails(self):
        for field in ("revision", "tree", "artifact_sha256"):
            changed = copy.deepcopy(self.ledger)
            changed["candidate_source"][field] = "0" * (64 if field == "artifact_sha256" else 40)
            self.assertIsNotNone(common_corpus_receipt.verify(self.receipt, changed, ROOT), field)

    def test_missing_host_report_fails_even_with_rehashed_binding(self):
        changed = json.loads(BINDING.read_text())
        changed["reports"]["core-linuxX64"].pop(next(iter(changed["reports"]["core-linuxX64"])))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "binding.json"
            path.write_text(json.dumps(changed))
            receipt = {**self.receipt, "binding_path": str(path),
                       "binding_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            self.assertIn("report", common_corpus_receipt.verify(receipt, self.ledger, ROOT))

    def test_changed_gate_result_fails(self):
        changed = {**self.receipt, "result_sha256": "0" * 64}
        self.assertIn("result", common_corpus_receipt.verify(changed, self.ledger, ROOT))
