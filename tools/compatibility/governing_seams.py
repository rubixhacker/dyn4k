from __future__ import annotations

import argparse
import gzip
import json
import os
import subprocess
import tempfile
from pathlib import Path

import candidate_coverage
import java_corpus
import method_coverage


FIXTURE = Path(__file__).parent / "fixtures/governing/GoverningSeams.java"
MAIN = "org.dyn4j.dynamics.contact.GoverningSeams"
EXPECTED_OUTPUT = "governing seams passed\n"
JAVA_TOOL_OPTIONS_BANNER = "Picked up JAVA_TOOL_OPTIONS: "


def lane_environment(additional_options: str | None = None) -> tuple[dict[str, str], str | None]:
    env = os.environ.copy()
    inherited_options = env.get("JAVA_TOOL_OPTIONS", "")
    options = " ".join(value for value in (inherited_options, additional_options) if value)
    if options:
        env["JAVA_TOOL_OPTIONS"] = options
    else:
        env.pop("JAVA_TOOL_OPTIONS", None)
    return env, options or None


def strip_java_tool_options_banner(stderr: str, options: str | None) -> str:
    if options is None:
        return stderr
    return stderr.removeprefix(JAVA_TOOL_OPTIONS_BANNER + options + "\n")


def original_corpus(ledger: dict, root: Path) -> dict:
    record = ledger["review_receipts"]["method_coverage"]
    path = method_coverage.safe_path(root, record["corpus"])
    if candidate_coverage.digest(path) != record["corpus_sha256"]:
        raise ValueError("original Java corpus receipt differs")
    report = json.loads(path.read_text())
    if (report["candidate_commit"] != ledger["candidate_source"]["revision"]
            or report["artifact_sha256"] != ledger["candidate_source"]["artifact_sha256"]
            or report["actual_executed_cases_per_lane"] != 2385 or not report["passed"]):
        raise ValueError("original Java corpus outcome differs")
    return report


def capture(ledger: dict, root: Path) -> tuple[dict, bytes]:
    root = root.resolve()
    source = ledger["candidate_source"]
    jar = root / source["artifact"]
    baseline = Path("/tmp/dyn4k-baseline-cache/dyn4j-6.0.0.jar")
    if (candidate_coverage.digest(jar) != source["artifact_sha256"]
            or source["artifact_sha256"] == ledger["baseline"]["binary_sha256"]
            or candidate_coverage.digest(baseline) != ledger["baseline"]["binary_sha256"]):
        raise ValueError("baseline or candidate artifact differs")
    corpus = original_corpus(ledger, root)
    stdlib = Path(corpus["dependencies"]["stdlib"]["path"])
    if candidate_coverage.digest(stdlib) != corpus["dependencies"]["stdlib"]["sha256"]:
        raise ValueError("Kotlin standard library differs")
    method_record = ledger["review_receipts"]["method_coverage"]
    method_path = method_coverage.safe_path(root, method_record["path"])
    if candidate_coverage.digest(method_path) != method_record["sha256"]:
        raise ValueError("original method coverage receipt differs")
    tools = json.loads(method_path.read_text())["tools"]
    agent, _ = method_coverage.checked_tools(tools)
    jdks = {int(key): Path(value["java"]["path"]).parent.parent
            for key, value in corpus["tools"].items()}
    for major, jdk in jdks.items():
        if corpus["tools"][str(major)] != {
                name: java_corpus.tool(jdk, name, major) for name in ("javac", "java")}:
            raise ValueError("Java tool identity differs")
    with tempfile.TemporaryDirectory(prefix="dyn4k-ledger-governing-seams-") as directory:
        location = Path(directory)
        agent_path = location / "jacocoagent.jar"
        agent_path.write_bytes(agent)
        execution = location / "methods.exec"
        lanes = {}
        for provider, archive in (("baseline", baseline), ("candidate", jar)):
            agent_options = None
            if provider == "candidate":
                agent_options = "-javaagent:" + str(agent_path) + "=destfile=" + str(execution)
                agent_options += ",append=true,dumponexit=true,output=file"
            env, java_options = lane_environment(agent_options)
            for compiler in (8, 21):
                classes = location / f"{provider}-javac{compiler}"
                classes.mkdir()
                cp = os.pathsep.join((str(archive), str(stdlib)))
                options = ["-source", "8", "-target", "8"] if compiler == 8 else ["--release", "8"]
                compiled = subprocess.run([str(jdks[compiler] / "bin/javac"), *options,
                                           "-cp", cp, "-d", str(classes), str(FIXTURE)],
                                          capture_output=True, text=True, timeout=90)
                if compiled.returncode:
                    raise ValueError(f"governing fixture does not compile: {provider} Java {compiler}: "
                                     + compiled.stderr[-500:])
                for runtime in (8, 21):
                    lane = f"{provider}-javac{compiler}-java{runtime}"
                    run = subprocess.run([str(jdks[runtime] / "bin/java"), "-cp",
                                          os.pathsep.join((str(classes), cp)), MAIN],
                                         capture_output=True, text=True, timeout=90, env=env)
                    if run.returncode or run.stdout != EXPECTED_OUTPUT:
                        raise ValueError(f"governing fixture failed: {lane}: {run.stderr[-500:]}")
                    lanes[lane] = {"status": "passed", "exit_code": run.returncode,
                                   "stdout": run.stdout,
                                   "stderr": strip_java_tool_options_banner(run.stderr, java_options)}
        if not execution.is_file():
            raise ValueError("candidate method execution archive is missing")
        raw = execution.read_bytes()
        methods = method_coverage.analyze(execution, jar, tools, jdks[21])
    if candidate_coverage.digest(jar) != source["artifact_sha256"]:
        raise ValueError("candidate artifact changed during governing fixture")
    hit_ids = sorted(row["owner"] + "|" + row["name"] + "|" + row["descriptor"]
                     for row in methods if row["covered_instructions"] > 0)
    if len(lanes) != 8 or len(hit_ids) < 50:
        raise ValueError("governing fixture invocation or method inventory is incomplete")
    return {"lanes": lanes, "observed_method_ids": hit_ids,
            "tools": tools, "jdk_tools": corpus["tools"],
            "stdlib_sha256": candidate_coverage.digest(stdlib)}, raw


def make(ledger: dict, root: Path, execution_path: str) -> tuple[dict, bytes]:
    run, raw = capture(ledger, root)
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    source = ledger["candidate_source"]
    return ({"schema_version": 1, "candidate_revision": source["revision"],
             "candidate_tree": source["tree"],
             "candidate_artifact_sha256": source["artifact_sha256"],
             "baseline_revision": ledger["baseline"]["commit"],
             "baseline_artifact_sha256": ledger["baseline"]["binary_sha256"],
             "fixture_sha256": candidate_coverage.digest(FIXTURE),
             "execution": execution_path,
             "execution_sha256": method_coverage.digest(compressed),
             **run}, compressed)


def check(report: dict, ledger: dict, root: Path, replay: bool = False) -> str | None:
    try:
        root = root.resolve()
        source = ledger["candidate_source"]
        if (report.get("schema_version") != 1
                or report.get("candidate_revision") != source["revision"]
                or report.get("candidate_tree") != source["tree"]
                or report.get("candidate_artifact_sha256") != source["artifact_sha256"]
                or report.get("baseline_revision") != ledger["baseline"]["commit"]
                or report.get("baseline_artifact_sha256") != ledger["baseline"]["binary_sha256"]
                or candidate_coverage.digest(root / source["artifact"]) != source["artifact_sha256"]):
            return "candidate or baseline identity differs from governing fixture"
        if report.get("fixture_sha256") != candidate_coverage.digest(FIXTURE):
            return "governing fixture source differs"
        corpus = original_corpus(ledger, root)
        if report.get("jdk_tools") != corpus["tools"]:
            return "governing Java tools differ"
        stdlib = Path(corpus["dependencies"]["stdlib"]["path"])
        if candidate_coverage.digest(stdlib) != report.get("stdlib_sha256"):
            return "governing Kotlin standard library differs"
        method_record = ledger["review_receipts"]["method_coverage"]
        method_path = method_coverage.safe_path(root, method_record["path"])
        if candidate_coverage.digest(method_path) != method_record["sha256"]:
            return "governing original method receipt differs"
        tools = json.loads(method_path.read_text())["tools"]
        if report.get("tools") != tools:
            return "governing method tools differ"
        compressed = method_coverage.safe_path(root, report["execution"]).read_bytes()
        if method_coverage.digest(compressed) != report.get("execution_sha256"):
            return "governing method execution archive differs"
        jdk21 = Path(corpus["tools"]["21"]["java"]["path"]).parent.parent
        with tempfile.TemporaryDirectory(prefix="dyn4k-ledger-governing-check-") as directory:
            raw = Path(directory) / "methods.exec"
            raw.write_bytes(gzip.decompress(compressed))
            methods = method_coverage.analyze(raw, root / source["artifact"], tools, jdk21)
        observed = sorted(row["owner"] + "|" + row["name"] + "|" + row["descriptor"]
                          for row in methods if row["covered_instructions"] > 0)
        if observed != report.get("observed_method_ids"):
            return "governing method hits differ from raw execution archive"
        lanes = report.get("lanes", {})
        if (len(lanes) != 8 or any(row != {"status": "passed", "exit_code": 0,
                                            "stdout": EXPECTED_OUTPUT, "stderr": ""}
                                  for row in lanes.values())):
            return "governing fixture lane outcome differs"
        if replay:
            repeated, _ = capture(ledger, root)
            if repeated["lanes"] != lanes or repeated["observed_method_ids"] != observed:
                return "governing fixture differs from replayed baseline or candidate run"
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as error:
        return f"governing fixture replay failed: {error}"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe uncovered Java behavior on both exact archives.")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--execution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.execution.exists() or args.output.exists():
        parser.error("governing fixture output exists")
    root = args.root.resolve()
    report, raw = make(json.loads(args.ledger.read_text()), root,
                       args.execution.resolve().relative_to(root).as_posix())
    args.execution.write_bytes(raw)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"lanes": len(report["lanes"]),
                      "observed_methods": len(report["observed_method_ids"])}, sort_keys=True))


if __name__ == "__main__":
    main()
