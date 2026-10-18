import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import safari_yarn_lock


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
        (self.repository / "build.gradle.kts").write_text("plugins {}\n")
        (self.repository / "settings.gradle.kts").write_text('rootProject.name = "dyn4k"\n')
        (self.repository / "gradle/wrapper").mkdir(parents=True)
        (self.repository / "gradle/wrapper/gradle-wrapper.properties").write_text(
            "distributionUrl=gradle-9.5-bin.zip\n")
        subprocess.run(["git", "init", "-q", str(self.repository)], check=True)
        subprocess.run(["git", "-C", str(self.repository), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repository), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"],
                       check=True)
        self.candidate = subprocess.check_output(
            ["git", "-C", str(self.repository), "rev-parse", "HEAD"], text=True).strip()
        self.output = self.root / "capture"

    def generated(self, data=b"host generated lock\n"):
        path = self.repository / "build/js/yarn.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        package = path.parent / "package.json"
        package.write_text('{"name":"root"}\n')
        module = path.parent / "packages/dyn4k-dyn4k-core-test/package.json"
        module.parent.mkdir(parents=True)
        module.write_text('{"name":"test"}\n')

    def test_failed_lock_task_captures_exact_different_bytes_and_inputs(self):
        def failure(*args):
            self.generated()
            (self.output / "stderr.txt").write_text(
                "Lock file was changed. Run the `kotlinUpgradeYarnLock` task\n")
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
        self.assertEqual('{"name":"test"}\n',
                         (self.output / "generated/build/js/packages/dyn4k-dyn4k-core-test/package.json").read_text())
        self.assertNotEqual(receipt["tracked_sha256"], receipt["generated_sha256"])
        self.assertEqual(self.candidate, json.loads((self.output / "receipt.json").read_text())
                         ["candidate_sha"])

    def test_other_gradle_failure_cannot_be_called_a_lock_mismatch(self):
        def failure(*args):
            self.generated()
            (self.output / "stderr.txt").write_text("Task failed for another reason\n")
            return {"command": ["./gradlew", ":kotlinStoreYarnLock"],
                    "pid": 123, "exit_code": 1, "started_ns": 1,
                    "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=failure):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate, self.output)
        self.assertEqual("OTHER_GRADLE_RESULT", receipt["status"])

    def test_missing_generated_lock_is_explicitly_incomplete(self):
        with mock.patch.object(safari_yarn_lock, "run_lock_task", return_value={
                "command": ["./gradlew", ":kotlinStoreYarnLock"], "pid": 123,
                "exit_code": 1, "started_ns": 1, "finished_ns": 2}):
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
            return {"command": ["./gradlew", ":kotlinStoreYarnLock"], "pid": 123,
                    "exit_code": 0, "started_ns": 1, "finished_ns": 2}

        with mock.patch.object(safari_yarn_lock, "run_lock_task", side_effect=success):
            receipt = safari_yarn_lock.capture(self.repository, self.candidate, self.output)
        self.assertEqual("LOCK_MATCHED_DIAGNOSTIC_ONLY", receipt["status"])
        self.assertFalse(receipt["qualified"])

    def test_lock_task_keeps_gradle_mismatch_enforcement(self):
        process = mock.Mock()
        process.pid = 123
        process.returncode = 1
        process.communicate.return_value = (b":kotlinStoreYarnLock FAILED\n",
                                             b"Lock file was changed\n")
        self.output.mkdir()
        with mock.patch.object(safari_yarn_lock.subprocess, "Popen", return_value=process) as popen:
            result = safari_yarn_lock.run_lock_task(self.repository, self.output)
        command = popen.call_args.args[0]
        self.assertEqual([str(self.repository / "gradlew"), "--no-daemon",
                          "--console=plain", "--rerun-tasks", ":kotlinStoreYarnLock"],
                         command)
        self.assertNotIn("kotlinUpgradeYarnLock", command)
        self.assertEqual(1, result["exit_code"])
        self.assertEqual(b"Lock file was changed\n",
                         (self.output / "stderr.txt").read_bytes())

    def test_manual_workflow_has_separate_mac_route_and_uploads_failed_capture(self):
        workflow = (Path(__file__).resolve().parents[2] /
                    ".github/workflows/safari-yarn-lock-diagnostic.yml").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("runs-on: macos-26", workflow)
        self.assertIn("java-version: '21'", workflow)
        self.assertIn("ref: ${{ inputs.candidate_sha }}", workflow)
        self.assertIn("if: always()", workflow)
        self.assertIn("tools/qualification/safari_yarn_lock.py", workflow)
        self.assertNotIn("kotlinUpgradeYarnLock", workflow)
        self.assertNotIn("yarnLockMismatchReport", workflow)


if __name__ == "__main__":
    unittest.main()
