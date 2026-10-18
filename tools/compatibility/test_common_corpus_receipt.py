from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import common_corpus_receipt


ROOT = Path(__file__).resolve().parents[2]
ORIGIN = Path("/tmp/dyn4k-merge-complete-corpus-rotation-gate-wave")
UPSTREAM = Path("/tmp/dyn4k-named-module-baseline-source-058bf6d")
RESULT = Path("/tmp/dyn4k-full-common-corpus-rotation-gate-result.json")
BINDING = Path("/tmp/dyn4k-full-common-corpus-rotation-gate-binding.json")


@unittest.skipUnless(all(path.exists() for path in (ORIGIN, UPSTREAM, RESULT, BINDING)),
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
