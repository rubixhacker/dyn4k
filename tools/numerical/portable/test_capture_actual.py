import os
import signal
import subprocess
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import capture_actual
import baseline_capture
from actual_arithmetic import CaptureRejected


class CaptureSourceGuardTest(unittest.TestCase):
    def test_jvm_fixture_preserves_approved_baseline_source(self):
        self.assertEqual(baseline_capture.fixture_source_sha256(),
                         "dd104a7e018b9d0bd77c9af14e929699d68f29fa4ac8179a5bd7d98bdc87d9ce")

    def test_rotation_fixture_requires_sealed_worker_writes(self):
        names = capture_actual.archive_file_names(
            "captureRotationPremises", "worker-class-load-42.log")
        self.assertIn("worker-write-traces.zip", names)
        self.assertNotIn("focused-assessment.json", names)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR", str(Path.home())))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        subprocess.run(("git", "init", "-q"), cwd=self.root, check=True)
        (self.root / ".gitignore").write_text(
            "**/build/\n.gradle/\n.kotlin/\n__pycache__/\n"
            "kotlin-js-store/\n*.ignored.kt\n")
        source = self.root / "tools/numerical/portable/src/commonTest/kotlin/portable"
        source.mkdir(parents=True)
        (source / "Tracked.kt").write_text("package portable\n")
        subprocess.run(("git", "add", "."), cwd=self.root, check=True)
        subprocess.run(("git", "-c", "user.name=Capture Test", "-c",
                        "user.email=capture-test@example.invalid", "commit", "-qm",
                        "fixture"), cwd=self.root, check=True)
        root = patch.object(capture_actual, "ROOT", self.root)
        root.start()
        self.addCleanup(root.stop)

    def test_capture_writes_canonical_source_before_failed_stage(self):
        subprocess.run(("git", "-C", str(self.root), "config", "core.autocrlf", "true"),
                       check=True)
        converted = capture_actual.git("archive", "--format=tar", "HEAD")
        canonical = capture_actual.git("-c", "core.autocrlf=false", "archive",
                                       "--format=tar", "HEAD")
        self.assertNotEqual(converted, canonical)
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR", str(Path.home())))
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "capture"
        jdk = Path(temporary.name) / "jdk"
        (jdk / "bin").mkdir(parents=True)
        (jdk / "bin/java").write_bytes(b"test executable")
        real_run = subprocess.run

        def stop_before_execution(command, *args, **kwargs):
            if command[0] == "git":
                return real_run(command, *args, **kwargs)
            return SimpleNamespace(returncode=1)

        with patch.object(capture_actual, "JDK21", jdk), \
                patch.object(capture_actual, "expected_case_ids", return_value={"method": []}), \
                patch.object(capture_actual.subprocess, "run", side_effect=stop_before_execution):
            with self.assertRaisesRegex(CaptureRejected, "publication failed"):
                capture_actual.run_capture("method", output)
        self.assertEqual((output / "source.tar").read_bytes(), canonical)
        self.assertFalse((output / "receipt.json").exists())

    def test_boolean_selector_reaches_clean_source_guard(self):
        method = "captureRevoluteLimitsFalse"
        self.assertEqual(capture_actual.capture_case_ids()[method],
                         ["joint-Revolute-LimitsEnabled-false"])
        self.assertEqual(capture_actual.target_test_class(method),
                         "portable.RevoluteLimitsFalseCaptureTest")
        self.assertEqual(capture_actual.target_test_class("captureWheelActive"),
                         "portable.ProspectiveArithmeticTest")
        self.assertEqual(capture_actual.target_test_class("captureRotationPremises"),
                         "portable.RotationPremiseFixtureTest")
        self.assertEqual(len(capture_actual.capture_case_ids()), 18)
        with patch.object(capture_actual, "clean_source",
                          side_effect=CaptureRejected("selected source guard")):
            with self.assertRaisesRegex(CaptureRejected, "selected source guard"):
                capture_actual.run_capture(method, self.root / "capture",
                                           self.root / "reference.jsonl")

    def test_boolean_execveat_trace_command_and_process_lines(self):
        method = "captureRevoluteLimitsFalse"
        self.assertEqual(
            capture_actual.trace_syscalls(method),
            "trace=execve,execveat,clone,clone3,bind,listen,write,writev,sendto,sendmsg")
        self.assertEqual(
            capture_actual.trace_syscalls(method, helper=True),
            "trace=execve,execveat,clone,clone3,connect,openat,write,writev,close")
        self.assertEqual(
            capture_actual.trace_syscalls("captureWheelActive"),
            "trace=execve,clone,clone3,write,writev,sendto,sendmsg")
        self.assertEqual(capture_actual.trace_syscalls("captureGeometry"),
                         "trace=execve")
        records = (b'execve("/jdk/java", ["java"], 0x0) = 0\n'
                   b'execveat(AT_FDCWD, "/jdk/java", ["java"], 0x0, 0) = -1 ENOENT\n'
                   b'clone3({flags=CLONE_THREAD}, 88) = 124\n')
        expected = [f"123 {line.decode()}" for line in records.splitlines()[:2]]
        self.assertEqual(capture_actual.executed_process_lines(
            "123", records, method), expected)
        self.assertEqual(capture_actual.executed_process_lines(
            "123", records, "captureWheelActive"), expected[:1])

    def test_boolean_archive_inventory_excludes_nonworker_argument_logs(self):
        output = self.root / "archive"
        output.mkdir()
        method = "captureRevoluteLimitsFalse"
        class_log = output / "worker-class-load-123.log"
        argument_log = output / "worker-arguments-123.log"
        names = capture_actual.archive_file_names(method, class_log, argument_log)
        self.assertTrue({"jdi-helper-classes.zip", "jdi-evidence.zip",
                         "jdi-helper-traces.zip", "jdi-transport.json"} <= names)
        v6 = capture_actual.archive_file_names(method, class_log, argument_log,
                                               version6=True)
        self.assertEqual(v6 - names, {"class-witness-agent.jar", "class-witness.log",
                                      "mirror.log", "all-process-traces.zip",
                                      "capture-metadata.json", "jdi-helper-arguments.log"})
        archive_names = {"worker-write-traces.zip", "jdi-helper-classes.zip",
                         "jdi-evidence.zip", "jdi-helper-traces.zip"}
        for name in names - archive_names:
            (output / name).write_bytes(b"sealed")
        for name in archive_names:
            with zipfile.ZipFile(output / name, "w") as archive:
                archive.writestr("trace.123", b"safe\n")
        capture_actual.verify_archive_inventory(output, method,
                                                class_log, argument_log)
        (output / "worker-arguments-999.log").write_bytes(b"unvetted")
        with self.assertRaisesRegex(CaptureRejected, "archive inventory"):
            capture_actual.verify_archive_inventory(output, method,
                                                    class_log, argument_log)

    def test_boolean_jdwp_option_and_live_socket_owner(self):
        self.assertEqual(capture_actual.boolean_jdwp_option(40001),
                         "-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,"
                         "address=127.0.0.1:40001")
        for port in (0, 65536, True, "40001"):
            with self.assertRaises(CaptureRejected):
                capture_actual.boolean_jdwp_option(port)
        proc = self.root / "proc"
        (proc / "net").mkdir(parents=True)
        (proc / "net/tcp").write_text(
            "sl  local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n"
            "0: 0100007F:9C41 00000000:0000 0A 0 0 0 0 0 77123\n")
        (proc / "123/fd").mkdir(parents=True)
        (proc / "123/fd/9").symlink_to("socket:[77123]")
        self.assertTrue(capture_actual.socket_owner(proc, 123, 40001))
        self.assertFalse(capture_actual.socket_owner(proc, 123, 40002))
        self.assertFalse(capture_actual.socket_owner(proc, 124, 40001))

    def test_boolean_budget_counts_generated_output_and_expires(self):
        generated = self.root / "build"
        generated.mkdir()
        (generated / "old.bin").write_bytes(b"a" * 100)
        output = self.root / "capture"
        output.mkdir()
        temporary = self.root / "temporary"
        temporary.mkdir()
        budget = capture_actual.CaptureBudget(
            output, temporary, (generated,), limit_bytes=10, seconds=2)
        budget.check()
        (generated / "new.bin").write_bytes(b"a" * 11)
        with self.assertRaisesRegex(CaptureRejected, "budget"):
            budget.check()
        (generated / "new.bin").unlink()
        with self.assertRaisesRegex(CaptureRejected, "budget"):
            budget.check(extra_bytes=10)
        with patch.object(capture_actual.time, "monotonic", return_value=budget.deadline + 1):
            with self.assertRaisesRegex(CaptureRejected, "timed out"):
                budget.check()

    def test_bounded_stage_stops_process_on_budget_failure(self):
        budget = SimpleNamespace(check=lambda: (_ for _ in ()).throw(
            CaptureRejected("bounded budget")))
        process = SimpleNamespace(poll=lambda: None)
        active = []
        with patch.object(capture_actual.subprocess, "Popen", return_value=process), \
                patch.object(capture_actual, "stop_capture_process") as stop:
            with self.assertRaisesRegex(CaptureRejected, "budget"):
                capture_actual.run_bounded_process(
                    ["tool"], self.root, {}, self.root / "stage.log", budget, active)
        self.assertEqual(active, [])
        stop.assert_called_once_with(process)

    def test_completed_stage_reaps_group_before_later_sealing(self):
        budget = SimpleNamespace(check=lambda: None)
        process = SimpleNamespace(poll=lambda: 0, returncode=0)
        active = []
        with patch.object(capture_actual.subprocess, "Popen", return_value=process), \
                patch.object(capture_actual, "stop_capture_process") as stop:
            status = capture_actual.run_bounded_process(
                ["tool"], self.root, {}, self.root / "stage.log", budget, active)
        self.assertEqual(status, 0)
        self.assertEqual(active, [])
        stop.assert_called_once_with(process)

    def test_watchdog_interrupts_blocked_sealing_and_restores_handler(self):
        prior = signal.getsignal(signal.SIGALRM)
        started = time.monotonic()
        with self.assertRaisesRegex(CaptureRejected, "timed out"):
            with capture_actual.capture_watchdog(0.02):
                time.sleep(1)
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(signal.getsignal(signal.SIGALRM), prior)

    def test_selected_jdi_worker_needs_one_successful_exec(self):
        prefix = self.root / "worker-trace"
        (self.root / "worker-trace.12").write_text(
            'execve("/tmp/dyn4k-tools/jdk21/bin/java", '
            '["java", "GradleWorkerMain"], 0x0) = 0\n')
        self.assertEqual(capture_actual.selected_worker_pid(prefix), 12)
        (self.root / "worker-trace.13").write_text(
            'execve("/tmp/dyn4k-tools/jdk21/bin/java", '
            '["java", "GradleWorkerMain"], 0x0) = 0\n')
        with self.assertRaisesRegex(CaptureRejected, "ambiguous"):
            capture_actual.selected_worker_pid(prefix)
        (self.root / "worker-trace.13").write_text("unrelated\n")
        (self.root / "worker-trace.12").write_text(
            'execve("/tmp/dyn4k-tools/jdk21/bin/java", '
            '["java", "GradleWorkerMain"], 0x0) = -1\n')
        self.assertIsNone(capture_actual.selected_worker_pid(prefix))

    def test_capture_source_tar_ignores_same_type_commit_replacement(self):
        original = capture_actual.git("rev-parse", "HEAD").decode().strip()
        source = self.root / "tools/numerical/portable/src/commonTest/kotlin/portable/Tracked.kt"
        source.write_text("package portable\nclass Substitute\n")
        subprocess.run(("git", "add", "."), cwd=self.root, check=True)
        subprocess.run(("git", "-c", "user.name=Capture Test", "-c",
                        "user.email=capture-test@example.invalid", "commit", "-qm",
                        "substitute"), cwd=self.root, check=True)
        substitute = capture_actual.git("rev-parse", "HEAD").decode().strip()
        subprocess.run(("git", "checkout", "-q", original), cwd=self.root, check=True)
        subprocess.run(("git", "replace", original, substitute), cwd=self.root, check=True)
        canonical = capture_actual.git("--no-replace-objects", "-c",
                                       "core.autocrlf=false", "archive", "--format=tar",
                                       original)
        substituted = capture_actual.git("-c", "core.autocrlf=false", "archive",
                                         "--format=tar", original)
        self.assertNotEqual(canonical, substituted)
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR", str(Path.home())))
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "capture"
        jdk = Path(temporary.name) / "jdk"
        (jdk / "bin").mkdir(parents=True)
        (jdk / "bin/java").write_bytes(b"test executable")
        real_run = subprocess.run

        def stop_before_execution(command, *args, **kwargs):
            if command[0] == "git":
                return real_run(command, *args, **kwargs)
            return SimpleNamespace(returncode=1)

        with patch.object(capture_actual, "JDK21", jdk), \
                patch.object(capture_actual, "expected_case_ids", return_value={"method": []}), \
                patch.object(capture_actual.subprocess, "run", side_effect=stop_before_execution):
            with self.assertRaisesRegex(CaptureRejected, "publication failed"):
                capture_actual.run_capture("method", output)
        self.assertEqual((output / "source.tar").read_bytes(), canonical)
        self.assertFalse((output / "receipt.json").exists())
        source.write_text("package portable\nclass Substitute\n")
        subprocess.run(("git", "add", "."), cwd=self.root, check=True)
        self.assertEqual(capture_actual.git("status", "--porcelain"), b"")
        with self.assertRaisesRegex(CaptureRejected, "target source is not clean"):
            capture_actual.clean_source()

    def test_only_exact_generated_roots_are_exempt(self):
        for relative in ("build/cache/generated.bin", ".gradle/cache/state.bin",
                         "dyn4k-core/build/classes/Generated.class",
                         "tools/numerical/portable/build/classes/Generated.class",
                         "tools/numerical/portable/__pycache__/cases.pyc"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"generated")
        self.assertEqual(capture_actual.clean_source(),
                         capture_actual.git("rev-parse", "HEAD").decode().strip())

    def test_ignored_kotlin_under_source_build_is_rejected(self):
        self.assertEqual(capture_actual.clean_source(),
                         capture_actual.git("rev-parse", "HEAD").decode().strip())
        for relative in ("tools/numerical/portable/src/commonTest/kotlin/portable/"
                         "build/Injected.kt",
                         "tools/numerical/portable/src/commonMain/kotlin/"
                         "build/generated/Shadow.kt",
                         "tools/numerical/portable/src/commonTest/kotlin/portable/"
                         "Injected.ignored.kt"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("package portable\nclass Injected\n")
            self.assertEqual(capture_actual.git("status", "--porcelain",
                                                "--untracked-files=all"), b"")
            with self.subTest(relative=relative), self.assertRaises(CaptureRejected):
                capture_actual.clean_source()
            path.unlink()
            self.assertEqual(capture_actual.clean_source(),
                             capture_actual.git("rev-parse", "HEAD").decode().strip())


if __name__ == "__main__":
    unittest.main()
