from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

import candidate_coverage
import java_corpus


HELPER = Path(__file__).parent / "fixtures/JacocoMethodReport.java"
DISPATCH_HELPER = Path(__file__).parent / "fixtures/ClassfileDispatchReport.java"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_path(root: Path, name: str) -> Path:
    if (not isinstance(name, str) or not name or Path(name).is_absolute()
            or ".." in Path(name).parts):
        raise ValueError("method receipt path is unsafe")
    return root / name


def tools_record(agent_bundle: Path, jacoco_core: Path, asm: list[Path]) -> dict:
    paths = [agent_bundle.resolve(), jacoco_core.resolve(), *(path.resolve() for path in asm)]
    if any(not path.is_file() for path in paths) or len(set(paths)) != len(paths):
        raise ValueError("method coverage tool is missing or duplicate")
    with zipfile.ZipFile(agent_bundle) as archive:
        agent = archive.read("jacocoagent.jar")
    return {"agent_bundle": {"path": str(paths[0]), "sha256": candidate_coverage.digest(paths[0])},
            "agent_runtime_sha256": digest(agent),
            "jacoco_core": {"path": str(paths[1]), "sha256": candidate_coverage.digest(paths[1])},
            "asm": [{"path": str(path), "sha256": candidate_coverage.digest(path)}
                    for path in paths[2:]],
            "helper_sha256": candidate_coverage.digest(HELPER)}


def checked_tools(record: dict) -> tuple[bytes, list[Path]]:
    if record.get("helper_sha256") != candidate_coverage.digest(HELPER):
        raise ValueError("method coverage helper source differs")
    entries = [record["agent_bundle"], record["jacoco_core"], *record["asm"]]
    paths = [Path(item["path"]) for item in entries]
    if any(not path.is_file() or candidate_coverage.digest(path) != item["sha256"]
           for path, item in zip(paths, entries)):
        raise ValueError("method coverage tool path or SHA-256 differs")
    with zipfile.ZipFile(paths[0]) as archive:
        agent = archive.read("jacocoagent.jar")
    if digest(agent) != record["agent_runtime_sha256"]:
        raise ValueError("method coverage agent runtime differs")
    return agent, paths[1:]


def analyze(execution: Path, jar: Path, record: dict, jdk21: Path) -> list[dict]:
    _, libraries = checked_tools(record)
    with tempfile.TemporaryDirectory(prefix="dyn4k-ledger-jacoco-helper-") as directory:
        classes = Path(directory)
        cp = ":".join(str(path) for path in libraries)
        subprocess.run([str(jdk21 / "bin/javac"), "-cp", cp, "-d", str(classes),
                        str(HELPER)], check=True, capture_output=True, text=True, timeout=60)
        output = subprocess.run([str(jdk21 / "bin/java"), "-cp", f"{classes}:{cp}",
                                 "JacocoMethodReport", str(execution), str(jar)],
                                check=True, capture_output=True, text=True, timeout=60).stdout
    rows = []
    for line in output.splitlines():
        owner, name, descriptor, covered, total = line.split("\t")
        rows.append({"owner": owner, "name": name, "descriptor": descriptor,
                     "covered_instructions": int(covered), "total_instructions": int(total)})
    identities = {(row["owner"], row["name"], row["descriptor"]) for row in rows}
    if (len(rows) < 3000 or len(identities) != len(rows)
            or any(row["covered_instructions"] < 0
                   or row["covered_instructions"] > row["total_instructions"] for row in rows)):
        raise ValueError("method coverage inventory is incomplete or invalid")
    return rows


def dispatch_inventory(jar: Path, record: dict, jdk21: Path) -> tuple[dict, dict, dict, dict]:
    _, libraries = checked_tools(record)
    with tempfile.TemporaryDirectory(prefix="dyn4k-ledger-dispatch-helper-") as directory:
        classes = Path(directory)
        cp = ":".join(str(path) for path in libraries)
        subprocess.run([str(jdk21 / "bin/javac"), "-cp", cp, "-d", str(classes),
                        str(DISPATCH_HELPER)], check=True, capture_output=True, text=True,
                       timeout=60)
        output = subprocess.run([str(jdk21 / "bin/java"), "-cp", f"{classes}:{cp}",
                                 "ClassfileDispatchReport", str(jar)], check=True,
                                capture_output=True, text=True, timeout=60).stdout
    classes_by_name = {}
    methods = {}
    invokes = {}
    opcodes = {}
    for line in output.splitlines():
        parts = line.split("\t")
        if parts[0] == "C":
            _, owner, access, parent, interfaces = parts
            classes_by_name[owner] = {"access": int(access), "parent": parent,
                                      "interfaces": interfaces.split(",") if interfaces else []}
        elif parts[0] == "M":
            _, owner, name, descriptor, access = parts
            methods[(owner, name, descriptor)] = int(access)
        elif parts[0] == "I":
            _, owner, name, descriptor, opcode, target_owner, target_name, target_descriptor = parts
            invokes.setdefault((owner, name, descriptor), []).append(
                (int(opcode), target_owner, target_name, target_descriptor))
        elif parts[0] == "O":
            _, owner, name, descriptor, values = parts
            key = (owner, name, descriptor)
            if key in opcodes:
                raise ValueError("duplicate classfile opcode row")
            opcodes[key] = [int(value) for value in values.split(",") if value]
        else:
            raise ValueError("classfile dispatch inventory has an unknown row")
    if len(classes_by_name) < 200 or len(methods) < 3000 or set(opcodes) != set(methods):
        raise ValueError("classfile dispatch inventory is incomplete")
    return classes_by_name, methods, invokes, opcodes


def instrumented(ledger: dict, corpus: dict, root: Path, upstream: Path,
                 tools: dict) -> tuple[dict, bytes, list[dict]]:
    agent, _ = checked_tools(tools)
    source = ledger["candidate_source"]
    jar = root / source["artifact"]
    if (candidate_coverage.digest(jar) != source["artifact_sha256"]
            or source["artifact_sha256"] == ledger["baseline"]["binary_sha256"]
            or corpus["candidate_commit"] != source["revision"]
            or corpus["artifact_sha256"] != source["artifact_sha256"]):
        raise ValueError("candidate source or artifact differs")
    dependencies = {key: Path(value["path"]) for key, value in corpus["dependencies"].items()}
    jdks = {int(key): Path(value["java"]["path"]).parent.parent
            for key, value in corpus["tools"].items()}
    with tempfile.TemporaryDirectory(prefix="dyn4k-ledger-java-methods-") as directory:
        location = Path(directory)
        agent_path = location / "jacocoagent.jar"
        agent_path.write_bytes(agent)
        execution = location / "methods.exec"
        env = {"JAVA_TOOL_OPTIONS": "-javaagent:" + str(agent_path)
               + "=destfile=" + str(execution) + ",append=true,dumponexit=true,output=file"}
        run = java_corpus.capture(ledger, root, upstream, jar, dependencies, jdks,
                                  location / "run", runtime_env=env)
        if (not run["passed"] or run["normalized_case_ids"] != corpus["normalized_case_ids"]
                or run["actual_executed_cases_per_lane"] != 2385
                or not execution.is_file()):
            raise ValueError("instrumented original Java cases failed or changed")
        raw = execution.read_bytes()
        methods = analyze(execution, jar, tools, jdks[21])
    if candidate_coverage.digest(jar) != source["artifact_sha256"]:
        raise ValueError("candidate artifact changed during method coverage")
    return run, raw, methods


def make(ledger: dict, corpus: dict, root: Path, upstream: Path,
         tools: dict, corpus_path: str, execution_path: str) -> tuple[dict, bytes]:
    root = root.resolve()
    corpus_file = safe_path(root, corpus_path)
    if json.loads(corpus_file.read_text()) != corpus:
        raise ValueError("original Java corpus receipt differs")
    run, raw, methods = instrumented(ledger, corpus, root, upstream, tools)
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    return ({"schema_version": 1, "candidate_revision": ledger["candidate_source"]["revision"],
             "candidate_tree": ledger["candidate_source"]["tree"],
             "candidate_artifact_sha256": ledger["candidate_source"]["artifact_sha256"],
             "baseline_revision": ledger["baseline"]["commit"],
             "original_corpus": corpus_path,
             "original_corpus_sha256": candidate_coverage.digest(corpus_file),
             "execution": execution_path, "execution_sha256": digest(compressed),
             "tools": tools, "actual_executed_cases_per_lane": 2385,
             "candidate_lanes": sum(key.startswith("candidate-") and row["status"] == "passed"
                                    for key, row in run["lanes"].items()),
             "method_count": len(methods),
             "observed_method_count": sum(row["covered_instructions"] > 0 for row in methods),
             "methods": methods}, compressed)


def check(report: dict, ledger: dict, corpus: dict, root: Path,
          upstream: Path, replay: bool = False) -> str | None:
    try:
        root = root.resolve()
        source = ledger["candidate_source"]
        if (report.get("schema_version") != 1
                or report.get("candidate_revision") != source["revision"]
                or report.get("candidate_tree") != source["tree"]
                or report.get("candidate_artifact_sha256") != source["artifact_sha256"]
                or report.get("baseline_revision") != ledger["baseline"]["commit"]
                or candidate_coverage.digest(root / source["artifact"]) != source["artifact_sha256"]):
            return "candidate source or artifact differs from method coverage"
        corpus_path = safe_path(root, report["original_corpus"])
        if (candidate_coverage.digest(corpus_path) != report["original_corpus_sha256"]
                or json.loads(corpus_path.read_text()) != corpus
                or corpus.get("passed") is not True
                or corpus.get("actual_executed_cases_per_lane") != 2385):
            return "original Java corpus receipt differs from method coverage"
        compressed = safe_path(root, report["execution"]).read_bytes()
        if digest(compressed) != report["execution_sha256"]:
            return "method execution archive differs"
        _, libraries = checked_tools(report["tools"])
        jdks = {int(key): Path(value["java"]["path"]).parent.parent
                for key, value in corpus["tools"].items()}
        with tempfile.TemporaryDirectory(prefix="dyn4k-ledger-method-check-") as directory:
            raw = Path(directory) / "methods.exec"
            raw.write_bytes(gzip.decompress(compressed))
            observed = analyze(raw, root / source["artifact"], report["tools"], jdks[21])
        if (observed != report.get("methods") or report.get("method_count") != len(observed)
                or report.get("observed_method_count") != sum(row["covered_instructions"] > 0
                                                               for row in observed)):
            return "method coverage rows differ from raw execution archive"
        if (report.get("actual_executed_cases_per_lane") != 2385
                or report.get("candidate_lanes") != 4):
            return "method coverage Java case or candidate lane count differs"
        if replay:
            run, _, repeated = instrumented(ledger, corpus, root, upstream, report["tools"])
            observed_hits = {(row["owner"], row["name"], row["descriptor"])
                             for row in observed if row["covered_instructions"] > 0}
            repeated_hits = {(row["owner"], row["name"], row["descriptor"])
                             for row in repeated if row["covered_instructions"] > 0}
            if observed_hits != repeated_hits or not run["passed"]:
                return "method execution differs from replayed original Java cases"
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, zipfile.BadZipFile) as error:
        return f"method coverage replay failed: {error}"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture candidate method execution through original Java cases.")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--agent-bundle", type=Path, required=True)
    parser.add_argument("--jacoco-core", type=Path, required=True)
    parser.add_argument("--asm", type=Path, action="append", required=True)
    parser.add_argument("--execution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.output.exists() or args.execution.exists():
        parser.error("method coverage output exists")
    report, compressed = make(json.loads(args.ledger.read_text()),
                              json.loads(args.corpus.read_text()), root, args.upstream,
                              tools_record(args.agent_bundle, args.jacoco_core, args.asm),
                              args.corpus.resolve().relative_to(root).as_posix(),
                              args.execution.resolve().relative_to(root).as_posix())
    args.execution.write_bytes(compressed)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"method_count": report["method_count"],
                      "observed_method_count": report["observed_method_count"],
                      "cases": report["actual_executed_cases_per_lane"]}, sort_keys=True))


if __name__ == "__main__":
    main()
