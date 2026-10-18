import json
import hashlib
import io
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import safari_yarn_lock


LOCK_FAILURE = ("FAILURE: Build failed with an exception.\n\n"
                "* What went wrong:\n"
                "Execution failed for task ':kotlinStoreYarnLock' "
                "(registered by plugin class 'org.jetbrains.kotlin.gradle.targets.js.yarn.YarnPlugin').\n"
                "> Lock file was changed. Run the `kotlinUpgradeYarnLock` task "
                "to actualize lock file\n\n"
                "* Try:\n"
                "> Run with --stacktrace option to get the stack trace.\n"
                "> Run with --info or --debug option to get more log output.\n\n"
                "BUILD FAILED in 21s\n")


class SafariYarnLockTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = self.root / "source"
        self.repository.mkdir()
        (self.repository / "kotlin-js-store").mkdir()
        (self.repository / "kotlin-js-store/yarn.lock").write_bytes(b"tracked lock\n")
        (self.repository / "gradlew").write_text("#!/bin/sh\n")
        (self.repository / ".gitignore").write_text("build/\n")
        (self.repository / "build.gradle.kts").write_text("plugins {}\n")
        (self.repository / "settings.gradle.kts").write_text('rootProject.name = "dyn4k"\n')
        (self.repository / "gradle/wrapper").mkdir(parents=True)
        (self.repository / "gradle/wrapper/gradle-wrapper.properties").write_text(
            "distributionUrl=gradle-9.5-bin.zip\n")
        (self.repository / "tools/qualification").mkdir(parents=True)
        (self.repository / "tools/qualification/full_hosted.py").write_text("# hosted source\n")
        for module in ("dyn4k-core", "dyn4k"):
            (self.repository / module).mkdir()
            (self.repository / module / "build.gradle.kts").write_text("plugins {}\n")
        subprocess.run(["git", "init", "-q", str(self.repository)], check=True)
        subprocess.run(["git", "-C", str(self.repository), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repository), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"],
                       check=True)
        self.candidate = subprocess.check_output(
            ["git", "-C", str(self.repository), "rev-parse", "HEAD"], text=True).strip()
        self.output = self.root / "capture"

    def generated(self, data=b"host generated lock\n", safari=False):
        path = self.repository / "build/js/yarn.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        package = path.parent / "package.json"
        names = ("dyn4k-dyn4k-core", "dyn4k-dyn4k-core-test",
                 "dyn4k-dyn4k", "dyn4k-dyn4k-test")
        package.write_text(json.dumps({"name": "dyn4k", "workspaces":
                                       [f"packages/{name}" for name in names]}) + "\n")
        for name in names:
            module = path.parent / "packages" / name / "package.json"
            module.parent.mkdir(parents=True)
            value = {"name": name}
            if safari and name.endswith("-test"):
                value["devDependencies"] = {"karma-safari-launcher": "1.0.0"}
            module.write_text(json.dumps(value) + "\n")

    def write_logs(self, output=None, stderr=LOCK_FAILURE):
        folder = output or self.output
        folder.mkdir(exist_ok=True)
        (folder / "stdout.txt").write_text(
            "> Task :dyn4k-core:jsTestPackageJson\n"
            "> Task :dyn4k:jsTestPackageJson\n"
            "> Task :kotlinNpmInstall\n"
            "> Task :kotlinStoreYarnLock FAILED\n")
        (folder / "stderr.txt").write_text(stderr)

    def hosted_capture(self):
        def failure(repository, output, command):
            self.generated(safari=True)
            self.write_logs()
            return {"command": command, "pid": 123, "exit_code": 1,
                    "started_ns": 1, "finished_ns": 2,
                    "stdout_bytes_seen": (output / "stdout.txt").stat().st_size,
                    "stderr_bytes_seen": (output / "stderr.txt").stat().st_size,
                    "stdout_truncated": False, "stderr_truncated": False,
                    "timed_out": False, "stream_incomplete": False}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=failure):
            return safari_yarn_lock.capture(self.repository, self.candidate,
                                            self.output, "development")

    def test_failed_lock_task_captures_exact_different_bytes_and_inputs(self):
        def failure(*args):
            self.generated()
            self.write_logs()
            return {"command": ["./gradlew", "--no-daemon", "--console=plain",
                                "--rerun-tasks", ":kotlinStoreYarnLock"],
                    "pid": 123, "exit_code": 1, "started_ns": 1,
                    "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=failure):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate, self.output)
        self.assertEqual("LOCK_MISMATCH_CAPTURED", receipt["status"])
        self.assertEqual(b"tracked lock\n", (self.output / "tracked/kotlin-js-store/yarn.lock").read_bytes())
        self.assertEqual(b"host generated lock\n",
                         (self.output / "generated/build/js/yarn.lock").read_bytes())
        self.assertEqual('{"name": "dyn4k-dyn4k-core-test"}\n',
                         (self.output / "generated/build/js/packages/dyn4k-dyn4k-core-test/package.json").read_text())
        self.assertNotEqual(receipt["tracked_sha256"], receipt["generated_sha256"])
        for item in receipt["files"]:
            if "source_path" in item:
                self.assertEqual(item["source_path"], item["source_realpath"])
        self.assertEqual(self.candidate, json.loads((self.output / "receipt.json").read_text())
                         ["candidate_sha"])

    def test_other_gradle_failure_cannot_be_called_a_lock_mismatch(self):
        def failure(*args):
            self.generated()
            self.write_logs(stderr="Task failed for another reason\n")
            return {"command": ["./gradlew", ":kotlinStoreYarnLock"],
                    "pid": 123, "exit_code": 1, "started_ns": 1,
                    "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=failure):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate, self.output)
        self.assertEqual("OTHER_GRADLE_RESULT", receipt["status"])

    def test_clean_checkout_swap_during_task_rejects_original_candidate(self):
        (self.repository / "build.gradle.kts").write_text("plugins { swapped }\n")
        subprocess.run(["git", "-C", str(self.repository), "add", "build.gradle.kts"],
                       check=True)
        subprocess.run(["git", "-C", str(self.repository), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit", "-qm", "swapped"],
                       check=True)
        swapped = subprocess.check_output(
            ["git", "-C", str(self.repository), "rev-parse", "HEAD"], text=True).strip()
        subprocess.run(["git", "-C", str(self.repository), "checkout", "-q",
                        self.candidate], check=True)

        def failure(*args):
            self.generated()
            self.write_logs()
            subprocess.run(["git", "-C", str(self.repository), "checkout", "-q", swapped],
                           check=True)
            return {"command": ["./gradlew", ":kotlinStoreYarnLock"], "pid": 123,
                    "exit_code": 1, "started_ns": 1, "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=failure):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate, self.output)
        self.assertEqual("SOURCE_CHANGED", receipt["status"])
        self.assertEqual(swapped, receipt["head_after"])
        self.assertFalse(receipt["qualified"])

    def test_clean_checkout_swap_during_capture_rejects_original_candidate(self):
        (self.repository / "new-source.kt").write_text("fun changed() = true\n")
        subprocess.run(["git", "-C", str(self.repository), "add", "new-source.kt"],
                       check=True)
        subprocess.run(["git", "-C", str(self.repository), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit", "-qm", "source"],
                       check=True)
        swapped = subprocess.check_output(
            ["git", "-C", str(self.repository), "rev-parse", "HEAD"], text=True).strip()
        subprocess.run(["git", "-C", str(self.repository), "checkout", "-q",
                        self.candidate], check=True)

        def failure(*args):
            self.generated()
            self.write_logs()
            return {"command": ["./gradlew", ":kotlinStoreYarnLock"], "pid": 123,
                    "exit_code": 1, "started_ns": 1, "finished_ns": 2}

        original = safari_yarn_lock.capture_package_graph

        def switched(*args):
            original(*args)
            subprocess.run(["git", "-C", str(self.repository), "checkout", "-q", swapped],
                           check=True)

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=failure), \
                mock.patch.object(safari_yarn_lock, "capture_package_graph", side_effect=switched):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate, self.output)
        self.assertEqual("SOURCE_CHANGED", receipt["status"])
        self.assertEqual(swapped, receipt["head_after"])

    def test_generated_lock_change_during_capture_rejects_stale_copy(self):
        def failure(*args):
            self.generated()
            self.write_logs()
            return {"command": ["./gradlew", ":kotlinStoreYarnLock"], "pid": 123,
                    "exit_code": 1, "started_ns": 1, "finished_ns": 2}

        original = safari_yarn_lock.capture_package_graph

        def changed(*args):
            original(*args)
            (self.repository / "build/js/yarn.lock").write_bytes(b"changed again\n")

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=failure), \
                mock.patch.object(safari_yarn_lock, "capture_package_graph", side_effect=changed):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate, self.output)
        self.assertEqual("CAPTURE_REJECTED", receipt["status"])
        self.assertIn("generated input changed", receipt["reason"])

    def test_missing_root_or_all_workspace_packages_is_incomplete(self):
        for absent in ("all", "root"):
            with self.subTest(absent=absent):
                output = self.root / f"capture-{absent}"

                def failure(*args):
                    self.generated()
                    if absent == "all":
                        shutil.rmtree(self.repository / "build/js/packages")
                    else:
                        (self.repository / "build/js/package.json").unlink()
                    self.write_logs(output)
                    return {"command": ["./gradlew", ":kotlinStoreYarnLock"],
                            "pid": 123, "exit_code": 1, "started_ns": 1,
                            "finished_ns": 2}

                with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=failure):
                    receipt = safari_yarn_lock.capture(self.repository, self.candidate, output)
                shutil.rmtree(self.repository / "build")
                self.assertEqual("INCOMPLETE_PACKAGE_GRAPH", receipt["status"])
                self.assertTrue(receipt["missing_package_inputs"])
                self.assertFalse(receipt["qualified"])

    def test_malformed_workspace_graph_is_incomplete_with_receipt(self):
        def failure(*args):
            self.generated()
            (self.repository / "build/js/package.json").write_text(
                '{"name":"dyn4k","workspaces":[{}]}\n')
            self.write_logs()
            return {"command": ["./gradlew", ":kotlinStoreYarnLock"], "pid": 123,
                    "exit_code": 1, "started_ns": 1, "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=failure):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate, self.output)
        self.assertEqual("INCOMPLETE_PACKAGE_GRAPH", receipt["status"])
        self.assertTrue((self.output / "receipt.json").is_file())

    def test_generated_build_or_package_symlink_ancestor_is_rejected(self):
        for ancestor in ("build/js", "build/js/packages/dyn4k-dyn4k-core-test"):
            with self.subTest(ancestor=ancestor):
                output = self.root / f"capture-{ancestor.replace('/', '-')}"

                def failure(*args):
                    self.generated()
                    path = self.repository / ancestor
                    outside = self.root / f"outside-{ancestor.replace('/', '-')}"
                    shutil.move(str(path), str(outside))
                    path.symlink_to(outside, target_is_directory=True)
                    self.write_logs(output)
                    return {"command": ["./gradlew", ":kotlinStoreYarnLock"],
                            "pid": 123, "exit_code": 1, "started_ns": 1,
                            "finished_ns": 2}

                with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=failure):
                    receipt = safari_yarn_lock.capture(self.repository, self.candidate, output)
                shutil.rmtree(self.repository / "build")
                self.assertEqual("CAPTURE_REJECTED", receipt["status"])
                self.assertIn("symlink", receipt["reason"])
                self.assertFalse(receipt["qualified"])

    def test_quoted_lock_phrase_followed_by_unrelated_failure_is_not_mismatch(self):
        def failure(*args):
            self.generated()
            self.write_logs(stderr=(
                "Some log quoted: Lock file was changed. Run the `kotlinUpgradeYarnLock` task\n"
                "Execution failed for unrelated plugin\n"))
            return {"command": ["./gradlew", ":kotlinStoreYarnLock"], "pid": 123,
                    "exit_code": 1, "started_ns": 1, "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=failure):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate, self.output)
        self.assertEqual("OTHER_GRADLE_RESULT", receipt["status"])

    def test_missing_generated_lock_is_explicitly_incomplete(self):
        def failure(*args):
            self.write_logs()
            return {"command": ["./gradlew", ":kotlinStoreYarnLock"], "pid": 123,
                    "exit_code": 1, "started_ns": 1, "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=failure):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate, self.output)
        self.assertEqual("NO_GENERATED_LOCK", receipt["status"])
        self.assertFalse((self.output / "generated/build/js/yarn.lock").exists())

    def test_candidate_and_source_drift_are_rejected_before_running(self):
        with mock.patch.object(safari_yarn_lock, "run_lock_task") as run:
            with self.assertRaisesRegex(ValueError, "candidate SHA"):
                safari_yarn_lock.capture(self.repository, "a" * 40, self.output)
            (self.repository / "build.gradle.kts").write_text("plugins { altered }\n")
            with self.assertRaisesRegex(ValueError, "dirty tracked"):
                safari_yarn_lock.capture(self.repository, self.candidate, self.output)
            run.assert_not_called()

    def test_source_mutation_during_task_is_not_clean_capture(self):
        def mutated(*args):
            self.generated()
            self.write_logs()
            (self.repository / "kotlin-js-store/yarn.lock").write_bytes(b"mutated\n")
            return {"command": ["./gradlew", ":kotlinStoreYarnLock"], "pid": 123,
                    "exit_code": 1, "started_ns": 1, "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=mutated):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate, self.output)
        self.assertEqual("SOURCE_CHANGED", receipt["status"])
        self.assertEqual(b"mutated\n", (self.output / "tracked-after/kotlin-js-store/yarn.lock").read_bytes())

    def test_non_lock_source_mutation_during_task_is_not_clean_capture(self):
        def mutated(*args):
            self.generated()
            self.write_logs()
            (self.repository / "build.gradle.kts").write_text("plugins { altered }\n")
            return {"command": ["./gradlew", ":kotlinStoreYarnLock"], "pid": 123,
                    "exit_code": 1, "started_ns": 1, "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=mutated):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate, self.output)
        self.assertEqual("SOURCE_CHANGED", receipt["status"])

    def test_preexisting_generated_lock_and_in_tree_output_rejected(self):
        self.generated()
        with mock.patch.object(safari_yarn_lock, "run_lock_task") as run:
            with self.assertRaisesRegex(ValueError, "preexisting generated lock"):
                safari_yarn_lock.capture(self.repository, self.candidate, self.output)
            (self.repository / "build/js/yarn.lock").unlink()
            with self.assertRaisesRegex(ValueError, "outside the source"):
                safari_yarn_lock.capture(self.repository, self.candidate,
                                         self.repository / "build/capture")
            run.assert_not_called()

    def test_successful_lock_task_remains_diagnostic_only(self):
        def success(*args):
            self.generated(b"tracked lock\n")
            self.write_logs(stderr="")
            return {"command": ["./gradlew", ":kotlinStoreYarnLock"], "pid": 123,
                    "exit_code": 0, "started_ns": 1, "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=success):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate, self.output)
        self.assertEqual("LOCK_MATCHED_DIAGNOSTIC_ONLY", receipt["status"])
        self.assertFalse(receipt["qualified"])

    def test_lock_task_keeps_gradle_mismatch_enforcement(self):
        wrapper = self.repository / "gradlew"
        wrapper.write_text("#!/bin/sh\n"
                           "printf ':kotlinStoreYarnLock FAILED\\n'\n"
                           "printf 'Lock file was changed\\n' >&2\n"
                           "exit 1\n")
        wrapper.chmod(0o755)
        self.output.mkdir()
        result = safari_yarn_lock.run_lock_task(self.repository, self.output)
        command = result["command"]
        self.assertEqual([str(self.repository / "gradlew"), "--no-daemon",
                          "--console=plain", "--rerun-tasks", ":kotlinStoreYarnLock"],
                         command)
        self.assertNotIn("kotlinUpgradeYarnLock", command)
        self.assertEqual(1, result["exit_code"])
        self.assertEqual(b"Lock file was changed\n",
                         (self.output / "stderr.txt").read_bytes())

    def test_process_streams_and_bounds_logs_without_buffering_complete_output(self):
        wrapper = self.repository / "gradlew"
        wrapper.write_text("#!/bin/sh\npython3 -c 'import sys; "
                           "sys.stdout.buffer.write(b\"x\" * 257); "
                           "sys.stderr.buffer.write(b\"y\" * 257)'\n")
        wrapper.chmod(0o755)
        self.output.mkdir()
        with mock.patch.object(safari_yarn_lock, "MAX_FILE_BYTES", 128):
            result = safari_yarn_lock.run_lock_task(self.repository, self.output)
        self.assertEqual(0, result["exit_code"])
        self.assertEqual(128, (self.output / "stdout.txt").stat().st_size)
        self.assertEqual(128, (self.output / "stderr.txt").stat().st_size)
        self.assertTrue(result["stdout_truncated"])
        self.assertTrue(result["stderr_truncated"])
        self.assertEqual(257, result["stdout_bytes_seen"])
        self.assertEqual(257, result["stderr_bytes_seen"])

    def test_process_deadline_kills_a_stalled_wrapper(self):
        wrapper = self.repository / "gradlew"
        wrapper.write_text("#!/bin/sh\nsleep 5\n")
        wrapper.chmod(0o755)
        self.output.mkdir()
        with mock.patch.object(safari_yarn_lock, "MAX_PROCESS_SECONDS", 0.2):
            result = safari_yarn_lock.run_lock_task(self.repository, self.output)
        self.assertTrue(result["timed_out"])
        self.assertLess(result["finished_ns"] - result["started_ns"], 3_000_000_000)

    def test_truncated_log_cannot_be_labeled_a_complete_mismatch(self):
        def failure(*args):
            self.generated()
            self.write_logs()
            return {"command": ["./gradlew", ":kotlinStoreYarnLock"], "pid": 123,
                    "exit_code": 1, "started_ns": 1, "finished_ns": 2,
                    "stdout_truncated": True, "stderr_truncated": False,
                    "timed_out": False}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=failure):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate, self.output)
        self.assertEqual("INCOMPLETE_LOG_CAPTURE", receipt["status"])
        self.assertFalse(receipt["qualified"])

    def test_full_hosted_development_uses_exact_safari_source_command(self):
        def failure(repository, output, command):
            self.assertEqual([str(repository / "gradlew"), "--no-daemon", "--console=plain",
                              "--rerun-tasks", "--init-script",
                              str(output / "development/qualification.init.gradle"),
                              ":dyn4k-core:jsBrowserTest", ":dyn4k:jsBrowserTest",
                              f"-PqualificationInvocationId={command[-1].split('=')[1]}"], command)
            script = (output / "development/qualification.init.gradle").read_bytes()
            self.assertEqual("6a0057de491e563866306c0eae7d2baf9c6f1e70ec52497120e6d563b04b3eec",
                             hashlib.sha256(script).hexdigest())
            self.generated(safari=True)
            self.write_logs()
            return {"command": command, "pid": 123, "exit_code": 1,
                    "started_ns": 1, "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=failure):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate,
                                               self.output, "development")
        self.assertEqual("LOCK_MISMATCH_CAPTURED", receipt["status"])
        self.assertEqual("development", receipt["configuration"])
        self.assertFalse(receipt["qualified"])
        self.assertIn("development/qualification.init.gradle",
                      [item["path"] for item in receipt["files"]])

    def hosted_browser_failure(self, stderr):
        def failure(repository, output, command):
            self.generated(b"tracked lock\n", safari=True)
            stdout = ("> Task :dyn4k-core:jsTestPackageJson\n"
                      "> Task :dyn4k:jsTestPackageJson\n"
                      "> Task :kotlinNpmInstall\n"
                      "> Task :kotlinStoreYarnLock\n"
                      "> Task :dyn4k:jsBrowserTest\n"
                      "Safari has not captured in 60000 ms, killing.\n"
                      "> Task :dyn4k:jsBrowserTest FAILED\n")
            (output / "stdout.txt").write_text(stdout)
            (output / "stderr.txt").write_text(stderr)
            return {"command": command, "pid": 123, "exit_code": 1,
                    "started_ns": 1, "finished_ns": 2,
                    "stdout_bytes_seen": len(stdout.encode()),
                    "stderr_bytes_seen": len(stderr.encode()),
                    "stdout_truncated": False, "stderr_truncated": False,
                    "timed_out": False, "stream_incomplete": False}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=failure):
            return safari_yarn_lock.capture(self.repository, self.candidate,
                                            self.output, "development")

    def test_full_hosted_browser_capture_timeout_is_unqualified(self):
        receipt = self.hosted_browser_failure(
            "Safari failed 2 times (timeout). Giving up.\n"
            "Execution failed for task ':dyn4k:jsBrowserTest'.\n"
            "> Errors occurred during launch of browser for testing.\n")
        self.assertEqual("SAFARI_CAPTURE_TIMEOUT", receipt["status"])
        self.assertFalse(receipt["qualified"])
        with self.assertRaisesRegex(ValueError, "hosted diagnostic identity differs"):
            safari_yarn_lock.audit_capture(self.repository, self.candidate, self.output)

    def test_full_hosted_source_failure_is_not_browser_capture_timeout(self):
        receipt = self.hosted_browser_failure(
            "Execution failed for task ':dyn4k:jsBrowserTest'.\n"
            "> Test assertion failed.\n")
        self.assertEqual("OTHER_GRADLE_RESULT", receipt["status"])
        self.assertFalse(receipt["qualified"])

    def test_full_hosted_production_uses_exact_flag_and_script(self):
        def failure(repository, output, command):
            self.assertEqual("-PqualificationProduction=true", command[-1])
            self.assertEqual("eeaa1019f7b65efcfe2435f92425b2453bec947794a1db7090fcd8fa09479794",
                             hashlib.sha256((output / "production/qualification.init.gradle").read_bytes()).hexdigest())
            self.generated(safari=True)
            self.write_logs()
            return {"command": command, "pid": 123, "exit_code": 1,
                    "started_ns": 1, "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=failure):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate,
                                               self.output, "production")
        self.assertEqual("LOCK_MISMATCH_CAPTURED", receipt["status"])

    def test_full_hosted_wrong_command_or_process_is_rejected(self):
        def wrong(repository, output, command):
            self.generated(safari=True)
            self.write_logs()
            return {"command": [str(repository / "gradlew"), ":kotlinStoreYarnLock"],
                    "pid": 123, "exit_code": 1, "started_ns": 1, "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=wrong):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate,
                                               self.output, "development")
        self.assertEqual("PROCESS_BINDING_REJECTED", receipt["status"])

    def test_full_hosted_chrome_only_graph_cannot_match_safari(self):
        def chrome(repository, output, command):
            self.generated()
            self.write_logs()
            return {"command": command, "pid": 123, "exit_code": 1,
                    "started_ns": 1, "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=chrome):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate,
                                               self.output, "development")
        self.assertEqual("INCOMPLETE_PACKAGE_GRAPH", receipt["status"])

    def test_full_hosted_changed_init_script_is_rejected(self):
        def changed(repository, output, command):
            self.generated(safari=True)
            self.write_logs()
            (output / "development/qualification.init.gradle").write_text("// changed\n")
            return {"command": command, "pid": 123, "exit_code": 1,
                    "started_ns": 1, "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=changed):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate,
                                               self.output, "development")
        self.assertEqual("CAPTURE_REJECTED", receipt["status"])

    def test_full_hosted_wrong_candidate_never_starts_process(self):
        with mock.patch.object(safari_yarn_lock, "run_lock_task") as runner:
            with self.assertRaisesRegex(ValueError, "candidate SHA"):
                safari_yarn_lock.capture(self.repository, "a" * 40,
                                         self.output, "development")
            runner.assert_not_called()

    def test_full_hosted_public_audit_binds_command_candidate_process_and_raw_bytes(self):
        receipt = self.hosted_capture()
        self.assertEqual("LOCK_MISMATCH_CAPTURED", receipt["status"])
        self.assertEqual("LOCK_MISMATCH_CAPTURED", safari_yarn_lock.audit_capture(
            self.repository, self.candidate, self.output)["status"])
        for mutation in ("candidate", "command", "process", "raw"):
            with self.subTest(mutation=mutation):
                saved = (self.output / "receipt.json").read_bytes()
                raw = self.output / "generated/build/js/yarn.lock"
                raw_saved = raw.read_bytes()
                record = json.loads(saved)
                if mutation == "candidate":
                    record["candidate_sha"] = "a" * 40
                elif mutation == "command":
                    record["process"]["command"].remove("--init-script")
                elif mutation == "process":
                    record["process"]["pid"] = 0
                else:
                    raw.write_bytes(b"tampered lock\n")
                (self.output / "receipt.json").write_text(json.dumps(record) + "\n")
                with self.assertRaises(ValueError):
                    safari_yarn_lock.audit_capture(self.repository, self.candidate,
                                                   self.output)
                (self.output / "receipt.json").write_bytes(saved)
                raw.write_bytes(raw_saved)

    def test_full_hosted_public_audit_rejects_resealed_chrome_only_package(self):
        self.hosted_capture()
        path = self.output / "generated/build/js/packages/dyn4k-dyn4k-core-test/package.json"
        package = json.loads(path.read_text())
        del package["devDependencies"]["karma-safari-launcher"]
        path.write_text(json.dumps(package) + "\n")
        receipt_path = self.output / "receipt.json"
        receipt = json.loads(receipt_path.read_text())
        member = next(item for item in receipt["files"] if item["path"] ==
                      "generated/build/js/packages/dyn4k-dyn4k-core-test/package.json")
        member["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        member["size"] = path.stat().st_size
        receipt_path.write_text(json.dumps(receipt) + "\n")
        with self.assertRaisesRegex(ValueError, "Safari package"):
            safari_yarn_lock.audit_capture(self.repository, self.candidate, self.output)

    def test_full_hosted_public_cli_audits_capture(self):
        self.hosted_capture()
        arguments = ["safari_yarn_lock.py", "--candidate-sha", self.candidate,
                     "--output", str(self.output), "--audit"]
        with mock.patch.object(safari_yarn_lock, "ROOT", self.repository), \
                mock.patch.object(sys, "argv", arguments), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, safari_yarn_lock.main())
        self.assertEqual("LOCK_MISMATCH_CAPTURED", json.loads(output.getvalue())["status"])

    def test_manual_workflow_has_separate_mac_route_and_uploads_failed_capture(self):
        root = Path(__file__).resolve().parents[2]
        workflow = (root /
                    ".github/workflows/safari-yarn-lock-diagnostic.yml").read_text()
        qualification = (root / ".github/workflows/qualification.yml").read_text()
        qualified_launcher = re.search(r"(?m)^      SAFARI_BIN: (.+)$", qualification)
        self.assertIsNotNone(qualified_launcher)
        self.assertIn("    env:\n      SAFARI_BIN: " + qualified_launcher.group(1) + "\n",
                      workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("runs-on: macos-26", workflow)
        self.assertIn("java-version: '21'", workflow)
        self.assertIn("ref: ${{ inputs.candidate_sha }}", workflow)
        self.assertIn('--configuration "${{ inputs.configuration }}"', workflow)
        self.assertIn("--audit", workflow)
        self.assertIn("${{ github.run_id }}-${{ github.run_attempt }}", workflow)
        self.assertIn("if: always()", workflow)
        self.assertIn("tools/qualification/safari_yarn_lock.py", workflow)
        self.assertNotIn("kotlinUpgradeYarnLock", workflow)
        self.assertNotIn("yarnLockMismatchReport", workflow)

    def test_manual_workflow_retains_separate_safari_launch_context(self):
        root = Path(__file__).resolve().parents[2]
        workflow = (root /
                    ".github/workflows/safari-yarn-lock-diagnostic.yml").read_text()
        self.assertIn("DYN4K_SAFARI_LAUNCH_CONTEXT: ${{ runner.temp }}/safari-launch-context",
                      workflow)
        self.assertIn("- name: Capture source Kotlin/JS lock generation\n        env:\n"
                      "          DYN4K_SAFARI_LAUNCH_CONTEXT:", workflow)
        self.assertIn("name: safari-launch-context-${{ inputs.candidate_sha }}-", workflow)
        self.assertIn("path: ${{ runner.temp }}/safari-launch-context/", workflow)
        self.assertIn("if: always()", workflow)
        launcher = (root / "tools/qualification/safari-launch.sh").read_text()
        self.assertIn('DYN4K_SAFARI_LAUNCH_CONTEXT:-', launcher)
        self.assertIn('exec /usr/bin/open -W -a /Applications/Safari.app "$1" \\\n'
                      '    > "$context/open-$$.stdout" 2> "$context/open-$$.stderr"',
                      launcher)


if __name__ == "__main__":
    unittest.main()
