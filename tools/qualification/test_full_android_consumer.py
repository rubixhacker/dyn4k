import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parent))
import full_android_consumer as subject


class OriginalRowTests(unittest.TestCase):
    CASE = {"id": "dyn4k-core:org.dyn4j.ExampleTest#checks",
            "classname": "org.dyn4j.ExampleTest", "method": "checks"}

    def raw(self, rows):
        lines = [
            f"INSTRUMENTATION_STATUS: class={subject.PACKAGE}.FullJourneyTest",
            "INSTRUMENTATION_STATUS: test=allInstalledCases",
            "INSTRUMENTATION_STATUS: numtests=1",
            "INSTRUMENTATION_STATUS_CODE: 1",
        ]
        for identity, status in rows:
            lines.extend((f"INSTRUMENTATION_STATUS: dyn4k_case={identity}",
                          f"INSTRUMENTATION_STATUS: dyn4k_status={status}",
                          "INSTRUMENTATION_STATUS_CODE: 0"))
        lines.extend((f"INSTRUMENTATION_STATUS: class={subject.PACKAGE}.FullJourneyTest",
                      "INSTRUMENTATION_STATUS: test=allInstalledCases",
                      "INSTRUMENTATION_STATUS: numtests=1",
                      "INSTRUMENTATION_STATUS_CODE: 0", "OK (1 test)",
                      "INSTRUMENTATION_CODE: -1"))
        return "\n".join(lines)

    def test_exact_method_row_passes(self):
        raw = self.raw([(self.CASE["id"], "PASSED")])
        xml, observed = subject.xml_from_original_rows(raw, [self.CASE], 0)
        self.assertIn(self.CASE["id"].encode(), xml)
        self.assertEqual(observed["portable"]["passed"], 1)

    def test_missing_duplicate_foreign_and_skipped_rows_fail(self):
        original = self.CASE["id"]
        for rows in ([], [(original, "PASSED"), (original, "PASSED")],
                     [(original + "Foreign", "PASSED")], [(original, "SKIPPED")],
                     [(original, "FAILED")]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                subject.xml_from_original_rows(self.raw(rows), [self.CASE], 0)

    def test_failed_process_cannot_be_normalized(self):
        with self.assertRaises(ValueError):
            subject.xml_from_original_rows(self.raw([(self.CASE["id"], "PASSED")]),
                                           [self.CASE], 1)


class ReplayIntegrityTests(unittest.TestCase):
    def test_missing_helper_and_foreign_source_paths_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            roots = ("dyn4k-core/src/commonTest/kotlin",
                     "dyn4k/src/commonTest/kotlin",
                     "dyn4k-core/src/androidHostTest/kotlin")
            for root in roots:
                source = checkout / root / "Example.kt"
                source.parent.mkdir(parents=True)
                source.write_text("class Example\n")
            helper = checkout / roots[0] / "Helper.kt"
            helper.write_text("class Helper\n")
            original = subject.original_source_hashes(checkout)
            self.assertEqual(subject.verified_original_sources(checkout, original), original)
            missing = original.copy()
            del missing[helper.relative_to(checkout).as_posix()]
            with self.assertRaisesRegex(ValueError, "source file set"):
                subject.verified_original_sources(checkout, missing)
            for foreign in ("/etc/hosts", "../escape.kt", "README.md"):
                with self.subTest(foreign=foreign), self.assertRaises(ValueError):
                    subject.verified_original_sources(checkout, original | {foreign: "0" * 64})

    def test_invented_dexdump_descriptor_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary)
            directory = archive / "debug-dex"
            directory.mkdir()
            dex = b"test dex bytes"
            (directory / "classes.dex").write_bytes(dex)
            with zipfile.ZipFile(archive / "app.apk", "w") as apk:
                apk.writestr("classes.dex", dex)
            genuine = "Class descriptor  : 'Lorg/dyn4j/Real;'\n"
            (directory / "classes.dex.dexdump.txt").write_text(
                genuine + "Class descriptor  : 'Lorg/dyn4j/Invented;'\n")
            completed = mock.Mock(returncode=0, stdout=genuine.encode(), stderr=None)
            with mock.patch.object(subject.subprocess, "run", return_value=completed):
                with self.assertRaisesRegex(ValueError, "dexdump output differs"):
                    subject.archived_dex_descriptors(archive, "debug-dex", "app.apk")


if __name__ == "__main__":
    unittest.main()
