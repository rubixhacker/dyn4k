import os
import json
import hashlib
import shutil
import subprocess
import sys
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

    def test_rejects_browser_major_that_only_starts_with_selected_major(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "TEST-suite.xml"
            report.write_text(
                '<testsuite tests="1" failures="0" errors="0" skipped="0">'
                '<testcase classname="jsBrowserTest.sample.FirstTest" '
                'name="identity[js, browser, ChromeHeadless1199.0.0.0, Linux0.0.0]"/>'
                '</testsuite>'
            )
            with self.assertRaisesRegex(ValueError, "wrong runtime"):
                verify_reports(
                    Path(directory),
                    {("sample.FirstTest", "identity")},
                    "jsBrowserTest",
                    "ChromeHeadless119",
                )

    def test_browser_launcher_binds_the_process_image(self):
        from runner import verify_browser_launches

        selected = Path(shutil.which("sleep"))
        launcher = Path(__file__).with_name("browser_launcher.py")
        with tempfile.TemporaryDirectory() as directory:
            attestation = Path(directory) / "launch.jsonl"
            token = "test-browser-launch"
            env = dict(os.environ, DYN4K_BROWSER_SELECTED_BINARY=str(selected),
                       DYN4K_BROWSER_ATTESTATION=str(attestation), DYN4K_BROWSER_TOKEN=token,
                       DYN4K_BROWSER_RUNTIME="chromium")
            launched = subprocess.run(
                [sys.executable, str(launcher), "0.2"], env=env,
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(0, launched.returncode, launched.stderr)
            records = verify_browser_launches(attestation, selected, token, "chromium")
            self.assertEqual(selected.resolve(), Path(records[0]["process_executable"]))

            forged = json.loads(attestation.read_text())
            forged["process_sha256"] = "0" * 64
            attestation.write_text(json.dumps(forged) + "\n")
            with self.assertRaisesRegex(ValueError, "process image"):
                verify_browser_launches(attestation, selected, token, "chromium")

    def test_staged_physics_contract_rejects_noop_and_missing_assertions(self):
        from runner import verify_consumer_physics_contract

        source = (Path(__file__).resolve().parents[3] / "consumers/qualification/browser-wasi"
                  / "src/commonTest/kotlin/qualification/StagedWorldTest.kt")
        original = source.read_text()
        verify_consumer_physics_contract(source)
        mutations = (
            "package qualification\nclass StagedWorldTest {\n"
            "  @Test fun stagedModulesShareBodiesAndDeliverCollisionCallbacks() {}\n}\n",
            original.replace("assertSame(moving, same)", "Unit"),
            original.replace("world.step(1)", "Unit"),
            original.replace("collisions++", "Unit"),
            original.replace("assertTrue(contact != null)", "Unit"),
            original.replace("assertTrue(began > 0", "assertTrue(began >= 0"),
        )
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "StagedWorldTest.kt"
            for mutated in mutations:
                self.assertNotEqual(original, mutated)
                candidate.write_text(mutated)
                with self.assertRaisesRegex(ValueError, "physics contract"):
                    verify_consumer_physics_contract(candidate)

    def test_lane_receipt_rejects_changed_console_and_executable_bytes(self):
        from runner import audit_lane_receipt

        with tempfile.TemporaryDirectory() as directory:
            lane_dir = Path(directory)
            module_dir = lane_dir / "dyn4k-core"
            module_dir.mkdir()
            files = {
                "gradle_console": module_dir / "gradle-console.log",
                "raw_console": module_dir / "wasmtime-console.log",
                "linked_executable": module_dir / "linked-executable.wasm",
            }
            for label, path in files.items():
                path.write_bytes(label.encode())
            module = {"status": "PASSED"}
            for label, path in files.items():
                module[label] = str(path)
                module["linked_sha256" if label == "linked_executable" else label + "_sha256"] = (
                    hashlib.sha256(path.read_bytes()).hexdigest()
                )
            receipt = lane_dir / "lane.json"
            receipt.write_text(json.dumps({"status": "FAILED", "target": "wasmWasi",
                                           "modules": {"dyn4k-core": module}}))
            audit_lane_receipt(receipt)
            for path in files.values():
                original = path.read_bytes()
                path.write_bytes(original + b"tampered")
                with self.assertRaisesRegex(ValueError, "digest"):
                    audit_lane_receipt(receipt)
                path.write_bytes(original)

            del module["raw_console_sha256"]
            receipt.write_text(json.dumps({"status": "FAILED", "target": "wasmWasi",
                                           "modules": {"dyn4k-core": module}}))
            with self.assertRaisesRegex(ValueError, "digest"):
                audit_lane_receipt(receipt)

    def test_existing_failed_lane_is_not_overwritten(self):
        from runner import run_lane

        with tempfile.TemporaryDirectory() as directory:
            lane_dir = Path(directory) / "failed-lane"
            lane_dir.mkdir()
            receipt = lane_dir / "lane.json"
            receipt.write_text('{"status":"FAILED","reason":"world unavailable"}\n')
            before = receipt.read_bytes()
            self.assertEqual(1, run_lane(Path(directory), "wrong-sha", receipt, lane_dir,
                                         "js", "chromium", "minimum", "development",
                                         Path(directory) / "missing-chrome", "119.0.6045.105"))
            self.assertEqual(before, receipt.read_bytes())

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
