from __future__ import annotations

import copy
import gzip
import json
import unittest
from collections import Counter
from pathlib import Path

import raw_signature_audit


ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = Path("/tmp/dyn4k-baseline-cache/dyn4j-source")


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
