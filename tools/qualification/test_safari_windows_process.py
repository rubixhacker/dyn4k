import ctypes
import subprocess
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import safari_yarn_lock


class SafariWindowsProcessTests(unittest.TestCase):
    def test_resume_requires_unique_primary_thread_and_suspend_count_one(self):
        closed = []

        class Function:
            def __init__(self, action):
                self.action = action

            def __call__(self, *arguments):
                return self.action(*arguments)

        def first(snapshot, pointer):
            entry = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32))
            entry[2] = 901
            entry[3] = 345
            return 1

        kernel = mock.Mock(CreateToolhelp32Snapshot=Function(lambda *_: 777),
                           Thread32First=Function(first),
                           Thread32Next=Function(lambda *_: 0),
                           OpenThread=Function(lambda access, inherit, tid: 888 if
                                               (access, inherit, tid) == (2, 0, 901) else 0),
                           ResumeThread=Function(lambda handle: 1),
                           CloseHandle=Function(lambda handle: closed.append(handle) or 1))
        process = mock.Mock(pid=345)
        safari_yarn_lock._resume_suspended_windows_process(kernel, process)
        self.assertEqual([888, 777], closed)

        closed.clear()
        kernel.ResumeThread = Function(lambda handle: 0)
        with self.assertRaisesRegex(OSError, "cannot resume"):
            safari_yarn_lock._resume_suspended_windows_process(kernel, process)
        self.assertEqual([888, 777], closed)

        closed.clear()
        kernel.ResumeThread = Function(lambda handle: 1)
        process.pid = 346
        with self.assertRaisesRegex(OSError, "primary thread is missing"):
            safari_yarn_lock._resume_suspended_windows_process(kernel, process)
        self.assertEqual([777], closed)

    def test_job_accounting_reads_active_process_count_or_fails_closed(self):
        class Function:
            def __init__(self, action):
                self.action = action

            def __call__(self, *arguments):
                return self.action(*arguments)

        def query(job, kind, pointer, size, returned):
            self.assertEqual((789, 1, 48, None), (job, kind, size, returned))
            ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32))[10] = 2
            return 1

        kernel = mock.Mock(QueryInformationJobObject=Function(query))
        self.assertEqual(2, safari_yarn_lock._windows_job_active_count(kernel, 789))
        kernel.QueryInformationJobObject = Function(lambda *_: 0)
        with self.assertRaisesRegex(OSError, "cannot query"):
            safari_yarn_lock._windows_job_active_count(kernel, 789)

    def test_suspended_windows_launch_assigns_job_before_resume(self):
        calls = []
        unbound_child_started = []

        class Stream:
            def read(self, _size):
                return b""

            def close(self):
                pass

        class Process:
            pid = 345
            _handle = 456
            returncode = 0
            stdout = Stream()
            stderr = Stream()

            def wait(self, timeout):
                return self.returncode

        class Function:
            def __init__(self, action):
                self.action = action

            def __call__(self, *arguments):
                return self.action(*arguments)

        def launch(_command, **kwargs):
            calls.append(("launch_flags", kwargs["creationflags"]))
            if not kwargs["creationflags"] & safari_yarn_lock.WINDOWS_CREATE_SUSPENDED:
                unbound_child_started.append(True)
            return Process()

        def resume(_kernel, process):
            calls.append(("resume", process.pid))

        kernel = mock.Mock(CreateJobObjectW=Function(lambda *_: 789),
                           SetInformationJobObject=Function(lambda *_: 1),
                           AssignProcessToJobObject=Function(lambda *_:
                                                             calls.append(("assign", 345)) or 1),
                           QueryInformationJobObject=Function(lambda *_: 1),
                           TerminateJobObject=Function(lambda *_: 1),
                           CloseHandle=Function(lambda *_: 1))
        proxy = mock.Mock(wraps=os)
        proxy.name = "nt"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "capture"
            output.mkdir()
            with mock.patch.object(subprocess, "CREATE_NEW_PROCESS_GROUP", 0,
                                   create=True), \
                    mock.patch.object(subprocess, "Popen", side_effect=launch), \
                    mock.patch.object(safari_yarn_lock, "os", proxy), \
                    mock.patch.object(safari_yarn_lock.ctypes, "WinDLL", return_value=kernel,
                                      create=True), \
                    mock.patch.object(safari_yarn_lock, "_resume_suspended_windows_process",
                                      side_effect=resume, create=True), \
                    mock.patch.object(safari_yarn_lock, "_windows_job_active_count",
                                      return_value=0, create=True):
                result = safari_yarn_lock._run_lock_task_windows(
                    Path(temporary), output, ["gradle"])
        self.assertEqual(0, result["exit_code"])
        self.assertFalse(unbound_child_started)
        self.assertTrue(calls[0][1] & 0x00000004)
        self.assertLess(calls.index(("assign", 345)), calls.index(("resume", 345)))

    def test_complete_pipe_stream_rejects_active_detached_job_child(self):
        calls = []

        class Stream:
            def read(self, _size):
                return b""

            def close(self):
                pass

        class Process:
            pid = 345
            _handle = 456
            returncode = 0
            stdout = Stream()
            stderr = Stream()

            def wait(self, timeout):
                return self.returncode

        class Function:
            def __init__(self, action):
                self.action = action

            def __call__(self, *arguments):
                return self.action(*arguments)

        kernel = mock.Mock(CreateJobObjectW=Function(lambda *_: 789),
                           SetInformationJobObject=Function(lambda *_: 1),
                           AssignProcessToJobObject=Function(lambda *_: 1),
                           QueryInformationJobObject=Function(lambda *_: 1),
                           TerminateJobObject=Function(lambda job, code:
                                                       calls.append(("terminate", job, code)) or 1),
                           CloseHandle=Function(lambda handle:
                                                calls.append(("close", handle)) or 1))
        proxy = mock.Mock(wraps=os)
        proxy.name = "nt"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "capture"
            output.mkdir()
            with mock.patch.object(subprocess, "CREATE_NEW_PROCESS_GROUP", 0,
                                   create=True), \
                    mock.patch.object(subprocess, "Popen", return_value=Process()), \
                    mock.patch.object(safari_yarn_lock, "os", proxy), \
                    mock.patch.object(safari_yarn_lock.ctypes, "WinDLL", return_value=kernel,
                                      create=True), \
                    mock.patch.object(safari_yarn_lock, "_resume_suspended_windows_process",
                                      return_value=None, create=True), \
                    mock.patch.object(safari_yarn_lock, "_windows_job_active_count",
                                      return_value=1, create=True):
                result = safari_yarn_lock._run_lock_task_windows(
                    Path(temporary), output, ["gradle"])
        self.assertTrue(result["stream_incomplete"])
        self.assertIn(("terminate", 789, 1), calls)

    def test_reader_failure_is_incomplete_even_after_thread_exits(self):
        class FailingStream:
            def __init__(self, first):
                self.first = first
                self.calls = 0

            def read(self, _size):
                self.calls += 1
                if self.calls == 1:
                    return self.first
                raise OSError("read failed after signature")

            def close(self):
                pass

        class Process:
            pid = 123
            returncode = 1

            def __init__(self):
                self.stdout = FailingStream(b"> Task :kotlinStoreYarnLock FAILED\n")
                self.stderr = FailingStream(b"Lock file was changed\n")

            def wait(self, timeout):
                return self.returncode

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "capture"
            output.mkdir()
            proxy = mock.Mock(wraps=os)
            proxy.name = "posix"
            with mock.patch.object(subprocess, "CREATE_NEW_PROCESS_GROUP", 0, create=True), \
                    mock.patch.object(subprocess, "Popen", return_value=Process()), \
                    mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess(
                        ["taskkill"], 0)), \
                    mock.patch.object(safari_yarn_lock, "os", proxy):
                result = safari_yarn_lock._run_lock_task_windows(
                    Path(temporary), output, ["gradle"])
            self.assertTrue(result["stream_incomplete"])
            self.assertEqual(1, result["exit_code"])
            self.assertEqual(len((output / "stdout.txt").read_bytes()),
                             result["stdout_bytes_seen"])

    def test_exited_parent_with_open_descendant_pipe_triggers_tree_cleanup(self):
        release = threading.Event()
        killed = []

        class HeldStream:
            def read(self, _size):
                release.wait(2)
                return b""

            def close(self):
                pass

        class Process:
            pid = 345
            returncode = 0

            def __init__(self):
                self.stdout = HeldStream()
                self.stderr = HeldStream()

            def wait(self, timeout):
                return self.returncode

        def taskkill(command, **_kwargs):
            killed.append(command)
            release.set()
            return subprocess.CompletedProcess(command, 0)

        try:
            with tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "capture"
                output.mkdir()
                proxy = mock.Mock(wraps=os)
                proxy.name = "posix"
                with mock.patch.object(subprocess, "CREATE_NEW_PROCESS_GROUP", 0,
                                       create=True), \
                        mock.patch.object(subprocess, "Popen", return_value=Process()), \
                        mock.patch.object(subprocess, "run", side_effect=taskkill), \
                        mock.patch.object(safari_yarn_lock, "os", proxy), \
                        mock.patch.object(safari_yarn_lock, "MAX_DRAIN_SECONDS", 0.05):
                    result = safari_yarn_lock._run_lock_task_windows(
                        Path(temporary), output, ["gradle"])
                self.assertTrue(result["stream_incomplete"])
                self.assertEqual([["taskkill", "/T", "/F", "/PID", "345"]], killed)
        finally:
            release.set()

    def test_windows_job_terminates_descendant_after_parent_exit(self):
        release = threading.Event()
        calls = []

        class HeldStream:
            def read(self, _size):
                release.wait(2)
                return b""

            def close(self):
                pass

        class Process:
            pid = 345
            _handle = 456
            returncode = 0

            def __init__(self):
                self.stdout = HeldStream()
                self.stderr = HeldStream()

            def wait(self, timeout):
                return self.returncode

        class Function:
            def __init__(self, action):
                self.action = action

            def __call__(self, *arguments):
                return self.action(*arguments)

        def terminate(job, code):
            calls.append(("terminate", job, code))
            release.set()
            return 1

        kernel = mock.Mock(CreateJobObjectW=Function(lambda *_: 789),
                           AssignProcessToJobObject=Function(lambda *args:
                                                             calls.append(("assign", *args)) or 1),
                           TerminateJobObject=Function(terminate),
                           CloseHandle=Function(lambda handle:
                                                calls.append(("close", handle)) or 1))
        proxy = mock.Mock(wraps=os)
        proxy.name = "nt"
        try:
            with tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "capture"
                output.mkdir()
                with mock.patch.object(subprocess, "CREATE_NEW_PROCESS_GROUP", 0,
                                       create=True), \
                        mock.patch.object(subprocess, "Popen", return_value=Process()), \
                        mock.patch.object(safari_yarn_lock, "os", proxy), \
                        mock.patch.object(safari_yarn_lock.ctypes, "WinDLL", return_value=kernel,
                                          create=True), \
                        mock.patch.object(safari_yarn_lock, "_resume_suspended_windows_process",
                                          return_value=None), \
                        mock.patch.object(safari_yarn_lock, "_windows_job_active_count",
                                          return_value=1), \
                        mock.patch.object(safari_yarn_lock, "MAX_DRAIN_SECONDS", 0.05):
                    result = safari_yarn_lock._run_lock_task_windows(
                        Path(temporary), output, ["gradle"])
                self.assertTrue(result["stream_incomplete"])
                self.assertIn(("assign", 789, 456), calls)
                self.assertIn(("terminate", 789, 1), calls)
                self.assertIn(("close", 789), calls)
        finally:
            release.set()

    def test_windows_job_assignment_failure_stops_process_and_closes_pipes(self):
        class Stream:
            closed = False

            def close(self):
                self.closed = True

        class Process:
            pid = 345
            _handle = 456
            returncode = 1

            def __init__(self):
                self.stdout = Stream()
                self.stderr = Stream()

            def wait(self, timeout):
                return self.returncode

        class Function:
            def __init__(self, action):
                self.action = action

            def __call__(self, *arguments):
                return self.action(*arguments)

        closed = []
        kernel = mock.Mock(CreateJobObjectW=Function(lambda *_: 789),
                           AssignProcessToJobObject=Function(lambda *_: 0),
                           CloseHandle=Function(lambda handle: closed.append(handle) or 1))
        proxy = mock.Mock(wraps=os)
        proxy.name = "nt"
        process = Process()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "capture"
            output.mkdir()
            with mock.patch.object(subprocess, "CREATE_NEW_PROCESS_GROUP", 0,
                                   create=True), \
                    mock.patch.object(subprocess, "Popen", return_value=process), \
                    mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess(
                        ["taskkill"], 0)) as taskkill, \
                    mock.patch.object(safari_yarn_lock, "os", proxy), \
                    mock.patch.object(safari_yarn_lock.ctypes, "WinDLL", return_value=kernel,
                                      create=True):
                with self.assertRaisesRegex(OSError, "cannot bind.*before execution"):
                    safari_yarn_lock._run_lock_task_windows(Path(temporary), output, ["gradle"])
        self.assertEqual([789], closed)
        taskkill.assert_not_called()
        self.assertTrue(process.stdout.closed and process.stderr.closed)

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
