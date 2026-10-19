#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import qualify


BASELINE_SHA256 = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
FIXTURE = Path(__file__).resolve().parent / "fixtures/VectorSubclassDispatch.java"
MAIN = "qualification.VectorSubclassDispatch"
SUCCESS = "vector subclass dispatch passed\n"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invoke(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ValueError(
            f"command failed with exit {result.returncode}: {command[0]}\n"
            f"stdout: {result.stdout[-1000:]}\nstderr: {result.stderr[-1000:]}")
    return result.stdout


def run_fixture(java_home, provider, stdlib, classes):
    javac = java_home / "bin" / "javac"
    java = java_home / "bin" / "java"
    if not javac.is_file() or not java.is_file():
        raise ValueError("selected JDK has no javac or java executable")
    classes.mkdir()
    invoke([str(javac), "-encoding", "UTF-8", "-source", "8", "-target", "8",
            "-classpath", str(provider), "-d", str(classes), str(FIXTURE)])
    classpath = os.pathsep.join((str(classes), str(provider), str(stdlib)))
    result = invoke([str(java), "-classpath", classpath, MAIN])
    if result != SUCCESS:
        raise ValueError(f"subclass fixture output differs: {result!r}")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--stdlib", required=True, type=Path)
    parser.add_argument("--java-home", required=True, type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    qualify.require_clean_checkout(repository, args.candidate_commit)
    audit = qualify.load_json_strict(args.audit)
    if (audit.get("candidate_sha") != args.candidate_commit
            or audit.get("status") != "PASSED" or "jvm" not in audit.get("targets", [])):
        raise ValueError("selected staged audit or JVM target differs from candidate")
    qualify.verify_audit_against_staging(audit, repository)
    relative = qualify.target_binary_path("dyn4k-core", "jvm")
    artifacts = [item for item in audit["artifacts"] if item.get("path") == relative]
    if len(artifacts) != 1:
        raise ValueError("staged audit has no unique core JVM binary")
    candidate = repository / "build/staging-repository" / relative
    for path in (args.baseline, candidate, args.stdlib, FIXTURE):
        if not path.is_file():
            raise ValueError(f"required fixture or jar is absent: {path}")
    baseline_sha = digest(args.baseline)
    if baseline_sha != BASELINE_SHA256:
        raise ValueError("pinned dyn4j 6.0.0 baseline jar differs")
    candidate_sha = digest(candidate)
    if (candidate_sha == baseline_sha
            or candidate_sha != artifacts[0].get("sha256")):
        raise ValueError("candidate JVM provider differs from audited staged artifact")
    with tempfile.TemporaryDirectory(prefix="dyn4k-vector-dispatch-") as directory:
        root = Path(directory)
        baseline = run_fixture(args.java_home, args.baseline, args.stdlib,
                               root / "baseline")
        observed = run_fixture(args.java_home, candidate, args.stdlib,
                               root / "candidate")
    if observed != baseline:
        raise ValueError("candidate subclass dispatch differs from baseline")
    print(json.dumps({"fixture": "MATCHED_BASELINE", "qualification": "unpassed",
                      "candidate_commit": args.candidate_commit,
                      "baseline_sha256": baseline_sha,
                      "candidate_sha256": candidate_sha,
                      "fixture_sha256": digest(FIXTURE),
                      "stdlib_sha256": digest(args.stdlib),
                      "java_home": str(args.java_home)}, sort_keys=True))


if __name__ == "__main__":
    main()
