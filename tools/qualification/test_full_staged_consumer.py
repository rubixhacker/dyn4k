import json
import os
import shutil
import tempfile
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
        stage = Path(tempfile.gettempdir()).resolve() / "staging"
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
            ("file", str(stage / "checkout/dyn4k-core/build/libs/dyn4k-core-jvm.jar")),
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


class RetainedRawArchiveTests(unittest.TestCase):
    def setUp(self):
        archive = os.environ.get("DYN4K_SUITE_ARCHIVE")
        if not archive:
            self.skipTest("set DYN4K_SUITE_ARCHIVE for the retained real JVM raw archive")
        self.repository = Path(os.environ["DYN4K_SUITE_REPOSITORY"])
        self.hashes = {"dyn4k-core": os.environ["DYN4K_SUITE_EXPECTED_CORE"],
                       "dyn4k": os.environ["DYN4K_SUITE_EXPECTED_FACADE"]}
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = Path(self.temp.name) / "archive"
        shutil.copytree(archive, self.archive)

    def reseal(self):
        path = self.archive / "receipt.json"
        receipt = json.loads(path.read_bytes())
        receipt.pop("seal_sha256")
        receipt["files"] = suite.inventory(self.archive)
        receipt["seal_sha256"] = suite.sha(suite.encoded(receipt))
        path.write_bytes(suite.encoded(receipt) + b"\n")

    def test_public_positive_and_independent_hash_negative(self):
        self.assertEqual(suite.verify(self.archive, self.repository, self.hashes)["status"],
                         "NOT_RUN")
        with self.assertRaises(ValueError):
            suite.verify(self.archive, self.repository,
                         {**self.hashes, "dyn4k-core": "0" * 64})

    def test_resealed_missing_duplicate_foreign_and_skipped_xml_rejected(self):
        for mutation in ("missing", "duplicate", "foreign", "skipped"):
            with self.subTest(mutation=mutation):
                shutil.rmtree(self.archive)
                shutil.copytree(os.environ["DYN4K_SUITE_ARCHIVE"], self.archive)
                xml = self.archive / "raw/TEST-org.dyn4j.geometry.Vector2NormalizationParityTest.xml"
                root = ET.fromstring(xml.read_bytes())
                cases = root.findall("testcase")
                if mutation == "missing":
                    root.remove(cases[0])
                elif mutation == "duplicate":
                    root.append(ET.fromstring(ET.tostring(cases[0])))
                elif mutation == "foreign":
                    cases[0].set("name", "foreign[jvm]")
                else:
                    ET.SubElement(cases[0], "skipped")
                    root.set("skipped", "1")
                root.set("tests", str(len(root.findall("testcase"))))
                xml.write_bytes(ET.tostring(root))
                self.reseal()
                with self.assertRaises(ValueError):
                    suite.verify(self.archive, self.repository, self.hashes)

    def test_resealed_source_build_graph_and_binary_substitution_rejected(self):
        for mutation in ("graph", "binary", "candidate"):
            with self.subTest(mutation=mutation):
                shutil.rmtree(self.archive)
                shutil.copytree(os.environ["DYN4K_SUITE_ARCHIVE"], self.archive)
                if mutation == "graph":
                    staged = str(suite.staged_binary(Path(json.loads(
                        (self.archive / "receipt.json").read_bytes())["staging_repository"]),
                        "dyn4k-core"))
                    for name in ("test.stdout", "graph.stdout"):
                        path = self.archive / "raw" / name
                        path.write_text(path.read_text().replace(
                            staged, "/checkout/dyn4k-core/build/libs/dyn4k-core-jvm.jar"))
                elif mutation == "binary":
                    path = self.archive / f"resolved/dyn4k-core-jvm-{suite.VERSION}.jar"
                    data = path.read_bytes()
                    path.write_bytes(bytes([data[0] ^ 1]) + data[1:])
                else:
                    path = self.archive / "receipt.json"
                    receipt = json.loads(path.read_bytes())
                    receipt["candidate_sha"] = "25cf11cde2a40072fb8bc3d459f44522864866ff"
                    path.write_bytes(suite.encoded(receipt) + b"\n")
                self.reseal()
                with self.assertRaises(ValueError):
                    suite.verify(self.archive, self.repository, self.hashes)


if __name__ == "__main__":
    unittest.main()
