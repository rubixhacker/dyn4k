import argparse
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import tarfile
import time


ARCHIVE_SHA256 = "4bde6246926890dcee824f6e6ac42a06752f47d77e5097d86e3c0d6d4b709fe5"
SOURCE_SHA256 = "06525ee83048d477139312ad96e750585354e5f9f56663bdde0f959dce5b16dc"
HERE = Path(__file__).resolve().parent
PATCH = HERE / "strace-7.2.patch"
INCLUDE = HERE / "owned_snapshot.inc"
_BUILD_DEADLINE = ContextVar("ordinary_build_deadline", default=None)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_record(path, record):
    pending = Path(str(path) + ".tmp")
    pending.write_text(json.dumps(record, sort_keys=True) + "\n")
    os.replace(pending, path)


def _live_group_members(group, handles):
    live = []
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
                    raise RuntimeError("owned build group identity is uncertain")
            else:
                handle = os.pidfd_open(pid)
                try:
                    again = (entry / "stat").read_text().rsplit(")", 1)[1].split()
                    if (int(again[2]) != group or again[0] in {"Z", "X"} or
                            int(again[19]) != start_ticks or
                            select.select([handle], [], [], 0)[0]):
                        raise RuntimeError("owned build group identity is uncertain")
                    handles[pid] = (handle, start_ticks)
                except BaseException:
                    os.close(handle)
                    raise
            if not select.select([handle], [], [], 0)[0]:
                live.append(pid)
        except (OSError, ValueError, IndexError) as error:
            raise RuntimeError("owned build group identity is uncertain") from error
    return live


def _wait_group_exit(process, handles, deadline):
    while time.monotonic() < deadline:
        live = _live_group_members(process.pid, handles)
        if not live and all(select.select([handle], [], [], 0)[0]
                            for handle, _ in handles.values()):
            process.poll()
            return process.returncode is not None
        time.sleep(0.02)
    return (not _live_group_members(process.pid, handles) and
            all(select.select([handle], [], [], 0)[0]
                for handle, _ in handles.values()) and process.poll() is not None)


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
                "stdout": b"",
                "stderr": str(error).encode("utf-8", "replace")}
    if build_deadline is not None:
        remaining = max(0, build_deadline - time.monotonic())
        timeout = min(timeout, max(0, remaining - min(5, remaining * 0.8)))
    timed_out = False
    handles = {}
    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except (subprocess.TimeoutExpired, TimeoutError) as timeout_error:
            timed_out = True
            stdout = timeout_error.stdout or b""
            stderr = timeout_error.stderr or b""
            cleanup_error = None
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            cleanup_deadline = (build_deadline if build_deadline is not None else
                                time.monotonic() + 4.5)
            try:
                exited = _wait_group_exit(process, handles,
                    min(cleanup_deadline, time.monotonic() + 2))
            except RuntimeError as error:
                exited = False
                cleanup_error = str(error)
            if not exited:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    exited = _wait_group_exit(process, handles, cleanup_deadline)
                except RuntimeError as error:
                    exited = False
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
        else:
            cleanup_status = "COMPLETE"
            cleanup_error = None
            streams_complete = True
    finally:
        for handle, _ in handles.values():
            os.close(handle)
        process.stdout.close()
        process.stderr.close()
        if build_deadline is not None:
            signal.signal(signal.SIGALRM, prior_handler)
    return {"argv": argv, "cwd": str(cwd), "utc_start_ns": started,
            "utc_end_ns": time.time_ns(), "exit_code": 124 if timed_out else process.returncode,
            "process_exit_code": (process.poll() if process.returncode is not None
                                  else "NOT_OBSERVED"), "timed_out": timed_out,
            "cleanup_status": cleanup_status, "cleanup_error": cleanup_error,
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
    compiler = shutil.which("gcc")
    if compiler is None:
        raise ValueError("gcc compiler is unavailable")
    compiler = str(Path(compiler).resolve())
    env = {key: value for key, value in os.environ.items()
           if key not in {"CC", "CXX", "MAKEFLAGS", "MFLAGS", "GNUMAKEFLAGS"}}
    env.update({"LC_ALL": "C", "TZ": "UTC", "SOURCE_DATE_EPOCH": "1770000000",
                "CFLAGS": "-O2 -g0 -ffile-prefix-map=" + str(tree) + "=/strace-7.2",
                "CC": compiler, "MAKEFLAGS": "-j2"})
    record = {"schema": "ordinary-snapshot-build/1", "status": "INCOMPLETE",
              "archive_sha256": ARCHIVE_SHA256,
              "upstream_source_sha256": SOURCE_SHA256,
              "patch_sha256": digest(PATCH), "include_sha256": digest(INCLUDE),
              "compiler_path": compiler, "compiler_sha256": digest(compiler),
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
        if command["exit_code"]:
            record["status"] = "TIMEOUT" if command["timed_out"] else "FAILED"
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
