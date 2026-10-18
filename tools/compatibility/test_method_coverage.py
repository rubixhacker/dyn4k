from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import method_coverage


ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = Path("/tmp/dyn4k-baseline-cache/dyn4j-source")
RECEIPT = ROOT / "tools/compatibility/receipts/java-method-coverage-0681a8cd.json"


@unittest.skipUnless(UPSTREAM.is_dir(), "pinned source checkout unavailable")
class MethodCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads((ROOT / "tools/compatibility/declaration-ledger.json").read_text())
        cls.corpus = json.loads((ROOT / "tools/compatibility/receipts/java-corpus-0681a8cd/report.json").read_text())
        cls.receipt = json.loads(RECEIPT.read_text())

    def test_full_unchanged_java_corpus_observes_exact_candidate_methods(self):
        self.assertIsNone(method_coverage.check(self.receipt, self.ledger, self.corpus,
                                                 ROOT, UPSTREAM))
        self.assertEqual(self.receipt["actual_executed_cases_per_lane"], 2385)
        self.assertEqual(self.receipt["candidate_lanes"], 4)
        self.assertGreaterEqual(sum(row["covered_instructions"] > 0
                                    for row in self.receipt["methods"]), 2000)

    def test_claimed_method_hit_or_candidate_identity_cannot_change(self):
        changed = copy.deepcopy(self.receipt)
        row = next(row for row in changed["methods"] if row["covered_instructions"] > 0)
        row["covered_instructions"] = 0
        self.assertIn("method", method_coverage.check(changed, self.ledger, self.corpus,
                                                       ROOT, UPSTREAM))
        changed = copy.deepcopy(self.receipt)
        changed["candidate_artifact_sha256"] = "0" * 64
        self.assertIn("candidate", method_coverage.check(changed, self.ledger, self.corpus,
                                                          ROOT, UPSTREAM))
