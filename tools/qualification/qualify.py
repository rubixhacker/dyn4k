#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import uuid
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


def target_publication_name(module, target):
    suffix = target.lower().replace("wasmjs", "wasm-js").replace("wasmwasi", "wasm-wasi")
    return f"{module}-{suffix}"


def check_providers(graph):
    if re.search(r"(?:^|\W)org\.dyn4j:dyn4j(?::|\W)", graph) and re.search(
        r"(?:^|\W)io\.github\.rubixhacker:dyn4k-core(?:-jvm)?(?::|\W)", graph
    ):
        raise ValueError("duplicate org.dyn4j provider: exclude org.dyn4j:dyn4j from the consumer dependency graph")


def target_binary_path(module, target):
    publication = target_publication_name(module, target)
    extension = ".aar" if target == "android" else ".jar" if target in (
        "jvm", "js", "wasmJs", "wasmWasi") else ".klib"
    return f'{GROUP.replace(".", "/")}/{publication}/{VERSION}/{publication}-{VERSION}{extension}'


def full_suite_cases(suite_manifest):
    if not isinstance(suite_manifest, dict) or suite_manifest.get("kind") != "complete-port":
        raise ValueError("frozen complete suite manifest is unavailable")
    if suite_manifest.get("schema") != 1 or not suite_manifest.get("id"):
        raise ValueError("complete suite manifest identity is invalid")
    cases = suite_manifest.get("cases")
    areas = {"geometry", "collision", "dynamics", "joints", "compatibility"}
    if not isinstance(cases, list) or not cases:
        raise ValueError("complete suite manifest has no cases")
    declared_areas = suite_manifest.get("areas")
    if not isinstance(declared_areas, list) or not all(isinstance(area, str) for area in declared_areas) or set(declared_areas) != areas:
        raise ValueError("complete suite manifest omits a required area")
    identities = []
    covered = set()
    for item in cases:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise ValueError("complete suite case identity is invalid")
        if item.get("area") not in areas:
            raise ValueError("complete suite case area is invalid")
        identities.append(item["id"])
        covered.add(item["area"])
    if len(set(identities)) != len(identities) or covered != areas:
        raise ValueError("complete suite cases are duplicate or incomplete")
    return identities


def evaluate(case, evidence, candidate_sha=None, candidate_manifest=None,
             suite_manifest=None, artifact_audit=None):
    result = {"id": case["id"], "status": "NOT_RUN"}
    if evidence is None:
        result["reason"] = "no evidence supplied"
        return result
    if not isinstance(evidence, dict):
        return {**result, "status": "FAILED", "reason": "evidence must be an object"}
    if evidence.get("unavailable_reason"):
        result.update(status="UNAVAILABLE", reason=evidence["unavailable_reason"])
        return result
    required = ("candidate_sha", "runtime_identity", "runtime_version", "expected",
                "executed", "failures", "skipped", "consumer", "suite_id",
                "target", "runtime", "version", "configuration", "case_results",
                "artifact_hashes", "invocation_id", "exit_code", "command",
                "candidate_manifest_sha256", "suite_manifest_sha256", "audit_manifest_sha256")
    missing = [name for name in required if name not in evidence]
    problems = [f"missing {name}" for name in missing]
    if not finite_json(evidence):
        problems.append("non-finite observation is invalid")
    if not SHA40.fullmatch(str(evidence.get("candidate_sha", ""))):
        problems.append("candidate SHA must be a full commit hash")
    if candidate_sha and evidence.get("candidate_sha") != candidate_sha:
        problems.append("candidate SHA differs from report")
    for key in ("target", "runtime", "version", "configuration"):
        if evidence.get(key) != case[key]:
            problems.append(f"{key} differs from lane")
    if not re.fullmatch(r"[0-9a-f]{32}", str(evidence.get("invocation_id", ""))):
        problems.append("fresh execution invocation ID is missing")
    if evidence.get("exit_code") != 0 or not isinstance(evidence.get("command"), list):
        problems.append("successful executable command is missing")
    try:
        cases = full_suite_cases(suite_manifest)
    except ValueError as error:
        problems.append(str(error))
        cases = []
    if not isinstance(candidate_manifest, dict) or not isinstance(artifact_audit, dict):
        problems.append("candidate manifest and staged artifact audit are required")
        lane = None
    else:
        if candidate_manifest.get("schema") != 1:
            problems.append("candidate manifest schema is invalid")
        if candidate_manifest.get("candidate_sha") != candidate_sha:
            problems.append("candidate manifest SHA differs from report")
        if artifact_audit.get("candidate_sha") != candidate_sha or artifact_audit.get("status") != "PASSED":
            problems.append("staged artifact audit did not pass for this candidate")
        if suite_manifest and candidate_manifest.get("suite_manifest_sha256") != manifest_digest(suite_manifest):
            problems.append("candidate manifest does not bind frozen suite")
        if candidate_manifest.get("audit_manifest_sha256") != manifest_digest(artifact_audit):
            problems.append("candidate manifest does not bind staged audit")
        for name, source in (("candidate_manifest_sha256", candidate_manifest),
                             ("audit_manifest_sha256", artifact_audit)):
            if evidence.get(name) != manifest_digest(source):
                problems.append(f"{name} differs from frozen candidate evidence")
        if suite_manifest and evidence.get("suite_manifest_sha256") != manifest_digest(suite_manifest):
            problems.append("suite manifest SHA-256 differs from frozen suite")
        lanes = candidate_manifest.get("lanes")
        lane = lanes.get(case["id"]) if isinstance(lanes, dict) else None
        if not isinstance(lane, dict):
            problems.append("selected runtime lane is absent from candidate manifest")
    if lane:
        for key in ("runtime_identity", "runtime_version", "configuration"):
            if not isinstance(lane.get(key), str) or not lane[key] or evidence.get(key) != lane[key]:
                problems.append(f"{key} differs from selected candidate runtime")
        if suite_manifest and (lane.get("suite_id") != suite_manifest.get("id")
                               or evidence.get("suite_id") != suite_manifest.get("id")):
            problems.append("complete suite identity differs from frozen manifest")
        artifacts = artifact_audit.get("artifacts")
        audited = target_binary_hashes(artifacts).get(case["target"], {}) if isinstance(artifacts, list) else {}
        bound_hashes = lane.get("artifact_hashes")
        if not isinstance(bound_hashes, dict) or set(bound_hashes) != set(MODULES):
            problems.append("both target binary hashes are required")
        else:
            for module in MODULES:
                expected_hash = bound_hashes[module]
                if (not SHA64.fullmatch(str(expected_hash)) or audited.get(module) != expected_hash
                        or not isinstance(evidence.get("artifact_hashes"), dict)
                        or evidence["artifact_hashes"].get(module) != expected_hash):
                    problems.append(f"{module} binary hash differs from target audit")
    observations = evidence.get("case_results")
    if not isinstance(observations, list):
        problems.append("complete case results are missing")
    else:
        identities = [item.get("id") for item in observations if isinstance(item, dict)]
        if (len(identities) != len(observations) or not all(isinstance(identity, str) for identity in identities)
                or len(set(identity for identity in identities if isinstance(identity, str))) != len(identities)
                or set(identity for identity in identities if isinstance(identity, str)) != set(cases)):
            problems.append("complete case identities are missing, duplicate, or unexpected")
        if any(not isinstance(item, dict) or item.get("status") != "PASSED"
               for item in observations):
            problems.append("a complete suite case did not pass")
    for key in ("expected", "executed", "failures", "skipped"):
        if type(evidence.get(key)) is not int or evidence[key] < 0:
            problems.append(f"{key} must be a nonnegative integer")
    if all(type(evidence.get(key)) is int for key in ("expected", "executed", "failures", "skipped")):
        if not cases or evidence["expected"] != len(cases) or evidence["executed"] != len(cases):
            problems.append("suite counts differ from frozen expected cases")
        if evidence["failures"] or evidence["skipped"]:
            problems.append("failed or skipped tests")
    if evidence.get("consumer") != "PASSED":
        problems.append("staged external consumer did not pass")
    result.update(status="FAILED" if problems else "PASSED",
                  reason="; ".join(problems) if problems else "all required evidence present")
    return result


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def manifest_digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_json_strict(path):
    return json.loads(path.read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def finite_json(value):
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(finite_json(item) for item in value.values())
    if isinstance(value, list):
        return all(finite_json(item) for item in value)
    return True


def require_clean_checkout(repository, candidate_sha):
    head = subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
    if head != candidate_sha:
        raise ValueError(f"candidate SHA differs from checkout {head}")
    tracked = subprocess.check_output(
        ["git", "-C", str(repository), "status", "--porcelain=v1", "--untracked-files=no"],
        text=True)
    if tracked.strip():
        raise ValueError("dirty tracked checkout invalidates candidate evidence: " + tracked.strip())
    untracked = subprocess.check_output(
        ["git", "-C", str(repository), "ls-files", "--others", "-z"])
    generated_directories = {b"build", b".gradle", b".kotlin", b"__pycache__"}
    generated_files = {b"kotlin-js-store/yarn.lock",
                       b"consumers/qualification/portable/kotlin-js-store/yarn.lock"}
    relevant = [path for path in untracked.split(b"\0") if path
                and path not in generated_files
                and not generated_directories.intersection(path.split(b"/"))]
    if relevant:
        names = ", ".join(os.fsdecode(path) for path in relevant[:5])
        raise ValueError(f"untracked checkout inputs invalidate candidate evidence: {names}")


def audit_staging(root, candidate_sha):
    errors, artifacts = [], []
    if not SHA40.fullmatch(candidate_sha):
        raise ValueError("candidate SHA must be a full commit hash")
    for module in MODULES:
        expected = {target_publication_name(module, target)
                    for target in {row["target"] for row in matrix()}}
        root_metadata = root / GROUP.replace(".", "/") / module / VERSION / f"{module}-{VERSION}.module"
        if root_metadata.is_file():
            root_data = json.loads(root_metadata.read_text())
            published = {item.get("available-at", {}).get("module")
                         for item in root_data.get("variants", [])}
            published.discard(None)
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


def verify_audit_against_staging(audit_data, repository):
    if not isinstance(audit_data, dict) or not SHA40.fullmatch(str(audit_data.get("candidate_sha", ""))):
        raise ValueError("staged audit candidate identity is invalid")
    staged = audit_staging(repository / "build/staging-repository", audit_data["candidate_sha"])
    observed_files = {item["path"]: item["sha256"] for item in staged["artifacts"]}
    recorded = audit_data.get("artifacts")
    if not isinstance(recorded, list) or any(not isinstance(item, dict) for item in recorded):
        raise ValueError("staged audit artifact list is invalid")
    recorded_files = {item.get("path"): item.get("sha256") for item in recorded}
    if (len(recorded_files) != len(recorded) or recorded_files != observed_files
            or audit_data.get("status") != staged["status"]
            or sorted(audit_data.get("errors", [])) != sorted(staged["errors"])):
        raise ValueError("staged audit differs from current staged files")


def target_binary_hashes(artifacts):
    audited = {item.get("path"): item.get("sha256") for item in artifacts
               if isinstance(item, dict)}
    return {row["target"]: {
        module: audited.get(target_binary_path(module, row["target"])) for module in MODULES}
        for row in matrix()}


def expected_probe_cases(manifest, group):
    if "cases" in group:
        cases = group["cases"]
    else:
        names = manifest.get("case_names", [])
        cases = [{"classname": group.get("classname"),
                  "name": name + group.get("name_suffix", "")} for name in names]
        additional_names = group.get("additional_case_names", [])
        if not isinstance(additional_names, list):
            raise ValueError("additional probe case names must be a list")
        cases.extend({"classname": group.get("additional_classname"),
                      "name": name + group.get("name_suffix", "")}
                     for name in additional_names)
    if not isinstance(cases, list):
        raise ValueError("probe cases must be a list")
    identities = []
    for case in cases:
        if (not isinstance(case, dict) or not isinstance(case.get("classname"), str)
                or not isinstance(case.get("name"), str) or not case["classname"] or not case["name"]):
            raise ValueError("probe case identity is invalid")
        identities.append((case["classname"], case["name"]))
    if len(set(identities)) != len(identities):
        raise ValueError("probe manifest has duplicate case identities")
    return identities


def run_probe(command, report_paths, candidate_sha, output, manifest=None):
    problems = []
    groups = manifest.get("groups") if isinstance(manifest, dict) else None
    if not isinstance(groups, list) or not groups or manifest.get("kind") != "foundation-probe":
        problems.append("frozen foundation probe manifest is required")
        groups = []
    patterns = [group.get("report_pattern") for group in groups if isinstance(group, dict)]
    if len(patterns) != len(groups) or len(set(patterns)) != len(patterns):
        problems.append("probe manifest has duplicate or invalid report groups")
    if sorted(report_paths) != sorted(patterns):
        problems.append("requested report groups differ from frozen manifest")
    expected = executed = failures = skipped = 0
    expected_by_group = {}
    for group in groups:
        try:
            identities = expected_probe_cases(manifest, group)
            expected_by_group[group["id"]] = identities
            expected += len(identities)
        except (KeyError, TypeError, ValueError) as error:
            problems.append(str(error))
    if not expected:
        problems.append("probe manifest has no required cases")
    completed = None
    if not problems:
        for pattern in patterns:
            for path in Path().glob(pattern):
                path.unlink()
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode:
            problems.append(f"probe command exited {completed.returncode}")
        for group in groups:
            expected_cases = expected_by_group[group["id"]]
            paths = list(Path().glob(group["report_pattern"]))
            if expected_cases and not paths:
                problems.append(f'missing report group {group["id"]}')
            if not expected_cases and paths:
                problems.append(f'unexpected report for empty group {group["id"]}')
            observed_cases = []
            for path in paths:
                try:
                    root = ET.parse(path).getroot()
                    if root.tag != "testsuite":
                        raise ValueError("root element is not testsuite")
                    suite_time = float(root.get("time", "0"))
                    if not math.isfinite(suite_time) or suite_time < 0:
                        raise ValueError("suite time is invalid")
                    testcases = list(root.iter("testcase"))
                    reported = {key: int(root.get(key, "-1")) for key in
                                ("tests", "failures", "errors", "skipped")}
                    if any(value < 0 for value in reported.values()):
                        raise ValueError("suite counts are missing or negative")
                    actual_failures = sum(bool(testcase.find("failure") is not None) for testcase in testcases)
                    actual_errors = sum(bool(testcase.find("error") is not None) for testcase in testcases)
                    actual_skips = sum(bool(testcase.find("skipped") is not None) for testcase in testcases)
                    if (reported["tests"] != len(testcases) or reported["failures"] != actual_failures
                            or reported["errors"] != actual_errors or reported["skipped"] != actual_skips):
                        raise ValueError("suite counts differ from case elements")
                    for testcase in testcases:
                        duration = float(testcase.get("time", "nan"))
                        if not math.isfinite(duration) or duration < 0:
                            raise ValueError("case time is invalid")
                        identity = (testcase.get("classname"), testcase.get("name"))
                        if not all(identity):
                            raise ValueError("case identity is missing")
                        observed_cases.append(identity)
                    executed += len(testcases) - actual_skips
                    failures += actual_failures + actual_errors
                    skipped += actual_skips
                except (ET.ParseError, OSError, TypeError, ValueError) as error:
                    problems.append(f"invalid report {path}: {error}")
            if len(observed_cases) != len(set(observed_cases)):
                problems.append(f'duplicate cases in group {group["id"]}')
            if set(observed_cases) != set(expected_cases):
                problems.append(f'partial or unexpected cases in group {group["id"]}')
    if failures or skipped:
        problems.append("probe has failed or skipped cases")
    if executed != expected:
        problems.append("probe executed count differs from frozen expected count")
    result = {"candidate_sha": candidate_sha, "command": command,
              "exit_code": completed.returncode if completed else None,
              "expected": expected, "executed": executed, "failures": failures,
              "skipped": skipped, "manifest_sha256": manifest_digest(manifest) if manifest else None,
              "status": "PROBE_FAILED" if problems else "PROBE_PASSED",
              "reason": "; ".join(problems) if problems else "frozen foundation cases executed",
              "scope": "foundation probe only; not a complete lane"}
    output.write_text(json.dumps(result, indent=2) + "\n")
    if completed:
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
        result_name = specification.get("result_file")
        if not isinstance(result_name, str) or not result_name:
            evidence[case["id"]] = {"error": "result file path is missing"}
            continue
        result_file = Path(result_name)
        if result_file.is_dir():
            evidence[case["id"]] = {"error": "result file path is a directory"}
            continue
        invocation_id = uuid.uuid4().hex
        previous = None
        if result_file.exists() or result_file.is_symlink():
            previous = result_file.with_name(result_file.name + ".previous-" + invocation_id)
            result_file.rename(previous)
        environment = dict(os.environ, DYN4K_QUALIFICATION_INVOCATION=invocation_id)
        result = subprocess.run(command, text=True, capture_output=True, check=False,
                                env=environment)
        if result.returncode or not result_file.is_file() or result_file.is_symlink():
            evidence[case["id"]] = {"error": "command failed or result file missing",
                                    "exit_code": result.returncode,
                                    "stderr": result.stderr[-4000:],
                                    "previous_result": str(previous) if previous else None}
            continue
        try:
            observed = json.loads(result_file.read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (ValueError, OSError) as error:
            evidence[case["id"]] = {"error": f"invalid result JSON: {error}",
                                    "exit_code": result.returncode}
            continue
        if not isinstance(observed, dict) or observed.get("invocation_id") != invocation_id:
            evidence[case["id"]] = {"error": "result invocation ID differs from execution",
                                    "exit_code": result.returncode}
            continue
        observed["command"] = command
        observed["exit_code"] = result.returncode
        evidence[case["id"]] = observed
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


def execution_succeeded(evidence):
    return bool(evidence) and all(
        "error" not in result and "unavailable_reason" not in result
        and result.get("exit_code") == 0
        and re.fullmatch(r"[0-9a-f]{32}", str(result.get("invocation_id", ""))) is not None
        for result in evidence.values()
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("matrix")
    record = sub.add_parser("record")
    record.add_argument("--candidate-sha", required=True)
    record.add_argument("--evidence", type=Path)
    record.add_argument("--audit", type=Path)
    record.add_argument("--candidate-manifest", type=Path)
    record.add_argument("--availability", type=Path)
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
    probe.add_argument("--manifest", type=Path, required=True)
    probe.add_argument("--group", action="append", required=True)
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
    repository = Path(subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True).strip())
    try:
        require_clean_checkout(repository, args.candidate_sha)
    except (subprocess.CalledProcessError, ValueError) as error:
        parser.error(str(error))
    if args.action == "probe":
        if not SHA40.fullmatch(args.candidate_sha):
            parser.error("candidate SHA must be a full commit hash")
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if not command:
            parser.error("probe needs a command")
        frozen_path = repository / "tools/qualification/foundation-probes.json"
        if args.manifest.resolve() != frozen_path.resolve():
            parser.error("probe manifest must be the tracked frozen foundation manifest")
        frozen = load_json_strict(frozen_path)
        selected = [group for group in frozen.get("groups", []) if group.get("id") in args.group]
        if len(selected) != len(args.group) or len(set(args.group)) != len(args.group):
            parser.error("unknown or duplicate frozen probe group")
        frozen["groups"] = selected
        result = run_probe(command, args.report, args.candidate_sha, args.output, frozen)
        print(json.dumps(result))
        return 0 if result["status"] == "PROBE_PASSED" else 1
    if args.action == "audit-staging":
        result = audit_staging(args.repository, args.candidate_sha)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        return 0 if result["status"] == "PASSED" else 1
    if not SHA40.fullmatch(args.candidate_sha):
        parser.error("candidate SHA must be a full commit hash")
    if args.action == "execute":
        plan = load_json_strict(args.plan)
        valid_ids = {case["id"] for case in expand(matrix())}
        unknown = set(plan) - valid_ids
        if unknown:
            parser.error("unknown lane: " + ", ".join(sorted(unknown)))
        evidence = execute_plan(plan, args.candidate_sha, args.output)
        return 0 if execution_succeeded(evidence) else 1
    evidence = load_json_strict(args.evidence) if args.evidence else {}
    audit_data = load_json_strict(args.audit) if args.audit else None
    if audit_data and audit_data.get("candidate_sha") != args.candidate_sha:
        parser.error("audit candidate SHA differs from report")
    if audit_data:
        try:
            verify_audit_against_staging(audit_data, repository)
        except ValueError as error:
            parser.error(str(error))
    candidate_manifest = load_json_strict(args.candidate_manifest) if args.candidate_manifest else None
    full_manifest_path = repository / "tools/qualification/full-suite-manifest.json"
    tracked_manifest = subprocess.run(
        ["git", "-C", str(repository), "ls-files", "--error-unmatch", "--",
         str(full_manifest_path.relative_to(repository))],
        capture_output=True, check=False).returncode == 0
    suite_manifest = load_json_strict(full_manifest_path) if tracked_manifest and full_manifest_path.is_file() else None
    cases = expand(matrix())
    availability = load_json_strict(args.availability) if args.availability else {}
    valid_availability = {row["target"] for row in matrix()} | {
        f'{row["target"]}:{row["runtime"]}' for row in matrix()} | {
        f'{case["target"]}:{case["runtime"]}:{case["version"]}' for case in cases} | {
        case["id"] for case in cases}
    unknown = set(availability) - valid_availability
    if unknown:
        parser.error("unknown availability selector: " + ", ".join(sorted(unknown)))
    if any(not isinstance(reason, str) or not reason.strip() for reason in availability.values()):
        parser.error("every unavailable reason must be nonempty text")
    for case in cases:
        if case["id"] not in evidence:
            reason = availability.get(case["id"],
                availability.get(f'{case["target"]}:{case["runtime"]}:{case["version"]}',
                    availability.get(f'{case["target"]}:{case["runtime"]}',
                        availability.get(case["target"]))))
            if reason:
                evidence[case["id"]] = {"unavailable_reason": reason}
    results = [evaluate(case, evidence.get(case["id"]), args.candidate_sha,
                        candidate_manifest, suite_manifest, audit_data)
               for case in cases]
    report = {"candidate_sha": args.candidate_sha, "total": len(results),
              "counts": {status: sum(item["status"] == status for item in results)
                         for status in ("PASSED", "FAILED", "UNAVAILABLE", "NOT_RUN")},
              "lanes": results}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["counts"]))
    return 0 if report["counts"]["PASSED"] == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
