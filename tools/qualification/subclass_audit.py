#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import qualify
import geometry_subclass_dispatch
import joint_subclass_dispatch
import subclass_provider
import vector_subclass_dispatch


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
JAVA_VERSION = re.compile(r'(?:openjdk|java) version "([^"]+)"')
JAVAC_VERSION = re.compile(r"\bjavac\s+(\S+)")


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
    if not subclass_provider.matches_provider(values.pop("provider"), provider):
        raise ValueError("AABB class provider differs from selected JAR")
    return values


def parse_vector(raw):
    if raw != vector_subclass_dispatch.SUCCESS:
        raise ValueError("vector fixture output is incomplete or differs")
    return raw


def execute(command, output, name, environment):
    started = datetime.now(timezone.utc)
    timed_out = False
    try:
        result = subprocess.run(command, capture_output=True, timeout=120, env=environment)
    except subprocess.TimeoutExpired as error:
        timed_out = True
        timeout_error = error
        stdout, stderr, exit_code = error.stdout or b"", error.stderr or b"", None
    else:
        stdout, stderr, exit_code = result.stdout, result.stderr, result.returncode
    finished = datetime.now(timezone.utc)
    (output / f"{name}.stdout").write_bytes(stdout)
    (output / f"{name}.stderr").write_bytes(stderr)
    metadata = {"schema": 1, "argv": command, "exit_code": exit_code,
                "started_at_utc": started.isoformat(), "finished_at_utc": finished.isoformat(),
                "timed_out": timed_out, "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
                "stdout_size": len(stdout), "stderr_size": len(stderr)}
    (output / f"{name}.process.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    if timed_out:
        raise ValueError(f"{name} timed out") from timeout_error
    if exit_code:
        raise ValueError(f"{name} exited {exit_code}")
    return stdout.decode("utf-8")


def verify_process(output, name, command):
    path = output / f"{name}.process.json"
    if any((output / f"{name}.{suffix}").is_symlink()
           for suffix in ("stdout", "stderr", "process.json")):
        raise ValueError(f"{name} process evidence contains a symlink")
    metadata = qualify.load_json_strict(path)
    expected = {"schema", "argv", "exit_code", "started_at_utc", "finished_at_utc",
                "timed_out", "stdout_sha256", "stderr_sha256", "stdout_size", "stderr_size"}
    if not isinstance(metadata, dict) or set(metadata) != expected:
        raise ValueError(f"{name} process metadata is incomplete")
    if metadata["argv"] != command:
        raise ValueError(f"{name} argv differs from expected command")
    if type(metadata["exit_code"]) is not int or metadata["exit_code"] != 0 or metadata["timed_out"] is not False:
        raise ValueError(f"{name} exit was not successful")
    try:
        started = datetime.fromisoformat(metadata["started_at_utc"])
        finished = datetime.fromisoformat(metadata["finished_at_utc"])
        if (started.utcoffset() != timezone.utc.utcoffset(started)
                or finished.utcoffset() != timezone.utc.utcoffset(finished)
                or finished < started):
            raise ValueError("invalid order or timezone")
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} invocation time is invalid") from error
    for stream in ("stdout", "stderr"):
        raw = (output / f"{name}.{stream}").read_bytes()
        if (metadata[f"{stream}_sha256"] != hashlib.sha256(raw).hexdigest()
                or metadata[f"{stream}_size"] != len(raw)):
            raise ValueError(f"{name} {stream} differs from recorded stream")
    return metadata


def verify_family_bindings(output, receipt):
    statuses = receipt.get("families")
    controls = receipt.get("family_controls")
    if (not isinstance(statuses, dict) or not isinstance(controls, dict)
            or set(statuses) != set(FAMILIES) or set(controls) != set(FAMILIES)):
        raise ValueError("top receipt has missing or extra family controls")
    for family in FAMILIES:
        if statuses[family] != "PASSED":
            raise ValueError(f"{family} did not pass")
        path = output / family / "control.json"
        if path.is_symlink() or sha256(path) != controls[family]:
            raise ValueError(f"{family} control differs from top receipt")
        control = qualify.load_json_strict(path)
        if control.get("status") != "PASSED":
            raise ValueError(f"{family} control did not pass")


def version_from_raw(java_raw, javac_raw, expected_major):
    java = JAVA_VERSION.search(java_raw)
    javac = JAVAC_VERSION.search(javac_raw)
    if not java or not javac or java.group(1) != javac.group(1):
        raise ValueError("Java and javac version observations differ or are absent")
    version = java.group(1)
    major = 8 if version.startswith("1.8.") else int(version.split(".", 1)[0])
    if major != expected_major:
        raise ValueError("observed Java major differs from selected JDK")
    return version


def run_jdk_identity(java_home, expected_major, output, environment):
    java = java_home / "bin/java"
    javac = java_home / "bin/javac"
    java_raw = execute([str(java), "-version"], output, "java-version", environment)
    javac_raw = execute([str(javac), "-version"], output, "javac-version", environment)
    java_text = java_raw + (output / "java-version.stderr").read_text()
    javac_text = javac_raw + (output / "javac-version.stderr").read_text()
    return {"major": expected_major, "version": version_from_raw(java_text, javac_text, expected_major),
            "home": str(java_home), "java_sha256": sha256(java), "javac_sha256": sha256(javac),
            "processes": {name: sha256(output / f"{name}.process.json")
                          for name in ("java-version", "javac-version")}}


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


def run_vector_raw(baseline, candidate, stdlib, java_home, output, environment):
    output.mkdir(exist_ok=True)
    classes = output / "raw-classes"
    classes.mkdir()
    fixture = vector_subclass_dispatch.FIXTURE
    execute([str(java_home / "bin/javac"), "-encoding", "UTF-8", "-source", "8",
             "-target", "8", "-cp", str(baseline), "-d", str(classes), str(fixture)],
            output, "raw-compile", environment)
    for name, provider in (("raw-baseline", baseline), ("raw-candidate", candidate)):
        parse_vector(execute([str(java_home / "bin/java"), "-cp",
                              os.pathsep.join((str(classes), str(provider), str(stdlib))),
                              vector_subclass_dispatch.MAIN], output, name, environment))
    receipt = {"status": "PASSED", "fixture_sha256": sha256(fixture),
               "class_sha256": sha256(classes / "qualification/VectorSubclassDispatch.class"),
               "baseline_sha256": sha256(baseline), "candidate_sha256": sha256(candidate)}
    (output / "raw-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def run_geometry(baseline, candidate, stdlib, java_home, output, environment):
    output.mkdir()
    classes = output / "classes"
    classes.mkdir()
    fixture = HERE / "fixtures/GeometrySubclassDispatch.java"
    execute([str(java_home / "bin/javac"), "-encoding", "UTF-8", "-source", "8",
             "-target", "8", "-cp", str(baseline), "-d", str(classes), str(fixture)],
            output, "compile", environment)
    observations = {}
    for name, provider in (("baseline", baseline), ("candidate", candidate)):
        raw = execute([str(java_home / "bin/java"), "-cp",
                       os.pathsep.join((str(provider), str(classes), str(stdlib))),
                       "GeometrySubclassDispatch"], output, name, environment)
        observations[name] = geometry_subclass_dispatch.parse(raw, provider)
    differences = {key: {name: observations[name][key] for name in observations}
                   for key in geometry_subclass_dispatch.CASES
                   if observations["baseline"][key] != observations["candidate"][key]}
    receipt = {"status": "PASSED" if not differences else "FAILED",
               "case_count": len(geometry_subclass_dispatch.CASES),
               "baseline": observations["baseline"], "candidate": observations["candidate"],
               "differences": differences, "fixture_sha256": sha256(fixture),
               "class_sha256": sha256(classes / "GeometrySubclassDispatch.class"),
               "baseline_sha256": sha256(baseline), "candidate_sha256": sha256(candidate)}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    if differences:
        raise ValueError("geometry subclass observations differ from pinned baseline")
    return receipt


def run_joint(baseline, candidate, stdlib, java_home, output, environment):
    output.mkdir()
    classes = output / "classes"
    classes.mkdir()
    fixture = HERE / "fixtures/JointSubclassDispatch.java"
    execute([str(java_home / "bin/javac"), "-encoding", "UTF-8", "-source", "8",
             "-target", "8", "-cp", str(baseline), "-d", str(classes), str(fixture)],
            output, "compile", environment)
    observations = {}
    for name, provider in (("baseline", baseline), ("candidate", candidate)):
        raw = execute([str(java_home / "bin/java"), "-cp",
                       os.pathsep.join((str(classes), str(provider), str(stdlib))),
                       "org.dyn4j.dynamics.joint.JointSubclassDispatch"], output, name, environment)
        observations[name] = joint_subclass_dispatch.observations(raw.encode("utf-8"), provider)
    expected = {**joint_subclass_dispatch.EXPECTED,
                **{key: observations["baseline"][key] for key in joint_subclass_dispatch.STATE_KEYS}}
    mismatches = {key: {"expected": value, "actual": observations["candidate"].get(key)}
                  for key, value in expected.items() if observations["candidate"].get(key) != value}
    if ({key: observations["baseline"][key] for key in joint_subclass_dispatch.EXPECTED}
            != joint_subclass_dispatch.EXPECTED):
        raise ValueError("pinned joint baseline observations changed")
    joint_subclass_dispatch.check_baseline_state(observations["baseline"])
    receipt = {"status": "PASSED" if not mismatches else "FAILED",
               "case_count": len(joint_subclass_dispatch.EXPECTED) + len(joint_subclass_dispatch.STATE_KEYS),
               "baseline": observations["baseline"], "candidate": observations["candidate"],
               "mismatches": mismatches, "fixture_sha256": sha256(fixture),
               "class_sha256": sha256(classes / "org/dyn4j/dynamics/joint/JointSubclassDispatch.class"),
               "baseline_sha256": sha256(baseline), "candidate_sha256": sha256(candidate)}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    if mismatches:
        raise ValueError("joint subclass observations differ from pinned baseline")
    return receipt


def run_vector_reviewed(command, output, environment):
    output.mkdir()
    raw = execute(command, output, "runner", environment)
    summary = json.loads(raw)
    if summary.get("fixture") != "MATCHED_BASELINE" or summary.get("qualification") != "unpassed":
        raise ValueError("vector fixture did not report a scoped match")
    receipt = {**summary, "status": "PASSED"}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def vector_runner_command(args):
    return [sys.executable, str(HERE / "vector_subclass_dispatch.py"),
            "--baseline", str(args.baseline), "--repository", str(args.repository),
            "--candidate-commit", args.candidate_commit, "--audit", str(args.audit),
            "--stdlib", str(args.stdlib), "--java-home", str(args.java_home)]


def expected_processes(family, args, baseline, candidate, stdlib, output):
    java = str(args.java_home / "bin/java")
    javac = str(args.java_home / "bin/javac")
    classes = output / ("raw-classes" if family == "vector" else "classes")
    fixture = (vector_subclass_dispatch.FIXTURE if family == "vector" else
               AABB_FIXTURE if family == "aabb" else
               HERE / "fixtures/GeometrySubclassDispatch.java" if family == "geometry" else
               HERE / "fixtures/JointSubclassDispatch.java")
    compile_name = "raw-compile" if family == "vector" else "compile"
    baseline_name = "raw-baseline" if family == "vector" else "baseline"
    candidate_name = "raw-candidate" if family == "vector" else "candidate"
    commands = {compile_name: [javac, "-encoding", "UTF-8", "-source", "8", "-target", "8",
                               "-cp", str(baseline), "-d", str(classes), str(fixture)]}
    for name, provider in ((baseline_name, baseline), (candidate_name, candidate)):
        if family == "geometry":
            classpath = os.pathsep.join((str(provider), str(classes), str(stdlib)))
            main = "GeometrySubclassDispatch"
        else:
            classpath = os.pathsep.join((str(classes), str(provider), str(stdlib)))
            main = (vector_subclass_dispatch.MAIN if family == "vector" else
                    "AabbSubclassDispatch" if family == "aabb" else
                    "org.dyn4j.dynamics.joint.JointSubclassDispatch")
        commands[name] = [java, "-cp", classpath, main]
    if family == "vector" and not args.diagnostic_jar:
        commands["runner"] = vector_runner_command(args)
    return commands


def verify_jdk_identity(args, output, recorded):
    java = args.java_home / "bin/java"
    javac = args.java_home / "bin/javac"
    commands = {"java-version": [str(java), "-version"],
                "javac-version": [str(javac), "-version"]}
    if (not isinstance(recorded, dict) or recorded.get("major") != args.jdk_major
            or recorded.get("home") != str(args.java_home)
            or recorded.get("java_sha256") != sha256(java)
            or recorded.get("javac_sha256") != sha256(javac)
            or set(recorded.get("processes", {})) != set(commands)):
        raise ValueError("JDK identity differs from selected Java home")
    for name, command in commands.items():
        verify_process(output, name, command)
        if sha256(output / f"{name}.process.json") != recorded["processes"][name]:
            raise ValueError("JDK version process metadata differs")
    java_text = ((output / "java-version.stdout").read_text()
                 + (output / "java-version.stderr").read_text())
    javac_text = ((output / "javac-version.stdout").read_text()
                  + (output / "javac-version.stderr").read_text())
    observed = version_from_raw(java_text, javac_text, args.jdk_major)
    if recorded.get("version") != observed:
        raise ValueError("observed Java version differs from receipt")


def verify_fixture(family, output, baseline, candidate, receipt):
    if receipt.get("status") != "PASSED":
        raise ValueError(f"{family} fixture receipt did not pass")
    if family == "vector":
        for name in ("raw-baseline", "raw-candidate"):
            parse_vector((output / f"{name}.stdout").read_text())
        if receipt.get("fixture") != "MATCHED_BASELINE" or receipt.get("qualification") != "unpassed":
            raise ValueError("vector reviewed runner result differs")
        raw_receipt = qualify.load_json_strict(output / "raw-receipt.json")
        if (raw_receipt.get("status") != "PASSED" or
                raw_receipt.get("candidate_sha256") != sha256(candidate)):
            raise ValueError("vector raw receipt differs")
    elif family == "aabb":
        observations = {name: parse_aabb((output / f"{name}.stdout").read_text(), provider)
                        for name, provider in (("baseline", baseline), ("candidate", candidate))}
        if (observations["baseline"] != AABB_EXPECTED or observations["candidate"] != AABB_EXPECTED
                or receipt.get("case_count") != len(AABB_EXPECTED)
                or receipt.get("baseline") != observations["baseline"]
                or receipt.get("candidate") != observations["candidate"]
                or receipt.get("differences") != {}):
            raise ValueError("AABB fixture observations or receipt differ")
    elif family == "geometry":
        observations = {
            name: geometry_subclass_dispatch.parse((output / f"{name}.stdout").read_text(), provider)
            for name, provider in (("baseline", baseline), ("candidate", candidate))}
        if (observations["baseline"] != observations["candidate"]
                or receipt.get("case_count") != len(geometry_subclass_dispatch.CASES)
                or receipt.get("baseline") != observations["baseline"]
                or receipt.get("candidate") != observations["candidate"]
                or receipt.get("differences") != {}):
            raise ValueError("geometry fixture observations or receipt differ")
    else:
        observations = {
            name: joint_subclass_dispatch.observations(
                (output / f"{name}.stdout").read_bytes(), provider)
            for name, provider in (("baseline", baseline), ("candidate", candidate))}
        joint_subclass_dispatch.check_baseline_state(observations["baseline"])
        if ({key: observations["baseline"][key] for key in joint_subclass_dispatch.EXPECTED}
                != joint_subclass_dispatch.EXPECTED
                or observations["baseline"] != observations["candidate"]
                or receipt.get("case_count") != len(joint_subclass_dispatch.EXPECTED)
                   + len(joint_subclass_dispatch.STATE_KEYS)
                or receipt.get("baseline") != observations["baseline"]
                or receipt.get("candidate") != observations["candidate"]
                or receipt.get("mismatches") != {}):
            raise ValueError("joint fixture observations or receipt differ")
    fixture = (vector_subclass_dispatch.FIXTURE if family == "vector" else
               AABB_FIXTURE if family == "aabb" else
               HERE / "fixtures/GeometrySubclassDispatch.java" if family == "geometry" else
               HERE / "fixtures/JointSubclassDispatch.java")
    classes = output / ("raw-classes" if family == "vector" else "classes")
    class_name = ("qualification/VectorSubclassDispatch.class" if family == "vector" else
                  "AabbSubclassDispatch.class" if family == "aabb" else
                  "GeometrySubclassDispatch.class" if family == "geometry" else
                  "org/dyn4j/dynamics/joint/JointSubclassDispatch.class")
    source_receipt = (raw_receipt if family == "vector" else receipt)
    if (source_receipt.get("fixture_sha256") != sha256(fixture)
            or source_receipt.get("class_sha256") != sha256(classes / class_name)
            or source_receipt.get("baseline_sha256") != sha256(baseline)
            or source_receipt.get("candidate_sha256") != sha256(candidate)):
        raise ValueError(f"{family} fixture or compiled class digest differs")


def verify_bundle(args):
    output = args.output.resolve(strict=True)
    receipt = qualify.load_json_strict(output / "receipt.json")
    diagnostic = bool(args.diagnostic_jar)
    expected_status = "UNQUALIFIED" if diagnostic else "PASSED"
    required = {"schema", "status", "qualification", "families", "family_controls",
                "mode", "capture_output_path", "baseline_sha256", "stdlib_sha256",
                "candidate_path", "candidate_sha256", "jdk"}
    if not diagnostic:
        required |= {"candidate_commit", "audit_sha256"}
    if (not isinstance(receipt, dict) or receipt.get("schema") != 2
            or set(receipt) != required
            or receipt.get("status") != expected_status or receipt.get("qualification") != "unpassed"
            or receipt.get("mode") != ("diagnostic" if diagnostic else "audited-staged")):
        raise ValueError("top subclass receipt has invalid mode or status")
    baseline = args.baseline.resolve(strict=True)
    stdlib = args.stdlib.resolve(strict=True)
    if (sha256(baseline) != BASELINE_SHA256 or receipt.get("baseline_sha256") != BASELINE_SHA256
            or receipt.get("stdlib_sha256") != sha256(stdlib)):
        raise ValueError("baseline or stdlib differs from receipt")
    args.java_home = args.java_home.resolve(strict=True)
    if diagnostic:
        if args.repository or args.candidate_commit or args.audit:
            raise ValueError("diagnostic replay cannot carry candidate-bound arguments")
        candidate = args.diagnostic_jar.resolve(strict=True)
        if sha256(candidate) == BASELINE_SHA256:
            raise ValueError("baseline JAR supplied as diagnostic candidate")
    else:
        if not args.repository or not args.candidate_commit or not args.audit:
            raise ValueError("candidate commit, repository, and staged audit are required")
        args.repository = args.repository.resolve(strict=True)
        args.audit = args.audit.resolve(strict=True)
        audit = qualify.load_json_strict(args.audit)
        candidate = resolve_candidate(args.repository, args.candidate_commit, audit, BASELINE_SHA256)
        if (receipt.get("candidate_commit") != args.candidate_commit
                or receipt.get("audit_sha256") != sha256(args.audit)):
            raise ValueError("candidate commit or staged audit differs from receipt")
    if (receipt.get("candidate_path") != str(candidate)
            or receipt.get("candidate_sha256") != sha256(candidate)):
        raise ValueError("candidate path or hash differs from receipt")
    captured_output = receipt.get("capture_output_path")
    if not isinstance(captured_output, str) or not Path(captured_output).is_absolute():
        raise ValueError("capture output path is absent or invalid")
    verify_jdk_identity(args, output, receipt.get("jdk"))
    verify_family_bindings(output, receipt)
    for family in FAMILIES:
        folder = output / family
        control = qualify.load_json_strict(folder / "control.json")
        commands = expected_processes(family, args, baseline, candidate, stdlib,
                                      Path(captured_output) / family)
        required_control = {"status", "qualification", "mode", "candidate_sha256",
                            "processes", "receipt_sha256"}
        if family == "vector":
            required_control.add("raw_receipt_sha256")
        if (set(control) != required_control
                or control.get("qualification") != "unpassed" or control.get("mode") != receipt["mode"]
                or control.get("candidate_sha256") != receipt["candidate_sha256"]
                or set(control.get("processes", {})) != set(commands)):
            raise ValueError(f"{family} process control is incomplete")
        for name, command in commands.items():
            verify_process(folder, name, command)
            if control["processes"][name] != sha256(folder / f"{name}.process.json"):
                raise ValueError(f"{family} process metadata digest differs")
        for suffix in ("stdout", "stderr", "process.json"):
            observed = {path.name.removesuffix("." + suffix) for path in folder.glob("*." + suffix)}
            if observed != set(commands):
                raise ValueError(f"{family} raw process set is incomplete or extra")
        family_receipt = qualify.load_json_strict(folder / "receipt.json")
        if control.get("receipt_sha256") != sha256(folder / "receipt.json"):
            raise ValueError(f"{family} fixture receipt digest differs")
        if family == "vector":
            if control.get("raw_receipt_sha256") != sha256(folder / "raw-receipt.json"):
                raise ValueError("vector raw receipt digest differs")
            if not diagnostic:
                summary = qualify.load_json_strict(folder / "runner.stdout")
                if (summary.get("candidate_commit") != args.candidate_commit
                        or summary.get("candidate_sha256") != sha256(candidate)
                        or {**summary, "status": "PASSED"} != family_receipt):
                    raise ValueError("vector reviewed runner receipt differs")
            elif family_receipt.get("candidate_sha256") != sha256(candidate):
                raise ValueError("vector reviewed runner receipt differs")
        verify_fixture(family, folder, baseline, candidate, family_receipt)
    return {"status": "VERIFIED_UNQUALIFIED" if diagnostic else "VERIFIED",
            "candidate_sha256": sha256(candidate), "families": list(FAMILIES),
            "java_version": receipt["jdk"]["version"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--repository", type=Path)
    parser.add_argument("--candidate-commit")
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--diagnostic-jar", type=Path)
    parser.add_argument("--stdlib", required=True, type=Path)
    parser.add_argument("--java-home", required=True, type=Path)
    parser.add_argument("--jdk-major", required=True, type=int, choices=(8, 21))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.verify:
        try:
            result = verify_bundle(args)
        except (OSError, UnicodeError, ValueError, TypeError) as error:
            print(json.dumps({"status": "FAILED", "error": str(error)}, sort_keys=True))
            return 1
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "VERIFIED" else 1
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("output already contains evidence; choose a new directory")
    output.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.pop("OLLAMA_API_KEY", None)
    (output / "java-tmp").mkdir(exist_ok=True)
    environment["JAVA_TOOL_OPTIONS"] = "-Djava.io.tmpdir=" + str(output / "java-tmp")
    receipt = {"schema": 2, "status": "FAILED", "qualification": "unpassed",
               "families": {}, "family_controls": {},
               "capture_output_path": str(output),
               "mode": "diagnostic" if args.diagnostic_jar else "audited-staged"}
    try:
        baseline = args.baseline.resolve(strict=True)
        stdlib = args.stdlib.resolve(strict=True)
        args.baseline, args.stdlib = baseline, stdlib
        args.java_home = args.java_home.resolve(strict=True)
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
            args.repository = repository
            args.audit = args.audit.resolve(strict=True)
            audit = qualify.load_json_strict(args.audit)
            candidate = resolve_candidate(repository, args.candidate_commit, audit,
                                          receipt["baseline_sha256"])
            receipt["candidate_commit"] = args.candidate_commit
            receipt["audit_sha256"] = sha256(args.audit)
        receipt["candidate_path"] = str(candidate)
        receipt["candidate_sha256"] = sha256(candidate)
        receipt["jdk"] = run_jdk_identity(args.java_home, args.jdk_major, output, environment)
        errors = []
        for family in FAMILIES:
            directory = output / family
            try:
                if family == "aabb":
                    result = run_aabb(baseline, candidate, stdlib, args.java_home,
                                      directory, environment)
                elif family == "vector" and args.diagnostic_jar:
                    result = run_vector_raw(baseline, candidate, stdlib, args.java_home,
                                            directory, environment)
                    result = {**result, "fixture": "MATCHED_BASELINE", "qualification": "unpassed"}
                    (directory / "receipt.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
                elif family == "vector":
                    result = run_vector_reviewed(vector_runner_command(args), directory, environment)
                    run_vector_raw(baseline, candidate, stdlib, args.java_home,
                                   directory, environment)
                elif family == "geometry":
                    result = run_geometry(baseline, candidate, stdlib, args.java_home,
                                          directory, environment)
                else:
                    result = run_joint(baseline, candidate, stdlib, args.java_home,
                                       directory, environment)
                receipt["families"][family] = result["status"]
            except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired) as error:
                receipt["families"][family] = "FAILED"
                errors.append(f"{family}: {error}")
            directory.mkdir(exist_ok=True)
            control = {"status": receipt["families"][family], "qualification": "unpassed",
                       "mode": receipt["mode"], "candidate_sha256": receipt["candidate_sha256"],
                       "processes": {path.name.removesuffix(".process.json"): sha256(path)
                                     for path in directory.glob("*.process.json")}}
            if (directory / "receipt.json").is_file():
                control["receipt_sha256"] = sha256(directory / "receipt.json")
            if (directory / "raw-receipt.json").is_file():
                control["raw_receipt_sha256"] = sha256(directory / "raw-receipt.json")
            (directory / "control.json").write_text(json.dumps(control, indent=2, sort_keys=True) + "\n")
            receipt["family_controls"][family] = sha256(directory / "control.json")
        if errors:
            receipt["status"] = "UNQUALIFIED_FAILED" if args.diagnostic_jar else "FAILED"
            receipt["errors"] = errors
        elif not args.diagnostic_jar:
            receipt["status"] = "PASSED"
    except (OSError, ValueError) as error:
        receipt["error"] = str(error)
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    if receipt["status"] in ("PASSED", "UNQUALIFIED"):
        try:
            verify_bundle(args)
        except (OSError, UnicodeError, ValueError, TypeError) as error:
            receipt["status"] = "UNQUALIFIED_FAILED" if args.diagnostic_jar else "FAILED"
            receipt["error"] = f"public replay failed: {error}"
            (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": receipt["status"], "qualification": receipt["qualification"],
                      "families": receipt["families"], "error": receipt.get("error"),
                      "errors": receipt.get("errors")}, sort_keys=True))
    return 0 if receipt["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
