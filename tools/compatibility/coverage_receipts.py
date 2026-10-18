from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import candidate_coverage
import java_corpus
import signature_index
import ledger as validator


def attach(original: dict, root: Path, revision: str, jar: Path,
           signature_path: Path, corpus_path: Path, baseline_source: Path,
           module_reports: dict[str, Path] | None = None) -> dict:
    if any(item.get("candidate") is not None or item.get("evidence")
           for section in ("production", "tests", "declarations") for item in original[section]):
        raise ValueError("input ledger already contains candidate coverage")
    ledger = candidate_coverage.materialize(original, root, revision, jar)
    signature = json.loads(gzip.decompress(signature_path.read_bytes()))
    error = signature_index.validate_report(signature, ledger, jar, root)
    if error:
        raise ValueError(error)
    signature_index.attach_report(ledger, signature, signature_path, root)
    ledger["candidate_source"]["build_receipt"] = signature["build_receipt"]
    ledger["candidate_source"]["build_receipt_sha256"] = signature["build_receipt_sha256"]
    corpus = json.loads(corpus_path.read_text())
    error = java_corpus.validate_report(corpus, ledger, root, baseline_source, jar)
    if error:
        raise ValueError(error)
    name = corpus_path.resolve().relative_to(root.resolve()).as_posix()
    checksum = candidate_coverage.digest(corpus_path)
    for item in ledger["tests"]:
        item["evidence"] = [{"kind": "java-test", "status": "passed", "target": "jvm",
                             "report": name, "report_sha256": checksum}]
    if module_reports:
        needed = {"module-descriptor", "named-module-consumer", "java8-classpath"}
        if set(module_reports) != needed:
            raise ValueError("named-module report set is incomplete")
        ledger["module"]["evidence"] = [
            {"kind": kind, "status": "passed", "target": "jvm",
             "report": path.resolve().relative_to(root.resolve()).as_posix(),
             "report_sha256": candidate_coverage.digest(path)}
            for kind, path in sorted(module_reports.items())]
        module_errors, module_gaps, _ = validator.validate_module(
            ledger["module"], {key: value for key, value in original["module"].items()
                               if key not in {"candidate", "evidence"}},
            original["baseline"], root, revision)
        if module_errors or module_gaps:
            raise ValueError(f"module receipts fail replay: invalid={module_errors}, gaps={module_gaps}")
    return ledger


def main() -> None:
    parser = argparse.ArgumentParser(description="Attach replayed candidate coverage to the pinned ledger.")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--revision", required=True)
    parser.add_argument("--jar", type=Path, required=True)
    parser.add_argument("--signature-report", type=Path, required=True)
    parser.add_argument("--corpus-report", type=Path, required=True)
    parser.add_argument("--baseline-source", type=Path, required=True)
    parser.add_argument("--module-report", action="append", default=[],
                        help="KIND=PATH for each of the three named-module receipts")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = json.loads(args.ledger.read_text())
    module_reports = {}
    for value in args.module_report:
        kind, separator, name = value.partition("=")
        if not separator or kind in module_reports:
            parser.error("invalid or duplicate module report argument")
        module_reports[kind] = Path(name)
    result = attach(original, args.root, args.revision, args.jar,
                    args.signature_report, args.corpus_report, args.baseline_source,
                    module_reports or None)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"production_mapped": sum(item["candidate"] is not None for item in result["production"]),
                      "tests_passed": sum(bool(item["evidence"]) for item in result["tests"]),
                      "declarations_mapped": sum(item["candidate"] is not None for item in result["declarations"]),
                      "signatures_passed": sum(any(record["status"] == "passed" for record in item["evidence"])
                                               for item in result["declarations"]),
                      "module_passed": sum(record["status"] == "passed"
                                           for record in result["module"]["evidence"])}, sort_keys=True))


if __name__ == "__main__":
    main()
