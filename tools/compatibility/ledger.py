from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "baseline"))
import verify as oracle
import module_probe


MODULE_SOURCE = "src/main/java/module-info.java"
FIXTURE_SHA256 = {
    "module-info.java": "acc256154b37acb90c2abc9113404f585edec3e900697dfd4ef56267240ea0ce",
    "example/Main.java": "2cd5a3ad610ccd7e1de179eefdf69d19196391438ee423e8f3eeac6c8abf391f",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tracked_paths(source: Path, prefix: str) -> list[str]:
    output = subprocess.run(["git", "-C", str(source), "ls-tree", "-r", "--name-only",
                             oracle.COMMIT, prefix], check=True, capture_output=True, text=True).stdout
    return sorted(path for path in output.splitlines() if path.endswith(".java"))


def tracked_sha(source: Path, path: str) -> str:
    content = subprocess.run(["git", "-C", str(source), "show", f"{oracle.COMMIT}:{path}"],
                             check=True, capture_output=True).stdout
    return sha256(content)


def declaration_inventory(signatures: dict[str, str], production: dict[str, str]) -> dict[str, tuple[str, str]]:
    result = {}
    for name, text in sorted(signatures.items()):
        header = next((line.strip() for line in text.splitlines() if line.strip().endswith("{")), None)
        if header is None:
            raise ValueError(f"type header missing: {name}")
        compiled = re.search(r'^Compiled from "([^"/]+\.java)"', text)
        if compiled is None:
            raise ValueError(f"source owner missing: {name}")
        package = name.rpartition(".")[0].replace(".", "/")
        source_file = f"src/main/java/{package}/{compiled.group(1)}"
        if source_file not in production:
            raise ValueError(f"source owner absent: {name}: {source_file}")
        result[f"{name}|type"] = (source_file, header)
        api = oracle.surface(text)
        if api is None:
            continue
        for (member, parameters), signature in api[1].items():
            key = f"{name}|{member}|{parameters}"
            if key in result:
                raise ValueError(f"duplicate declaration: {key}")
            result[key] = (source_file, signature)
    return result


def reference(source: Path, jar: Path, sources_jar: Path, inventory: Path,
              baseline_run: Path) -> dict:
    if oracle.digest(jar) != oracle.BINARY_SHA256:
        raise ValueError("baseline JAR SHA-256 differs from the pin")
    if oracle.digest(sources_jar) != oracle.SOURCES_SHA256:
        raise ValueError("baseline source JAR SHA-256 differs from the pin")
    oracle.verify_source_inputs(source, sources_jar, oracle.COMMIT)
    saved = json.loads(inventory.read_text())
    production_paths = tracked_paths(source, "src/main/java")
    test_paths = tracked_paths(source, "src/test/java")
    if len(production_paths) != 268 or len(test_paths) != 199:
        raise ValueError("pinned source file counts differ")
    classes, signatures = oracle.jar_types(jar)
    baseline = {"commit": oracle.COMMIT, "binary_sha256": oracle.BINARY_SHA256,
                "sources_sha256": oracle.SOURCES_SHA256}
    if (any(saved["baseline"].get(key) != value for key, value in baseline.items())
            or saved["production_java_files"] != production_paths
            or saved["test_java_files"] != test_paths
            or saved["types"] != classes
            or saved["public_protected_jvm_signatures"] != signatures):
        raise ValueError("saved baseline inventory differs from pinned source or JAR")
    production = {path: tracked_sha(source, path) for path in production_paths}
    tests = {path: tracked_sha(source, path) for path in test_paths}
    module_source = (source / MODULE_SOURCE).read_text()
    module_name = re.search(r"\bmodule\s+([A-Za-z0-9_.]+)\s*\{", module_source)
    module_exports = sorted(re.findall(r"\bexports\s+([A-Za-z0-9_.]+)\s*;", module_source))
    fixture_sha = {path: sha256((module_probe.FIXTURE / path).read_bytes()) for path in FIXTURE_SHA256}
    if (MODULE_SOURCE not in production or module_name is None
            or module_name.group(1) != module_probe.MODULE_NAME
            or set(module_exports) != module_probe.EXPORTS or len(module_exports) != 17
            or fixture_sha != FIXTURE_SHA256 or not module_probe.descriptor(jar)["passed"]):
        raise ValueError("pinned module descriptor or unchanged consumer fixture differs")
    module = {"id": "module-info.java", "source_file": MODULE_SOURCE,
              "sha256": production[MODULE_SOURCE], "name": module_name.group(1),
              "exports": module_exports, "fixture_sha256": fixture_sha}
    run = json.loads(baseline_run.read_text())
    oracle.validate_run_report(run)
    if (run.get("commit") != oracle.COMMIT or run.get("binary_sha256") != oracle.BINARY_SHA256
            or run.get("test_files") != 199 or run.get("test_input_sha256", {}).items() < tests.items()
            or saved.get("test_annotations") != 2171):
        raise ValueError("baseline run or annotation count differs from pinned test inputs")
    counts = {"textual_annotations": saved["test_annotations"],
              "actual_executed_cases": run["actual_executed_cases"], "ignored": run["ignored"]}
    return {"baseline": baseline, "production": production, "tests": tests,
            "baseline_test_counts": counts,
            "declarations": declaration_inventory(signatures, production), "module": module}


def generate(expected: dict) -> dict:
    return {
        "schema_version": 1, "baseline": expected["baseline"],
        "baseline_test_counts": expected.get("baseline_test_counts"),
        "module": {**expected["module"], "candidate": None, "evidence": []},
        "production": [{"id": path, "sha256": digest,
                        "owner_type": path.removeprefix("src/main/java/").removesuffix(".java").replace("/", "."),
                        "candidate": None, "evidence": []}
                       for path, digest in expected["production"].items()],
        "tests": [{"id": path, "sha256": digest,
                   "owner_type": path.removeprefix("src/test/java/").removesuffix(".java").replace("/", "."),
                   "candidate": None, "evidence": []}
                  for path, digest in expected["tests"].items()],
        "declarations": [{"id": key, "source_file": source_file, "signature": signature,
                          "candidate": None, "evidence": []}
                         for key, (source_file, signature) in expected["declarations"].items()],
    }


def check_evidence(item: dict, evidence: dict, root: Path, baseline: dict,
                   source_sha256: str, reports: dict[Path, tuple[str, dict | None]]) -> str | None:
    status = evidence.get("status")
    if status not in {"missing", "unrun", "ignored", "unapproved_exception", "passed"}:
        return "unknown evidence status"
    if status != "passed":
        return None
    report_path = evidence.get("report")
    if not isinstance(report_path, str) or not report_path or Path(report_path).is_absolute() or ".." in Path(report_path).parts:
        return "passed evidence has no safe report path"
    report_file = root / report_path
    if not report_file.is_file():
        return "passed evidence report is missing or changed"
    if report_file not in reports:
        content = report_file.read_bytes()
        try:
            reports[report_file] = (sha256(content), json.loads(content))
        except ValueError:
            reports[report_file] = (sha256(content), None)
    report_sha, report = reports[report_file]
    if report_sha != evidence.get("report_sha256"):
        return "passed evidence report is missing or changed"
    if not isinstance(report, dict):
        return "passed evidence report is invalid"
    candidate = item.get("candidate")
    if not isinstance(candidate, dict):
        return "passed evidence has no counterpart"
    required = (report.get("baseline") == baseline and report.get("candidate_identity") == candidate.get("identity")
                and report.get("candidate_commit") == candidate.get("commit")
                and report.get("artifact_sha256") == candidate.get("artifact_sha256")
                and report.get("source_sha256") == source_sha256
                and isinstance(report.get("passed_identities"), list)
                and item["id"] in report["passed_identities"]
                and isinstance(report.get("command"), list) and bool(report["command"])
                and all(isinstance(part, str) and part for part in report["command"])
                and type(report.get("expected_cases")) is int and report["expected_cases"] > 0
                and type(report.get("actual_executed_cases")) is int
                and report["actual_executed_cases"] == report["expected_cases"]
                and type(report.get("failures")) is int and report["failures"] == 0
                and type(report.get("ignored")) is int and report["ignored"] == 0
                and type(report.get("process_exit_code")) is int and report["process_exit_code"] == 0
                and isinstance(report.get("output"), str)
                and oracle.result_field(report["output"], "ACTUAL_TESTS") == report["actual_executed_cases"]
                and oracle.result_field(report["output"], "FAILURES") == 0
                and oracle.result_field(report["output"], "IGNORED") == 0)
    if not required:
        return "passed evidence report lacks matching execution identity or complete results"
    return None


def validate_module(item: object, expected: dict, baseline: dict, root: Path,
                    candidate_revision: str | None) -> tuple[list[str], list[str]]:
    invalid = []
    gaps = []
    if not isinstance(item, dict):
        return ["module: executable obligation missing"], gaps
    for field, value in expected.items():
        if item.get(field) != value:
            invalid.append(f"module: changed {field}")
    candidate = item.get("candidate")
    jar = None
    if candidate is None:
        gaps.append("module: module-info.java: missing counterpart")
    elif not isinstance(candidate, dict):
        invalid.append("module: invalid candidate mapping")
    else:
        artifact = candidate.get("artifact")
        if (candidate.get("identity") != module_probe.MODULE_NAME
                or not isinstance(candidate.get("commit"), str)
                or not re.fullmatch(r"[0-9a-f]{40}", candidate["commit"])
                or candidate_revision and candidate["commit"] != candidate_revision
                or not isinstance(artifact, str) or not artifact or Path(artifact).is_absolute()
                or ".." in Path(artifact).parts):
            invalid.append("module: invalid or stale candidate mapping")
        else:
            jar = root / artifact
            if (not jar.is_file() or not re.fullmatch(r"[0-9a-f]{64}", str(candidate.get("artifact_sha256")))
                    or sha256(jar.read_bytes()) != candidate["artifact_sha256"]
                    or candidate["artifact_sha256"] == oracle.BINARY_SHA256):
                invalid.append("module: candidate artifact missing, changed, or baseline JAR")
                jar = None
    evidence = item.get("evidence")
    if not isinstance(evidence, list):
        return invalid + ["module: evidence list missing"], gaps
    needed = {"module-descriptor", "named-module-consumer", "java8-classpath"}
    passed = set()
    seen = set()
    for record in evidence:
        if not isinstance(record, dict) or record.get("kind") not in needed:
            invalid.append("module: unknown evidence kind")
            continue
        kind = record["kind"]
        if kind in seen:
            invalid.append(f"module: duplicate {kind} evidence")
            continue
        seen.add(kind)
        status = record.get("status")
        if status not in {"missing", "unrun", "ignored", "unapproved_exception", "passed"}:
            invalid.append(f"module: {kind}: unknown evidence status")
        elif status != "passed":
            gaps.append(f"module: {kind}: {status}")
        elif jar is None:
            invalid.append(f"module: {kind}: passed evidence has no verified candidate JAR")
        else:
            report_path = record.get("report")
            if (not isinstance(report_path, str) or not report_path or Path(report_path).is_absolute()
                    or ".." in Path(report_path).parts):
                invalid.append(f"module: {kind}: report path missing or unsafe")
                continue
            report_file = root / report_path
            if not report_file.is_file() or sha256(report_file.read_bytes()) != record.get("report_sha256"):
                invalid.append(f"module: {kind}: report missing or changed")
                continue
            try:
                report = json.loads(report_file.read_text())
            except ValueError:
                invalid.append(f"module: {kind}: report is invalid JSON")
                continue
            if not isinstance(report, dict) or any((
                    report.get("schema_version") != 1,
                    report.get("kind") != kind,
                    report.get("baseline") != baseline,
                    report.get("candidate_identity") != module_probe.MODULE_NAME,
                    report.get("candidate_commit") != candidate["commit"],
                    report.get("artifact_sha256") != candidate["artifact_sha256"],
                    report.get("source_sha256") != expected["sha256"],
                    report.get("fixture_sha256") != expected["fixture_sha256"],
            )):
                invalid.append(f"module: {kind}: report identity differs")
                continue
            dependencies = report.get("dependencies")
            if not isinstance(dependencies, list):
                invalid.append(f"module: {kind}: dependency list missing")
                continue
            paths = []
            for dependency in dependencies:
                if not isinstance(dependency, dict):
                    invalid.append(f"module: {kind}: invalid dependency")
                    continue
                name = dependency.get("path")
                if (not isinstance(name, str) or not name or Path(name).is_absolute()
                        or ".." in Path(name).parts):
                    invalid.append(f"module: {kind}: unsafe dependency path")
                    continue
                path = root / name
                if (not path.is_file() or path.suffix != ".jar"
                        or sha256(path.read_bytes()) != dependency.get("sha256")
                        or dependency.get("sha256") == oracle.BINARY_SHA256):
                    invalid.append(f"module: {kind}: dependency missing, changed, or baseline JAR")
                    continue
                paths.append(path)
            if len(paths) != len(dependencies):
                continue
            java8 = None
            if kind == "java8-classpath":
                java8_name = report.get("java8_java")
                if not isinstance(java8_name, str) or not java8_name:
                    invalid.append("module: Java 8 executable path missing")
                    continue
                java8 = Path(java8_name)
                if not java8.is_file() or sha256(java8.read_bytes()) != report.get("java8_java_sha256"):
                    invalid.append("module: Java 8 executable missing or changed")
                    continue
            try:
                observed = module_probe.probe(jar, kind, paths, java8)
            except (OSError, ValueError) as error:
                invalid.append(f"module: {kind}: probe failed: {error}")
                continue
            if not observed["passed"] or report.get("observed") != observed:
                invalid.append(f"module: {kind}: recorded pass differs from executed probe")
            else:
                passed.add(kind)
    for kind in sorted(needed - passed):
        gaps.append(f"module: module-info.java: unrun {kind}")
    return invalid, gaps


def validate(ledger: dict, expected: dict, root: Path, candidate_revision: str | None = None) -> dict:
    invalid = []
    gaps = []
    artifact_hashes = {}
    reports = {}
    if (ledger.get("schema_version") != 1 or ledger.get("baseline") != expected["baseline"]
            or ledger.get("baseline_test_counts") != expected.get("baseline_test_counts")):
        invalid.append("schema or pinned source/JAR identity differs")
    for section in ("production", "tests", "declarations"):
        entries = ledger.get(section)
        if not isinstance(entries, list):
            invalid.append(f"{section}: entries missing")
            continue
        observed = {}
        mapped = set()
        for item in entries:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                invalid.append(f"{section}: invalid entry")
                continue
            key = item["id"]
            if key in observed:
                invalid.append(f"{section}: duplicate {key}")
            observed[key] = item
            candidate = item.get("candidate")
            if candidate is None:
                gaps.append(f"{section}: {key}: missing counterpart")
            elif not isinstance(candidate, dict) or not isinstance(candidate.get("identity"), str) or not candidate["identity"]:
                invalid.append(f"{section}: {key}: invalid candidate identity")
            else:
                if candidate["identity"] in mapped:
                    invalid.append(f"{section}: duplicate candidate mapping {candidate['identity']}")
                mapped.add(candidate["identity"])
                if not isinstance(candidate.get("commit"), str) or not re.fullmatch(r"[0-9a-f]{40}", candidate["commit"]):
                    invalid.append(f"{section}: {key}: invalid candidate commit")
                elif candidate_revision and candidate["commit"] != candidate_revision:
                    invalid.append(f"{section}: {key}: stale candidate commit")
                if not isinstance(candidate.get("artifact_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", candidate["artifact_sha256"]):
                    invalid.append(f"{section}: {key}: invalid candidate artifact SHA-256")
                artifact = candidate.get("artifact")
                if (not isinstance(artifact, str) or not artifact or Path(artifact).is_absolute()
                        or ".." in Path(artifact).parts):
                    invalid.append(f"{section}: {key}: invalid candidate artifact path")
                else:
                    artifact_file = root / artifact
                    if artifact_file not in artifact_hashes:
                        artifact_hashes[artifact_file] = sha256(artifact_file.read_bytes()) if artifact_file.is_file() else None
                    if artifact_hashes[artifact_file] != candidate.get("artifact_sha256"):
                        invalid.append(f"{section}: {key}: candidate artifact is missing or changed")
            evidence = item.get("evidence")
            if not isinstance(evidence, list):
                invalid.append(f"{section}: {key}: evidence list missing")
                continue
            passing = set()
            needed = {"java-signature", "common-portable"} if section == "declarations" else (
                {"java-test"} if section == "tests" else {"implementation"})
            for record in evidence:
                if not isinstance(record, dict):
                    invalid.append(f"{section}: {key}: invalid evidence")
                    continue
                if record.get("kind") not in needed:
                    invalid.append(f"{section}: {key}: unknown evidence kind")
                    continue
                source_key = item["source_file"] if section == "declarations" else key
                source_sha = (expected["tests"] if section == "tests" else expected["production"]).get(source_key, "")
                error = check_evidence(item, record, root, expected["baseline"], source_sha, reports)
                if error:
                    invalid.append(f"{section}: {key}: {error}")
                elif record["status"] == "passed":
                    passing.add(record.get("kind"))
                else:
                    gaps.append(f"{section}: {key}: {record['status']}")
            for kind in sorted(needed - passing):
                gaps.append(f"{section}: {key}: unrun {kind}")
        expected_keys = set(expected[section])
        for key in sorted(expected_keys - set(observed)):
            invalid.append(f"{section}: omitted {key}")
        for key in sorted(set(observed) - expected_keys):
            invalid.append(f"{section}: unexpected {key}")
        for key in sorted(expected_keys & set(observed)):
            item = observed[key]
            wanted = expected[section][key]
            if section == "declarations":
                if (item.get("source_file"), item.get("signature")) != wanted:
                    invalid.append(f"{section}: changed {key}")
            elif item.get("sha256") != wanted:
                invalid.append(f"{section}: changed source SHA-256 {key}")
            if section != "declarations":
                prefix = "src/main/java/" if section == "production" else "src/test/java/"
                owner = key.removeprefix(prefix).removesuffix(".java").replace("/", ".")
                if item.get("owner_type") != owner:
                    invalid.append(f"{section}: changed owner {key}")
    module_invalid, module_gaps = validate_module(ledger.get("module"), expected["module"],
                                                   expected["baseline"], root, candidate_revision)
    invalid.extend(module_invalid)
    gaps.extend(module_gaps)
    return {"passed": not invalid and not gaps, "invalid": invalid, "gaps": gaps,
            "missing_counterparts": sum("missing counterpart" in gap for gap in gaps),
            "counts": {**{name: len(expected[name]) for name in ("production", "tests", "declarations")},
                       "module": 1}}


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the pinned declaration and test ledger.")
    parser.add_argument("action", choices=("generate", "validate"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--jar", type=Path, required=True)
    parser.add_argument("--sources-jar", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, default=Path("docs/verification/baseline-inventory.json"))
    parser.add_argument("--baseline-run", type=Path, default=Path("docs/verification/baseline-run.json"))
    parser.add_argument("--ledger", type=Path, default=Path("tools/compatibility/declaration-ledger.json"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    expected = reference(args.source, args.jar, args.sources_jar, args.inventory, args.baseline_run)
    if args.action == "generate":
        if args.ledger.exists():
            parser.error("ledger exists; generation cannot overwrite candidate mappings or evidence")
        args.ledger.write_text(json.dumps(generate(expected), indent=2, sort_keys=True) + "\n")
        return
    candidate_revision = subprocess.run(["git", "rev-parse", "HEAD"], check=True,
                                        capture_output=True, text=True).stdout.strip()
    report = validate(json.loads(args.ledger.read_text()), expected, Path.cwd(), candidate_revision)
    report["candidate_revision"] = candidate_revision
    if args.report:
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": report["passed"], "invalid": len(report["invalid"]),
                      "gaps": len(report["gaps"]), "missing_counterparts": report["missing_counterparts"],
                      "counts": report["counts"]}, indent=2))
    raise SystemExit(2 if report["invalid"] else 0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
