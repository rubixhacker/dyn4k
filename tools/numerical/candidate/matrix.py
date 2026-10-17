import argparse
import gzip
import hashlib
import json
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import unquote, urlparse

import receipt


ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = Path(__file__).resolve().parent
BASELINE_SHA256 = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
FAMILIES = (
    ("geometry", "geometry", "", 585),
    ("motion", "motion", "F-", 30),
    ("contacts", "contacts", "C-", 195),
    ("joints", "joints", "P-J-", 232),
    ("joint_checkpoints", "joints", "P-JCP-", 92),
    ("joint_interactions", "joints", "P-JINT-", 25),
    ("ccd", "ccd", "CCD-world-", 180),
    ("long", "long", "L-", 91),
)
SCALES = (0.01, 1.0, 100.0)
OFFSETS = ((0.0, 0.0), (1000.0, 1000.0), (-1000.0, 1000.0),
           (1000000.0, -1000000.0), (-1000000.0, 1000000.0))
SPLIT_FAMILIES = {"motion", "contacts", "ccd", "long"}


def digest(path):
    hash_value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hash_value.update(block)
    return hash_value.hexdigest()


def command(args, log):
    with Path(log).open("xb") as stream:
        return subprocess.run(args, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                              check=False).returncode


def lines(path):
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            yield number, json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError("nonfinite JSON token " + value)))


def trace_identity(path):
    raw_hash = digest(path)
    stream_hash = hashlib.sha256()
    runtime_hash = hashlib.sha256()
    kinds = Counter()
    first = None
    with gzip.open(path, "rb") as stream:
        for number, line in enumerate(stream, 1):
            stream_hash.update(line)
            if number == 1:
                first = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError("nonfinite input token " + value)))
                if first.get("kind") != "inputs":
                    raise ValueError(f"{path}: first record is not inputs")
                input_hash = hashlib.sha256(line).hexdigest()
            else:
                runtime_hash.update(line)
            for kind in (b'"kind":"event"', b'"kind":"state"', b'"kind":"action"',
                         b'"kind":"instrumented-callback"', b'"kind":"outer-endpoint"'):
                if kind in line:
                    kinds[kind.decode().split('"')[3]] += 1
                    break
    if first is None:
        raise ValueError(f"{path}: empty trace")
    return {"gzip_sha256": raw_hash, "stream_sha256": stream_hash.hexdigest(),
            "runtime_stream_sha256": runtime_hash.hexdigest(),
            "input_line_sha256": input_hash, "record_counts": dict(kinds),
            "file_bytes": path.stat().st_size}


def runtime_identity(directory, provider_hash):
    stamp = directory / "runtime.json"
    value = json.loads(stamp.read_text(encoding="utf-8"))
    if set(value) != receipt.RUNTIME_FIELDS:
        raise ValueError(f"{stamp}: invalid process runtime fields")
    loaded = urlparse(value["engine_location"])
    if loaded.scheme != "file" or loaded.netloc not in ("", "localhost"):
        raise ValueError(f"{stamp}: engine code source is not a local file")
    if digest(Path(unquote(loaded.path))) != provider_hash:
        raise ValueError(f"{stamp}: loaded engine differs from provider")
    executable = Path(value["process_command"])
    value["process_command_sha256"] = digest(executable)
    value["runtime_stamp_sha256"] = digest(stamp)
    return value


def inspect(directory, provider_hash, expected):
    summary_file = directory / "summary.jsonl"
    query_file = directory / "queries.jsonl"
    summaries = [item for _, item in lines(summary_file)]
    queries = [item for _, item in lines(query_file)]
    query_case_hashes = {}
    with query_file.open("rb") as stream:
        for line in stream:
            case_id = json.loads(line)["id"]
            query_case_hashes.setdefault(case_id, hashlib.sha256()).update(line)
    traces = {}
    failures = []
    seen_files = set()
    for item in summaries:
        name = item.get("file")
        if item.get("status"):
            failures.append({"id": item.get("id"), "status": item["status"],
                             "firstFailureStep": item.get("firstFailureStep"),
                             "reason": item.get("reason")})
        if name is None:
            continue
        if name in seen_files:
            raise ValueError(f"{directory}: duplicate trace filename {name}")
        seen_files.add(name)
        trace = directory / name
        if not trace.is_file():
            raise ValueError(f"{directory}: missing trace {name}")
        traces[name] = {"id": item["id"], "summary": item,
                        **trace_identity(trace)}
    actual_files = {path.name for path in directory.glob("*.jsonl.gz")}
    if actual_files != seen_files:
        raise ValueError(f"{directory}: missing or extra trace files {sorted(actual_files ^ seen_files)}")
    if expected == "geometry":
        case_count = len({item["id"] for item in queries})
    elif expected == "joint_checkpoints":
        case_count = len({item["id"] for item in summaries
                          if not item["id"].endswith("-preparation")})
    elif expected == "joint_interactions":
        case_count = len({item["id"] for item in summaries
                          if not item["id"].endswith("-preparation")})
    else:
        case_count = len({item["id"] for item in summaries})
    return {"runtime": runtime_identity(directory, provider_hash),
            "summary_sha256": digest(summary_file), "queries_sha256": digest(query_file),
            "query_case_sha256": {key: value.hexdigest() for key, value in query_case_hashes.items()},
            "query_rows": len(queries), "summary_rows": len(summaries),
            "case_summaries": summaries,
            "case_count": case_count, "executed_steps": sum(item.get("steps", 0) for item in summaries),
            "failures": failures, "traces": traces}


def compile_provider(provider, jar, java21, directory):
    classes = directory / "classes"
    classes.mkdir()
    sources = sorted((CANDIDATE / "calibration").glob("*.java"))
    sources.append(CANDIDATE / "runtime" / "RuntimeStamp.java")
    args = [str(java21 / "bin" / "javac"), "--release", "21", "-cp", str(jar),
            "-d", str(classes), *(str(source) for source in sources)]
    code = command(args, directory / "compile.log")
    if code:
        raise ValueError(f"{provider} javac exited {code}; see {directory / 'compile.log'}")
    return classes, {"command": args, "log_sha256": digest(directory / "compile.log")}


def run_provider(provider, jar, java21, stdlib, directory, selected):
    classes, compilation = compile_provider(provider, jar, java21, directory)
    classpath = [classes, jar]
    if provider == "candidate":
        classpath.append(stdlib)
    runs = {}
    for name, family, filter_value, expected in FAMILIES:
        if selected and name not in selected:
            continue
        target = directory / name
        target.mkdir()
        def execute(chunk_name, case_filter):
            output = target / chunk_name if chunk_name else target
            if chunk_name:
                output.mkdir()
            args = [str(java21 / "bin" / "java"), "-Xmx2g", "-cp",
                    ":".join(str(part) for part in classpath), "CandidateCases",
                    str(output), family, case_filter]
            exit_code = command(args, output / "run.log")
            record = {"command": args, "exit_code": exit_code,
                      "log_sha256": digest(output / "run.log")}
            try:
                record.update(inspect(output, digest(jar), name))
                if record["runtime"]["process_command_sha256"] != digest(java21 / "bin" / "java"):
                    raise ValueError("recorder ran under a different Java executable")
                if not record["runtime"]["java_version"].startswith("21."):
                    raise ValueError("recorder did not run on Java 21")
            except (OSError, ValueError, KeyError, TypeError) as failure:
                record["inspection_failure"] = str(failure)
            if chunk_name:
                (output / "chunk.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
            print(json.dumps({"provider": provider, "family": name, "chunk": chunk_name,
                              "exit_code": exit_code, "case_count": record.get("case_count"),
                              "failures": len(record.get("failures", [])),
                              "inspection_failure": record.get("inspection_failure")}), flush=True)
            return record
        if name in SPLIT_FAMILIES:
            chunks = {}
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {}
                for scale_index, scale in enumerate(SCALES):
                    for origin_index, origin in enumerate(OFFSETS):
                        chunk_name = f"s{scale_index}-o{origin_index}"
                        suffix = f"s{scale}-o{origin[0]},{origin[1]}"
                        compound_filter = filter_value + "&&" + suffix
                        futures[pool.submit(execute, chunk_name, compound_filter)] = chunk_name
                for future in as_completed(futures):
                    chunks[futures[future]] = future.result()
            run = {"chunks": chunks, "expected_case_count": expected,
                   "case_count": sum(item.get("case_count", 0) for item in chunks.values()),
                   "summary_rows": sum(item.get("summary_rows", 0) for item in chunks.values()),
                   "query_rows": sum(item.get("query_rows", 0) for item in chunks.values()),
                   "executed_steps": sum(item.get("executed_steps", 0) for item in chunks.values()),
                   "failures": [failure for item in chunks.values() for failure in item.get("failures", [])],
                   "traces": {file: trace for item in chunks.values()
                              for file, trace in item.get("traces", {}).items()},
                   "query_case_sha256": {key: value for item in chunks.values()
                                         for key, value in item.get("query_case_sha256", {}).items()},
                   "exit_code": max(item["exit_code"] for item in chunks.values())}
            errors = {chunk: item["inspection_failure"] for chunk, item in chunks.items()
                      if item.get("inspection_failure")}
            if errors:
                run["inspection_failure"] = errors
        else:
            run = execute("", filter_value)
            run["expected_case_count"] = expected
        if run.get("case_count") != expected:
            run["coverage_failure"] = f"{run.get('case_count')} / {expected} declared cases"
        runs[name] = run
        (directory / "progress.json").write_text(json.dumps({
            "provider_sha256": digest(jar), "compilation": compilation,
            "families": runs}, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"provider": provider, "family": name, "case_count": run.get("case_count"),
                          "failures": len(run.get("failures", [])),
                          "inspection_failure": run.get("inspection_failure")}), flush=True)
    return {"provider_sha256": digest(jar), "compilation": compilation, "families": runs}


def world_quality_controls(jars, java8, java21, stdlib, directory):
    controls = {}
    for provider, jar in jars:
        target = directory / provider
        target.mkdir()
        classes = target / "classes"
        classes.mkdir()
        source = CANDIDATE / "runtime8" / "WorldQualityProbe.java"
        compile_args = [str(java21 / "bin" / "javac"), "--release", "8", "-cp",
                        str(jar), "-d", str(classes), str(source)]
        compile_exit = command(compile_args, target / "compile.log")
        if compile_exit:
            controls[provider] = {"compile_exit": compile_exit,
                                  "compile_log_sha256": digest(target / "compile.log")}
            continue
        classpath = [classes, jar]
        if provider == "candidate":
            classpath.append(stdlib)
        for lane, jdk in (("java8", java8), ("java21", java21)):
            executable = jdk / "bin" / "java"
            args = [str(executable), "-cp", ":".join(str(part) for part in classpath),
                    "WorldQualityProbe"]
            log = target / (lane + ".log")
            exit_code = command(args, log)
            text = log.read_text(encoding="utf-8", errors="replace")
            rows = [line for line in text.splitlines() if line.startswith("WORLD_QUALITY,")]
            stamps = [line for line in text.splitlines() if line.startswith("RUNTIME,")]
            check = None
            if len(stamps) != 1 or len(rows) != 6:
                check = f"runtime rows={len(stamps)} quality rows={len(rows)}; expected 1 and 6"
            else:
                parts = stamps[0].split(",", 3)
                location = urlparse(parts[3])
                expected_version = "1.8." if lane == "java8" else "21."
                if location.scheme != "file" or digest(Path(unquote(location.path))) != digest(jar):
                    check = "loaded provider differs from declared JAR"
                elif not parts[1].startswith(expected_version):
                    check = "executing JVM version differs from requested lane"
            controls[f"{provider}-{lane}"] = {"command": args, "exit_code": exit_code,
                "executable_sha256": digest(executable), "provider_sha256": digest(jar),
                "log_sha256": digest(log), "runtime": stamps, "rows": rows,
                "check_failure": check}
            print(json.dumps({"control": f"{provider}-{lane}", "exit_code": exit_code,
                              "rows": len(rows), "check_failure": check}), flush=True)
    return controls


def pair_diagnostics(baseline, candidate):
    paired = {}
    for name, _, _, _ in FAMILIES:
        if name not in baseline["families"] or name not in candidate["families"]:
            continue
        left = baseline["families"][name]
        right = candidate["families"][name]
        if "traces" not in left or "traces" not in right:
            paired[name] = {"status": "UNINSPECTED"}
            continue
        cases = {}
        for file in sorted(set(left["traces"]) | set(right["traces"])):
            a = left["traces"].get(file)
            b = right["traces"].get(file)
            if a is None or b is None:
                status = "MISSING_BASELINE" if a is None else "MISSING_CANDIDATE"
            elif a["record_counts"] != b["record_counts"]:
                status = "RECORD_COUNT_DIFFERENCE"
            elif a["input_line_sha256"] != b["input_line_sha256"]:
                status = "INPUT_DIFFERENCE"
            elif a["runtime_stream_sha256"] != b["runtime_stream_sha256"]:
                status = "RUNTIME_BYTE_DIFFERENCE"
            else:
                status = "BYTE_IDENTICAL_DIAGNOSTIC"
            cases[file] = {"id": (a or b)["id"], "status": status}
        for side, run in (("baseline", left), ("candidate", right)):
            for failure in run["failures"]:
                cases.setdefault(failure["id"], {"id": failure["id"]})[side + "_failure"] = failure
        queries = {}
        for case_id in sorted(set(left["query_case_sha256"]) | set(right["query_case_sha256"])):
            a = left["query_case_sha256"].get(case_id)
            b = right["query_case_sha256"].get(case_id)
            queries[case_id] = "BYTE_IDENTICAL_DIAGNOSTIC" if a == b else "QUERY_BYTE_DIFFERENCE"
        paired[name] = {"traces": cases, "queries": queries,
                        "trace_status_counts": dict(Counter(item["status"] for item in cases.values()
                                                            if "status" in item)),
                        "query_status_counts": dict(Counter(queries.values()))}
    return paired


def main():
    parser = argparse.ArgumentParser(description="Run Java calibration cases against staged and pinned providers")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--baseline-jar", required=True, type=Path)
    parser.add_argument("--java21", required=True, type=Path)
    parser.add_argument("--java8", required=True, type=Path)
    parser.add_argument("--kotlin-stdlib", required=True, type=Path)
    parser.add_argument("--families", nargs="*", choices=[item[0] for item in FAMILIES])
    args = parser.parse_args()
    commit = receipt.clean_commit()
    if digest(args.baseline_jar) != BASELINE_SHA256:
        raise ValueError("pinned baseline JAR hash differs")
    if not receipt.ARTIFACT.is_file():
        raise ValueError("staged candidate JAR is missing")
    for executable in (args.java21 / "bin" / "javac", args.java21 / "bin" / "java",
                       args.java8 / "bin" / "java"):
        if not executable.is_file():
            raise ValueError(f"JDK 21 executable is missing: {executable}")
    if not args.kotlin_stdlib.is_file():
        raise ValueError("Kotlin stdlib is missing")
    args.output.mkdir(parents=True)
    result = {"candidate_commit": commit, "source_sha256": receipt.source_hash(),
              "build_config_sha256": receipt.build_config_hash(),
              "java21_executable_sha256": digest(args.java21 / "bin" / "java"),
              "java8_executable_sha256": digest(args.java8 / "bin" / "java"),
              "baseline_jar_sha256": digest(args.baseline_jar),
              "candidate_jar_sha256": digest(receipt.ARTIFACT),
              "kotlin_stdlib_sha256": digest(args.kotlin_stdlib),
              "selected_families": args.families or [item[0] for item in FAMILIES]}
    for provider, jar in (("baseline", args.baseline_jar), ("candidate", receipt.ARTIFACT)):
        directory = args.output / provider
        directory.mkdir()
        result[provider] = run_provider(provider, jar, args.java21, args.kotlin_stdlib,
                                        directory, set(args.families or []))
        (args.output / "manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    controls = args.output / "world_quality_controls"
    controls.mkdir()
    result["world_quality_controls"] = world_quality_controls(
        (("baseline", args.baseline_jar), ("candidate", receipt.ARTIFACT)),
        args.java8, args.java21, args.kotlin_stdlib, controls)
    result["paired_diagnostics"] = pair_diagnostics(result["baseline"], result["candidate"])
    failed = any(run.get("inspection_failure") or run.get("coverage_failure") or
                 run.get("exit_code") or run.get("failures")
                 for provider in ("baseline", "candidate")
                 for run in result[provider]["families"].values())
    failed |= any(control.get("compile_exit") or control.get("exit_code") or
                  control.get("check_failure") for control in result["world_quality_controls"].values())
    result["status"] = "FAILED" if failed else "CAPTURED_UNQUALIFIED"
    (args.output / "manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "manifest": str(args.output / "manifest.json")}), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
