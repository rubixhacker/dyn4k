import sys
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
