import ctypes
from ctypes import wintypes
import os
import subprocess
from pathlib import Path


METHODS = {"Linux": "linux_proc_vmhwm_v1",
           "Darwin": "macos_wait4_maxrss_v1",
           "Windows": "windows_psapi_peak_working_set_v1"}


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


def stress_monitor_method(system):
    return METHODS.get(system, "unsupported_unknown_external_peak_v1")


def darwin_wait4_peak_rss(pid, options):
    if type(pid) is not int or pid <= 0:
        raise ValueError("macOS terminal usage PID is invalid")
    observed_pid, status, usage = os.wait4(pid, options)
    if observed_pid == 0 and options & os.WNOHANG:
        return None
    if observed_pid != pid or type(status) is not int or status < 0 or usage is None:
        raise ValueError("macOS terminal usage PID or status is invalid")
    value = usage.ru_maxrss
    if type(value) is not int or value <= 0:
        raise ValueError("macOS terminal peak RSS is invalid")
    return status, value


def peak_rss_bytes(pid, system):
    if type(pid) is not int or pid <= 0:
        raise ValueError("stress monitor PID is invalid")
    if system == "Darwin":
        result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "pid=", "-o", "rss="],
                                capture_output=True, text=True, timeout=1, check=False)
        fields = result.stdout.split()
        if result.returncode != 0 or len(fields) != 2:
            raise ValueError("macOS external RSS sample is invalid")
        observed_pid, kib = map(int, fields)
        if observed_pid != pid or kib <= 0:
            raise ValueError("macOS external RSS PID or sample is invalid")
        return kib * 1024
    if system == "Windows":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.restype = wintypes.BOOL
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p,
                                               ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
                                               wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            raise OSError("Windows external process handle is unavailable")
        try:
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                raise OSError("Windows external peak working set is unavailable")
            if counters.PeakWorkingSetSize <= 0:
                raise ValueError("Windows external peak working set is invalid")
            return counters.PeakWorkingSetSize
        finally:
            kernel.CloseHandle(handle)
    if system != "Linux":
        raise ValueError(f"external peak RSS monitor is unvalidated for {system}")
    status = Path(f"/proc/{pid}/status").read_text()
    rows = [line.split() for line in status.splitlines() if line.startswith("VmHWM:")]
    if len(rows) != 1 or len(rows[0]) != 3 or rows[0][2] != "kB":
        raise ValueError("Linux VmHWM reading is invalid")
    value = int(rows[0][1])
    if value <= 0:
        raise ValueError("Linux VmHWM reading is invalid")
    return value * 1024
