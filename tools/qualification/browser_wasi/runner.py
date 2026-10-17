from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


PACKAGE = re.compile(r"^package\s+([\w.]+)", re.MULTILINE)
CLASS = re.compile(r"^(?:(?:internal|private|public|open|abstract|data)\s+)*class\s+(\w+)")
FUNCTION = re.compile(r"\bfun\s+([A-Za-z_][A-Za-z_0-9]*)\s*\(")
TEAMCITY = re.compile(r"^##teamcity\[(\w+) name='([^']*)'")
MODULES = ("dyn4k-core", "dyn4k")
TARGETS = ("js", "wasmJs", "wasmWasi")
VERSION = "0.1.0-alpha.1"
CONSUMER = Path("consumers/qualification/browser-wasi")
RUNTIME_VERSIONS = {
    "chromium": {"minimum": "119.0.6045.105", "current": "155.0.8059.84"},
    "firefox": {"minimum": "120.0.1", "current": "158.0"},
    "wasmtime": {"minimum": "37.0.3", "current": "49.0.3"},
}


def source_cases(source_root: Path) -> set[tuple[str, str]]:
    cases: set[tuple[str, str]] = set()
    annotations = 0
    for source in sorted(source_root.rglob("*.kt")):
        content = source.read_text()
        package_match = PACKAGE.search(content)
        if not package_match:
            raise ValueError(f"package missing: {source}")
        package = package_match.group(1)
        class_name = None
        waiting = False
        for line in content.splitlines():
            match = CLASS.match(line)
            if match:
                class_name = match.group(1)
            if "@Test" in line:
                annotations += line.count("@Test")
                waiting = True
            if waiting:
                function = FUNCTION.search(line)
                if function:
                    if not class_name:
                        raise ValueError(f"test class missing: {source}")
                    case = (f"{package}.{class_name}", function.group(1))
                    if case in cases:
                        raise ValueError(f"duplicate test: {case}")
                    cases.add(case)
                    waiting = False
        if waiting:
            raise ValueError(f"test function missing: {source}")
    if not cases or len(cases) != annotations:
        raise ValueError(f"test inventory incomplete: {len(cases)} functions, {annotations} annotations")
    return cases


def verify_reports(
    report_dir: Path,
    expected: set[tuple[str, str]],
    task_name: str,
    runtime_marker: str,
) -> dict[str, object]:
    files = sorted(report_dir.glob("TEST-*.xml"))
    if not files:
        raise ValueError(f"missing XML reports: {report_dir}")
    observed: list[tuple[str, str]] = []
    failures = 0
    skipped = 0
    for path in files:
        suite = ET.parse(path).getroot()
        if suite.tag != "testsuite":
            raise ValueError(f"invalid test suite: {path}")
        cases = suite.findall("testcase")
        counts = {key: int(suite.attrib[key]) for key in ("tests", "failures", "errors", "skipped")}
        actual_failures = sum(case.find("failure") is not None for case in cases)
        actual_errors = sum(case.find("error") is not None for case in cases)
        actual_skips = sum(case.find("skipped") is not None for case in cases)
        if counts != {"tests": len(cases), "failures": actual_failures,
                      "errors": actual_errors, "skipped": actual_skips}:
            raise ValueError(f"report counts differ from cases: {path}")
        failures += actual_failures + actual_errors
        skipped += actual_skips
        for case in cases:
            name = case.attrib.get("name", "")
            class_name = case.attrib.get("classname", "")
            if not name.endswith("]") or f"{runtime_marker}" not in name:
                raise ValueError(f"wrong runtime or missing runtime identity: {name}")
            prefix = f"{task_name}."
            if not class_name.startswith(prefix):
                raise ValueError(f"wrong test task: {class_name}")
            observed.append((class_name[len(prefix):], name.split("[", 1)[0]))
    if failures:
        raise ValueError(f"{failures} failed tests")
    if skipped:
        raise ValueError(f"{skipped} skipped tests")
    if not observed or len(observed) != len(set(observed)):
        raise ValueError("zero or duplicate test identities")
    if set(observed) != expected:
        raise ValueError(
            f"missing or unexpected tests: missing={sorted(expected - set(observed))[:5]} "
            f"unexpected={sorted(set(observed) - expected)[:5]}"
        )
    return {"expected": len(expected), "executed": len(observed), "failures": 0,
            "skipped": 0, "cases": sorted([list(case) for case in observed]),
            "report_files": [str(path) for path in files]}


def verify_wasmtime_output(
    output: str, expected: set[tuple[str, str]]
) -> dict[str, object]:
    suites: list[str] = []
    active: tuple[str, str] | None = None
    finished: list[tuple[str, str]] = []
    failures = 0
    skipped = 0
    for line in output.splitlines():
        event = TEAMCITY.match(line)
        if not event:
            continue
        kind, name = event.groups()
        if kind == "testSuiteStarted":
            suites.append(name)
        elif kind == "testSuiteFinished":
            if not suites or suites.pop() != name or active:
                raise ValueError("unbalanced test suite")
        elif kind == "testStarted":
            if len(suites) != 2 or active:
                raise ValueError("overlapping or unscoped test")
            active = (f"{suites[0]}.{suites[1]}", name)
        elif kind == "testFinished":
            if not active or active[1] != name:
                raise ValueError("test finish differs from start")
            finished.append(active)
            active = None
        elif kind == "testFailed":
            failures += 1
        elif kind == "testIgnored":
            skipped += 1
    if active or suites:
        raise ValueError("unfinished tests or suites")
    if failures or skipped:
        raise ValueError(f"{failures} failed and {skipped} skipped tests")
    if not finished or len(finished) != len(set(finished)):
        raise ValueError("zero or duplicate test identities")
    if set(finished) != expected:
        raise ValueError(
            f"missing or unexpected tests: missing={sorted(expected - set(finished))[:5]} "
            f"unexpected={sorted(set(finished) - expected)[:5]}"
        )
    return {"expected": len(expected), "executed": len(finished), "failures": 0,
            "skipped": 0, "cases": sorted([list(case) for case in finished])}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True, check=False)


def candidate_identity(root: Path, expected_sha: str) -> None:
    head = command(["git", "rev-parse", "HEAD"], root)
    if head.returncode or head.stdout.strip() != expected_sha:
        raise ValueError(f"source SHA differs: {head.stdout.strip()}")
    status = command(["git", "status", "--porcelain", "--untracked-files=all"], root)
    if status.returncode:
        raise ValueError(status.stderr)
    generated = ("kotlin-js-store/", ".gradle/", ".kotlin/", "build/",
                 "dyn4k-core/build/", "dyn4k/build/", f"{CONSUMER}/build/",
                 f"{CONSUMER}/.gradle/", f"{CONSUMER}/.kotlin/")
    dirty = [line for line in status.stdout.splitlines()
             if not line[3:].startswith(generated)]
    if dirty:
        raise ValueError(f"source checkout is dirty: {dirty[:5]}")


def staged_files(root: Path) -> dict[str, str]:
    staging = root / "build/staging-repository/io/github/rubixhacker"
    hashes: dict[str, str] = {}
    for module in MODULES:
        root_publication = staging / module / VERSION
        for extension in ("module", "pom"):
            path = root_publication / f"{module}-{VERSION}.{extension}"
            if not path.is_file():
                raise ValueError(f"missing staged artifact: {path}")
            hashes[str(path.relative_to(root))] = sha256(path)
        for target in TARGETS:
            publication = f"{module}-{target.lower().replace('wasmjs', 'wasm-js').replace('wasmwasi', 'wasm-wasi')}"
            directory = staging / publication / VERSION
            for extension in ("jar", "module", "pom"):
                path = directory / f"{publication}-{VERSION}.{extension}"
                if not path.is_file():
                    raise ValueError(f"missing staged artifact: {path}")
                hashes[str(path.relative_to(root))] = sha256(path)
    return hashes


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def stage(root: Path, sha: str, output: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    result: dict[str, object] = {"candidate_sha": sha, "status": "FAILED"}
    try:
        candidate_identity(root, sha)
        tasks = [f":{module}:publish{publication}PublicationToStagingRepository"
                 for module in MODULES
                 for publication in ("KotlinMultiplatform", "Js", "WasmJs", "WasmWasi")]
        args = [str(root / "gradlew"), *tasks, "--rerun-tasks", "--console=plain", "--no-daemon"]
        env = dict(os.environ, JAVA_HOME=os.environ.get("JAVA_HOME", "/tmp/dyn4k-tools/jdk21"))
        completed = command(args, root, env)
        log = output / "stage-console.log"
        log.write_text(completed.stdout + completed.stderr)
        result.update(command=args, exit_code=completed.returncode, console=str(log))
        if completed.returncode:
            raise ValueError("staging command failed")
        candidate_identity(root, sha)
        result["artifacts"] = staged_files(root)
        result["status"] = "PASSED"
    except (OSError, ValueError) as error:
        result["reason"] = str(error)
    write_json(output / "stage.json", result)
    return 0 if result["status"] == "PASSED" else 1


def verified_stage(root: Path, sha: str, receipt: Path) -> dict[str, str]:
    recorded = json.loads(receipt.read_text())
    if recorded.get("candidate_sha") != sha or recorded.get("status") != "PASSED":
        raise ValueError("staging receipt does not bind this passing candidate")
    actual = staged_files(root)
    if recorded.get("artifacts") != actual:
        raise ValueError("staged artifact hashes differ from receipt")
    return actual


def runtime_version(binary: Path, target: str, runtime: str, expected: str, role: str) -> str:
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError(f"runtime binary unavailable: {binary}")
    observed = command([str(binary), "--version"], binary.parent)
    output = (observed.stdout + observed.stderr).strip()
    prefixes = {"chromium": "Google Chrome for Testing ",
                "firefox": "Mozilla Firefox ", "wasmtime": "wasmtime "}
    if runtime not in prefixes or observed.returncode or not output.startswith(prefixes[runtime]):
        raise ValueError(f"wrong runtime binary: {output}")
    version = output[len(prefixes[runtime]):].split()[0]
    if version != expected:
        raise ValueError(f"wrong runtime version: {output}")
    if runtime not in RUNTIME_VERSIONS or (target == "wasmWasi") != (runtime == "wasmtime"):
        raise ValueError(f"wrong target/runtime pair: {target}/{runtime}")
    if role not in ("minimum", "current"):
        raise ValueError(f"wrong version role: {role}")
    if expected != RUNTIME_VERSIONS[runtime][role]:
        raise ValueError(f"selected {role} version differs from pinned matrix: {expected}")
    return output


def test_source(root: Path, module: str) -> Path:
    if module == "consumer":
        return root / CONSUMER / "src/commonTest/kotlin"
    return root / module / "src/commonTest/kotlin"


def test_project(root: Path, module: str) -> Path:
    return root / CONSUMER if module == "consumer" else root / module


def linked_file(project: Path, target: str, configuration: str, module: str) -> Path:
    kind = "Production" if configuration == "production" else "Development"
    suffix = "optimized" if target != "js" and configuration == "production" else "kotlin"
    basename = ("dyn4k-browser-wasi-consumer" if module == "consumer"
                else f"dyn4k-{module}") + "-test"
    extension = ".wasm" if target == "wasmWasi" else ".mjs" if target == "wasmJs" else ".js"
    return (project / "build/compileSync" / target / "test" /
            f"test{kind}Executable" / suffix / f"{basename}{extension}")


def gradle_test_task(module: str, target: str, configuration: str) -> str:
    prefix = ":" if module == "consumer" else f":{module}:"
    if target != "wasmWasi":
        return f"{prefix}{target}BrowserTest"
    kind = "Production" if configuration == "production" else "Development"
    optimize = "Optimize" if configuration == "production" else ""
    return f"{prefix}compileTest{kind}ExecutableKotlinWasmWasi{optimize}"


def run_lane(root: Path, sha: str, receipt: Path, output: Path, target: str,
             runtime: str, role: str, configuration: str, binary: Path,
             expected_version: str) -> int:
    output.mkdir(parents=True, exist_ok=True)
    lane: dict[str, object] = {"candidate_sha": sha, "target": target,
                               "runtime": runtime, "version_role": role,
                               "configuration": configuration, "status": "FAILED"}
    try:
        candidate_identity(root, sha)
        lane["artifact_hashes"] = verified_stage(root, sha, receipt)
        lane["runtime_version"] = runtime_version(binary, target, runtime, expected_version, role)
        lane["runtime_binary"] = str(binary.resolve())
        lane["runtime_sha256"] = sha256(binary)
        lane["expected_runtime_version"] = expected_version
        if target not in TARGETS or configuration not in ("development", "production"):
            raise ValueError("unknown target or configuration")
        results: dict[str, object] = {}
        for module in (*MODULES, "consumer"):
            project = test_project(root, module)
            expected = source_cases(test_source(root, module))
            if module == "consumer" and (
                "qualification.StagedWorldTest",
                "stagedModulesShareBodiesAndDeliverCollisionCallbacks",
            ) not in expected:
                raise ValueError("staged physics assertion is missing")
            module_output = output / module
            module_output.mkdir(exist_ok=True)
            env = dict(os.environ, JAVA_HOME=os.environ.get("JAVA_HOME", "/tmp/dyn4k-tools/jdk21"))
            if runtime == "chromium":
                env.update(DYN4K_BROWSER="chromium", CHROME_BIN=str(binary))
            elif runtime == "firefox":
                env.update(DYN4K_BROWSER="firefox", FIREFOX_BIN=str(binary))
            gradle = [str(root / "gradlew")]
            if module == "consumer":
                gradle += ["-p", str(project), f"-PqualificationRepository={root / 'build/staging-repository'}"]
            task = gradle_test_task(module, target, configuration)
            if target != "wasmWasi":
                gradle.append("kotlinUpgradeYarnLock" if target == "js"
                              else "kotlinWasmUpgradeYarnLock")
            gradle += [task, "--rerun-tasks", "--console=plain", "--no-daemon"]
            if configuration == "production" and target != "wasmWasi":
                gradle.append("-PqualificationProduction=true")
            report_dir = project / "build/test-results" / f"{target}BrowserTest"
            if target != "wasmWasi" and report_dir.exists():
                shutil.rmtree(report_dir)
            built = command(gradle, root, env)
            console = module_output / "gradle-console.log"
            console.write_text(built.stdout + built.stderr)
            if built.returncode:
                raise ValueError(f"{module} Gradle task failed: {console}")
            linked = linked_file(project, target, configuration, module)
            if not linked.is_file():
                raise ValueError(f"missing linked test executable: {linked}")
            if configuration == "production" and target != "wasmWasi":
                marker = f"qualification test input: {linked}"
                if marker not in built.stdout:
                    raise ValueError(f"production test did not select optimized input: {linked}")
            if target == "wasmWasi":
                invocation = [str(binary), "run", "-W", "gc=y", "-W", "exceptions=y",
                              "-W", "function-references=y", "--invoke", "startUnitTests", str(linked)]
                observed = command(invocation, root)
                raw = module_output / "wasmtime-console.log"
                raw.write_text(observed.stdout + observed.stderr)
                if observed.returncode:
                    raise ValueError(f"{module} Wasmtime tests failed: {raw}")
                evidence = verify_wasmtime_output(observed.stdout, expected)
                evidence["command"] = invocation
                evidence["exit_code"] = observed.returncode
                evidence["raw_console"] = str(raw)
            else:
                marker = ("ChromeHeadless" if runtime == "chromium" else "Firefox") + expected_version.split(".")[0]
                evidence = verify_reports(report_dir, expected, f"{target}BrowserTest", marker)
                xml_dir = module_output / "xml"
                xml_dir.mkdir(exist_ok=True)
                copied = []
                for report in sorted(report_dir.glob("TEST-*.xml")):
                    copy = xml_dir / report.name
                    shutil.copy2(report, copy)
                    copied.append({"path": str(copy), "sha256": sha256(copy)})
                evidence["raw_xml"] = copied
            evidence["gradle_command"] = gradle
            evidence["gradle_exit_code"] = built.returncode
            evidence["gradle_console"] = str(console)
            evidence["linked_executable"] = str(linked)
            evidence["linked_sha256"] = sha256(linked)
            if sha256(binary) != lane["runtime_sha256"]:
                raise ValueError(f"runtime binary changed during {module} execution")
            runtime_version(binary, target, runtime, expected_version, role)
            results[module] = evidence
            write_json(module_output / "result.json", evidence)
        candidate_identity(root, sha)
        lane["modules"] = results
        lane["status"] = "PASSED"
    except (OSError, ValueError, json.JSONDecodeError) as error:
        lane["reason"] = str(error)
    write_json(output / "lane.json", lane)
    return 0 if lane["status"] == "PASSED" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("stage", "run"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--target", choices=TARGETS)
    parser.add_argument("--runtime", choices=("chromium", "firefox", "wasmtime"))
    parser.add_argument("--version-role", choices=("minimum", "current"))
    parser.add_argument("--configuration", choices=("development", "production"))
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()
    if arguments.action == "stage":
        return stage(arguments.root.resolve(), arguments.candidate_sha, arguments.output.resolve())
    required = (arguments.receipt, arguments.target, arguments.runtime, arguments.version_role,
                arguments.configuration, arguments.binary, arguments.expected_version)
    if any(value is None for value in required):
        parser.error("run requires receipt, target, runtime, version-role, configuration, binary, and expected-version")
    return run_lane(arguments.root.resolve(), arguments.candidate_sha, arguments.receipt.resolve(),
                    arguments.output.resolve(), arguments.target, arguments.runtime,
                    arguments.version_role, arguments.configuration, arguments.binary.resolve(),
                    arguments.expected_version)


if __name__ == "__main__":
    sys.exit(main())
