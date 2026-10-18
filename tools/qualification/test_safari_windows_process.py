import subprocess
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import safari_yarn_lock


class SafariWindowsProcessTests(unittest.TestCase):
    def test_threaded_process_capture_bounds_both_streams(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "capture"
            output.mkdir()
            command = [sys.executable, "-c", "import sys; "
                       "sys.stdout.buffer.write(b'x' * 257); "
                       "sys.stderr.buffer.write(b'y' * 257)"]
            group_flag = (subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
            with mock.patch.object(subprocess, "CREATE_NEW_PROCESS_GROUP", group_flag,
                                   create=True), \
                    mock.patch.object(safari_yarn_lock, "MAX_FILE_BYTES", 128):
                result = safari_yarn_lock._run_lock_task_windows(
                    Path(temporary), output, command)
            self.assertEqual(0, result["exit_code"])
            self.assertFalse(result["stream_incomplete"])
            self.assertEqual((257, 257), (result["stdout_bytes_seen"],
                                          result["stderr_bytes_seen"]))
            self.assertTrue(result["stdout_truncated"] and result["stderr_truncated"])
            self.assertEqual(b"x" * 128, (output / "stdout.txt").read_bytes())
            self.assertEqual(b"y" * 128, (output / "stderr.txt").read_bytes())

    def test_threaded_process_capture_enforces_deadline(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "capture"
            output.mkdir()
            command = [sys.executable, "-c", "import time; time.sleep(5)"]
            started = time.monotonic()
            group_flag = (subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
            with mock.patch.object(subprocess, "CREATE_NEW_PROCESS_GROUP", group_flag,
                                   create=True), \
                    mock.patch.object(safari_yarn_lock, "MAX_PROCESS_SECONDS", 0.2):
                result = safari_yarn_lock._run_lock_task_windows(
                    Path(temporary), output, command)
            self.assertTrue(result["timed_out"])
            self.assertFalse(result["stream_incomplete"])
            self.assertLess(time.monotonic() - started, 3)


if __name__ == "__main__":
    unittest.main()
