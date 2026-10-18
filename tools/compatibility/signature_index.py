from __future__ import annotations

import argparse
import gzip
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "baseline"))
import verify as oracle
import execution_probe
import build_provenance
from candidate_coverage import digest


def observe(rows: list[dict], jar: Path, production: list[dict]) -> dict:
    jar = jar.resolve()
    artifact_sha = digest(jar)
    if artifact_sha == oracle.BINARY_SHA256:
        raise ValueError("pinned baseline JAR cannot be a candidate artifact")
    javap_name = shutil.which("javap")
    if javap_name is None:
        raise ValueError("javap is unavailable")
    javap = Path(javap_name).resolve()
    version = subprocess.run([str(javap), "-version"], capture_output=True, text=True,
                             check=True).stdout.strip()
    originals = {item["id"]: item["sha256"] for item in production}
    by_type = {}
    for item in rows:
        by_type.setdefault(item["id"].split("|")[0], []).append(item)
    classes = []
    outcomes = {}
    for name in sorted(by_type):
        group = by_type[name]
        type_row = next((item for item in group if item["id"] == f"{name}|type"), None)
        if type_row is None:
            raise ValueError(f"type obligation missing from signature index: {name}")
        if type_row.get("candidate") is None:
            for item in group:
                outcomes[item["id"]] = {"passed": False, "reason": "candidate type is unmapped",
                                        "source_sha256": originals[item["source_file"]]}
            continue
        commands = [[str(javap), "-classpath", str(jar), "-protected", "-s", name],
                    [str(javap), "-classpath", str(jar), "-protected", "-s", "-v", name]]
        runs = [subprocess.run(command, capture_output=True, text=True,
                               check=False, timeout=30) for command in commands]
        record = {"name": name, "commands": commands,
                  "process_exit_codes": [run.returncode for run in runs],
                  "raw_stdout": [run.stdout for run in runs],
                  "raw_stderr": [run.stderr for run in runs]}
        classes.append(record)
        try:
            if any(run.returncode != 0 for run in runs):
                raise ValueError("javap command failed")
            header, members = execution_probe.declarations(runs[0].stdout, runs[1].stdout, oracle)
            for item in group:
                parts = item["id"].split("|")
                actual = header if len(parts) == 2 else members.get((parts[1], parts[2]))
                wanted = item["signature"] if len(parts) == 2 else (item["signature"], item.get("flags"))
                matched = actual == wanted
                outcomes[item["id"]] = {"passed": matched,
                                        "reason": None if matched else "candidate JVM declaration differs or is absent",
                                        "source_sha256": originals[item["source_file"]]}
        except ValueError as error:
            record["parser_error"] = str(error)
            for item in group:
                outcomes[item["id"]] = {"passed": False, "reason": f"candidate JVM probe failed: {error}",
                                        "source_sha256": originals[item["source_file"]]}
    if digest(jar) != artifact_sha:
        raise ValueError("candidate JAR changed during signature inventory")
    passed = sorted(key for key, outcome in outcomes.items() if outcome["passed"])
    return {"schema_version": 3, "kind": "java-signature", "target": "jvm",
            "probe": "javap-inventory-v1", "artifact_sha256": artifact_sha,
            "javap": str(javap), "javap_sha256": digest(javap), "javap_version": version,
            "classes": classes, "outcomes": outcomes, "passed_identities": passed,
            "checked_identities": len(outcomes), "matched_identities": len(passed),
            "javap_invocations": 2 * len(classes), "failures": len(outcomes) - len(passed),
            "ignored": 0, "process_exit_code": int(len(outcomes) != len(passed))}


def make_report(ledger: dict, jar: Path, build_path: Path, root: Path) -> dict:
    root = root.resolve()
    source = ledger["candidate_source"]
    if jar.resolve() != (root / source["artifact"]).resolve():
        raise ValueError("candidate artifact path differs from source mapping")
    if not build_path.is_file() or root not in build_path.resolve().parents:
        raise ValueError("candidate build receipt is missing or outside the worktree")
    build = json.loads(build_path.read_text())
    error = build_provenance.verify(build, root, jar, source)
    if error:
        raise ValueError(error)
    index = observe(ledger["declarations"], jar, ledger["production"])
    return {"schema_version": 3, "kind": "java-signature", "target": "jvm",
            "probe": "javap-inventory-v1", "baseline": ledger["baseline"],
            "candidate_commit": source["revision"], "source_tree": source["tree"],
            "artifact_sha256": source["artifact_sha256"],
            "build_receipt": build_path.resolve().relative_to(root).as_posix(),
            "build_receipt_sha256": digest(build_path), "index": index}


def validate_report(report: dict, ledger: dict, jar: Path, root: Path) -> str | None:
    root = root.resolve()
    source = ledger.get("candidate_source", {})
    if not isinstance(report, dict) or any((
            report.get("schema_version") != 3,
            report.get("kind") != "java-signature",
            report.get("target") != "jvm",
            report.get("probe") != "javap-inventory-v1",
            report.get("baseline") != ledger.get("baseline"),
            report.get("candidate_commit") != source.get("revision"),
            report.get("source_tree") != source.get("tree"),
            report.get("artifact_sha256") != source.get("artifact_sha256"),
            jar.resolve() != (root / source.get("artifact", "")).resolve(),
    )):
        return "signature report baseline or candidate identity differs"
    receipt_name = report.get("build_receipt")
    if (not isinstance(receipt_name, str) or not receipt_name
            or Path(receipt_name).is_absolute() or ".." in Path(receipt_name).parts):
        return "signature report build receipt path is unsafe"
    receipt_path = root / receipt_name
    if not receipt_path.is_file() or digest(receipt_path) != report.get("build_receipt_sha256"):
        return "signature report build receipt is missing or changed"
    try:
        receipt = json.loads(receipt_path.read_text())
        error = build_provenance.verify(receipt, root, jar, source)
        if error:
            return error
        observed = observe(ledger["declarations"], jar, ledger["production"])
    except (OSError, ValueError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, KeyError, TypeError) as error:
        return f"signature report replay failed: {error}"
    if report.get("index") != observed:
        return "signature report differs from replayed javap inventory"
    return None


def attach_report(ledger: dict, report: dict, report_path: Path, root: Path) -> dict:
    root = root.resolve()
    source = ledger["candidate_source"]
    if (report.get("candidate_commit") != source["revision"]
            or report.get("source_tree") != source["tree"]
            or report.get("artifact_sha256") != source["artifact_sha256"]):
        raise ValueError("signature report candidate source or artifact differs")
    receipt_name = report.get("build_receipt")
    if (not isinstance(receipt_name, str) or not receipt_name
            or Path(receipt_name).is_absolute() or ".." in Path(receipt_name).parts
            or not (root / receipt_name).is_file()
            or digest(root / receipt_name) != report.get("build_receipt_sha256")):
        raise ValueError("signature report build receipt is missing or changed")
    source["build_receipt"] = receipt_name
    source["build_receipt_sha256"] = report["build_receipt_sha256"]
    name = report_path.resolve().relative_to(root).as_posix()
    checksum = digest(report_path)
    outcomes = report["index"]["outcomes"]
    for item in ledger["declarations"]:
        outcome = outcomes[item["id"]]
        if outcome["passed"] and item["candidate"]:
            item["evidence"] = [{"kind": "java-signature", "status": "passed", "target": "jvm",
                                 "report": name, "report_sha256": checksum}]
        elif item["candidate"]:
            item["evidence"] = [{"kind": "java-signature", "status": "failed",
                                 "target": "jvm", "reason": outcome["reason"]}]
    return ledger


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture one replayable JVM declaration inventory.")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output-ledger", type=Path, required=True)
    args = parser.parse_args()
    if any(path.exists() for path in (args.build_receipt, args.report, args.output_ledger)):
        parser.error("one or more output paths already exist")
    root = args.root.resolve()
    ledger = json.loads(args.ledger.read_text())
    source = ledger["candidate_source"]
    jar = root / source["artifact"]
    proof = build_provenance.probe(root, source["revision"], jar)
    if not proof["passed"]:
        parser.error(f"candidate source rebuild failed: {proof['reason']}")
    args.build_receipt.parent.mkdir(parents=True, exist_ok=True)
    args.build_receipt.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    report = make_report(ledger, jar, args.build_receipt, root)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with gzip.GzipFile(filename=str(args.report), mode="wb", compresslevel=9, mtime=0) as stream:
        stream.write((json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode())
    attach_report(ledger, report, args.report, root)
    args.output_ledger.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"checked": report["index"]["checked_identities"],
                      "matched": report["index"]["matched_identities"],
                      "failed": report["index"]["failures"],
                      "report_sha256": digest(args.report)}, sort_keys=True))


if __name__ == "__main__":
    main()
