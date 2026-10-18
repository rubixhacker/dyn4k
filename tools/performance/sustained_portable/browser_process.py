import hashlib
import os
from pathlib import Path
import time


TICKS_PER_SECOND = os.sysconf("SC_CLK_TCK")
TICK_NS = 1_000_000_000 // TICKS_PER_SECOND


def boottime_ns():
    return time.clock_gettime_ns(time.CLOCK_BOOTTIME)


def process_stat(proc_root, pid):
    raw = (proc_root / str(pid) / "stat").read_text()
    fields = raw[raw.rfind(")") + 2:].split()
    if len(fields) < 20:
        raise ValueError(f"incomplete process stat: {pid}")
    return {
        "pid": pid, "state": fields[0], "ppid": int(fields[1]),
        "pgrp": int(fields[2]), "session": int(fields[3]),
        "start_ticks": int(fields[19]),
    }


def image_digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
        finished = os.fstat(stream.fileno())
    current = path.stat()
    identity = (opened.st_dev, opened.st_ino, opened.st_size)
    if identity != (finished.st_dev, finished.st_ino, finished.st_size) or identity != (
        current.st_dev, current.st_ino, current.st_size
    ):
        raise ValueError("browser executable changed during image read")
    return value.hexdigest(), identity


def verify_mapped_image(proc_root, pid, selected, expected_sha256):
    mapped = proc_root / str(pid) / "exe"
    mapped_path = os.readlink(mapped)
    mapped_sha, mapped_identity = image_digest(mapped)
    selected_sha, _ = image_digest(selected)
    if mapped_sha != expected_sha256 or selected_sha != expected_sha256:
        raise ValueError("browser mapped image differs from selected Chrome binary")
    return {"path": mapped_path, "sha256": mapped_sha,
            "device": mapped_identity[0], "inode": mapped_identity[1],
            "bytes": mapped_identity[2]}


class ChromeObserver:
    def __init__(self, wrapper_pid, profile, page_url, selected_binary,
                 selected_sha256, launched_boottime_ns, proc_root=Path("/proc")):
        self.proc_root = Path(proc_root)
        self.wrapper = process_stat(self.proc_root, wrapper_pid)
        self.profile_arg = f"--user-data-dir={profile}"
        self.page_url = page_url
        self.selected_binary = Path(selected_binary)
        self.selected_sha256 = selected_sha256
        self.launched_boottime_ns = launched_boottime_ns
        self.observed = {}
        if self.wrapper["state"] in ("Z", "X"):
            raise ValueError("browser wrapper exited before observation")

    def _argv(self, pid):
        raw = (self.proc_root / str(pid) / "cmdline").read_bytes()
        return [os.fsdecode(value) for value in raw.split(b"\0") if value]

    def _lineage(self, stat):
        ancestors = []
        seen = set()
        current = stat
        while current["pid"] != self.wrapper["pid"]:
            if current["pid"] in seen or len(ancestors) >= 32:
                raise ValueError("browser process ancestry is cyclic or too deep")
            seen.add(current["pid"])
            parent = process_stat(self.proc_root, current["ppid"])
            ancestors.append({"pid": parent["pid"], "start_ticks": parent["start_ticks"]})
            current = parent
        if current["start_ticks"] != self.wrapper["start_ticks"]:
            raise ValueError("browser wrapper PID was reused")
        return ancestors

    def _observe(self, pid, argv):
        before = process_stat(self.proc_root, pid)
        if before["state"] in ("Z", "X"):
            raise ValueError("browser process is no longer live")
        after = process_stat(self.proc_root, pid)
        if after["state"] in ("Z", "X") or any(
            before[key] != after[key]
            for key in ("pid", "ppid", "pgrp", "session", "start_ticks")
        ):
            raise ValueError("browser process changed during observation")
        if after["session"] != self.wrapper["session"]:
            raise ValueError("browser process is outside launched session")
        if after["start_ticks"] * TICK_NS < self.launched_boottime_ns - TICK_NS:
            raise ValueError("browser process predates the launch")
        if self.profile_arg not in argv or self.page_url not in argv:
            raise ValueError("browser argv differs from launched profile or page")
        ancestry = self._lineage(after)
        key = (pid, after["start_ticks"])
        now = boottime_ns()
        if key not in self.observed:
            image = verify_mapped_image(self.proc_root, pid, self.selected_binary,
                                        self.selected_sha256)
            self.observed[key] = {
                "pid": pid, "start_ticks": after["start_ticks"],
                "start_boottime_floor_ns": after["start_ticks"] * TICK_NS,
                "first_seen_boottime_ns": now,
                "last_seen_boottime_ns": now,
                "argv": argv, "profile_arg": self.profile_arg,
                "page_url": self.page_url, "ancestry": ancestry,
                "session": after["session"], "pgrp": after["pgrp"],
                "mapped_image": image,
            }
        else:
            record = self.observed[key]
            if argv != record["argv"] or ancestry != record["ancestry"]:
                raise ValueError("browser process identity changed during capture")
            image = self.proc_root / str(pid) / "exe"
            mapped = image.stat()
            if (mapped.st_dev, mapped.st_ino, mapped.st_size) != (
                record["mapped_image"]["device"], record["mapped_image"]["inode"],
                record["mapped_image"]["bytes"]
            ):
                raise ValueError("browser mapped image changed during capture")
            record["last_seen_boottime_ns"] = now
        if len(self.observed) > 1:
            raise ValueError("ambiguous browser processes use the launched profile")

    def sample(self):
        for proc in self.proc_root.iterdir():
            if not proc.name.isdecimal():
                continue
            pid = int(proc.name)
            try:
                argv = self._argv(pid)
            except OSError:
                continue
            if self.profile_arg not in argv and self.page_url not in argv:
                continue
            if any(arg.startswith("--type=") for arg in argv):
                continue
            try:
                exe_path = os.readlink(proc / "exe")
            except OSError as error:
                raise ValueError(f"browser candidate image unavailable: {pid}") from error
            if Path(exe_path).name != "chrome" and (
                not argv or Path(argv[0]).name != "chrome"
            ):
                continue
            try:
                self._observe(pid, argv)
            except OSError as error:
                raise ValueError(f"browser process observation raced: {pid}") from error

    def finish(self, page_ns, first_resource_ns, last_resource_ns,
               completion_ns, nonce):
        self.sample()
        if len(self.observed) != 1:
            raise ValueError("browser process image was not uniquely observed")
        record = next(iter(self.observed.values()))
        current = process_stat(self.proc_root, record["pid"])
        if current["state"] in ("Z", "X") or current["start_ticks"] != record["start_ticks"]:
            raise ValueError("browser process exited or PID was reused before completion")
        if not all(type(value) is int and value > 0 for value in (
            page_ns, first_resource_ns, last_resource_ns, completion_ns
        )):
            raise ValueError("browser page, resource, or completion time is missing")
        if not (self.launched_boottime_ns <= page_ns <= first_resource_ns <=
                last_resource_ns <= completion_ns <= record["last_seen_boottime_ns"]):
            raise ValueError("browser process and resource exchange times disagree")
        if record["start_boottime_floor_ns"] > page_ns:
            raise ValueError("browser process started after its page request")
        image = verify_mapped_image(self.proc_root, record["pid"],
                                    self.selected_binary, self.selected_sha256)
        if image != record["mapped_image"]:
            raise ValueError("browser mapped image changed before completion")
        return {
            **record, "method": "linux_procfs_exe",
            "wrapper_pid": self.wrapper["pid"],
            "wrapper_start_ticks": self.wrapper["start_ticks"],
            "launch_boottime_ns": self.launched_boottime_ns,
            "page_served_boottime_ns": page_ns,
            "first_resource_boottime_ns": first_resource_ns,
            "last_resource_boottime_ns": last_resource_ns,
            "completion_boottime_ns": completion_ns,
            "completion_nonce_sha256": hashlib.sha256(nonce.encode()).hexdigest(),
            "selected_image_path": str(self.selected_binary),
            "selected_image_sha256": self.selected_sha256,
        }
