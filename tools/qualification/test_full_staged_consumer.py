import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import full_staged_consumer as suite


CLASS = "org.dyn4j.geometry.Vector2NormalizationParityTest"
IDS = {f"dyn4k-core:{CLASS}#{name}" for name in ("first", "second")}


def report(names, *, skipped=False):
    root = ET.Element("testsuite", tests=str(len(names)), failures="0", errors="0",
                      skipped=str(int(skipped)), time="0.2")
    for index, name in enumerate(names):
        case = ET.SubElement(root, "testcase", classname=CLASS, name=f"{name}[jvm]",
                             time="0.1")
        if skipped and index == 0:
            ET.SubElement(case, "skipped")
    return ET.tostring(root)


class FullStagedConsumerTests(unittest.TestCase):
    def test_exact_raw_cases(self):
        self.assertEqual(suite.raw_case_ids(report(["first", "second"]), IDS), IDS)

    def test_missing_duplicate_foreign_and_skipped_raw_cases_rejected(self):
        for names, skipped in ((["first"], False), (["first", "first"], False),
                               (["first", "foreign"], False),
                               (["first", "second"], True)):
            with self.subTest(names=names, skipped=skipped):
                with self.assertRaises(ValueError):
                    suite.raw_case_ids(report(names, skipped=skipped), IDS)

    def test_original_test_source_must_be_in_approved_manifest(self):
        manifest = {"lanes": {"jvm:Java:current:default": {
            "case_scopes": ["portable", "jvm"], "target": "jvm", "runtime": "Java",
            "version": "current", "configuration": "default"}},
                    "cases": [{"id": case, "classname": CLASS, "method": case.split("#")[-1],
                               "module": "dyn4k-core", "scope": "portable",
                               "source": {"path": "dyn4k-core/src/commonTest/kotlin/org/dyn4j/geometry/Vector2NormalizationParityTest.kt",
                                          "sha256": "a" * 64}}
                              for case in sorted(IDS)]}
        self.assertEqual(suite.class_contract(manifest, "jvm:Java:current:default", CLASS)[0], IDS)
        manifest["cases"][0]["source"]["path"] = "other.kt"
        with self.assertRaises(ValueError):
            suite.class_contract(manifest, "jvm:Java:current:default", CLASS)

    def test_graph_rejects_source_build_substitution_and_provider_changes(self):
        stage = Path("/staging")
        hashes = {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64}
        artifacts = []
        for module in suite.MODULES:
            path = suite.staged_binary(stage, module)
            artifacts.append({"component": f"{suite.GROUP}:{module}-jvm:{suite.VERSION}",
                              "file": str(path), "name": path.name, "size": 1,
                              "sha256": hashes[module]})
        graph = {"configuration": "jvmTestRuntimeClasspath", "artifacts": artifacts,
                 "components": [item["component"] for item in artifacts] +
                 [f"{suite.GROUP}:{module}:{suite.VERSION}" for module in suite.MODULES]}
        self.assertEqual(set(suite.graph_artifacts(graph, stage, hashes)), set(suite.MODULES))
        changes = (
            ("file", "/checkout/dyn4k-core/build/libs/dyn4k-core-jvm.jar"),
            ("component", "org.dyn4j:dyn4j:6.0.0"),
            ("sha256", "c" * 64),
        )
        for field, value in changes:
            with self.subTest(field=field):
                changed = {**graph, "artifacts": [{**artifacts[0], field: value}, artifacts[1]]}
                with self.assertRaises(ValueError):
                    suite.graph_artifacts(changed, stage, hashes)
        with self.assertRaises(ValueError):
            suite.graph_artifacts({**graph, "artifacts": artifacts + [artifacts[0]]}, stage, hashes)


if __name__ == "__main__":
    unittest.main()
