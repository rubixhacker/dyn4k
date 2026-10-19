import unittest
import xml.etree.ElementTree as ET
import json
import tempfile
from pathlib import Path
from unittest import mock

import full_browser_consumer as browser


class BrowserRowsTest(unittest.TestCase):
    def setUp(self):
        self.selected = {("org.dyn4j.SampleTest", "first"): "core:first",
                         ("org.dyn4j.SampleTest", "second"): "core:second"}

    def xml(self, names, tests=None, failures=0, skipped=0):
        suite = ET.Element("testsuite", {"name": "jsBrowserTest.org.dyn4j.SampleTest",
                                         "tests": str(len(names) if tests is None else tests),
                                         "failures": str(failures), "errors": "0",
                                         "skipped": str(skipped), "time": "0.25"})
        for name in names:
            ET.SubElement(suite, "testcase", {
                "classname": "jsBrowserTest.org.dyn4j.SampleTest",
                "name": f"{name}[js, browser, ChromeHeadless155.0.0.0, Linux0.0.0]",
                "time": "0.01"})
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

    def test_missing_nonfinite_and_negative_xml_durations_are_rejected(self):
        for target in ("suite", "case"):
            for value in (None, "NaN", "Infinity", "-1", "-0.0"):
                with self.subTest(target=target, value=value):
                    suite = self.xml(["first"])
                    element = suite if target == "suite" else suite[0]
                    if value is None:
                        del element.attrib["time"]
                    else:
                        element.set("time", value)
                    with self.assertRaisesRegex(ValueError, "duration"):
                        browser.rows(ET.tostring(suite), self.selected, 155)

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


class SelectedBundleTest(unittest.TestCase):
    middle = b");\nconfig.set({webpack: createWebpackConfig()});\n\n"
    reporter = b"const reviewedReporter = true;\n"
    port = 34567

    def settings(self, work, mode):
        _, selected, runner = browser.bundle_paths(work, "core", mode)
        paths = [str(runner), str(selected)]
        return {"singleRun": True, "autoWatch": False,
                "basePath": str(work / "root/js/packages" /
                                "dyn4k-full-staged-browser-consumer-core-test"),
                "files": paths, "frameworks": ["webpack-output", "mocha", "webpack"],
                "client": {"args": []}, "browsers": ["ChromeHeadless"],
                "customLaunchers": {}, "failOnFailingTestSuite": False,
                "failOnEmptyTestSuite": False, "reporters": ["karma-kotlin-reporter"],
                "preprocessors": {path: ["webpack", "sourcemap"] for path in paths},
                "proxies": {}, "webpackCopy": []}

    def config(self, settings):
        return (browser.KARMA_HEADER + json.dumps(settings).encode() + self.middle
                + browser.KARMA_REPORTER_MARKER + self.reporter
                + f"\n\n// qualification-port.js\nconfig.set({{port: {self.port}}});\n\n\n\n\n}}\n".encode())

    def test_configured_paths_and_later_overrides(self):
        work = Path("/evidence/build")
        with mock.patch.object(browser, "KARMA_GENERATED_MIDDLE_SHA256", browser.sha(self.middle)):
            for mode in ("development", "production"):
                with self.subTest(mode=mode):
                    settings = self.settings(work, mode)
                    raw = self.config(settings)
                    self.assertEqual(browser.configured_bundle(raw, work, "core", mode,
                                                               self.reporter, self.port),
                                     browser.bundle_paths(work, "core", mode)[:2])
                    for override in (b"config.set({files: [runner, selected, '/tmp/extra.js']});\n",
                                     b"config.set({preprocessors: {'/tmp/extra.js': ['webpack']}});\n"):
                        for marker in (browser.KARMA_REPORTER_MARKER,
                                       b"// qualification-port.js"):
                            changed = raw.replace(marker, override + marker)
                            with self.subTest(override=override, marker=marker), self.assertRaisesRegex(
                                    ValueError, "later override"):
                                browser.configured_bundle(changed, work, "core", mode,
                                                          self.reporter, self.port)
                    settings["files"].append("/tmp/untracked-injection.js")
                    with self.assertRaisesRegex(ValueError, "selected bundle path"):
                        browser.configured_bundle(self.config(settings), work, "core", mode,
                                                  self.reporter, self.port)

    def test_effective_files_reject_extra_script_and_changed_preprocessor(self):
        work = Path("/evidence/build")
        tmpdir = "/evidence/tmp"
        webpack = Path(tmpdir) / "_karma_webpack_123"
        _, selected, runner = browser.bundle_paths(work, "core", "development")
        root = work / "root/js/node_modules"
        evidence = {"tmpdir": tmpdir,
                    "effective_files": [str(webpack / "runtime.js"),
                                        str(webpack / "commons.js"),
                                        str(root / "mocha/mocha.js"),
                                        str(root / "karma-mocha/lib/adapter.js"),
                                        str(runner), str(selected), str(webpack / "**/*")],
                    "effective_preprocessors": {str(path): ["webpack", "sourcemap"]
                                                for path in (runner, selected)},
                    "input_sha256": {str(root / name): digest for name, digest
                                     in browser.RUNTIME_INPUT_SHA256.items()}}
        browser.effective_files(evidence, work, "core", "development")
        evidence["effective_files"].insert(5, "/tmp/untracked-injection.js")
        with self.assertRaisesRegex(ValueError, "effective file list"):
            browser.effective_files(evidence, work, "core", "development")
        evidence["effective_files"].pop(5)
        evidence["effective_preprocessors"][str(selected)] = ["sourcemap"]
        with self.assertRaisesRegex(ValueError, "preprocessors"):
            browser.effective_files(evidence, work, "core", "development")

    def test_resealed_selected_copy_must_match_linked_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            work = folder / "build"
            linked, selected, runner = browser.bundle_paths(work, "core", "development")
            config = self.settings(work, "development")
            (folder / "karma.conf.js").write_bytes(self.config(config))
            (folder / "browser-reporter.js").write_bytes(self.reporter)
            (folder / "linked-executable.js").write_bytes(b"linked bytes")
            (folder / "karma-selected.js").write_bytes(b"different selected bytes")
            evidence = {"source_path": str(selected), "archive_path": str(folder / "karma-selected.js"),
                        "sha256": browser.sha(b"different selected bytes"), "node_pid": 123,
                        "browser_id": "browser-id", "browser_name": "Chrome Headless 155.0.0.0 (Linux 0.0.0)",
                        "captured_ns": 2, "complete_ns": 3}
            (folder / "selected-bundle.json").write_text(json.dumps(evidence))
            record = {"started_ns": 1, "finished_ns": 4,
                      "linked_sha256": browser.sha(b"linked bytes"), "karma_port": self.port}
            with mock.patch.object(browser, "KARMA_GENERATED_MIDDLE_SHA256",
                                   browser.sha(self.middle)):
                with self.assertRaisesRegex(ValueError, "selected bundle bytes"):
                    browser.selected_bundle(folder, work, "core", "development", record, 155)


if __name__ == "__main__":
    unittest.main()
