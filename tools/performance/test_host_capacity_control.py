import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import yaml

import host_capacity_control as control


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/performance-host-capacity-control.yml"
WORKFLOW_SHA256 = "1bf19a013aa4849e174e379d7bf808b419841fdfd0b670dcd34639ac080e22a6"


def digest(data):
    return hashlib.sha256(data).hexdigest()


class HostCapacityControlTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path.home())
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.archive = self.root / "archive"
        self.archive.mkdir()
        self.key = b"test-only-host-capacity-key-32-bytes-long"
        self.key_path = self.root / "operator.key"
        self.key_path.write_bytes(self.key)
        ready = b'{"ready_pid": 42, "touched_bytes": 16777216}\n'
        (self.archive / "stdout.raw").write_bytes(ready)
        (self.archive / "stderr.raw").write_bytes(b"")
        (self.archive / "child.py").write_bytes(control.CHILD_SOURCE.encode())
        (self.archive / "executable.bin").write_bytes(b"test executable bytes")
        (self.archive / "tool-executed.py").write_bytes(Path(control.__file__).read_bytes())
        (self.archive / "ready.pid").write_bytes(b"42")
        self.commit = "f27d6afbd88e1c99fbc663b4eb771058b802ac65"
        runtime_sha = digest((self.archive / "executable.bin").read_bytes())
        self.record = {
            "version": 1, "qualification": "unpassed", "status": "observed",
            "error": None, "source_commit": self.commit,
            "tool_sha256": digest(Path(control.__file__).read_bytes()),
            "tool_working_sha256": digest(Path(control.__file__).read_bytes()),
            "tool_encoding": "git_exact",
            "host_system": "Windows", "host_machine": "AMD64", "host_release": "2025",
            "workflow_run_id": "123", "workflow_attempt": "1",
            "pid": 42, "started_ns": 100, "image_observed_ns": 110,
            "image_method": "windows_query_image", "image_path": "C:\\python.exe",
            "image_sha256": runtime_sha, "expected_runtime_sha256": runtime_sha,
            "sample_observed_ns": 120, "sample_bytes": 1000,
            "stop_requested_ns": 130, "stop_dispatched_ns": 131,
            "stop_method": "windows_terminate_process_v1", "stop_result": "os_success",
            "terminal_observed_ns": 140, "ended_ns": 150,
            "terminal_exit_code": 1, "terminal_wait_status": None,
            "terminal_peak_bytes": 2000, "terminal_metric_kind": "peak_working_set_bytes",
            "stdout_sha256": digest(ready), "stderr_sha256": digest(b""),
            "ready_sha256": digest(b"42"),
            "child_sha256": digest(control.CHILD_SOURCE.encode()),
            "executable_sha256": runtime_sha,
        }

    def seal(self, record):
        record = copy.deepcopy(record)
        record["signature"] = control.signature(record, self.key)
        (self.archive / "receipt.json").write_text(json.dumps(record, sort_keys=True) + "\n")

    def public_verify(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["host_capacity_control.py", "verify", "--archive",
                                      str(self.archive), "--trusted-key", str(self.key_path),
                                      "--expected-source-commit", self.commit]), \
             patch("host_capacity_control.source_at_commit",
                   return_value=Path(control.__file__).read_bytes()), \
             contextlib.redirect_stdout(output):
            try:
                control.main()
                code = 0
            except SystemExit as exc:
                code = exc.code
        return code, json.loads(output.getvalue())

    def replacement_fixture(self):
        repository = self.root / "replacement-repository"
        repository.mkdir()

        def git(*args):
            return subprocess.check_output(["git", "-C", str(repository), *args],
                                           stderr=subprocess.PIPE).strip().decode()

        git("init", "-q")
        git("config", "user.name", "Host capacity test")
        git("config", "user.email", "host-capacity@example.invalid")
        source = repository / control.SOURCE_PATH
        source.parent.mkdir(parents=True)
        original = Path(control.__file__).read_bytes()
        substituted = original + b"\n# same-type replacement fixture\n"
        source.write_bytes(original)
        git("add", control.SOURCE_PATH)
        git("commit", "-qm", "original")
        original_commit = git("rev-parse", "HEAD")
        original_blob = git("rev-parse", f"{original_commit}:{control.SOURCE_PATH}")
        source.write_bytes(substituted)
        git("commit", "-qam", "substituted")
        substituted_commit = git("rev-parse", "HEAD")
        substituted_blob = git("rev-parse", f"{substituted_commit}:{control.SOURCE_PATH}")
        git("checkout", "-q", original_commit)
        executed = self.root / "executed.py"
        executed.write_bytes(substituted)
        return repository, executed, original_commit, substituted_commit, original_blob, substituted_blob

    def test_public_replay_accepts_canonical_commit_without_replacement(self):
        repository, _, original_commit, _, _, _ = self.replacement_fixture()
        original = (repository / control.SOURCE_PATH).read_bytes()
        executed = self.root / "canonical-executed.py"
        executed.write_bytes(original)
        self.commit = original_commit
        record = copy.deepcopy(self.record)
        record.update(source_commit=original_commit, tool_sha256=digest(original),
                      tool_working_sha256=digest(original))
        self.seal(record)
        output = io.StringIO()
        with patch.object(control, "ROOT", repository), \
             patch.object(control, "__file__", str(executed)), \
             patch.object(sys, "argv", ["host_capacity_control.py", "verify",
                                       "--archive", str(self.archive),
                                       "--trusted-key", str(self.key_path),
                                       "--expected-source-commit", original_commit]), \
             contextlib.redirect_stdout(output):
            control.main()
        self.assertEqual({"diagnostic": "verified", "qualification": "unpassed",
                          "host_system": "Windows", "pid": 42,
                          "terminal_peak_bytes": 2000,
                          "terminal_metric_kind": "peak_working_set_bytes"},
                         json.loads(output.getvalue()))

    def test_public_replay_rejects_same_type_commit_and_blob_replacements(self):
        (repository, executed, original_commit, substituted_commit,
         original_blob, substituted_blob) = self.replacement_fixture()
        self.commit = original_commit
        substituted = executed.read_bytes()
        (self.archive / "tool-executed.py").write_bytes(substituted)
        record = copy.deepcopy(self.record)
        record.update(source_commit=original_commit, tool_sha256=digest(substituted),
                      tool_working_sha256=digest(substituted))
        self.seal(record)
        for original_oid, substitute_oid in ((original_commit, substituted_commit),
                                             (original_blob, substituted_blob)):
            with self.subTest(replaced=original_oid):
                subprocess.run(["git", "-C", str(repository), "replace", original_oid,
                                substitute_oid], check=True, stdout=subprocess.PIPE)
                self.assertEqual(substituted, subprocess.check_output(
                    ["git", "-C", str(repository), "show",
                     f"{original_commit}:{control.SOURCE_PATH}"]))
                output = io.StringIO()
                with patch.object(control, "ROOT", repository), \
                     patch.object(control, "__file__", str(executed)), \
                     patch.object(sys, "argv", ["host_capacity_control.py", "verify",
                                               "--archive", str(self.archive),
                                               "--trusted-key", str(self.key_path),
                                               "--expected-source-commit", original_commit]), \
                     contextlib.redirect_stdout(output):
                    with self.assertRaises(SystemExit) as exit_status:
                        control.main()
                self.assertEqual(1, exit_status.exception.code)
                self.assertEqual("unpassed", json.loads(output.getvalue())["qualification"])
                subprocess.run(["git", "-C", str(repository), "replace", "-d", original_oid],
                               check=True, stdout=subprocess.PIPE)

    def test_public_capture_rejects_replaced_commit_before_child_or_key_creation(self):
        repository, executed, original_commit, substituted_commit, _, _ = self.replacement_fixture()
        subprocess.run(["git", "-C", str(repository), "replace", original_commit,
                        substituted_commit], check=True, stdout=subprocess.PIPE)
        capture_archive = self.root / "replacement-capture"
        capture_key = self.root / "replacement-capture.key"
        output = io.StringIO()
        with patch.object(control, "ROOT", repository), \
             patch.object(control, "__file__", str(executed)), \
             patch.object(control.platform, "system", return_value="Darwin"), \
             patch.object(sys, "argv", ["host_capacity_control.py", "capture",
                                       "--archive", str(capture_archive),
                                       "--key-output", str(capture_key),
                                       "--expected-source-commit", original_commit]), \
             contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as exit_status:
                control.main()
        self.assertEqual(1, exit_status.exception.code)
        self.assertEqual("unpassed", json.loads(output.getvalue())["qualification"])
        self.assertFalse(capture_archive.exists())
        self.assertFalse(capture_key.exists())

    def public_capture_with_delayed_child(self, child_source):
        if sys.platform != "linux":
            self.skipTest("local process oracle requires Linux /proc and wait4")
        capture_archive = self.root / "capture"
        capture_key = self.root / "capture.key"
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                         cwd=control.ROOT, text=True).strip()
        source_bytes = Path(control.__file__).read_bytes()
        committed_bytes = control.source_at_commit(commit)
        source_check = (contextlib.nullcontext() if source_bytes == committed_bytes else
                        patch.object(control, "source_at_commit", return_value=source_bytes))

        def linux_image(pid):
            executable = os.readlink(f"/proc/{pid}/exe")
            return {"pid": pid, "observed_ns": time.monotonic_ns(),
                    "method": "macos_libproc", "executable_path": executable,
                    "sha256": control.sha256(executable)}

        stop_calls = []

        def simulated_terminal_stop(process, system, pid, handle):
            stop_calls.append(pid)
            marker = json.loads((capture_archive / "stdout.raw").read_text())
            if marker != {"ready_pid": pid, "touched_bytes": 16 * 1024 * 1024}:
                raise ValueError("stop before stdout readiness")
            requested = time.monotonic_ns()
            os.kill(pid, signal.SIGTERM)
            dispatched = time.monotonic_ns()
            observed_pid, status, usage = os.wait4(pid, 0)
            if observed_pid != pid:
                raise ValueError("wait4 child PID differs")
            process.returncode = os.waitstatus_to_exitcode(status)
            return {"stop_requested_ns": requested, "stop_dispatched_ns": dispatched,
                    "stop_method": "posix_sigterm_wait4_v1", "stop_result": "os_success",
                    "terminal_wait_status": status, "terminal_exit_code": process.returncode,
                    "terminal_peak_bytes": usage.ru_maxrss * 1024,
                    "terminal_observed_ns": time.monotonic_ns()}

        output = io.StringIO()
        with patch.object(control, "CHILD_SOURCE", child_source), \
             patch.object(control.platform, "system", return_value="Darwin"), \
             patch.object(control, "observe_process_image", side_effect=linux_image), \
             patch.object(control, "peak_rss_bytes", return_value=1), \
             patch.object(control, "capture_stop", side_effect=simulated_terminal_stop), \
             source_check, \
             patch.object(sys, "argv", ["host_capacity_control.py", "capture", "--archive",
                                       str(capture_archive), "--key-output", str(capture_key),
                                       "--expected-source-commit", commit]), \
             contextlib.redirect_stdout(output):
            try:
                control.main()
                code = 0
            except SystemExit as exc:
                code = exc.code
        receipt = json.loads((capture_archive / "receipt.json").read_text())
        self.assertEqual(control.signature(receipt, capture_key.read_bytes()),
                         receipt["signature"])
        with self.assertRaises(ProcessLookupError):
            os.kill(receipt["pid"], 0)
        return code, json.loads(output.getvalue()), receipt, stop_calls

    def test_public_capture_waits_for_complete_pid_and_flushed_stdout(self):
        ready_write = "Path(sys.argv[1]).write_text(str(os.getpid()))"
        delayed = control.CHILD_SOURCE.replace(
            ready_write, "Path(sys.argv[1]).touch()\ntime.sleep(0.15)\n" +
            "Path(sys.argv[1]).write_text(str(os.getpid())[:1])\ntime.sleep(0.15)\n" +
            ready_write + "\ntime.sleep(0.15)")
        code, result, receipt, stops = self.public_capture_with_delayed_child(delayed)
        self.assertEqual(0, code, result)
        self.assertEqual("observed", receipt["status"])
        self.assertEqual([receipt["pid"]], stops)
        self.assertEqual("unpassed", result["qualification"])

    def test_public_capture_waits_after_pid_write_for_stdout_flush(self):
        ready_write = "Path(sys.argv[1]).write_text(str(os.getpid()))"
        delayed = control.CHILD_SOURCE.replace(ready_write, ready_write + "\ntime.sleep(0.2)")
        code, result, receipt, stops = self.public_capture_with_delayed_child(delayed)
        self.assertEqual(0, code, result)
        self.assertEqual("observed", receipt["status"])
        self.assertEqual([receipt["pid"]], stops)

    def test_public_capture_rejects_genuine_wrong_pid_after_flushed_marker(self):
        delayed = control.CHILD_SOURCE.replace(
            "Path(sys.argv[1]).write_text(str(os.getpid()))",
            "Path(sys.argv[1]).touch()\ntime.sleep(0.15)\n" +
            "Path(sys.argv[1]).write_text(str(os.getpid() + 1))\ntime.sleep(0.15)")
        code, result, receipt, stops = self.public_capture_with_delayed_child(delayed)
        self.assertEqual(1, code)
        self.assertEqual("failed", receipt["status"])
        self.assertIn("ready PID differs", receipt["error"])
        self.assertEqual([], stops)
        self.assertEqual("unpassed", result["qualification"])

    def test_public_capture_rejects_wrong_stdout_marker_and_reaps_child(self):
        marker = 'print(json.dumps({"ready_pid": os.getpid(), "touched_bytes": len(data)}), flush=True)'
        wrong = control.CHILD_SOURCE.replace(marker, marker.replace("os.getpid()", "os.getpid() + 1"))
        code, result, receipt, stops = self.public_capture_with_delayed_child(wrong)
        self.assertEqual(1, code)
        self.assertEqual("failed", receipt["status"])
        self.assertIn("ready marker differs", receipt["error"])
        self.assertEqual([], stops)
        self.assertEqual("unpassed", result["qualification"])

    def test_public_replay_accepts_test_only_receipt_without_host_source_paths(self):
        self.seal(self.record)
        code, result = self.public_verify()
        self.assertEqual(0, code, result)
        self.assertEqual("verified", result["diagnostic"])
        self.assertEqual("unpassed", result["qualification"])

    def test_public_replay_accepts_mac_wait4_bytes_and_rejects_unit_mismatch(self):
        record = copy.deepcopy(self.record)
        record.update(host_system="Darwin", host_machine="arm64", host_release="26",
                      image_method="macos_libproc", image_path="/opt/python/bin/python3",
                      stop_method="posix_sigterm_wait4_v1", terminal_exit_code=-15,
                      terminal_wait_status=15, terminal_metric_kind="peak_rss_bytes")
        self.seal(record)
        code, result = self.public_verify()
        self.assertEqual(0, code, result)
        record["terminal_peak_bytes"] = 1
        self.seal(record)
        code, result = self.public_verify()
        self.assertNotEqual(0, code, result)
        self.assertEqual("unpassed", result["qualification"])

    def test_public_replay_accepts_archived_windows_crlf_source_projection(self):
        committed = Path(control.__file__).read_bytes()
        executed = committed.replace(b"\n", b"\r\n")
        (self.archive / "tool-executed.py").write_bytes(executed)
        record = copy.deepcopy(self.record)
        record["tool_working_sha256"] = digest(executed)
        record["tool_encoding"] = "git_crlf"
        self.seal(record)
        code, result = self.public_verify()
        self.assertEqual(0, code, result)
        (self.archive / "tool-executed.py").write_bytes(executed + b"print('injected')\r\n")
        record["tool_working_sha256"] = digest((self.archive / "tool-executed.py").read_bytes())
        self.seal(record)
        code, result = self.public_verify()
        self.assertNotEqual(0, code, result)
        mixed = committed.replace(b"\n", b"\r\n", 1)
        (self.archive / "tool-executed.py").write_bytes(mixed)
        record["tool_working_sha256"] = digest(mixed)
        self.seal(record)
        code, result = self.public_verify()
        self.assertNotEqual(0, code, result)

    def test_public_replay_rejects_signed_identity_counter_source_and_dispatch_attacks(self):
        attacks = {
            "wrong_pid": ("pid", 43),
            "wrong_image": ("image_sha256", "0" * 64),
            "wrong_counter": ("terminal_peak_bytes", 999),
            "wrong_source": ("source_commit", "0" * 40),
            "missing_dispatch": ("stop_result", None),
            "natural_exit": ("stop_result", "already_exited"),
            "wrong_exit": ("terminal_exit_code", 0),
            "wrong_method": ("stop_method", "popen_return_v1"),
        }
        for name, (field, value) in attacks.items():
            with self.subTest(name=name):
                changed = copy.deepcopy(self.record)
                if value is None:
                    del changed[field]
                else:
                    changed[field] = value
                self.seal(changed)
                code, result = self.public_verify()
                self.assertNotEqual(0, code, result)
                self.assertEqual("unpassed", result["qualification"])
        self.seal(self.record)
        (self.archive / "executable.bin").write_bytes(b"altered executable")
        code, result = self.public_verify()
        self.assertNotEqual(0, code, result)

    def test_public_replay_rejects_raw_mutation_and_key_inside_archive(self):
        self.seal(self.record)
        (self.archive / "stdout.raw").write_bytes(b"altered raw")
        code, result = self.public_verify()
        self.assertNotEqual(0, code, result)
        (self.archive / "stdout.raw").write_bytes(
            b'{"ready_pid": 42, "touched_bytes": 16777216}\n')
        (self.archive / "ready.pid").write_bytes(b"43")
        code, result = self.public_verify()
        self.assertNotEqual(0, code, result)
        (self.archive / "ready.pid").write_bytes(b"42")
        (self.archive / "extra.txt").write_bytes(b"unbound")
        code, result = self.public_verify()
        self.assertNotEqual(0, code, result)
        (self.archive / "extra.txt").unlink()
        (self.archive / "stdout.raw").write_bytes(
            b'{"ready_pid": 42, "touched_bytes": 16777216}\n')
        inside = self.archive / "operator.key"
        inside.write_bytes(self.key)
        with patch.object(sys, "argv", ["host_capacity_control.py", "verify", "--archive",
                                      str(self.archive), "--trusted-key", str(inside),
                                      "--expected-source-commit", self.commit]), \
             patch("host_capacity_control.source_at_commit",
                   return_value=Path(control.__file__).read_bytes()), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit):
                control.main()
        self.assertIn("outside every archive", output.getvalue())

    def test_producer_stop_uses_native_windows_result_and_mac_exact_wait4(self):
        process = Mock(pid=42)
        process.wait.return_value = 1
        with patch("host_capacity_control.windows_dispatch_stop") as dispatch, \
             patch("host_capacity_control.windows_terminal_peak", return_value=2000):
            result = control.capture_stop(process, "Windows", 42, 123)
        dispatch.assert_called_once_with(process, 42)
        self.assertEqual("os_success", result["stop_result"])
        self.assertEqual(1, result["terminal_exit_code"])
        self.assertEqual(2000, result["terminal_peak_bytes"])
        with patch("host_capacity_control.windows_dispatch_stop",
                   side_effect=OSError(5, "access denied")):
            with self.assertRaises(OSError):
                control.capture_stop(process, "Windows", 42, 123)
        with patch("host_capacity_control.os.kill") as send, \
             patch("host_capacity_control.wait4_peak_rss", return_value=(15, 2000)) as wait:
            result = control.capture_stop(process, "Darwin", 42, None)
        send.assert_called_once()
        wait.assert_called_once_with(42, 0, "Darwin")
        self.assertEqual(15, result["terminal_wait_status"])
        self.assertEqual(2000, result["terminal_peak_bytes"])

    def test_workflow_is_parsed_pinned_and_bounded(self):
        source = WORKFLOW.read_bytes()
        self.assertEqual(WORKFLOW_SHA256, digest(source))
        document = yaml.safe_load(source)
        self.assertEqual({"macos-26", "windows-2025"},
                         set(document["jobs"]["capture"]["strategy"]["matrix"]["os"]))
        steps = document["jobs"]["capture"]["steps"]
        self.assertTrue(all(len(step["run"]) < 21000 for step in steps if "run" in step))
        self.assertEqual(2, sum(step.get("if") == "always()" for step in steps))
        self.assertIn("${{ github.sha }}", source.decode())
