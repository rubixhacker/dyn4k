from __future__ import annotations

import copy
import gzip
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import raw_signature_audit


ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = Path("/tmp/dyn4k-baseline-cache/dyn4j-source")


class RawSignatureGateBindingTests(unittest.TestCase):
    def test_ledger_selected_receipt_is_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "receipts" / "new-candidate.json"
            path.parent.mkdir()
            receipt = {"candidate_revision": "new-candidate"}
            path.write_text(json.dumps(receipt))
            ledger = {"review_receipts": {"common_corpus": {
                "path": "receipts/new-candidate.json",
                "sha256": raw_signature_audit.digest(path.read_bytes()),
            }}}
            with patch.object(raw_signature_audit.common_corpus_receipt, "verify",
                              return_value=None) as verify:
                self.assertEqual(raw_signature_audit.checked_common_gate(ledger, root), receipt)
            verify.assert_called_once_with(receipt, ledger, root)

    def test_changed_hash_and_unsafe_path_are_rejected_before_replay(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            path = root / "receipt.json"
            path.write_text("not-json")
            other_path = root / "other-receipt.json"
            other_path.write_text("{}")
            outside_path = Path(outside) / "receipt.json"
            outside_path.write_text("{}")
            (root / "linked-receipt.json").symlink_to(outside_path)
            ledger = {"review_receipts": {"common_corpus": {
                "path": "receipt.json", "sha256": "0" * 64,
            }}}
            with patch.object(raw_signature_audit.common_corpus_receipt, "verify") as verify:
                with self.assertRaisesRegex(ValueError, "hash"):
                    raw_signature_audit.checked_common_gate(ledger, root)
                ledger["review_receipts"]["common_corpus"]["sha256"] = (
                    raw_signature_audit.digest(path.read_bytes()))
                ledger["review_receipts"]["common_corpus"]["path"] = "other-receipt.json"
                with self.assertRaisesRegex(ValueError, "hash"):
                    raw_signature_audit.checked_common_gate(ledger, root)
                for unsafe in ("../receipt.json", str(path)):
                    ledger["review_receipts"]["common_corpus"]["path"] = unsafe
                    with self.subTest(path=unsafe), self.assertRaisesRegex(ValueError, "path"):
                        raw_signature_audit.checked_common_gate(ledger, root)
                ledger["review_receipts"]["common_corpus"]["path"] = "linked-receipt.json"
                with self.assertRaisesRegex(ValueError, "path"):
                    raw_signature_audit.checked_common_gate(ledger, root)
            verify.assert_not_called()

    def test_full_receipt_replay_failure_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "receipt.json"
            path.write_text("{}")
            ledger = {"review_receipts": {"common_corpus": {
                "path": "receipt.json",
                "sha256": raw_signature_audit.digest(path.read_bytes()),
            }}}
            with patch.object(raw_signature_audit.common_corpus_receipt, "verify",
                              return_value="candidate source differs"):
                with self.assertRaisesRegex(ValueError, "candidate source differs"):
                    raw_signature_audit.checked_common_gate(ledger, root)

    def test_historical_receipt_binding_still_passes(self):
        ledger = json.loads((ROOT / "tools/compatibility/declaration-ledger.json").read_text())
        receipt_path = ROOT / ledger["review_receipts"]["common_corpus"]["path"]
        receipt = json.loads(receipt_path.read_text())
        with patch.object(raw_signature_audit.common_corpus_receipt, "verify",
                          return_value=None) as verify:
            self.assertEqual(raw_signature_audit.checked_common_gate(ledger, ROOT), receipt)
        verify.assert_called_once_with(receipt, ledger, ROOT)

    def test_classify_uses_the_ledger_gate(self):
        ledger = json.loads((ROOT / "tools/compatibility/declaration-ledger.json").read_text())
        ledger["review_receipts"]["common_corpus"]["path"] = "receipts/new-candidate.json"
        signature = json.loads(gzip.decompress(
            (ROOT / "tools/compatibility/receipts/jvm-signatures-0681a8cd.json.gz").read_bytes()))
        strict = json.loads((ROOT / "tools/compatibility/receipts/strict-jvm-0681a8cd.json").read_text())
        with (patch.object(raw_signature_audit, "checked_original_sources"),
              patch.object(raw_signature_audit.candidate_coverage, "digest",
                           return_value=ledger["candidate_source"]["artifact_sha256"]),
              patch.object(raw_signature_audit, "checked_common_gate",
                           side_effect=ValueError("selected gate reached")) as gate):
            with self.assertRaisesRegex(ValueError, "selected gate reached"):
                raw_signature_audit.classify(ledger, signature, strict, ROOT, UPSTREAM)
        gate.assert_called_once_with(ledger, ROOT)


@unittest.skipUnless(UPSTREAM.is_dir(), "pinned source checkout unavailable")
class RawSignatureAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads((ROOT / "tools/compatibility/declaration-ledger.json").read_text())
        cls.signature = json.loads(gzip.decompress((ROOT / "tools/compatibility/receipts/jvm-signatures-0681a8cd.json.gz").read_bytes()))
        cls.strict = json.loads((ROOT / "tools/compatibility/receipts/strict-jvm-0681a8cd.json").read_text())

    def test_each_raw_difference_has_one_source_linked_disposition(self):
        result = raw_signature_audit.classify(self.ledger, self.signature, self.strict,
                                              ROOT, UPSTREAM)
        self.assertEqual(len(result["rows"]), 156)
        self.assertEqual(Counter(row["category"] for row in result["rows"]), {
            "strict-source-visible": 110,
            "internal-type-header": 26,
            "package-documentation": 16,
            "anonymous-behavior": 4,
        })
        self.assertEqual(len({row["id"] for row in result["rows"]}), 156)
        self.assertEqual(Counter(row["difference_rule"] for row in result["rows"]), {
            "final-member-on-final-owner": 59,
            "constructor-list-wildcard-widening": 2,
            "kotlin-iterable-marker": 1,
            "inherited-interface-spelling": 49,
            "kotlin-mutable-iterator-marker": 24,
            "visibility-widened": 1,
            "package-documentation-only": 16,
            "anonymous-class-replaced": 4,
        })
        self.assertEqual(result["candidate_revision"], "0681a8cd2e3f12327296a58da68bc8338224ea73")

    def test_unequal_raw_rows_have_separate_governing_acceptance(self):
        result = raw_signature_audit.classify(self.ledger, self.signature, self.strict,
                                              ROOT, UPSTREAM)
        self.assertEqual(Counter(row["acceptance_disposition"] for row in result["rows"]), {
            "source-compatible": 111,
            "internal-behavior-equivalent": 29,
            "documentation-only": 16,
        })
        self.assertTrue(all(row["raw_obligation_status"] == "unpassed"
                            for row in result["rows"]))
        self.assertTrue(all(row["acceptance_evidence"] for row in result["rows"]
                            if row["acceptance_disposition"] != "unresolved"))
        self.assertTrue(all(row["behavior_case"] for row in result["rows"]
                            if row["category"] == "anonymous-behavior"))

    def test_deleting_or_swapping_a_raw_row_is_rejected(self):
        result = raw_signature_audit.classify(self.ledger, self.signature, self.strict,
                                              ROOT, UPSTREAM)
        self.assertIsNone(raw_signature_audit.check(result, self.ledger, self.signature,
                                                    self.strict, ROOT, UPSTREAM))
        missing = copy.deepcopy(result)
        missing["rows"].pop()
        self.assertIn("differs", raw_signature_audit.check(missing, self.ledger, self.signature,
                                                            self.strict, ROOT, UPSTREAM))
        swapped = copy.deepcopy(result)
        swapped["rows"][0]["baseline_signature"] = swapped["rows"][1]["baseline_signature"]
        self.assertIn("differs", raw_signature_audit.check(swapped, self.ledger, self.signature,
                                                            self.strict, ROOT, UPSTREAM))

    def test_changed_pinned_source_and_candidate_source_are_rejected(self):
        result = raw_signature_audit.classify(self.ledger, self.signature, self.strict,
                                              ROOT, UPSTREAM)
        changed = copy.deepcopy(self.ledger)
        changed["production"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "pinned source"):
            raw_signature_audit.classify(changed, self.signature, self.strict, ROOT, UPSTREAM)
        changed = copy.deepcopy(self.ledger)
        target = next(row for row in changed["declarations"] if row["id"] == "org.dyn4j.collision.Filter$1|type")
        target["candidate"]["sources"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "candidate source"):
            raw_signature_audit.classify(changed, self.signature, self.strict, ROOT, UPSTREAM)
        self.assertEqual(result["candidate_jar_sha256"], self.ledger["candidate_source"]["artifact_sha256"])
