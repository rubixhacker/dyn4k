from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from candidate_coverage import digest, git
import build_provenance


HARNESS = Path(__file__).resolve().parent / "fixtures/ledger_corpus/LedgerCorpusReport.java"
PARAMETER_CLASSES = {
    "org.dyn4j.collision.broadphase.CollisionBodyBroadphaseTest": 25,
    "org.dyn4j.collision.broadphase.CollisionItemBroadphaseTest": 29,
}
PARAMETER_PATTERN = re.compile(r"([^\[]+)\[([^@\]]+)@([0-9a-fA-F]+)\]")


def read_xml(path: Path, expected: int) -> list[tuple[str, str]]:
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
    return identities


def normalized_cases(identities: list[tuple[str, str]]) -> Counter:
    groups = {}
    for owner, count in PARAMETER_CLASSES.items():
        rows = [name for class_name, name in identities if class_name == owner]
        seen = {}
        for name in rows:
            match = PARAMETER_PATTERN.fullmatch(name)
            if match is None:
                raise ValueError(f"parameterized case identity is malformed: {owner}")
            method, parameter_type, address = match.groups()
            seen.setdefault((parameter_type, address), set()).add(method)
        if len(seen) != 5 or len(rows) != count * 5 or any(len(methods) != count for methods in seen.values()):
            raise ValueError(f"parameterized case inventory differs: {owner}")
        groups[owner] = {key: index for index, key in enumerate(seen)}
    result = Counter()
    for owner, name in identities:
        if owner in groups:
            method, parameter_type, address = PARAMETER_PATTERN.fullmatch(name).groups()
            name = f"{method}[{parameter_type}#{groups[owner][(parameter_type, address)]}]"
        result[(owner, name)] += 1
    return result


def tool(jdk: Path, name: str, major: int) -> dict:
    path = (jdk / "bin" / name).resolve()
    if not path.is_file():
        raise ValueError(f"JDK {major} {name} is missing")
    run = subprocess.run([str(path), "-version"], capture_output=True, text=True, check=True)
    version = (run.stdout + run.stderr).strip()
    marker = "1.8." if major == 8 else "21."
    if marker not in version:
        raise ValueError(f"JDK {major} {name} version differs")
    return {"path": str(path), "sha256": digest(path), "version": version}


def checked_inputs(ledger: dict, source: Path) -> dict[str, str]:
    if git(source, "rev-parse", "HEAD") != ledger["baseline"]["commit"]:
        raise ValueError("pinned Java source checkout revision differs")
    run_inputs = json.loads((Path(__file__).resolve().parents[2] /
                             "docs/verification/baseline-run.json").read_text())["test_input_sha256"]
    tests = {row["id"]: row["sha256"] for row in ledger["tests"]}
    if {path: run_inputs[path] for path in tests} != tests:
        raise ValueError("pinned Java test source hashes differ from baseline run")
    for path, checksum in run_inputs.items():
        if not (source / path).is_file() or digest(source / path) != checksum:
            raise ValueError(f"pinned Java source input differs: {path}")
    return run_inputs


def java_temp_directory(output: Path) -> Path:
    output = output.resolve()
    if not output.is_dir():
        raise ValueError("Java corpus output directory is missing")
    directory = output / "java-tmp"
    try:
        directory.mkdir()
    except FileExistsError:
        pass
    resolved = directory.resolve()
    if directory.is_symlink() or not resolved.is_dir() or resolved.parent != output:
        raise ValueError("Java corpus temporary directory is outside its output")
    return resolved


def runtime_command(java: str, classpath: str, java_tmp: Path, xml: Path,
                    classes: list[str]) -> list[str]:
    java_tmp = java_tmp.resolve(strict=True)
    if not java_tmp.is_dir():
        raise ValueError("Java corpus temporary directory is missing")
    return [java, f"-Djava.io.tmpdir={java_tmp}", "-cp", classpath,
            "LedgerCorpusReport", str(xml), *classes]


def replay_temp_directory(root: Path):
    try:
        root = root.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError("Java corpus replay root is missing or unsafe") from error
    if not root.is_dir():
        raise ValueError("Java corpus replay root is not a directory")
    build = root / "build"
    if build.is_symlink():
        raise ValueError("Java corpus replay build directory is a symlink")
    try:
        build.mkdir(exist_ok=True)
    except FileExistsError as error:
        raise ValueError("Java corpus replay build path is not a directory") from error
    resolved_build = build.resolve(strict=True)
    if (build.is_symlink() or not resolved_build.is_dir()
            or resolved_build.parent != root):
        raise ValueError("Java corpus replay directory is outside its worktree build output")
    return tempfile.TemporaryDirectory(prefix="dyn4k-ledger-corpus-replay-",
                                       dir=resolved_build)


def capture(ledger: dict, root: Path, source: Path, jar: Path, deps: dict[str, Path],
            jdks: dict[int, Path], output: Path,
            runtime_env: dict[str, str] | None = None) -> dict:
    root = root.resolve()
    source = source.resolve()
    jar = jar.resolve()
    if output.exists():
        raise ValueError("corpus output directory already exists")
    output.mkdir(parents=True)
    java_tmp = java_temp_directory(output)
    inputs = checked_inputs(ledger, source)
    source_binding = ledger["candidate_source"]
    if (jar != (root / source_binding["artifact"]).resolve()
            or digest(jar) != source_binding["artifact_sha256"]
            or digest(jar) == ledger["baseline"]["binary_sha256"]):
        raise ValueError("candidate JAR differs from source mapping or is the pinned baseline")
    baseline = Path(deps["baseline"]).resolve()
    if digest(baseline) != ledger["baseline"]["binary_sha256"]:
        raise ValueError("pinned baseline JAR differs")
    dependencies = {key: {"path": str(path.resolve()), "sha256": digest(path)}
                    for key, path in deps.items()}
    jdk_tools = {str(major): {name: tool(jdk, name, major) for name in ("javac", "java")}
                 for major, jdk in jdks.items()}
    sources = [source / row["id"] for row in ledger["tests"]]
    classes = sorted({".".join(path.relative_to(source / "src/test/java").with_suffix("").parts)
                      for path in sources if "@Test" in path.read_text(errors="replace")
                      or "@RunWith" in path.read_text(errors="replace")})
    if len(sources) != 199 or len(classes) != 190:
        raise ValueError("pinned Java test file or class inventory differs")
    argfile = output / "sources.args"
    argfile.write_text("\n".join('"' + str(path) + '"' for path in sources) + "\n")
    lanes = {}
    reference = None
    for provider, archive in (("baseline", baseline), ("candidate", jar)):
        for compiler in (8, 21):
            directory = output / "classes" / f"{provider}-javac{compiler}"
            directory.mkdir(parents=True)
            cp = os.pathsep.join(str(path) for path in
                                 (archive, deps["stdlib"], deps["annotations"], deps["junit"], deps["hamcrest"]))
            options = ["-source", "8", "-target", "8"] if compiler == 8 else ["--release", "8"]
            command = [jdk_tools[str(compiler)]["javac"]["path"], "-encoding", "UTF-8", *options,
                       "-cp", cp, "-d", str(directory), "@" + str(argfile), str(HARNESS)]
            compile_run = subprocess.run(command, capture_output=True, text=True, check=False, timeout=300)
            compile_record = {"command": command, "exit_code": compile_run.returncode,
                              "raw_stdout": compile_run.stdout, "raw_stderr": compile_run.stderr}
            if compile_run.returncode:
                lanes[f"{provider}-javac{compiler}"] = {"compile": compile_record, "status": "failed"}
                continue
            resources = source / "src/test/resources"
            if resources.exists():
                shutil.copytree(resources, directory, dirs_exist_ok=True)
            for runtime in (8, 21):
                lane = f"{provider}-javac{compiler}-java{runtime}"
                xml = output / f"{lane}.xml"
                run_command = runtime_command(jdk_tools[str(runtime)]["java"]["path"],
                                              os.pathsep.join((cp, str(directory))),
                                              java_tmp, xml, classes)
                run = subprocess.run(run_command, capture_output=True, text=True, check=False,
                                     timeout=600,
                                     env={**os.environ, **runtime_env} if runtime_env else None)
                record = {"compile": compile_record, "command": run_command,
                          "exit_code": run.returncode, "raw_stdout": run.stdout,
                          "raw_stderr": run.stderr, "xml": xml.name,
                          "xml_sha256": digest(xml) if xml.is_file() else None,
                          "status": "failed"}
                if run.returncode == 0 and xml.is_file():
                    identities = normalized_cases(read_xml(xml, ledger["baseline_test_counts"]["actual_executed_cases"]))
                    if reference is None:
                        reference = identities
                    if identities == reference:
                        record["status"] = "passed"
                    else:
                        record["reason"] = "candidate Java case identities differ from pinned baseline execution"
                lanes[lane] = record
    if digest(jar) != source_binding["artifact_sha256"]:
        raise ValueError("candidate JAR changed during Java corpus")
    complete = all(lanes.get(f"{provider}-javac{compiler}-java{runtime}", {}).get("status") == "passed"
                   for provider in ("baseline", "candidate") for compiler in (8, 21) for runtime in (8, 21))
    return {"schema_version": 3, "kind": "java-test", "target": "jvm",
            "probe": "unchanged-junit-xml-v1", "baseline": ledger["baseline"],
            "candidate_commit": source_binding["revision"], "source_tree": source_binding["tree"],
            "artifact_sha256": source_binding["artifact_sha256"], "input_sha256": inputs,
            "harness_sha256": digest(HARNESS), "dependencies": dependencies,
            "tools": jdk_tools, "lanes": lanes,
            "normalized_case_ids": sorted([list(item) for item in reference] if reference else []),
            "actual_executed_cases_per_lane": len(reference) if reference else 0,
            "passed": complete, "reason": None if complete else "one or more unchanged Java lanes failed"}


def validate_report(report: dict, ledger: dict, root: Path, source: Path, jar: Path) -> str | None:
    root = root.resolve()
    source = source.resolve()
    jar = jar.resolve()
    binding = ledger.get("candidate_source", {})
    if not isinstance(report, dict) or any((
            report.get("schema_version") != 3,
            report.get("kind") != "java-test",
            report.get("target") != "jvm",
            report.get("probe") != "unchanged-junit-xml-v1",
            report.get("baseline") != ledger.get("baseline"),
            report.get("candidate_commit") != binding.get("revision"),
            report.get("source_tree") != binding.get("tree"),
            report.get("artifact_sha256") != binding.get("artifact_sha256"),
            report.get("harness_sha256") != digest(HARNESS),
            report.get("passed") is not True,
    )):
        return "Java corpus report identity or executable outcome differs"
    try:
        if report.get("input_sha256") != checked_inputs(ledger, source):
            return "Java corpus original source hashes differ"
        receipt_name = report.get("build_receipt")
        if (not isinstance(receipt_name, str) or not receipt_name
                or Path(receipt_name).is_absolute() or ".." in Path(receipt_name).parts):
            return "Java corpus build receipt path is unsafe"
        receipt_path = root / receipt_name
        if not receipt_path.is_file() or digest(receipt_path) != report.get("build_receipt_sha256"):
            return "Java corpus build receipt differs"
        dependencies = report.get("dependencies", {})
        dep_paths = {}
        for key in ("baseline", "stdlib", "annotations", "junit", "hamcrest"):
            entry = dependencies.get(key, {})
            path = Path(entry.get("path", ""))
            if not path.is_file() or digest(path) != entry.get("sha256"):
                return f"Java corpus dependency differs: {key}"
            dep_paths[key] = path
        jdks = {}
        for major in (8, 21):
            entries = report.get("tools", {}).get(str(major), {})
            java = Path(entries.get("java", {}).get("path", ""))
            if not java.is_file():
                return f"Java corpus JDK {major} is missing"
            jdk = java.parent.parent
            if entries != {name: tool(jdk, name, major) for name in ("javac", "java")}:
                return f"Java corpus JDK {major} identity differs"
            jdks[major] = jdk
        xml_root = report.get("xml_root")
        if (not isinstance(xml_root, str) or not xml_root
                or Path(xml_root).is_absolute() or ".." in Path(xml_root).parts):
            return "Java corpus XML root is unsafe"
        raw_root = root / xml_root
        expected = ledger["baseline_test_counts"]["actual_executed_cases"]
        archived_reference = Counter(map(tuple, report.get("normalized_case_ids", [])))
        if len(archived_reference) != expected or report.get("actual_executed_cases_per_lane") != expected:
            return "Java corpus original identity index is incomplete"
        for provider in ("baseline", "candidate"):
            for compiler in (8, 21):
                for runtime in (8, 21):
                    lane = f"{provider}-javac{compiler}-java{runtime}"
                    record = report.get("lanes", {}).get(lane, {})
                    xml = raw_root / f"{lane}.xml"
                    if (record.get("status") != "passed" or not xml.is_file()
                            or digest(xml) != record.get("xml_sha256")
                            or normalized_cases(read_xml(xml, expected)) != archived_reference):
                        return f"Java corpus XML or outcome differs: {lane}"
        build_error = build_provenance.verify(json.loads(receipt_path.read_text()), root, jar, binding)
        if build_error:
            return build_error
        with replay_temp_directory(root) as directory:
            observed = capture(ledger, root, source, jar, dep_paths, jdks, Path(directory) / "run")
        if (not observed["passed"] or observed["input_sha256"] != report["input_sha256"]
                or observed["normalized_case_ids"] != report["normalized_case_ids"]
                or observed["actual_executed_cases_per_lane"] != expected):
            return "Java corpus differs from replayed unchanged sources"
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
            ET.ParseError, KeyError, TypeError) as error:
        return f"Java corpus replay failed: {error}"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run unchanged pinned Java tests against baseline and candidate.")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--baseline-jar", type=Path, required=True)
    parser.add_argument("--stdlib", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--hamcrest", type=Path, required=True)
    parser.add_argument("--jdk8", type=Path, required=True)
    parser.add_argument("--jdk21", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    ledger = json.loads(args.ledger.read_text())
    jar = root / ledger["candidate_source"]["artifact"]
    if root not in args.output.resolve().parents or root not in args.build_receipt.resolve().parents:
        parser.error("raw output and build receipt must be inside the worktree")
    if args.output.exists():
        parser.error("output directory already exists")
    report = capture(ledger, root, args.source, jar,
                     {"baseline": args.baseline_jar, "stdlib": args.stdlib,
                      "annotations": args.annotations, "junit": args.junit,
                      "hamcrest": args.hamcrest}, {8: args.jdk8, 21: args.jdk21}, args.output)
    shutil.rmtree(args.output / "classes")
    (args.output / "sources.args").unlink()
    report["xml_root"] = args.output.resolve().relative_to(root).as_posix()
    report["build_receipt"] = args.build_receipt.resolve().relative_to(root).as_posix()
    report["build_receipt_sha256"] = digest(args.build_receipt)
    report_path = args.output / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": report["passed"], "cases": report["actual_executed_cases_per_lane"],
                      "lanes": {key: value["status"] for key, value in report["lanes"].items()},
                      "report_sha256": digest(report_path)}, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
