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
    REVIEWED_SUCCESSOR = "8b0071563a31f7866f9fe8c3549ed284c9e7a092"

    @staticmethod
    def public_candidate(root: Path, sha: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(Path(__file__).with_name("runner.py")), "candidate",
             "--root", str(root), "--candidate-sha", sha],
            capture_output=True, text=True, check=False,
        )

    def test_public_candidate_accepts_exact_reviewed_source_and_rejects_mutants(self):
        source_root = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "reviewed-candidate"
            subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout",
                            str(source_root), str(checkout)], check=True)
            subprocess.run(["git", "-C", str(checkout), "checkout", "--quiet",
                            "--detach", self.REVIEWED_SUCCESSOR], check=True)
            exact = self.public_candidate(checkout, self.REVIEWED_SUCCESSOR)
            self.assertEqual(0, exact.returncode, exact.stderr)
            verified = json.loads(exact.stdout)
            self.assertEqual("VERIFIED", verified["status"])
            self.assertEqual(self.REVIEWED_SUCCESSOR, verified["candidate_sha"])
            self.assertEqual(2521, verified["suite_methods"])

            generated = checkout / "consumers/qualification/browser-wasi/build/generated.txt"
            generated.parent.mkdir(parents=True)
            generated.write_text("generated output")
            with_output = self.public_candidate(checkout, self.REVIEWED_SUCCESSOR)
            self.assertEqual(0, with_output.returncode, with_output.stderr)

            stale = self.public_candidate(checkout, "0" * 40)
            self.assertEqual(1, stale.returncode)
            self.assertIn("source SHA differs", stale.stderr)

            production = next((checkout / "dyn4k-core/src/commonMain/kotlin").rglob("*.kt"))
            production.write_bytes(production.read_bytes() + b"\n// source mutation\n")
            changed = self.public_candidate(checkout, self.REVIEWED_SUCCESSOR)
            self.assertEqual(1, changed.returncode)
            self.assertIn("dirty", changed.stderr)
            subprocess.run(["git", "-C", str(checkout), "update-index",
                            "--assume-unchanged", str(production)], check=True)
            hidden_change = self.public_candidate(checkout, self.REVIEWED_SUCCESSOR)
            self.assertEqual(1, hidden_change.returncode, hidden_change.stderr)
            self.assertIn("committed source bytes differ", hidden_change.stderr)
            subprocess.run(["git", "-C", str(checkout), "update-index",
                            "--no-assume-unchanged", str(production)], check=True)
            subprocess.run(["git", "-C", str(checkout), "restore", str(production)],
                           check=True)

            ignored = production.parent / "UntrackedCandidateInput.kt"
            ignored.write_text("package ignored\nclass UntrackedCandidateInput\n")
            (checkout / ".git/info/exclude").write_text(
                "/dyn4k-core/src/commonMain/kotlin/**/UntrackedCandidateInput.kt\n")
            untracked = self.public_candidate(checkout, self.REVIEWED_SUCCESSOR)
            self.assertEqual(1, untracked.returncode)
            self.assertIn("untracked candidate input", untracked.stderr)
            ignored.unlink()

            old = subprocess.check_output(
                ["git", "-C", str(checkout), "show",
                 "5f02826703f799fee0bd185b335e5cba36a08900:tools/qualification/full-common-corpus.json"])
            old_manifest = json.loads(old)
            current_manifest = json.loads(
                (checkout / "tools/qualification/full-common-corpus.json").read_text())
            old_manifest["source_tree_sha256"] = current_manifest["source_tree_sha256"]
            old_manifest["counts"]["total_methods"] = current_manifest["counts"]["total_methods"]
            (checkout / "tools/qualification/full-common-corpus.json").write_text(
                json.dumps(old_manifest, sort_keys=True))
            old_corpus = self.public_candidate(checkout, self.REVIEWED_SUCCESSOR)
            self.assertEqual(1, old_corpus.returncode)
            self.assertTrue(
                "dirty" in old_corpus.stderr or "corpus" in old_corpus.stderr,
                old_corpus.stderr,
            )

            from runner import candidate_identity

            with mock.patch("runner.full_corpus.candidate_checkout_problems", return_value=[]):
                with self.assertRaisesRegex(ValueError, "candidate commit bytes differ"):
                    candidate_identity(checkout, self.REVIEWED_SUCCESSOR)
                with mock.patch("runner.full_corpus.committed_bytes",
                                side_effect=lambda root, sha, path: (root / path).read_bytes()):
                    with self.assertRaisesRegex(ValueError, "corpus differs from source tree"):
                        candidate_identity(checkout, self.REVIEWED_SUCCESSOR)

            subprocess.run(["git", "-C", str(checkout), "restore",
                            "tools/qualification/full-common-corpus.json"], check=True)
            consumer_build = checkout / "consumers/qualification/browser-wasi/build.gradle.kts"
            consumer_build.write_bytes(consumer_build.read_bytes().replace(
                b"io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1",
                b"io.github.rubixhacker:dyn4k-core:0.1.0-alpha.0"))
            with mock.patch("runner.full_corpus.candidate_checkout_problems", return_value=[]):
                with self.assertRaisesRegex(ValueError, "consumer dependency pins differ"):
                    candidate_identity(checkout, self.REVIEWED_SUCCESSOR)

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

    @staticmethod
    def public_historical_audit(
        receipt: Path, audit_view: Path, extra_mounts: tuple[str, ...] = ()
    ) -> subprocess.CompletedProcess[str]:
        root = Path(json.loads(receipt.read_text())["candidate_root"])
        auditor_root = Path(__file__).resolve().parents[3]
        replay = Path(os.environ["DYN4K_BROWSER_WASI_REPLAY_ROOT"])
        audit_view.mkdir()
        mounts = ["--ro-bind", "/", "/", "--bind", "/tmp", "/tmp",
                  "--dev-bind", "/dev", "/dev", "--proc", "/proc",
                  "--ro-bind", str(auditor_root), str(audit_view),
                  "--bind", str(replay), str(root)]
        for suffix in ("build", "dyn4k-core/build", "dyn4k/build",
                       "consumers/qualification/browser-wasi/build"):
            mounts.extend(("--bind", str(root / suffix), str(root / suffix)))
        mounts.extend(extra_mounts)
        return subprocess.run(
            ["bwrap", *mounts, "--", "env", "PYTHONDONTWRITEBYTECODE=1", "python3",
             str(audit_view / "tools/qualification/browser_wasi/runner.py"),
             "audit", "--receipt", str(receipt)],
            capture_output=True, text=True, check=False,
        )

    def assert_resealed_public_config_mutation_rejected(
        self, mutation: str, lane_name: str = "js-chromium-minimum-production"
    ) -> None:
        from runner import sha256

        evidence_root = os.environ.get("DYN4K_BROWSER_WASI_REVIEW_EVIDENCE")
        replay_root = os.environ.get("DYN4K_BROWSER_WASI_REPLAY_ROOT")
        if not evidence_root or not replay_root:
            self.skipTest("set review evidence and replay root for public historical audit")
        source = Path(evidence_root) / lane_name
        self.assertTrue((source / "lane.json").is_file(), source)
        with tempfile.TemporaryDirectory() as directory:
            lane, copied = self.copy_lane(source, directory)
            receipt = copied / "lane.json"
            self.save_copied_lane(lane, copied)
            baseline = self.public_historical_audit(receipt, Path(directory) / "baseline-auditor")
            self.assertEqual(0, baseline.returncode, baseline.stderr)

            module = lane["modules"]["dyn4k-core"]
            config = Path(module["karma_config"])
            content = config.read_text()
            if mutation in ("json_exclude_input", "json_custom_launcher", "json_disable_set"):
                before, separator, after = content.partition("});")
                self.assertEqual("});", separator)
                start = before.index("config.set({") + len("config.set(")
                settings = json.loads(before[start:] + "}")
                if mutation == "json_exclude_input":
                    settings["exclude"] = [settings["files"][1]]
                elif mutation == "json_custom_launcher":
                    settings["customLaunchers"] = {
                        "ChromeHeadless": {"base": "FirefoxHeadless"}}
                else:
                    settings["set"] = None
                config.write_text(before[:start] + json.dumps(settings, indent=2) + ");" + after)
            else:
                port_setter = f"config.set({{port: {module['karma_port']}}});"
                self.assertEqual(1, content.count(port_setter))
                if mutation == "unreachable_port_setter":
                    replacement = "return;\n" + port_setter
                elif mutation == "later_browser_override":
                    replacement = 'config.set({browsers: ["FirefoxHeadless"]});\n' + port_setter
                elif mutation == "later_js_input_override":
                    wrong = module["linked_source"].replace(
                        "testProductionExecutable", "testDevelopmentExecutable")
                    self.assertNotEqual(wrong, module["linked_source"])
                    replacement = ('config.set({files: ["/tmp/runner.js", ' + json.dumps(wrong) +
                                   '], preprocessors: {' + json.dumps(wrong) +
                                   ': ["webpack", "sourcemap"]}});\n' + port_setter)
                else:
                    self.fail(f"unknown Karma mutation: {mutation}")
                config.write_text(content.replace(port_setter, replacement))
            module["karma_config_sha256"] = sha256(config)
            self.save_copied_lane(lane, copied)
            rejected = self.public_historical_audit(receipt, Path(directory) / "mutant-auditor")
            self.assertEqual(1, rejected.returncode, rejected.stderr)
            self.assertIn("Karma", rejected.stderr)

    def test_public_audit_rejects_unreachable_port_setter(self):
        self.assert_resealed_public_config_mutation_rejected("unreachable_port_setter")

    def test_public_audit_rejects_later_browser_override(self):
        self.assert_resealed_public_config_mutation_rejected("later_browser_override")

    def test_public_audit_rejects_later_js_input_override(self):
        self.assert_resealed_public_config_mutation_rejected("later_js_input_override")

    def test_public_audit_rejects_json_excluded_js_input(self):
        self.assert_resealed_public_config_mutation_rejected("json_exclude_input")

    def test_public_audit_rejects_json_excluded_wasm_input(self):
        self.assert_resealed_public_config_mutation_rejected(
            "json_exclude_input", "wasmJs-firefox-minimum-production")

    def test_public_audit_rejects_json_custom_launcher(self):
        self.assert_resealed_public_config_mutation_rejected("json_custom_launcher")

    def test_public_audit_rejects_json_disabled_port_setter(self):
        self.assert_resealed_public_config_mutation_rejected("json_disable_set")

    def test_public_audit_rejects_changed_karma_helper_bytes(self):
        evidence_root = os.environ.get("DYN4K_BROWSER_WASI_REVIEW_EVIDENCE")
        replay_root = os.environ.get("DYN4K_BROWSER_WASI_REPLAY_ROOT")
        if not evidence_root or not replay_root:
            self.skipTest("set review evidence and replay root for public historical audit")
        source = Path(evidence_root) / "wasmJs-firefox-minimum-production"
        with tempfile.TemporaryDirectory() as directory:
            lane, copied = self.copy_lane(source, directory)
            receipt = copied / "lane.json"
            self.save_copied_lane(lane, copied)
            baseline = self.public_historical_audit(receipt, Path(directory) / "baseline-auditor")
            self.assertEqual(0, baseline.returncode, baseline.stderr)
            config = Path(lane["modules"]["dyn4k-core"]["karma_config"]).read_text()
            before = config.partition("});")[0]
            settings = json.loads(before[before.index("config.set({") + len("config.set("):] + "}")
            runner_input = Path(settings["files"][0])
            changed = Path(directory) / "changed-karma-runner.js"
            changed.write_bytes(runner_input.read_bytes() + b"\n")
            rejected = self.public_historical_audit(
                receipt, Path(directory) / "mutant-auditor",
                ("--bind", str(changed), str(runner_input)))
            self.assertEqual(1, rejected.returncode, rejected.stderr)
            self.assertIn("Karma", rejected.stderr)

    def test_committed_common_corpus_has_all_browser_and_wasi_cases(self):
        from runner import common_corpus_cases

        root = Path(__file__).resolve().parents[3]
        candidate = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        core = common_corpus_cases(root, candidate, "dyn4k-core")
        facade = common_corpus_cases(root, candidate, "dyn4k")
        self.assertEqual(2460, len(core))
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
                evidence = {"status": "PASSED", "expected": 2460 if name == "dyn4k-core"
                            else 58 if name == "dyn4k" else 1,
                            "executed": 2460 if name == "dyn4k-core"
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

    def test_resealed_relabel_with_forged_command_and_output_is_rejected(self):
        from runner import (audit_lane_receipt, gradle_command, linked_file, sha256,
                            test_project)

        evidence_root = os.environ.get("DYN4K_BROWSER_WASI_REVIEW_EVIDENCE")
        if evidence_root is None:
            self.skipTest("set DYN4K_BROWSER_WASI_REVIEW_EVIDENCE to a full 20-lane archive")
        for original, claimed in (("development", "production"),
                                  ("production", "development")):
            source = Path(evidence_root) / f"js-chromium-minimum-{original}"
            self.assertTrue((source / "lane.json").is_file(), source)
            with tempfile.TemporaryDirectory() as directory:
                lane, copied = self.copy_lane(source, directory)
                lane["configuration"] = claimed
                root = Path(lane["candidate_root"])
                for name, module in lane["modules"].items():
                    module["configuration"] = claimed
                    module["gradle_command"] = gradle_command(root, name, "js", claimed)
                    linked = linked_file(test_project(root, name), "js", claimed, name)
                    module["linked_source"] = str(linked)
                    stdout = Path(module["gradle_stdout"])
                    output = "".join(line for line in stdout.read_text().splitlines(True)
                                     if not line.startswith("qualification test input:"))
                    if claimed == "production":
                        output += f"qualification test input: {linked}\n"
                    stdout.write_text(output)
                    console = Path(module["gradle_console"])
                    console.write_text(output + Path(module["gradle_stderr"]).read_text())
                    module["gradle_stdout_sha256"] = sha256(stdout)
                    module["gradle_console_sha256"] = sha256(console)
                self.save_copied_lane(lane, copied)
                with self.subTest(original=original, claimed=claimed):
                    with self.assertRaisesRegex(ValueError, "linked source digest"):
                        with mock.patch("runner.candidate_identity"):
                            audit_lane_receipt(copied / "lane.json")

    def test_resealed_browser_omitted_karma_evidence_is_rejected(self):
        from runner import audit_lane_receipt

        evidence_root = os.environ.get("DYN4K_BROWSER_WASI_REVIEW_EVIDENCE")
        if evidence_root is None:
            self.skipTest("set DYN4K_BROWSER_WASI_REVIEW_EVIDENCE to a full 20-lane archive")
        source = Path(evidence_root) / "js-chromium-minimum-development"
        self.assertTrue((source / "lane.json").is_file(), source)
        for omitted in (("karma_port",), ("karma_config",),
                        ("karma_config_sha256",),
                        ("karma_port", "karma_config", "karma_config_sha256")):
            with tempfile.TemporaryDirectory() as directory:
                lane, copied = self.copy_lane(source, directory)
                for module in lane["modules"].values():
                    for field in omitted:
                        module.pop(field)
                self.save_copied_lane(lane, copied)
                with self.subTest(omitted=omitted):
                    with self.assertRaises(ValueError):
                        with mock.patch("runner.candidate_identity"):
                            audit_lane_receipt(copied / "lane.json")

    def test_resealed_browser_mismatched_karma_config_is_rejected(self):
        from runner import audit_lane_receipt, sha256

        evidence_root = os.environ.get("DYN4K_BROWSER_WASI_REVIEW_EVIDENCE")
        if evidence_root is None:
            self.skipTest("set DYN4K_BROWSER_WASI_REVIEW_EVIDENCE to a full 20-lane archive")
        for lane_name, mutation in (
            ("js-chromium-minimum-production", "wrong_receipt_port"),
            ("js-chromium-minimum-production", "wrong_active_port"),
            ("js-chromium-minimum-development", "wrong_browser"),
            ("js-chromium-minimum-production", "wrong_js_input"),
            ("wasmJs-firefox-minimum-production", "wrong_wasm_loader"),
            ("js-chromium-minimum-production", "spoofed_config_comment"),
        ):
            source = Path(evidence_root) / lane_name
            self.assertTrue((source / "lane.json").is_file(), source)
            with tempfile.TemporaryDirectory() as directory:
                lane, copied = self.copy_lane(source, directory)
                module = lane["modules"]["dyn4k-core"]
                config = Path(module["karma_config"])
                content = config.read_text()
                if mutation == "wrong_receipt_port":
                    module["karma_port"] += 1
                elif mutation == "wrong_active_port":
                    port = module["karma_port"]
                    original = f"config.set({{port: {port}}});"
                    self.assertIn(original, content)
                    content = content.replace(
                        original,
                        f"config.set({{port: {port + 1}}});\n// {original}",
                    )
                elif mutation == "wrong_browser":
                    self.assertIn('"ChromeHeadless"', content)
                    content = content.replace('"ChromeHeadless"', '"FirefoxHeadless"')
                elif mutation == "wrong_js_input":
                    production = module["linked_source"]
                    self.assertIn(production, content)
                    content = content.replace(
                        production,
                        production.replace("testProductionExecutable", "testDevelopmentExecutable"),
                    )
                elif mutation == "spoofed_config_comment":
                    first_block = content.partition("config.set({")[2].partition("});")[0]
                    content = ("/* config.set({" + first_block + "}); */\n" +
                               content.replace('"ChromeHeadless"', '"FirefoxHeadless"'))
                else:
                    self.assertIn("static/load.mjs", content)
                    content = content.replace("static/load.mjs", "static/other.mjs")
                if mutation != "wrong_receipt_port":
                    config.write_text(content)
                    module["karma_config_sha256"] = sha256(config)
                self.save_copied_lane(lane, copied)
                with self.subTest(lane=lane_name, mutation=mutation):
                    with self.assertRaisesRegex(ValueError, "Karma"):
                        with mock.patch("runner.candidate_identity"):
                            audit_lane_receipt(copied / "lane.json")

    def test_browser_port_configuration_is_isolated_and_removed(self):
        from runner import isolated_karma_port

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with isolated_karma_port(root) as port:
                source = root / "karma.config.d/qualification-port.js"
                self.assertIn(f"port: {port}", source.read_text())
                self.assertGreater(port, 0)
            self.assertFalse((root / "karma.config.d").exists())

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
