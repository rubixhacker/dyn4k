from __future__ import annotations

import argparse
import copy
import json
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import build_provenance
import java_corpus
from candidate_coverage import digest

ROOT = Path(__file__).resolve().parents[2]


def check(report: dict, ledger: dict, root: Path, upstream: Path, origin: Path,
          build_receipt: dict, jvm_report: dict) -> str | None:
    try:
        source = ledger["candidate_source"]
        artifact = origin / build_provenance.ANDROID_ARTIFACT
        if any((report.get("schema_version") != 3,
                report.get("kind") != "java-test",
                report.get("target") != "android-host",
                report.get("passed") is not True,
                report.get("baseline") != ledger["baseline"],
                report.get("candidate_commit") != source["revision"],
                report.get("source_tree") != source["tree"],
                report.get("artifact_sha256") != build_receipt["artifact_sha256"],
                report.get("input_sha256") != java_corpus.checked_inputs(ledger, upstream),
                report.get("harness_sha256") != jvm_report["harness_sha256"],
                report.get("dependencies") != jvm_report["dependencies"],
                report.get("tools") != jvm_report["tools"],
                report.get("normalized_case_ids") != jvm_report["normalized_case_ids"],
                report.get("actual_executed_cases_per_lane") != 2385)):
            return "Android Java corpus identity, source, or case index differs"
        receipt_name = report.get("build_receipt")
        if (not isinstance(receipt_name, str) or not receipt_name
                or Path(receipt_name).is_absolute() or ".." in Path(receipt_name).parts
                or digest(root / receipt_name) != report.get("build_receipt_sha256")):
            return "Android Java corpus build receipt missing or changed"
        android_source = {"revision": source["revision"], "tree": source["tree"],
                          "artifact": build_provenance.ANDROID_ARTIFACT,
                          "artifact_sha256": build_receipt["artifact_sha256"]}
        error = build_provenance.verify_variant(build_receipt, origin, artifact,
                                                android_source, "android")
        if error:
            return error
        xml_name = report.get("xml_root")
        if (not isinstance(xml_name, str) or not xml_name
                or Path(xml_name).is_absolute() or ".." in Path(xml_name).parts):
            return "Android Java corpus XML root is unsafe"
        xml_root = root / xml_name
        expected = {tuple(row) for row in jvm_report["normalized_case_ids"]}
        for provider in ("baseline", "candidate"):
            for compiler in (8, 21):
                for runtime in (8, 21):
                    lane = f"{provider}-javac{compiler}-java{runtime}"
                    xml = xml_root / f"{lane}.xml"
                    entry = report["lanes"][lane]
                    if (entry.get("status") != "passed" or not xml.is_file()
                            or entry.get("xml_sha256") != digest(xml)):
                        return f"Android Java corpus lane missing or changed: {lane}"
                    observed = java_corpus.normalized_cases(java_corpus.read_xml(xml, 2385))
                    if set(observed) != expected or any(count != 1 for count in observed.values()):
                        return f"Android Java case identity differs: {lane}"
        if digest(artifact) != build_receipt["artifact_sha256"]:
            return "Android candidate artifact changed after corpus execution"
        candidate_ledger = copy.deepcopy(ledger)
        candidate_ledger["candidate_source"].update(android_source)
        deps = {key: Path(value["path"]) for key, value in jvm_report["dependencies"].items()}
        jdks = {int(key): Path(value["java"]["path"]).parent.parent
                for key, value in jvm_report["tools"].items()}
        with tempfile.TemporaryDirectory(prefix="dyn4k-android-java-replay-") as directory:
            observed = java_corpus.capture(candidate_ledger, origin, upstream, artifact,
                                           deps, jdks, Path(directory) / "cases")
        if (not observed["passed"]
                or observed["normalized_case_ids"] != report["normalized_case_ids"]):
            return "Android Java corpus differs from executed source replay"
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as error:
        return f"Android Java corpus replay failed: {error}"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run pinned unchanged Java cases against Android host classes.")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--origin", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--jvm-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Android Java corpus output exists")
    ledger = json.loads(args.ledger.read_text())
    build = json.loads(args.build_receipt.read_text())
    artifact = args.origin / build_provenance.ANDROID_ARTIFACT
    source = {"revision": ledger["candidate_source"]["revision"],
              "tree": ledger["candidate_source"]["tree"],
              "artifact": build_provenance.ANDROID_ARTIFACT,
              "artifact_sha256": build["artifact_sha256"]}
    error = build_provenance.verify_variant(build, args.origin, artifact, source, "android")
    if error:
        parser.error(error)
    candidate_ledger = copy.deepcopy(ledger)
    candidate_ledger["candidate_source"].update(source)
    jvm = json.loads(args.jvm_report.read_text())
    deps = {key: Path(value["path"]) for key, value in jvm["dependencies"].items()}
    jdks = {int(key): Path(value["java"]["path"]).parent.parent
            for key, value in jvm["tools"].items()}
    result = java_corpus.capture(candidate_ledger, args.origin, args.source, artifact,
                                 deps, jdks, args.output)
    shutil.rmtree(args.output / "classes")
    (args.output / "sources.args").unlink()
    result["target"] = "android-host"
    result["xml_root"] = args.output.resolve().relative_to(ROOT).as_posix()
    result["build_receipt"] = args.build_receipt.resolve().relative_to(ROOT).as_posix()
    result["build_receipt_sha256"] = digest(args.build_receipt)
    report_path = args.output / "report.json"
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": result["passed"],
                      "cases": result["actual_executed_cases_per_lane"],
                      "lanes": {key: value["status"] for key, value in result["lanes"].items()},
                      "report_sha256": digest(report_path)}, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
