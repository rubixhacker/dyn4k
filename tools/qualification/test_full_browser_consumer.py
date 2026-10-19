import unittest
import xml.etree.ElementTree as ET
import json

import full_browser_consumer as browser


class BrowserRowsTest(unittest.TestCase):
    def setUp(self):
        self.selected = {("org.dyn4j.SampleTest", "first"): "core:first",
                         ("org.dyn4j.SampleTest", "second"): "core:second"}

    def xml(self, names, tests=None, failures=0, skipped=0):
        suite = ET.Element("testsuite", {"name": "jsBrowserTest.org.dyn4j.SampleTest",
                                         "tests": str(len(names) if tests is None else tests),
                                         "failures": str(failures), "errors": "0",
                                         "skipped": str(skipped)})
        for name in names:
            ET.SubElement(suite, "testcase", {
                "classname": "jsBrowserTest.org.dyn4j.SampleTest",
                "name": f"{name}[js, browser, ChromeHeadless155.0.0.0, Linux0.0.0]"})
        return suite

    def test_original_order_is_preserved(self):
        suite = self.xml(["second", "first"])
        self.assertEqual(browser.rows(ET.tostring(suite), self.selected, 155),
                         ["core:second", "core:first"])

    def test_duplicate_method_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicates"):
            browser.rows(ET.tostring(self.xml(["first", "first"])), self.selected, 155)

    def test_foreign_method_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "foreign"):
            browser.rows(ET.tostring(self.xml(["first", "foreign"])), self.selected, 155)

    def test_wrong_chromium_version_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "runtime"):
            browser.rows(ET.tostring(self.xml(["first"])), self.selected, 119)

    def test_missing_count_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            browser.rows(ET.tostring(self.xml(["first"], tests=2)), self.selected, 155)

    def test_failing_and_skipped_rows_are_rejected(self):
        failed = self.xml(["first"], failures=1)
        failed[0].append(ET.Element("failure"))
        with self.assertRaisesRegex(ValueError, "failing"):
            browser.rows(ET.tostring(failed), self.selected, 155)
        skipped = self.xml(["first"], skipped=1)
        skipped[0].append(ET.Element("skipped"))
        with self.assertRaisesRegex(ValueError, "skipped"):
            browser.rows(ET.tostring(skipped), self.selected, 155)

    def test_input_map_rejects_duplicate_and_malformed_rows(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            browser.selected_map(b"a\tA\tm\na\tA\tm\n")
        with self.assertRaisesRegex(ValueError, "differs"):
            browser.selected_map(b"a\tA\n")

    def karma(self, methods):
        suite = "org.dyn4j SampleTest.Chrome Headless 155.0.0.0 (Linux 0.0.0)"
        flow = "karmaTC123"
        messages = [f"##teamcity[testSuiteStarted name='{suite}' flowId='{flow}']"]
        for method in methods:
            messages.extend((
                f"##teamcity[testStarted name='{method}' captureStandardOutput='true' flowId='{flow}']",
                f"##teamcity[testFinished name='{method}' duration='' flowId='{flow}']"))
        messages.append(f"##teamcity[testSuiteFinished name='{suite}' duration='%s' flowId='{flow}']")
        return b"".join((json.dumps({"sha256": browser.sha(message.encode()),
                                     "message": message}) + "\n").encode()
                        for message in messages)

    def test_raw_karma_methods_are_replayed(self):
        self.assertEqual(browser.karma_rows(self.karma(["second", "first"]),
                                            self.selected, 155),
                         ["core:second", "core:first"])

    def test_raw_karma_rejects_missing_duplicate_and_foreign_methods(self):
        for methods in (["first"], ["first", "first"], ["first", "foreign"]):
            with self.subTest(methods=methods), self.assertRaises(ValueError):
                browser.karma_rows(self.karma(methods), self.selected, 155)

    def test_raw_karma_rejects_wrong_runtime(self):
        with self.assertRaisesRegex(ValueError, "suite start"):
            browser.karma_rows(self.karma(["first", "second"]), self.selected, 119)


if __name__ == "__main__":
    unittest.main()
