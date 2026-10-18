import os
import platform
import ctypes
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

from stress_monitor import darwin_wait4_peak_rss, peak_rss_bytes, stress_monitor_method
from sustained_archive import PROCESS_IMAGE_METHODS, observe_process_image


class StressMonitorTest(unittest.TestCase):
    def test_available_linux_process_peak_is_read_externally(self):
        if platform.system() != "Linux":
            self.skipTest("Linux process status unavailable")
        before = peak_rss_bytes(os.getpid(), "Linux")
        allocated = bytearray(8 * 1024 * 1024)
        for position in range(0, len(allocated), 4096):
            allocated[position] = 1
        after = peak_rss_bytes(os.getpid(), "Linux")
        self.assertGreater(before, 0)
        self.assertGreaterEqual(after, before)
        self.assertEqual("linux_proc_vmhwm_v1", stress_monitor_method("Linux"))

    def test_macos_ps_reads_exact_pid_and_kib_units(self):
        with patch("stress_monitor.subprocess.run", return_value=subprocess.CompletedProcess(
                [], 0, stdout="123 8192\n", stderr="")) as run:
            self.assertEqual(8 * 1024 * 1024, peak_rss_bytes(123, "Darwin"))
        self.assertEqual(["/bin/ps", "-p", "123", "-o", "pid=", "-o", "rss="],
                         run.call_args.args[0])
        self.assertEqual("macos_wait4_maxrss_v1", stress_monitor_method("Darwin"))
        with patch("stress_monitor.subprocess.run", return_value=subprocess.CompletedProcess(
                [], 0, stdout="124 8192\n", stderr="")):
            with self.assertRaisesRegex(ValueError, "PID"):
                peak_rss_bytes(123, "Darwin")

    def test_macos_terminal_wait4_binds_child_pid_and_peak_rss(self):
        usage = type("Usage", (), {"ru_maxrss": 8 * 1024 * 1024})()
        with patch("stress_monitor.os.wait4", return_value=(123, 0, usage)) as wait4:
            self.assertEqual((0, 8 * 1024 * 1024),
                             darwin_wait4_peak_rss(123, os.WNOHANG))
        wait4.assert_called_once_with(123, os.WNOHANG)
        with patch("stress_monitor.os.wait4", return_value=(0, 0, None)):
            self.assertIsNone(darwin_wait4_peak_rss(123, os.WNOHANG))
        with patch("stress_monitor.os.wait4", return_value=(124, 0, usage)):
            with self.assertRaisesRegex(ValueError, "PID"):
                darwin_wait4_peak_rss(123, os.WNOHANG)
        with patch("stress_monitor.os.wait4", return_value=(123, 0,
                   type("Usage", (), {"ru_maxrss": 0})())):
            with self.assertRaisesRegex(ValueError, "peak RSS"):
                darwin_wait4_peak_rss(123, os.WNOHANG)

    def test_windows_psapi_reads_os_peak_and_closes_handle(self):
        calls = []

        class Function:
            def __init__(self, callback):
                self.callback = callback

            def __call__(self, *args):
                return self.callback(*args)

        class Kernel:
            def __init__(self):
                self.OpenProcess = Function(lambda rights, inherit, pid: calls.append(
                    ("open", rights, pid)) or 12345)
                self.CloseHandle = Function(lambda handle: calls.append(
                    ("close", handle)) or 1)

        class Psapi:
            def __init__(self):
                def memory(handle, pointer, size):
                    calls.append(("sample", handle, size))
                    from stress_monitor import PROCESS_MEMORY_COUNTERS
                    data = ctypes.cast(pointer, ctypes.POINTER(PROCESS_MEMORY_COUNTERS))
                    data.contents.PeakWorkingSetSize = 9 * 1024 * 1024
                    return 1
                self.GetProcessMemoryInfo = Function(memory)

        with patch("stress_monitor.ctypes.WinDLL", side_effect=lambda name, **kwargs:
                   Kernel() if name == "kernel32" else Psapi(), create=True):
            self.assertEqual(9 * 1024 * 1024, peak_rss_bytes(123, "Windows"))
        self.assertEqual(["open", "sample", "close"], [entry[0] for entry in calls])
        self.assertEqual("windows_psapi_peak_working_set_v1",
                         stress_monitor_method("Windows"))

    def test_unknown_platform_never_reads_procfs(self):
        with patch("stress_monitor.Path") as path:
            self.assertTrue(stress_monitor_method("FreeBSD").startswith("unsupported_"))
            with self.assertRaisesRegex(ValueError, "unvalidated"):
                peak_rss_bytes(123, "FreeBSD")
            path.assert_not_called()

    def test_native_monitor_failures_do_not_become_zero_samples(self):
        with patch("stress_monitor.subprocess.run", return_value=subprocess.CompletedProcess(
                [], 0, stdout="999 8192\n", stderr="")):
            with self.assertRaisesRegex(ValueError, "PID"):
                peak_rss_bytes(123, "Darwin")
        kernel = MagicMock()
        psapi = MagicMock()
        kernel.OpenProcess.return_value = 12345
        psapi.GetProcessMemoryInfo.return_value = 0
        with patch("stress_monitor.ctypes.WinDLL", side_effect=[kernel, psapi], create=True):
            with self.assertRaisesRegex(OSError, "unavailable"):
                peak_rss_bytes(123, "Windows")
        kernel.CloseHandle.assert_called_once_with(12345)

    def test_native_hosted_probe_when_available(self):
        if platform.system() not in ("Darwin", "Windows"):
            self.skipTest("hosted macOS or Windows runner required")
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"])
        try:
            image = observe_process_image(child.pid)
            self.assertEqual(child.pid, image["pid"])
            self.assertEqual(PROCESS_IMAGE_METHODS[platform.system()], image["method"])
            sampled_rss = peak_rss_bytes(child.pid, platform.system())
            self.assertGreater(sampled_rss, 0)
            if platform.system() == "Darwin":
                status, terminal_peak = darwin_wait4_peak_rss(child.pid, 0)
                child.returncode = os.waitstatus_to_exitcode(status)
                self.assertGreaterEqual(terminal_peak, sampled_rss)
                self.assertEqual(0, child.returncode)
            else:
                self.assertEqual(0, child.wait(timeout=5))
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)

    def test_linux_invalid_pid_is_rejected_before_procfs(self):
        with patch("stress_monitor.Path") as path:
            for pid in (0, -1, True, "123"):
                with self.assertRaisesRegex(ValueError, "PID"):
                    peak_rss_bytes(pid, "Linux")
            path.assert_not_called()
