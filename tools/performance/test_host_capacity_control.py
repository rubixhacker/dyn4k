import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
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
