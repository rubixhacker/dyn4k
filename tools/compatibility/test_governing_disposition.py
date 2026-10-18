from __future__ import annotations

import copy
import gzip
import json
import unittest
from pathlib import Path

import governing_disposition


ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = Path("/tmp/dyn4k-baseline-cache/dyn4j-source")
RECEIPTS = ROOT / "tools/compatibility/receipts"


@unittest.skipUnless(UPSTREAM.is_dir(), "pinned source checkout unavailable")
class GoverningDispositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads((ROOT / "tools/compatibility/declaration-ledger.json").read_text())
        cls.report = json.loads(gzip.decompress(
            (RECEIPTS / "governing-disposition-final-0681a8cd.json.gz").read_bytes()))

    def test_governing_rows_keep_raw_diagnostics_and_target_lanes_separate(self):
        self.assertIsNone(governing_disposition.check(self.report, self.ledger, ROOT, UPSTREAM))
        self.assertEqual(len(self.report["production"]), 268)
        self.assertEqual(len(self.report["declarations"]), 3508)
        self.assertEqual(self.report["raw_diagnostics"]["unequal"], 156)
        self.assertEqual(self.report["raw_diagnostics"]["accepted_unequal"], 156)
        self.assertEqual(self.report["source_implementation"]["accepted"], 268)
        self.assertEqual(self.report["source_compatibility"]["accepted"], 3508)
        self.assertEqual(self.report["behavior_coverage"]["accepted"], 3508)
        self.assertEqual(self.report["behavior_coverage"]["unresolved"], 0)
        self.assertEqual(self.report["target_qualification"]["future_lanes_passed"], 0)
        self.assertEqual(self.report["target_qualification"]["future_lanes_unpassed"], 112)
        rows = {row["id"]: row for row in self.report["declarations"]}
        self.assertEqual(rows["org.dyn4j.collision.Filter$1|type"]["behavior_status"],
                         "executed-original-common-case")
        self.assertEqual(rows["org.dyn4j.collision.broadphase.package-info|type"]
                         ["behavior_status"], "documentation-only")
        self.assertEqual(rows["org.dyn4j.world.PhysicsWorld|addJoint|(Lorg/dyn4j/dynamics/joint/Joint;)V"]
                         ["behavior_status"], "executed-concrete-dispatch")
        module = next(row for row in self.report["production"]
                      if row["id"] == "src/main/java/module-info.java")
        self.assertEqual({entry["kind"] for entry in module["behavior_evidence"]},
                         {"module-descriptor", "named-module-consumer", "java8-classpath"})

    def test_method_hit_raw_acceptance_and_row_deletion_mutations_fail(self):
        changed = copy.deepcopy(self.report)
        changed["declarations"].pop()
        self.assertIn("differs", governing_disposition.check(changed, self.ledger,
                                                              ROOT, UPSTREAM))
        changed = copy.deepcopy(self.report)
        row = next(row for row in changed["declarations"]
                   if row["behavior_status"] == "executed-java-method")
        row["behavior_evidence"]["covered_instructions"] = 0
        self.assertIn("differs", governing_disposition.check(changed, self.ledger,
                                                              ROOT, UPSTREAM))
        changed = copy.deepcopy(self.report)
        changed["raw_diagnostics"]["unequal"] = 0
        self.assertIn("differs", governing_disposition.check(changed, self.ledger,
                                                              ROOT, UPSTREAM))
        changed_ledger = copy.deepcopy(self.ledger)
        changed_ledger["module"]["evidence"] = changed_ledger["module"]["evidence"][:-1]
        self.assertIn("named-module evidence inventory", governing_disposition.check(
            self.report, changed_ledger, ROOT, UPSTREAM))

    def test_unlinked_abstract_contracts_have_executed_concrete_targets(self):
        links = governing_disposition.receipt(
            ROOT, self.ledger["review_receipts"]["portable_links"])
        abstract = [row for row in links["declarations"]
                    if row["link_status"] == "no-direct-original-test"
                    and len(row["id"].split("|")) == 3
                    and " abstract " in " " + row["baseline_signature"] + " "]
        self.assertEqual(len(abstract), 501)
        dispositions = {row["id"]: row for row in self.report["declarations"]}
        for row in abstract:
            observed = dispositions[row["id"]]
            self.assertEqual(observed["behavior_status"], "executed-concrete-dispatch")
            self.assertTrue(observed["behavior_evidence"]["implementations"])
            for target in observed["behavior_evidence"]["implementations"]:
                self.assertTrue({"unchanged-java-corpus", "governing-seam-probe"} &
                                set(target["executed_implementation"]["execution_routes"]))
        detect = dispositions[
            "org.dyn4j.collision.broadphase.BroadphaseDetector|detect|()Ljava/util/List;"]
        concrete = {target["concrete_type"] for target in
                    detect["behavior_evidence"]["implementations"]}
        self.assertTrue({"org/dyn4j/collision/broadphase/DynamicAABBTree",
                         "org/dyn4j/collision/broadphase/Sap",
                         "org/dyn4j/collision/broadphase/BruteForceBroadphase"} <= concrete)
        self.assertTrue(all("unchanged-java-corpus" in target["executed_implementation"]
                            ["execution_routes"] for target in
                            detect["behavior_evidence"]["implementations"]))

    def test_bridge_and_static_forwarder_require_exact_pure_dispatch(self):
        bridge = [25, 182, 192, 176]
        static = [178, 25, 182, 177]
        self.assertTrue(governing_disposition.pure_forwarder(
            bridge, 0x1041, ["ACC_PUBLIC", "ACC_BRIDGE", "ACC_SYNTHETIC"],
            "public org.dyn4j.Copyable copy();", 1))
        self.assertTrue(governing_disposition.pure_forwarder(
            static, 0x0009, ["ACC_PUBLIC"], "public static void run();", 1))
        for opcodes, flags, baseline, signature, calls in (
                (bridge, 0x0001, ["ACC_PUBLIC", "ACC_BRIDGE"], "public Copyable copy();", 1),
                (static, 0x0001, ["ACC_PUBLIC"], "public static void run();", 1),
                ([25, 182, 153, 176], 0x1041,
                 ["ACC_PUBLIC", "ACC_BRIDGE", "ACC_SYNTHETIC"], "public Copyable copy();", 1),
                ([25, 182, 182, 176], 0x1041,
                 ["ACC_PUBLIC", "ACC_BRIDGE", "ACC_SYNTHETIC"], "public Copyable copy();", 2)):
            with self.subTest(opcodes=opcodes, flags=flags):
                self.assertFalse(governing_disposition.pure_forwarder(
                    opcodes, flags, baseline, signature, calls))
