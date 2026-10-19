#!/usr/bin/env python3
import argparse
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

import independent_gates
import qualify


LANE = "jvm:Java:current:default"
run_command = subprocess.run


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_capture(repository, candidate_sha, staging, audit_path, output):
    repository, staging, output = Path(repository), Path(staging), Path(output)
    qualify.require_clean_checkout(repository, candidate_sha)
    audit = qualify.load_json_strict(audit_path)
    if audit.get("candidate_sha") != candidate_sha or audit.get("status") != "PASSED":
        raise ValueError("duplicate provider requires a passing exact-source staging audit")
    qualify.verify_audit_against_staging(audit, repository)
    hashes = qualify.target_binary_hashes(audit["artifacts"])["jvm"]
    source_tree = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "rev-parse",
         f"{candidate_sha}^{{tree}}"], text=True).strip()
    if output.exists():
        raise ValueError("duplicate provider output already exists")
    output.mkdir(parents=True)
    started = time.time_ns()
    (output / "artifacts").mkdir()
    for module in qualify.MODULES:
        source = staging / qualify.target_binary_path(module, "jvm")
        destination = output / "artifacts" / f"{module}.jar"
        shutil.copyfile(source, destination)
        if sha256(destination) != hashes[module]:
            raise ValueError(f"duplicate provider staged binary differs: {module}")
    base = ["./gradlew", "-p", "consumers/qualification", "--no-daemon", "--console=plain",
            f"-PqualificationRepository={staging.resolve()}", "-PwithUpstream=true"]
    graph_command = [*base, "dependencies", "--configuration", "runtimeClasspath"]
    graph = run_command(graph_command, cwd=repository, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, check=False)
    (output / "graph.log").write_bytes(graph.stdout)
    (output / "graph-command.json").write_text(json.dumps(
        {"command": graph_command, "exit_code": graph.returncode}) + "\n")
    command = [*base, "verifySingleProvider"]
    task = run_command(command, cwd=repository, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, check=False)
    (output / "task.raw.log").write_bytes(task.stdout)
    runtime = run_command(["java", "-version"], capture_output=True, check=False)
    (output / "runtime.log").write_bytes(runtime.stdout + runtime.stderr)
    graph_hash = sha256(output / "graph.log")
    output_text = (f"QUALIFICATION_LANE={LANE}\n".encode() + task.stdout +
                   f"\nQUALIFICATION_PROVIDER_GRAPH_SHA256={graph_hash}\n".encode())
    (output / "task.log").write_bytes(output_text)
    try:
        qualify.check_providers(graph.stdout.decode(errors="replace"))
    except ValueError as error:
        graph_has_duplicate = "duplicate org.dyn4j provider" in str(error)
    else:
        graph_has_duplicate = False
    diagnostic = b"duplicate org.dyn4j provider" in task.stdout
    succeeded = (graph.returncode == 0 and graph_has_duplicate and task.returncode != 0
                 and diagnostic and runtime.returncode == 0
                 and b"> Task :verifySingleProvider" in task.stdout
                 and b"BUILD FAILED" in task.stdout)
    finished = time.time_ns()
    paths = sorted(path for path in output.rglob("*") if path.is_file())
    files = [{"path": path.relative_to(output).as_posix(), "sha256": sha256(path),
              "mtime_ns": path.stat().st_mtime_ns} for path in paths]
    receipt = {"schema": 1, "status": "PASSED" if succeeded else "FAILED",
               "candidate_sha": candidate_sha, "source_tree": source_tree,
               "lane": LANE, "target": "jvm", "runtime": "Java", "version": "current",
               "configuration": "default",
               "runtime_identity": (runtime.stdout + runtime.stderr).decode(errors="replace").strip(),
               "artifact_hashes": hashes,
               "process": {"command": command, "exit_code": task.returncode,
                           "started_ns": started, "finished_ns": finished,
                           "stdout": "task.log", "stderr": "task.raw.log"},
               "provider_graph": "graph.log", "files": files}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    independent_gates._inventory(output, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--staging-repository", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run_capture(args.repository, args.candidate_sha, args.staging_repository,
                             args.audit, args.output)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "capture-error.txt").write_text(str(error) + "\n")
        raise SystemExit(1) from error
    print(json.dumps({"status": result["status"], "candidate_sha": result["candidate_sha"],
                      "task_exit": result["process"]["exit_code"]}))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
