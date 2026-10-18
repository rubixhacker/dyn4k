from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock


INSPECTION_TIMEOUT_SECONDS = 90


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(path: Path, value: str) -> None:
    path.write_text(value.rstrip("\n") + "\n", encoding="utf-8")


def find_objdump() -> list[str] | None:
    for name in ("llvm-objdump.exe", "objdump.exe", "llvm-objdump", "objdump"):
        found = shutil.which(name)
        if found:
            return [found]
    return None


def stop_process_tree(process: subprocess.Popen[bytes]) -> str:
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False,
            )
            cleanup = f"taskkill_exit_{result.returncode}"
        except (OSError, subprocess.TimeoutExpired) as error:
            cleanup = f"taskkill_failed_{type(error).__name__}"
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            cleanup = "process_group_killed"
        except ProcessLookupError:
            cleanup = "process_group_already_exited"
        except OSError as error:
            cleanup = f"process_group_kill_failed_{type(error).__name__}"
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            cleanup += "+direct_process_killed"
        except OSError as error:
            cleanup += f"+direct_kill_failed_{type(error).__name__}"
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cleanup += "+direct_wait_timeout"
    return cleanup


def bounded_process(command: list[str], stdout_path: Path, stderr_path: Path, receipt_path: Path,
                    timeout_seconds: float, deadline_epoch: float | None = None) -> dict[str, object]:
    if timeout_seconds <= 0:
        raise ValueError("timeout must be positive")
    available = timeout_seconds if deadline_epoch is None else min(timeout_seconds, deadline_epoch - time.time())
    receipt: dict[str, object] = {
        "command": command,
        "limitSeconds": timeout_seconds,
        "effectiveSeconds": max(0.0, available),
        "deadlineEpoch": deadline_epoch,
        "state": "NOT_STARTED",
        "childExitCode": None,
        "cleanup": "not_needed",
    }
    started = time.monotonic()
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        if available <= 0:
            receipt["state"] = "TIMEOUT"
            receipt["cleanup"] = "deadline_elapsed_before_start"
        else:
            settings: dict[str, object] = {"stdout": stdout, "stderr": stderr}
            if os.name == "nt":
                settings["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                settings["start_new_session"] = True
            try:
                process = subprocess.Popen(command, **settings)
                try:
                    receipt["childExitCode"] = process.wait(timeout=available)
                    receipt["state"] = "EXITED"
                except subprocess.TimeoutExpired:
                    receipt["state"] = "TIMEOUT"
                    receipt["cleanup"] = stop_process_tree(process)
                    receipt["childExitCode"] = process.returncode
            except OSError as error:
                receipt["state"] = "START_FAILED"
                receipt["error"] = str(error)
    receipt["elapsedSeconds"] = time.monotonic() - started
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def receipt_exit(receipt: dict[str, object]) -> int:
    if receipt["state"] == "TIMEOUT":
        return 124
    if receipt["state"] != "EXITED":
        return 125
    return 0 if receipt["childExitCode"] == 0 else 1


def descendant_status(pid: int, proc_root: Path = Path("/proc")) -> str:
    if os.name != "posix" or not proc_root.is_dir():
        return "UNVERIFIED"
    try:
        stat = (proc_root / str(pid) / "stat").read_text(encoding="utf-8")
    except FileNotFoundError:
        return "STOPPED"
    except OSError:
        return "UNVERIFIED"
    return "STOPPED" if stat.rsplit(") ", 1)[-1].split()[0] == "Z" else "RUNNING"


def inspect(tool: list[str] | None, flag: str, executable: Path, output: Path, label: str,
            timeout_seconds: float = INSPECTION_TIMEOUT_SECONDS, deadline_epoch: float | None = None) -> bool:
    if tool is None:
        write(output.with_name(f"{label}-status.txt"), "UNAVAILABLE: llvm-objdump and objdump not found")
        write(output.with_name(f"{label}-exit-code.txt"), "NOT_RUN")
        return False
    command = [*tool, flag, str(executable)]
    write(output.with_name(f"{label}-command.txt"), "\n".join(command))
    receipt = bounded_process(
        command, output, output.with_name(f"{label}-stderr.log"),
        output.with_name(f"{label}-receipt.json"), timeout_seconds, deadline_epoch,
    )
    state = str(receipt["state"])
    write(output.with_name(f"{label}-exit-code.txt"),
          str(receipt["childExitCode"]) if state == "EXITED" else state)
    if state != "EXITED":
        cleanup = str(receipt["cleanup"])
        if state == "TIMEOUT" and cleanup == "deadline_elapsed_before_start":
            detail = "child not started after deadline"
        elif state == "TIMEOUT":
            detail = f"cleanup={cleanup}; childExitCode={receipt['childExitCode']}; descendant liveness unverified"
        else:
            detail = f"cleanup={cleanup}; childExitCode={receipt['childExitCode']}"
        write(output.with_name(f"{label}-status.txt"),
              f"{state}: {detail}; see {label}-receipt.json")
        return False
    if receipt["childExitCode"] != 0:
        write(output.with_name(f"{label}-status.txt"), f"FAILED: tool exit {receipt['childExitCode']}")
        return False
    if output.stat().st_size == 0:
        write(output.with_name(f"{label}-status.txt"), "FAILED: tool produced no output")
        return False
    if label == "imports" and "DLL Name:" not in output.read_text(encoding="utf-8", errors="replace"):
        write(output.with_name(f"{label}-status.txt"), "FAILED: PE import list is absent")
        return False
    write(output.with_name(f"{label}-status.txt"), "OK")
    return True


def collect(test_directory: Path, output_directory: Path, gradle_log: Path, gradle_command: Path,
            build_file: Path, objdump: list[str] | None, deadline_epoch: float | None = None) -> bool:
    output_directory.mkdir(parents=True, exist_ok=True)
    write(output_directory / "test-executable-search.txt", str(test_directory.resolve()))
    candidates = sorted(test_directory.rglob("*.exe")) if test_directory.is_dir() else []
    write(output_directory / "test-executable-candidates.txt", "\n".join(str(path) for path in candidates) or "NONE")

    context = ["focused Gradle command:"]
    context.append(gradle_command.read_text(encoding="utf-8") if gradle_command.is_file() else "UNAVAILABLE")
    context.append("build.gradle.kts SHA-256:")
    context.append(sha256(build_file) if build_file.is_file() else "UNAVAILABLE")
    context.append("compiler/link lines from Gradle --info console:")
    if gradle_log.is_file():
        needles = ("compileTestKotlinMingwX64", "linkDebugTestMingwX64", "Run tool:",
                   "compiler arguments", "compilerArgs", "konanc", "Kotlin/Native compiler")
        lines = [line for line in gradle_log.read_text(encoding="utf-8", errors="replace").splitlines()
                 if any(needle.lower() in line.lower() for needle in needles)]
        context.extend(lines or ["UNAVAILABLE: no compiler or link command lines emitted"])
        write(output_directory / "compiler-link-invocation-status.txt",
              "OBSERVED: matching Gradle log lines only; input, output, and PE binding unverified" if lines else
              "UNAVAILABLE: no matching compiler/link log lines")
    else:
        context.append("UNAVAILABLE: Gradle console missing")
        write(output_directory / "compiler-link-invocation-status.txt", "UNAVAILABLE: Gradle console missing")
    write(output_directory / "compiler-link-context.txt", "\n".join(context))

    if len(candidates) != 1:
        write(output_directory / "test-executable-status.txt",
              f"UNAVAILABLE: expected one debugTest PE, found {len(candidates)}")
        for index, candidate in enumerate(candidates):
            retained = output_directory / f"candidate-{index}-{candidate.name}"
            shutil.copy2(candidate, retained)
            write(output_directory / f"candidate-{index}-sha256.txt", f"{sha256(retained)}  {retained.name}")
        return False

    retained = output_directory / candidates[0].name
    shutil.copy2(candidates[0], retained)
    write(output_directory / "test-executable-sha256.txt", f"{sha256(retained)}  {retained.name}")
    write(output_directory / "test-executable-status.txt", "OK")
    imports_ok = inspect(objdump, "-p", retained, output_directory / "test-imports.txt", "imports",
                         deadline_epoch=deadline_epoch)
    disassembly_ok = inspect(objdump, "-d", retained, output_directory / "test-disassembly.txt", "disassembly",
                             deadline_epoch=deadline_epoch)
    return imports_ok and disassembly_ok


def self_test() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        test_directory = root / "debugTest"
        test_directory.mkdir()
        log = root / "gradle.log"
        write(log, "> Task :dyn4k-core:linkDebugTestMingwX64\nRun tool: konanc -target mingw_x64 -o test")
        command = root / "gradle-command.txt"
        write(command, ".\\gradlew.bat :dyn4k-core:mingwX64Test --info")
        build_file = root / "build.gradle.kts"
        write(build_file, "mingwX64()")
        executable = test_directory / "test.exe"
        executable.write_bytes(b"MZtest")
        stub = root / "objdump.py"
        write(stub, "import sys\nprint('DLL Name: msvcrt.dll' if sys.argv[1] == '-p' else 'sqrtsd')")
        tool = [sys.executable, str(stub)]
        if not collect(test_directory, root / "positive", log, command, build_file, tool):
            raise AssertionError("one PE and working inspection tools were rejected")
        if sha256(root / "positive" / "test.exe") != sha256(executable):
            raise AssertionError("retained PE hash changed")
        if "linkDebugTestMingwX64" not in (root / "positive" / "compiler-link-context.txt").read_text():
            raise AssertionError("link context was not retained")
        status = (root / "positive" / "compiler-link-invocation-status.txt").read_text()
        if "binding unverified" not in status or "complete" in status:
            raise AssertionError("log line was overstated as complete compiler provenance")
        write(log, "> Task :dyn4k-core:linkDebugTestMingwX64\nRun tool: konanc")
        if not collect(test_directory, root / "partial-command", log, command, build_file, tool):
            raise AssertionError("partial compiler log blocked PE retention")
        if "binding unverified" not in (root / "partial-command" / "compiler-link-invocation-status.txt").read_text():
            raise AssertionError("partial compiler command was reported as complete")
        write(log, "Run tool: konanc -target mingw_x64 -o unrelated")
        if not collect(test_directory, root / "wrong-output", log, command, build_file, tool):
            raise AssertionError("unrelated compiler output blocked PE retention")
        if "binding unverified" not in (root / "wrong-output" / "compiler-link-invocation-status.txt").read_text():
            raise AssertionError("unrelated output was reported as bound to the PE")
        if "unrelated" not in (root / "wrong-output" / "compiler-link-context.txt").read_text():
            raise AssertionError("unrelated raw log line was discarded")
        if collect(test_directory, root / "missing-tool", log, command, build_file, None):
            raise AssertionError("missing inspection tool was accepted")
        if not (root / "missing-tool" / "disassembly-status.txt").is_file():
            raise AssertionError("missing disassembly status was not retained")
        empty_stub = root / "empty-objdump.py"
        write(empty_stub, "pass")
        if collect(test_directory, root / "empty-output", log, command, build_file,
                   [sys.executable, str(empty_stub)]):
            raise AssertionError("empty import and disassembly output was accepted")
        executable.unlink()
        if collect(test_directory, root / "missing-pe", log, command, build_file, tool):
            raise AssertionError("missing debugTest PE was accepted")
        (test_directory / "a.exe").write_bytes(b"MZa")
        (test_directory / "b.exe").write_bytes(b"MZb")
        if collect(test_directory, root / "ambiguous-pe", log, command, build_file, tool):
            raise AssertionError("ambiguous debugTest PEs were accepted")
        if len(list((root / "ambiguous-pe").glob("candidate-*.exe"))) != 2:
            raise AssertionError("ambiguous PEs were not retained")

        hanger = root / "hang.py"
        write(hanger, "import subprocess, sys, time\n"
              "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
              "print(f'child_pid={child.pid}', flush=True)\n"
              "print('partial stderr', file=sys.stderr, flush=True)\n"
              "time.sleep(60)")

        timeout_children: list[str] = []

        def check_stopped(stdout_path: Path) -> None:
            child_pid = int(stdout_path.read_text(encoding="utf-8").split("child_pid=", 1)[1].splitlines()[0])
            time.sleep(0.1)
            status = descendant_status(child_pid)
            if status == "RUNNING":
                raise AssertionError(f"timed-out child is still running: {child_pid}")
            timeout_children.append(status)

        executable.write_bytes(b"MZtest")
        timed = root / "timed-inspector"
        timed.mkdir()
        if inspect([sys.executable, str(hanger)], "-p", executable, timed / "test-imports.txt", "imports",
                   timeout_seconds=0.3):
            raise AssertionError("timed-out inspector was accepted")
        status = (timed / "imports-status.txt").read_text(encoding="utf-8")
        if not status.startswith("TIMEOUT"):
            raise AssertionError("inspector timeout status was not retained")
        if (timed / "imports-exit-code.txt").read_text(encoding="utf-8").strip() != "TIMEOUT":
            raise AssertionError("inspector timeout exit receipt was not retained")
        if "partial stderr" not in (timed / "imports-stderr.log").read_text(encoding="utf-8"):
            raise AssertionError("inspector partial stderr was lost")
        check_stopped(timed / "test-imports.txt")

        mode = root / "timed-mode"
        mode.mkdir()
        mode_receipt = bounded_process([sys.executable, str(hanger)], mode / "stdout.log", mode / "stderr.log",
                                       mode / "receipt.json", timeout_seconds=0.3)
        if mode_receipt["state"] != "TIMEOUT" or receipt_exit(mode_receipt) != 124:
            raise AssertionError("timed-out mode process was accepted")
        if "partial stderr" not in (mode / "stderr.log").read_text(encoding="utf-8"):
            raise AssertionError("mode partial stderr was lost")
        check_stopped(mode / "stdout.log")
        deadline = bounded_process([sys.executable, str(hanger)], mode / "skipped.stdout", mode / "skipped.stderr",
                                   mode / "skipped-receipt.json", timeout_seconds=1, deadline_epoch=time.time() - 1)
        if deadline["state"] != "TIMEOUT" or deadline["cleanup"] != "deadline_elapsed_before_start":
            raise AssertionError("elapsed deadline started a child process")
        if descendant_status(12345, root / "no-proc") != "UNVERIFIED":
            raise AssertionError("absence of /proc was reported as a stopped descendant")
        simulated = [descendant_status(12345, root / "no-proc") for _ in range(2)]
        if simulated.count("STOPPED") != 0 or simulated.count("UNVERIFIED") != 2:
            raise AssertionError("unverified descendants were counted as stopped")

        uncertain = ("taskkill_exit_1+direct_kill_failed_OSError+direct_wait_timeout",
                     "taskkill_failed_TimeoutExpired+direct_process_killed",
                     "process_group_kill_failed_PermissionError+direct_wait_timeout")
        for index, cleanup in enumerate(uncertain):
            receipt = {"state": "TIMEOUT", "cleanup": cleanup, "childExitCode": None}

            def simulated_timeout(_command: list[str], _stdout: Path, _stderr: Path, receipt_path: Path,
                                  _timeout: float, _deadline: float | None) -> dict[str, object]:
                receipt_path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
                return receipt

            destination = root / f"uncertain-{index}"
            destination.mkdir()
            with mock.patch.object(sys.modules[__name__], "bounded_process", side_effect=simulated_timeout):
                if inspect(tool, "-p", executable, destination / "test-imports.txt", "imports"):
                    raise AssertionError("uncertain cleanup was accepted")
            status = (destination / "imports-status.txt").read_text(encoding="utf-8")
            if cleanup not in status or "liveness unverified" not in status or "child stopped" in status:
                raise AssertionError("uncertain cleanup was overstated or omitted")
            if json.loads((destination / "imports-receipt.json").read_text())["cleanup"] != cleanup:
                raise AssertionError("raw cleanup uncertainty was not retained")

    print("TEST_PE_COLLECTION_SELF_TEST_OK positive=2 adverse=12 "
          f"timeout_children_stopped={timeout_children.count('STOPPED')} "
          f"timeout_children_unverified={timeout_children.count('UNVERIFIED')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("collect")
    command.add_argument("--test-directory", required=True, type=Path)
    command.add_argument("--output-directory", required=True, type=Path)
    command.add_argument("--gradle-log", required=True, type=Path)
    command.add_argument("--gradle-command", required=True, type=Path)
    command.add_argument("--build-file", required=True, type=Path)
    command.add_argument("--deadline-epoch", required=True, type=float)
    bounded = commands.add_parser("run-bounded")
    bounded.add_argument("--timeout-seconds", required=True, type=float)
    bounded.add_argument("--deadline-epoch", required=True, type=float)
    bounded.add_argument("--stdout", required=True, type=Path)
    bounded.add_argument("--stderr", required=True, type=Path)
    bounded.add_argument("--receipt", required=True, type=Path)
    bounded.add_argument("command_line", nargs=argparse.REMAINDER)
    commands.add_parser("self-test")
    args = parser.parse_args()
    if args.command == "self-test":
        return self_test()
    if args.command == "run-bounded":
        command_line = args.command_line[1:] if args.command_line[:1] == ["--"] else args.command_line
        if not command_line:
            parser.error("run-bounded needs a child command after --")
        receipt = bounded_process(command_line, args.stdout, args.stderr, args.receipt,
                                  args.timeout_seconds, args.deadline_epoch)
        print(f"BOUNDED_COMMAND_{receipt['state']} receipt={args.receipt}")
        return receipt_exit(receipt)
    try:
        ok = collect(args.test_directory, args.output_directory, args.gradle_log,
                     args.gradle_command, args.build_file, find_objdump(), args.deadline_epoch)
    except (OSError, ValueError) as error:
        args.output_directory.mkdir(parents=True, exist_ok=True)
        write(args.output_directory / "collector-status.txt", f"FAILED: {error}")
        print(f"TEST_PE_COLLECTION_FAILED {error}", file=sys.stderr)
        return 1
    write(args.output_directory / "collector-status.txt", "OK" if ok else "FAILED: see status files")
    print("TEST_PE_COLLECTION_OK" if ok else "TEST_PE_COLLECTION_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
