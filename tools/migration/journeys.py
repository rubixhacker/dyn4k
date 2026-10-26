#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


SAMPLE_REVISION = "2c6b318e929baab77e9753ae78a4965eee74a30a"
SOURCE_MANIFEST_SHA256 = "15ce636ac8eec34b24e73bc96270b49a44c94318850050b1e9bc0d930a9c8d58"
SCENES = ("Tracking", "Pyramid", "Crank", "Billiards", "Truck")
PROVIDERS = ("baseline", "candidate")
PINNED_JARS = {
    "dyn4j-6.0.0.jar": "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e",
    "jogl-all-2.3.2.jar": "e74603dc77b4183f108480279dbbf7fed3ac206069478636406c1fb45e83b31a",
    "gluegen-rt-2.3.2.jar": "084844543b18f7ff71b4c0437852bd22f0cb68d7e44c2c611c1bbea76f8c6fdf",
}
CANDIDATE_JAR = "dyn4k-core-jvm-0.1.0-alpha.1.jar"
JAVASSIST_SHA256 = "eba37290994b5e4868f3af98ff113f6244a6b099385d9ad46881307d3cb01aaf"
ROOT = Path(__file__).resolve().parents[2]


def require_clean_candidate(expected_commit=None):
    commit = git(ROOT, "rev-parse", "HEAD")
    if (expected_commit is not None and commit != expected_commit) or git(
            ROOT, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("candidate worktree changed; exact committed harness required")
    return commit


def git(samples, *arguments):
    result = subprocess.run(["git", "-C", str(samples), *arguments], capture_output=True, check=True)
    return result.stdout.decode().strip()


def inspect_samples(samples):
    if git(samples, "rev-parse", "HEAD") != SAMPLE_REVISION:
        raise ValueError("sample checkout revision differs from pinned revision")
    if git(samples, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("sample checkout changed")
    paths = git(samples, "ls-files", "--", "*.java").splitlines()
    if len(paths) != 42 or paths != sorted(paths):
        raise ValueError("expected 42 sorted tracked Java sources")
    manifest = "".join(
        f"{hashlib.sha256((samples / path).read_bytes()).hexdigest()}  {path}\n"
        for path in paths
    )
    digest = hashlib.sha256(manifest.encode()).hexdigest()
    if digest != SOURCE_MANIFEST_SHA256:
        raise ValueError("sample source manifest changed")
    return {"revision": SAMPLE_REVISION, "java_source_count": len(paths),
            "manifest_sha256": digest, "manifest": manifest}


def raw_evidence_manifest(output):
    paths = sorted(path for path in output.rglob("*") if path.is_file() or path.is_symlink())
    lines = []
    for path in paths:
        relative = path.relative_to(output).as_posix()
        if relative in ("summary.json", "evidence.sha256"):
            continue
        if path.is_symlink() or "\n" in relative:
            raise ValueError(f"unsafe raw evidence path: {relative}")
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {relative}\n")
    return "".join(lines).encode()


def write_summary(output, report):
    manifest = raw_evidence_manifest(output)
    (output / "evidence.sha256").write_bytes(manifest)
    report["evidence_manifest_sha256"] = hashlib.sha256(manifest).hexdigest()
    report["evidence_file_count"] = len(manifest.splitlines())
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")


def verify_evidence(output):
    report = json.loads((output / "summary.json").read_text())
    manifest = (output / "evidence.sha256").read_bytes()
    if (manifest != raw_evidence_manifest(output) or
            hashlib.sha256(manifest).hexdigest() != report.get("evidence_manifest_sha256") or
            len(manifest.splitlines()) != report.get("evidence_file_count")):
        raise ValueError("raw evidence changed or summary manifest binding differs")
    return report


def record_unavailable(output, reason):
    output.mkdir(parents=True, exist_ok=True)
    cases = [{"provider": provider, "scene": scene, "status": "UNAVAILABLE", "reason": reason}
             for provider in PROVIDERS for scene in SCENES]
    report = {"cases": cases, "expected_cases": 10, "passed_cases": 0,
              "unavailable_cases": 10, "failed_cases": 0}
    write_summary(output, report)
    return report


def inspect_artifacts(provider, resolved, repository):
    jars = sorted(resolved.glob("*.jar"))
    names = {jar.name for jar in jars}
    if len(jars) != len(names) or not jars:
        raise ValueError("resolved JAR set is empty or ambiguous")
    expected = {"jogl-all-2.3.2.jar", "gluegen-rt-2.3.2.jar"}
    expected.add("dyn4j-6.0.0.jar" if provider == "baseline" else CANDIDATE_JAR)
    if not expected <= names:
        raise ValueError(f"published dependency missing: {sorted(expected - names)}")
    if provider == "baseline" and names != expected:
        raise ValueError("baseline dependency graph has unexpected JARs")
    if provider == "candidate" and "dyn4j-6.0.0.jar" in names:
        raise ValueError("duplicate org.dyn4j provider in candidate graph")
    if provider == "candidate" and any(jar.name.startswith("dyn4k-core-") and jar.name != CANDIDATE_JAR for jar in jars):
        raise ValueError("candidate graph has multiple dyn4k-core artifacts")
    if provider == "candidate":
        if repository is None:
            raise ValueError("staged repository is required for candidate")
        staged_jar = repository / "io/github/rubixhacker/dyn4k-core-jvm/0.1.0-alpha.1" / CANDIDATE_JAR
        if not staged_jar.is_file() or staged_jar.read_bytes() != (resolved / CANDIDATE_JAR).read_bytes():
            raise ValueError("candidate JAR differs from staged publication")
        pom = staged_jar.with_suffix(".pom")
        module = staged_jar.with_suffix(".module")
        if not pom.is_file() or not module.is_file():
            raise ValueError("staged publication metadata missing")
        root = ET.parse(pom).getroot()
        identity = tuple(root.findtext(key) or root.findtext("{*}" + key)
                         for key in ("groupId", "artifactId", "version"))
        if identity != ("io.github.rubixhacker", "dyn4k-core-jvm", "0.1.0-alpha.1"):
            raise ValueError("staged publication metadata identity differs")
    observed = []
    for jar in jars:
        digest = hashlib.sha256(jar.read_bytes()).hexdigest()
        if jar.name in PINNED_JARS and digest != PINNED_JARS[jar.name]:
            raise ValueError(f"{jar.name} SHA-256 differs from pinned artifact")
        observed.append({"name": jar.name, "sha256": digest})
    report = {"provider": provider, "jars": observed}
    if provider == "candidate":
        report["staged_metadata"] = {
            "pom_sha256": hashlib.sha256(pom.read_bytes()).hexdigest(),
            "module_sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
        }
    return report


def compile_samples(provider, samples, resolved, repository, output, javac, timeout=180):
    if output.exists() and any(output.iterdir()):
        raise ValueError("compile output directory is not empty")
    classes = output / "classes"
    classes.mkdir(parents=True)
    report = {"provider": provider, "status": "FAILED", "exit_code": None,
              "stage": "preparation", "reason": None}
    try:
        source = inspect_samples(samples)
        artifacts = inspect_artifacts(provider, resolved, repository)
        sources = [samples / path for path in git(samples, "ls-files", "--", "*.java").splitlines()]
        classpath = os.pathsep.join(str(resolved / jar["name"]) for jar in artifacts["jars"])
        command = [str(javac), "--release", "8", "-cp", classpath, "-d", str(classes), *map(str, sources)]
        report.update(source_count=source["java_source_count"],
                      source_manifest_sha256=source["manifest_sha256"],
                      artifacts=artifacts["jars"], command=command, stage="compilation")
        exit_code = subprocess_log(command, output / "javac.log", timeout)
        report["exit_code"] = exit_code
        if exit_code:
            report["reason"] = "TIMEOUT" if exit_code == 124 else "javac failed"
        else:
            report["stage"] = "version"
            version_log = output / "javac-version.log"
            version_exit = subprocess_log([str(javac), "-version"], version_log, timeout)
            if version_exit:
                report["exit_code"] = version_exit
                report["reason"] = "TIMEOUT" if version_exit == 124 else "javac version failed"
            else:
                report["javac_version"] = version_log.read_text().strip()
                report["status"] = "PASSED"
                report["reason"] = None
        report["class_count"] = len(list(classes.rglob("*.class")))
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        report["reason"] = str(error)
        report["class_count"] = len(list(classes.rglob("*.class")))
    (output / "compile.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def subprocess_log(command, log, timeout=180):
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
        log.write_text(result.stdout + result.stderr)
        return result.returncode
    except subprocess.TimeoutExpired as error:
        output = error.stdout or b""
        stderr = error.stderr or b""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        log.write_text(output + stderr + "\nPROCESS TIMEOUT\n")
        return 124


def build_observer(plain_classes, observed_classes, resolved, instrumentation, javac, java, log, timeout=180):
    receipt = log.with_name("observer-build.json")
    report = {"status": "FAILED", "stage": "preparation", "exit_code": None, "reason": None,
              "commands": []}
    try:
        javassist = instrumentation / "javassist-3.30.2-GA.jar"
        if not javassist.is_file() or hashlib.sha256(javassist.read_bytes()).hexdigest() != JAVASSIST_SHA256:
            raise ValueError("Javassist artifact missing or SHA-256 changed")
        shutil.copytree(plain_classes, observed_classes)
        jars = sorted(resolved.glob("*.jar"))
        classpath = os.pathsep.join([str(observed_classes), *map(str, jars)])
        observer = ROOT / "consumers/migration/src/main/java/org/dyn4j/samples/framework/SceneObserver.java"
        weave = ROOT / "tools/migration/HookWeaver.java"
        commands = [
            [str(javac), "--release", "8", "-cp", classpath, "-d", str(observed_classes), str(observer)],
            [str(javac), "--release", "8", "-cp", os.pathsep.join([str(observed_classes), str(javassist)]),
             "-d", str(observed_classes), str(weave)],
            [str(java), "-cp", os.pathsep.join([classpath, str(javassist)]), "HookWeaver", str(observed_classes)],
        ]
        with log.open("w") as stream:
            for stage, command in zip(("observer compile", "weaver compile", "weave"), commands):
                report["stage"] = stage
                stream.write("$ " + " ".join(command) + "\n")
                command_log = log.with_name("observer-command.log")
                exit_code = subprocess_log(command, command_log, timeout)
                stream.write(command_log.read_text() + "\n")
                command_log.unlink()
                report["commands"].append({"stage": stage, "command": command, "exit_code": exit_code})
                report["exit_code"] = exit_code
                if exit_code:
                    report["reason"] = "TIMEOUT" if exit_code == 124 else f"{stage} failed"
                    break
            else:
                report.update(status="PASSED", reason=None)
    except (OSError, ValueError) as error:
        report["reason"] = str(error)
        with log.open("a") as stream:
            stream.write(str(error) + "\n")
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    return report["exit_code"] if report["status"] == "PASSED" else (report["exit_code"] or 1)


def podman_scene(scene, mode, samples, resolved, classes, output, jdk, image, cpuset=None, timeout=180):
    output.mkdir(parents=True)
    evidence = output / "evidence"
    evidence.mkdir()
    (evidence / "tmp").mkdir(mode=0o700)
    jars = sorted(resolved.glob("*.jar"))
    dependency_cp = ":".join("/work/lib/" + jar.name for jar in jars)
    script = "run-plain-scene.sh" if mode == "plain" else "run-scene.sh"
    container_classes = "/work/classes-plain" if mode == "plain" else "/work/classes"
    command = [
        "podman", "run", "--rm", "--network=none", "--userns=keep-id",
        "--security-opt", "label=disable",
        "-v", f"{samples.resolve()}:/work/samples:ro",
        "-v", f"{resolved.resolve()}:/work/lib:ro",
        "-v", f"{(ROOT / 'tools/migration').resolve()}:/work/tools/migration:ro",
        "-v", f"{classes.resolve()}:{container_classes}:ro",
        "-v", f"{evidence.resolve()}:/work/evidence:rw",
        "-v", f"{jdk.resolve()}:/jdk:ro",
        "-e", f"DEPENDENCY_CP={dependency_cp}",
        "-e", "PLAIN_EVIDENCE_DIR=/work/evidence",
        "-e", "TMPDIR=/work/evidence/tmp",
    ]
    if cpuset:
        command.extend(["-e", f"MIGRATION_CPUSET={cpuset}", image, "taskset", "-c", cpuset])
    else:
        command.append(image)
    command.extend(["bash", f"/work/tools/migration/{script}", scene])
    if mode == "observed":
        command.append("18" if scene == "Truck" else "12")
    (output / "invocation.json").write_text(json.dumps({"command": command}, indent=2) + "\n")
    exit_code = subprocess_log(command, output / "container.log", timeout=timeout)
    validation_path = evidence / scene / ("plain-validation.json" if mode == "plain" else "validation.json")
    try:
        validation = json.loads(validation_path.read_text())
    except (OSError, ValueError):
        validation = {}
    passed = exit_code == 0 and (validation.get("failed", validation.get("failed_checks")) == 0
                                 and validation.get("unexecuted", validation.get("unexecuted_checks")) == 0
                                 and validation.get("executed", validation.get("executed_checks", 0)) > 0)
    return {"mode": mode, "status": "PASSED" if passed else "FAILED", "exit_code": exit_code,
            "validation": validation, "evidence": str(evidence / scene)}


def run_all(samples, resolved_root, repository, instrumentation, output, javac, java, jdk, image, timeout, cpuset=None):
    commit = require_clean_candidate()
    source = inspect_samples(samples)
    if output.exists() and any(output.iterdir()):
        raise ValueError("journey output directory is not empty")
    output.mkdir(parents=True)
    image_id = None
    preparation = {"stage": "headful image", "status": "UNAVAILABLE", "reason": None}
    if shutil.which("podman") is None:
        preparation["reason"] = "podman executable unavailable"
    else:
        try:
            exists = subprocess.run(["podman", "image", "exists", image], capture_output=True,
                                    text=True, check=False, timeout=timeout)
            (output / "image-exists.log").write_text(exists.stdout + exists.stderr)
            if exists.returncode == 0:
                inspected = subprocess.run(["podman", "image", "inspect", "--format", "{{.Id}}", image],
                                           capture_output=True, text=True, check=False, timeout=timeout)
                (output / "image-inspect.log").write_text(inspected.stdout + inspected.stderr)
                if inspected.returncode == 0 and inspected.stdout.strip():
                    image_id = inspected.stdout.strip()
                    preparation["status"] = "PASSED"
                else:
                    preparation.update(status="FAILED", reason="headful image inspection failed",
                                       exit_code=inspected.returncode)
            else:
                preparation["reason"] = f"headful container image unavailable: {image}"
        except subprocess.TimeoutExpired as error:
            preparation.update(status="FAILED", reason="TIMEOUT", command=error.cmd)
        except OSError as error:
            preparation.update(status="FAILED", reason=str(error))
    (output / "preparation.json").write_text(json.dumps(preparation, indent=2) + "\n")
    image_available = preparation["status"] == "PASSED"
    cases = []
    for provider in PROVIDERS:
        provider_output = output / provider
        provider_output.mkdir()
        resolved = resolved_root / provider
        try:
            compile_report = compile_samples(provider, samples, resolved, repository, provider_output / "compile", javac, timeout)
        except (OSError, ValueError) as error:
            compile_report = {"status": "FAILED", "reason": str(error)}
            (provider_output / "compile.json").write_text(json.dumps(compile_report, indent=2) + "\n")
        if compile_report["status"] != "PASSED":
            cases.extend({"provider": provider, "scene": scene, "status": "FAILED",
                          "reason": "unchanged Java source compilation failed"} for scene in SCENES)
            continue
        if not image_available:
            cases.extend({"provider": provider, "scene": scene, "status": preparation["status"],
                          "reason": preparation["reason"]} for scene in SCENES)
            continue
        observed_classes = provider_output / "observer-classes"
        observer_status = build_observer(provider_output / "compile/classes", observed_classes,
                                         resolved, instrumentation, javac, java, provider_output / "observer-build.log", timeout)
        for scene in SCENES:
            plain = podman_scene(scene, "plain", samples, resolved, provider_output / "compile/classes",
                                 provider_output / scene / "plain", jdk, image, cpuset, timeout)
            observed = (podman_scene(scene, "observed", samples, resolved, observed_classes,
                                     provider_output / scene / "observed", jdk, image, cpuset, timeout)
                        if observer_status == 0 else {"status": "FAILED", "reason": "observer build failed"})
            cases.append({"provider": provider, "scene": scene,
                          "status": "PASSED" if plain["status"] == observed["status"] == "PASSED" else "FAILED",
                          "rendered_acceptance": "UNREVIEWED" if scene == "Truck" else "NOT_APPLICABLE",
                          "plain": plain, "observed": observed})
    try:
        require_clean_candidate(commit)
    except ValueError as error:
        (output / "candidate-check.json").write_text(json.dumps({"status": "FAILED", "reason": str(error)}, indent=2) + "\n")
        raise
    try:
        final_source = inspect_samples(samples)
        if any(final_source[key] != source[key] for key in
               ("revision", "java_source_count", "manifest_sha256", "manifest")):
            raise ValueError("sample source changed during journey execution")
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        (output / "sample-check.json").write_text(json.dumps({"status": "FAILED", "reason": str(error)}, indent=2) + "\n")
        raise
    (output / "sample-check.json").write_text(json.dumps({
        "status": "PASSED", "revision": final_source["revision"],
        "java_source_count": final_source["java_source_count"],
        "manifest_sha256": final_source["manifest_sha256"],
    }, indent=2) + "\n")
    report = {"candidate_commit": commit, "candidate_worktree_clean": True, "container_cpuset_cpus": cpuset,
              "truck_rendered_acceptance": "UNREVIEWED",
              "headful_image": image, "headful_image_id": image_id,
              "source_revision": source["revision"], "source_manifest_sha256": source["manifest_sha256"],
              "expected_cases": 10, "passed_cases": sum(case["status"] == "PASSED" for case in cases),
              "failed_cases": sum(case["status"] == "FAILED" for case in cases),
              "unavailable_cases": sum(case["status"] == "UNAVAILABLE" for case in cases), "cases": cases}
    write_summary(output, report)
    return report


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect-samples")
    inspect.add_argument("--samples", type=Path, required=True)
    unavailable = commands.add_parser("unavailable")
    unavailable.add_argument("--output", type=Path, required=True)
    unavailable.add_argument("--reason", required=True)
    verification = commands.add_parser("verify-evidence")
    verification.add_argument("--output", type=Path, required=True)
    artifacts = commands.add_parser("inspect-artifacts")
    artifacts.add_argument("--provider", choices=PROVIDERS, required=True)
    artifacts.add_argument("--resolved", type=Path, required=True)
    artifacts.add_argument("--repository", type=Path)
    compile_command = commands.add_parser("compile")
    compile_command.add_argument("--provider", choices=PROVIDERS, required=True)
    compile_command.add_argument("--samples", type=Path, required=True)
    compile_command.add_argument("--resolved", type=Path, required=True)
    compile_command.add_argument("--repository", type=Path)
    compile_command.add_argument("--output", type=Path, required=True)
    compile_command.add_argument("--javac", type=Path, default=Path("javac"))
    compile_command.add_argument("--timeout-seconds", type=float, default=180)
    run = commands.add_parser("run-all")
    run.add_argument("--samples", type=Path, required=True)
    run.add_argument("--resolved-root", type=Path, required=True)
    run.add_argument("--repository", type=Path, required=True)
    run.add_argument("--instrumentation", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--javac", type=Path, default=Path("javac"))
    run.add_argument("--java", type=Path, default=Path("java"))
    run.add_argument("--jdk", type=Path, required=True)
    run.add_argument("--headful-image", default="localhost/dyn4k-migration:journeys")
    run.add_argument("--timeout-seconds", type=float, default=180)
    run.add_argument("--cpuset-cpus")
    args = parser.parse_args()
    try:
        if hasattr(args, "timeout_seconds") and args.timeout_seconds <= 0:
            raise ValueError("timeout-seconds must be positive")
        if args.command == "inspect-samples":
            report = inspect_samples(args.samples)
            print(json.dumps({k: v for k, v in report.items() if k != "manifest"}, sort_keys=True))
        elif args.command == "inspect-artifacts":
            print(json.dumps(inspect_artifacts(args.provider, args.resolved, args.repository), sort_keys=True))
        elif args.command == "verify-evidence":
            report = verify_evidence(args.output)
            print(json.dumps({"evidence_file_count": report["evidence_file_count"],
                              "evidence_manifest_sha256": report["evidence_manifest_sha256"]}, sort_keys=True))
        elif args.command == "compile":
            report = compile_samples(args.provider, args.samples, args.resolved, args.repository, args.output,
                                     args.javac, args.timeout_seconds)
            print(json.dumps(report, sort_keys=True))
            return 0 if report["status"] == "PASSED" else 1
        elif args.command == "run-all":
            report = run_all(args.samples, args.resolved_root, args.repository,
                             args.instrumentation, args.output, args.javac, args.java,
                             args.jdk, args.headful_image, args.timeout_seconds, args.cpuset_cpus)
            print(json.dumps({key: report[key] for key in ("expected_cases", "passed_cases", "failed_cases", "unavailable_cases")}, sort_keys=True))
            return 0 if report["passed_cases"] == report["expected_cases"] else 1
        else:
            print(json.dumps(record_unavailable(args.output, args.reason), sort_keys=True))
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
