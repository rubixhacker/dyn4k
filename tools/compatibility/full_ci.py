from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from exception_ci import seal_exception, validate_exception_report
from world_ci import seal_world


ROOT = Path(__file__).resolve().parents[2]
VERSION = "0.1.0-alpha.1"
BASELINE_SHA = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
STDLIB_SHA = "2226de463d309d4a5500a481320b3dea515a6981dcae1def531fbc158884e25f"
ANNOTATIONS_SHA = "ace2a10dc8e2d5fd34925ecac03e4988b2c0f851650c94b8cef49ba1bd111478"
ADVERSE_AUDIT_SHA = "aaed70cf906eb2e1944e56b80713fe6398a5339d55f4977128b54dd70cba607a"
FIXTURE_SHA = {
    "b668a59b6b50e6d5be1ca4828d2eaa179c6f9b3623a839be3e8c2c063d9ce6a4",
    "bb3f75b5f938b5e6da6e2444f5626606daa2223d29ba5c9ba2405660e50097ed",
    "b37d307b808a55961bad6d6cfd5606ec7d27b2ba33567e8d44621d0942530ff0",
}
FIXTURES = sorted((ROOT / "tools/baseline/fixtures").glob("*.java"))
PROJECTION = ROOT / "tools/compatibility/fixtures/java_source_projection"
PARAMETER_SUITES = {
    "org.dyn4j.collision.broadphase.CollisionBodyBroadphaseTest": (
        25, ("Sap", "Sap", "DynamicAABBTree", "DynamicAABBTree", "BruteForceBroadphase")),
    "org.dyn4j.collision.broadphase.CollisionItemBroadphaseTest": (
        29, ("CollisionItemBroadphaseDetectorAdapter",) * 5),
}
PARAMETER_PATTERN = re.compile(r"([^\[]+)\[([^@\]]+)@([0-9a-fA-F]+)\]")
LANES = {f"{provider}-javac{compiler}-java{runtime}"
         for provider in ("baseline", "candidate", "android") for compiler in (8, 21)
         for runtime in (8, 21)}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_corpus(report: dict) -> None:
    for key, marker, expected in (("actual_executed_cases", "ACTUAL_TESTS", 2385),
                                  ("failures", "FAILURES", 0), ("ignored", "IGNORED", 0)):
        if type(report.get(key)) is not int or report[key] != expected:
            raise ValueError(f"{key} must equal {expected}")
        if report.get("output", "").splitlines().count(f"{marker}={expected}") != 1:
            raise ValueError(f"missing or conflicting {marker} marker")
    if report.get("process_exit_code") != 0:
        raise ValueError("JUnit process failed")


def parameter_groups(identities: list[tuple[str, str]], expected: int) -> dict:
    groups = {}
    for class_name, (method_count, type_names) in PARAMETER_SUITES.items():
        rows = [name for owner, name in identities if owner == class_name]
        if not rows and expected != 2385:
            continue
        seen = {}
        for name in rows:
            match = PARAMETER_PATTERN.fullmatch(name)
            if match is None:
                raise ValueError(f"{class_name} parameter group name is malformed")
            method, parameter_type, address = match.groups()
            key = (parameter_type, address)
            seen.setdefault(key, []).append(method)
        if len(seen) != 5 or len(rows) != method_count * 5:
            raise ValueError(f"{class_name} parameter group count differs")
        actual_types = tuple(key[0] for key in seen)
        if actual_types != tuple(f"org.dyn4j.collision.broadphase.{name}" for name in type_names):
            raise ValueError(f"{class_name} parameter group types differ")
        expected_methods = set(next(iter(seen.values())))
        if len(expected_methods) != method_count or any(len(methods) != method_count or
                                                        set(methods) != expected_methods
                                                        for methods in seen.values()):
            raise ValueError(f"{class_name} parameter group methods differ")
        groups[class_name] = {key: index for index, key in enumerate(seen)}
    return groups


def validate_xml(path: Path, expected: int = 2385) -> list[tuple[str, str]]:
    suite = ET.parse(path).getroot()
    if suite.tag != "testsuite" or any(suite.get(key) != str(value) for key, value in
                                       (("tests", expected), ("failures", 0),
                                        ("errors", 0), ("skipped", 0))):
        raise ValueError("JUnit XML count or status differs")
    cases = suite.findall("testcase")
    if len(cases) != expected or any(not case.get("classname") or not case.get("name")
                                     or len(case) for case in cases):
        raise ValueError("JUnit XML lacks complete passing case identities")
    identities = [(case.get("classname"), case.get("name")) for case in cases]
    if len(set(identities)) != expected:
        raise ValueError("JUnit XML has duplicate or missing case identities")
    parameter_groups(identities, expected)
    return identities


def normalized_cases(identities: list[tuple[str, str]]) -> Counter:
    groups = parameter_groups(list(identities), len(identities)) if len(identities) == 2385 else {}
    normalized = []
    for class_name, name in identities:
        if class_name in groups:
            method, parameter_type, address = PARAMETER_PATTERN.fullmatch(name).groups()
            index = groups[class_name][(parameter_type, address)]
            name = f"{method}[{parameter_type}#{index}]"
        normalized.append((class_name, name))
    return Counter(normalized)


def seal_lanes(output: Path, evidence: dict, candidate_sha: str) -> dict[str, str]:
    if evidence.get("status") != "PASSED" or evidence.get("candidate_sha") != candidate_sha:
        raise ValueError("full compatibility result is not passing at candidate SHA")
    corpus = evidence.get("corpus")
    if not isinstance(corpus, dict) or {key for key in corpus if key in LANES} != LANES:
        raise ValueError("corpus lane inventory is incomplete")
    expected_files = {f"corpus-{lane}.{suffix}" for lane in LANES for suffix in ("xml", "json")}
    actual_files = {path.name for suffix in ("xml", "json")
                    for path in output.glob(f"corpus-*.{suffix}")}
    if actual_files != expected_files:
        raise ValueError("corpus XML/JSON file set differs")
    hashes = {}
    for lane in sorted(LANES):
        row = corpus[lane]
        if row.get("status") != "PASSED" or row.get("cases") != 2385:
            raise ValueError(f"{lane} did not pass all 2385 cases")
        for suffix, field in (("xml", "xml_sha256"), ("json", "report_sha256")):
            name = f"corpus-{lane}.{suffix}"
            path = output / name
            if row.get("xml" if suffix == "xml" else "report") != name or not path.is_file() or path.is_symlink():
                raise ValueError(f"{name} is missing from passing evidence")
            actual = digest(path)
            if row.get(field) != actual:
                raise ValueError(f"{name} hash differs from passing evidence")
            hashes[name] = actual
    return hashes


def validate_projection(report: dict, work: Path, fixture: Path,
                        providers: dict[str, str], audit_sha: str) -> None:
    if report.get("audit_sha256") != audit_sha or report.get("providers") != providers:
        raise ValueError("source projection input or provider hashes differ")
    expected_keys = {(provider, compiler, runtime) for provider in providers
                     for compiler in ("jdk8", "jdk21") for runtime in ("jdk8", "jdk21")}
    observations = report.get("observations")
    if not isinstance(observations, list) or len(observations) != 12:
        raise ValueError("source projection observation matrix is incomplete")
    observed_keys = set()
    for row in observations:
        if not isinstance(row, dict):
            raise ValueError("source projection observation is malformed")
        key = (row.get("provider"), row.get("compiler"), row.get("runtime"))
        if key in observed_keys or key not in expected_keys or type(row.get("probes")) is not int or row["probes"] != 77:
            raise ValueError("source projection lane or probe count differs")
        observed_keys.add(key)
        log = work / f"run-{'-'.join(key)}.log"
        if not log.is_file() or digest(log) != row.get("run_log_sha256") or log.read_text().strip() != "(1.0, 2.0)\nACTUAL_PROBES=77":
            raise ValueError("source projection runtime log differs")
    if observed_keys != expected_keys:
        raise ValueError("source projection provider/compiler/runtime set differs")
    source_hashes = report.get("source_sha256")
    source_root = work / "sources"
    generated = {str(path.relative_to(source_root)): path for path in source_root.rglob("*.java")}
    fixtures = ("extra/Names.java", "org/dyn4j/geometry/simplify/NodeDispatchProbe.java")
    probes = [name for name in generated if re.fullmatch(r"(?:[^/]+/)+ProjectionProbe(0[1-9]|[1-6][0-9]|7[0-7])\.java", name)]
    if (report.get("source_count") != 80 or len(probes) != 77 or
            {int(re.search(r"Probe(\d+)\.java$", name)[1]) for name in probes} != set(range(1, 78)) or
            set(generated) != set(probes) | {"projection/Suite.java"} or
            not isinstance(source_hashes, dict) or set(source_hashes) != set(generated) | set(fixtures)):
        raise ValueError("source projection source inventory differs")
    for name, path in {**generated, **{name: fixture / name for name in fixtures}}.items():
        if not path.is_file() or digest(path) != source_hashes[name]:
            raise ValueError(f"source projection source hash differs: {name}")


def validate_source_inputs(source: Path, hashes: dict, expected_count: int = 218) -> None:
    if len(hashes) != expected_count:
        raise ValueError("pinned test input inventory is incomplete")
    root = source.resolve()
    for relative, expected in hashes.items():
        path = (source / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file() or digest(path) != expected:
            raise ValueError(f"pinned test source or resource changed: {relative}")


def validate_audit(report: dict, candidate_hash: str) -> None:
    api_types = report.get("compared_api_types")
    if (not isinstance(api_types, list) or len(api_types) != 216
            or any(not isinstance(name, str) or not name for name in api_types)
            or len(set(api_types)) != 216
            or report.get("compared_baseline_declarations") != 3078):
        raise ValueError("required declaration inventory is incomplete")
    if report.get("baseline_sha256") != BASELINE_SHA or report.get("candidate_sha256") != candidate_hash:
        raise ValueError("comparison archive hash differs")
    for key in ("missing_types", "signature_mismatches", "added_member_risks",
                "inventory_errors", "fixture_failures", "fixture_errors"):
        if report.get(key) != []:
            raise ValueError(f"strict comparison has {key}")
    observed = {row.get("source_sha256") for row in report.get("fixture_results", [])}
    if observed != FIXTURE_SHA or len(report["fixture_results"]) != len(FIXTURE_SHA):
        raise ValueError("permanent Java 8 fixtures were omitted or changed")
    if any(row.get("baseline_exit_code") != 0 or row.get("candidate_exit_code") != 0
           for row in report["fixture_results"]):
        raise ValueError("permanent Java 8 fixture compilation failed")


def run(command: list[str], log: Path, *, env: dict | None = None,
        timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True,
                            timeout=timeout, check=False)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(result.stdout + result.stderr)
    return result


def checked_archive(path: Path, label: str) -> str:
    if not path.is_file() or path.is_symlink() or not path.stat().st_size:
        raise ValueError(f"missing or empty {label}: {path}")
    return digest(path)


def fetch(url: str, path: Path, expected: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        urllib.request.urlretrieve(url, path)
    actual = checked_archive(path, url)
    if actual != expected:
        raise ValueError(f"dependency SHA-256 differs: {url}")
    return actual


def version(jdk: Path, executable: str, major: int) -> str:
    binary = jdk / "bin" / executable
    if not binary.is_file():
        raise ValueError(f"missing {executable}: {binary}")
    observed = subprocess.run([str(binary), "-version"], capture_output=True, text=True,
                              check=False)
    value = (observed.stdout + observed.stderr).strip()
    pattern = r"(?:1\.8\.|\b8(?:\.|\b))" if major == 8 else r"\b21(?:\.|\b)"
    if observed.returncode or not re.search(pattern, value):
        raise ValueError(f"expected Java {major} {executable}, got {value}")
    return value.splitlines()[0]


def staged_archives(staging: Path, output: Path) -> tuple[dict[str, Path], dict[str, str]]:
    base = staging / "io/github/rubixhacker"
    jvm = base / "dyn4k-core-jvm" / VERSION / f"dyn4k-core-jvm-{VERSION}.jar"
    aar = base / "dyn4k-core-android" / VERSION / f"dyn4k-core-android-{VERSION}.aar"
    hashes = {"staged_jvm_jar": checked_archive(jvm, "staged JVM JAR"),
              "staged_android_aar": checked_archive(aar, "staged Android AAR")}
    archived = output / "archives"
    archived.mkdir(parents=True, exist_ok=True)
    for archive in (jvm, aar):
        sidecar = archive.with_name(archive.name + ".sha256")
        checked_archive(sidecar, "staged SHA-256 sidecar")
        if sidecar.read_text().strip().lower() != digest(archive):
            raise ValueError(f"staged checksum differs: {archive}")
        shutil.copy2(archive, archived / archive.name)
        shutil.copy2(sidecar, archived / sidecar.name)
        if digest(archived / archive.name) != digest(archive):
            raise ValueError(f"staged archive changed during capture: {archive}")
    with zipfile.ZipFile(archived / aar.name) as opened:
        members = [name for name in opened.namelist() if name == "classes.jar"]
        if len(members) != 1:
            raise ValueError("Android AAR lacks one classes.jar")
        android = output / "android-classes.jar"
        android.write_bytes(opened.read(members[0]))
    hashes["staged_android_classes_jar"] = checked_archive(android, "Android classes.jar")
    return {"jvm": archived / jvm.name, "android": android}, hashes


def junit_report(output: str, exit_code: int) -> dict:
    def field(label: str) -> int | None:
        matches = [line.split("=", 1)[1] for line in output.splitlines()
                   if line.startswith(label + "=")]
        return int(matches[0]) if len(matches) == 1 and matches[0].isdigit() else None

    return {"actual_executed_cases": field("ACTUAL_TESTS"), "failures": field("FAILURES"),
            "ignored": field("IGNORED"), "process_exit_code": exit_code, "output": output}


def corpus_matrix(source: Path, providers: dict[str, Path], deps: list[Path],
                  jdks: dict[int, Path], output: Path, evidence: dict) -> None:
    tests = sorted((source / "src/test/java").rglob("*.java"))
    classes = sorted({".".join(path.relative_to(source / "src/test/java").with_suffix("").parts)
                      for path in tests if "@Test" in path.read_text(errors="replace")
                      or "@RunWith" in path.read_text(errors="replace")})
    if len(tests) != 199 or len(classes) != 190:
        raise ValueError(f"pinned test inventory changed: {len(tests)} files, {len(classes)} classes")
    harness = ROOT / "tools/compatibility/PinnedCorpusReport.java"
    evidence["archives"]["corpus_harness_source"] = checked_archive(harness, "JUnit XML harness")
    argfile = output / "test-sources.args"
    argfile.write_text("\n".join('"' + str(path) + '"' for path in tests) + "\n")
    expected_identities = None
    for provider, archive in providers.items():
        for compiler_major, compiler in jdks.items():
            key = f"{provider}-javac{compiler_major}"
            classes_dir = output / "classes" / key
            classes_dir.mkdir(parents=True, exist_ok=True)
            cp = os.pathsep.join(str(path) for path in
                                 [archive, *([] if provider == "baseline" else deps[:2]), *deps[2:]])
            options = (["-source", "8", "-target", "8"] if compiler_major == 8
                       else ["--release", "8"])
            command = [str(compiler / "bin/javac"), "-encoding", "UTF-8", *options,
                       "-cp", cp, "-d", str(classes_dir), "@" + str(argfile), str(harness)]
            compiled = run(command, output / "logs" / f"compile-{key}.log")
            evidence["corpus"][key] = {"compile_exit_code": compiled.returncode,
                                       "compile_log_sha256": digest(output / "logs" / f"compile-{key}.log")}
            if compiled.returncode:
                evidence["errors"].append(f"{key}: unchanged source did not compile")
                continue
            resources = source / "src/test/resources"
            if resources.exists():
                shutil.copytree(resources, classes_dir, dirs_exist_ok=True)
            for runtime_major, runtime in jdks.items():
                case = f"{key}-java{runtime_major}"
                xml = output / f"corpus-{case}.xml"
                result = run([str(runtime / "bin/java"), "-cp", os.pathsep.join([cp, str(classes_dir)]),
                              "PinnedCorpusReport", str(xml), *classes],
                             output / "logs" / f"run-{case}.log")
                report = junit_report(result.stdout, result.returncode)
                report.update({"provider": provider, "compiler": compiler_major,
                               "runtime": runtime_major, "archive_sha256": digest(archive),
                               "run_log_sha256": digest(output / "logs" / f"run-{case}.log"),
                               "xml_sha256": digest(xml) if xml.is_file() else None})
                (output / f"corpus-{case}.json").write_text(json.dumps(report, indent=2) + "\n")
                try:
                    validate_corpus(report)
                    identities = validate_xml(xml)
                    normalized = normalized_cases(identities)
                    if expected_identities is None:
                        expected_identities = normalized
                    elif normalized != expected_identities:
                        raise ValueError("JUnit case identities differ from pinned baseline run")
                    identity_hash = hashlib.sha256(json.dumps(sorted(
                        (class_name, name, count) for (class_name, name), count in normalized.items()
                    )).encode()).hexdigest()
                    report["case_id_sha256"] = identity_hash
                    (output / f"corpus-{case}.json").write_text(json.dumps(report, indent=2) + "\n")
                    evidence["corpus"][case] = {"status": "PASSED", "report": f"corpus-{case}.json",
                                                "xml": f"corpus-{case}.xml", "xml_sha256": digest(xml),
                                                "report_sha256": digest(output / f"corpus-{case}.json"),
                                                "cases": 2385, "case_id_sha256": identity_hash}
                except (OSError, ValueError, ET.ParseError) as error:
                    evidence["errors"].append(f"{case}: {error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pinned Java corpus and staged archive audits.")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--staging-repository", type=Path, required=True)
    parser.add_argument("--jdk8", type=Path, required=True)
    parser.add_argument("--jdk21", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    evidence = {"candidate_sha": args.candidate_sha, "status": "FAILED", "errors": [],
                "archives": {}, "tools": {}, "baseline": {}, "audits": {},
                "corpus": {}, "source_projection": {}, "exception_serialization": {},
                "world_fixtures": {}}
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if head != args.candidate_sha:
            raise ValueError(f"candidate SHA differs from checkout: {head}")
        jdks = {8: args.jdk8.resolve(), 21: args.jdk21.resolve()}
        for major, jdk in jdks.items():
            evidence["tools"][f"javac{major}"] = version(jdk, "javac", major)
            evidence["tools"][f"java{major}"] = version(jdk, "java", major)
        archives, hashes = staged_archives(args.staging_repository.resolve(), output)
        evidence["archives"].update(hashes)
        deps_dir = output / "deps"
        stdlib = deps_dir / "kotlin-stdlib-2.4.20.jar"
        annotations = deps_dir / "annotations-13.0.jar"
        fetch("https://repo.maven.apache.org/maven2/org/jetbrains/kotlin/kotlin-stdlib/2.4.20/kotlin-stdlib-2.4.20.jar", stdlib,
              STDLIB_SHA)
        fetch("https://repo.maven.apache.org/maven2/org/jetbrains/annotations/13.0/annotations-13.0.jar", annotations,
              ANNOTATIONS_SHA)
        evidence["archives"].update({"kotlin_stdlib": digest(stdlib), "annotations": digest(annotations)})
        baseline_cache = output / "baseline-cache"
        env = {**os.environ, "JAVA_HOME": str(jdks[21]),
               "PATH": str(jdks[21] / "bin") + os.pathsep + os.environ["PATH"]}
        baseline = run([sys.executable, str(ROOT / "tools/baseline/verify.py"),
                        "--cache", str(baseline_cache), "--inventory", str(output / "baseline-inventory.json"),
                        "--summary", str(output / "baseline-run.json")],
                       output / "logs/baseline-verify.log", env=env, timeout=1800)
        evidence["baseline"]["verify_exit_code"] = baseline.returncode
        if baseline.returncode:
            evidence["errors"].append("pinned baseline source, archive, or corpus verification failed")
        else:
            baseline_report = json.loads((output / "baseline-run.json").read_text())
            validate_corpus(baseline_report)
            evidence["baseline"].update({"source_revision": baseline_report["commit"],
                                         "executed_cases": baseline_report["actual_executed_cases"],
                                         "inventory_sha256": digest(output / "baseline-inventory.json"),
                                         "run_sha256": digest(output / "baseline-run.json")})
        binary = baseline_cache / "dyn4j-6.0.0.jar"
        if checked_archive(binary, "pinned baseline JAR") != BASELINE_SHA:
            raise ValueError("pinned baseline JAR hash differs")
        if baseline.returncode:
            raise ValueError("baseline verification must pass before candidate checks")
        source = baseline_cache / "dyn4j-source"
        validate_source_inputs(source, baseline_report["test_input_sha256"])
        junit = baseline_cache / "deps/junit-4.13.1.jar"
        hamcrest = baseline_cache / "deps/hamcrest-core-1.3.jar"
        for path in (junit, hamcrest):
            evidence["archives"][path.name] = checked_archive(path, path.name)
        for name, archive in archives.items():
            result = run([sys.executable, str(ROOT / "tools/baseline/verify.py"), "compare",
                          "--baseline-jar", str(binary), "--candidate", str(archive),
                          "--require-fixture", *(part for fixture in FIXTURES for part in
                                                 ("--fixture", str(fixture))),
                          "--dependency-jar", str(stdlib), "--dependency-jar", str(annotations)],
                         output / "logs" / f"audit-{name}.log", env=env, timeout=1800)
            try:
                audit = json.loads(result.stdout)
                (output / f"audit-{name}.json").write_text(json.dumps(audit, indent=2) + "\n")
                validate_audit(audit, digest(archive))
                if result.returncode:
                    raise ValueError("strict compare process failed")
                evidence["audits"][name] = {"status": "PASSED", "report": f"audit-{name}.json",
                                             "report_sha256": digest(output / f"audit-{name}.json")}
            except ValueError as error:
                evidence["audits"][name] = {"status": "FAILED", "exit_code": result.returncode}
                evidence["errors"].append(f"{name} strict audit: {error}")
        adverse_audit = PROJECTION / "frozen-adverse-audit.json"
        if checked_archive(adverse_audit, "frozen adverse audit") != ADVERSE_AUDIT_SHA:
            raise ValueError("frozen adverse audit hash differs")
        projection = run([sys.executable, str(PROJECTION / "probe_added_members.py"),
                          "--audit", str(adverse_audit),
                          "--baseline", str(binary), "--candidate", f"jvm={archives['jvm']}",
                          "--candidate", f"android={archives['android']}",
                          "--stdlib", str(stdlib), "--annotations", str(annotations),
                          "--jdk8", str(jdks[8]), "--jdk21", str(jdks[21]),
                          "--work", str(output / "projection")],
                         output / "logs/source-projection.log", timeout=1800)
        evidence["source_projection"]["exit_code"] = projection.returncode
        if projection.returncode:
            evidence["errors"].append("adverse Java source projection or node dispatch failed")
        else:
            try:
                projection_report = json.loads((output / "projection/result.json").read_text())
                validate_projection(projection_report, output / "projection", PROJECTION,
                                    {"baseline": BASELINE_SHA,
                                     "jvm": hashes["staged_jvm_jar"],
                                     "android": hashes["staged_android_classes_jar"]},
                                    ADVERSE_AUDIT_SHA)
                evidence["source_projection"].update({"report_sha256": digest(output / "projection/result.json"),
                                                      "observations": len(projection_report["observations"])})
            except (OSError, ValueError, KeyError, TypeError) as error:
                evidence["errors"].append(f"source projection report: {error}")
        exception = run([sys.executable, str(ROOT / "tools/compatibility/exception_ci.py"),
                         "--baseline", str(binary), "--jvm", str(archives["jvm"]),
                         "--android", str(archives["android"]),
                         "--java8", str(jdks[8]), "--java21", str(jdks[21]),
                         "--stdlib", str(stdlib),
                         "--output", str(output / "exception-serialization")],
                        output / "logs/exception-serialization.log", timeout=3600)
        evidence["exception_serialization"]["exit_code"] = exception.returncode
        exception_report = output / "exception-serialization/result.json"
        if exception_report.is_file():
            evidence["exception_serialization"]["report_sha256"] = digest(exception_report)
        if exception.returncode:
            evidence["errors"].append("exception serialization fixture or adverse controls failed")
        else:
            try:
                checked = json.loads(exception_report.read_text())
                if (checked.get("status") != "PASSED" or checked.get("providers") != {
                        "baseline": BASELINE_SHA, "jvm": hashes["staged_jvm_jar"],
                        "android": hashes["staged_android_classes_jar"]} or
                        checked.get("fixture", {}).get("processes") != 636 or
                        checked.get("fixture", {}).get("identities") != 27 or
                        checked.get("public_api", {}).get("observations") != 18 or
                        set(checked.get("adverse", {})) != {"uid", "payload"}):
                    raise ValueError("exception serialization result is incomplete")
            except (OSError, ValueError, KeyError, TypeError) as error:
                evidence["errors"].append(f"exception serialization report: {error}")
        world_output = output / "logs/world-fixtures"
        world = run([sys.executable, str(ROOT / "tools/compatibility/world_ci.py"),
                     "--candidate-sha", args.candidate_sha,
                     "--baseline", str(binary), "--jvm", str(archives["jvm"]),
                     "--android", str(archives["android"]),
                     "--java8", str(jdks[8]), "--java21", str(jdks[21]),
                     "--stdlib", str(stdlib), "--output", str(world_output)],
                    output / "logs/world-fixtures.log", timeout=3600)
        evidence["world_fixtures"]["exit_code"] = world.returncode
        world_report = world_output / "result.json"
        if world_report.is_file():
            evidence["world_fixtures"]["report_sha256"] = digest(world_report)
        if world.returncode:
            evidence["errors"].append("frozen World Java fixture or adverse control failed")
        else:
            try:
                sealed_world = seal_world(world_output, args.candidate_sha,
                                          {"baseline": BASELINE_SHA,
                                           "jvm": hashes["staged_jvm_jar"],
                                           "android": hashes["staged_android_classes_jar"]},
                                          evidence["world_fixtures"]["report_sha256"])
                evidence["world_fixtures"].update({"executions": 138, "modes": 23,
                                                    "sources": 12, "files": len(sealed_world)})
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                evidence["errors"].append(f"World fixture report: {error}")
        corpus_matrix(source, {"baseline": binary, "candidate": archives["jvm"],
                               "android": archives["android"]},
                      [stdlib, annotations, junit, hamcrest], jdks, output, evidence)
        validate_source_inputs(source, baseline_report["test_input_sha256"])
        source_check = run([sys.executable, str(ROOT / "tools/baseline/verify.py"), "check-source",
                            "--checkout", str(source),
                            "--sources-jar", str(baseline_cache / "dyn4j-6.0.0-sources.jar"),
                            "--commit", baseline_report["commit"]],
                           output / "logs/final-source-check.log")
        evidence["baseline"]["final_source_check_exit_code"] = source_check.returncode
        if source_check.returncode:
            evidence["errors"].append("pinned source or source archive changed after corpus execution")
        for label, path, expected in (("staged JVM JAR", archives["jvm"], hashes["staged_jvm_jar"]),
                                      ("staged Android AAR", output / "archives" /
                                       f"dyn4k-core-android-{VERSION}.aar", hashes["staged_android_aar"]),
                                      ("Android classes.jar", archives["android"],
                                       hashes["staged_android_classes_jar"]),
                                      ("Kotlin standard library", stdlib, STDLIB_SHA),
                                      ("annotations", annotations, ANNOTATIONS_SHA)):
            if checked_archive(path, label) != expected:
                evidence["errors"].append(f"{label} changed after verification")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.TimeoutExpired,
            zipfile.BadZipFile) as error:
        evidence["errors"].append(str(error))
    if not evidence["errors"]:
        try:
            seal_lanes(output, {**evidence, "status": "PASSED"}, args.candidate_sha)
            seal_exception(output / "exception-serialization",
                           {"baseline": BASELINE_SHA,
                            "jvm": evidence["archives"]["staged_jvm_jar"],
                            "android": evidence["archives"]["staged_android_classes_jar"]},
                           evidence["exception_serialization"]["report_sha256"])
            seal_world(output / "logs/world-fixtures", args.candidate_sha,
                       {"baseline": BASELINE_SHA,
                        "jvm": evidence["archives"]["staged_jvm_jar"],
                        "android": evidence["archives"]["staged_android_classes_jar"]},
                       evidence["world_fixtures"]["report_sha256"])
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            evidence["errors"].append(str(error))
    evidence["status"] = "PASSED" if not evidence["errors"] else "FAILED"
    (output / "result.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({"status": evidence["status"], "errors": evidence["errors"]}, indent=2))
    return 0 if evidence["status"] == "PASSED" else 1


def seal_main() -> int:
    parser = argparse.ArgumentParser(description="Seal the full compatibility lane evidence before upload.")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[2:])
    output = args.output.resolve()
    manifest = {"candidate_sha": args.candidate_sha, "status": "FAILED",
                "files": {}, "exception_files": {}, "world_files": {}, "error": None}
    try:
        evidence = json.loads((output / "result.json").read_text())
        manifest["files"] = seal_lanes(output, evidence, args.candidate_sha)
        manifest["exception_files"] = seal_exception(
            output / "exception-serialization",
            {"baseline": BASELINE_SHA,
             "jvm": evidence["archives"]["staged_jvm_jar"],
             "android": evidence["archives"]["staged_android_classes_jar"]},
            evidence["exception_serialization"]["report_sha256"])
        manifest["world_files"] = seal_world(
            output / "logs/world-fixtures", args.candidate_sha,
            {"baseline": BASELINE_SHA,
             "jvm": evidence["archives"]["staged_jvm_jar"],
             "android": evidence["archives"]["staged_android_classes_jar"]},
            evidence["world_fixtures"]["report_sha256"])
        manifest["status"] = "PASSED"
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        manifest["error"] = str(error)
        manifest["files"] = {path.name: digest(path) for suffix in ("xml", "json")
                             for path in output.glob(f"corpus-*.{suffix}") if path.is_file()}
        world_output = output / "logs/world-fixtures"
        manifest["world_files"] = {path.relative_to(world_output).as_posix(): digest(path)
                                   for path in world_output.rglob("*") if path.is_file()}
    output.mkdir(parents=True, exist_ok=True)
    (output / "lane-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"status": manifest["status"], "files": len(manifest["files"]),
                      "exception_files": len(manifest["exception_files"]),
                      "world_files": len(manifest["world_files"]),
                      "error": manifest["error"]}, indent=2))
    return 0 if manifest["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(seal_main() if sys.argv[1:2] == ["seal"] else main())
