import os
import json
import hashlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from runner import (gradle_test_task, runtime_version, source_cases, staged_files,
                    verify_reports, verify_wasmtime_output)


class SourceCasesTest(unittest.TestCase):
    @staticmethod
    def copy_lane(source: Path, directory: str) -> tuple[dict, Path]:
        copied = Path(directory) / source.name
        shutil.copytree(source, copied)

        def replace_paths(value):
            if isinstance(value, str):
                return value.replace(str(source), str(copied))
            if isinstance(value, list):
                return [replace_paths(item) for item in value]
            if isinstance(value, dict):
                return {key: replace_paths(item) for key, item in value.items()}
            return value

        return replace_paths(json.loads((copied / "lane.json").read_text())), copied

    @staticmethod
    def save_copied_lane(lane: dict, copied: Path) -> None:
        from runner import sealed_lane, sha256, write_json

        for module in lane["modules"].values():
            result = Path(module["result_json"])
            write_json(result, {key: value for key, value in module.items()
                                if key not in ("result_json", "result_json_sha256")})
            module["result_json_sha256"] = sha256(result)
        write_json(copied / "lane.json", sealed_lane(lane))

    def test_committed_common_corpus_has_all_browser_and_wasi_cases(self):
        from runner import common_corpus_cases

        root = Path(__file__).resolve().parents[3]
        candidate = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        core = common_corpus_cases(root, candidate, "dyn4k-core")
        facade = common_corpus_cases(root, candidate, "dyn4k")
        self.assertEqual(2454, len(core))
        self.assertEqual(58, len(facade))
        self.assertIn(("org.dyn4j.coverage.world.core.PhysicsWorldCoreCoverageTest",
                       "addBody"), core)

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

    def test_browser_process_keeps_karmas_launcher_pid(self):
        selected = Path(shutil.which("sleep"))
        launcher = Path(__file__).with_name("browser_launcher.py")
        with tempfile.TemporaryDirectory() as directory:
            attestation = Path(directory) / "launch.jsonl"
            env = dict(os.environ, DYN4K_BROWSER_SELECTED_BINARY=str(selected),
                       DYN4K_BROWSER_ATTESTATION=str(attestation),
                       DYN4K_BROWSER_TOKEN="test-process-lifecycle",
                       DYN4K_BROWSER_RUNTIME="chromium")
            launched = subprocess.Popen([sys.executable, str(launcher), "10"], env=env,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            recorded_pid = None
            try:
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and not attestation.is_file():
                    time.sleep(0.01)
                self.assertTrue(attestation.is_file(), "browser launch was not attested")
                recorded_pid = json.loads(attestation.read_text())["pid"]
                self.assertEqual(launched.pid, recorded_pid)
            finally:
                launched.terminate()
                launched.wait(timeout=3)
                launched.stderr.close()
                if recorded_pid is not None and recorded_pid != launched.pid:
                    os.kill(recorded_pid, 15)

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

    def test_audit_rejects_forged_passing_wasmtime_receipt(self):
        from runner import audit_lane_receipt

        with tempfile.TemporaryDirectory() as directory:
            lane_dir = Path(directory)
            modules = {}
            for name in ("dyn4k-core", "dyn4k", "consumer"):
                folder = lane_dir / name
                folder.mkdir()
                evidence = {"status": "PASSED", "expected": 2454 if name == "dyn4k-core"
                            else 58 if name == "dyn4k" else 1,
                            "executed": 2454 if name == "dyn4k-core"
                            else 58 if name == "dyn4k" else 1,
                            "failures": 0, "skipped": 0}
                for field, filename in (("gradle_console", "gradle-console.log"),
                                        ("raw_console", "wasmtime-console.log"),
                                        ("linked_executable", "linked-executable.wasm")):
                    path = folder / filename
                    path.write_text("BUILD SUCCESSFUL\n" if field == "gradle_console"
                                    else "fake PASS\n")
                    evidence[field] = str(path)
                    digest_field = "linked_sha256" if field == "linked_executable" else field + "_sha256"
                    evidence[digest_field] = hashlib.sha256(path.read_bytes()).hexdigest()
                result = folder / "result.json"
                result.write_text(json.dumps(evidence))
                evidence["result_json"] = str(result)
                evidence["result_json_sha256"] = hashlib.sha256(result.read_bytes()).hexdigest()
                modules[name] = evidence
            receipt = lane_dir / "lane.json"
            receipt.write_text(json.dumps({"status": "PASSED", "target": "wasmWasi",
                                           "modules": modules}))
            with self.assertRaises(ValueError):
                audit_lane_receipt(receipt)

    def test_audit_rejects_tampered_receipt_seal(self):
        from runner import audit_lane_receipt, sealed_lane

        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "lane.json"
            lane = sealed_lane({"status": "FAILED", "target": "wasmWasi", "modules": {},
                                "reason": "runtime failed"})
            receipt.write_text(json.dumps(lane))
            audit_lane_receipt(receipt)
            lane["reason"] = "claimed success"
            receipt.write_text(json.dumps(lane))
            with self.assertRaisesRegex(ValueError, "seal"):
                audit_lane_receipt(receipt)

    def test_resealed_browser_configuration_relabel_is_rejected(self):
        from runner import audit_lane_receipt

        evidence_root = os.environ.get("DYN4K_BROWSER_WASI_REVIEW_EVIDENCE")
        if evidence_root is None:
            self.skipTest("set DYN4K_BROWSER_WASI_REVIEW_EVIDENCE to a full 20-lane archive")
        for target, runtime in (("js", "chromium"), ("wasmJs", "firefox")):
            for original, claimed in (("development", "production"),
                                      ("production", "development")):
                source = Path(evidence_root) / f"{target}-{runtime}-minimum-{original}"
                self.assertTrue((source / "lane.json").is_file(), source)
                with tempfile.TemporaryDirectory() as directory:
                    lane, copied = self.copy_lane(source, directory)
                    lane["configuration"] = claimed
                    for module in lane["modules"].values():
                        module["configuration"] = claimed
                    self.save_copied_lane(lane, copied)
                    with self.subTest(target=target, original=original, claimed=claimed):
                        with self.assertRaisesRegex(ValueError, "configuration|production|development"):
                            with mock.patch("runner.candidate_identity"):
                                audit_lane_receipt(copied / "lane.json")

    def test_resealed_browser_output_binding_mutations_are_rejected(self):
        from runner import audit_lane_receipt, sha256

        evidence_root = os.environ.get("DYN4K_BROWSER_WASI_REVIEW_EVIDENCE")
        if evidence_root is None:
            self.skipTest("set DYN4K_BROWSER_WASI_REVIEW_EVIDENCE to a full 20-lane archive")
        for original, mutation, expected_error in (
            ("production", "missing_production_flag", "Gradle configuration"),
            ("production", "missing_production_marker", "browser configuration input"),
            ("production", "development_linked_source", "linked source configuration"),
            ("production", "wrong_linked_digest", "linked source digest"),
            ("production", "wrong_browser_task", "Gradle configuration"),
            ("development", "added_production_flag", "Gradle configuration"),
        ):
            source = Path(evidence_root) / f"js-chromium-minimum-{original}"
            self.assertTrue((source / "lane.json").is_file(), source)
            with tempfile.TemporaryDirectory() as directory:
                lane, copied = self.copy_lane(source, directory)
                module = lane["modules"]["dyn4k-core"]
                if mutation == "missing_production_flag":
                    module["gradle_command"].remove("-PqualificationProduction=true")
                elif mutation == "missing_production_marker":
                    stdout = Path(module["gradle_stdout"])
                    stdout.write_text("".join(line for line in stdout.read_text().splitlines(True)
                                              if not line.startswith("qualification test input:")))
                    console = Path(module["gradle_console"])
                    console.write_text(stdout.read_text() + Path(module["gradle_stderr"]).read_text())
                    module["gradle_stdout_sha256"] = sha256(stdout)
                    module["gradle_console_sha256"] = sha256(console)
                elif mutation == "development_linked_source":
                    module["linked_source"] = module["linked_source"].replace(
                        "testProductionExecutable", "testDevelopmentExecutable")
                elif mutation == "wrong_linked_digest":
                    module["linked_source_sha256"] = "0" * 64
                elif mutation == "wrong_browser_task":
                    module["gradle_command"][2] = ":dyn4k-core:wasmJsBrowserTest"
                else:
                    module["gradle_command"].append("-PqualificationProduction=true")
                self.save_copied_lane(lane, copied)
                with self.subTest(mutation=mutation):
                    with self.assertRaisesRegex(ValueError, expected_error):
                        with mock.patch("runner.candidate_identity"):
                            audit_lane_receipt(copied / "lane.json")

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
