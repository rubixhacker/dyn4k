from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import portable_links


ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = Path("/tmp/dyn4k-named-module-baseline-source-058bf6d")


@unittest.skipUnless(UPSTREAM.is_dir(), "pinned source checkout unavailable")
class PortableLinksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads((ROOT / "tools/compatibility/declaration-ledger.json").read_text())
        cls.gate = json.loads((ROOT / "tools/compatibility/receipts/full-common-0681a8cd.json").read_text())
        cls.links = portable_links.make(cls.ledger, cls.gate, ROOT, UPSTREAM)

    def test_all_original_rows_are_accounted_without_promoting_context_links(self):
        self.assertEqual(len(self.links["production"]), 268)
        self.assertEqual(len(self.links["declarations"]), 3508)
        self.assertEqual(self.links["declaration_anchor_counts"], {"anchored": 3508})
        self.assertEqual(self.links["original_identity_counts"], {
            "portable": 2353, "jvm_only": 32, "mapped_common_methods": 2253,
            "related_body_supplements": 5})
        by_id = {row["id"]: row for row in self.links["declarations"]}
        self.assertTrue(by_id["org.dyn4j.AVLTree|remove|(Ljava/lang/Comparable;)Z"]["behavior_tests"])
        self.assertTrue(any("fun remove(" in anchor["text"]
                            for anchor in by_id["org.dyn4j.AVLTree|remove|(Ljava/lang/Comparable;)Z"]["candidate_declaration_anchors"]))
        self.assertEqual(by_id["org.dyn4j.exception.CopyException|type"]["common_source_status"],
                         "common-expect-and-jvm-actual")
        self.assertTrue(any("expect open class CopyException" in anchor["text"]
                            for anchor in by_id["org.dyn4j.exception.CopyException|type"]["candidate_declaration_anchors"]))
        self.assertTrue(any("fun <T : BinarySearchTreeSearchCriteria<E>> search" in anchor["text"]
                            for anchor in by_id["org.dyn4j.AVLTree|search|(Lorg/dyn4j/BinarySearchTreeSearchCriteria;)Lorg/dyn4j/BinarySearchTreeSearchCriteria;"]["candidate_declaration_anchors"]))
        self.assertEqual(by_id["org.dyn4j.geometry.MassType|NORMAL|"]["candidate_declaration_anchors"][0]["relation"],
                         "enum-entry")
        self.assertEqual(by_id["org.dyn4j.geometry.MassType|values|()[Lorg/dyn4j/geometry/MassType;"]["candidate_declaration_anchors"][0]["relation"],
                         "compiler-generated-enum-member")
        self.assertEqual(by_id["org.dyn4j.geometry.package-info|type"]["link_status"],
                         "package-documentation-only")
        self.assertEqual(self.links["qualification_status"], "MAPPED_UNPASSED")

    def test_missing_implementation_declaration_or_behavior_row_fails(self):
        for section in ("production", "declarations"):
            changed = copy.deepcopy(self.links)
            changed[section].pop()
            self.assertIn("differ", portable_links.check(changed, self.ledger, self.gate, ROOT, UPSTREAM))
        changed = copy.deepcopy(self.links)
        target = next(row for row in changed["declarations"] if row["behavior_tests"])
        target["behavior_tests"].pop()
        self.assertIn("differ", portable_links.check(changed, self.ledger, self.gate, ROOT, UPSTREAM))

    def test_null_iterator_and_callback_cases_keep_six_host_links(self):
        controls = (
            ("src/main/java/org/dyn4j/collision/AbstractCollisionBody.java",
             "org.dyn4j.collision.AbstractCollisionBodyTest#addNullConvex"),
            ("src/main/java/org/dyn4j/AVLTree.java",
             "org.dyn4j.AVLTreeTest#headIteratorMissing"),
            ("src/main/java/org/dyn4j/world/AbstractCollisionWorld.java",
             "org.dyn4j.world.AbstractCollisionWorldTest#detectWithListeners"),
        )
        for source, original in controls:
            with self.subTest(original=original):
                row = next(row for row in self.links["production"] if row["id"] == source)
                link = next(link for link in row["behavior_tests"] if link["original"] == original)
                self.assertEqual(set(link["hosts"]),
                                 {"jvm", "linuxX64", "jsNode", "wasmJsNode",
                                  "wasmWasiNode", "androidHost"})
                changed = copy.deepcopy(self.links)
                target = next(item for item in changed["production"] if item["id"] == source)
                target["behavior_tests"] = [item for item in target["behavior_tests"]
                                            if item["original"] != original]
                self.assertIn("differ", portable_links.check(
                    changed, self.ledger, self.gate, ROOT, UPSTREAM))

    def test_source_artifact_and_receipt_mutations_fail(self):
        for field in ("revision", "artifact_sha256"):
            changed = copy.deepcopy(self.ledger)
            changed["candidate_source"][field] = "0" * (40 if field == "revision" else 64)
            with self.assertRaises(ValueError):
                portable_links.make(changed, self.gate, ROOT, UPSTREAM)
        changed_gate = {**self.gate, "binding_sha256": "0" * 64}
        with self.assertRaises(ValueError):
            portable_links.make(self.ledger, changed_gate, ROOT, UPSTREAM)
