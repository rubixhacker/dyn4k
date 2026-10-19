#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

import qualify


BASELINE_SHA256 = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
HERE = Path(__file__).resolve().parent
AABB_FIXTURE = HERE / "fixtures/AabbSubclassDispatch.java"
AABB_EXPECTED = {
    "area": "12.0",
    "perimeter": "14.0",
    "intersection": "1.0,1.0,3.0,4.0,pairCalls=0,zeroCalls=0",
    "zero_single": "0.0,0.0,0.0,0.0,zeroCalls=0",
    "zero_pair": "0.0,0.0,0.0,0.0,zeroCalls=0",
}
FAMILIES = ("vector", "aabb", "geometry", "joint")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_candidate(repository, candidate_commit, audit, baseline_sha):
    qualify.require_clean_checkout(repository, candidate_commit)
    if (not isinstance(audit, dict) or audit.get("candidate_sha") != candidate_commit
            or audit.get("status") != "PASSED"
            or not isinstance(audit.get("targets"), list) or "jvm" not in audit["targets"]):
        raise ValueError("audit commit, status, or JVM target differs from candidate")
    qualify.verify_audit_against_staging(audit, repository)
    relative = qualify.target_binary_path("dyn4k-core", "jvm")
    artifacts = audit.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("audited artifacts are absent")
    selected = [item for item in artifacts if isinstance(item, dict) and item.get("path") == relative]
    if len(selected) != 1:
        raise ValueError("audited core JVM binary is missing or repeated")
    candidate = repository / "build/staging-repository" / relative
    if not candidate.is_file() or sha256(candidate) != selected[0].get("sha256"):
        raise ValueError("candidate artifact hash differs from the replayed audit")
    if sha256(candidate) == baseline_sha:
        raise ValueError("baseline JAR supplied as candidate")
    return candidate


def parse_aabb(raw, provider):
    values = {}
    for line in raw.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key in values:
            raise ValueError("AABB fixture has a malformed or duplicate observation")
        values[key] = value
    if set(values) != set(AABB_EXPECTED) | {"provider"}:
        raise ValueError("AABB fixture has missing or extra observations")
    url = urlparse(values.pop("provider"))
    if url.scheme != "file" or Path(unquote(url.path)).resolve() != provider.resolve():
        raise ValueError("AABB class provider differs from selected JAR")
    return values


def execute(command, output, name, environment):
    try:
        result = subprocess.run(command, capture_output=True, timeout=120, env=environment)
    except subprocess.TimeoutExpired as error:
        (output / f"{name}.stdout").write_bytes(error.stdout or b"")
        (output / f"{name}.stderr").write_bytes(error.stderr or b"")
        raise ValueError(f"{name} timed out") from error
    (output / f"{name}.stdout").write_bytes(result.stdout)
    (output / f"{name}.stderr").write_bytes(result.stderr)
    if result.returncode:
        raise ValueError(f"{name} exited {result.returncode}")
    return result.stdout.decode("utf-8")


def run_aabb(baseline, candidate, stdlib, java_home, output, environment):
    output.mkdir()
    classes = output / "classes"
    classes.mkdir()
    execute([str(java_home / "bin/javac"), "-encoding", "UTF-8", "-source", "8",
             "-target", "8", "-cp", str(baseline), "-d", str(classes), str(AABB_FIXTURE)],
            output, "compile", environment)
    observations = {}
    for name, provider in (("baseline", baseline), ("candidate", candidate)):
        raw = execute([str(java_home / "bin/java"), "-cp",
                       os.pathsep.join((str(classes), str(provider), str(stdlib))),
                       "AabbSubclassDispatch"], output, name, environment)
        observations[name] = parse_aabb(raw, provider)
    receipt = {"case_count": len(AABB_EXPECTED), "baseline": observations["baseline"],
               "candidate": observations["candidate"], "fixture_sha256": sha256(AABB_FIXTURE),
               "class_sha256": sha256(classes / "AabbSubclassDispatch.class"),
               "baseline_sha256": sha256(baseline), "candidate_sha256": sha256(candidate)}
    receipt["differences"] = {key: {"baseline": observations["baseline"][key],
                                    "candidate": observations["candidate"][key]}
                              for key in AABB_EXPECTED
                              if observations["baseline"][key] != observations["candidate"][key]}
    receipt["status"] = "PASSED" if observations["baseline"] == AABB_EXPECTED and not receipt["differences"] else "FAILED"
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    if receipt["status"] != "PASSED":
        raise ValueError("AABB subclass observations differ from pinned baseline")
    return receipt


def run_script(family, command, output, environment):
    output.mkdir()
    raw = execute(command, output, "runner", environment)
    summary = json.loads(raw)
    if family == "vector":
        if summary.get("fixture") != "MATCHED_BASELINE" or summary.get("qualification") != "unpassed":
            raise ValueError("vector fixture did not report a scoped match")
        receipt = summary
        receipt["status"] = "PASSED"
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    else:
        receipt = qualify.load_json_strict(output / "receipt.json")
        expected_count = 31
        if (summary.get("status") != "PASSED" or receipt.get("status") != "PASSED"
                or receipt.get("case_count", summary.get("cases")) != expected_count):
            raise ValueError(f"{family} fixture receipt is incomplete")
    return receipt


def family_command(family, args, candidate, output):
    python = os.environ.get("PYTHON", "python3")
    if family == "vector":
        return [python, str(HERE / "vector_subclass_dispatch.py"), "--baseline", str(args.baseline),
                "--repository", str(args.repository), "--candidate-commit", args.candidate_commit,
                "--audit", str(args.audit), "--stdlib", str(args.stdlib),
                "--java-home", str(args.java_home)]
    if family == "geometry":
        return [python, str(HERE / "geometry_subclass_dispatch.py"),
                "--baseline-jar", str(args.baseline), "--candidate-jar", str(candidate),
                "--kotlin-stdlib", str(args.stdlib), "--java-home", str(args.java_home),
                "--output", str(output)]
    return [python, str(HERE / "joint_subclass_dispatch.py"),
            "--baseline", str(args.baseline), "--candidate", str(candidate),
            "--kotlin-stdlib", str(args.stdlib), "--java-home", str(args.java_home),
            "--output", str(output)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--repository", type=Path)
    parser.add_argument("--candidate-commit")
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--diagnostic-jar", type=Path)
    parser.add_argument("--stdlib", required=True, type=Path)
    parser.add_argument("--java-home", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.pop("OLLAMA_API_KEY", None)
    (output / "java-tmp").mkdir(exist_ok=True)
    environment["JAVA_TOOL_OPTIONS"] = "-Djava.io.tmpdir=" + str(output / "java-tmp")
    receipt = {"status": "FAILED", "qualification": "unpassed", "families": {},
               "mode": "diagnostic" if args.diagnostic_jar else "audited-staged"}
    try:
        baseline = args.baseline.resolve(strict=True)
        stdlib = args.stdlib.resolve(strict=True)
        receipt["baseline_sha256"] = sha256(baseline)
        receipt["stdlib_sha256"] = sha256(stdlib)
        if receipt["baseline_sha256"] != BASELINE_SHA256:
            raise ValueError("pinned dyn4j 6.0.0 baseline JAR differs")
        if not (args.java_home / "bin/java").is_file() or not (args.java_home / "bin/javac").is_file():
            raise ValueError("selected JDK has no java or javac")
        if args.diagnostic_jar:
            if args.repository or args.candidate_commit or args.audit:
                raise ValueError("diagnostic JAR cannot carry candidate-bound arguments")
            candidate = args.diagnostic_jar.resolve(strict=True)
            if sha256(candidate) == BASELINE_SHA256:
                raise ValueError("baseline JAR supplied as diagnostic candidate")
            receipt["status"] = "UNQUALIFIED"
        else:
            if not args.repository or not args.candidate_commit or not args.audit:
                raise ValueError("candidate commit, repository, and staged audit are required")
            repository = args.repository.resolve(strict=True)
            audit = qualify.load_json_strict(args.audit)
            candidate = resolve_candidate(repository, args.candidate_commit, audit,
                                          receipt["baseline_sha256"])
            receipt["candidate_commit"] = args.candidate_commit
            receipt["audit_sha256"] = sha256(args.audit)
        receipt["candidate_path"] = str(candidate)
        receipt["candidate_sha256"] = sha256(candidate)
        receipt["java_home"] = str(args.java_home.resolve())
        errors = []
        for family in FAMILIES:
            directory = output / family
            try:
                if family == "aabb":
                    result = run_aabb(baseline, candidate, stdlib, args.java_home,
                                      directory, environment)
                elif family == "vector" and args.diagnostic_jar:
                    result = {"status": "UNQUALIFIED", "reason": "vector diagnostic requires the audited runner"}
                else:
                    result = run_script(family, family_command(family, args, candidate, directory),
                                        directory, environment)
                receipt["families"][family] = result["status"]
            except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired) as error:
                receipt["families"][family] = "FAILED"
                errors.append(f"{family}: {error}")
            directory.mkdir(exist_ok=True)
            (directory / "control.json").write_text(json.dumps(
                {"status": receipt["families"][family], "qualification": "unpassed",
                 "mode": receipt["mode"], "candidate_sha256": receipt["candidate_sha256"]},
                indent=2, sort_keys=True) + "\n")
        if errors:
            receipt["status"] = "UNQUALIFIED_FAILED" if args.diagnostic_jar else "FAILED"
            receipt["errors"] = errors
        elif not args.diagnostic_jar:
            receipt["status"] = "PASSED"
    except (OSError, ValueError) as error:
        receipt["error"] = str(error)
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": receipt["status"], "qualification": receipt["qualification"],
                      "families": receipt["families"], "error": receipt.get("error"),
                      "errors": receipt.get("errors")}, sort_keys=True))
    return 0 if receipt["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
