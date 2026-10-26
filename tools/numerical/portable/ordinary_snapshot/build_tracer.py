import argparse
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import signal
import stat
import subprocess
import tarfile
import time


ARCHIVE_SHA256 = "4bde6246926890dcee824f6e6ac42a06752f47d77e5097d86e3c0d6d4b709fe5"
SOURCE_SHA256 = "06525ee83048d477139312ad96e750585354e5f9f56663bdde0f959dce5b16dc"
HERE = Path(__file__).resolve().parent
PATCH = HERE / "strace-7.2.patch"
INCLUDE = HERE / "owned_snapshot.inc"
_BUILD_DEADLINE = ContextVar("ordinary_build_deadline", default=None)
_COMPILER_MAX_BYTES = 64 * 1024 * 1024


class OwnedGroupIdentityError(RuntimeError):
    pass


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compiler_identity(retained_path=None):
    selected = shutil.which("gcc")
    if selected is None:
        raise ValueError("gcc compiler is unavailable")
    path = str(Path(selected).resolve())
    if retained_path is not None and (type(retained_path) is not str or
                                      len(retained_path) > 4096 or
                                      retained_path != path):
        raise ValueError("compiler path differs")
    try:
        before = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_size > _COMPILER_MAX_BYTES:
            raise ValueError("compiler file differs")
        handle = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK |
                         os.O_NOFOLLOW)
        try:
            opened = os.fstat(handle)
            if (not stat.S_ISREG(opened.st_mode) or
                    (opened.st_dev, opened.st_ino) !=
                    (before.st_dev, before.st_ino) or
                    opened.st_size > _COMPILER_MAX_BYTES):
                raise ValueError("compiler file differs")
            value = hashlib.sha256()
            length = 0
            while block := os.read(handle, 1024 * 1024):
                length += len(block)
                if length > _COMPILER_MAX_BYTES:
                    raise ValueError("compiler file differs")
                value.update(block)
            after = os.fstat(handle)
            if (length != opened.st_size or
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) !=
                    (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)):
                raise ValueError("compiler file differs")
        finally:
            os.close(handle)
    except OSError as error:
        raise ValueError("compiler file differs") from error
    return path, value.hexdigest()


def write_record(path, record):
    pending = Path(str(path) + ".tmp")
    pending.write_text(json.dumps(record, sort_keys=True) + "\n")
    os.replace(pending, path)


def _assert_group_leader_identity(group, handles):
    if group not in handles:
        return
    try:
        fields = Path(f"/proc/{group}/stat").read_text().rsplit(")", 1)[1].split()
        start_ticks = int(fields[19])
    except FileNotFoundError:
        return
    except (OSError, ValueError, IndexError) as error:
        raise RuntimeError("owned build group identity is uncertain") from error
    if start_ticks != handles[group][1]:
        raise OwnedGroupIdentityError("owned build group identity is uncertain")


def _live_group_members(group, handles):
    live = []
    _assert_group_leader_identity(group, handles)
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            if int(fields[2]) != group or fields[0] in {"Z", "X"}:
                continue
            pid = int(entry.name)
            start_ticks = int(fields[19])
            if pid in handles:
                handle, bound_ticks = handles[pid]
                if bound_ticks != start_ticks or select.select([handle], [], [], 0)[0]:
                    raise OwnedGroupIdentityError("owned build group identity is uncertain")
            else:
                handle = os.pidfd_open(pid)
                try:
                    again = (entry / "stat").read_text().rsplit(")", 1)[1].split()
                    if (int(again[2]) != group or again[0] in {"Z", "X"} or
                            int(again[19]) != start_ticks or
                            select.select([handle], [], [], 0)[0]):
                        raise OwnedGroupIdentityError("owned build group identity is uncertain")
                    handles[pid] = (handle, start_ticks)
                except BaseException:
                    os.close(handle)
                    raise
            if not select.select([handle], [], [], 0)[0]:
                live.append(pid)
        except (OSError, ValueError, IndexError) as error:
            raise RuntimeError("owned build group identity is uncertain") from error
    _assert_group_leader_identity(group, handles)
    return live


def _wait_group_exit(process, handles, deadline):
    while time.monotonic() < deadline:
        try:
            live = _live_group_members(process.pid, handles)
        except OwnedGroupIdentityError:
            raise
        except RuntimeError:
            time.sleep(0.02)
            continue
        if not live and all(select.select([handle], [], [], 0)[0]
                            for handle, _ in handles.values()):
            process.poll()
            return process.returncode is not None
        time.sleep(0.02)
    try:
        return (not _live_group_members(process.pid, handles) and
                all(select.select([handle], [], [], 0)[0]
                    for handle, _ in handles.values()) and process.poll() is not None)
    except RuntimeError:
        return False


def _bind_launch_parent(process, handles):
    handle = os.pidfd_open(process.pid)
    try:
        fields = Path(f"/proc/{process.pid}/stat").read_text().rsplit(")", 1)[1].split()
        if int(fields[2]) != process.pid or int(fields[3]) != process.pid:
            raise RuntimeError("owned build group identity is uncertain")
        handles[process.pid] = (handle, int(fields[19]))
    except (OSError, ValueError, IndexError, RuntimeError) as error:
        os.close(handle)
        raise RuntimeError("owned build group identity is uncertain") from error


def _signal_bound_members(handles, pids, sig):
    for pid in pids:
        try:
            signal.pidfd_send_signal(handles[pid][0], sig)
        except ProcessLookupError:
            pass


def _scan_group_for_cleanup(process, handles, deadline):
    error = None
    while time.monotonic() < deadline:
        try:
            return _live_group_members(process.pid, handles), None
        except OwnedGroupIdentityError as failure:
            return [], str(failure)
        except RuntimeError as failure:
            error = str(failure)
            time.sleep(0.02)
    return [], error or "owned build group exit is unproved"


def run(argv, cwd, environment, timeout):
    started = time.time_ns()
    build_deadline = _BUILD_DEADLINE.get()
    if build_deadline is not None:
        remaining = max(0, build_deadline - time.monotonic())
        reserve = min(5, remaining * 0.8)
        timeout = min(timeout, max(0, remaining - reserve))
    if timeout <= 0:
        return {"argv": argv, "cwd": str(cwd), "utc_start_ns": started,
                "utc_end_ns": time.time_ns(), "exit_code": 124,
                "process_exit_code": "NOT_OBSERVED", "timed_out": True,
                "cleanup_status": "NOT_STARTED", "streams_complete": False,
                "failure_type": "DEADLINE_EXPIRED",
                "stdout": b"", "stderr": b"build deadline expired"}
    prior_handler = signal.getsignal(signal.SIGALRM) if build_deadline is not None else None
    if build_deadline is not None:
        signal.signal(signal.SIGALRM, lambda _signum, _frame: None)
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
    except OSError as error:
        if build_deadline is not None:
            signal.signal(signal.SIGALRM, prior_handler)
        return {"argv": argv, "cwd": str(cwd), "utc_start_ns": started,
                "utc_end_ns": time.time_ns(), "exit_code": 127,
                "process_exit_code": "NOT_OBSERVED", "timed_out": False,
                "cleanup_status": "NOT_STARTED", "streams_complete": False,
                "failure_type": "LAUNCH_FAILED",
                "stdout": b"",
                "stderr": str(error).encode("utf-8", "replace")}
    if build_deadline is not None:
        remaining = max(0, build_deadline - time.monotonic())
        timeout = min(timeout, max(0, remaining - min(5, remaining * 0.8)))
    timed_out = False
    handles = {}
    binding_error = None
    try:
        try:
            _bind_launch_parent(process, handles)
        except (OSError, RuntimeError) as error:
            binding_error = str(error)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except (subprocess.TimeoutExpired, TimeoutError) as timeout_error:
            timed_out = True
            stdout = timeout_error.stdout or b""
            stderr = timeout_error.stderr or b""
            cleanup_error = binding_error
            cleanup_deadline = (build_deadline if build_deadline is not None else
                                time.monotonic() + 4.5)
            exited = False
            if binding_error is None:
                try:
                    live, scan_error = _scan_group_for_cleanup(
                        process, handles, cleanup_deadline)
                    cleanup_error = scan_error
                    _signal_bound_members(handles, live, signal.SIGTERM)
                    if scan_error is None:
                        try:
                            exited = _wait_group_exit(process, handles,
                                min(cleanup_deadline, time.monotonic() + 2))
                        except RuntimeError as error:
                            cleanup_error = str(error)
                    if not exited:
                        _signal_bound_members(handles, handles, signal.SIGKILL)
                        try:
                            exited = _wait_group_exit(process, handles,
                                                      cleanup_deadline)
                        except RuntimeError as error:
                            cleanup_error = str(error)
                except (OSError, RuntimeError) as error:
                    cleanup_error = str(error)
            try:
                stdout, stderr = process.communicate(timeout=max(
                    0, min(0.5, cleanup_deadline - time.monotonic())))
                streams_complete = True
            except subprocess.TimeoutExpired as error:
                stdout = error.stdout or stdout
                stderr = error.stderr or stderr
                streams_complete = False
            cleanup_status = ("COMPLETE" if exited and streams_complete and
                              cleanup_error is None else "INCOMPLETE")
            failure_type = "COMMAND_TIMEOUT"
        else:
            streams_complete = True
            cleanup_error = binding_error
            failure_type = None
            cleanup_deadline = (build_deadline if build_deadline is not None else
                                time.monotonic() + 4.5)
            exited = False
            if binding_error is None:
                try:
                    live, scan_error = _scan_group_for_cleanup(
                        process, handles, cleanup_deadline)
                    cleanup_error = scan_error
                    if live:
                        failure_type = "OWNED_GROUP_SURVIVED"
                        _signal_bound_members(handles, live, signal.SIGTERM)
                        try:
                            exited = _wait_group_exit(process, handles,
                                min(cleanup_deadline, time.monotonic() + 2))
                        except RuntimeError as error:
                            cleanup_error = str(error)
                        if not exited:
                            _signal_bound_members(handles, handles, signal.SIGKILL)
                            try:
                                exited = _wait_group_exit(process, handles,
                                                          cleanup_deadline)
                            except RuntimeError as error:
                                cleanup_error = str(error)
                    else:
                        if cleanup_error is not None:
                            _signal_bound_members(handles, handles, signal.SIGKILL)
                        if cleanup_error is None:
                            exited = _wait_group_exit(process, handles,
                                                      cleanup_deadline)
                except (OSError, RuntimeError) as error:
                    cleanup_error = str(error)
            cleanup_status = ("COMPLETE" if exited and cleanup_error is None
                              else "INCOMPLETE")
            if cleanup_status != "COMPLETE" and failure_type is None:
                failure_type = "OWNED_GROUP_EXIT_UNPROVED"
    finally:
        for handle, _ in handles.values():
            os.close(handle)
        process.stdout.close()
        process.stderr.close()
        if build_deadline is not None:
            signal.signal(signal.SIGALRM, prior_handler)
    return {"argv": argv, "cwd": str(cwd), "utc_start_ns": started,
            "utc_end_ns": time.time_ns(),
            "exit_code": (124 if timed_out else 125 if failure_type else
                          process.returncode),
            "process_exit_code": (process.poll() if process.returncode is not None
                                  else "NOT_OBSERVED"), "timed_out": timed_out,
            "cleanup_status": cleanup_status, "cleanup_error": cleanup_error,
            "failure_type": failure_type,
            "streams_complete": streams_complete, "stdout": stdout, "stderr": stderr}


def build(archive, output, *, timeout=600):
    if timeout <= 0:
        raise ValueError("private build deadline must be positive")
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("private build output already exists")
    output.mkdir(mode=0o700, parents=True)
    initial = {"schema": "ordinary-snapshot-build/1", "status": "INCOMPLETE",
               "archive_sha256": ARCHIVE_SHA256, "commands": []}
    record_path = output / "build-record.json"
    write_record(record_path, initial)
    prior_handler = signal.getsignal(signal.SIGALRM)
    prior_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    deadline_token = _BUILD_DEADLINE.set(started + timeout)
    use_timer = prior_timer[0] == 0 or prior_timer[0] > timeout
    def expire_build(_signum, _frame):
        raise TimeoutError("private build deadline expired")
    if use_timer:
        signal.signal(signal.SIGALRM, expire_build)
        signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        return _build(archive, output, timeout=timeout)
    except Exception as error:
        record = json.loads(record_path.read_text())
        if record["status"] == "INCOMPLETE":
            record["status"] = "TIMEOUT" if isinstance(error, TimeoutError) else "FAILED"
            record["error_type"] = type(error).__name__
            write_record(record_path, record)
        raise
    finally:
        _BUILD_DEADLINE.reset(deadline_token)
        if use_timer:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, prior_handler)
            if prior_timer[0]:
                signal.setitimer(signal.ITIMER_REAL,
                                 max(0.000001, prior_timer[0] -
                                     (time.monotonic() - started)),
                                 prior_timer[1])


def _build(archive, output, *, timeout):
    deadline = _BUILD_DEADLINE.get() or time.monotonic() + timeout
    archive = Path(archive).resolve()
    output = Path(output).resolve()
    if digest(archive) != ARCHIVE_SHA256:
        raise ValueError("pinned strace source archive differs")
    commands = []
    with tarfile.open(archive, "r:xz") as source:
        names = source.getnames()
        if not names or any(name != "strace-7.2" and
                            not name.startswith("strace-7.2/") or
                            ".." in Path(name).parts for name in names):
            raise ValueError("strace source archive layout differs")
        source.extractall(output, filter="data")
    tree = output / "strace-7.2"
    source_file = tree / "src/strace.c"
    if digest(source_file) != SOURCE_SHA256:
        raise ValueError("pinned strace source file differs")
    shutil.copyfile(INCLUDE, tree / "src/owned_snapshot.inc")
    compiler, compiler_sha256 = compiler_identity()
    env = {key: value for key, value in os.environ.items()
           if key not in {"CC", "CXX", "MAKEFLAGS", "MFLAGS", "GNUMAKEFLAGS"}}
    env.update({"LC_ALL": "C", "TZ": "UTC", "SOURCE_DATE_EPOCH": "1770000000",
                "CFLAGS": "-O2 -g0 -ffile-prefix-map=" + str(tree) + "=/strace-7.2",
                "CC": compiler, "MAKEFLAGS": "-j2"})
    record = {"schema": "ordinary-snapshot-build/1", "status": "INCOMPLETE",
              "archive_sha256": ARCHIVE_SHA256,
              "upstream_source_sha256": SOURCE_SHA256,
              "patch_sha256": digest(PATCH), "include_sha256": digest(INCLUDE),
              "compiler_path": compiler, "compiler_sha256": compiler_sha256,
              "commands": []}
    for index, (argv, cwd) in enumerate(((["git", "apply", str(PATCH)], tree),
                      ([str(tree / "configure"), "--disable-mpers",
                        "--disable-stacktrace"], output),
                      (["make", "-j2"], output))):
        command = run(argv, cwd, env, max(
            0, deadline - time.monotonic() - min(5, timeout / 5)))
        for name in ("stdout", "stderr"):
            path = output / f"build-{index}-{name}.raw"
            with path.open("xb") as stream:
                stream.write(command[name])
            command[name + "_path"] = str(path)
        commands.append(command)
        record["commands"].append(
            {key: value for key, value in command.items()
             if key not in {"stdout", "stderr"}} |
            {"stdout_sha256": hashlib.sha256(command["stdout"]).hexdigest(),
             "stderr_sha256": hashlib.sha256(command["stderr"]).hexdigest()})
        write_record(output / "build-record.json", record)
        if (command["exit_code"] != 0 or command["cleanup_status"] != "COMPLETE"
                or not command["streams_complete"] or
                command["process_exit_code"] != 0):
            record["status"] = "TIMEOUT" if command["timed_out"] else "FAILED"
            record["error_type"] = command.get("failure_type") or "COMMAND_INCOMPLETE"
            write_record(output / "build-record.json", record)
            raise RuntimeError(f"private strace build failed: {argv[0]}: " +
                               command["stderr"].decode("utf-8", "replace")[-2000:])
    binary = output / "src/strace"
    record["status"] = "COMPLETE"
    record["binary_sha256"] = digest(binary)
    write_record(output / "build-record.json", record)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive")
    parser.add_argument("output")
    parser.add_argument("--compare-binary")
    args = parser.parse_args()
    result = build(args.archive, args.output)
    if args.compare_binary and digest(args.compare_binary) != result["binary_sha256"]:
        raise ValueError("private strace binary differs from exact rebuild")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
