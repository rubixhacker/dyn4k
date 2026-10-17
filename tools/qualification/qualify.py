#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
VERSION = "0.1.0-alpha.1"
GROUP = "io.github.rubixhacker"
MODULES = ("dyn4k-core", "dyn4k")


def matrix():
    groups = [
        ("jvm", ["Java"], "8", "jvm"),
        ("android", ["Android JVM"], "API 21", "android"),
        ("js", ["Chromium", "Firefox", "Safari", "Node.js"], "119/120/18.2/22.0.0", "web"),
        ("wasmJs", ["Chromium", "Firefox", "Safari", "Node.js"], "119/120/18.2/22.0.0", "web"),
        ("wasmWasi", ["Node.js", "Wasmtime"], "24.15.0/37.0.0", "web"),
        ("linuxX64", ["Linux x64"], "kernel 4.9.156 glibc 2.19", "native"),
        ("linuxArm64", ["Linux ARM64"], "kernel 4.9.156 glibc 2.25", "native"),
        ("mingwX64", ["Windows x64"], "Windows 10 1507 build 10240", "native"),
        ("macosArm64", ["macOS ARM64"], "macOS 11", "native"),
        ("iosArm64", ["iOS physical ARM64"], "iOS 15", "native"),
        ("iosSimulatorArm64", ["iOS simulator ARM64"], "iOS 15", "native"),
        ("iosX64", ["iOS simulator x64"], "iOS 15", "native"),
        ("tvosArm64", ["tvOS physical ARM64"], "tvOS 15", "native"),
        ("tvosSimulatorArm64", ["tvOS simulator ARM64"], "tvOS 15", "native"),
        ("watchosArm64", ["watchOS physical ILP32"], "watchOS 8", "native"),
        ("watchosDeviceArm64", ["watchOS physical LP64"], "watchOS 26", "native"),
        ("watchosSimulatorArm64", ["watchOS simulator ARM64"], "watchOS 8", "native"),
        ("androidNativeArm32", ["Android Native armeabi-v7a"], "API 21", "native"),
        ("androidNativeArm64", ["Android Native arm64-v8a"], "API 21", "native"),
        ("androidNativeX86", ["Android Native x86"], "API 21", "native"),
        ("androidNativeX64", ["Android Native x86_64"], "API 21", "native"),
    ]
    rows = []
    web_floors = {"Chromium": "119", "Firefox": "120", "Safari": "18.2", "Node.js": "22.0.0"}
    for target, runtimes, floor, kind in groups:
        for runtime in runtimes:
            minimum = floor
            if target in ("js", "wasmJs"):
                minimum = web_floors[runtime]
            elif target == "wasmWasi":
                minimum = "24.15.0 without experimental Wasm flags" if runtime == "Node.js" else "37.0.0 with -W gc=y -W exceptions=y -W function-references=y"
            rows.append({"target": target, "runtime": runtime, "minimum": minimum, "kind": kind})
    assert len(rows) == 28 and len({row["target"] for row in rows}) == 21
    return rows


def expand(rows):
    configs = {"jvm": ("no-optimize", "default"),
               "android": ("debug", "r8-optimized"),
               "web": ("development", "production"),
               "native": ("debug-g", "optimized-opt")}
    return [{**row, "version": version, "configuration": config,
             "id": f'{row["target"]}:{row["runtime"]}:{version}:{config}'}
            for row in rows for version in ("minimum", "current")
            for config in configs[row["kind"]]]


def check_providers(graph):
    if re.search(r"(?:^|\W)org\.dyn4j:dyn4j(?::|\W)", graph) and re.search(
        r"(?:^|\W)io\.github\.rubixhacker:dyn4k-core(?:-jvm)?(?::|\W)", graph
    ):
        raise ValueError("duplicate org.dyn4j provider: exclude org.dyn4j:dyn4j from the consumer dependency graph")


def evaluate(case, evidence, candidate_sha=None, artifact_hashes=None):
    result = {"id": case["id"], "status": "NOT_RUN"}
    if evidence is None:
        result["reason"] = "no evidence supplied"
        return result
    if evidence.get("unavailable_reason"):
        result.update(status="UNAVAILABLE", reason=evidence["unavailable_reason"])
        return result
    required = ("candidate_sha", "artifact_sha256", "runtime_identity", "runtime_version",
                "expected", "executed", "failures", "skipped", "consumer", "suite",
                "target", "runtime", "version", "configuration")
    missing = [name for name in required if name not in evidence]
    problems = [f"missing {name}" for name in missing]
    if not SHA40.fullmatch(str(evidence.get("candidate_sha", ""))):
        problems.append("candidate SHA must be a full commit hash")
    if candidate_sha and evidence.get("candidate_sha") != candidate_sha:
        problems.append("candidate SHA differs from report")
    if not SHA64.fullmatch(str(evidence.get("artifact_sha256", ""))):
        problems.append("artifact SHA-256 is missing or malformed")
    if artifact_hashes is not None and evidence.get("artifact_sha256") not in artifact_hashes:
        problems.append("artifact SHA-256 is absent from staged audit")
    if not evidence.get("runtime_identity"):
        problems.append("runtime identity is empty")
    if not evidence.get("runtime_version"):
        problems.append("runtime version is empty")
    for key in ("target", "runtime", "version", "configuration"):
        if evidence.get(key) != case[key]:
            problems.append(f"{key} differs from lane")
    for key in ("expected", "executed", "failures", "skipped"):
        if type(evidence.get(key)) is not int or evidence[key] < 0:
            problems.append(f"{key} must be a nonnegative integer")
    if all(type(evidence.get(key)) is int for key in ("expected", "executed", "failures", "skipped")):
        if evidence["expected"] == 0 or evidence["executed"] != evidence["expected"]:
            problems.append("empty or incomplete suite")
        if evidence["failures"] or evidence["skipped"]:
            problems.append("failed or skipped tests")
    if evidence.get("consumer") != "PASSED":
        problems.append("staged external consumer did not pass")
    if evidence.get("suite") != "complete":
        problems.append("full portable correctness suite was not executed")
    result.update(status="FAILED" if problems else "PASSED",
                  reason="; ".join(problems) if problems else "all required evidence present")
    return result


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def audit_staging(root, candidate_sha):
    errors, artifacts = [], []
    if not SHA40.fullmatch(candidate_sha):
        raise ValueError("candidate SHA must be a full commit hash")
    for module in MODULES:
        root_metadata = root / GROUP.replace(".", "/") / module / VERSION / f"{module}-{VERSION}.module"
        if root_metadata.is_file():
            root_data = json.loads(root_metadata.read_text())
            published = {item.get("available-at", {}).get("module")
                         for item in root_data.get("variants", [])}
            published.discard(None)
            expected = {module + "-" + target.lower().replace("wasmjs", "wasm-js").replace("wasmwasi", "wasm-wasi")
                        for target in {row["target"] for row in matrix()}}
            if published != expected:
                errors.append(f"{module}: root metadata target mapping differs: missing={sorted(expected - published)} extra={sorted(published - expected)}")
        else:
            errors.append(f"{module}: root Gradle metadata missing")
            published = set()
        for name in [module] + sorted(published | expected):
            base = root / GROUP.replace(".", "/") / name / VERSION
            pom = base / f"{name}-{VERSION}.pom"
            metadata = base / f"{name}-{VERSION}.module"
            if not pom.is_file() or not metadata.is_file():
                errors.append(f"{name}: staged POM or Gradle metadata missing")
                continue
            pom_root = ET.parse(pom).getroot()
            ns = "{http://maven.apache.org/POM/4.0.0}"
            for key, expected in (("groupId", GROUP), ("artifactId", name), ("version", VERSION)):
                if pom_root.findtext(ns + key) != expected:
                    errors.append(f"{name}: wrong POM {key}")
            for key in ("name", "description", "url", "licenses", "scm", "developers"):
                if pom_root.find(ns + key) is None:
                    errors.append(f"{name}: missing POM {key}")
            dependencies = {(entry.findtext(ns + "groupId"), entry.findtext(ns + "artifactId"),
                             entry.findtext(ns + "version"))
                            for entry in pom_root.findall(ns + "dependencies/" + ns + "dependency")}
            if any(group == "org.dyn4j" for group, _, _ in dependencies):
                errors.append(f"{name}: upstream dyn4j leaks into production dependencies")
            if module == "dyn4k" and (GROUP, name.replace("dyn4k", "dyn4k-core", 1), VERSION) not in dependencies:
                errors.append(f"{name}: coordinated dyn4k-core dependency missing")
            module_data = json.loads(metadata.read_text())
            if module_data.get("component", {}).get("version") != VERSION:
                errors.append(f"{name}: wrong Gradle metadata version")
            files = [path for path in base.iterdir() if path.is_file() and path.suffix in (".jar", ".aar", ".klib", ".md")]
            binaries = [path for path in files if "sources" not in path.name and "javadoc" not in path.name
                        and "dokka" not in path.name and "license" not in path.name]
            if not binaries:
                errors.append(f"{name}: no staged binary")
            if not any("sources" in path.name for path in files):
                errors.append(f"{name}: sources artifact missing")
            if not any("javadoc" in path.name or "dokka" in path.name for path in files):
                errors.append(f"{name}: API documentation artifact missing")
            if not any("license" in path.name for path in files):
                errors.append(f"{name}: license artifact missing")
            for license_file in (path for path in files if "license" in path.name):
                source_license = Path("LICENSE.md")
                if source_license.is_file() and license_file.read_bytes() != source_license.read_bytes():
                    errors.append(f"{name}: license differs from repository license")
            for path in [pom, metadata] + files:
                sha = digest(path)
                artifacts.append({"path": str(path.relative_to(root)), "sha256": sha})
                checksum = path.with_name(path.name + ".sha256")
                if not checksum.is_file() or checksum.read_text().strip().lower() != sha:
                    errors.append(f"{path.name}: SHA-256 sidecar missing or incorrect")
                if path.suffix == ".jar" and "sources" not in path.name and "javadoc" not in path.name:
                    with zipfile.ZipFile(path) as archive:
                        if "META-INF/LICENSE.md" not in archive.namelist():
                            errors.append(f"{path.name}: embedded license missing")
    return {"candidate_sha": candidate_sha, "artifacts": artifacts,
            "status": "PASSED" if not errors else "FAILED", "errors": errors}


def run_probe(command, report_paths, candidate_sha, output):
    for pattern in report_paths:
        for path in Path().glob(pattern):
            path.unlink()
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    expected = executed = failures = skipped = 0
    for pattern in report_paths:
        for path in Path().glob(pattern):
            root = ET.parse(path).getroot()
            expected += int(root.get("tests", 0))
            skipped += int(root.get("skipped", 0))
            failures += int(root.get("failures", 0)) + int(root.get("errors", 0))
            executed += int(root.get("tests", 0)) - int(root.get("skipped", 0))
    result = {"candidate_sha": candidate_sha, "command": command,
              "exit_code": completed.returncode, "expected": expected,
              "executed": executed, "failures": failures, "skipped": skipped,
              "status": "FAILED" if completed.returncode or failures or skipped or not expected else "PASSED",
              "scope": "foundation probe only; not a complete lane"}
    output.write_text(json.dumps(result, indent=2) + "\n")
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    return result


def execute_plan(plan, candidate_sha, output):
    evidence = {}
    for case in expand(matrix()):
        specification = plan.get(case["id"])
        if specification is None:
            continue
        if specification.get("unavailable_reason"):
            evidence[case["id"]] = {"unavailable_reason": specification["unavailable_reason"]}
            continue
        command = specification.get("command")
        if not isinstance(command, list) or not command:
            evidence[case["id"]] = {"error": "no executable command"}
            continue
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        result_file = Path(specification.get("result_file", ""))
        if result.returncode or not result_file.is_file():
            evidence[case["id"]] = {"error": "command failed or result file missing",
                                    "exit_code": result.returncode,
                                    "stderr": result.stderr[-4000:]}
            continue
        observed = json.loads(result_file.read_text())
        observed["command"] = command
        observed["exit_code"] = result.returncode
        evidence[case["id"]] = observed
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("matrix")
    record = sub.add_parser("record")
    record.add_argument("--candidate-sha", required=True)
    record.add_argument("--evidence", type=Path)
    record.add_argument("--audit", type=Path)
    record.add_argument("--output", type=Path, required=True)
    execute = sub.add_parser("execute")
    execute.add_argument("--candidate-sha", required=True)
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)
    audit = sub.add_parser("audit-staging")
    audit.add_argument("--candidate-sha", required=True)
    audit.add_argument("--repository", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    provider = sub.add_parser("check-providers")
    provider.add_argument("graph", type=Path)
    probe = sub.add_parser("probe")
    probe.add_argument("--candidate-sha", required=True)
    probe.add_argument("--report", action="append", required=True)
    probe.add_argument("--output", type=Path, required=True)
    probe.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == "matrix":
        print(json.dumps(expand(matrix()), indent=2))
        return 0
    if args.action == "check-providers":
        try:
            check_providers(args.graph.read_text())
        except ValueError as error:
            print(error, file=sys.stderr)
            return 1
        print("one org.dyn4j provider")
        return 0
    checkout_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if args.candidate_sha != checkout_sha:
        parser.error(f"candidate SHA differs from checkout {checkout_sha}")
    if args.action == "probe":
        if not SHA40.fullmatch(args.candidate_sha):
            parser.error("candidate SHA must be a full commit hash")
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if not command:
            parser.error("probe needs a command")
        result = run_probe(command, args.report, args.candidate_sha, args.output)
        print(json.dumps(result))
        return 0 if result["status"] == "PASSED" else 1
    if args.action == "audit-staging":
        result = audit_staging(args.repository, args.candidate_sha)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        return 0 if result["status"] == "PASSED" else 1
    if not SHA40.fullmatch(args.candidate_sha):
        parser.error("candidate SHA must be a full commit hash")
    if args.action == "execute":
        plan = json.loads(args.plan.read_text())
        valid_ids = {case["id"] for case in expand(matrix())}
        unknown = set(plan) - valid_ids
        if unknown:
            parser.error("unknown lane: " + ", ".join(sorted(unknown)))
        evidence = execute_plan(plan, args.candidate_sha, args.output)
        return 0 if evidence else 1
    evidence = json.loads(args.evidence.read_text()) if args.evidence else {}
    if evidence and not args.audit:
        parser.error("staged audit is required when lane evidence is supplied")
    audit_data = json.loads(args.audit.read_text()) if args.audit else None
    if audit_data and audit_data.get("candidate_sha") != args.candidate_sha:
        parser.error("audit candidate SHA differs from report")
    artifact_hashes = {item["sha256"] for item in audit_data["artifacts"]} if audit_data else None
    cases = expand(matrix())
    results = [evaluate(case, evidence.get(case["id"]), args.candidate_sha, artifact_hashes) for case in cases]
    report = {"candidate_sha": args.candidate_sha, "total": len(results),
              "counts": {status: sum(item["status"] == status for item in results)
                         for status in ("PASSED", "FAILED", "UNAVAILABLE", "NOT_RUN")},
              "lanes": results}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["counts"]))
    return 0 if report["counts"]["PASSED"] == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
