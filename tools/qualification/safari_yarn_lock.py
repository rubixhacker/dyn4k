#!/usr/bin/env python3
import argparse
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
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TRACKED_LOCK = Path("kotlin-js-store/yarn.lock")
GENERATED_LOCK = Path("build/js/yarn.lock")
SOURCE_INPUTS = (Path("build.gradle.kts"), Path("settings.gradle.kts"),
                 Path("gradle/wrapper/gradle-wrapper.properties"))
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PACKAGES = 128
MAX_PROCESS_SECONDS = 600
MAX_DRAIN_SECONDS = 5
REQUIRED_PACKAGES = ("dyn4k-dyn4k-core", "dyn4k-dyn4k-core-test",
                     "dyn4k-dyn4k", "dyn4k-dyn4k-test")
REQUIRED_PACKAGE_INPUTS = (Path("build/js/package.json"),) + tuple(
    Path("build/js/packages") / name / "package.json" for name in REQUIRED_PACKAGES)
LOCK_ERROR_LINE = ("> Lock file was changed. Run the `kotlinUpgradeYarnLock` task "
                   "to actualize lock file")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(repository, *args):
    return subprocess.check_output(["git", "-C", str(repository), *args], text=True).strip()


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
    if git(repository, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("dirty tracked or untracked source checkout")
    committed = subprocess.check_output(
        ["git", "-C", str(repository), "show", f"{candidate_sha}:{TRACKED_LOCK}"])
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


def run_lock_task(repository, output):
    command = [str(repository / "gradlew"), "--no-daemon", "--console=plain",
               "--rerun-tasks", ":kotlinStoreYarnLock"]
    started = time.time_ns()
    process = subprocess.Popen(command, cwd=repository, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    deadline = time.monotonic() + MAX_PROCESS_SECONDS
    seen = {"stdout": 0, "stderr": 0}
    kept = {"stdout": 0, "stderr": 0}
    timed_out = False
    stream_incomplete = False
    with (output / "stdout.txt").open("wb") as stdout, \
            (output / "stderr.txt").open("wb") as stderr, \
            selectors.DefaultSelector() as selector:
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


def capture(repository, candidate_sha, output):
    repository = repository.resolve()
    output = output.resolve()
    if output.is_relative_to(repository):
        raise ValueError("diagnostic output must be outside the source checkout")
    if output.exists() and any(output.iterdir()):
        raise ValueError("diagnostic output must be empty")
    if (repository / GENERATED_LOCK).exists():
        raise ValueError("preexisting generated lock prevents a fresh diagnosis")
    require_candidate(repository, candidate_sha)
    output.mkdir(parents=True, exist_ok=True)
    files = [copy_file(repository, TRACKED_LOCK, output, "tracked")]
    files += [copy_file(repository, path, output, "inputs") for path in SOURCE_INPUTS]
    source_inputs = (TRACKED_LOCK, *SOURCE_INPUTS)
    committed_hashes = {path.as_posix(): hashlib.sha256(subprocess.check_output(
        ["git", "-C", str(repository), "show", f"{candidate_sha}:{path}"])).hexdigest()
                        for path in source_inputs}
    captured_hashes = {Path(item["source_path"]).relative_to(repository).as_posix():
                       item["sha256"] for item in files}
    if captured_hashes != committed_hashes:
        raise ValueError("archived source inputs differ from candidate")
    receipt = {"schema": 1, "kind": "safari-yarn-lock-diagnostic",
               "candidate_sha": candidate_sha, "qualified": False,
               "host": {"system": platform.system(), "machine": platform.machine(),
                        "java_home": os.environ.get("JAVA_HOME"),
                        "runner_image_os": os.environ.get("ImageOS"),
                        "runner_image_version": os.environ.get("ImageVersion")},
               "tracked_sha256": captured_hashes[TRACKED_LOCK.as_posix()],
               "source_input_sha256": committed_hashes}
    process = run_lock_task(repository, output)
    receipt["process"] = process
    for name in ("stdout.txt", "stderr.txt"):
        path = output / name
        if path.is_file():
            files.append({"path": name, "sha256": digest(path), "size": path.stat().st_size})
    receipt["head_after_task"] = git(repository, "rev-parse", "HEAD")
    receipt["tracked_changes_after_task"] = git(repository, "status", "--porcelain=v1",
                                                  "--untracked-files=no")
    try:
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
        if (receipt["head_after_task"] != candidate_sha
                or receipt["head_after"] != candidate_sha
                or receipt["tracked_changes_after_task"] or receipt["tracked_changes_after"]
                or receipt["source_input_after_sha256"] != committed_hashes):
            receipt["status"] = "SOURCE_CHANGED"
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
        elif process["exit_code"] == 0 and receipt["generated_sha256"] == receipt["tracked_sha256"]:
            receipt["status"] = "LOCK_MATCHED_DIAGNOSTIC_ONLY"
        elif (process["exit_code"] != 0
              and receipt["generated_sha256"] != receipt["tracked_sha256"]
              and lock_failure_signature(output / "stderr.txt")):
            receipt["status"] = "LOCK_MISMATCH_CAPTURED"
        else:
            receipt["status"] = "OTHER_GRADLE_RESULT"
    except (OSError, ValueError) as error:
        receipt.update(status="CAPTURE_REJECTED", reason=str(error))
    receipt["files"] = files
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description="Capture a Kotlin/JS Yarn lock mismatch")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    receipt = capture(ROOT, args.candidate_sha, args.output)
    print(json.dumps({"candidate_sha": receipt["candidate_sha"],
                      "status": receipt["status"], "qualified": False,
                      "output": str(args.output)}))
    return 0 if receipt["status"] in ("LOCK_MISMATCH_CAPTURED",
                                       "LOCK_MATCHED_DIAGNOSTIC_ONLY") else 1


if __name__ == "__main__":
    raise SystemExit(main())
