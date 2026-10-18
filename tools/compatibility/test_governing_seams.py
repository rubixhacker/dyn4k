from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import governing_seams


ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / "tools/compatibility/receipts/governing-seams-0681a8cd.json"


class GoverningSeamsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads((ROOT / "tools/compatibility/declaration-ledger.json").read_text())
        cls.report = json.loads(RECEIPT.read_text())

    def test_uncovered_behavior_runs_against_both_exact_archives(self):
        self.assertIsNone(governing_seams.check(self.report, self.ledger, ROOT, replay=True))
        self.assertEqual(len(self.report["lanes"]), 8)
        self.assertTrue(all(row["status"] == "passed" for row in self.report["lanes"].values()))
        self.assertIn("org/dyn4j/AVLTree|isSelfBalancing|()Z",
                      self.report["observed_method_ids"])
        self.assertIn("org/dyn4j/geometry/AbstractShape|project|(Lorg/dyn4j/geometry/Vector2;)Lorg/dyn4j/geometry/Interval;",
                      self.report["observed_method_ids"])

    def test_changed_fixture_artifact_or_method_hit_is_rejected(self):
        changed = copy.deepcopy(self.report)
        changed["fixture_sha256"] = "0" * 64
        self.assertIn("fixture", governing_seams.check(changed, self.ledger, ROOT))
        changed = copy.deepcopy(self.report)
        changed["candidate_artifact_sha256"] = "0" * 64
        self.assertIn("candidate", governing_seams.check(changed, self.ledger, ROOT))
        changed = copy.deepcopy(self.report)
        changed["observed_method_ids"].pop()
        self.assertIn("method", governing_seams.check(changed, self.ledger, ROOT))
