#!/usr/bin/env python3
import argparse
import ctypes
import fnmatch
import hashlib
import itertools
import json
import os
import platform
import re
import selectors
import signal
import stat
import subprocess
import threading
import time
import uuid
from pathlib import Path

import full_hosted
import safari_reporter


ROOT = Path(__file__).resolve().parents[2]
TRACKED_LOCK = Path("kotlin-js-store/yarn.lock")
GENERATED_LOCK = Path("build/js/yarn.lock")
SOURCE_INPUTS = (Path("build.gradle.kts"), Path("settings.gradle.kts"),
                 Path("gradle/wrapper/gradle-wrapper.properties"))
HOSTED_SOURCE_INPUTS = (Path("tools/qualification/full_hosted.py"),
                        Path("dyn4k-core/build.gradle.kts"),
                        Path("dyn4k/build.gradle.kts"),
                        Path("tools/qualification/safari-launch.sh"),
                        Path(".github/workflows/safari-yarn-lock-diagnostic.yml"),
                        Path("tools/qualification/safari_reporter.py"),
                        Path("tools/qualification/safari_windows_file.py"),
                        Path("tools/qualification/safari-karma-reporter.js"))
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PACKAGES = 128
MAX_PROCESS_SECONDS = 600
MAX_DRAIN_SECONDS = 5
WINDOWS_KILL_JOB_ON_CLOSE = 0x00002000
WINDOWS_CREATE_SUSPENDED = 0x00000004
REQUIRED_PACKAGES = ("dyn4k-dyn4k-core", "dyn4k-dyn4k-core-test",
                     "dyn4k-dyn4k", "dyn4k-dyn4k-test")
REQUIRED_PACKAGE_INPUTS = (Path("build/js/package.json"),) + tuple(
    Path("build/js/packages") / name / "package.json" for name in REQUIRED_PACKAGES)
CONTEXT_ROOTS = (Path("build/js/packages/dyn4k-dyn4k-core-test"),
                 Path("build/js/packages/dyn4k-dyn4k-test"))
CONTEXT_MAX_FILES = 16
CONTEXT_MAX_FILE_BYTES = 256 * 1024
CONTEXT_MAX_TOTAL_BYTES = 1024 * 1024
CONTEXT_MAX_ENTRIES = 2048
CONTEXT_MAX_DEPTH = 16
CONTEXT_MAX_SECONDS = 15
CONTEXT_MAX_LAUNCHES = 8
CONTEXT_MAX_RAW_ENTRIES = 128
CONTEXT_MAX_UPLOAD_BYTES = 2 * 1024 * 1024
CONTEXT_MAX_INVENTORY_BYTES = 256 * 1024
LOCK_ERROR_LINE = ("> Lock file was changed. Run the `kotlinUpgradeYarnLock` task "
                   "to actualize lock file")
HOSTED_TASK_MARKERS = (b"> Task :dyn4k-core:jsTestPackageJson",
                       b"> Task :dyn4k:jsTestPackageJson",
                       b"> Task :kotlinNpmInstall")


def hosted_task_markers(process):
    final = (b"> Task :kotlinStoreYarnLock" if process.get("exit_code") == 0
             else b"> Task :kotlinStoreYarnLock FAILED")
    return (*HOSTED_TASK_MARKERS, final)


def safari_capture_timeout(stdout, stderr):
    return (b"Safari has not captured in 60000 ms, killing." in stdout
            and re.search(rb"(?m)^> Task :(?:dyn4k-core|dyn4k):jsBrowserTest FAILED\r?$",
                          stdout) is not None
            and re.search(rb"Safari failed \d+ times \(timeout\)\. Giving up\.",
                          stderr) is not None
            and b"Errors occurred during launch of browser for testing." in stderr)


def safari_output_overflow(stdout, stderr):
    return (re.search(rb"(?m)^> Task :(?:dyn4k-core|dyn4k):jsBrowserTest FAILED\r?$",
                      stdout) is not None
            and b"##teamcity[testFailed name='overflow-message'" in stderr
            and b"Cannot process output: too long teamcity service message "
            b"(more than 1Mb). Event was lost." in stderr)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture_karma_context(repository, candidate_sha, context, raw_context):
    repository = repository.resolve()
    windows = os.name == "nt"
    if windows:
        from safari_windows_file import FILE_ATTRIBUTE_REPARSE_POINT, LockedDirectory
    if re.fullmatch(r"[0-9a-f]{40}", candidate_sha) is None:
        raise ValueError("invalid Safari context candidate SHA")
    if (context.is_symlink() or context.resolve().is_relative_to(repository)
            or raw_context.resolve() == context.resolve()
            or raw_context.resolve().is_relative_to(context.resolve())
            or context.resolve().is_relative_to(raw_context.resolve())
            or raw_context.resolve().is_relative_to(repository)):
        raise ValueError("Safari upload context must be a separate external directory")
    context.mkdir(parents=True)
    inventory = {"schema": 1, "candidate_sha": candidate_sha, "qualified": False,
                 "status": "CONTEXT_INCOMPLETE", "inputs": [],
                 "limits": {"files": CONTEXT_MAX_FILES,
                            "file_bytes": CONTEXT_MAX_FILE_BYTES,
                            "total_bytes": CONTEXT_MAX_TOTAL_BYTES,
                            "upload_bytes": CONTEXT_MAX_UPLOAD_BYTES,
                            "inventory_bytes": CONTEXT_MAX_INVENTORY_BYTES,
                            "raw_entries": CONTEXT_MAX_RAW_ENTRIES,
                            "entries": CONTEXT_MAX_ENTRIES,
                            "depth": CONTEXT_MAX_DEPTH,
                            "seconds": CONTEXT_MAX_SECONDS,
                            "launches": CONTEXT_MAX_LAUNCHES},
                 "entries_seen": 0, "matched_files": 0,
                 "copied_files": 0, "copied_bytes": 0,
                 "upload_data_bytes": 0}
    started = time.monotonic()
    deadline = started + CONTEXT_MAX_SECONDS
    incomplete = False
    config = context / "config"
    seen_files = set()
    copied_configs = set()
    reporter_source = None

    def record(path, status, reason, **details):
        nonlocal incomplete
        inventory["inputs"].append({"path": str(path), "status": status,
                                    "reason": reason, **details})
        if status in ("failed", "truncated") or reason not in ("copied", "excluded_node_modules"):
            incomplete = True

    def check_deadline(path):
        if time.monotonic() >= deadline:
            record(path, "failed", "traversal_deadline")
            raise TimeoutError("Safari context traversal deadline")

    def scan(directory):
        return os.scandir(directory.path if windows else directory)

    def close_directory(directory):
        directory.close() if windows else os.close(directory)

    def open_file(directory, name):
        if windows:
            return directory.open_file(name)
        return os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                       dir_fd=directory)

    def open_child(directory, name):
        if windows:
            return directory.child(name)
        return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                       dir_fd=directory)

    def visit(directory_fd, relative, depth, seen_files):
        check_deadline(relative)
        with scan(directory_fd) as entries:
            for entry in entries:
                path = relative / entry.name
                inventory["entries_seen"] += 1
                if inventory["entries_seen"] > CONTEXT_MAX_ENTRIES:
                    record(path, "failed", "entry_count_limit")
                    raise ValueError("Safari context entry count limit")
                check_deadline(path)
                if entry.name == "node_modules":
                    record(path, "skipped", "excluded_node_modules")
                    continue
                if (entry.is_symlink() or windows and
                        entry.stat(follow_symlinks=False).st_file_attributes &
                        FILE_ATTRIBUTE_REPARSE_POINT):
                    record(path, "skipped", "symlink")
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if depth >= CONTEXT_MAX_DEPTH:
                        record(path, "failed", "depth_limit")
                        raise ValueError("Safari context depth limit")
                    child_fd = open_child(directory_fd, entry.name)
                    try:
                        visit(child_fd, path, depth + 1, seen_files)
                    finally:
                        close_directory(child_fd)
                    continue
                if not fnmatch.fnmatchcase(entry.name, "*karma*.js"):
                    continue
                inventory["matched_files"] += 1
                if inventory["matched_files"] > CONTEXT_MAX_FILES:
                    record(path, "failed", "file_count_limit")
                    raise ValueError("Safari context file count limit")
                source_fd = open_file(directory_fd, entry.name)
                try:
                    before = os.fstat(source_fd)
                    if not stat.S_ISREG(before.st_mode):
                        record(path, "skipped", "non_regular")
                        continue
                    identity = (before.st_dev, before.st_ino)
                    if identity in seen_files:
                        record(path, "skipped", "duplicate_inode")
                        continue
                    seen_files.add(identity)
                    remaining = min(CONTEXT_MAX_TOTAL_BYTES - inventory["copied_bytes"],
                                    CONTEXT_MAX_UPLOAD_BYTES - CONTEXT_MAX_INVENTORY_BYTES
                                    - inventory["upload_data_bytes"])
                    if remaining <= 0:
                        record(path, "skipped", "total_byte_limit",
                               original_size=before.st_size, retained_size=0)
                        continue
                    limit = min(before.st_size, CONTEXT_MAX_FILE_BYTES, remaining)
                    chunks = []
                    size = 0
                    while size < limit:
                        check_deadline(path)
                        chunk = os.read(source_fd, min(64 * 1024, limit - size))
                        if not chunk:
                            break
                        chunks.append(chunk)
                        size += len(chunk)
                    after = os.fstat(source_fd)
                    if (size != limit or (before.st_dev, before.st_ino, before.st_size,
                                          before.st_mtime_ns)
                            != (after.st_dev, after.st_ino, after.st_size,
                                after.st_mtime_ns)):
                        record(path, "failed", "source_changed_during_copy")
                        continue
                    data = b"".join(chunks)
                    destination = config / path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination_guard = (LockedDirectory(context, Path("config") / path.parent,
                                                         resolve_root=False)
                                         if windows else None)
                    try:
                        destination_fd = os.open(destination,
                                                 os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                                 getattr(os, "O_NOFOLLOW", 0), 0o600)
                        try:
                            with os.fdopen(destination_fd, "wb") as stream:
                                stream.write(data)
                        except BaseException:
                            destination.unlink(missing_ok=True)
                            raise
                    finally:
                        if destination_guard is not None:
                            destination_guard.close()
                    inventory["copied_files"] += 1
                    inventory["copied_bytes"] += size
                    inventory["upload_data_bytes"] += size
                    status = "truncated" if size < before.st_size else "copied"
                    if status == "copied":
                        copied_configs.add(path)
                    reason = ("per_file_byte_limit" if status == "truncated"
                              and CONTEXT_MAX_FILE_BYTES <= remaining
                              else "total_byte_limit" if status == "truncated" else "copied")
                    record(path, status, reason, original_size=before.st_size,
                           retained_size=size, sha256=hashlib.sha256(data).hexdigest())
                finally:
                    os.close(source_fd)

    def copy_sidecar(directory_fd, name, seen_files):
        check_deadline(name)
        try:
            source_fd = open_file(directory_fd, name)
        except (OSError, ValueError) as error:
            record(name, "failed", "missing_or_unreadable_sidecar",
                   original_size=None, retained_size=0, error=str(error))
            return
        original_size = None
        try:
            before = os.fstat(source_fd)
            original_size = before.st_size
            if not stat.S_ISREG(before.st_mode):
                record(name, "failed", "non_regular_sidecar",
                       original_size=before.st_size, retained_size=0)
                return
            identity = (before.st_dev, before.st_ino)
            if identity in seen_files:
                record(name, "failed", "duplicate_sidecar_inode",
                       original_size=before.st_size, retained_size=0)
                return
            seen_files.add(identity)
            remaining = max(0, CONTEXT_MAX_UPLOAD_BYTES - CONTEXT_MAX_INVENTORY_BYTES
                            - inventory["upload_data_bytes"])
            limit = min(before.st_size, CONTEXT_MAX_FILE_BYTES, remaining)
            chunks = []
            size = 0
            while size < limit:
                check_deadline(name)
                chunk = os.read(source_fd, min(64 * 1024, limit - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
            after = os.fstat(source_fd)
            if (size != limit or (before.st_dev, before.st_ino, before.st_size,
                                  before.st_mtime_ns)
                    != (after.st_dev, after.st_ino, after.st_size,
                        after.st_mtime_ns)):
                record(name, "failed", "sidecar_changed_during_copy",
                       original_size=before.st_size, retained_size=0)
                return
            data = b"".join(chunks)
            destination = context / name
            destination_guard = (LockedDirectory(context, resolve_root=False)
                                 if windows else None)
            try:
                destination_fd = os.open(destination,
                                         os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                         getattr(os, "O_NOFOLLOW", 0), 0o600)
                try:
                    with os.fdopen(destination_fd, "wb") as stream:
                        stream.write(data)
                except BaseException:
                    destination.unlink(missing_ok=True)
                    raise
            finally:
                if destination_guard is not None:
                    destination_guard.close()
            inventory["upload_data_bytes"] += size
            status = "truncated" if size < before.st_size else "copied"
            reason = ("per_file_byte_limit" if status == "truncated"
                      and CONTEXT_MAX_FILE_BYTES <= remaining
                      else "upload_byte_limit" if status == "truncated" else "copied")
            record(name, status, reason, original_size=before.st_size,
                   retained_size=size, sha256=hashlib.sha256(data).hexdigest())
        except OSError as error:
            record(name, "failed", "sidecar_copy_failed",
                   original_size=original_size, retained_size=0, error=str(error))
        finally:
            os.close(source_fd)

    try:
        require_candidate(repository, candidate_sha)
        reporter_source = safari_reporter.committed_fragment(repository, candidate_sha)
        inventory["reporter_source_sha256"] = hashlib.sha256(reporter_source).hexdigest()
        if config.exists() or config.is_symlink():
            raise ValueError("Safari context config destination already exists")
        config.mkdir()
        for root in CONTEXT_ROOTS:
            check_deadline(root)
            if windows:
                try:
                    directory_fd = LockedDirectory(repository, root)
                except (OSError, ValueError) as error:
                    record(root, "skipped", "missing_or_unsafe_root", error=str(error))
                    continue
                try:
                    visit(directory_fd, root, len(root.parts), seen_files)
                finally:
                    close_directory(directory_fd)
                continue
            directory_fd = os.open(repository, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                try:
                    for part in root.parts:
                        child_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                           dir_fd=directory_fd)
                        os.close(directory_fd)
                        directory_fd = child_fd
                except OSError as error:
                    record(root, "skipped", "missing_or_unsafe_root", error=str(error))
                    continue
                visit(directory_fd, root, len(root.parts), seen_files)
            finally:
                os.close(directory_fd)
        if inventory["copied_files"] == 0:
            record("config", "failed", "no_karma_config")
        for root in CONTEXT_ROOTS:
            required_config = root / "karma.conf.js"
            if required_config not in copied_configs:
                record(required_config, "failed", "missing_module_karma_config")
        modes = set()
        for project, root in ((Path("dyn4k-core"), CONTEXT_ROOTS[0]),
                              (Path("dyn4k"), CONTEXT_ROOTS[1])):
            required_config = root / "karma.conf.js"
            if required_config in copied_configs:
                try:
                    modes.add(safari_reporter.validate_config(
                        (config / required_config).read_bytes(), reporter_source,
                        repository, project))
                except safari_reporter.ConfigBindingError as error:
                    record(required_config, "failed", str(error))
        if len(modes) > 1:
            record("config", "failed", "karma_config_source_mismatch")
        elif len(modes) == 1:
            inventory["configuration"] = next(iter(modes))
        require_candidate(repository, candidate_sha)
    except (OSError, ValueError, TimeoutError) as error:
        record("config", "failed", "scan_failed", error=str(error))
    try:
        if raw_context.is_symlink():
            raise ValueError("symlink Safari raw context")
        directory_fd = (LockedDirectory(raw_context, resolve_root=False) if windows else
                        os.open(raw_context, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
        try:
            with scan(directory_fd) as entries:
                names = [entry.name for entry in itertools.islice(
                    entries, CONTEXT_MAX_RAW_ENTRIES + 1)]
            if len(names) > CONTEXT_MAX_RAW_ENTRIES:
                record("raw_context", "failed", "raw_entry_count_limit")
                names = names[:CONTEXT_MAX_RAW_ENTRIES]
            launches = [name for name in names
                        if re.fullmatch(r"launch-[0-9]+\.txt", name)]
            if len(launches) > CONTEXT_MAX_LAUNCHES:
                record("launch", "failed", "launch_count_limit")
                launches = launches[:CONTEXT_MAX_LAUNCHES]
            if not launches:
                record("launch", "failed", "launcher_not_invoked")
            required = ["session-after.txt", "process-after.txt", "host-outcome.txt"]
            for launch in launches:
                pid = launch.removeprefix("launch-").removesuffix(".txt")
                required.extend((launch, f"process-{pid}.txt", f"redirect-{pid}.html",
                                 f"open-{pid}.stdout", f"open-{pid}.stderr",
                                 f"sample-state-{pid}.txt", f"launch-outcome-{pid}.txt"))
            for name in names:
                if name not in required:
                    record(name, "skipped", "unexpected_sidecar")
            for name in required:
                copy_sidecar(directory_fd, name, seen_files)
        finally:
            close_directory(directory_fd)
        host_outcome = context / "host-outcome.txt"
        if (not host_outcome.is_file() or host_outcome.read_text(errors="replace").splitlines()
                != ["session_exit=0", "process_exit=0"]):
            record("host-outcome.txt", "failed", "host_capture_incomplete")
        for launch in launches:
            pid = launch.removeprefix("launch-").removesuffix(".txt")
            state = context / f"sample-state-{pid}.txt"
            process = context / f"process-{pid}.txt"
            outcome = context / f"launch-outcome-{pid}.txt"
            outcome_text = outcome.read_text(errors="replace") if outcome.is_file() else ""
            if outcome_text == "open_state=pending\n":
                record(launch, "failed", "open_pending")
            if (not state.is_file() or not process.is_file() or not outcome.is_file()
                    or [line for line in process.read_text(errors="replace").splitlines()
                        if line.startswith("sample=")]
                    != [f"sample={number}" for number in range(1, 6)]
                    or (outcome_text != "open_state=pending\n" and not re.fullmatch(
                        r"(?:open_state=finished\n)?open_exit=\d+\n", outcome_text))
                    or state.read_text(errors="replace").splitlines()
                    != ["samples_completed=5", "sampler_exit=0"]):
                record(launch, "failed", "sampler_incomplete")
        require_candidate(repository, candidate_sha)
    except (OSError, ValueError, TimeoutError) as error:
        record("raw_context", "failed", "sidecar_scan_failed", error=str(error))
    inventory["elapsed_seconds"] = time.monotonic() - started
    if not incomplete:
        inventory["status"] = "CONTEXT_COMPLETE"
    encoded = (json.dumps(inventory, indent=2, sort_keys=True) + "\n").encode()
    omitted = 0
    while len(encoded) > CONTEXT_MAX_INVENTORY_BYTES and inventory["inputs"]:
        inventory["inputs"].pop()
        omitted += 1
        inventory["status"] = "CONTEXT_INCOMPLETE"
        inventory["inventory_entries_omitted"] = omitted
        encoded = (json.dumps(inventory, indent=2, sort_keys=True) + "\n").encode()
    if len(encoded) > CONTEXT_MAX_INVENTORY_BYTES:
        raise ValueError("Safari context inventory exceeds its byte bound")
    (context / "inventory.json").write_bytes(encoded)
    return inventory


def git(repository, *args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C", str(repository),
                                    *args], text=True).strip()


def source_path(repository, relative):
    if relative.is_absolute() or not relative.parts or any(
            part in ("", ".", "..") for part in relative.parts):
        raise ValueError(f"unsafe source path: {relative}")
    path = repository
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"symlink source path or ancestor: {relative}")
    if not path.resolve().is_relative_to(repository):
        raise ValueError(f"source path escapes checkout: {relative}")
    return path


def source_bytes(repository, relative):
    path = source_path(repository, relative)
    if os.name == "nt":
        from safari_windows_file import LockedDirectory
        with LockedDirectory(repository, relative.parent) as directory:
            descriptor = directory.open_file(relative.name)
            try:
                before = os.fstat(descriptor)
                if before.st_size > MAX_FILE_BYTES:
                    raise ValueError(f"oversized diagnostic source: {relative}")
                chunks = []
                read_bytes = 0
                while read_bytes < before.st_size:
                    chunk = os.read(descriptor, min(64 * 1024, before.st_size - read_bytes))
                    if not chunk:
                        raise ValueError(f"incomplete diagnostic source: {relative}")
                    chunks.append(chunk)
                    read_bytes += len(chunk)
                if os.read(descriptor, 1):
                    raise ValueError(f"source path identity changed: {relative}")
                data = b"".join(chunks)
                after = os.fstat(descriptor)
                if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                    raise ValueError(f"source path identity changed: {relative}")
                return data
            finally:
                os.close(descriptor)
    directory = os.open(repository, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in relative.parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(relative.parts[-1], os.O_RDONLY | os.O_NOFOLLOW,
                             dir_fd=directory)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError(f"non-regular diagnostic source: {relative}")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                data = stream.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                raise ValueError(f"oversized diagnostic source: {relative}")
            if path.resolve(strict=True) != path:
                raise ValueError(f"source path identity changed: {relative}")
            return data
        finally:
            os.close(descriptor)
    finally:
        os.close(directory)


def source_digest(repository, relative):
    return hashlib.sha256(source_bytes(repository, relative)).hexdigest()


def require_candidate(repository, candidate_sha):
    if git(repository, "rev-parse", "HEAD") != candidate_sha:
        raise ValueError("candidate SHA differs from checkout")
    committed = safari_reporter.committed_bytes(repository, candidate_sha, TRACKED_LOCK)
    if git(repository, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("dirty tracked or untracked source checkout")
    if source_bytes(repository, TRACKED_LOCK) != committed:
        raise ValueError("tracked lock differs from candidate")


def copy_file(repository, relative, output, prefix):
    source = source_path(repository, relative)
    data = source_bytes(repository, relative)
    destination = output / prefix / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return {"path": destination.relative_to(output).as_posix(),
            "sha256": digest(destination), "size": destination.stat().st_size,
            "source_path": str(source), "source_realpath": str(source.resolve(strict=True))}


def lock_failure_signature(stderr):
    lines = stderr.read_text(errors="replace").splitlines()
    if (lines.count("FAILURE: Build failed with an exception.") != 1
            or lines.count("* What went wrong:") != 1):
        return False
    start = lines.index("* What went wrong:") + 1
    end = next((index for index in range(start, len(lines))
                if lines[index].startswith("* ")), len(lines))
    block = [line for line in lines[start:end] if line]
    failures = [line for line in lines if line.startswith("Execution failed")]
    task_failure = (r"Execution failed for task ':kotlinStoreYarnLock' "
                    r"\(registered by plugin class "
                    r"'org\.jetbrains\.kotlin\.gradle\.targets\.js\.yarn\.YarnPlugin'\)\.")
    return (len(block) == 2 and re.fullmatch(task_failure, block[0]) is not None
            and block[1] == LOCK_ERROR_LINE and failures == [block[0]]
            and any(re.fullmatch(r"BUILD FAILED in \d+(?:ms|s|m \d+s)", line)
                    for line in lines))


def full_hosted_command(repository, init, configuration, invocation_id):
    command = [str(repository / "gradlew"), "--no-daemon", "--console=plain",
               "--rerun-tasks", "--init-script", str(init),
               ":dyn4k-core:jsBrowserTest", ":dyn4k:jsBrowserTest",
               f"-PqualificationInvocationId={invocation_id}"]
    if configuration == "production":
        command.append("-PqualificationProduction=true")
    return command


def run_lock_task(repository, output, command=None):
    if command is None:
        wrapper = "gradlew.bat" if os.name == "nt" else "gradlew"
        command = [str(repository / wrapper), "--no-daemon", "--console=plain",
                   "--rerun-tasks", ":kotlinStoreYarnLock"]
    if os.name == "nt":
        return _run_lock_task_windows(repository, output, command)
    with (output / "stdout.txt").open("wb") as stdout, \
            (output / "stderr.txt").open("wb") as stderr:
        return _run_lock_task_posix(repository, command, stdout, stderr)


def _run_lock_task_posix(repository, command, stdout, stderr):
    started = time.time_ns()
    process = subprocess.Popen(command, cwd=repository, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    deadline = time.monotonic() + MAX_PROCESS_SECONDS
    seen = {"stdout": 0, "stderr": 0}
    kept = {"stdout": 0, "stderr": 0}
    timed_out = False
    stream_incomplete = False
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ, ("stdout", stdout))
        selector.register(process.stderr, selectors.EVENT_READ, ("stderr", stderr))
        drain_deadline = None
        while selector.get_map():
            now = time.monotonic()
            if now >= deadline and not timed_out:
                timed_out = True
                drain_deadline = now + MAX_DRAIN_SECONDS
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif process.poll() is not None and drain_deadline is None:
                drain_deadline = now + MAX_DRAIN_SECONDS
            if drain_deadline is not None and now >= drain_deadline:
                stream_incomplete = True
                break
            remaining = (drain_deadline if drain_deadline is not None else deadline) - now
            for key, _ in selector.select(timeout=min(max(remaining, 0), 0.5)):
                name, destination = key.data
                chunk = os.read(key.fd, 64 * 1024)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                seen[name] += len(chunk)
                writable = min(len(chunk), max(0, MAX_FILE_BYTES - kept[name]))
                if writable:
                    destination.write(chunk[:writable])
                    kept[name] += writable
    if process.poll() is None:
        try:
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=MAX_DRAIN_SECONDS)
    process.stdout.close()
    process.stderr.close()
    finished = time.time_ns()
    return {"command": command, "pid": process.pid, "exit_code": process.returncode,
            "started_ns": started, "finished_ns": finished,
            "deadline_seconds": MAX_PROCESS_SECONDS, "timed_out": timed_out,
            "stream_incomplete": stream_incomplete,
            "stdout_bytes_seen": seen["stdout"], "stderr_bytes_seen": seen["stderr"],
            "stdout_truncated": seen["stdout"] > MAX_FILE_BYTES,
            "stderr_truncated": seen["stderr"] > MAX_FILE_BYTES}


def _resume_suspended_windows_process(kernel, process):
    class ThreadEntry(ctypes.Structure):
        _fields_ = (("size", ctypes.c_uint32), ("usage", ctypes.c_uint32),
                    ("thread_id", ctypes.c_uint32), ("owner_pid", ctypes.c_uint32),
                    ("base_priority", ctypes.c_int32), ("delta_priority", ctypes.c_int32),
                    ("flags", ctypes.c_uint32))

    kernel.CreateToolhelp32Snapshot.argtypes = (ctypes.c_uint32, ctypes.c_uint32)
    kernel.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel.Thread32First.argtypes = (ctypes.c_void_p, ctypes.POINTER(ThreadEntry))
    kernel.Thread32First.restype = ctypes.c_int
    kernel.Thread32Next.argtypes = (ctypes.c_void_p, ctypes.POINTER(ThreadEntry))
    kernel.Thread32Next.restype = ctypes.c_int
    kernel.OpenThread.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    kernel.OpenThread.restype = ctypes.c_void_p
    kernel.ResumeThread.argtypes = (ctypes.c_void_p,)
    kernel.ResumeThread.restype = ctypes.c_uint32
    snapshot = kernel.CreateToolhelp32Snapshot(0x00000004, 0)
    if snapshot in (None, ctypes.c_void_p(-1).value):
        raise OSError("cannot snapshot suspended Safari diagnostic thread")
    try:
        entry = ThreadEntry()
        entry.size = ctypes.sizeof(entry)
        if not kernel.Thread32First(snapshot, ctypes.byref(entry)):
            raise OSError("cannot enumerate suspended Safari diagnostic thread")
        threads = []
        deadline = time.monotonic() + MAX_DRAIN_SECONDS
        while True:
            if entry.owner_pid == process.pid:
                threads.append(entry.thread_id)
                if len(threads) != 1:
                    raise OSError("suspended Safari diagnostic has multiple threads")
            if time.monotonic() >= deadline:
                raise TimeoutError("suspended Safari diagnostic thread scan exceeded deadline")
            if not kernel.Thread32Next(snapshot, ctypes.byref(entry)):
                break
        if len(threads) != 1:
            raise OSError("suspended Safari diagnostic primary thread is missing")
        thread = kernel.OpenThread(0x0002, 0, threads[0])
        if not thread:
            raise OSError("cannot open suspended Safari diagnostic primary thread")
        try:
            if kernel.ResumeThread(thread) != 1:
                raise OSError("cannot resume suspended Safari diagnostic primary thread")
        finally:
            kernel.CloseHandle(thread)
    finally:
        kernel.CloseHandle(snapshot)


def _windows_job_active_count(kernel, job):
    class Accounting(ctypes.Structure):
        _fields_ = (("total_user_time", ctypes.c_int64),
                    ("total_kernel_time", ctypes.c_int64),
                    ("period_user_time", ctypes.c_int64),
                    ("period_kernel_time", ctypes.c_int64),
                    ("page_faults", ctypes.c_uint32),
                    ("total_processes", ctypes.c_uint32),
                    ("active_processes", ctypes.c_uint32),
                    ("terminated_processes", ctypes.c_uint32))

    kernel.QueryInformationJobObject.argtypes = (ctypes.c_void_p, ctypes.c_int,
                                                ctypes.c_void_p, ctypes.c_uint32,
                                                ctypes.c_void_p)
    kernel.QueryInformationJobObject.restype = ctypes.c_int
    accounting = Accounting()
    if not kernel.QueryInformationJobObject(job, 1, ctypes.byref(accounting),
                                            ctypes.sizeof(accounting), None):
        raise OSError("cannot query Safari diagnostic Windows job lifetime")
    return accounting.active_processes


def _run_lock_task_windows(repository, output, command):
    with (output / "stdout.txt").open("wb") as stdout, \
            (output / "stderr.txt").open("wb") as stderr:
        return _run_lock_task_windows_opened(repository, command, stdout, stderr)


def _run_lock_task_windows_opened(repository, command, stdout, stderr):
    started = time.time_ns()
    job = None
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
        kernel.CreateJobObjectW.restype = ctypes.c_void_p
        kernel.SetInformationJobObject.argtypes = (ctypes.c_void_p, ctypes.c_int,
                                                  ctypes.c_void_p, ctypes.c_uint32)
        kernel.SetInformationJobObject.restype = ctypes.c_int
        kernel.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        kernel.AssignProcessToJobObject.restype = ctypes.c_int
        kernel.TerminateJobObject.argtypes = (ctypes.c_void_p, ctypes.c_uint)
        kernel.TerminateJobObject.restype = ctypes.c_int
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel.CloseHandle.restype = ctypes.c_int
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise OSError("cannot create Safari diagnostic Windows job")
        class BasicLimits(ctypes.Structure):
            _fields_ = (("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                        ("flags", ctypes.c_uint32), ("minimum_working_set", ctypes.c_size_t),
                        ("maximum_working_set", ctypes.c_size_t),
                        ("active_limit", ctypes.c_uint32), ("affinity", ctypes.c_size_t),
                        ("priority", ctypes.c_uint32), ("scheduling", ctypes.c_uint32))

        class ExtendedLimits(ctypes.Structure):
            _fields_ = (("basic", BasicLimits), ("io_counters", ctypes.c_uint64 * 6),
                        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                        ("peak_process_memory", ctypes.c_size_t),
                        ("peak_job_memory", ctypes.c_size_t))

        limits = ExtendedLimits()
        limits.basic.flags = WINDOWS_KILL_JOB_ON_CLOSE
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits),
                                              ctypes.sizeof(limits)):
            kernel.CloseHandle(job)
            raise OSError("cannot set Safari diagnostic kill-on-close job limit")
    try:
        process = subprocess.Popen(
            command, cwd=repository, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP |
                          (WINDOWS_CREATE_SUSPENDED if job else 0))
    except BaseException:
        if job is not None:
            kernel.CloseHandle(job)
        raise
    if job is not None:
        try:
            if not kernel.AssignProcessToJobObject(job, process._handle):
                raise OSError("cannot assign suspended Safari diagnostic process to Windows job")
            _resume_suspended_windows_process(kernel, process)
        except BaseException as error:
            kernel.TerminateJobObject(job, 1)
            kernel.CloseHandle(job)
            try:
                process.wait(timeout=MAX_DRAIN_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=MAX_DRAIN_SECONDS)
            process.stdout.close()
            process.stderr.close()
            raise OSError("cannot bind Safari diagnostic process before execution") from error

    def terminate_tree():
        if job is not None and kernel.TerminateJobObject(job, 1):
            return
        try:
            killed = subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=MAX_DRAIN_SECONDS, check=False)
            if killed.returncode != 0 and process.poll() is None:
                process.kill()
        except (OSError, subprocess.TimeoutExpired):
            if process.poll() is None:
                process.kill()

    seen = {"stdout": 0, "stderr": 0}
    kept = {"stdout": 0, "stderr": 0}
    reader_errors = []
    timed_out = False
    with stdout, stderr:
        def drain(name, source, destination):
            try:
                while chunk := source.read(64 * 1024):
                    seen[name] += len(chunk)
                    writable = min(len(chunk), max(0, MAX_FILE_BYTES - kept[name]))
                    if writable:
                        destination.write(chunk[:writable])
                        kept[name] += writable
            except Exception as error:
                reader_errors.append(f"{name}: {type(error).__name__}: {error}")

        threads = [threading.Thread(target=drain, args=(name, source, destination),
                                    daemon=True)
                   for name, source, destination in (("stdout", process.stdout, stdout),
                                                     ("stderr", process.stderr, stderr))]
        for thread in threads:
            thread.start()
        try:
            process.wait(timeout=MAX_PROCESS_SECONDS)
        except subprocess.TimeoutExpired:
            timed_out = True
            terminate_tree()
            try:
                process.wait(timeout=MAX_DRAIN_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=MAX_DRAIN_SECONDS)
        for thread in threads:
            thread.join(timeout=MAX_DRAIN_SECONDS)
        stream_incomplete = bool(reader_errors) or any(thread.is_alive() for thread in threads)
        if job is not None:
            try:
                active = _windows_job_active_count(kernel, job)
            except OSError:
                active = 1
            if active:
                stream_incomplete = True
        if stream_incomplete and not timed_out:
            terminate_tree()
            for thread in threads:
                thread.join(timeout=MAX_DRAIN_SECONDS)
    if not any(thread.is_alive() for thread in threads):
        process.stdout.close()
        process.stderr.close()
    if job is not None:
        kernel.CloseHandle(job)
    finished = time.time_ns()
    return {"command": command, "pid": process.pid, "exit_code": process.returncode,
            "started_ns": started, "finished_ns": finished,
            "deadline_seconds": MAX_PROCESS_SECONDS, "timed_out": timed_out,
            "stream_incomplete": stream_incomplete,
            "stdout_bytes_seen": seen["stdout"], "stderr_bytes_seen": seen["stderr"],
            "stdout_truncated": seen["stdout"] > kept["stdout"],
            "stderr_truncated": seen["stderr"] > kept["stderr"]}


def capture_package_graph(repository, output, files, receipt):
    root_package = Path("build/js/package.json")
    packages_root = Path("build/js/packages")
    directory = source_path(repository, packages_root)
    packages = list(itertools.islice(directory.glob("*/package.json"), MAX_PACKAGES + 1)) \
        if directory.is_dir() else []
    too_many = len(packages) > MAX_PACKAGES
    observed = [root_package] if source_path(repository, root_package).is_file() else []
    observed += sorted(path.relative_to(repository) for path in packages[:MAX_PACKAGES])
    receipt["package_inputs_expected"] = [path.as_posix() for path in REQUIRED_PACKAGE_INPUTS]
    receipt["package_inputs_observed"] = [path.as_posix() for path in observed]
    receipt["missing_package_inputs"] = [path.as_posix() for path in REQUIRED_PACKAGE_INPUTS
                                         if path not in observed]
    receipt["unexpected_package_inputs"] = [path.as_posix() for path in observed
                                            if path not in REQUIRED_PACKAGE_INPUTS]
    receipt["package_count_exceeds_bound"] = too_many
    for relative in observed:
        files.append(copy_file(repository, relative, output, "generated"))
    errors = []
    for relative in observed:
        try:
            value = json.loads((output / "generated" / relative).read_text())
        except (UnicodeError, json.JSONDecodeError):
            errors.append(f"invalid JSON: {relative}")
            continue
        if not isinstance(value, dict):
            errors.append(f"invalid package object: {relative}")
        elif relative == root_package:
            expected_workspaces = {f"packages/{name}" for name in REQUIRED_PACKAGES}
            workspaces = value.get("workspaces")
            if value.get("name") != "dyn4k" or not isinstance(workspaces, list) \
                    or not all(isinstance(item, str) for item in workspaces) \
                    or set(workspaces) != expected_workspaces or len(workspaces) != len(expected_workspaces):
                errors.append("root package workspaces differ")
        elif value.get("name") != relative.parent.name:
            errors.append(f"package name differs: {relative}")
    receipt["package_graph_errors"] = errors
    if receipt.get("configuration") in ("development", "production"):
        for name in ("dyn4k-dyn4k-core-test", "dyn4k-dyn4k-test"):
            path = output / "generated/build/js/packages" / name / "package.json"
            try:
                dependency = json.loads(path.read_text())["devDependencies"]["karma-safari-launcher"]
            except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
                dependency = None
            if dependency != "1.0.0":
                errors.append(f"Safari launcher dependency differs: {name}")


def capture(repository, candidate_sha, output, configuration=None):
    repository = repository.resolve()
    output = output.resolve()
    if configuration not in (None, "development", "production"):
        raise ValueError("invalid Safari diagnostic configuration")
    if output.is_relative_to(repository):
        raise ValueError("diagnostic output must be outside the source checkout")
    if output.exists() and any(output.iterdir()):
        raise ValueError("diagnostic output must be empty")
    if (repository / GENERATED_LOCK).exists():
        raise ValueError("preexisting generated lock prevents a fresh diagnosis")
    require_candidate(repository, candidate_sha)
    output.mkdir(parents=True, exist_ok=True)
    files = [copy_file(repository, TRACKED_LOCK, output, "tracked")]
    source_inputs = (TRACKED_LOCK, *SOURCE_INPUTS,
                     *(HOSTED_SOURCE_INPUTS if configuration else ()))
    files += [copy_file(repository, path, output, "inputs") for path in source_inputs[1:]]
    committed_hashes = {path.as_posix(): hashlib.sha256(
        safari_reporter.committed_bytes(repository, candidate_sha, path)).hexdigest()
                        for path in source_inputs}
    captured_hashes = {Path(item["source_path"]).relative_to(repository).as_posix():
                       item["sha256"] for item in files}
    if captured_hashes != committed_hashes:
        raise ValueError("archived source inputs differ from candidate")
    receipt = {"schema": 1, "kind": "safari-yarn-lock-diagnostic",
               "candidate_sha": candidate_sha, "qualified": False,
               "configuration": configuration,
               "repository_root": str(repository), "archive_root": str(output),
               "host": {"system": platform.system(), "machine": platform.machine(),
                        "java_home": os.environ.get("JAVA_HOME"),
                        "runner_image_os": os.environ.get("ImageOS"),
                        "runner_image_version": os.environ.get("ImageVersion")},
               "tracked_sha256": captured_hashes[TRACKED_LOCK.as_posix()],
               "source_input_sha256": committed_hashes}
    expected_command = None
    if configuration:
        init = output / configuration / "qualification.init.gradle"
        init.parent.mkdir()
        init.write_text(full_hosted.init_script("jsSafari", configuration))
        files.append({"path": init.relative_to(output).as_posix(),
                      "sha256": digest(init), "size": init.stat().st_size})
        receipt["invocation_id"] = uuid.uuid4().hex
        expected_command = full_hosted_command(repository, init, configuration,
                                               receipt["invocation_id"])
        receipt["init_script_sha256"] = digest(init)
    reporter_stage = None
    try:
        if configuration:
            with safari_reporter.stage(repository, candidate_sha,
                                       (Path("dyn4k-core"), Path("dyn4k")), output) as reporter_stage:
                process = run_lock_task(repository, output, expected_command)
            receipt["reporter_stage"] = reporter_stage
            for item in reporter_stage["forensic"]:
                if "archive_path" in item:
                    files.append({"path": item["archive_path"], "sha256": item["sha256"],
                                  "size": item["retained_size"]})
        else:
            process = run_lock_task(repository, output)
    except safari_reporter.StageFailure as error:
        for item in error.result["forensic"]:
            if "archive_path" in item:
                files.append({"path": item["archive_path"], "sha256": item["sha256"],
                              "size": item["retained_size"]})
        receipt.update(status="STAGED_REPORTER_CHANGED", reason=str(error),
                       reporter_stage=error.result, files=files)
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2,
                                                       sort_keys=True) + "\n")
        return receipt
    except OSError as error:
        if reporter_stage is not None:
            receipt["reporter_stage"] = reporter_stage
            for item in reporter_stage["forensic"]:
                if "archive_path" in item:
                    files.append({"path": item["archive_path"], "sha256": item["sha256"],
                                  "size": item["retained_size"]})
        for name in ("stdout.txt", "stderr.txt"):
            path = output / name
            try:
                if path.is_file():
                    files.append({"path": name, "sha256": digest(path),
                                  "size": path.stat().st_size})
            except OSError:
                pass
        receipt.update(status="PROCESS_CAPTURE_FAILED", reason=str(error)[:512], files=files)
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2,
                                                       sort_keys=True) + "\n")
        return receipt
    receipt["process"] = process
    for name in ("stdout.txt", "stderr.txt"):
        path = output / name
        if path.is_file():
            files.append({"path": name, "sha256": digest(path), "size": path.stat().st_size})
    receipt["head_after_task"] = git(repository, "rev-parse", "HEAD")
    receipt["tracked_changes_after_task"] = git(repository, "status", "--porcelain=v1",
                                                  "--untracked-files=no")
    try:
        if configuration and digest(output / configuration / "qualification.init.gradle") != receipt["init_script_sha256"]:
            raise ValueError("hosted Safari init script changed during task")
        if source_path(repository, GENERATED_LOCK).is_file():
            files.append(copy_file(repository, GENERATED_LOCK, output, "generated"))
            receipt["generated_sha256"] = digest(output / "generated" / GENERATED_LOCK)
        capture_package_graph(repository, output, files, receipt)
        files.append(copy_file(repository, TRACKED_LOCK, output, "tracked-after"))
        receipt["tracked_after_sha256"] = digest(output / "tracked-after" / TRACKED_LOCK)
        for item in files:
            if item["path"].startswith("generated/") and source_digest(
                    repository, Path(item["source_path"]).relative_to(repository)) != item["sha256"]:
                raise ValueError(f"generated input changed during capture: {item['path']}")
        receipt["source_input_after_sha256"] = {
            path.as_posix(): source_digest(repository, path) for path in source_inputs}
        receipt["head_after"] = git(repository, "rev-parse", "HEAD")
        receipt["tracked_changes_after"] = git(repository, "status", "--porcelain=v1",
                                                 "--untracked-files=no")
        stdout = (output / "stdout.txt").read_bytes()
        lock_succeeded = re.search(rb"(?m)^> Task :kotlinStoreYarnLock\r?$", stdout) is not None
        lock_failed = re.search(rb"(?m)^> Task :kotlinStoreYarnLock FAILED\r?$", stdout) is not None
        if (configuration and receipt["reporter_stage"]["status"] != "CLEAN"):
            receipt["status"] = "STAGED_REPORTER_CHANGED"
        elif (receipt["head_after_task"] != candidate_sha
                or receipt["head_after"] != candidate_sha
                or receipt["tracked_changes_after_task"] or receipt["tracked_changes_after"]
                or receipt["source_input_after_sha256"] != committed_hashes):
            receipt["status"] = "SOURCE_CHANGED"
        elif configuration and (process.get("command") != expected_command
                                or not isinstance(process.get("pid"), int)
                                or process["pid"] <= 0
                                or not isinstance(process.get("started_ns"), int)
                                or not isinstance(process.get("finished_ns"), int)
                                or process["started_ns"] >= process["finished_ns"]
                                or not all(marker in stdout for marker in HOSTED_TASK_MARKERS)
                                or not (lock_succeeded or lock_failed)):
            receipt["status"] = "PROCESS_BINDING_REJECTED"
        elif process.get("timed_out"):
            receipt["status"] = "PROCESS_TIMEOUT"
        elif (process.get("stream_incomplete") or process.get("stdout_truncated")
              or process.get("stderr_truncated") or not (output / "stdout.txt").is_file()
              or not (output / "stderr.txt").is_file()):
            receipt["status"] = "INCOMPLETE_LOG_CAPTURE"
        elif "generated_sha256" not in receipt:
            receipt["status"] = "NO_GENERATED_LOCK"
        elif (receipt["missing_package_inputs"] or receipt["unexpected_package_inputs"]
              or receipt["package_count_exceeds_bound"] or receipt["package_graph_errors"]):
            receipt["status"] = "INCOMPLETE_PACKAGE_GRAPH"
        elif (process["exit_code"] == 0
              and (not configuration or lock_succeeded)
              and receipt["generated_sha256"] == receipt["tracked_sha256"]):
            receipt["status"] = "LOCK_MATCHED_DIAGNOSTIC_ONLY"
        elif (process["exit_code"] != 0
              and (not configuration or lock_failed)
              and receipt["generated_sha256"] != receipt["tracked_sha256"]
              and lock_failure_signature(output / "stderr.txt")):
            receipt["status"] = "LOCK_MISMATCH_CAPTURED"
        elif (configuration and process["exit_code"] != 0 and lock_succeeded
              and receipt["generated_sha256"] == receipt["tracked_sha256"]
              and safari_capture_timeout(stdout, (output / "stderr.txt").read_bytes())):
            receipt["status"] = "SAFARI_CAPTURE_TIMEOUT"
        elif (configuration and process["exit_code"] != 0 and lock_succeeded
              and receipt["generated_sha256"] == receipt["tracked_sha256"]
              and safari_output_overflow(stdout, (output / "stderr.txt").read_bytes())):
            receipt["status"] = "SAFARI_TEST_OUTPUT_OVERFLOW"
        else:
            receipt["status"] = "OTHER_GRADLE_RESULT"
    except (OSError, ValueError) as error:
        receipt.update(status="CAPTURE_REJECTED", reason=str(error))
    receipt["files"] = files
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def audit_capture(repository, candidate_sha, output):
    repository = repository.resolve()
    output = output.resolve()
    require_candidate(repository, candidate_sha)
    receipt = json.loads(source_bytes(output, Path("receipt.json")))
    configuration = receipt.get("configuration")
    if (receipt.get("candidate_sha") != candidate_sha
            or receipt.get("qualified") is not False
            or receipt.get("status") != "LOCK_MISMATCH_CAPTURED"
            or receipt.get("head_after_task") != candidate_sha
            or receipt.get("head_after") != candidate_sha
            or receipt.get("tracked_changes_after_task") != ""
            or receipt.get("tracked_changes_after") != ""
            or configuration not in ("development", "production")
            or not isinstance(receipt.get("invocation_id"), str)
            or not re.fullmatch(r"[0-9a-f]{32}", receipt["invocation_id"])):
        raise ValueError("hosted diagnostic identity differs")
    source_inputs = (TRACKED_LOCK, *SOURCE_INPUTS, *HOSTED_SOURCE_INPUTS)
    init_relative = Path(configuration) / "qualification.init.gradle"
    expected = {init_relative.as_posix(), "stdout.txt", "stderr.txt",
                f"tracked/{TRACKED_LOCK}", f"tracked-after/{TRACKED_LOCK}",
                f"generated/{GENERATED_LOCK}"}
    expected.update(f"inputs/{path}" for path in source_inputs[1:])
    expected.update(f"generated/{path}" for path in REQUIRED_PACKAGE_INPUTS)
    if (receipt.get("package_inputs_expected") != [path.as_posix() for path in REQUIRED_PACKAGE_INPUTS]
            or set(receipt.get("package_inputs_observed", []))
            != {path.as_posix() for path in REQUIRED_PACKAGE_INPUTS}
            or receipt.get("missing_package_inputs") != []
            or receipt.get("unexpected_package_inputs") != []
            or receipt.get("package_graph_errors") != []
            or receipt.get("package_count_exceeds_bound") is not False):
        raise ValueError("hosted diagnostic package graph inventory differs")
    files = receipt.get("files")
    if not isinstance(files, list) or {item.get("path") for item in files
                                       if isinstance(item, dict)} != expected or len(files) != len(expected):
        raise ValueError("hosted diagnostic file inventory differs")
    for item in files:
        relative = Path(item["path"])
        data = source_bytes(output, relative)
        if (hashlib.sha256(data).hexdigest() != item.get("sha256")
                or len(data) != item.get("size")):
            raise ValueError(f"hosted diagnostic raw file differs: {relative}")
    committed = {path.as_posix(): hashlib.sha256(
        safari_reporter.committed_bytes(repository, candidate_sha, path)).hexdigest()
                 for path in source_inputs}
    if (receipt.get("source_input_sha256") != committed
            or receipt.get("source_input_after_sha256") != committed):
        raise ValueError("hosted diagnostic candidate source binding differs")
    for path in source_inputs:
        prefix = "tracked" if path == TRACKED_LOCK else "inputs"
        if hashlib.sha256(source_bytes(output, Path(prefix) / path)).hexdigest() != committed[path.as_posix()]:
            raise ValueError(f"hosted diagnostic archived source differs: {path}")
    script = full_hosted.init_script("jsSafari", configuration).encode()
    if (source_bytes(output, init_relative) != script
            or receipt.get("init_script_sha256") != hashlib.sha256(script).hexdigest()):
        raise ValueError("hosted diagnostic init script differs")
    original_repository = Path(receipt.get("repository_root", ""))
    original_output = Path(receipt.get("archive_root", ""))
    if not original_repository.is_absolute() or not original_output.is_absolute():
        raise ValueError("hosted diagnostic original paths are absent")
    process = receipt.get("process")
    expected_command = full_hosted_command(original_repository,
                                           original_output / init_relative,
                                           configuration, receipt["invocation_id"])
    if (not isinstance(process, dict) or process.get("command") != expected_command
            or not isinstance(process.get("pid"), int) or process["pid"] <= 0
            or not isinstance(process.get("started_ns"), int)
            or not isinstance(process.get("finished_ns"), int)
            or process["started_ns"] >= process["finished_ns"]
            or not isinstance(process.get("exit_code"), int)
            or process["exit_code"] == 0
            or any(process.get(key) is not False for key in
                   ("timed_out", "stream_incomplete", "stdout_truncated", "stderr_truncated"))):
        raise ValueError("hosted diagnostic process binding differs")
    stdout = output / "stdout.txt"
    stderr = output / "stderr.txt"
    if (process.get("stdout_bytes_seen") != stdout.stat().st_size
            or process.get("stderr_bytes_seen") != stderr.stat().st_size
            or not all(marker in stdout.read_bytes() for marker in hosted_task_markers(process))
            or not lock_failure_signature(stderr)):
        raise ValueError("hosted diagnostic process output differs")
    tracked = source_bytes(output, Path("tracked") / TRACKED_LOCK)
    generated = source_bytes(output, Path("generated") / GENERATED_LOCK)
    if (tracked == generated
            or tracked != source_bytes(output, Path("tracked-after") / TRACKED_LOCK)
            or receipt.get("tracked_sha256") != hashlib.sha256(tracked).hexdigest()
            or receipt.get("tracked_after_sha256") != hashlib.sha256(tracked).hexdigest()
            or receipt.get("generated_sha256") != hashlib.sha256(generated).hexdigest()):
        raise ValueError("hosted diagnostic lock bytes differ")
    for name in ("dyn4k-dyn4k-core-test", "dyn4k-dyn4k-test"):
        data = source_bytes(output, Path("generated/build/js/packages") / name / "package.json")
        if json.loads(data).get("devDependencies", {}).get("karma-safari-launcher") != "1.0.0":
            raise ValueError(f"hosted diagnostic Safari package differs: {name}")
    return receipt


def main():
    parser = argparse.ArgumentParser(description="Capture a Kotlin/JS Yarn lock mismatch")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--configuration", choices=("development", "production"))
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--input-context", type=Path)
    parser.add_argument("--capture-context", action="store_true")
    args = parser.parse_args()
    if args.capture_context:
        if args.audit or args.configuration or args.input_context is None:
            parser.error("context scan requires input context and cannot audit or run Gradle")
        inventory = capture_karma_context(ROOT, args.candidate_sha,
                                          args.output, args.input_context)
        print(json.dumps({"candidate_sha": inventory["candidate_sha"],
                          "status": inventory["status"], "qualified": False,
                          "output": str(args.output)}))
        return 0 if inventory["status"] == "CONTEXT_COMPLETE" else 1
    if args.input_context is not None:
        parser.error("input context requires --capture-context")
    receipt = (audit_capture(ROOT, args.candidate_sha, args.output) if args.audit
               else capture(ROOT, args.candidate_sha, args.output, args.configuration))
    print(json.dumps({"candidate_sha": receipt["candidate_sha"],
                      "status": receipt["status"], "qualified": False,
                      "output": str(args.output)}))
    return 0 if receipt["status"] in ("LOCK_MISMATCH_CAPTURED",
                                       "LOCK_MATCHED_DIAGNOSTIC_ONLY") else 1


if __name__ == "__main__":
    raise SystemExit(main())
