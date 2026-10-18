import unittest
import tempfile
import hashlib
from pathlib import Path

from evidence import parse_instrumentation, validate_lane
from run import instrumentation_filter, verify_installed_apk


class InstrumentationEvidenceTest(unittest.TestCase):
    def test_api21_candidate_uses_exact_short_testfile_argument(self):
        portable = [f"org.dyn4j.coverage.LongPortableCase{index:03d}Test"
                    for index in range(171)]
        prepared = {"portable_classes": portable}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            classes, arguments, selection = instrumentation_filter(
                prepared, "candidate", "debug", "21", directory)
            self.assertEqual(len(classes), 173)
            self.assertEqual(arguments, ["-e", "testFile",
                                         "/data/local/tmp/dyn4k-candidate-debug-classes.txt"])
            self.assertEqual(selection.read_text().splitlines(), list(classes))
            self.assertGreater(selection.stat().st_size, 4096)
            _, newer_arguments, newer_selection = instrumentation_filter(
                prepared, "candidate", "debug", "37", directory)
            self.assertEqual(newer_arguments, ["-e", "class", ",".join(classes)])
            self.assertIsNone(newer_selection)
            baseline_classes, baseline_arguments, baseline_selection = instrumentation_filter(
                prepared, "baseline", "debug", "21", directory)
            self.assertEqual(baseline_arguments,
                             ["-e", "class", ",".join(baseline_classes)])
            self.assertIsNone(baseline_selection)

    def test_installed_apk_hash_rejects_wrong_device_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            apk = Path(temporary) / "installed-base.apk"
            apk.write_bytes(b"device APK")
            digest = hashlib.sha256(b"device APK").hexdigest()
            self.assertEqual(verify_installed_apk(apk, digest)["sha256"], digest)
            apk.write_bytes(b"forged APK")
            with self.assertRaisesRegex(ValueError, "installed APK differs"):
                verify_installed_apk(apk, digest)

    def test_accepts_distinct_executed_consumer_and_portable_cases(self):
        raw = """INSTRUMENTATION_STATUS: class=ConsumerJourneyTest
INSTRUMENTATION_STATUS: test=worldAndCallbacks
INSTRUMENTATION_STATUS_CODE: 1
INSTRUMENTATION_STATUS: class=ConsumerJourneyTest
INSTRUMENTATION_STATUS: test=worldAndCallbacks
INSTRUMENTATION_STATUS_CODE: 0
INSTRUMENTATION_STATUS: dyn4k_case=org.dyn4j.world.WorldResultTest#resultIsMutable
INSTRUMENTATION_STATUS: dyn4k_status=PASSED
INSTRUMENTATION_STATUS_CODE: 0
INSTRUMENTATION_STATUS: class=PortableSuiteTest
INSTRUMENTATION_STATUS: test=allPortableCases
INSTRUMENTATION_STATUS_CODE: 0
INSTRUMENTATION_RESULT: stream=
OK (2 tests)
INSTRUMENTATION_CODE: -1
"""
        result = parse_instrumentation(raw)
        self.assertEqual(result["instrumentation"]["passed"], 2)
        self.assertEqual(result["portable"]["passed"], 1)
        validate_lane(result, {"org.dyn4j.world.WorldResultTest#resultIsMutable"},
                      {"ConsumerJourneyTest#worldAndCallbacks", "PortableSuiteTest#allPortableCases"}, 0)

    def test_rejects_missing_portable_case(self):
        raw = "INSTRUMENTATION_STATUS: class=Suite\nINSTRUMENTATION_STATUS: test=passes\nINSTRUMENTATION_STATUS_CODE: 0\nOK (1 test)\nINSTRUMENTATION_CODE: -1\n"
        result = parse_instrumentation(raw)
        with self.assertRaisesRegex(ValueError, "missing"):
            validate_lane(result, {"Missing#test"}, {"Suite#passes"}, 0)

    def test_rejects_skipped_case(self):
        raw = """INSTRUMENTATION_STATUS: dyn4k_case=Suite#test
INSTRUMENTATION_STATUS: dyn4k_status=SKIPPED
INSTRUMENTATION_STATUS_CODE: 0
INSTRUMENTATION_STATUS: class=Suite
INSTRUMENTATION_STATUS: test=passes
INSTRUMENTATION_STATUS_CODE: 0
OK (1 test)
INSTRUMENTATION_CODE: -1
"""
        with self.assertRaisesRegex(ValueError, "skipped"):
            validate_lane(parse_instrumentation(raw), {"Suite#test"}, {"Suite#passes"}, 0)

    def test_rejects_duplicate_case(self):
        raw = """INSTRUMENTATION_STATUS: dyn4k_case=Suite#test
INSTRUMENTATION_STATUS: dyn4k_status=PASSED
INSTRUMENTATION_STATUS_CODE: 0
INSTRUMENTATION_STATUS: dyn4k_case=Suite#test
INSTRUMENTATION_STATUS: dyn4k_status=PASSED
INSTRUMENTATION_STATUS_CODE: 0
OK (1 test)
INSTRUMENTATION_CODE: -1
"""
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_instrumentation(raw)

    def test_retains_multiline_failure_cause(self):
        raw = """INSTRUMENTATION_STATUS: class=Suite
INSTRUMENTATION_STATUS: test=fails
INSTRUMENTATION_STATUS: stack=java.lang.AssertionError
Caused by: java.lang.LinkageError: method became final
INSTRUMENTATION_STATUS_CODE: -2
OK (1 test)
INSTRUMENTATION_CODE: -1
"""
        result = parse_instrumentation(raw)
        self.assertIn("LinkageError", result["instrumentation"]["cases"]["Suite#fails"]["stack"])

    def test_rejects_failed_duplicate_or_nonterminal_runner_code(self):
        cases = """INSTRUMENTATION_STATUS: class=Suite
INSTRUMENTATION_STATUS: test=passes
INSTRUMENTATION_STATUS_CODE: 0
INSTRUMENTATION_RESULT: stream=
OK (1 test)
"""
        for suffix in ("INSTRUMENTATION_CODE: 0\n",
                       "INSTRUMENTATION_CODE: -1\nINSTRUMENTATION_CODE: -1\n",
                       "INSTRUMENTATION_CODE: -1\ntrailing output\n"):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                validate_lane(parse_instrumentation(cases + suffix), set(), {"Suite#passes"}, 0)

    def test_rejects_missing_duplicate_or_inconsistent_summary(self):
        case = """INSTRUMENTATION_STATUS: class=Suite
INSTRUMENTATION_STATUS: test=passes
INSTRUMENTATION_STATUS_CODE: 0
INSTRUMENTATION_RESULT: stream=
"""
        for summary in ("", "OK (2 tests)\n", "OK (0 tests)\n",
                        "OK (1 test)\nOK (1 test)\n", "OK (1 test)\nother final result\n",
                        "FAILURES!!!\nTests run: 1,  Failures: 1\n"):
            with self.subTest(summary=summary), self.assertRaises(ValueError):
                validate_lane(parse_instrumentation(case + summary + "INSTRUMENTATION_CODE: -1\n"),
                              set(), {"Suite#passes"}, 0)

    def test_rejects_summary_before_case_execution(self):
        raw = "OK (1 test)\nINSTRUMENTATION_STATUS: class=Suite\nINSTRUMENTATION_STATUS: test=passes\nINSTRUMENTATION_STATUS_CODE: 0\nINSTRUMENTATION_CODE: -1\n"
        with self.assertRaises(ValueError):
            validate_lane(parse_instrumentation(raw), set(), {"Suite#passes"}, 0)

    def test_rejects_failed_instrumentation_process_exit(self):
        raw = """INSTRUMENTATION_STATUS: class=Suite
INSTRUMENTATION_STATUS: test=passes
INSTRUMENTATION_STATUS_CODE: 0
INSTRUMENTATION_RESULT: stream=
OK (1 test)
INSTRUMENTATION_CODE: -1
"""
        with self.assertRaisesRegex(ValueError, "process exit"):
            validate_lane(parse_instrumentation(raw), set(), {"Suite#passes"}, 1)


if __name__ == "__main__":
    unittest.main()
