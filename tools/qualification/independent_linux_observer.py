#!/usr/bin/env python3
import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import sys
import threading
import time


WITNESS_SCHEMA = "independent-execution-witness/1"
ZERO = "0" * 64
PTRACE_TRACEME = 0
PTRACE_CONT = 7
PTRACE_SETOPTIONS = 0x4200
PTRACE_GETEVENTMSG = 0x4201
PTRACE_O_TRACEFORK = 2
PTRACE_O_TRACEVFORK = 4
PTRACE_O_TRACECLONE = 8
PTRACE_O_TRACEEXEC = 16
PTRACE_O_TRACEEXIT = 64
PTRACE_O_EXITKILL = 0x100000
OPTIONS = (PTRACE_O_TRACEFORK | PTRACE_O_TRACEVFORK | PTRACE_O_TRACECLONE |
           PTRACE_O_TRACEEXEC | PTRACE_O_TRACEEXIT | PTRACE_O_EXITKILL)
EVENT_FORK = 1
EVENT_VFORK = 2
EVENT_CLONE = 3
EVENT_EXEC = 4
EVENT_EXIT = 6
WAIT_ALL = 0x40000000
DEFAULT_EVENTS = 4096
DEFAULT_PROCESSES = 256
DEFAULT_LOG_BYTES = 8 * 1024 * 1024
MAX_EVENTS = 8192
MAX_PROCESSES = 1024
MAX_SECONDS = 3600
MAX_ARCHIVE_FILES = 4096
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
MAX_INPUT_BYTES = MAX_ARCHIVE_BYTES
MAX_IMAGE_BYTES = MAX_ARCHIVE_BYTES
MAX_LOG_BYTES = 16 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
libc = ctypes.CDLL(None, use_errno=True)
libc.ptrace.restype = ctypes.c_long
libc.ptrace.argtypes = (ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
                        ctypes.c_void_p)


class ObservationError(ValueError):
    pass


def _ptrace(request, pid, data=0):
    result = libc.ptrace(request, pid, None, ctypes.c_void_p(data))
    if result == -1:
        code = ctypes.get_errno()
        raise OSError(code, f"ptrace request {request} for pid {pid}: {os.strerror(code)}")
    return result


def _event_pid(pid):
    result = ctypes.c_ulong()
    value = libc.ptrace(PTRACE_GETEVENTMSG, pid, None, ctypes.byref(result))
    if value == -1:
        code = ctypes.get_errno()
        raise OSError(code, f"ptrace event message for pid {pid}: {os.strerror(code)}")
    return result.value


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ObservationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_json(raw):
    return json.loads(raw, object_pairs_hook=_strict_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ObservationError(f"non-finite JSON value: {value}")))


def _sha_file(path, deadline=None, byte_limit=None, label="input"):
    digest = hashlib.sha256()
    limit = MAX_INPUT_BYTES if byte_limit is None else min(MAX_INPUT_BYTES, byte_limit)
    handle = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    with os.fdopen(handle, "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ObservationError(f"not a regular file: {path}")
        if before.st_size > limit:
            raise ObservationError(f"{label} byte limit exceeded: {path}")
        bytes_read = 0
        for block in iter(lambda: source.read(1024 * 1024), b""):
            if deadline is not None and time.monotonic() > deadline:
                raise ObservationError("trace timeout during file hashing")
            bytes_read += len(block)
            if bytes_read > limit:
                raise ObservationError(f"{label} byte limit exceeded: {path}")
            digest.update(block)
        after = os.fstat(source.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ObservationError(f"file changed during hashing: {path}")
    return digest.hexdigest()


def _safe_input(path):
    path = Path(path).absolute()
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ObservationError(f"input must be one regular, unlinked file: {path}")
    return path


def _archive_digest(path, deadline=None):
    path = Path(path).absolute()
    if ".." in path.parts or path.is_symlink():
        raise ObservationError("archive path is symbolic or uses traversal")
    if path.is_file():
        archive = _safe_input(path)
        return _sha_file(archive, deadline, MAX_ARCHIVE_BYTES, "archive")
    if not path.is_dir():
        raise ObservationError(f"archive is absent: {path}")
    files = []
    total_bytes = 0
    for base, directories, names in os.walk(path, followlinks=False):
        for name in directories + names:
            if deadline is not None and time.monotonic() > deadline:
                raise ObservationError("archive seal exceeded trace timeout")
            member = Path(base) / name
            relative = member.relative_to(path).as_posix()
            if (member.is_symlink() or "\\" in relative or "\n" in relative or
                    "\r" in relative or any(part in ("", ".", "..")
                                            for part in relative.split("/"))):
                raise ObservationError(f"unsafe archive member: {relative}")
            info = member.lstat()
            if stat.S_ISDIR(info.st_mode):
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ObservationError(f"nonregular or hardlinked archive member: {relative}")
            remaining = MAX_ARCHIVE_BYTES - total_bytes
            if len(files) >= MAX_ARCHIVE_FILES or info.st_size > remaining:
                raise ObservationError("archive file or byte limit exceeded")
            digest = _sha_file(member, deadline, remaining, "archive")
            total_bytes += info.st_size
            after = member.lstat()
            if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != (
                    after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise ObservationError(f"archive member changed during hashing: {relative}")
            files.append({"path": relative, "sha256": digest,
                          "mtime_ns": info.st_mtime_ns})
    if not any(item["path"] == "receipt.json" for item in files):
        raise ObservationError("archive receipt.json is absent")
    return hashlib.sha256(_json_bytes(sorted(files, key=lambda item: item["path"]))).hexdigest()


def _stat(pid):
    raw = Path(f"/proc/{pid}/stat").read_text()
    fields = raw[raw.rfind(")") + 2:].split()
    return {"parent_pid": int(fields[1]), "start_ticks": int(fields[19])}


def _image(pid, deadline=None):
    stat_before = _stat(pid)
    handle = os.open(f"/proc/{pid}/exe", os.O_RDONLY | os.O_CLOEXEC)
    try:
        info = os.fstat(handle)
        if not stat.S_ISREG(info.st_mode):
            raise ObservationError(f"pid {pid} executable is not a regular image")
        if info.st_size > MAX_IMAGE_BYTES:
            raise ObservationError(f"process image byte limit exceeded for pid {pid}")
        path = os.readlink(f"/proc/{pid}/exe")
        digest = hashlib.sha256()
        bytes_read = 0
        while block := os.read(handle, 1024 * 1024):
            if deadline is not None and time.monotonic() > deadline:
                raise ObservationError("trace timeout during process image capture")
            bytes_read += len(block)
            if bytes_read > MAX_IMAGE_BYTES:
                raise ObservationError(f"process image byte limit exceeded for pid {pid}")
            digest.update(block)
        stat_after = _stat(pid)
        if stat_before["start_ticks"] != stat_after["start_ticks"]:
            raise ObservationError(f"pid {pid} start identity changed during image capture")
        argv = [part.decode("utf-8", "surrogateescape") for part in
                Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0") if part]
        if not argv:
            raise ObservationError(f"pid {pid} has no observable argv")
        return {"pid": pid, "start_ticks": stat_before["start_ticks"],
                "executable_path": path, "executable_dev": info.st_dev,
                "executable_ino": info.st_ino, "executable_sha256": digest.hexdigest(),
                "argv": argv}
    finally:
        os.close(handle)


def _identity(pid, boot_id):
    return {"pid": pid, "boot_id": boot_id, **_stat(pid)}


def _status(status):
    return {"exit_code": os.WEXITSTATUS(status) if os.WIFEXITED(status) else None,
            "signal": os.WTERMSIG(status) if os.WIFSIGNALED(status) else None}


def _continue_tracee(pid, event, sig):
    try:
        _ptrace(PTRACE_CONT, pid, sig if event == 0 else 0)
    except ProcessLookupError:
        if event != EVENT_EXIT:
            raise


class EventLog:
    def __init__(self, root, event_limit=DEFAULT_EVENTS, byte_limit=DEFAULT_LOG_BYTES):
        requested = Path(root).absolute()
        if ".." in requested.parts or requested.name in ("", ".", ".."):
            raise ObservationError("observer output uses path traversal")
        self.root = requested.parent.resolve(strict=True) / requested.name
        self.root.mkdir(mode=0o700, parents=False, exist_ok=False)
        self.fd = os.open(self.root / "events.jsonl",
                          os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self.count = 0
        self.head = ZERO
        self.rows = []
        self.size = 0
        self.event_limit = event_limit
        self.byte_limit = byte_limit

    def add(self, kind, **data):
        terminal = kind in ("error", "end")
        reserved = 0 if terminal else 1 if kind == "archive" else 2
        if self.count >= self.event_limit - reserved:
            raise ObservationError("event limit exceeded")
        body = {"seq": self.count + 1, "previous_sha256": self.head,
                "kind": kind, "observed_at_ns": time.monotonic_ns(),
                "observed_wall_ns": time.time_ns(), **data}
        digest = hashlib.sha256(_json_bytes(body)).hexdigest()
        row = {**body, "sha256": digest}
        raw = _json_bytes(row) + b"\n"
        if self.size + len(raw) > self.byte_limit - (0 if terminal else 4096):
            raise ObservationError("event log byte limit exceeded")
        if os.write(self.fd, raw) != len(raw):
            raise ObservationError("short event log write")
        os.fsync(self.fd)
        self.count += 1
        self.head = digest
        self.rows.append(row)
        self.size += len(raw)
        return row

    def close(self):
        os.close(self.fd)


def _expected(spec, deadline=None):
    result = {}
    for item in spec:
        if "=" not in item:
            raise ObservationError("expected process must be NAME=EXECUTABLE")
        name, raw = item.split("=", 1)
        if not name or name == "build" or name in result or "/" in name:
            raise ObservationError(f"invalid expected process name: {name}")
        path = Path(raw).resolve(strict=True)
        if not path.is_file():
            raise ObservationError(f"expected executable is not a file: {path}")
        result[name] = {"path": str(path), "sha256": _sha_file(path, deadline)}
    return result


def _generated_expected(spec, existing):
    result = {}
    for item in spec:
        if "=" not in item:
            raise ObservationError("generated process must be NAME=EXECUTABLE")
        name, raw = item.split("=", 1)
        requested = Path(raw)
        if (not name or name == "build" or name in existing or name in result
                or "/" in name or not requested.is_absolute() or ".." in requested.parts):
            raise ObservationError(f"invalid generated process selection: {item}")
        path = requested.parent.resolve() / requested.name
        if path.exists() or path.is_symlink():
            raise ObservationError(f"generated executable already exists: {path}")
        result[name] = {"path": str(path), "sha256": None}
    return result


def _matching_image(image, expected):
    return (image["executable_path"] == expected["path"] and
            (expected["sha256"] is None or
             image["executable_sha256"] == expected["sha256"]) and
            all(value in image["argv"] for value in expected.get("argv_contains", [])))


def _limits(run):
    limits = run.get("limits", {"processes": DEFAULT_PROCESSES,
                                "events": DEFAULT_EVENTS, "log_bytes": DEFAULT_LOG_BYTES})
    if (not isinstance(limits, dict) or set(limits) != {"processes", "events", "log_bytes"}
            or any(type(limits[key]) is not int or not floor <= limits[key] <= cap
                   for key, floor, cap in (("processes", 1, MAX_PROCESSES),
                                           ("events", DEFAULT_EVENTS, MAX_EVENTS),
                                           ("log_bytes", DEFAULT_LOG_BYTES, MAX_LOG_BYTES)))):
        raise ObservationError("observer process, event, or log limit is invalid")
    return limits


def _derive(rows):
    if not rows or rows[0]["kind"] != "run" or rows[-1]["kind"] != "end":
        raise ObservationError("run start or end event is missing")
    if rows[-2]["kind"] != "archive" or any(
            type(row["observed_at_ns"]) is not int or row["observed_at_ns"] <= 0 or
            row["observed_at_ns"] > following["observed_at_ns"]
            for row, following in zip(rows, rows[1:])):
        raise ObservationError("event time or archive seal order differs")
    run, end = rows[0], rows[-1]
    limits = _limits(run)
    if len(rows) > limits["events"]:
        raise ObservationError("observer event limit exceeded")
    if end["result"] != "observed" or type(end["lost_events"]) is not int or end["lost_events"] != 0:
        raise ObservationError("observation ended with an error or lost events")
    if any(row["kind"] == "error" for row in rows):
        raise ObservationError("observation error is present")
    boot = run["boot_id"]
    root = run["root_pid"]
    identities = {}
    parents = {}
    images = {}
    exits = {}
    reaped = {}
    pending = {}
    archive = None
    for row in rows[1:-1]:
        kind = row["kind"]
        pid = row.get("pid")
        if kind == "spawn":
            if pid in identities or len(identities) >= limits["processes"]:
                raise ObservationError("duplicate or excessive process creation")
            if row["boot_id"] != boot or type(row["start_ticks"]) is not int:
                raise ObservationError("invalid process start identity")
            parent = row["parent_pid"]
            if pid != root and parent not in identities:
                raise ObservationError("unobserved process ancestry")
            identities[pid] = (boot, row["start_ticks"])
            parents[pid] = parent
            images[pid] = []
        elif kind == "image":
            if pid not in identities or (row["boot_id"], row["start_ticks"]) != identities[pid]:
                raise ObservationError("wrong PID-start image identity")
            if pid in exits or not row["argv"] or not SHA.fullmatch(row["executable_sha256"]):
                raise ObservationError("invalid observed image")
            images[pid].append(row)
        elif kind == "exit":
            if pid not in identities or (row["boot_id"], row["start_ticks"]) != identities[pid]:
                raise ObservationError("wrong PID-start exit identity")
            if pid in exits or not images[pid]:
                raise ObservationError("process exited without a captured image")
            exits[pid] = row
            pending[pid] = {"exit_code": row["exit_code"], "signal": row["signal"]}
        elif kind == "reap":
            if pid not in pending or pid in reaped or _status(row["wait_status"]) != pending[pid]:
                raise ObservationError("missing or mismatched process exit")
            reaped[pid] = row
        elif kind == "archive":
            if archive is not None or set(identities) != set(reaped) or not SHA.fullmatch(
                    row["archive_sha256"]):
                raise ObservationError("archive was not sealed after all process exits")
            archive = row
        else:
            raise ObservationError(f"unknown event kind: {kind}")
    if set(identities) != set(exits) or set(exits) != set(reaped):
        raise ObservationError("missing process image, exit, or reap")
    if root not in images or not images[root]:
        raise ObservationError("observed root process image is missing")
    if archive is None:
        raise ObservationError("archive digest is missing")
    build_images = [(pid, image) for pid, process_images in images.items()
                    for image in process_images if image["origin"] == "exec" and
                    _matching_image(image, run["build"])]
    if not build_images:
        raise ObservationError("wrong expected build executable")
    build_pid, build_image = min(build_images, key=lambda pair: pair[1]["seq"])

    def descends_from(pid, ancestor):
        while pid != root and pid != ancestor:
            pid = parents[pid]
        return pid == ancestor

    selected = {}
    used = set()
    for name, expected in run["expected_processes"].items():
        matches = [(pid, image) for pid, process_images in images.items()
                   for image in process_images if pid != root and pid != build_pid and
                   descends_from(pid, build_pid) and
                   image["origin"] == "exec" and _matching_image(image, expected)
                   and pid not in used]
        if not matches:
            raise ObservationError(f"expected executable was not observed: {name}")
        pid, image = min(matches, key=lambda pair: pair[1]["seq"])
        used.add(pid)
        selected[name] = image
    if any(exits[pid]["exit_code"] != 0 for pid in identities):
        raise ObservationError("observed process exited unsuccessfully")
    def process(image):
        pid = image["pid"]
        return {"pid": pid, "parent_pid": next(row["parent_pid"] for row in rows
                if row["kind"] == "spawn" and row["pid"] == pid),
                "boot_id": boot, "start_ticks": image["start_ticks"],
                "executable_path": image["executable_path"],
                "executable_dev": image["executable_dev"],
                "executable_ino": image["executable_ino"],
                "executable_sha256": image["executable_sha256"],
                "argv": image["argv"], "started_ns": image["observed_at_ns"],
                "finished_ns": exits[pid]["observed_at_ns"],
                "exit_code": exits[pid]["exit_code"], "signal": exits[pid]["signal"]}
    result = {"schema": WITNESS_SCHEMA, "status": "OBSERVED_UNSIGNED",
              "qualification": "unqualified", "candidate_sha": run["candidate_sha"],
              "lane": run["lane"], "archive_sha256": archive["archive_sha256"],
              "runtime_identity": run["runtime_identity"], "mode": run["mode"],
              "staged_artifacts": run["staged_artifacts"],
              "executables": {name: image["executable_sha256"] for name, image in selected.items()},
              "auditor": "independent-linux-ptrace-observer/1",
              "build": process(build_image),
              "processes": {name: process(image) for name, image in selected.items()},
              "coverage": {"processes": len(identities),
                           "images": sum(map(len, images.values())),
                           "fork_events": len(identities) - 1,
                           "lost_events": end["lost_events"],
                           "event_count": len(rows)},
              "event_log_sha256": rows[-1]["sha256"]}
    return result


def _checked_files(root):
    requested = Path(root).absolute()
    if ".." in requested.parts:
        raise ObservationError("observer root uses path traversal")
    if requested.is_symlink():
        raise ObservationError("observer root is symbolic")
    root = requested.parent.resolve(strict=True) / requested.name
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if set(os.listdir(directory)) != {"events.jsonl", "witness.json"}:
            raise ObservationError("observer output inventory differs")
        result = {}
        for name, limit in (("events.jsonl", MAX_LOG_BYTES),
                            ("witness.json", 1024 * 1024)):
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            except OSError as error:
                raise ObservationError(f"symbolic or inaccessible output: {name}: {error}") from error
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ObservationError(f"symbolic or hardlinked output: {name}")
                if info.st_size > limit:
                    raise ObservationError(f"oversized observer output: {name}")
                with os.fdopen(os.dup(fd), "rb") as source:
                    result[name] = source.read(limit + 1)
                if len(result[name]) > limit or os.fstat(fd).st_size != info.st_size:
                    raise ObservationError(f"changed observer output during read: {name}")
            finally:
                os.close(fd)
        return result
    finally:
        os.close(directory)


def verify(root):
    files = _checked_files(root)
    raw = files["events.jsonl"]
    if not raw.endswith(b"\n"):
        raise ObservationError("event log is truncated or oversized")
    lines = raw.splitlines()
    if not lines or len(lines) > MAX_EVENTS:
        raise ObservationError("event log is empty or oversized")
    previous = ZERO
    rows = []
    for index, line in enumerate(lines, 1):
        row = _parse_json(line)
        if line != _json_bytes(row):
            raise ObservationError(f"changed event bytes at {index}")
        digest = row.pop("sha256", None)
        if row.get("seq") != index or row.get("previous_sha256") != previous:
            raise ObservationError(f"event sequence or chain gap at {index}")
        if digest != hashlib.sha256(_json_bytes(row)).hexdigest():
            raise ObservationError(f"changed event bytes at {index}")
        row["sha256"] = digest
        rows.append(row)
        previous = digest
    if len(raw) > _limits(rows[0])["log_bytes"]:
        raise ObservationError("observer event log byte limit exceeded")
    witness_raw = files["witness.json"]
    witness = _parse_json(witness_raw)
    if witness_raw != _json_bytes(witness) + b"\n":
        raise ObservationError("changed witness bytes")
    try:
        reconstructed = _derive(rows)
    except (KeyError, IndexError, TypeError, OverflowError) as error:
        raise ObservationError(f"incomplete event structure: {error}") from error
    if witness != reconstructed:
        raise ObservationError("witness differs from observed event log")
    return witness


def _launch(argv, pipe):
    try:
        _ptrace(PTRACE_TRACEME, 0)
        os.kill(os.getpid(), signal.SIGSTOP)
        os.execvpe(argv[0], argv, os.environ)
    except BaseException as error:
        os.write(pipe, f"{type(error).__name__}: {error}".encode())
        os._exit(125)


def _capture(args, deadline):
    if sys.platform != "linux":
        raise ObservationError("ptrace observer requires Linux")
    if not args.argv:
        raise ObservationError("command argv is empty")
    if args.argv[0] == "--":
        args.argv = args.argv[1:]
    if not args.argv:
        raise ObservationError("command argv is empty")
    if not COMMIT.fullmatch(args.candidate_sha):
        raise ObservationError("candidate SHA must have 40 lowercase hex characters")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        raise ObservationError("trace timeout must be finite and positive")
    if args.timeout > MAX_SECONDS:
        raise ObservationError(f"trace timeout exceeds {MAX_SECONDS} seconds")
    if not args.lane or not args.runtime_identity or not args.mode:
        raise ObservationError("lane, runtime identity, and mode are required")
    limits = _limits({"limits": {"processes": getattr(args, "max_processes", DEFAULT_PROCESSES),
                                 "events": getattr(args, "max_events", DEFAULT_EVENTS),
                                 "log_bytes": getattr(args, "max_log_bytes", DEFAULT_LOG_BYTES)}})
    generated = getattr(args, "generated_expect", [])
    markers = getattr(args, "build_argv_contains", [])
    if (len(args.argv) > 256 or sum(map(len, args.argv)) > 65536 or
            len(args.expect) + len(generated) > 32 or len(markers) > 8 or
            any(not marker or len(marker) > 256 for marker in markers)):
        raise ObservationError("command or expected process limit exceeded")
    expected = _expected(args.expect, deadline)
    expected.update(_generated_expected(generated, expected))
    if not expected:
        raise ObservationError("at least one child executable is required")
    build_path = Path(args.build_executable or args.argv[0]).resolve(strict=True)
    build = {"path": str(build_path), "sha256": _sha_file(build_path, deadline),
             "argv_contains": markers}
    artifacts = {}
    for item in args.artifact:
        if "=" not in item:
            raise ObservationError("artifact must be NAME=PATH")
        name, path = item.split("=", 1)
        if name in artifacts or not name:
            raise ObservationError("duplicate or empty artifact name")
        artifacts[name] = _sha_file(_safe_input(path), deadline)
    log = EventLog(args.output, limits["events"], limits["log_bytes"])
    root_pid = None
    live = set()
    pending = {}
    known = {}
    initial_stop = set()
    early_stops = set()
    error = None
    current_stop = None
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    read_pipe, write_pipe = os.pipe2(os.O_CLOEXEC)
    try:
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
        try:
            root_pid = os.fork()
            if root_pid == 0:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
                os.close(read_pipe)
                _launch(args.argv, write_pipe)
            live.add(root_pid)
        finally:
            if root_pid != 0:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        os.close(write_pipe)
        log.add("run", root_pid=root_pid, boot_id=boot,
                candidate_sha=args.candidate_sha, lane=args.lane,
                runtime_identity=args.runtime_identity, mode=args.mode,
                archive_path=str(Path(args.archive).absolute()), staged_artifacts=artifacts,
                build=build, expected_processes=expected, requested_argv=args.argv,
                limits=limits)
        while live:
            if log.count >= limits["events"] - 2:
                raise ObservationError("event limit exceeded")
            if time.monotonic() > deadline:
                raise ObservationError(f"trace timeout after {args.timeout} seconds")
            try:
                pid, status = os.waitpid(-1, WAIT_ALL | os.WNOHANG)
            except ChildProcessError as exc:
                raise ObservationError("tracee disappeared before a recorded exit") from exc
            if pid == 0:
                time.sleep(0.001)
                continue
            if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                terminal = _status(status)
                if pid in known and pid not in pending:
                    log.add("exit", pid=pid, boot_id=boot,
                            start_ticks=known[pid], origin="terminal_wait", **terminal)
                    pending[pid] = terminal
                if pid not in pending or terminal != pending[pid]:
                    detail = os.read(read_pipe, 4096).decode(errors="replace") if pid == root_pid else ""
                    raise ObservationError(f"pid {pid} exited without observed exit: {detail}")
                log.add("reap", pid=pid, wait_status=status)
                live.discard(pid)
                continue
            if not os.WIFSTOPPED(status):
                raise ObservationError(f"unrecognized wait status for pid {pid}: {status}")
            sig = os.WSTOPSIG(status)
            event = status >> 16
            current_stop = {"pid": pid, "event": event, "signal": sig, "wait_status": status}
            if pid == root_pid and pid not in known:
                if sig != signal.SIGSTOP:
                    raise ObservationError("root did not stop before exec")
                identity = _identity(pid, boot)
                known[pid] = identity["start_ticks"]
                log.add("spawn", **identity, origin="traceme")
                _ptrace(PTRACE_SETOPTIONS, pid, OPTIONS)
                _ptrace(PTRACE_CONT, pid)
                continue
            if pid in initial_stop:
                if sig != signal.SIGSTOP:
                    raise ObservationError(f"new pid {pid} missed its initial stop")
                initial_stop.remove(pid)
                _ptrace(PTRACE_SETOPTIONS, pid, OPTIONS)
                image = _image(pid, deadline)
                if image["start_ticks"] != known[pid]:
                    raise ObservationError(f"new pid {pid} changed start identity")
                log.add("image", boot_id=boot, origin="fork", **image)
                _ptrace(PTRACE_CONT, pid)
                continue
            if pid not in known and sig == signal.SIGSTOP and event == 0:
                if pid in early_stops:
                    raise ObservationError(f"duplicate unregistered stop for pid {pid}")
                early_stops.add(pid)
                continue
            if pid not in known or pid in pending:
                raise ObservationError(f"unregistered or exited tracee: {pid}")
            if sig == signal.SIGTRAP and event in (EVENT_FORK, EVENT_VFORK, EVENT_CLONE):
                child = _event_pid(pid)
                live.add(child)
                if child in known or len(known) >= limits["processes"]:
                    raise ObservationError("duplicate or excessive traced child")
                identity = _identity(child, boot)
                known[child] = identity["start_ticks"]
                initial_stop.add(child)
                log.add("spawn", pid=child, boot_id=boot,
                        start_ticks=identity["start_ticks"], parent_pid=pid,
                        observed_parent_pid=identity["parent_pid"],
                        origin={EVENT_FORK: "fork", EVENT_VFORK: "vfork",
                                EVENT_CLONE: "clone"}[event])
                if child in early_stops:
                    early_stops.remove(child)
                    initial_stop.remove(child)
                    _ptrace(PTRACE_SETOPTIONS, child, OPTIONS)
                    image = _image(child, deadline)
                    if image["start_ticks"] != known[child]:
                        raise ObservationError(f"new pid {child} changed start identity")
                    log.add("image", boot_id=boot, origin="fork", **image)
                    _ptrace(PTRACE_CONT, child)
            elif sig == signal.SIGTRAP and event == EVENT_EXEC:
                image = _image(pid, deadline)
                if image["start_ticks"] != known[pid]:
                    raise ObservationError(f"pid {pid} changed start identity at exec")
                log.add("image", boot_id=boot, origin="exec", **image)
            elif sig == signal.SIGTRAP and event == EVENT_EXIT:
                try:
                    identity = _identity(pid, boot)
                    if identity["start_ticks"] != known[pid]:
                        raise ObservationError(f"pid {pid} changed start identity at exit")
                    state = _status(_event_pid(pid))
                except ProcessLookupError:
                    pass
                else:
                    pending[pid] = state
                    log.add("exit", pid=pid, boot_id=boot,
                            start_ticks=identity["start_ticks"], origin="ptrace_exit", **state)
            elif event:
                raise ObservationError(f"unsupported ptrace event {event} for pid {pid}")
            _continue_tracee(pid, event, sig)
        observed_images = [row for row in log.rows if row["kind"] == "image"]
        if not any(row["origin"] == "exec" and _matching_image(row, build)
                   for row in observed_images):
            raise ObservationError("wrong expected build executable")
        for name, image_expected in expected.items():
            if not any(row["pid"] != root_pid and row["origin"] == "exec" and
                       _matching_image(row, image_expected) for row in observed_images):
                raise ObservationError(f"expected executable was not observed: {name}")
        if any(row["kind"] == "exit" and row["exit_code"] != 0 for row in log.rows):
            raise ObservationError("observed process exited unsuccessfully")
        if early_stops or initial_stop:
            raise ObservationError("unmatched child stop or missing process image")
        log.add("archive", archive_path=str(Path(args.archive).absolute()),
                archive_sha256=_archive_digest(args.archive, deadline))
    except BaseException as exc:
        error = exc
        lost_events = int(bool(live))
        message = f"{type(exc).__name__}: {exc}"
        if len(message) > 256:
            message = message[:253] + "..."
        log.add("error", message=message,
                errno=getattr(exc, "errno", None), lost_events=lost_events,
                current_stop=current_stop)
    finally:
        live.update(early_stops)
        for pid in list(live):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for pid in list(live):
            try:
                os.waitpid(pid, WAIT_ALL)
            except (ChildProcessError, OSError):
                pass
        os.close(read_pipe)
        log.add("end", result="failed" if error else "observed",
                lost_events=lost_events if error else 0)
        log.close()
    if error:
        raise ObservationError(f"capture failed; event log retained at {log.root}: {error}") from error
    rows = [_parse_json(line) for line in (log.root / "events.jsonl").read_bytes().splitlines()]
    witness = _derive(rows)
    fd = os.open(log.root / "witness.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        raw = _json_bytes(witness) + b"\n"
        if os.write(fd, raw) != len(raw):
            raise ObservationError("short witness write")
        os.fsync(fd)
    finally:
        os.close(fd)
    return verify(log.root)


def capture(args):
    if sys.platform != "linux":
        raise ObservationError("ptrace observer requires Linux")
    if not math.isfinite(args.timeout) or args.timeout <= 0 or args.timeout > MAX_SECONDS:
        raise ObservationError(f"trace timeout must be finite and within {MAX_SECONDS} seconds")
    if threading.current_thread() is not threading.main_thread():
        raise ObservationError("trace timeout requires the observer main thread")
    if signal.SIGALRM in signal.pthread_sigmask(signal.SIG_BLOCK, set()):
        raise ObservationError("observer wall-clock timer signal is blocked")
    if any(signal.getitimer(signal.ITIMER_REAL)):
        raise ObservationError("observer requires an unused wall-clock timer")
    previous_handler = signal.getsignal(signal.SIGALRM)

    def expired(_signum, _frame):
        raise ObservationError(f"trace timeout after {args.timeout} seconds")

    signal.signal(signal.SIGALRM, expired)
    try:
        deadline = time.monotonic() + args.timeout
        signal.setitimer(signal.ITIMER_REAL, args.timeout)
        return _capture(args, deadline)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Capture unsigned Linux process images")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("capture")
    run.add_argument("--output", required=True)
    run.add_argument("--candidate-sha", required=True)
    run.add_argument("--lane", required=True)
    run.add_argument("--runtime-identity", required=True)
    run.add_argument("--mode", required=True)
    run.add_argument("--archive", required=True)
    run.add_argument("--build-executable")
    run.add_argument("--build-argv-contains", action="append", default=[])
    run.add_argument("--artifact", action="append", default=[])
    run.add_argument("--expect", action="append", default=[])
    run.add_argument("--expect-generated", dest="generated_expect", action="append", default=[])
    run.add_argument("--timeout", type=float, default=20)
    run.add_argument("--max-processes", type=int, default=DEFAULT_PROCESSES)
    run.add_argument("--max-events", type=int, default=DEFAULT_EVENTS)
    run.add_argument("--max-log-bytes", type=int, default=DEFAULT_LOG_BYTES)
    run.add_argument("argv", nargs=argparse.REMAINDER)
    check = commands.add_parser("verify")
    check.add_argument("root")
    args = parser.parse_args(argv)
    try:
        result = capture(args) if args.command == "capture" else verify(args.root)
    except (OSError, ValueError) as error:
        print(f"OBSERVATION_FAILED: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": result["status"], "root": args.output if
                      args.command == "capture" else args.root,
                      "event_log_sha256": result["event_log_sha256"],
                      "coverage": result["coverage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
