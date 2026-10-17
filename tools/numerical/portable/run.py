import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from itertools import chain
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cases import declared_cases
from physical import nominal_free, sleep_wake_rows
from reference_diagnostic import diagnostic, portable_case_id
from receipt import Identity, Rejected, digest, records, seal


ROOT = Path(__file__).resolve().parents[3]
PORTABLE = Path(__file__).resolve().parent
STAGED = ROOT / "build/staging-repository/io/github/rubixhacker"
VERSION = "0.1.0-alpha.1"
HOST_TASKS = {
    "jvm": "jvmTest",
    "jvm8": "jvmTest",
    "android-host": "testAndroidHostTest",
    "linux-x64": "linuxX64Test",
    "node-js": "jsNodeTest",
    "node-wasm-js": "wasmJsNodeTest",
    "node-wasm-wasi": "wasmWasiNodeTest",
}
STAGE_TASKS = (
    ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
    ":dyn4k-core:publishJvmPublicationToStagingRepository",
    ":dyn4k-core:publishAndroidPublicationToStagingRepository",
    ":dyn4k-core:publishLinuxX64PublicationToStagingRepository",
    ":dyn4k-core:publishJsPublicationToStagingRepository",
    ":dyn4k-core:publishWasmJsPublicationToStagingRepository",
    ":dyn4k-core:publishWasmWasiPublicationToStagingRepository",
)
ARTIFACT_NAME = {
    "jvm": ("jvm", "jar"),
    "jvm8": ("jvm", "jar"),
    "android-host": ("android", "aar"),
    "linux-x64": ("linuxx64", "klib"),
    "node-js": ("js", "klib"),
    "node-wasm-js": ("wasm-js", "klib"),
    "node-wasm-wasi": ("wasm-wasi", "klib"),
}
OTHER_LANES = (
    "android-device", "linux-arm64", "windows-x64", "macos-arm64", "ios-arm64",
    "ios-simulator-arm64", "ios-simulator-x64", "tvos-arm64", "tvos-simulator-arm64",
    "watchos-arm64", "watchos-device-arm64", "watchos-simulator-arm64",
    "android-native-arm32", "android-native-arm64", "android-native-x86", "android-native-x64",
)
CATALOG = ROOT / "tools/numerical/fixtures.json"


def git(*args):
    return subprocess.run(("git", *args), cwd=ROOT, check=True, capture_output=True).stdout


def clean_identity():
    status = git("status", "--porcelain", "--untracked-files=all").decode()
    dirty = [line for line in status.splitlines() if not any(fragment in line for fragment in
             ("/build/", "/.gradle/", "/.kotlin/", "/__pycache__/"))]
    if dirty:
        raise Rejected("source tree is dirty: " + ", ".join(dirty[:5]))
    return git("rev-parse", "HEAD").decode().strip(), hashlib.sha256(git("archive", "--format=tar", "HEAD")).hexdigest()


def artifacts(host):
    suffix, extension = ARTIFACT_NAME[host]
    main = STAGED / f"dyn4k-core-{suffix}" / VERSION / f"dyn4k-core-{suffix}-{VERSION}.{extension}"
    metadata = STAGED / "dyn4k-core" / VERSION / f"dyn4k-core-{VERSION}.jar"
    for path in (main, metadata):
        if not path.is_file():
            raise Rejected(f"staged publication is absent: {path}")
    return {"target": main, "metadata": metadata}


def stage(output, commit, source_sha256):
    started = __import__("time").time()
    env = os.environ.copy()
    env.setdefault("ANDROID_HOME", str(Path.home() / "Android/Sdk"))
    command = [str(ROOT / "gradlew"), *STAGE_TASKS, "--rerun-tasks", "--no-daemon",
               "--console=plain", "-Dorg.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=1g"]
    with (output / "publication.log").open("x", encoding="utf-8") as log:
        completed = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, check=False)
    if completed.returncode:
        raise Rejected("staged publication build failed; see publication.log")
    if clean_identity() != (commit, source_sha256):
        raise Rejected("source changed during staged publication build")
    files = {str(path.relative_to(STAGED)): path
             for host in HOST_TASKS for path in artifacts(host).values()}
    if any(path.stat().st_mtime < started for path in files.values()):
        raise Rejected("staged publication is older than this build")
    manifest = {"candidate_commit": commit, "source_sha256": source_sha256,
                "artifact_sha256": {name: digest(path) for name, path in files.items()},
                "publication_log_sha256": digest(output / "publication.log")}
    (output / "publication.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def runtime(host, log_path):
    if host == "linux-x64":
        binaries = list((PORTABLE / "build/bin/linuxX64").rglob("*.kexe"))
        if len(binaries) != 1:
            raise Rejected(f"expected one Linux x64 test binary, found {len(binaries)}")
        binary = binaries[0].resolve()
        return {"host": host, "os": platform.platform(), "machine": platform.machine(),
                "device": False, "executable": str(binary), "executable_sha256": digest(binary),
                "version": platform.platform()}
    needle = "Starting process 'command '" if host.startswith("node-") else "Starting process 'Gradle Test Executor"
    commands = []
    with Path(log_path).open(encoding="utf-8") as stream:
        for line in stream:
            if needle in line and " Command: " in line:
                candidate = line.rsplit(" Command: ", 1)[1].split()[0]
                if not host.startswith("node-") or Path(candidate).name == "node":
                    commands.append(candidate)
    if not commands:
        raise Rejected(f"no executed test runtime command in Gradle log for {host}")
    resolved = Path(commands[-1]).resolve()
    if not resolved.is_file():
        raise Rejected(f"executed runtime is missing: {resolved}")
    result = {"host": host, "os": platform.platform(), "machine": platform.machine(),
              "device": False, "executable": str(resolved), "executable_sha256": digest(resolved)}
    command = (str(resolved), "--version") if host.startswith("node-") else (str(resolved), "-version")
    probe = subprocess.run(command, capture_output=True, text=True, check=False)
    result["version"] = (probe.stdout + probe.stderr).strip().splitlines()[0] if probe.stdout or probe.stderr else "UNAVAILABLE"
    if host == "jvm8" and 'version "1.8.' not in result["version"]:
        raise Rejected("JVM 8 lane did not execute on Java 8")
    return result


def extract_xml(host, output):
    directory = PORTABLE / "build/test-results" / HOST_TASKS[host]
    matching = sorted(directory.glob("TEST-*PortableMatrixTest*.xml"))
    if len(matching) != 1:
        raise Rejected(f"expected one matrix XML for {host}, found {len(matching)}")
    source = matching[0]
    with source.open("rb") as stream:
        stream.readline()
        suite = stream.readline().decode()
    attributes = dict(re.findall(r'([a-z]+)="([^"]*)"', suite))
    shutil.copyfile(source, output / "matrix.xml")
    trace = output / "trace.jsonl"
    cases = output / "cases"
    cases.mkdir()
    expected = {item["id"] for item in declared_cases()}
    observed = {}
    input_records = 0
    case_stream = None
    active_case = None
    with source.open("r", encoding="utf-8") as stream, trace.open("x", encoding="utf-8") as target:
        try:
            for line in stream:
                if "NUMERICAL_JSON " not in line:
                    continue
                payload = line.split("NUMERICAL_JSON ", 1)[1].split("]]>", 1)[0].strip()
                row = json.loads(payload, parse_constant=lambda value: (_ for _ in ()).throw(Rejected(value)))
                target.write(payload + "\n")
                case_id = row.get("id")
                if row.get("kind") == "inputs":
                    input_records += 1
                if case_id in expected:
                    count = observed.setdefault(case_id, {"inputs": 0, "states": 0,
                                                           "events": 0, "endpoints": 0,
                                                           "case_ends": 0, "tagged_nonfinite_values": 0})
                    kind = row.get("kind")
                    field = {"inputs": "inputs", "state": "states", "event": "events",
                             "endpoint": "endpoints", "case-end": "case_ends"}.get(kind)
                    if field is not None:
                        count[field] += 1
                    count["tagged_nonfinite_values"] += payload.count('"nonfinite":')
                if row.get("kind") == "inputs":
                    if case_stream is not None:
                        case_stream.close()
                    active_case = row.get("id")
                    case_stream = ((cases / f"{active_case}.jsonl").open("x", encoding="utf-8")
                                   if active_case in expected else None)
                if case_stream is not None and row.get("id") == active_case:
                    case_stream.write(payload + "\n")
                    if row.get("kind") == "case-end":
                        case_stream.close()
                        case_stream = None
                        active_case = None
        finally:
            if case_stream is not None:
                case_stream.close()
    raw_counts = {"expected_cases": len(expected), "input_records": input_records,
                  "observed_cases": len(observed),
                  "completed_cases": sum(item["case_ends"] == 1 for item in observed.values()),
                  "states": sum(item["states"] for item in observed.values()),
                  "tagged_nonfinite_values": sum(item["tagged_nonfinite_values"] for item in observed.values()),
                  "per_case": observed}
    return trace, attributes, raw_counts


def absent_lane(output, name, commit, source_sha256, status, reason):
    lane = output / name
    lane.mkdir(parents=True, exist_ok=False)
    result = {"host": name, "status": status, "reason": reason,
              "candidate_commit": commit, "source_sha256": source_sha256,
              "expected_cases": len(declared_cases()), "executed_cases": 0,
              "skipped": 0, "qualification": "UNPASSED"}
    (lane / "receipt.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def _compare_frozen_one(job):
    key, source, candidate = job
    try:
        if not candidate.is_file():
            raise Rejected("matching portable case trace is absent")
        return diagnostic(key, source, candidate)
    except (Rejected, OSError, EOFError, StopIteration, KeyError, TypeError, ValueError) as error:
        return {"fixture_key": key, "status": "FAILED",
                "reason": str(error), "qualification": "UNPASSED"}


def compare_frozen(lane, reference_dirs):
    catalog = json.loads(CATALOG.read_text())
    resolved = []
    jobs = []
    for fixture in catalog["fixtures"]:
        key = fixture["key"]
        filename = fixture["reference"]["file"]
        source = next((directory / filename for directory in reference_dirs
                       if (directory / filename).is_file()), None)
        if source is None:
            resolved.append({"fixture_key": key, "status": "UNAVAILABLE_REFERENCE",
                             "expected_reference_sha256": fixture["reference"]["gzip_sha256"],
                             "qualification": "UNPASSED"})
        else:
            jobs.append((key, source, lane / "cases" / f"{portable_case_id(key)}.jsonl"))
            resolved.append(None)
    if jobs:
        with ProcessPoolExecutor(max_workers=min(4, len(jobs))) as pool:
            compared = iter(pool.map(_compare_frozen_one, jobs))
            results = [entry if entry is not None else next(compared) for entry in resolved]
    else:
        results = resolved
    (lane / "frozen-comparison.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    return results


def execute(host, output, commit, source_sha256, reference_dirs):
    lane = output / host
    lane.mkdir(parents=True, exist_ok=False)
    target_artifacts = artifacts(host)
    artifact_sha256 = {name: digest(path) for name, path in target_artifacts.items()}
    started = __import__("time").time()
    env = os.environ.copy()
    env.setdefault("ANDROID_HOME", str(Path.home() / "Android/Sdk"))
    command = [str(ROOT / "gradlew"), "-p", str(PORTABLE), HOST_TASKS[host],
               f"-PportableRepository={ROOT / 'build/staging-repository'}",
               "--rerun-tasks", "--no-daemon", "--console=plain", "--info",
               "-Dorg.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=1g"]
    if host == "jvm8":
        command.extend(("-PportableJvm8=true", "-Dorg.gradle.java.installations.paths=/tmp/dyn4k-tools/jdk8"))
    with (lane / "gradle.log").open("x", encoding="utf-8") as log:
        completed = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
    outcome = {"host": host, "task": HOST_TASKS[host], "gradle_exit": completed.returncode,
               "status": "FAILED" if completed.returncode else "PASSED",
               "qualification": "UNPASSED", "frozen_comparison": "NOT_COMPARABLE_PORTABLE_SCHEMA",
               "candidate_commit": commit, "source_sha256": source_sha256,
               "artifact_sha256": artifact_sha256}
    trace = None
    try:
        xml = sorted((PORTABLE / "build/test-results" / HOST_TASKS[host]).glob("TEST-*PortableMatrixTest*.xml"))
        if len(xml) != 1 or xml[0].stat().st_mtime < started:
            raise Rejected("matrix XML is missing or stale")
        trace, attributes, raw_counts = extract_xml(host, lane)
        outcome["xml"] = attributes
        outcome["raw_counts"] = raw_counts
        outcome["started_cases"] = raw_counts["observed_cases"]
        outcome["executed_cases"] = raw_counts["completed_cases"]
        outcome["incomplete_cases"] = sorted(case_id for case_id, counts in
                                             raw_counts["per_case"].items()
                                             if counts["case_ends"] != 1)
        executed_runtime = runtime(host, lane / "gradle.log")
        outcome["runtime"] = executed_runtime
        comparisons = compare_frozen(lane, reference_dirs)
        outcome["frozen_comparison_results"] = {
            "available": sum(item["status"] != "UNAVAILABLE_REFERENCE" for item in comparisons),
            "unavailable": sum(item["status"] == "UNAVAILABLE_REFERENCE" for item in comparisons),
            "failed": sum(item["status"].startswith("FAILED") for item in comparisons)}
        physical = nominal_free(lane / "cases/long-free-60.jsonl")
        outcome["physical"] = physical
        sleep_ids = ([f"contacts-default-{hz}" for hz in (30, 60, 120)] +
                     [f"contacts-configured-{hz}-r{repetition}"
                      for hz in (30, 60, 120) for repetition in (1, 2)])
        sleep = sleep_wake_rows(chain.from_iterable(
            records(lane / "cases" / f"{case_id}.jsonl", allow_tagged_nonfinite=True)
            for case_id in sleep_ids if (lane / "cases" / f"{case_id}.jsonl").is_file()))
        outcome["sleep_wake_physical"] = sleep
        if completed.returncode:
            raise Rejected("Gradle task failed")
        if any(int(attributes.get(key, "-1")) != expected for key, expected in
               (("tests", 15), ("skipped", 0), ("failures", 0), ("errors", 0))):
            raise Rejected(f"matrix XML reports incomplete tests: {attributes}")
        if clean_identity() != (commit, source_sha256):
            raise Rejected("source changed during host execution")
        identity = Identity(commit, source_sha256, artifact_sha256, executed_runtime)
        sealed = seal(trace, declared_cases(), identity, target_artifacts)
        (lane / "receipt.json").write_text(json.dumps(sealed, indent=2, sort_keys=True) + "\n")
        outcome.update({"xml": attributes, "counts": sealed["counts"], "trace_sha256": sealed["trace_sha256"],
                        "artifact_sha256": identity.artifact_sha256,
                        "frozen_comparison": "UNPASSED"})
        if physical["status"] != "PASSED" or sleep["status"] != "PHYSICAL_PASSED":
            outcome["status"] = "FAILED"
            outcome["reason"] = "physical diagnostic failed"
    except (Rejected, OSError, ValueError, KeyError) as error:
        outcome["status"] = "FAILED"
        outcome["reason"] = str(error)
    if trace is not None and "trace_sha256" not in outcome:
        outcome["trace_sha256"] = digest(trace)
    if not (lane / "receipt.json").exists():
        (lane / "receipt.json").write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\n")
    (lane / "result.json").write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\n")
    return outcome


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--hosts", nargs="+", choices=HOST_TASKS, default=list(HOST_TASKS))
    parser.add_argument("--reference-dir", type=Path, action="append", default=[])
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.exists():
        parser.error("output already exists")
    try:
        commit, source_sha256 = clean_identity()
        output.mkdir(parents=True)
        try:
            publication = stage(output, commit, source_sha256)
        except Rejected as error:
            results = [absent_lane(output, host, commit, source_sha256, "NOT_RUN",
                                   f"Staged publication failed: {error}") for host in HOST_TASKS]
            results += [absent_lane(output, name, commit, source_sha256,
                                    "NOT_RUN" if name == "android-device" else "UNAVAILABLE",
                                    f"Staged publication failed: {error}") for name in OTHER_LANES]
            summary = {"commit": commit, "source_sha256": source_sha256,
                       "status": "FAILED", "reason": str(error), "lanes": results}
            (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
            print(json.dumps(summary, sort_keys=True))
            return 1
        reference_dirs = args.reference_dir or [Path("/tmp/dyn4k-configured-control/baseline-trace")]
        results = [execute(host, output, commit, source_sha256, reference_dirs) for host in args.hosts]
        for host in HOST_TASKS:
            if host not in args.hosts:
                results.append(absent_lane(output, host, commit, source_sha256, "NOT_RUN",
                                           "Host task was not selected for this invocation"))
        for name in OTHER_LANES:
            status = "NOT_RUN" if name == "android-device" else "UNAVAILABLE"
            reason = ("This consumer executed Android host tests only" if name == "android-device"
                      else "Target runtime is not available on this Bazzite host")
            results.append(absent_lane(output, name, commit, source_sha256, status, reason))
        summary = {"commit": commit, "source_sha256": source_sha256,
                   "publication": publication, "lanes": results}
        (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        print(json.dumps(summary, sort_keys=True))
        return 0 if all(result["status"] == "PASSED" for result in results if result["host"] in args.hosts) else 1
    except (Rejected, OSError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "FAILED", "reason": str(error)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
