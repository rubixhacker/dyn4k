from __future__ import annotations

import argparse
import hashlib
import gzip
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "baseline"))
import verify as oracle
import module_probe
import execution_probe
import candidate_coverage
import signature_index
import java_corpus
import build_provenance
import common_corpus_receipt
import raw_signature_audit
import portable_links
import android_java_corpus
import method_coverage
import governing_disposition
import governing_seams


MODULE_SOURCE = "src/main/java/module-info.java"
FIXTURE_SHA256 = {
    "module-info.java": "acc256154b37acb90c2abc9113404f585edec3e900697dfd4ef56267240ea0ce",
    "example/Main.java": "2cd5a3ad610ccd7e1de179eefdf69d19196391438ee423e8f3eeac6c8abf391f",
}
REQUIRED_KINDS = {"production": ("implementation",), "tests": ("java-test",),
                  "declarations": ("java-signature", "common-portable")}
MODULE_KINDS = ("module-descriptor", "named-module-consumer", "java8-classpath")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tracked_files(source: Path, prefix: str) -> list[str]:
    output = subprocess.run(["git", "-C", str(source), "ls-tree", "-r", "--name-only",
                             oracle.COMMIT, prefix], check=True, capture_output=True, text=True).stdout
    return sorted(output.splitlines())


def tracked_paths(source: Path, prefix: str) -> list[str]:
    return [path for path in tracked_files(source, prefix) if path.endswith(".java")]


def tracked_sha(source: Path, path: str) -> str:
    content = subprocess.run(["git", "-C", str(source), "show", f"{oracle.COMMIT}:{path}"],
                             check=True, capture_output=True).stdout
    return sha256(content)


def require_baseline_test_inputs(observed: object, tests: dict[str, str],
                                 resources: dict[str, str]) -> None:
    expected = tests | resources
    if not isinstance(observed, dict) or observed != expected:
        actual = observed if isinstance(observed, dict) else {}
        missing = sorted(expected.keys() - actual.keys())
        extra = sorted(actual.keys() - expected.keys())
        changed = sorted(key for key in expected.keys() & actual.keys() if expected[key] != actual[key])
        raise ValueError(f"baseline test input hashes differ: missing={missing}, extra={extra}, changed={changed}")


def declaration_inventory(signatures: dict[str, str], verbose_signatures: dict[str, str],
                          production: dict[str, str]) -> dict[str, tuple[str, str, list[str] | None]]:
    result = {}
    for name, text in sorted(signatures.items()):
        header, members = execution_probe.declarations(text, verbose_signatures[name], oracle)
        compiled = re.search(r'^Compiled from "([^"/]+\.java)"', text)
        if compiled is None:
            raise ValueError(f"source owner missing: {name}")
        package = name.rpartition(".")[0].replace(".", "/")
        source_file = f"src/main/java/{package}/{compiled.group(1)}"
        if source_file not in production:
            raise ValueError(f"source owner absent: {name}: {source_file}")
        result[f"{name}|type"] = (source_file, header, None)
        for (member, descriptor), (signature, flags) in members.items():
            key = f"{name}|{member}|{descriptor}"
            if key in result:
                raise ValueError(f"duplicate declaration: {key}")
            result[key] = (source_file, signature, flags)
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
    verbose_classes, verbose_signatures = oracle.jar_types(jar, verbose=True)
    if verbose_classes != classes or oracle.digest(jar) != oracle.BINARY_SHA256:
        raise ValueError("verbose declaration surface differs from pinned JAR")
    production = {path: tracked_sha(source, path) for path in production_paths}
    tests = {path: tracked_sha(source, path) for path in test_paths}
    resources = {path: tracked_sha(source, path) for path in tracked_files(source, "src/test/resources")}
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
    require_baseline_test_inputs(run.get("test_input_sha256"), tests, resources)
    if (run.get("commit") != oracle.COMMIT or run.get("binary_sha256") != oracle.BINARY_SHA256
            or run.get("test_files") != 199
            or saved.get("test_annotations") != 2171):
        raise ValueError("baseline run or annotation count differs from pinned test inputs")
    counts = {"textual_annotations": saved["test_annotations"],
              "actual_executed_cases": run["actual_executed_cases"], "ignored": run["ignored"]}
    return {"baseline": baseline, "production": production, "tests": tests,
            "baseline_test_counts": counts,
            "declarations": declaration_inventory(signatures, verbose_signatures, production), "module": module}


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
                          **({"flags": flags} if flags is not None else {}),
                          "candidate": None, "evidence": []}
                         for key, (source_file, signature, flags) in expected["declarations"].items()],
    }


def check_evidence(item: dict, evidence: dict, root: Path, baseline: dict,
                   source_sha256: str, reports: dict[Path, tuple[str, dict | None]],
                   ledger_data: dict | None = None, replays: dict[Path, str | None] | None = None,
                   baseline_source: Path | None = None) -> str | None:
    status = evidence.get("status")
    if status not in {"missing", "unrun", "failed", "ignored", "unapproved_exception", "passed"}:
        return "unknown evidence status"
    if status != "passed":
        return None
    if (baseline.get("binary_sha256") == oracle.BINARY_SHA256
            and (not isinstance(ledger_data, dict)
                 or not isinstance(ledger_data.get("candidate_source"), dict))):
        return "pinned candidate source provenance is missing"
    report_path = evidence.get("report")
    if not isinstance(report_path, str) or not report_path or Path(report_path).is_absolute() or ".." in Path(report_path).parts:
        return "passed evidence has no safe report path"
    report_file = root / report_path
    if not report_file.is_file():
        return "passed evidence report is missing or changed"
    if report_file not in reports:
        content = report_file.read_bytes()
        try:
            plain = gzip.decompress(content) if report_file.suffix == ".gz" else content
            reports[report_file] = (sha256(content), json.loads(plain))
        except (ValueError, OSError):
            reports[report_file] = (sha256(content), None)
    report_sha, report = reports[report_file]
    if report_sha != evidence.get("report_sha256"):
        return "passed evidence report is missing or changed"
    if not isinstance(report, dict):
        return "passed evidence report is invalid"
    if baseline.get("binary_sha256") == oracle.BINARY_SHA256 and report.get("schema_version") != 3:
        return "pinned candidate pass lacks replayable source and artifact provenance"
    candidate = item.get("candidate")
    if not isinstance(candidate, dict):
        return "passed evidence has no counterpart"
    kind = evidence.get("kind")
    target = evidence.get("target")
    if not isinstance(kind, str) or not isinstance(target, str) or not target:
        return "passed evidence kind or target is missing"
    if (report.get("schema_version") == 3 and kind == "java-signature"
            and target == "jvm" and report.get("probe") == "javap-inventory-v1"):
        if ledger_data is None or replays is None:
            return "signature index lacks ledger context"
        if report_file not in replays:
            replays[report_file] = signature_index.validate_report(
                report, ledger_data, root / candidate["artifact"], root)
        if replays[report_file]:
            return replays[report_file]
        outcome = report.get("index", {}).get("outcomes", {}).get(item["id"])
        if (not isinstance(outcome, dict) or outcome.get("passed") is not True
                or outcome.get("source_sha256") != source_sha256
                or item["id"] not in report["index"]["passed_identities"]):
            return "signature index lacks a matching passed original identity"
        return None
    if (report.get("schema_version") == 3 and kind == "java-test"
            and target == "jvm" and report.get("probe") == "unchanged-junit-xml-v1"):
        if ledger_data is None or replays is None or baseline_source is None:
            return "Java corpus receipt lacks pinned source context"
        if report_file not in replays:
            replays[report_file] = java_corpus.validate_report(
                report, ledger_data, root, baseline_source, root / candidate["artifact"])
        if replays[report_file]:
            return replays[report_file]
        if (candidate.get("identity") != item["id"]
                or report.get("input_sha256", {}).get(item["id"]) != source_sha256):
            return "Java corpus lacks matching unchanged original source identity"
        return None
    required = (report.get("schema_version") == 2
                and report.get("baseline") == baseline and report.get("candidate_identity") == candidate.get("identity")
                and report.get("kind") == kind and report.get("target") == target
                and report.get("candidate_commit") == candidate.get("commit")
                and report.get("artifact_sha256") == candidate.get("artifact_sha256")
                and report.get("source_sha256") == source_sha256
                and report.get("passed_identities") == [item["id"]])
    if not required:
        return "passed evidence report lacks matching execution identity or complete results"
    if (kind, target, report.get("probe")) != ("java-signature", "jvm", "javap-signature-v1"):
        return "passed evidence has no allowlisted executable probe for kind and target"
    if candidate.get("identity") != item["id"]:
        return "passed evidence candidate declaration identity differs"
    try:
        observed = execution_probe.signature(item, root / candidate["artifact"], oracle)
    except (OSError, ValueError, subprocess.TimeoutExpired, KeyError, TypeError) as error:
        return f"passed evidence probe failed: {error}"
    fields = ("command", "expected_cases", "actual_executed_cases", "failures", "ignored",
              "process_exit_code", "raw_stdout", "raw_stderr", "output")
    if (json.dumps(report.get("execution"), sort_keys=True) != json.dumps(observed, sort_keys=True)
            or any(type(report.get(field)) is not type(observed[field])
                   or report.get(field) != observed[field] for field in fields)
            or observed["actual_executed_cases"] != observed["expected_cases"]
            or observed["failures"] != 0 or observed["ignored"] != 0
            or observed["process_exit_code"] != 0):
        return "passed evidence differs from executed probe"
    return None


def validate_module(item: object, expected: dict, baseline: dict, root: Path,
                    candidate_revision: str | None,
                    provenance_error: str | None = None) -> tuple[list[str], list[str], set[str]]:
    invalid = []
    gaps = []
    if not isinstance(item, dict):
        return ["module: executable obligation missing"], gaps, set()
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
        return invalid + ["module: evidence list missing"], gaps, set()
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
        if status not in {"missing", "unrun", "failed", "ignored", "unapproved_exception", "passed"}:
            invalid.append(f"module: {kind}: unknown evidence status")
        elif status != "passed":
            gaps.append(f"module: {kind}: {status}")
        elif record.get("target") != "jvm":
            invalid.append(f"module: {kind}: passed evidence target is missing or unsupported")
        elif jar is None:
            invalid.append(f"module: {kind}: passed evidence has no verified candidate JAR")
        elif provenance_error:
            invalid.append(f"module: {kind}: {provenance_error}")
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
                expected_provider_sha256 = candidate["artifact_sha256"] if kind == "named-module-consumer" else None
                observed = module_probe.probe(jar, kind, paths, java8, expected_provider_sha256)
            except (OSError, ValueError) as error:
                invalid.append(f"module: {kind}: probe failed: {error}")
                continue
            if not observed["passed"] or report.get("observed") != observed:
                invalid.append(f"module: {kind}: recorded pass differs from executed probe")
            else:
                passed.add(kind)
    for kind in sorted(needed - passed):
        gaps.append(f"module: module-info.java: unrun {kind}")
    return invalid, gaps, passed


def candidate_source_binding(source: dict, requested_revision: str, root: Path) -> tuple[str, str | None]:
    if not re.fullmatch(r"[0-9a-f]{40}", requested_revision):
        return "invalid", "requested candidate revision is invalid"
    try:
        requested_tree = candidate_coverage.git(root, "rev-parse", f"{requested_revision}^{{tree}}")
    except (OSError, subprocess.CalledProcessError):
        return "invalid", "requested candidate revision cannot be verified"
    if source.get("revision") != requested_revision:
        return ("historical", "historical candidate source revision differs from requested HEAD: "
                f"recorded={source.get('revision')}, requested={requested_revision}")
    if source.get("tree") != requested_tree:
        return "invalid", "candidate source tree differs from requested HEAD tree"
    return "bound", None


def unbound_candidate_report(expected: dict, source: dict, requested_revision: str,
                             scope: str, reason: str) -> dict:
    status = "historical-unpassed" if scope == "historical" else "invalid-unpassed"
    obligations = [{"section": section, "id": key, "kind": kind,
                    "status": status, "reason": reason}
                   for section, kinds in REQUIRED_KINDS.items()
                   for key in expected[section] for kind in kinds]
    obligations.extend({"section": "module", "id": "module-info.java", "kind": kind,
                        "status": status, "reason": reason} for kind in MODULE_KINDS)
    by_kind = {}
    for item in obligations:
        bucket = by_kind.setdefault(item["kind"], {"total": 0, "passed": 0, "unpassed": 0})
        bucket["total"] += 1
        bucket["unpassed"] += 1
    return {"passed": False, "invalid": [reason], "gaps": [reason],
            "source_scope": status, "candidate_source_revision": source.get("revision"),
            "requested_candidate_revision": requested_revision,
            "governing_summary": None,
            "obligation_counts": {"total": len(obligations), "passed": 0,
                                  "unpassed": len(obligations), "by_kind": by_kind},
            "unpassed_obligations": obligations, "missing_counterparts": None,
            "counts": {**{section: len(expected[section]) for section in REQUIRED_KINDS},
                       "module": 1}}


def validate(ledger: dict, expected: dict, root: Path, candidate_revision: str | None = None,
             baseline_source: Path | None = None) -> dict:
    invalid = []
    gaps = []
    artifact_hashes = {}
    reports = {}
    replays = {}
    verified = {}
    source_revision = candidate_revision
    source_scope = "unscoped"
    projection = None
    governing_summary = None
    source = ledger.get("candidate_source")
    if candidate_revision is not None and isinstance(source, dict):
        binding, reason = candidate_source_binding(source, candidate_revision, root)
        if reason is not None:
            return unbound_candidate_report(expected, source, candidate_revision, binding, reason)
        source_scope = "bound-to-requested"
    if source is not None:
        if not isinstance(source, dict):
            invalid.append("candidate source revision record is invalid")
        else:
            source_revision = source.get("revision")
            artifact = source.get("artifact")
            if (not isinstance(source_revision, str) or not re.fullmatch(r"[0-9a-f]{40}", source_revision)
                    or not isinstance(artifact, str) or not artifact
                    or Path(artifact).is_absolute() or ".." in Path(artifact).parts):
                invalid.append("candidate source revision or artifact path is invalid")
            else:
                try:
                    projection = candidate_coverage.materialize(
                        generate(expected), root, source_revision, root / artifact)
                    projected_source = projection["candidate_source"]
                    if (any(source.get(key) != value for key, value in projected_source.items())
                            or set(source) - set(projected_source) - {"build_receipt", "build_receipt_sha256"}):
                        invalid.append("candidate source revision, tree, or artifact differs")
                except (OSError, ValueError, subprocess.CalledProcessError,
                        subprocess.TimeoutExpired) as error:
                    invalid.append(f"candidate source revision or artifact cannot be verified: {error}")
    if (ledger.get("schema_version") != 1 or ledger.get("baseline") != expected["baseline"]
            or ledger.get("baseline_test_counts") != expected.get("baseline_test_counts")):
        invalid.append("schema or pinned source/JAR identity differs")
    review_receipts = ledger.get("review_receipts", {})
    if not isinstance(review_receipts, dict) or set(review_receipts) - {
            "common_corpus", "raw_signature", "portable_links", "android_host",
            "method_coverage", "governing_seams", "governing_disposition"}:
        invalid.append("review_receipts: unknown or invalid receipt kind")
    else:
        def reviewed_file(record: dict, path_key: str, sha_key: str) -> Path:
            name = record.get(path_key)
            if (not isinstance(name, str) or not name or Path(name).is_absolute()
                    or ".." in Path(name).parts):
                raise ValueError(f"{path_key} is missing or unsafe")
            path = root / name
            if not path.is_file() or sha256(path.read_bytes()) != record.get(sha_key):
                raise ValueError(f"{path_key} is missing or changed")
            return path

        for kind, record in review_receipts.items():
            if not isinstance(record, dict):
                invalid.append(f"{kind}: review receipt is invalid")
                continue
            try:
                path = reviewed_file(record, "path", "sha256")
                if kind == "common_corpus":
                    error = common_corpus_receipt.verify(json.loads(path.read_text()), ledger, root)
                elif kind == "raw_signature":
                    signature_path = reviewed_file(record, "signature", "signature_sha256")
                    strict_path = reviewed_file(record, "strict", "strict_sha256")
                    pinned_source = baseline_source or Path(record.get("baseline_source", ""))
                    if not pinned_source.is_dir():
                        raise ValueError("baseline_source is missing")
                    error = raw_signature_audit.check(
                        json.loads(path.read_text()), ledger,
                        json.loads(gzip.decompress(signature_path.read_bytes())),
                        json.loads(strict_path.read_text()), root, pinned_source)
                elif kind == "portable_links":
                    gate_path = reviewed_file(record, "gate", "gate_sha256")
                    pinned_source = baseline_source or Path(record.get("baseline_source", ""))
                    if not pinned_source.is_dir():
                        raise ValueError("baseline_source is missing")
                    raw_links = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
                    error = portable_links.check(json.loads(raw_links), ledger,
                                                 json.loads(gate_path.read_text()),
                                                 root, pinned_source)
                elif kind == "android_host":
                    build_path = reviewed_file(record, "build", "build_sha256")
                    jvm_path = reviewed_file(record, "jvm", "jvm_sha256")
                    strict_path = reviewed_file(record, "strict", "strict_sha256")
                    pinned_source = baseline_source or Path(record.get("baseline_source", ""))
                    if not pinned_source.is_dir():
                        raise ValueError("baseline_source is missing")
                    build = json.loads(build_path.read_text())
                    strict = json.loads(strict_path.read_text())
                    error = android_java_corpus.check(
                        json.loads(path.read_text()), ledger, root, pinned_source, root,
                        build, json.loads(jvm_path.read_text()))
                    if not error:
                        dependencies = []
                        for name, checksum in strict["dependency_sha256"].items():
                            dependency = Path(name)
                            if not dependency.is_file() or candidate_coverage.digest(dependency) != checksum:
                                raise ValueError(f"strict Android dependency missing or changed: {name}")
                            dependencies.append(dependency)
                        baseline_jar = raw_signature_audit.BASELINE_JAR
                        if (not baseline_jar.is_file() or
                                candidate_coverage.digest(baseline_jar) != ledger["baseline"]["binary_sha256"]):
                            raise ValueError("pinned baseline JAR missing or changed")
                        android_jar = root / build_provenance.ANDROID_ARTIFACT
                        if oracle.compare_jars(baseline_jar, android_jar,
                                               dependencies=dependencies) != strict:
                            error = "strict Android source-visible comparison differs from replay"
                elif kind == "method_coverage":
                    corpus_path = reviewed_file(record, "corpus", "corpus_sha256")
                    pinned_source = baseline_source or Path(record.get("baseline_source", ""))
                    if not pinned_source.is_dir():
                        raise ValueError("baseline_source is missing")
                    error = method_coverage.check(json.loads(path.read_text()), ledger,
                                                  json.loads(corpus_path.read_text()),
                                                  root, pinned_source, replay=True)
                elif kind == "governing_seams":
                    error = governing_seams.check(json.loads(path.read_text()), ledger,
                                                  root, replay=True)
                elif kind == "governing_disposition":
                    pinned_source = baseline_source or Path(record.get("baseline_source", ""))
                    if not pinned_source.is_dir():
                        raise ValueError("baseline_source is missing")
                    raw = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
                    governing = json.loads(raw)
                    error = governing_disposition.check(governing, ledger, root, pinned_source)
                    if not error:
                        governing_summary = {
                            "source_implementation": governing["source_implementation"],
                            "source_compatibility": governing["source_compatibility"],
                            "behavior_coverage": governing["behavior_coverage"],
                            "raw_diagnostics": governing["raw_diagnostics"],
                            "target_qualification": governing["target_qualification"],
                        }
                else:
                    continue
                if error:
                    invalid.append(f"{kind}: {error}")
            except (OSError, ValueError, KeyError, TypeError) as error:
                invalid.append(f"{kind}: review receipt replay failed: {error}")
    for section in ("production", "tests", "declarations"):
        entries = ledger.get(section)
        if not isinstance(entries, list):
            invalid.append(f"{section}: entries missing")
            continue
        observed = {}
        mapped = set()
        groups = {}
        if section == "production" and source is not None:
            for row in entries:
                if isinstance(row, dict) and isinstance(row.get("candidate"), dict):
                    identity = row["candidate"].get("identity")
                    if isinstance(identity, str):
                        groups.setdefault(identity, set()).add(row.get("id"))
        projected = ({row["id"]: row for row in projection[section]}
                     if projection is not None else {})
        for item in entries:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                invalid.append(f"{section}: invalid entry")
                continue
            key = item["id"]
            if projection is not None:
                approved = projected.get(key)
                if approved is None or any(item.get(field) != approved.get(field)
                                           for field in ("candidate", "disposition", "reason")):
                    invalid.append(f"{section}: {key}: changed source mapping or review disposition")
            if key in observed:
                invalid.append(f"{section}: duplicate {key}")
            observed[key] = item
            candidate = item.get("candidate")
            if candidate is None:
                gaps.append(f"{section}: {key}: missing counterpart")
            elif not isinstance(candidate, dict) or not isinstance(candidate.get("identity"), str) or not candidate["identity"]:
                invalid.append(f"{section}: {key}: invalid candidate identity")
            else:
                if candidate["identity"] in mapped and not (section == "production" and source is not None):
                    invalid.append(f"{section}: duplicate candidate mapping {candidate['identity']}")
                mapped.add(candidate["identity"])
                if section == "production" and source is not None:
                    if candidate.get("mapped_baseline_ids") != sorted(groups.get(candidate["identity"], set())):
                        invalid.append(f"{section}: {key}: incomplete or ambiguous mapping group")
                if not isinstance(candidate.get("commit"), str) or not re.fullmatch(r"[0-9a-f]{40}", candidate["commit"]):
                    invalid.append(f"{section}: {key}: invalid candidate commit")
                elif source_revision and candidate["commit"] != source_revision:
                    invalid.append(f"{section}: {key}: stale candidate commit")
                if not isinstance(candidate.get("artifact_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", candidate["artifact_sha256"]):
                    invalid.append(f"{section}: {key}: invalid candidate artifact SHA-256")
                elif candidate["artifact_sha256"] == oracle.BINARY_SHA256:
                    invalid.append(f"{section}: {key}: pinned baseline JAR cannot be a candidate artifact")
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
                error = check_evidence(item, record, root, expected["baseline"], source_sha,
                                       reports, ledger, replays, baseline_source)
                if error:
                    invalid.append(f"{section}: {key}: {error}")
                elif record["status"] == "passed":
                    passing.add(record.get("kind"))
                else:
                    reason = record.get("reason") or item.get("reason") or "no executable result"
                    gaps.append(f"{section}: {key}: {record['status']}: {reason}")
            for kind in sorted(needed - passing):
                gaps.append(f"{section}: {key}: unrun {kind}: {item.get('reason') or 'no executable result'}")
            verified[(section, key)] = passing
        expected_keys = set(expected[section])
        for key in sorted(expected_keys - set(observed)):
            invalid.append(f"{section}: omitted {key}")
        for key in sorted(set(observed) - expected_keys):
            invalid.append(f"{section}: unexpected {key}")
        for key in sorted(expected_keys & set(observed)):
            item = observed[key]
            wanted = expected[section][key]
            if section == "declarations":
                if (item.get("source_file"), item.get("signature"), item.get("flags")) != wanted:
                    invalid.append(f"{section}: changed {key}")
            elif item.get("sha256") != wanted:
                invalid.append(f"{section}: changed source SHA-256 {key}")
            if section != "declarations":
                prefix = "src/main/java/" if section == "production" else "src/test/java/"
                owner = key.removeprefix(prefix).removesuffix(".java").replace("/", ".")
                if item.get("owner_type") != owner:
                    invalid.append(f"{section}: changed owner {key}")
    pinned_baseline = ledger.get("baseline")
    provenance_error = ("pinned candidate source provenance is missing"
                        if isinstance(pinned_baseline, dict)
                        and pinned_baseline.get("binary_sha256") == oracle.BINARY_SHA256
                        and not isinstance(source, dict) else None)
    if source is not None and isinstance(source, dict):
        receipt_name = source.get("build_receipt")
        if (not isinstance(receipt_name, str) or not receipt_name
                or Path(receipt_name).is_absolute() or ".." in Path(receipt_name).parts):
            provenance_error = "candidate source build receipt path is missing or unsafe"
        else:
            receipt_path = root / receipt_name
            if not receipt_path.is_file() or sha256(receipt_path.read_bytes()) != source.get("build_receipt_sha256"):
                provenance_error = "candidate source build receipt is missing or changed"
            else:
                try:
                    provenance_error = build_provenance.verify(
                        json.loads(receipt_path.read_text()), root, root / source["artifact"], source)
                except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
                    provenance_error = f"candidate source build receipt failed: {error}"
    if projection is not None and any(ledger.get("module", {}).get(field) != projection["module"].get(field)
                                      for field in ("candidate", "reason")):
        invalid.append("module: changed source mapping or review disposition")
    module_invalid, module_gaps, module_passed = validate_module(
        ledger.get("module"), expected["module"], expected["baseline"], root,
        source_revision, provenance_error)
    invalid.extend(module_invalid)
    gaps.extend(module_gaps)
    obligation_details = []
    for section, kinds in REQUIRED_KINDS.items():
        raw_entries = ledger.get(section)
        entries = {item.get("id"): item for item in (raw_entries if isinstance(raw_entries, list) else [])
                   if isinstance(item, dict)}
        for key in expected[section]:
            item = entries.get(key, {})
            records = {record.get("kind"): record for record in (item.get("evidence") or [])
                       if isinstance(record, dict)}
            for kind in kinds:
                if kind in verified.get((section, key), set()):
                    status, reason = "passed", None
                else:
                    record = records.get(kind, {})
                    status = ("missing" if item.get("candidate") is None else
                              "invalid" if record.get("status") == "passed" else
                              record.get("status", "unrun"))
                    reason = record.get("reason") or item.get("reason") or "no executable result"
                obligation_details.append({"section": section, "id": key, "kind": kind,
                                           "status": status, "reason": reason})
    for kind in MODULE_KINDS:
        module = ledger.get("module")
        module = module if isinstance(module, dict) else {}
        records = {record.get("kind"): record for record in (module.get("evidence") or [])
                   if isinstance(record, dict)}
        if kind in module_passed:
            status, reason = "passed", None
        else:
            record = records.get(kind, {})
            status = ("missing" if module.get("candidate") is None else
                      "invalid" if record.get("status") == "passed" else
                      record.get("status", "unrun"))
            reason = record.get("reason") or module.get("reason") or "no executable result"
        obligation_details.append({"section": "module", "id": "module-info.java",
                                   "kind": kind, "status": status, "reason": reason})
    obligation_counts = {"total": len(obligation_details),
                         "passed": sum(item["status"] == "passed" for item in obligation_details),
                         "unpassed": sum(item["status"] != "passed" for item in obligation_details)}
    by_kind = {}
    for item in obligation_details:
        bucket = by_kind.setdefault(item["kind"], {"total": 0, "passed": 0, "unpassed": 0})
        bucket["total"] += 1
        bucket["passed" if item["status"] == "passed" else "unpassed"] += 1
    obligation_counts["by_kind"] = by_kind
    return {"passed": not invalid and not gaps, "invalid": invalid, "gaps": gaps,
            "candidate_source_revision": source_revision,
            "requested_candidate_revision": candidate_revision, "source_scope": source_scope,
            "governing_summary": governing_summary,
            "obligation_counts": obligation_counts,
            "unpassed_obligations": [item for item in obligation_details if item["status"] != "passed"],
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
    report = validate(json.loads(args.ledger.read_text()), expected, Path.cwd(),
                      candidate_revision, args.source)
    report["candidate_revision"] = candidate_revision
    if args.report:
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": report["passed"], "source_scope": report["source_scope"],
                      "candidate_source_revision": report["candidate_source_revision"],
                      "requested_candidate_revision": candidate_revision,
                      "invalid": len(report["invalid"]),
                      "gaps": len(report["gaps"]), "missing_counterparts": report["missing_counterparts"],
                      "counts": report["counts"]}, indent=2))
    raise SystemExit(2 if report["invalid"] else 0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
