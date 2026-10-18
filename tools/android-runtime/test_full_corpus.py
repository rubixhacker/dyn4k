import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import android_corpus
import prepare
import run


class FullCorpusEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.manifest = {"cases": [
            {"id": "dyn4k-core:org.dyn4j.CoreTest#works", "module": "dyn4k-core",
             "classname": "org.dyn4j.CoreTest", "method": "works", "scope": "portable"},
            {"id": "dyn4k:io.github.FacadeTest#works", "module": "dyn4k",
             "classname": "io.github.FacadeTest", "method": "works", "scope": "portable"},
        ]}
        for module, classname in (("dyn4k-core", "org.dyn4j.CoreTest"),
                                  ("dyn4k", "io.github.FacadeTest")):
            directory = self.root / module / "build/test-results/jvmTest"
            directory.mkdir(parents=True)
            self.xml(module, classname, "works")

    def tearDown(self):
        self.temporary.cleanup()

    def xml(self, module, classname, method, suffix=""):
        path = self.root / module / "build/test-results/jvmTest" / f"TEST-{classname}.xml"
        path.write_text(f'<testsuite tests="1" failures="0" errors="0" skipped="0">'
                        f'<testcase classname="{classname}" name="{method}[jvm]">{suffix}</testcase>'
                        '</testsuite>')

    def test_accepts_exact_raw_xml_and_records_hashes(self):
        result = android_corpus.verify_jvm_xml(self.root, self.manifest)
        self.assertEqual(len(result["case_ids"]), 2)
        self.assertEqual(len(result["xml_files"]), 2)

    def test_rejects_missing_extra_duplicate_skipped_failed_or_forged_xml(self):
        variants = (
            ("dyn4k", "io.github.FacadeTest", "other", ""),
            ("dyn4k", "io.github.FacadeTest", "works", "<skipped/>") ,
            ("dyn4k", "io.github.FacadeTest", "works", "<failure/>") ,
        )
        for module, classname, method, suffix in variants:
            with self.subTest(method=method, suffix=suffix):
                self.xml(module, classname, method, suffix)
                with self.assertRaises(ValueError):
                    android_corpus.verify_jvm_xml(self.root, self.manifest)
        self.xml("dyn4k", "io.github.FacadeTest", "works")
        path = self.root / "dyn4k/build/test-results/jvmTest/TEST-io.github.FacadeTest.xml"
        path.write_text(path.read_text().replace('tests="1"', 'tests="2"'))
        with self.assertRaises(ValueError):
            android_corpus.verify_jvm_xml(self.root, self.manifest)
        self.xml("dyn4k", "io.github.FacadeTest", "works")
        duplicate = path.with_name("TEST-duplicate.xml")
        duplicate.write_bytes(path.read_bytes())
        with self.assertRaises(ValueError):
            android_corpus.verify_jvm_xml(self.root, self.manifest)

    def test_generated_full_app_inputs_detect_tampering(self):
        inputs = android_corpus.write_full_inputs(self.root, self.manifest)
        android_corpus.verify_full_inputs(self.root, self.manifest, inputs)
        asset = Path(inputs["case_asset"]["path"])
        asset.write_text(asset.read_text() + "forged\n")
        with self.assertRaisesRegex(ValueError, "full app input"):
            android_corpus.verify_full_inputs(self.root, self.manifest, inputs)
        with self.assertRaisesRegex(ValueError, "full app input"):
            android_corpus.verify_full_inputs(self.root, self.manifest, None)

    def test_full_rules_retain_exact_reflective_filter_types(self):
        rules = android_corpus.full_app_inputs(self.manifest)["keep_rules"].decode()
        types = (
            "CollisionModelConsumer$RootFilter", "CollisionModelConsumer$ChildFilter",
            "CollisionModelConsumer$OtherFilter",
            "org.dyn4j.collision.CollisionModelTest$RootFilter",
            "org.dyn4j.collision.CollisionModelTest$ChildFilter",
            "org.dyn4j.collision.CollisionModelTest$OtherFilter",
            "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest$Parent",
            "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest$Child",
            "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest$Sibling",
            "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest$Unrelated",
        )
        for name in types:
            self.assertIn(f"-keep,allowobfuscation class {name}\n", rules)
        self.assertNotIn("-keep class org.dyn4j.collision.TypeFilter", rules)

    def test_x86_dexopt_exception_retains_only_matrix_normmax_member(self):
        matrix = "org.dyn4j.coverage.UpstreamMatrix22CoverageTest"
        suite = {"cases": [
            {"id": f"dyn4k-core:{matrix}#norm", "module": "dyn4k-core",
             "classname": matrix, "method": "norm", "scope": "portable"},
            {"id": "dyn4k-core:org.dyn4j.coverage.OtherTest#norm", "module": "dyn4k-core",
             "classname": "org.dyn4j.coverage.OtherTest", "method": "norm", "scope": "portable"},
        ]}
        inputs = android_corpus.full_app_inputs(suite)
        rules = inputs["keep_rules"].decode().splitlines()
        self.assertIn(f"-keep,allowoptimization class {matrix} {{ *; }}", rules)
        self.assertIn("-keepclassmembers class org.dyn4j.geometry.Matrix22 "
                      "{ public double normMax(); }", rules)
        self.assertEqual(sum(line.startswith("-keepclassmembers class org.dyn4j.geometry.Matrix22")
                             for line in rules), 1)
        self.assertIn("-keep,allowoptimization class org.dyn4j.coverage.OtherTest { *; }", rules)
        self.assertEqual(sum(matrix in line for line in rules), 1)
        self.assertIn(f"dyn4k-core:{matrix}#norm\t{matrix}\tnorm",
                      inputs["case_asset"].decode().splitlines())

    def test_rejects_changed_manifest_or_raw_xml_after_preparation(self):
        binding = {"sha256": "frozen"}
        prepared = {"suite_manifest": binding,
                    "jvm_xml": android_corpus.verify_jvm_xml(self.root, self.manifest)}
        with patch.object(android_corpus, "load_suite", return_value=(self.manifest, binding)), \
                patch.object(android_corpus, "commit_time_ns", return_value=0):
            android_corpus.verify_xml_pins(self.root, prepared)
            prepared["suite_manifest"] = {"sha256": "forged"}
            with self.assertRaisesRegex(ValueError, "manifest"):
                android_corpus.verify_xml_pins(self.root, prepared)
            prepared["suite_manifest"] = binding
            self.xml("dyn4k", "io.github.FacadeTest", "other")
            with self.assertRaises(ValueError):
                android_corpus.verify_xml_pins(self.root, prepared)

    def test_rejects_xml_older_than_candidate_commit(self):
        threshold = max(path.stat().st_mtime_ns for path in
                        self.root.glob("*/build/test-results/jvmTest/TEST-*.xml")) + 1
        with self.assertRaisesRegex(ValueError, "stale raw JVM"):
            android_corpus.verify_jvm_xml(self.root, self.manifest, min_mtime_ns=threshold)

    def test_portable_jar_retains_abstract_common_test_helpers(self):
        classes = self.root / "dyn4k-core/build/classes/kotlin/jvm/test/org/dyn4j"
        classes.mkdir(parents=True)
        (classes / "CoreTest.class").write_bytes(b"case")
        (classes / "AbstractShapeTest.class").write_bytes(b"helper")
        (self.root / "dyn4k/build/classes/kotlin/jvm/test").mkdir(parents=True)
        jar = self.root / "portable.jar"
        prepare.build_portable_jar(self.root, jar, jvm_only_classes=set())
        with zipfile.ZipFile(jar) as archive:
            self.assertIn("org/dyn4j/AbstractShapeTest.class", archive.namelist())

    def test_portable_class_inventory_follows_manifest_and_rejects_missing_class(self):
        core = self.root / "dyn4k-core/build/classes/kotlin/jvm/test/org/dyn4j/CoreTest.class"
        facade = self.root / "dyn4k/build/classes/kotlin/jvm/test/io/github/FacadeTest.class"
        core.parent.mkdir(parents=True)
        facade.parent.mkdir(parents=True)
        core.write_bytes(b"core")
        facade.write_bytes(b"facade")
        self.assertEqual(prepare.portable_classes(self.root, self.manifest),
                         ["io.github.FacadeTest", "org.dyn4j.CoreTest"])
        facade.unlink()
        with self.assertRaisesRegex(ValueError, "compiled portable test missing"):
            prepare.portable_classes(self.root, self.manifest)

    def test_installed_runner_selects_only_frozen_test_classes(self):
        prepared = {"portable_classes": ["org.dyn4j.CoreTest", "io.github.FacadeTest"]}
        candidate = run.instrumentation_classes(prepared, "candidate")
        self.assertIn("org.dyn4j.CoreTest", candidate)
        self.assertIn("io.github.FacadeTest", candidate)
        self.assertNotIn("org.dyn4j.AbstractShapeTest", candidate)
        self.assertEqual(len(run.instrumentation_classes(prepared, "baseline")), 1)


if __name__ == "__main__":
    unittest.main()
