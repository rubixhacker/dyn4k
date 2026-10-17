from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

COMMIT = "058bf6d982a0fb89b54050f929f6ea9dae53b714"
BINARY_SHA256 = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
SOURCES_SHA256 = "83b47be47bdce27681139dab84937e0f586b70ab800dc494fbebed4b58893223"
BASE = "https://repo.maven.apache.org/maven2/org/dyn4j/dyn4j/6.0.0"
JUNIT = "https://repo.maven.apache.org/maven2/junit/junit/4.13.1/junit-4.13.1.jar"
HAMCREST = "https://repo.maven.apache.org/maven2/org/hamcrest/hamcrest-core/1.3/hamcrest-core-1.3.jar"
EXPECTED_CASES = 2385


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: Path, expected: str | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        temp = dest.with_suffix(dest.suffix + ".part")
        urllib.request.urlretrieve(url, temp)
        temp.replace(dest)
    if expected and digest(dest) != expected:
        dest.unlink(missing_ok=True)
        raise SystemExit(f"checksum mismatch for {dest.name}")
    if not dest.is_file() or not dest.stat().st_size:
        raise SystemExit(f"missing or empty artifact: {dest}")


def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    kwargs.setdefault("text", True)
    return subprocess.run(command, check=True, **kwargs)


def jar_types(binary: Path, only: set[str] | None = None) -> tuple[list[str], dict[str, str]]:
    names = run(["jar", "tf", str(binary)], capture_output=True).stdout.splitlines()
    classes = sorted(n[:-6].replace("/", ".") for n in names
                     if n.endswith(".class") and not n.endswith("module-info.class"))
    signatures = {name: run(["javap", "-classpath", str(binary), "-protected", "-s", name],
                            capture_output=True).stdout for name in classes
                  if only is None or name in only}
    return classes, signatures


def surface(signature: str) -> tuple[str, dict[tuple[str, str], str]] | None:
    lines = [line.strip() for line in signature.splitlines()]
    header = next((line for line in lines if line.endswith("{") and " class " in f" {line} "
                   or line.endswith("{") and " interface " in f" {line} "), None)
    if header is None or not header.startswith(("public ", "protected ")):
        return None
    header = re.sub(r"\s+", " ", header)
    members = {}
    for index, line in enumerate(lines):
        if not line.endswith(";") or not line.startswith(("public ", "protected ")):
            continue
        if index + 1 >= len(lines) or not lines[index + 1].startswith("descriptor: "):
            raise ValueError(f"missing descriptor for {line}")
        descriptor = lines[index + 1].removeprefix("descriptor: ")
        name = line.split("(", 1)[0].split()[-1] if "(" in line else line[:-1].split()[-1]
        parameter_types = descriptor.split(")", 1)[0] + ")" if "(" in descriptor else ""
        key = (name, parameter_types)
        declaration = re.sub(r"\s+", " ", line) + " descriptor: " + descriptor
        if descriptor.startswith("("):
            declaration = declaration.replace(" static final ", " static ", 1)
        members[key] = declaration
    return header, members


def split_top_level(value: str, separator: str) -> list[str]:
    parts = []
    depth = 0
    start = 0
    index = 0
    while index < len(value):
        if value[index] == "<":
            depth += 1
        elif value[index] == ">":
            depth -= 1
        elif depth == 0 and value.startswith(separator, index):
            parts.append(value[start:index].strip())
            index += len(separator)
            start = index
            continue
        index += 1
    parts.append(value[start:].strip())
    return parts


def type_contract(header: str) -> tuple[str, str | None, set[str]]:
    declaration = header.removesuffix(" {")
    implemented = split_top_level(declaration, " implements ")
    base = implemented[0]
    interfaces = set(split_top_level(implemented[1], ", ")) if len(implemented) > 1 else set()
    extended = split_top_level(base, " extends ")
    if len(extended) > 1:
        if " interface " in f" {extended[0]} ":
            interfaces.update(split_top_level(extended[1], ", "))
            superclass = None
        else:
            superclass = extended[1]
    else:
        superclass = None
    return extended[0], superclass, interfaces


def compare_jars(baseline: Path, candidate: Path, only: set[str] | None = None) -> dict[str, object]:
    baseline_types, baseline_signatures = jar_types(baseline, only)
    candidate_types, candidate_signatures = jar_types(candidate, set(baseline_types) if only is None else only)
    selected = set(baseline_types) if only is None else only
    unknown = sorted(selected - set(baseline_types))
    if unknown:
        raise ValueError(f"types absent from baseline: {', '.join(unknown)}")
    missing = []
    mismatches = []
    compared = []
    for name in sorted(selected):
        expected = surface(baseline_signatures[name])
        if expected is None:
            continue
        compared.append(name)
        if name not in candidate_signatures:
            missing.append(name)
            continue
        actual = surface(candidate_signatures[name])
        if actual is None:
            mismatches.append(f"{name}: public/protected type access lost")
            continue
        expected_type = type_contract(expected[0])
        actual_type = type_contract(actual[0])
        if (expected_type[0] != actual_type[0] or expected_type[1] != actual_type[1]
                or not expected_type[2].issubset(actual_type[2])):
            mismatches.append(f"{name}: type contract changed: {actual[0]}")
        for key, member in expected[1].items():
            if key not in actual[1]:
                mismatches.append(f"{name}: missing {member}")
            elif member != actual[1][key]:
                mismatches.append(f"{name}: changed {member} -> {actual[1][key]}")
    return {"baseline_types": len(baseline_types), "candidate_types": len(candidate_types),
            "compared_api_types": compared, "missing_types": missing,
            "signature_mismatches": mismatches}


def result_field(output: str, label: str) -> int | None:
    values = [line.split("=", 1)[1] for line in output.splitlines()
              if line.startswith(label + "=")]
    if len(values) != 1 or not values[0].isdigit():
        return None
    return int(values[0])


def validate_run_report(report: dict[str, object]) -> None:
    output = report.get("output")
    stderr = report.get("stderr")
    if not isinstance(output, str) or not isinstance(stderr, str):
        raise ValueError("run output fields are missing or invalid")
    expected = {"actual_executed_cases": ("ACTUAL_TESTS", EXPECTED_CASES),
                "failures": ("FAILURES", 0), "ignored": ("IGNORED", 0)}
    for field, (marker, value) in expected.items():
        observed = report.get(field)
        if type(observed) is not int or observed != value or result_field(output, marker) != observed:
            raise ValueError(f"invalid {field}: expected {value} and matching {marker} marker")
    if type(report.get("process_exit_code")) is not int or report["process_exit_code"] != 0:
        raise ValueError("baseline test process did not exit successfully")
    if report.get("compile_release") != 8 or report.get("harness_class_major") != 52:
        raise ValueError("harness must use Java 8 APIs and bytecode")
    if not isinstance(report.get("javac_version"), str) or not report["javac_version"]:
        raise ValueError("missing compiler version")
    if not isinstance(report.get("java_version"), str) or not report["java_version"]:
        raise ValueError("missing runtime version")
    if not isinstance(report.get("test_input_sha256"), dict) or not report["test_input_sha256"]:
        raise ValueError("missing test input hashes")


def verify_source_inputs(source: Path, sources_jar: Path, commit: str) -> dict[str, object]:
    actual = run(["git", "-C", str(source), "rev-parse", "HEAD"],
                 capture_output=True).stdout.strip()
    if actual != commit:
        raise ValueError(f"source revision mismatch: {actual}")
    status = run(["git", "-C", str(source), "status", "--porcelain=v1",
                  "--untracked-files=all", "--ignored", "--", "src/main/java",
                  "src/test/java", "src/test/resources"], capture_output=True).stdout
    if status:
        raise ValueError(f"dirty or untracked source inputs: {status.strip()}")
    paths = run(["git", "-C", str(source), "ls-tree", "-r", "--name-only", commit,
                 "src/main/java"], capture_output=True).stdout.splitlines()
    production = {path.removeprefix("src/main/java/"): path for path in paths
                  if path.endswith(".java")}
    with zipfile.ZipFile(sources_jar) as archive:
        archive_names = {name for name in archive.namelist() if name.endswith(".java")}
        if archive_names != set(production):
            raise ValueError(f"source archive entries differ: missing={sorted(set(production) - archive_names)}, "
                             f"extra={sorted(archive_names - set(production))}")
        for name, path in production.items():
            tracked = subprocess.run(["git", "-C", str(source), "show", f"{commit}:{path}"],
                                     check=True, capture_output=True).stdout
            if archive.read(name) != tracked:
                raise ValueError(f"source archive bytes differ: {name}")
    return {"commit": commit, "tracked_production_java_files": len(production),
            "source_jar_java_files": len(archive_names),
            "source_jar_sha256": digest(sources_jar), "source_inputs_clean": True,
            "source_jar_matches_tracked_bytes": True}


def checked_out_sources(cache: Path) -> Path:
    source = cache / "dyn4j-source"
    if not (source / ".git").exists():
        run(["git", "clone", "--filter=blob:none", "https://github.com/dyn4j/dyn4j.git", str(source)])
    status = run(["git", "-C", str(source), "status", "--porcelain=v1",
                  "--untracked-files=all", "--ignored", "--", "src/main/java",
                  "src/test/java", "src/test/resources"], capture_output=True).stdout
    if status:
        raise SystemExit(f"dirty or untracked source inputs: {status.strip()}")
    run(["git", "-C", str(source), "fetch", "origin", COMMIT])
    run(["git", "-C", str(source), "checkout", "--detach", COMMIT])
    actual = run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True).stdout.strip()
    if actual != COMMIT:
        raise SystemExit(f"source revision mismatch: {actual}")
    return source


def inventory(source: Path, binary: Path, output: Path) -> dict[str, object]:
    prod = sorted((source / "src/main/java").rglob("*.java"))
    tests = sorted((source / "src/test/java").rglob("*.java"))
    if len(prod) != 268 or len(tests) != 199:
        raise SystemExit(f"unaccounted source files: production={len(prod)} tests={len(tests)}")
    classes, signatures = jar_types(binary)
    data = {
        "baseline": {"coordinate": "org.dyn4j:dyn4j:6.0.0", "commit": COMMIT,
                     "binary_sha256": digest(binary), "sources_sha256": SOURCES_SHA256},
        "production_java_files": [str(p.relative_to(source)) for p in prod],
        "test_java_files": [str(p.relative_to(source)) for p in tests],
        "test_annotations": sum(p.read_text(errors="replace").count("@Test") for p in tests),
        "types": classes,
        "api_types": sorted(name for name, signature in signatures.items() if surface(signature) is not None),
        "public_protected_jvm_signatures": signatures,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


def execute(source: Path, binary: Path, cache: Path, output: Path) -> dict[str, object]:
    deps = cache / "deps"
    junit, hamcrest = deps / "junit-4.13.1.jar", deps / "hamcrest-core-1.3.jar"
    fetch(JUNIT, junit)
    fetch(HAMCREST, hamcrest)
    test_src = sorted((source / "src/test/java").rglob("*.java"))
    resources = source / "src/test/resources"
    test_inputs = [*test_src, *(path for path in sorted(resources.rglob("*")) if path.is_file())]
    test_hashes = {str(path.relative_to(source)): digest(path) for path in test_inputs}
    test_classes = [p for p in test_src if "@Test" in p.read_text(errors="replace") or "@RunWith" in p.read_text(errors="replace")]
    if not test_classes:
        raise SystemExit("empty test suite")
    work = cache / "run"
    if work.exists():
        shutil.rmtree(work)
    classes = work / "classes"
    classes.mkdir(parents=True)
    cp = os.pathsep.join(map(str, [binary, junit, hamcrest]))
    all_test_sources = [str(p) for p in test_src]
    argfile = work / "test-sources.args"
    argfile.write_text("\n".join('"' + p.replace('"', '\\"') + '"' for p in all_test_sources) + "\n")
    run(["javac", "-encoding", "UTF-8", "--release", "8", "-cp", cp,
         "-d", str(classes), "@" + str(argfile)])
    if resources.exists():
        shutil.copytree(resources, classes, dirs_exist_ok=True)
    class_names = sorted({
        ".".join(p.relative_to(source / "src/test/java").with_suffix("").parts)
        for p in test_classes
    })
    report_class = work / "BaselineJUnitReport.java"
    report_class.write_text('''import org.junit.runner.JUnitCore;\nimport org.junit.runner.Result;\npublic final class BaselineJUnitReport {\n public static void main(String[] args) { Result r = new JUnitCore().run(load(args));\n  System.out.println("ACTUAL_TESTS=" + r.getRunCount()); System.out.println("FAILURES=" + r.getFailureCount());\n  System.out.println("IGNORED=" + r.getIgnoreCount()); if (!r.wasSuccessful()) { r.getFailures().forEach(System.err::println); System.exit(1); } }\n static Class<?>[] load(String[] names) { try { Class<?>[] c = new Class<?>[names.length]; for (int i=0;i<names.length;i++) c[i]=Class.forName(names[i]); return c; } catch(Exception e) { throw new RuntimeException(e); } }\n}\n''')
    run(["javac", "--release", "8", "-cp", os.pathsep.join([cp, str(classes)]),
         "-d", str(classes), str(report_class)])
    harness_bytes = (classes / "BaselineJUnitReport.class").read_bytes()
    harness_major = int.from_bytes(harness_bytes[6:8], "big")
    result = subprocess.run(["java", "-cp", os.pathsep.join([cp, str(classes)]),
                             "BaselineJUnitReport", *class_names], check=False,
                            capture_output=True, text=True)
    actual = result_field(result.stdout, "ACTUAL_TESTS")
    failures = result_field(result.stdout, "FAILURES")
    summary = {"commit": COMMIT, "binary_sha256": digest(binary), "test_files": len(test_src),
               "test_classes": len(class_names), "actual_executed_cases": actual, "failures": failures,
               "ignored": result_field(result.stdout, "IGNORED"),
               "process_exit_code": result.returncode, "output": result.stdout, "stderr": result.stderr,
               "javac_version": run(["javac", "-version"], capture_output=True).stdout.strip(),
               "java_version": run(["java", "-version"], capture_output=True).stderr.splitlines()[0],
               "compile_release": 8, "harness_class_major": harness_major,
               "test_input_sha256": test_hashes,
               "junit_sha256": digest(junit), "hamcrest_sha256": digest(hamcrest)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n")
    try:
        validate_run_report(summary)
    except ValueError as error:
        raise SystemExit(f"upstream baseline suite failed: {error}; see the retained run summary") from error
    return summary


def main() -> None:
    if len(os.sys.argv) > 1 and os.sys.argv[1] == "check-source":
        source_parser = argparse.ArgumentParser(description="Check pinned source inputs and archive bytes.")
        source_parser.add_argument("--checkout", type=Path, required=True)
        source_parser.add_argument("--sources-jar", type=Path, required=True)
        source_parser.add_argument("--commit", required=True)
        options = source_parser.parse_args(os.sys.argv[2:])
        try:
            print(json.dumps(verify_source_inputs(options.checkout, options.sources_jar,
                                                  options.commit), indent=2))
        except (ValueError, OSError, zipfile.BadZipFile) as error:
            raise SystemExit(str(error)) from error
        return
    if len(os.sys.argv) > 1 and os.sys.argv[1] == "check-run":
        check_parser = argparse.ArgumentParser(description="Check an upstream JUnit run report.")
        check_parser.add_argument("--report", type=Path, required=True)
        options = check_parser.parse_args(os.sys.argv[2:])
        try:
            validate_run_report(json.loads(options.report.read_text()))
        except (ValueError, OSError) as error:
            raise SystemExit(str(error)) from error
        print("baseline run report valid")
        return
    if len(os.sys.argv) > 1 and os.sys.argv[1] == "compare":
        compare_parser = argparse.ArgumentParser(description="Compare JVM source compatibility surfaces.")
        compare_parser.add_argument("--baseline-jar", type=Path, required=True)
        compare_parser.add_argument("--candidate", type=Path, required=True)
        compare_parser.add_argument("--only", action="append", default=[])
        options = compare_parser.parse_args(os.sys.argv[2:])
        result = compare_jars(options.baseline_jar, options.candidate,
                              set(options.only) if options.only else None)
        print(json.dumps(result, indent=2))
        if result["missing_types"] or result["signature_mismatches"]:
            raise SystemExit(1)
        return
    parser = argparse.ArgumentParser(description="Verify the pinned dyn4j baseline corpus.")
    parser.add_argument("--cache", type=Path, default=Path(".cache/baseline"))
    parser.add_argument("--inventory", type=Path, default=Path("docs/verification/baseline-inventory.json"))
    parser.add_argument("--summary", type=Path, default=Path("docs/verification/baseline-run.json"))
    parser.add_argument("--candidate", type=Path, help="compare candidate JAR public/protected signatures")
    parser.add_argument("--inventory-only", action="store_true")
    args = parser.parse_args()
    cache = args.cache.resolve()
    binary = cache / "dyn4j-6.0.0.jar"
    sources_jar = cache / "dyn4j-6.0.0-sources.jar"
    fetch(BASE + "/dyn4j-6.0.0.jar", binary, BINARY_SHA256)
    fetch(BASE + "/dyn4j-6.0.0-sources.jar", sources_jar, SOURCES_SHA256)
    source = checked_out_sources(cache)
    source_provenance = verify_source_inputs(source, sources_jar, COMMIT)
    data = inventory(source, binary, args.inventory.resolve())
    data["source_provenance"] = source_provenance
    args.inventory.resolve().write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    if args.candidate:
        comparison = compare_jars(binary, args.candidate.resolve())
        print(json.dumps(comparison, indent=2))
        if comparison["missing_types"] or comparison["signature_mismatches"]:
            raise SystemExit(1)
    if not args.inventory_only:
        summary = execute(source, binary, cache, args.summary.resolve())
        print(json.dumps(summary, indent=2))
    print(f"inventory: {args.inventory.resolve()}")


if __name__ == "__main__":
    main()
