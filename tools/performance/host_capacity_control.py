#!/usr/bin/env python3
import argparse
import hashlib
import hmac
import json
import os
import platform
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from measure import sha256
from stress_monitor import peak_rss_bytes
from sustained_archive import (close_windows_peak_handle, observe_process_image,
                               require_external_key, wait4_peak_rss,
                               windows_dispatch_stop, windows_peak_handle,
                               windows_terminal_peak)


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = "tools/performance/host_capacity_control.py"
CHILD_SOURCE = "\n".join((
    "import json", "import os", "import sys", "import time", "from pathlib import Path", "",
    "data = bytearray(16 * 1024 * 1024)",
    "for offset in range(0, len(data), 4096):", "    data[offset] = 1",
    "Path(sys.argv[1]).write_text(str(os.getpid()))",
    'print(json.dumps({"ready_pid": os.getpid(), "touched_bytes": len(data)}), flush=True)',
    "time.sleep(30)", ""))
FIELDS = {"version", "qualification", "status", "error", "source_commit",
          "tool_sha256", "tool_working_sha256", "tool_encoding",
          "host_system", "host_machine", "host_release",
          "workflow_run_id", "workflow_attempt", "pid", "started_ns",
          "image_observed_ns", "image_method", "image_path", "image_sha256",
          "expected_runtime_sha256", "sample_observed_ns", "sample_bytes",
          "stop_requested_ns", "stop_dispatched_ns", "stop_method", "stop_result",
          "terminal_observed_ns", "ended_ns", "terminal_exit_code",
          "terminal_wait_status", "terminal_peak_bytes", "terminal_metric_kind",
          "stdout_sha256", "stderr_sha256", "ready_sha256", "child_sha256",
          "executable_sha256"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def signature(record, key):
    body = {name: value for name, value in record.items() if name != "signature"}
    data = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def source_at_commit(commit):
    require(bool(re.fullmatch(r"[0-9a-f]{40}", commit)), "source commit is invalid")
    return subprocess.check_output(["git", "show", f"{commit}:{SOURCE_PATH}"], cwd=ROOT)


def source_encoding(executed, committed):
    if executed == committed:
        return "git_exact"
    if b"\r" not in committed and executed == committed.replace(b"\n", b"\r\n"):
        return "git_crlf"
    raise ValueError("executed diagnostic source differs from committed bytes")


def capture_stop(process, system, pid, windows_handle):
    requested = time.monotonic_ns()
    if system == "Darwin":
        os.kill(pid, signal.SIGTERM)
        dispatched = time.monotonic_ns()
        status, peak = wait4_peak_rss(pid, 0, "Darwin")
        exit_code = os.waitstatus_to_exitcode(status)
        process.returncode = exit_code
        method = "posix_sigterm_wait4_v1"
    elif system == "Windows":
        windows_dispatch_stop(process, pid)
        dispatched = time.monotonic_ns()
        exit_code = process.wait(timeout=10)
        peak = windows_terminal_peak(windows_handle, pid)
        status = None
        method = "windows_terminate_process_v1"
    else:
        raise ValueError("diagnostic requires macOS or Windows")
    return {"stop_requested_ns": requested, "stop_dispatched_ns": dispatched,
            "stop_method": method, "stop_result": "os_success",
            "terminal_wait_status": status, "terminal_exit_code": exit_code,
            "terminal_peak_bytes": peak, "terminal_observed_ns": time.monotonic_ns()}


def validate_record(record, archive, expected_commit):
    require(set(record) == FIELDS, "diagnostic receipt fields differ")
    require(record["version"] == 1 and record["qualification"] == "unpassed" and
            record["status"] == "observed" and record["error"] is None,
            "diagnostic is incomplete")
    committed_source = source_at_commit(expected_commit)
    executed_source = (archive / "tool-executed.py").read_bytes()
    source_encoding(Path(__file__).read_bytes(), committed_source)
    require(record["source_commit"] == expected_commit and
            record["tool_sha256"] == hashlib.sha256(committed_source).hexdigest() and
            record["tool_working_sha256"] == hashlib.sha256(executed_source).hexdigest() and
            record["tool_encoding"] == source_encoding(executed_source, committed_source),
            "diagnostic source identity differs")
    system = record["host_system"]
    require(system in ("Darwin", "Windows") and
            isinstance(record["host_machine"], str) and record["host_machine"] and
            isinstance(record["host_release"], str) and record["host_release"] and
            isinstance(record["workflow_run_id"], str) and
            isinstance(record["workflow_attempt"], str), "diagnostic host identity differs")
    integer_fields = ("pid", "started_ns", "image_observed_ns", "sample_observed_ns",
                      "sample_bytes", "stop_requested_ns", "stop_dispatched_ns",
                      "terminal_observed_ns", "ended_ns", "terminal_exit_code",
                      "terminal_peak_bytes")
    require(all(type(record[name]) is int for name in integer_fields) and
            record["pid"] > 0 and record["sample_bytes"] > 0 and
            record["terminal_peak_bytes"] >= record["sample_bytes"] and
            record["started_ns"] <= record["image_observed_ns"] <=
            record["sample_observed_ns"] <= record["stop_requested_ns"] <=
            record["stop_dispatched_ns"] <= record["terminal_observed_ns"] <=
            record["ended_ns"], "diagnostic process interval or counter differs")
    method = "macos_libproc" if system == "Darwin" else "windows_query_image"
    require(record["image_method"] == method and
            isinstance(record["image_path"], str) and record["image_path"] and
            record["stop_result"] == "os_success", "diagnostic image or dispatch differs")
    if system == "Darwin":
        status = record["terminal_wait_status"]
        require(type(status) is int and os.WIFSIGNALED(status) and
                os.WTERMSIG(status) == signal.SIGTERM and
                record["terminal_exit_code"] == -signal.SIGTERM and
                record["stop_method"] == "posix_sigterm_wait4_v1" and
                record["terminal_metric_kind"] == "peak_rss_bytes",
                "macOS terminal usage or units differ")
    else:
        require(record["terminal_wait_status"] is None and
                record["terminal_exit_code"] == 1 and
                record["stop_method"] == "windows_terminate_process_v1" and
                record["terminal_metric_kind"] == "peak_working_set_bytes",
                "Windows terminal usage or native dispatch differs")
    for name, file_name in (("stdout_sha256", "stdout.raw"),
                            ("stderr_sha256", "stderr.raw"),
                            ("ready_sha256", "ready.pid"),
                            ("child_sha256", "child.py"),
                            ("executable_sha256", "executable.bin")):
        require(sha256(archive / file_name) == record[name],
                f"diagnostic {file_name} bytes differ")
    require((archive / "child.py").read_bytes() == CHILD_SOURCE.encode() and
            record["executable_sha256"] == record["image_sha256"] ==
            record["expected_runtime_sha256"], "diagnostic child or executable identity differs")
    lines = (archive / "stdout.raw").read_text().splitlines()
    require(len(lines) == 1 and not (archive / "stderr.raw").read_bytes(),
            "diagnostic child raw output differs")
    marker = json.loads(lines[0])
    require(marker == {"ready_pid": record["pid"], "touched_bytes": 16 * 1024 * 1024},
            "diagnostic ready marker differs from observed child")
    require((archive / "ready.pid").read_text() == str(record["pid"]),
            "diagnostic ready PID differs from observed child")


def capture(archive, key_path, expected_commit):
    archive = Path(archive).resolve()
    key_path = Path(key_path).resolve()
    require(not archive.exists() or not any(archive.iterdir()), "diagnostic archive is not empty")
    require(not key_path.exists() and not key_path.is_relative_to(archive),
            "test-only key must be new and outside archive")
    require(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                    text=True).strip() == expected_commit,
            "capture tool differs from exact source commit")
    committed_source = source_at_commit(expected_commit)
    executed_source = Path(__file__).read_bytes()
    encoding = source_encoding(executed_source, committed_source)
    system = platform.system()
    require(system in ("Darwin", "Windows"), "diagnostic requires macOS or Windows")
    archive.mkdir(parents=True, exist_ok=True)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    with key_path.open("xb") as stream:
        stream.write(key)
    require_external_key(key_path, [archive])
    (archive / "tool-executed.py").write_bytes(executed_source)
    (archive / "child.py").write_bytes(CHILD_SOURCE.encode())
    runtime = Path(sys.executable).resolve(strict=True)
    record = {name: None for name in FIELDS}
    record.update(version=1, qualification="unpassed", status="failed", error=None,
                  source_commit=expected_commit,
                  tool_sha256=hashlib.sha256(committed_source).hexdigest(),
                  tool_working_sha256=hashlib.sha256(executed_source).hexdigest(),
                  tool_encoding=encoding,
                  host_system=system, host_machine=platform.machine(),
                  host_release=platform.release(),
                  workflow_run_id=os.environ.get("GITHUB_RUN_ID", "local"),
                  workflow_attempt=os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
                  expected_runtime_sha256=sha256(runtime),
                  child_sha256=sha256(archive / "child.py"))
    process = None
    windows_handle = None
    try:
        with (archive / "stdout.raw").open("wb") as stdout, \
             (archive / "stderr.raw").open("wb") as stderr:
            record["started_ns"] = time.monotonic_ns()
            process = subprocess.Popen([str(runtime), "-u", str(archive / "child.py"),
                                        str(archive / "ready.pid")],
                                       stdout=stdout, stderr=stderr)
            pid = process.pid
            record["pid"] = pid
            image = observe_process_image(pid)
            require(image["pid"] == pid and image["sha256"] ==
                    record["expected_runtime_sha256"], "observed executable differs")
            record.update(image_observed_ns=image["observed_ns"],
                          image_method=image["method"], image_path=image["executable_path"],
                          image_sha256=image["sha256"])
            shutil.copyfile(image["executable_path"], archive / "executable.bin")
            require(sha256(archive / "executable.bin") == image["sha256"],
                    "archived executable differs from observed process")
            deadline = time.monotonic() + 5
            while not (archive / "ready.pid").is_file() and time.monotonic() < deadline:
                require(process.poll() is None, "diagnostic child exited before ready")
                time.sleep(0.02)
            require((archive / "ready.pid").is_file() and
                    (archive / "ready.pid").read_text() == str(pid),
                    "diagnostic child ready PID differs")
            if system == "Windows":
                windows_handle = windows_peak_handle(pid)
            record["sample_bytes"] = peak_rss_bytes(pid, system)
            record["sample_observed_ns"] = time.monotonic_ns()
            record.update(capture_stop(process, system, pid, windows_handle))
            record["ended_ns"] = time.monotonic_ns()
            record["terminal_metric_kind"] = ("peak_rss_bytes" if system == "Darwin" else
                                              "peak_working_set_bytes")
            record["status"] = "observed"
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if process is not None and process.poll() is None:
            try:
                process.kill()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired) as exc:
                record["status"] = "failed"
                record["error"] = f"cleanup {type(exc).__name__}: {exc}"
        if windows_handle is not None:
            close_windows_peak_handle(windows_handle)
    record["ended_ns"] = record["ended_ns"] or time.monotonic_ns()
    for field, file_name in (("stdout_sha256", "stdout.raw"),
                             ("stderr_sha256", "stderr.raw"),
                             ("ready_sha256", "ready.pid"),
                             ("executable_sha256", "executable.bin")):
        path = archive / file_name
        record[field] = sha256(path) if path.is_file() else None
    if record["status"] == "observed":
        try:
            validate_record(record, archive, expected_commit)
        except (OSError, ValueError) as exc:
            record["status"] = "failed"
            record["error"] = f"{type(exc).__name__}: {exc}"
    record["signature"] = signature(record, key)
    (archive / "receipt.json").write_text(json.dumps(record, sort_keys=True) + "\n")
    return record


def verify_archive(archive, key_path, expected_commit):
    archive = Path(archive).resolve(strict=True)
    require_external_key(key_path, [archive])
    expected_files = {"receipt.json", "stdout.raw", "stderr.raw", "ready.pid",
                      "child.py", "executable.bin", "tool-executed.py"}
    require({path.name for path in archive.iterdir()} == expected_files and
            all(path.is_file() and not path.is_symlink() for path in archive.iterdir()),
            "diagnostic archive inventory differs")
    key = Path(key_path).read_bytes()
    require(len(key) >= 32, "test-only key is too short")
    record = json.loads((archive / "receipt.json").read_text())
    require(isinstance(record, dict) and type(record.get("signature")) is str and
            hmac.compare_digest(record.get("signature", ""), signature(record, key)),
            "diagnostic signature differs")
    validate_record({name: value for name, value in record.items() if name != "signature"},
                    archive, expected_commit)
    return {"diagnostic": "verified", "qualification": "unpassed",
            "host_system": record["host_system"], "pid": record["pid"],
            "terminal_peak_bytes": record["terminal_peak_bytes"],
            "terminal_metric_kind": record["terminal_metric_kind"]}


def main():
    parser = argparse.ArgumentParser(description="Short terminal capacity diagnostic")
    commands = parser.add_subparsers(dest="command", required=True)
    capture_parser = commands.add_parser("capture")
    capture_parser.add_argument("--archive", required=True)
    capture_parser.add_argument("--key-output", required=True)
    capture_parser.add_argument("--expected-source-commit", required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--archive", required=True)
    verify_parser.add_argument("--trusted-key", required=True)
    verify_parser.add_argument("--expected-source-commit", required=True)
    args = parser.parse_args()
    try:
        if args.command == "capture":
            record = capture(args.archive, args.key_output, args.expected_source_commit)
            result = {"diagnostic": record["status"], "qualification": "unpassed",
                      "reason": record["error"]}
            good = record["status"] == "observed"
        else:
            result = verify_archive(args.archive, args.trusted_key,
                                    args.expected_source_commit)
            good = True
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        result = {"diagnostic": "unpassed", "qualification": "unpassed",
                  "reason": str(exc)}
        good = False
    print(json.dumps(result, sort_keys=True))
    if not good:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
