import json
import hashlib
import io
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
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
        qualification = Path(__file__).parent
        for name in ("safari-karma-reporter.js", "safari-launch.sh", "safari_reporter.py"):
            shutil.copyfile(qualification / name, self.repository / "tools/qualification" / name)
        (self.repository / ".github/workflows").mkdir(parents=True)
        shutil.copyfile(qualification.parents[1] / ".github/workflows/safari-yarn-lock-diagnostic.yml",
                        self.repository / ".github/workflows/safari-yarn-lock-diagnostic.yml")
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

    def test_full_hosted_teamcity_overflow_has_explicit_failure_status(self):
        def overflow(repository, output, command):
            self.generated(b"tracked lock\n", safari=True)
            stdout = ("> Task :dyn4k-core:jsTestPackageJson\n"
                      "> Task :dyn4k:jsTestPackageJson\n"
                      "> Task :kotlinNpmInstall\n"
                      "> Task :kotlinStoreYarnLock\n"
                      "> Task :dyn4k-core:jsBrowserTest FAILED\n")
            stderr = ("##teamcity[testFailed name='overflow-message' message='"
                      "Cannot process output: too long teamcity service message "
                      "(more than 1Mb). Event was lost.\n")
            (output / "stdout.txt").write_text(stdout)
            (output / "stderr.txt").write_text(stderr)
            return {"command": command, "pid": 123, "exit_code": 1,
                    "started_ns": 1, "finished_ns": 2,
                    "stdout_bytes_seen": len(stdout), "stderr_bytes_seen": len(stderr),
                    "stdout_truncated": False, "stderr_truncated": False,
                    "timed_out": False, "stream_incomplete": False}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=overflow):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate,
                                               self.output, "development")
        self.assertEqual("SAFARI_TEST_OUTPUT_OVERFLOW", receipt["status"])
        self.assertFalse(receipt["qualified"])

    def test_quoted_overflow_phrase_does_not_mask_other_gradle_failure(self):
        def other_failure(repository, output, command):
            self.generated(b"tracked lock\n", safari=True)
            stdout = ("> Task :dyn4k-core:jsTestPackageJson\n"
                      "> Task :dyn4k:jsTestPackageJson\n"
                      "> Task :kotlinNpmInstall\n"
                      "> Task :kotlinStoreYarnLock\n"
                      "> Task :dyn4k-core:jsBrowserTest FAILED\n")
            (output / "stdout.txt").write_text(stdout)
            (output / "stderr.txt").write_text(
                "Another failure quoted: Cannot process output: too long teamcity "
                "service message (more than 1Mb). Event was lost.\n")
            return {"command": command, "pid": 123, "exit_code": 1,
                    "started_ns": 1, "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=other_failure):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate,
                                               self.output, "development")
        self.assertEqual("OTHER_GRADLE_RESULT", receipt["status"])

    def test_safari_reporter_splits_service_messages_without_dropping_them(self):
        source = Path(__file__).with_name("safari-karma-reporter.js")
        script = "\n".join((
            "const assert = require('node:assert/strict');",
            "const fs = require('node:fs');",
            "const vm = require('node:vm');",
            "const output = [];",
            "function OriginalReporter(decorate) {",
            "  decorate(this);",
            "  this.emit = message => this.write(message);",
            "}",
            "OriginalReporter.$inject = ['baseReporterDecorator'];",
            "const plugin = {'reporter:karma-kotlin-reporter': ['type', OriginalReporter]};",
            "const config = {plugins: [plugin]};",
            "vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), {config, Buffer});",
            "const Reporter = plugin['reporter:karma-kotlin-reporter'][1];",
            "assert.deepEqual(Reporter.$inject, OriginalReporter.$inject);",
            "const reporter = new Reporter(instance => {",
            "  instance.write = message => output.push(message);",
            "});",
            "reporter.emit(\"##teamcity[testStarted name='one']\");",
            "reporter.emit(\"##teamcity[testFinished name='one']\\n\");",
            "assert.deepEqual(output, [\"##teamcity[testStarted name='one']\\n\",",
            "                          \"##teamcity[testFinished name='one']\\n\"]);",
            "assert.throws(() => reporter.emit('x'.repeat(262145)), /service message exceeds/);",
            "assert.equal(output.length, 2);",
            "for (let i = 0; i < 12000; i++) reporter.emit(",
            "  `##teamcity[testStarted name='case-${i}' payload='${'x'.repeat(80)}']`);",
            "assert.equal(output.length, 12002);",
            "assert.ok(output.every(line => line.endsWith('\\n')));",
            "assert.ok(Buffer.byteLength(output.join(''), 'utf8') > 1048576);",
        ))
        result = subprocess.run(["node", "-e", script, str(source)],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_hosted_capture_stages_and_binds_reporter_source(self):
        source = Path(__file__).with_name("safari-karma-reporter.js")
        def failure(repository, output, command):
            for module in ("dyn4k-core", "dyn4k"):
                staged = repository / module / "karma.config.d/qualification-safari-reporter.js"
                self.assertEqual(source.read_bytes(), staged.read_bytes())
            self.generated(safari=True)
            self.write_logs()
            return {"command": command, "pid": 123, "exit_code": 1,
                    "started_ns": 1, "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=failure):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate,
                                               self.output, "development")
        self.assertEqual("LOCK_MISMATCH_CAPTURED", receipt["status"])
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         receipt["source_input_sha256"]["tools/qualification/safari-karma-reporter.js"])
        self.assertEqual(source.read_bytes(),
                         (self.output / "inputs/tools/qualification/safari-karma-reporter.js").read_bytes())
        for relative in ("tools/qualification/safari-launch.sh",
                         ".github/workflows/safari-yarn-lock-diagnostic.yml"):
            data = (self.repository / relative).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(),
                             receipt["source_input_sha256"][relative])
            self.assertEqual(data, (self.output / "inputs" / relative).read_bytes())
        for module in ("dyn4k-core", "dyn4k"):
            self.assertFalse((self.repository / module / "karma.config.d").exists())

    def test_hosted_capture_rejects_reporter_source_changed_during_task(self):
        def changed(repository, output, command):
            self.generated(safari=True)
            self.write_logs()
            (repository / "tools/qualification/safari-karma-reporter.js").write_text(
                "config.plugins = [];\n")
            return {"command": command, "pid": 123, "exit_code": 1,
                    "started_ns": 1, "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=changed):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate,
                                               self.output, "development")
        self.assertEqual("SOURCE_CHANGED", receipt["status"])
        self.assertFalse(receipt["qualified"])
        for module in ("dyn4k-core", "dyn4k"):
            self.assertFalse((self.repository / module / "karma.config.d").exists())

    def test_public_hosted_capture_rejects_changed_staged_reporter_in_both_modules(self):
        for module in ("dyn4k-core", "dyn4k"):
            with self.subTest(module=module):
                shutil.rmtree(self.repository / "build", ignore_errors=True)
                for root in ("dyn4k-core", "dyn4k"):
                    directory = self.repository / root / "karma.config.d"
                    (directory / "qualification-safari-reporter.js").unlink(missing_ok=True)
                    if directory.is_dir() and not any(directory.iterdir()):
                        directory.rmdir()
                output = self.root / f"capture-{module}"
                changed_bytes = b"config.plugins = [];\n"

                def changed(repository, destination, command):
                    self.generated(b"tracked lock\n", safari=True)
                    stdout = ("> Task :dyn4k-core:jsTestPackageJson\n"
                              "> Task :dyn4k:jsTestPackageJson\n"
                              "> Task :kotlinNpmInstall\n"
                              "> Task :kotlinStoreYarnLock\n")
                    (destination / "stdout.txt").write_text(stdout)
                    (destination / "stderr.txt").write_text("")
                    (repository / module / "karma.config.d"
                     / "qualification-safari-reporter.js").write_bytes(changed_bytes)
                    return {"command": command, "pid": 123, "exit_code": 0,
                            "started_ns": 1, "finished_ns": 2,
                            "stdout_bytes_seen": len(stdout), "stderr_bytes_seen": 0,
                            "stdout_truncated": False, "stderr_truncated": False,
                            "timed_out": False, "stream_incomplete": False}

                arguments = ["safari_yarn_lock.py", "--candidate-sha", self.candidate,
                             "--output", str(output), "--configuration", "development"]
                with mock.patch.object(safari_yarn_lock, "ROOT", self.repository), \
                        mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=changed), \
                        mock.patch.object(sys, "argv", arguments), \
                        redirect_stdout(io.StringIO()) as printed:
                    self.assertEqual(1, safari_yarn_lock.main())
                receipt = json.loads((output / "receipt.json").read_text())
                self.assertEqual("STAGED_REPORTER_CHANGED", receipt["status"])
                self.assertFalse(receipt["qualified"])
                self.assertEqual(changed_bytes,
                                 (output / "forensic/safari-reporter" / module
                                  / "qualification-safari-reporter.js").read_bytes())
                self.assertFalse((self.repository / module / "karma.config.d").exists())
                self.assertEqual(receipt["status"], json.loads(printed.getvalue())["status"])

    def test_public_context_rejects_configs_without_committed_reporter(self):
        context, package = self.context_fixture()
        (package / "karma.conf.js").write_text("module.exports = {};\n")
        (self.repository / safari_yarn_lock.CONTEXT_ROOTS[1] / "karma.conf.js").write_text(
            "module.exports = {};\n")
        arguments = ["safari_yarn_lock.py", "--candidate-sha", self.candidate,
                     "--input-context", str(self.raw_context), "--output", str(context),
                     "--capture-context"]
        with mock.patch.object(safari_yarn_lock, "ROOT", self.repository), \
                mock.patch.object(sys, "argv", arguments), \
                redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(1, safari_yarn_lock.main())
        inventory = json.loads((context / "inventory.json").read_text())
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        self.assertEqual(2, len([item for item in inventory["inputs"]
                                 if item["reason"] == "reporter_fragment_missing"]))
        self.assertEqual(inventory["status"], json.loads(printed.getvalue())["status"])

    def test_public_hosted_capture_rejects_unowned_config_leftover(self):
        leftover = self.repository / "dyn4k-core/karma.config.d/extra.js"

        def changed(repository, destination, command):
            self.generated(b"tracked lock\n", safari=True)
            stdout = ("> Task :dyn4k-core:jsTestPackageJson\n"
                      "> Task :dyn4k:jsTestPackageJson\n"
                      "> Task :kotlinNpmInstall\n"
                      "> Task :kotlinStoreYarnLock\n")
            (destination / "stdout.txt").write_text(stdout)
            (destination / "stderr.txt").write_text("")
            leftover.write_bytes(b"other config\n")
            return {"command": command, "pid": 123, "exit_code": 0,
                    "started_ns": 1, "finished_ns": 2,
                    "stdout_bytes_seen": len(stdout), "stderr_bytes_seen": 0,
                    "stdout_truncated": False, "stderr_truncated": False,
                    "timed_out": False, "stream_incomplete": False}

        arguments = ["safari_yarn_lock.py", "--candidate-sha", self.candidate,
                     "--output", str(self.output), "--configuration", "development"]
        with mock.patch.object(safari_yarn_lock, "ROOT", self.repository), \
                mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=changed), \
                mock.patch.object(sys, "argv", arguments), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(1, safari_yarn_lock.main())
        receipt = json.loads((self.output / "receipt.json").read_text())
        self.assertEqual("STAGED_REPORTER_CHANGED", receipt["status"])
        self.assertEqual("LEFTOVER", receipt["reporter_stage"]["projects"]["dyn4k-core"])
        self.assertEqual(b"other config\n", leftover.read_bytes())
        self.assertEqual(b"other config\n",
                         (self.output / "forensic/safari-reporter/dyn4k-core/extra.js")
                         .read_bytes())
        self.assertFalse((self.repository / "dyn4k/karma.config.d").exists())

    def test_public_hosted_capture_rejects_staging_directory_swap_without_following_it(self):
        outside = self.output.parent / "outside-reporter"
        outside.mkdir()
        (outside / "qualification-safari-reporter.js").write_bytes(b"outside bytes\n")
        directory = self.repository / "dyn4k-core/karma.config.d"

        def changed(repository, destination, command):
            self.generated(b"tracked lock\n", safari=True)
            stdout = ("> Task :dyn4k-core:jsTestPackageJson\n"
                      "> Task :dyn4k:jsTestPackageJson\n"
                      "> Task :kotlinNpmInstall\n"
                      "> Task :kotlinStoreYarnLock\n")
            (destination / "stdout.txt").write_text(stdout)
            (destination / "stderr.txt").write_text("")
            (directory / "qualification-safari-reporter.js").unlink()
            directory.rmdir()
            directory.symlink_to(outside, target_is_directory=True)
            return {"command": command, "pid": 123, "exit_code": 0,
                    "started_ns": 1, "finished_ns": 2,
                    "stdout_bytes_seen": len(stdout), "stderr_bytes_seen": 0,
                    "stdout_truncated": False, "stderr_truncated": False,
                    "timed_out": False, "stream_incomplete": False}

        arguments = ["safari_yarn_lock.py", "--candidate-sha", self.candidate,
                     "--output", str(self.output), "--configuration", "development"]
        with mock.patch.object(safari_yarn_lock, "ROOT", self.repository), \
                mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=changed), \
                mock.patch.object(sys, "argv", arguments), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(1, safari_yarn_lock.main())
        receipt = json.loads((self.output / "receipt.json").read_text())
        self.assertEqual("STAGED_REPORTER_CHANGED", receipt["status"])
        self.assertEqual("DIRECTORY_CHANGED", receipt["reporter_stage"]["projects"]["dyn4k-core"])
        self.assertEqual(b"outside bytes\n",
                         (outside / "qualification-safari-reporter.js").read_bytes())
        self.assertTrue(directory.is_symlink())

    def test_public_hosted_capture_rejects_project_ancestor_swap_without_outside_access(self):
        project = self.repository / "dyn4k-core"
        moved = self.repository / "moved-core"
        outside = self.root / "outside-core"
        sentinel = outside / "karma.config.d/qualification-safari-reporter.js"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_bytes(b"OUTSIDE SENTINEL\n")

        def changed(repository, destination, command):
            self.generated(b"tracked lock\n", safari=True)
            (destination / "stdout.txt").write_text("> Task :kotlinStoreYarnLock\n")
            (destination / "stderr.txt").write_text("")
            project.rename(moved)
            project.symlink_to(outside, target_is_directory=True)
            return {"command": command, "pid": 123, "exit_code": 0,
                    "started_ns": 1, "finished_ns": 2,
                    "stdout_bytes_seen": 33, "stderr_bytes_seen": 0,
                    "stdout_truncated": False, "stderr_truncated": False,
                    "timed_out": False, "stream_incomplete": False}

        arguments = ["safari_yarn_lock.py", "--candidate-sha", self.candidate,
                     "--output", str(self.output), "--configuration", "development"]
        with mock.patch.object(safari_yarn_lock, "ROOT", self.repository), \
                mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=changed), \
                mock.patch.object(sys, "argv", arguments), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(1, safari_yarn_lock.main())
        receipt = json.loads((self.output / "receipt.json").read_text())
        self.assertEqual("CHANGED", receipt["reporter_stage"]["status"])
        self.assertEqual(b"OUTSIDE SENTINEL\n", sentinel.read_bytes())
        self.assertFalse((self.output / "forensic/safari-reporter/dyn4k-core"
                          / "qualification-safari-reporter.js").exists())

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
        self.assertIn("DYN4K_SAFARI_LAUNCH_CONTEXT: ${{ runner.temp }}/safari-launch-context-raw",
                      workflow)
        self.assertIn("- name: Capture source Kotlin/JS lock generation\n        env:\n"
                      "          DYN4K_SAFARI_LAUNCH_CONTEXT:", workflow)
        self.assertIn("name: safari-launch-context-${{ inputs.candidate_sha }}-", workflow)
        self.assertIn("path: ${{ runner.temp }}/safari-launch-context/", workflow)
        self.assertNotIn("path: ${{ runner.temp }}/safari-launch-context-raw/", workflow)
        self.assertIn("if: always()", workflow)
        self.assertIn("--capture-context", workflow)
        self.assertIn('--input-context "$raw" --output "$context"', workflow)
        self.assertIn('printf \'session_exit=%s\\nprocess_exit=%s\\n\'', workflow)
        self.assertNotIn("find \"$source\"", workflow)
        launcher = (root / "tools/qualification/safari-launch.sh").read_text()
        self.assertIn('DYN4K_SAFARI_LAUNCH_CONTEXT:-', launcher)
        self.assertIn('exec /usr/bin/open -W -a /Applications/Safari.app "$1"', launcher)

    def context_fixture(self, suffix=""):
        context = self.root / ("context" + suffix)
        self.raw_context = self.root / ("raw-context" + suffix)
        self.raw_context.mkdir()
        (self.raw_context / "launch-123.txt").write_text("pid=123\n")
        (self.raw_context / "sample-state-123.txt").write_text(
            "samples_completed=5\nsampler_exit=0\n")
        (self.raw_context / "process-123.txt").write_text(
            "sample=1\nsample=2\nsample=3\nsample=4\nsample=5\n")
        (self.raw_context / "launch-outcome-123.txt").write_text("open_exit=23\n")
        (self.raw_context / "redirect-123.html").write_text("redirect\n")
        (self.raw_context / "open-123.stdout").write_text("")
        (self.raw_context / "open-123.stderr").write_text("early failure\n")
        (self.raw_context / "session-after.txt").write_text("Aqua\n")
        (self.raw_context / "process-after.txt").write_text("process\n")
        (self.raw_context / "host-outcome.txt").write_text(
            "session_exit=0\nprocess_exit=0\n")
        for relative in safari_yarn_lock.CONTEXT_ROOTS:
            (self.repository / relative).mkdir(parents=True, exist_ok=True)
        package = self.repository / safari_yarn_lock.CONTEXT_ROOTS[0]
        return context, package

    def write_valid_karma_configs(self, mode="development"):
        reporter = (self.repository /
                    "tools/qualification/safari-karma-reporter.js").read_text()
        for module in ("dyn4k-core", "dyn4k"):
            package = f"dyn4k-{module}-test"
            package_root = self.repository / "build/js/packages" / package
            package_root.mkdir(parents=True, exist_ok=True)
            runner = str(self.repository / "build/js/node_modules/kotlin-web-helpers/dist"
                         / "kotlin-test-karma-runner.js")
            if mode == "production":
                source = str(self.repository / module / "build/compileSync/js/test"
                             / "testProductionExecutable/kotlin" / f"{package}.js")
            else:
                source = str(package_root / "kotlin" / f"{package}.js")
            settings = {"singleRun": True, "autoWatch": False,
                        "basePath": str(package_root), "files": [runner, source],
                        "frameworks": ["webpack-output", "mocha", "webpack"],
                        "client": {"args": []}, "browsers": ["Safari"],
                        "customLaunchers": {}, "failOnFailingTestSuite": False,
                        "failOnEmptyTestSuite": False,
                        "reporters": ["karma-kotlin-reporter"], "preprocessors": {
                            runner: ["webpack", "sourcemap"],
                            source: ["webpack", "sourcemap"]},
                        "proxies": {}, "webpackCopy": []}
            (package_root / "karma.conf.js").write_text(
                "\nmodule.exports = function(config) {\n\nconfig.set("
                + json.dumps(settings) + ");"
                + safari_yarn_lock.safari_reporter.APPROVED_GENERATOR_TAIL
                + reporter + "\n}\n")

    def test_public_capture_rejects_generated_config_symlinked_package_ancestor(self):
        self.write_valid_karma_configs()
        package = self.repository / "build/js/packages/dyn4k-dyn4k-core-test"
        outside = self.root / "outside-generated-package"
        package.rename(outside)
        package.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "unsafe|symlink|identity"):
            safari_yarn_lock.full_hosted.capture_safari_config(
                self.repository, self.candidate, Path("dyn4k-core"), "development",
                {"started_ns": 0, "finished_ns": time.time_ns() + 1_000_000_000},
                self.output, "development/karma-config/dyn4k-core/karma.conf.js")
        self.assertEqual((outside / "karma.conf.js").read_bytes(),
                         (package / "karma.conf.js").read_bytes())

    def capture_context(self, context):
        return safari_yarn_lock.capture_karma_context(
            self.repository, self.candidate, context, self.raw_context)

    def assert_context_upload_bound(self, context):
        files = [path for path in context.rglob("*") if path.is_file()]
        self.assertFalse(any(path.is_symlink() for path in context.rglob("*")))
        self.assertTrue(all(path.stat().st_size <= safari_yarn_lock.CONTEXT_MAX_FILE_BYTES
                            for path in files if path.name != "inventory.json"))
        self.assertLessEqual(sum(path.stat().st_size for path in files),
                             safari_yarn_lock.CONTEXT_MAX_UPLOAD_BYTES)
        self.assertLessEqual((context / "inventory.json").stat().st_size,
                             safari_yarn_lock.CONTEXT_MAX_INVENTORY_BYTES)

    def test_context_scanner_copies_regular_unique_config_with_inventory(self):
        context, package = self.context_fixture()
        source = package / "karma.conf.js"
        self.write_valid_karma_configs()
        (package / "node_modules").symlink_to(self.root, target_is_directory=True)
        inventory = self.capture_context(context)
        self.assertEqual("CONTEXT_COMPLETE", inventory["status"])
        self.assertFalse(inventory["qualified"])
        self.assertEqual(source.read_bytes(),
                         (context / "config" / safari_yarn_lock.CONTEXT_ROOTS[0]
                          / "karma.conf.js").read_bytes())
        self.assertTrue(any(item["status"] == "copied" for item in inventory["inputs"]))
        self.assertTrue(any(item["reason"] == "excluded_node_modules"
                            for item in inventory["inputs"]))
        self.assertTrue(any(item["path"] == "process-after.txt"
                            and item["original_size"] == item["retained_size"]
                            for item in inventory["inputs"]))
        self.assertTrue(any(item["path"] == "launch-123.txt"
                            and item["original_size"] == item["retained_size"]
                            for item in inventory["inputs"]))
        self.assertEqual(inventory, json.loads((context / "inventory.json").read_text()))
        self.assert_context_upload_bound(context)

    def test_context_scanner_ignores_irrelevant_klib_cache(self):
        context, _ = self.context_fixture()
        self.write_valid_karma_configs()
        cache = self.repository / "dyn4k-core/build/klib/cache/js/testDevelopmentExecutable"
        cache.mkdir(parents=True)
        for number in range(2050):
            (cache / f"entry-{number}.bin").write_bytes(b"x")
        inventory = self.capture_context(context)
        self.assertEqual("CONTEXT_COMPLETE", inventory["status"])
        self.assertEqual(2, inventory["copied_files"])
        self.assertLess(inventory["entries_seen"], safari_yarn_lock.CONTEXT_MAX_ENTRIES)

    def test_public_context_binds_exact_reporter_and_module_source(self):
        for mutation in ("none", "altered_fragment", "other_module", "mixed_mode",
                         "later_override", "commented_fragment", "provider_clear",
                         "bracket_chrome"):
            with self.subTest(mutation=mutation):
                context, _ = self.context_fixture(mutation)
                self.write_valid_karma_configs()
                core = self.repository / safari_yarn_lock.CONTEXT_ROOTS[0] / "karma.conf.js"
                facade = self.repository / safari_yarn_lock.CONTEXT_ROOTS[1] / "karma.conf.js"
                if mutation == "altered_fragment":
                    facade.write_text(facade.read_text().replace("this.write = function(message)",
                                                               "this.log = function(message)"))
                elif mutation == "other_module":
                    facade.write_bytes(core.read_bytes())
                elif mutation == "mixed_mode":
                    development_core = core.read_bytes()
                    self.write_valid_karma_configs("production")
                    core.write_bytes(development_core)
                elif mutation == "later_override":
                    head, tail = facade.read_text().rsplit("\n}\n", 1)
                    facade.write_text(head + "\nconfig.set({browsers: ['ChromeHeadless']});\n}\n" + tail)
                elif mutation == "commented_fragment":
                    facade.write_text(facade.read_text().replace(
                        "const DYN4K_SAFARI_REPORTER_NEWLINES", "// const DYN4K_SAFARI_REPORTER_NEWLINES"))
                elif mutation == "provider_clear":
                    fragment = (self.repository /
                                "tools/qualification/safari-karma-reporter.js").read_text()
                    facade.write_text(facade.read_text().replace(
                        fragment, "config.plugins = [];\n" + fragment))
                elif mutation == "bracket_chrome":
                    fragment = (self.repository /
                                "tools/qualification/safari-karma-reporter.js").read_text()
                    facade.write_text(facade.read_text().replace(
                        fragment, "config['set']({browsers: ['ChromeHeadless']});\n" + fragment))
                arguments = ["safari_yarn_lock.py", "--candidate-sha", self.candidate,
                             "--input-context", str(self.raw_context), "--output", str(context),
                             "--capture-context"]
                with mock.patch.object(safari_yarn_lock, "ROOT", self.repository), \
                        mock.patch.object(sys, "argv", arguments), \
                        redirect_stdout(io.StringIO()) as printed:
                    self.assertEqual(0 if mutation == "none" else 1,
                                     safari_yarn_lock.main())
                inventory = json.loads((context / "inventory.json").read_text())
                self.assertEqual("CONTEXT_COMPLETE" if mutation == "none"
                                 else "CONTEXT_INCOMPLETE", inventory["status"])
                self.assertEqual(inventory["status"], json.loads(printed.getvalue())["status"])
                if mutation != "none":
                    self.assertTrue(any(item["reason"] in (
                        "reporter_fragment_missing", "karma_config_module_mismatch",
                        "karma_config_source_mismatch", "karma_config_shape_mismatch",
                        "reporter_fragment_in_comment") for item in inventory["inputs"]))

    def test_public_context_rejects_same_type_replacement_commit(self):
        context, _ = self.context_fixture()
        self.write_valid_karma_configs()
        lock = self.repository / "kotlin-js-store/yarn.lock"
        substituted = b"replacement lock bytes\n"
        lock.write_bytes(substituted)
        subprocess.run(["git", "-C", str(self.repository), "add", "kotlin-js-store/yarn.lock"],
                       check=True)
        subprocess.run(["git", "-C", str(self.repository), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit", "-qm",
                        "replacement source"], check=True)
        replacement = subprocess.check_output(
            ["git", "-C", str(self.repository), "rev-parse", "HEAD"], text=True).strip()
        subprocess.run(["git", "-C", str(self.repository), "checkout", "-q", "--detach",
                        self.candidate], check=True)
        subprocess.run(["git", "-C", str(self.repository), "read-tree", replacement + "^{tree}"],
                       check=True)
        lock.write_bytes(substituted)
        subprocess.run(["git", "-C", str(self.repository), "replace", self.candidate,
                        replacement], check=True)
        arguments = ["safari_yarn_lock.py", "--candidate-sha", self.candidate,
                     "--input-context", str(self.raw_context), "--output", str(context),
                     "--capture-context"]
        with mock.patch.object(safari_yarn_lock, "ROOT", self.repository), \
                mock.patch.object(sys, "argv", arguments), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(1, safari_yarn_lock.main())
        inventory = json.loads((context / "inventory.json").read_text())
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        self.assertTrue(any(item["reason"] == "scan_failed" for item in inventory["inputs"]))

    def test_context_scanner_requires_both_module_configs(self):
        context, _ = self.context_fixture()
        package = self.repository / "build/js/packages/dyn4k-dyn4k-core-test"
        package.mkdir(parents=True, exist_ok=True)
        (package / "karma.conf.js").write_text("// core\n")
        inventory = self.capture_context(context)
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        self.assertTrue(any(item["reason"] == "missing_module_karma_config"
                            for item in inventory["inputs"]))

    def test_context_scanner_marks_per_file_byte_truncation(self):
        context, package = self.context_fixture()
        (package / "a-karma.js").write_bytes(b"12345")
        with mock.patch.object(safari_yarn_lock, "CONTEXT_MAX_FILE_BYTES", 4), \
                mock.patch.object(safari_yarn_lock, "CONTEXT_MAX_TOTAL_BYTES", 10):
            inventory = self.capture_context(context)
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        self.assertEqual(4, inventory["copied_bytes"])
        self.assertEqual("per_file_byte_limit", inventory["inputs"][0]["reason"])

    def test_context_scanner_marks_total_byte_truncation(self):
        context, package = self.context_fixture()
        (package / "a-karma.js").write_bytes(b"12345")
        with mock.patch.object(safari_yarn_lock, "CONTEXT_MAX_FILE_BYTES", 10), \
                mock.patch.object(safari_yarn_lock, "CONTEXT_MAX_TOTAL_BYTES", 3):
            inventory = self.capture_context(context)
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        self.assertEqual(3, inventory["copied_bytes"])
        self.assertEqual("total_byte_limit", inventory["inputs"][0]["reason"])

    def test_context_scanner_skips_duplicate_inode(self):
        context, package = self.context_fixture()
        source = package / "a-karma.js"
        source.write_text("config\n")
        os.link(source, package / "b-karma.js")
        inventory = self.capture_context(context)
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        self.assertEqual(1, inventory["copied_files"])
        self.assertTrue(any(item["reason"] == "duplicate_inode"
                            for item in inventory["inputs"]))

    def test_context_scanner_rejects_file_count_and_symlink_traversal(self):
        context, package = self.context_fixture()
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "outside-karma.js").write_text("outside\n")
        (package / "linked").symlink_to(outside, target_is_directory=True)
        (package / "linked-karma.js").symlink_to(outside / "outside-karma.js")
        (package / "a-karma.js").write_text("a\n")
        (package / "b-karma.js").write_text("b\n")
        with mock.patch.object(safari_yarn_lock, "CONTEXT_MAX_FILES", 1):
            inventory = self.capture_context(context)
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        self.assertTrue(any(item["reason"] == "symlink" for item in inventory["inputs"]))
        self.assertTrue(any(item["reason"] == "file_count_limit"
                            for item in inventory["inputs"]))
        self.assertFalse((context / "config" / safari_yarn_lock.CONTEXT_ROOTS[0]
                          / "linked/outside-karma.js").exists())
        self.assertLessEqual(inventory["copied_files"], 1)

    def test_context_scanner_rejects_symlink_root(self):
        context, package = self.context_fixture()
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "karma.conf.js").write_text("outside\n")
        package.rmdir()
        package.symlink_to(outside, target_is_directory=True)
        inventory = self.capture_context(context)
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        self.assertEqual(0, inventory["copied_files"])
        self.assertTrue(any(item["reason"] == "missing_or_unsafe_root"
                            for item in inventory["inputs"]))

    def test_context_scanner_retains_deadline_and_failed_scan(self):
        context, package = self.context_fixture()
        (package / "karma.conf.js").write_text("config\n")
        with mock.patch.object(safari_yarn_lock, "CONTEXT_MAX_SECONDS", 0):
            inventory = self.capture_context(context)
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        self.assertTrue(any(item["reason"] == "traversal_deadline"
                            for item in inventory["inputs"]))
        second_context = self.root / "second-context"
        with mock.patch.object(safari_yarn_lock.os, "scandir", side_effect=OSError("scan failed")):
            inventory = self.capture_context(second_context)
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        self.assertTrue(any(item["status"] == "failed" for item in inventory["inputs"]))

    def test_context_scanner_rejects_unfinished_sampler(self):
        context, package = self.context_fixture()
        (package / "karma.conf.js").write_text("config\n")
        (self.raw_context / "sample-state-123.txt").unlink()
        inventory = self.capture_context(context)
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        self.assertTrue(any(item["reason"] == "sampler_incomplete"
                            for item in inventory["inputs"]))

    def test_context_scanner_records_pending_open_as_incomplete(self):
        context, package = self.context_fixture()
        (package / "karma.conf.js").write_text("config\n")
        (self.raw_context / "launch-outcome-123.txt").write_text("open_state=pending\n")
        inventory = self.capture_context(context)
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        self.assertTrue(any(item["reason"] == "open_pending"
                            for item in inventory["inputs"]))
        self.assertEqual("open_state=pending\n",
                         (context / "launch-outcome-123.txt").read_text())

    def test_context_scanner_rejects_missing_process_samples(self):
        context, package = self.context_fixture()
        (package / "karma.conf.js").write_text("config\n")
        (self.raw_context / "process-123.txt").unlink()
        inventory = self.capture_context(context)
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        self.assertTrue(any(item["reason"] == "sampler_incomplete"
                            for item in inventory["inputs"]))

    def test_context_scanner_rejects_missing_launch_output(self):
        context, package = self.context_fixture()
        (package / "karma.conf.js").write_text("config\n")
        (self.raw_context / "open-123.stderr").unlink()
        inventory = self.capture_context(context)
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        self.assertTrue(any(item["reason"] == "missing_or_unreadable_sidecar"
                            for item in inventory["inputs"]))

    def test_context_scanner_rejects_and_bounds_oversized_process_snapshot(self):
        context, package = self.context_fixture()
        (package / "karma.conf.js").write_text("config\n")
        (self.raw_context / "process-after.txt").write_bytes(b"P" * 1_572_864)
        inventory = self.capture_context(context)
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        self.assertLessEqual((context / "process-after.txt").stat().st_size, 256 * 1024)
        self.assertTrue(any(item["path"] == "process-after.txt"
                            and item["original_size"] == 1_572_864
                            and item["retained_size"] <= 256 * 1024
                            and item["status"] == "truncated"
                            for item in inventory["inputs"]))
        self.assert_context_upload_bound(context)

    def test_context_scanner_rejects_and_bounds_large_launch_and_session(self):
        context, package = self.context_fixture()
        (package / "karma.conf.js").write_text("config\n")
        (self.raw_context / "session-after.txt").write_bytes(b"S" * 614_400)
        (self.raw_context / "launch-123.txt").write_bytes(b"L" * 614_400)
        output = io.StringIO()
        with mock.patch.object(safari_yarn_lock, "ROOT", self.repository), \
                mock.patch.object(sys, "argv", ["safari_yarn_lock.py", "--candidate-sha",
                                                self.candidate, "--input-context",
                                                str(self.raw_context), "--output", str(context),
                                                "--capture-context"]), \
                redirect_stdout(output):
            self.assertEqual(1, safari_yarn_lock.main())
        self.assertEqual("CONTEXT_INCOMPLETE", json.loads(output.getvalue())["status"])
        inventory = json.loads((context / "inventory.json").read_text())
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        for name in ("session-after.txt", "launch-123.txt"):
            self.assertLessEqual((context / name).stat().st_size, 256 * 1024)
            self.assertTrue(any(item["path"] == name
                                and item["original_size"] == 614_400
                                and item["retained_size"] <= 256 * 1024
                                and item["status"] == "truncated"
                                for item in inventory["inputs"]))
        self.assert_context_upload_bound(context)

    def test_context_cli_rejects_reviewers_oversized_snapshot(self):
        context, package = self.context_fixture()
        (package / "karma.conf.js").write_text("config\n")
        (self.raw_context / "process-after.txt").write_bytes(b"P" * 1_572_864)
        output = io.StringIO()
        with mock.patch.object(safari_yarn_lock, "ROOT", self.repository), \
                mock.patch.object(sys, "argv", ["safari_yarn_lock.py", "--candidate-sha",
                                                self.candidate, "--input-context",
                                                str(self.raw_context), "--output", str(context),
                                                "--capture-context"]), \
                redirect_stdout(output):
            self.assertEqual(1, safari_yarn_lock.main())
        self.assertEqual("CONTEXT_INCOMPLETE", json.loads(output.getvalue())["status"])
        self.assert_context_upload_bound(context)

    def test_context_scanner_caps_aggregate_uploaded_bytes(self):
        context, package = self.context_fixture()
        (package / "karma.conf.js").write_text("config\n")
        (self.raw_context / "process-after.txt").write_bytes(b"P" * 614_400)
        with mock.patch.object(safari_yarn_lock, "CONTEXT_MAX_UPLOAD_BYTES",
                               safari_yarn_lock.CONTEXT_MAX_INVENTORY_BYTES + 100):
            inventory = self.capture_context(context)
            self.assert_context_upload_bound(context)
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        self.assertTrue(any(item["reason"] == "upload_byte_limit"
                            for item in inventory["inputs"]))

    def test_context_scanner_rejects_symlink_host_snapshot(self):
        context, package = self.context_fixture()
        (package / "karma.conf.js").write_text("config\n")
        outside = self.root / "outside.txt"
        outside.write_text("outside\n")
        (self.raw_context / "session-after.txt").unlink()
        (self.raw_context / "session-after.txt").symlink_to(outside)
        inventory = self.capture_context(context)
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        self.assertFalse((context / "session-after.txt").exists())
        self.assertTrue(any(item["path"] == "session-after.txt"
                            and item["status"] == "failed"
                            for item in inventory["inputs"]))
        self.assert_context_upload_bound(context)

    def test_context_scanner_rejects_missing_or_unsafe_host_snapshot(self):
        context, package = self.context_fixture()
        (package / "karma.conf.js").write_text("config\n")
        (self.raw_context / "session-after.txt").unlink()
        inventory = self.capture_context(context)
        self.assertEqual("CONTEXT_INCOMPLETE", inventory["status"])
        self.assertTrue(any(item["path"] == "session-after.txt"
                            and item["status"] == "failed"
                            for item in inventory["inputs"]))

    def test_context_cli_reports_incomplete_with_nonzero_exit(self):
        context, package = self.context_fixture()
        (package / "karma.conf.js").write_text("config\n")
        (self.raw_context / "sample-state-123.txt").unlink()
        output = io.StringIO()
        with mock.patch.object(safari_yarn_lock, "ROOT", self.repository), \
                mock.patch.object(sys, "argv", ["safari_yarn_lock.py", "--candidate-sha",
                                                self.candidate, "--input-context",
                                                str(self.raw_context), "--output", str(context),
                                                "--capture-context"]), \
                redirect_stdout(output):
            result = safari_yarn_lock.main()
        self.assertEqual(1, result)
        self.assertEqual("CONTEXT_INCOMPLETE", json.loads(output.getvalue())["status"])
        self.assertFalse(json.loads((context / "inventory.json").read_text())["qualified"])

    def test_wrapper_joins_early_failed_launch_before_return(self):
        root = Path(__file__).resolve().parents[2]
        launcher = (root / "tools/qualification/safari-launch.sh").read_text()
        fake_open = self.root / "fake-open"
        fake_open.write_text("#!/bin/bash\nexit 23\n")
        fake_open.chmod(0o755)
        controlled = self.root / "controlled-launch.sh"
        controlled.write_text(launcher.replace("/usr/bin/open", str(fake_open))
                              .replace("/bin/sleep 2", "/bin/sleep 0.01"))
        redirect = self.root / "redirect.html"
        redirect.write_text("redirect\n")
        context = self.root / "launch-context"
        result = subprocess.run(["bash", str(controlled), str(redirect)],
                                env={**os.environ, "DYN4K_SAFARI_LAUNCH_CONTEXT": str(context)},
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(23, result.returncode)
        state = list(context.glob("sample-state-*.txt"))
        self.assertEqual(1, len(state))
        self.assertIn("samples_completed=5", state[0].read_text())
        self.assertIn("sampler_exit=0", state[0].read_text())
        process = list(context.glob("process-*.txt"))
        self.assertEqual(1, len(process))
        self.assertEqual(5, process[0].read_text().count("sample="))
        normal_environment = dict(os.environ)
        normal_environment.pop("DYN4K_SAFARI_LAUNCH_CONTEXT", None)
        normal = subprocess.run(["bash", str(controlled), str(redirect)],
                                env=normal_environment, capture_output=True,
                                text=True, timeout=5)
        self.assertEqual(23, normal.returncode)
        self.assertEqual(1, len(list(context.glob("sample-state-*.txt"))))

    def test_wrapper_records_pending_open_and_completed_samples(self):
        root = Path(__file__).resolve().parents[2]
        launcher = (root / "tools/qualification/safari-launch.sh").read_text()
        fake_open = self.root / "fake-open"
        fake_open.write_text("#!/bin/bash\nexec /bin/sleep 5\n")
        fake_open.chmod(0o755)
        controlled = self.root / "controlled-pending-launch.sh"
        controlled.write_text(launcher.replace("/usr/bin/open", str(fake_open))
                              .replace("/bin/sleep 2", "/bin/sleep 0.01"))
        redirect = self.root / "redirect.html"
        redirect.write_text("redirect\n")
        context = self.root / "pending-launch-context"
        process = subprocess.Popen(["bash", str(controlled), str(redirect)],
                                   env={**os.environ, "DYN4K_SAFARI_LAUNCH_CONTEXT":
                                        str(context)}, start_new_session=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not list(context.glob("sample-state-*.txt")):
                time.sleep(0.01)
            state = list(context.glob("sample-state-*.txt"))
            outcome = list(context.glob("launch-outcome-*.txt"))
            self.assertEqual(1, len(state))
            self.assertIn("samples_completed=5", state[0].read_text())
            self.assertEqual(1, len(outcome))
            self.assertEqual("open_state=pending\n", outcome[0].read_text())
        finally:
            os.killpg(process.pid, signal.SIGTERM)
            process.communicate(timeout=3)


if __name__ == "__main__":
    unittest.main()
