import os
import hashlib
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
import numeric_class_witness
from actual_arithmetic import CaptureRejected


class CaptureSourceGuardTest(unittest.TestCase):
    def test_focused_child_environment_excludes_inherited_options_and_secrets(self):
        owned_tmp = os.environ["TMPDIR"]
        seed = {"TMPDIR": owned_tmp, "HOME": "", "CODEX_HOME": "",
                "OLLAMA_API_KEY": "fake-test-secret", "FAKE_SECRET": "fake-test-secret",
                "JAVA_TOOL_OPTIONS": "-Dfake.secret=fake-test-secret",
                "GRADLE_OPTS": "-Dfake.secret=fake-test-secret",
                "HTTPS_PROXY": "http://fake.invalid"}
        with patch.dict(os.environ, seed, clear=True):
            focused = capture_actual.child_environment(focused=True)
            legacy = capture_actual.child_environment()
        self.assertEqual(focused["HOME"], "")
        self.assertEqual(focused["CODEX_HOME"], "")
        self.assertEqual(focused["TMPDIR"], owned_tmp)
        self.assertEqual(focused["JAVA_HOME"], str(capture_actual.JDK21))
        self.assertEqual(focused["ANDROID_HOME"], "/var/home/stewart/Android/Sdk")
        self.assertTrue(focused["GRADLE_USER_HOME"].endswith("/.gradle"))
        self.assertEqual(focused["DYN4K_CAPTURE_ENV_SENTINEL"],
                         "portable-capture-check")
        self.assertTrue(focused["PATH"].startswith(str(capture_actual.JDK21 / "bin")))
        self.assertIn("/Cellar/strace/7.2/bin", focused["PATH"])
        for name in ("OLLAMA_API_KEY", "FAKE_SECRET", "JAVA_TOOL_OPTIONS",
                     "GRADLE_OPTS", "HTTPS_PROXY"):
            self.assertNotIn(name, focused)
        self.assertIn("FAKE_SECRET", legacy)
        self.assertNotIn("OLLAMA_API_KEY", legacy)
        with patch.dict(os.environ, {"TMPDIR": owned_tmp}, clear=True):
            absent = capture_actual.child_environment(focused=True)
        self.assertNotIn("HOME", absent)
        self.assertNotIn("CODEX_HOME", absent)

    def test_focused_compilers_receive_selected_environment(self):
        jdk = self.root / "jdk"
        (jdk / "bin").mkdir(parents=True)
        (jdk / "bin/javac").write_bytes(b"compiler")
        environment = capture_actual.child_environment(focused=True)
        environment["JAVA_HOME"] = str(jdk)
        environment.pop("OLLAMA_API_KEY", None)
        calls = []

        def compiled(command, **kwargs):
            calls.append(kwargs["env"])
            classes = Path(command[command.index("-d") + 1])
            if "--release" in command:
                output = classes / "dyn4k/witness/NumericClassWitness.class"
                output.parent.mkdir(parents=True)
            else:
                output = classes / "RotationJdiProbe.class"
            output.write_bytes(b"compiled")
            return SimpleNamespace(returncode=0)

        with patch.object(numeric_class_witness.subprocess, "run",
                          side_effect=compiled):
            numeric_class_witness.build_agent(b"class NumericClassWitness {}", jdk,
                self.root / "agent.jar", self.root / "agent-compile",
                environment=environment)
        with patch.object(capture_actual.jdi_bridge, "_require_jdk21_javac"), \
                patch.object(capture_actual.jdi_bridge.subprocess, "run",
                             side_effect=compiled):
            capture_actual.jdi_bridge.compile_helper(
                b"class RotationJdiProbe {}", self.root,
                environment=environment, jdk_home=jdk)
        self.assertEqual(len(calls), 2)
        for selected in calls:
            self.assertEqual(selected, environment)
            self.assertNotIn("OLLAMA_API_KEY", selected)

    def test_small_gradle_launch_uses_capture_argument_constructor(self):
        command = capture_actual.gradle_test_command(
            ["strace", *capture_actual.trace_syscalls(
                "captureRevoluteLimitsFalse", version6=True), "-o", "trace"],
            "portable.RotationCaptureConcurrencyTest",
            "engineExposesNoMutableDiagnosticListener", "class-load-%p.log")
        self.assertEqual(command[0], "strace")
        self.assertIn("--tests", command)
        self.assertIn("portable.RotationCaptureConcurrencyTest."
                      "engineExposesNoMutableDiagnosticListener", command)
        self.assertIn("--offline", command)
        self.assertNotIn("-PportableBooleanJdiPort=None", command)

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

    def test_clean_source_requires_explicit_boolean_focus(self):
        with self.assertRaises(TypeError):
            capture_actual.clean_source()
        with self.assertRaises(CaptureRejected):
            capture_actual.clean_source(focused=None)

    def test_focused_initial_and_final_source_checks_select_git_environment(self):
        expected = capture_actual.git("--no-replace-objects", "rev-parse", "HEAD",
                                      focused=True).decode().strip()
        real_run = subprocess.run
        observed = []

        def run(command, *args, **kwargs):
            if command[0] == "git":
                observed.append(dict(kwargs["env"]))
            return real_run(command, *args, **kwargs)

        synthetic = {"FAKE_CREDENTIAL": "synthetic-test-value",
                     "JAVA_TOOL_OPTIONS": "-Dfake.option=synthetic-test-value",
                     "HTTPS_PROXY": "http://synthetic.invalid"}
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory, \
                patch.dict(os.environ, synthetic), \
                patch.object(capture_actual.subprocess, "run", side_effect=run):
            output = Path(directory) / "focused"
            with patch.object(capture_actual, "_run_capture", return_value="bounded"):
                self.assertEqual(capture_actual.run_capture(
                    "captureRevoluteLimitsFalse", output,
                    self.root / "reference.jsonl"), "bounded")
            capture_actual._require_source_unchanged(expected, focused=True)
            with self.assertRaisesRegex(CaptureRejected, "source changed"):
                capture_actual._require_source_unchanged("0" * 40, focused=True)
            self.assertEqual(len(observed), 9)
            for child in observed:
                self.assertEqual(child["TMPDIR"], os.environ["TMPDIR"])
                self.assertNotIn("FAKE_CREDENTIAL", child)
                self.assertNotIn("JAVA_TOOL_OPTIONS", child)
                self.assertNotIn("HTTPS_PROXY", child)
            observed.clear()
            self.assertEqual(capture_actual.clean_source(focused=False), expected)
            self.assertEqual(len(observed), 3)
            self.assertTrue(all("FAKE_CREDENTIAL" in child and
                                "JAVA_TOOL_OPTIONS" in child for child in observed))

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
                                      "output-observer-traces.zip",
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

    def test_rejected_trace_moves_to_private_counted_root(self):
        output = self.root / "eligible"
        scratch = self.root / "scratch"
        private = self.root / "private"
        for root in (output, scratch, private):
            root.mkdir()
        raw = b'1.000 read(4, "DYN4K_CAPTURE_ENV_SENTINEL=portable-capture-check", 55) = 55\n'
        trace = scratch / "worker-write-trace.42"
        trace.write_bytes(raw)
        budget = capture_actual.CaptureBudget(output, scratch, (),
                                             private=private, limit_bytes=len(raw) + 1)
        with self.assertRaisesRegex(CaptureRejected, "exposed the environment"):
            capture_actual.private_trace_or_reject(trace, private, budget, "worker")
        retained = private / trace.name
        self.assertFalse(trace.exists())
        self.assertEqual(retained.read_bytes(), raw)
        self.assertEqual(retained.stat().st_mode & 0o777, 0o600)
        self.assertEqual(hashlib.sha256(retained.read_bytes()).hexdigest(),
                         hashlib.sha256(raw).hexdigest())
        self.assertEqual(budget.check(), len(raw))
        self.assertFalse(any(output.iterdir()))
        (private / "extra").write_bytes(b"x")
        with self.assertRaisesRegex(CaptureRejected, "budget"):
            budget.check()

    def test_forbidden_key_name_is_retained_only_in_private_diagnostic(self):
        private = self.root / "private"
        private.mkdir(mode=0o700)
        private.chmod(0o700)
        trace = self.root / "jdi-helper-trace.42"
        trace.write_bytes(b'read(4, "OLLAMA_API_KEY", 14) = 14\n')
        with self.assertRaisesRegex(CaptureRejected, "JDI helper trace exposed"):
            capture_actual.private_trace_or_reject(trace, private, None,
                                                   "JDI helper")
        self.assertFalse(trace.exists())
        self.assertEqual((private / trace.name).stat().st_mode & 0o777, 0o600)

    def test_escaped_private_trace_is_rejected_and_counted(self):
        private = self.root / "private"
        private.mkdir(mode=0o700)
        trace = self.root / "worker-write-trace.42"
        raw = (b'1.000001 write(4, "DYN4K_CAPTURE_ENV_SENTINEL\\x3dportable-capture-check", 55) = 55\n')
        trace.write_bytes(raw)
        budget = capture_actual.CaptureBudget(self.root / "eligible", self.root,
                                             (), private=private)
        with self.assertRaisesRegex(CaptureRejected, "exposed the environment"):
            capture_actual.private_trace_or_reject(trace, private, budget, "worker")
        self.assertEqual((private / trace.name).read_bytes(), raw)
        self.assertEqual((private / trace.name).stat().st_mode & 0o777, 0o600)

    def test_private_trace_rejection_preserves_error_on_move_failure(self):
        scratch = self.root / "scratch"
        private = self.root / "private"
        scratch.mkdir()
        private.mkdir()
        trace = scratch / "worker-write-trace.42"
        trace.write_bytes(capture_actual.ENVIRONMENT_SENTINEL.encode())
        with patch.object(capture_actual.os, "replace", side_effect=OSError("move failed")):
            with self.assertRaisesRegex(CaptureRejected, "exposed the environment"):
                capture_actual.private_trace_or_reject(trace, private, None, "worker")
        self.assertTrue(trace.exists())

    def test_focused_capture_keeps_rejected_bytes_outside_archive(self):
        output = self.root / "focused"
        payload = capture_actual.ENVIRONMENT_SENTINEL.encode()

        def reject(method, eligible, reference, commit, temporary, budget, active, private):
            eligible.mkdir()
            trace = temporary / "worker-write-trace.42"
            trace.write_bytes(payload)
            budget.check()
            capture_actual.private_trace_or_reject(trace, private, budget, "worker write")

        with patch.object(capture_actual, "clean_source", return_value="reviewed"), \
                patch.object(capture_actual, "_run_capture", side_effect=reject), \
                patch.dict(os.environ, {"TMPDIR": os.environ["TMPDIR"]}):
            with self.assertRaisesRegex(CaptureRejected, "exposed the environment"):
                capture_actual.run_capture("captureRevoluteLimitsFalse", output,
                                           self.root / "reference.jsonl")
        private = self.root / "focused.private-unverified"
        self.assertEqual((private / "worker-write-trace.42").read_bytes(), payload)
        self.assertEqual((private / "UNVERIFIED.json").stat().st_mode & 0o777,
                         0o600)
        self.assertEqual(private.stat().st_mode & 0o777, 0o700)
        self.assertFalse(any(output.iterdir()))
        self.assertFalse(any(self.root.glob("dyn4k-actual-*")))

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
            capture_actual.clean_source(focused=False)

    def test_only_exact_generated_roots_are_exempt(self):
        for relative in ("build/cache/generated.bin", ".gradle/cache/state.bin",
                         "dyn4k-core/build/classes/Generated.class",
                         "tools/numerical/portable/build/classes/Generated.class",
                         "tools/numerical/portable/__pycache__/cases.pyc"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"generated")
        self.assertEqual(capture_actual.clean_source(focused=False),
                         capture_actual.git("rev-parse", "HEAD").decode().strip())

    def test_ignored_kotlin_under_source_build_is_rejected(self):
        self.assertEqual(capture_actual.clean_source(focused=False),
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
                capture_actual.clean_source(focused=False)
            path.unlink()
            self.assertEqual(capture_actual.clean_source(focused=False),
                             capture_actual.git("rev-parse", "HEAD").decode().strip())


if __name__ == "__main__":
    unittest.main()
