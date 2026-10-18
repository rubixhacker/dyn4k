import unittest

from evidence import parse_instrumentation, validate_lane


class InstrumentationEvidenceTest(unittest.TestCase):
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
