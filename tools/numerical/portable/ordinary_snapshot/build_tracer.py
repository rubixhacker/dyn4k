import argparse
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
            if pid not in handles:
                handles[pid] = os.pidfd_open(pid)
            if not select.select([handles[pid]], [], [], 0)[0]:
                live.append(pid)
        except (FileNotFoundError, ProcessLookupError):
            continue
    return live


def _wait_group_exit(process, handles, deadline):
    while time.monotonic() < deadline:
        live = _live_group_members(process.pid, handles)
        if not live and all(select.select([handle], [], [], 0)[0]
                            for handle in handles.values()):
            process.poll()
            return process.returncode is not None
        time.sleep(0.02)
    return (not _live_group_members(process.pid, handles) and
            all(select.select([handle], [], [], 0)[0]
                for handle in handles.values()) and process.poll() is not None)


def run(argv, cwd, environment, timeout):
    started = time.time_ns()
    if timeout <= 0:
        return {"argv": argv, "cwd": str(cwd), "utc_start_ns": started,
                "utc_end_ns": time.time_ns(), "exit_code": 124,
                "timed_out": True, "stdout": b"", "stderr": b"build deadline expired"}
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
    except OSError as error:
        return {"argv": argv, "cwd": str(cwd), "utc_start_ns": started,
                "utc_end_ns": time.time_ns(), "exit_code": 127,
                "timed_out": False, "stdout": b"",
                "stderr": str(error).encode("utf-8", "replace")}
    timed_out = False
    handles = {}
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except (subprocess.TimeoutExpired, TimeoutError):
        timed_out = True
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            if not _wait_group_exit(process, handles, time.monotonic() + 2):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                if not _wait_group_exit(process, handles, time.monotonic() + 2):
                    raise RuntimeError("owned build group exit could not be established")
            try:
                stdout, stderr = process.communicate(timeout=0.5)
            except subprocess.TimeoutExpired as error:
                raise RuntimeError("owned build streams did not close after group exit") from error
        finally:
            for handle in handles.values():
                os.close(handle)
    return {"argv": argv, "cwd": str(cwd), "utc_start_ns": started,
            "utc_end_ns": time.time_ns(), "exit_code": 124 if timed_out else process.returncode,
            "timed_out": timed_out, "stdout": stdout, "stderr": stderr}


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
        if use_timer:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, prior_handler)
            if prior_timer[0]:
                signal.setitimer(signal.ITIMER_REAL,
                                 max(0.000001, prior_timer[0] -
                                     (time.monotonic() - started)),
                                 prior_timer[1])


def _build(archive, output, *, timeout):
    deadline = time.monotonic() + timeout
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
