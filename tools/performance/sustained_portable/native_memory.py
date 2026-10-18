import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys
import time


class _MacTaskInfo(ctypes.Structure):
    _fields_ = [("virtual_size", ctypes.c_uint64),
                ("resident_size", ctypes.c_uint64),
                ("other", ctypes.c_uint64 * 4),
                ("counts", ctypes.c_int32 * 12)]


class _WindowsMemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("page_fault_count", wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in
        ("peak_working_set", "working_set", "peak_paged_pool", "paged_pool",
         "peak_nonpaged_pool", "nonpaged_pool", "pagefile", "peak_pagefile")]


def read_rss_bytes(pid):
    if sys.platform.startswith("linux"):
        fields = Path(f"/proc/{pid}/statm").read_text().split()
        if len(fields) < 2:
            raise ValueError("Linux process resident pages are unavailable")
        resident = int(fields[1]) * os.sysconf("SC_PAGE_SIZE")
    elif sys.platform == "darwin":
        info = _MacTaskInfo()
        info_size = ctypes.sizeof(info)
        if info_size != 96:
            raise ValueError(f"macOS PROC_PIDTASKINFO ABI size is {info_size}, expected 96")
        library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        library.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                                         ctypes.c_void_p, ctypes.c_int]
        library.proc_pidinfo.restype = ctypes.c_int
        if library.proc_pidinfo(pid, 4, 0, ctypes.byref(info), info_size) != info_size:
            raise OSError(ctypes.get_errno(), "macOS process resident bytes unavailable")
        resident = info.resident_size
    elif sys.platform == "win32":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,
                                               ctypes.POINTER(_WindowsMemoryCounters),
                                               wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            counters = _WindowsMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                raise ctypes.WinError(ctypes.get_last_error())
            resident = counters.working_set
        finally:
            kernel.CloseHandle(handle)
    else:
        raise ValueError(f"no resident-byte observer for {sys.platform}")
    if resident <= 0:
        raise ValueError("resident-byte probe returned a nonpositive value")
    return resident


def sample_while_alive(process, stop, interval_seconds=0.02):
    samples = []
    errors = []
    while process.poll() is None and not stop.is_set():
        timestamp = time.monotonic_ns()
        try:
            samples.append((timestamp, read_rss_bytes(process.pid)))
        except (OSError, ValueError) as error:
            if process.poll() is not None:
                break
            errors.append({"monotonic_ns": timestamp, "error": str(error)})
        stop.wait(interval_seconds)
    return {"pid": process.pid, "method": {"linux": "procfs_statm_resident",
             "darwin": "proc_pidinfo_task_resident", "win32": "GetProcessMemoryInfo_working_set"}.get(
                 "linux" if sys.platform.startswith("linux") else sys.platform),
            "samples": samples, "errors": errors,
            "status": "observed_diagnostic" if samples and not errors else "unavailable_or_partial"}
