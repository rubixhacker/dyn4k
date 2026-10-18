#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath, PureWindowsPath

import qualify


def publication_tasks(targets):
    if not targets or len(set(targets)) != len(targets) or not set(targets) <= qualify.matrix_targets():
        raise ValueError("publication targets are missing, duplicate, or unknown")
    return [f":{module}:publish{publication}PublicationToStagingRepository"
            for module in qualify.MODULES
            for publication in ("KotlinMultiplatform", *(target[0].upper() + target[1:] for target in targets))]


def stage_command(repository, tasks):
    wrapper = repository / ("gradlew.bat" if isinstance(repository, PureWindowsPath) else "gradlew")
    return [str(wrapper), "--no-daemon", "--console=plain", *tasks]


def receipt_repository(value):
    if isinstance(value, str):
        for path_type in (PureWindowsPath, PurePosixPath):
            path = path_type(value)
            windows_components = ((*path.anchor.split("\\"), *path.parts[1:])
                                  if path_type is PureWindowsPath else ())
            if (path.is_absolute() and str(path) == value and ".." not in path.parts
                    and not (path_type is PurePosixPath and value.startswith("//"))
                    and not any(part.rstrip(" .") != part for part in windows_components)):
                return path
    return None


def checkout_for_console(console):
    resolved = console.resolve()
    for root in resolved.parents:
        if (root / ".git").exists() and resolved.is_relative_to(
                root / "build/staging-repository/.qualification"):
            try:
                checkout = Path(subprocess.check_output(
                    ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                    text=True, stderr=subprocess.PIPE).strip()).resolve()
            except subprocess.CalledProcessError as error:
                raise ValueError("staging console checkout is invalid") from error
            if checkout != root:
                raise ValueError("staging console differs from resolved checkout")
            return checkout
    return None


def verify_receipt(receipt, console, candidate_sha, targets, expected_repository=None):
    tasks = publication_tasks(targets)
    repository = receipt_repository(receipt.get("repository"))
    if repository is None or receipt.get("command") != stage_command(repository, tasks):
        raise ValueError("staging receipt command differs from required Gradle invocation")
    checkout = checkout_for_console(console)
    if expected_repository is not None:
        trusted = receipt_repository(str(expected_repository))
        if trusted is None or str(repository) != str(trusted):
            raise ValueError("staging receipt repository differs from producer checkout")
    if checkout is not None and str(repository) != str(checkout):
        raise ValueError("staging receipt repository differs from producer checkout")
    if (receipt.get("candidate_sha") != candidate_sha
            or receipt.get("targets") != list(targets)
            or receipt.get("tasks") != tasks
            or receipt.get("status") != "PASSED"
            or receipt.get("exit_code") != 0):
        raise ValueError("staging receipt candidate, targets, tasks, or outcome differs")
    if not console.is_file() or console.is_symlink():
        raise ValueError("staging console is missing")
    raw = console.read_bytes()
    if hashlib.sha256(raw).hexdigest() != receipt.get("console_sha256"):
        raise ValueError("staging console bytes differ from receipt")
    lines = raw.decode("utf-8", errors="replace").splitlines()
    observed = {}
    for line in lines:
        match = re.fullmatch(r"> Task (:[^ ]+)(?: (.*))?", line)
        if match:
            observed[match.group(1)] = match.group(2) or "EXECUTED"
    if any(observed.get(task) not in ("EXECUTED", "UP-TO-DATE", "FROM-CACHE") for task in tasks):
        raise ValueError("staging console has a missing, skipped, or failed publication task")
    if "BUILD SUCCESSFUL" not in raw.decode("utf-8", errors="replace"):
        raise ValueError("staging console lacks a successful Gradle outcome")


def run_stage(repository, candidate_sha, targets, output, console):
    repository = repository.resolve()
    qualify.require_clean_checkout(repository, candidate_sha)
    targets = tuple(sorted(targets))
    tasks = publication_tasks(targets)
    command = stage_command(repository, tasks)
    console.parent.mkdir(parents=True, exist_ok=True)
    with console.open("wb") as stream:
        completed = subprocess.run(command, cwd=repository, stdout=stream,
                                   stderr=subprocess.STDOUT, check=False)
    receipt = {"candidate_sha": candidate_sha, "repository": str(repository),
               "targets": list(targets), "tasks": tasks,
               "command": command, "exit_code": completed.returncode,
               "console_sha256": hashlib.sha256(console.read_bytes()).hexdigest(),
               "status": "PASSED" if completed.returncode == 0 else "FAILED"}
    if receipt["status"] == "PASSED":
        try:
            verify_receipt(receipt, console, candidate_sha, targets, repository)
        except ValueError as error:
            receipt.update(status="FAILED", reason=str(error))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--target", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--console", type=Path, required=True)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[2]
    result = run_stage(repository, args.candidate_sha, args.target, args.output, args.console)
    print(json.dumps(result))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
