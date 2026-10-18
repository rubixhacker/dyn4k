#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import platform
import shutil
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


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(repository, *args):
    return subprocess.check_output(["git", "-C", str(repository), *args], text=True).strip()


def require_candidate(repository, candidate_sha):
    if git(repository, "rev-parse", "HEAD") != candidate_sha:
        raise ValueError("candidate SHA differs from checkout")
    if git(repository, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("dirty tracked or untracked source checkout")
    committed = subprocess.check_output(
        ["git", "-C", str(repository), "show", f"{candidate_sha}:{TRACKED_LOCK}"])
    if (repository / TRACKED_LOCK).read_bytes() != committed:
        raise ValueError("tracked lock differs from candidate")


def copy_file(repository, relative, output, prefix):
    source = repository / relative
    if not source.is_file() or source.is_symlink() or source.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"missing, unsafe, or oversized diagnostic file: {relative}")
    destination = output / prefix / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {"path": destination.relative_to(output).as_posix(),
            "sha256": digest(destination), "size": destination.stat().st_size}


def run_lock_task(repository, output):
    command = [str(repository / "gradlew"), "--no-daemon", "--console=plain",
               "--rerun-tasks", ":kotlinStoreYarnLock"]
    started = time.time_ns()
    process = subprocess.Popen(command, cwd=repository, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    finished = time.time_ns()
    (output / "stdout.txt").write_bytes(stdout)
    (output / "stderr.txt").write_bytes(stderr)
    return {"command": command, "pid": process.pid, "exit_code": process.returncode,
            "started_ns": started, "finished_ns": finished}


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
    receipt = {"schema": 1, "kind": "safari-yarn-lock-diagnostic",
               "candidate_sha": candidate_sha, "qualified": False,
               "host": {"system": platform.system(), "machine": platform.machine(),
                        "java_home": os.environ.get("JAVA_HOME"),
                        "runner_image_os": os.environ.get("ImageOS"),
                        "runner_image_version": os.environ.get("ImageVersion")},
               "tracked_sha256": digest(repository / TRACKED_LOCK)}
    process = run_lock_task(repository, output)
    receipt["process"] = process
    for name in ("stdout.txt", "stderr.txt"):
        path = output / name
        if path.is_file():
            files.append({"path": name, "sha256": digest(path), "size": path.stat().st_size})
    generated = repository / GENERATED_LOCK
    if generated.is_file() and not generated.is_symlink():
        files.append(copy_file(repository, GENERATED_LOCK, output, "generated"))
        receipt["generated_sha256"] = digest(generated)
    for relative in (Path("build/js/package.json"),):
        if (repository / relative).is_file():
            files.append(copy_file(repository, relative, output, "generated"))
    packages_root = repository / "build/js/packages"
    packages = sorted(packages_root.glob("*/package.json")) if packages_root.is_dir() else []
    if len(packages) > MAX_PACKAGES:
        raise ValueError("generated package input count exceeds diagnostic bound")
    for package in packages:
        files.append(copy_file(repository, package.relative_to(repository), output, "generated"))
    files.append(copy_file(repository, TRACKED_LOCK, output, "tracked-after"))
    receipt["tracked_after_sha256"] = digest(repository / TRACKED_LOCK)
    receipt["files"] = files
    receipt["tracked_changes_after"] = git(repository, "status", "--porcelain=v1",
                                             "--untracked-files=no")
    stderr = output / "stderr.txt"
    lock_error = (stderr.is_file() and
                  "Lock file was changed. Run the `kotlinUpgradeYarnLock` task"
                  in stderr.read_text(errors="replace"))
    if receipt["tracked_changes_after"] or receipt["tracked_after_sha256"] != receipt["tracked_sha256"]:
        receipt["status"] = "SOURCE_CHANGED"
    elif "generated_sha256" not in receipt:
        receipt["status"] = "NO_GENERATED_LOCK"
    elif process["exit_code"] == 0 and receipt["generated_sha256"] == receipt["tracked_sha256"]:
        receipt["status"] = "LOCK_MATCHED_DIAGNOSTIC_ONLY"
    elif (process["exit_code"] != 0
          and receipt["generated_sha256"] != receipt["tracked_sha256"]
          and lock_error):
        receipt["status"] = "LOCK_MISMATCH_CAPTURED"
    else:
        receipt["status"] = "OTHER_GRADLE_RESULT"
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
