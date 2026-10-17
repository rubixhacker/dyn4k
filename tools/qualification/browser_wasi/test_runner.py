import os
import tempfile
import unittest
from pathlib import Path

from runner import (gradle_test_task, runtime_version, source_cases, staged_files,
                    verify_reports, verify_wasmtime_output)


class SourceCasesTest(unittest.TestCase):
    def test_collects_each_public_test_identity_across_classes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Suite.kt"
            source.write_text(
                "package sample\n"
                "class FirstTest {\n"
                "  @Test fun identity() {}\n"
                "  @Test\n"
                "  fun collision() {}\n"
                "}\n"
                "class SecondTest {\n"
                "  @Test fun callback() {}\n"
                "}\n"
            )
            self.assertEqual(
                {
                    ("sample.FirstTest", "identity"),
                    ("sample.FirstTest", "collision"),
                    ("sample.SecondTest", "callback"),
                },
                source_cases(Path(directory)),
            )

    def test_rejects_skipped_or_partial_browser_results(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "TEST-suite.xml"
            report.write_text(
                '<testsuite tests="1" failures="0" errors="0" skipped="1">'
                '<testcase classname="jsBrowserTest.sample.FirstTest" '
                'name="identity[js, browser, ChromeHeadless155.0.0.0, Linux0.0.0]">'
                '<skipped/></testcase></testsuite>'
            )
            with self.assertRaisesRegex(ValueError, "skipped"):
                verify_reports(
                    Path(directory),
                    {("sample.FirstTest", "identity")},
                    "jsBrowserTest",
                    "ChromeHeadless155",
                )

            report.write_text('<testsuite tests="0" failures="0" errors="0" skipped="0"/>')
            with self.assertRaisesRegex(ValueError, "zero"):
                verify_reports(
                    Path(directory),
                    {("sample.FirstTest", "identity")},
                    "jsBrowserTest",
                    "ChromeHeadless155",
                )

    def test_wasmtime_requires_finished_physics_case(self):
        expected = {("sample.WorldTest", "collides")}
        started = (
            "##teamcity[testSuiteStarted name='sample']\n"
            "##teamcity[testSuiteStarted name='WorldTest']\n"
            "##teamcity[testStarted name='collides']\n"
        )
        with self.assertRaisesRegex(ValueError, "unfinished"):
            verify_wasmtime_output(started, expected)
        finished = (
            started
            + "##teamcity[testFinished name='collides']\n"
            + "##teamcity[testSuiteFinished name='WorldTest']\n"
            + "##teamcity[testSuiteFinished name='sample']\n"
        )
        self.assertEqual(1, verify_wasmtime_output(finished, expected)["executed"])

    def test_wasmtime_production_selects_binaryen_output_task(self):
        self.assertEqual(
            ":dyn4k-core:compileTestProductionExecutableKotlinWasmWasiOptimize",
            gradle_test_task("dyn4k-core", "wasmWasi", "production"),
        )
        self.assertEqual(
            ":compileTestDevelopmentExecutableKotlinWasmWasi",
            gradle_test_task("consumer", "wasmWasi", "development"),
        )

    def test_runtime_selection_rejects_wrong_binary_and_role(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "browser"
            binary.write_text("#!/bin/sh\nprintf 'Mozilla Firefox 120.0.1\\n'\n")
            os.chmod(binary, 0o755)
            self.assertEqual(
                "Mozilla Firefox 120.0.1",
                runtime_version(binary, "js", "firefox", "120.0.1", "minimum"),
            )
            with self.assertRaisesRegex(ValueError, "pinned matrix"):
                runtime_version(binary, "js", "firefox", "120.0.1", "current")
            with self.assertRaisesRegex(ValueError, "wrong runtime binary"):
                runtime_version(binary, "js", "chromium", "119.0.6045.105", "minimum")

    def test_missing_staged_publication_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "LICENSE.md").write_text("test license\n")
            with self.assertRaisesRegex(ValueError, "missing staged artifact"):
                staged_files(Path(directory))

if __name__ == "__main__":
    unittest.main()
