#!/usr/bin/env python3
import argparse
import contextlib
import csv
import hashlib
import hmac
import json
import io
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

from bounded_adapter import require_committed_sources, snapshot, verified_file
from candidate_runner import (API, CORE, FLAGS, IDENTITY, ROOT, STAGING, hash_path,
                              prepare, read_paths, source_trees)
from manifest import manifest
from measure import sha256, validate_csv
from sustained_archive import (PROCESS_IMAGE_METHODS, canonical, observed_host,
                               observe_process_image, require, require_external_key,
                               signature, validate_process_clock)


ROUTES = ("baseline", "direct_kotlin", "compatibility")
SOURCE = ROOT / "tools/performance/sustained_jvm"
STAGE = ["./gradlew", "--no-daemon", ":dyn4k-core:publishJvmPublicationToStagingRepository",
         ":dyn4k:publishJvmPublicationToStagingRepository"]
FORBIDDEN_JAVA_ENV = ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS", "CLASSPATH")


def fixture_hash(policy):
    return hashlib.sha256(canonical({"fixture": policy["fixture"],
                                     "joint_parameters": policy["joint_parameters"]})).hexdigest()


def _run_build(command, output, env):
    with (output.with_suffix(".stdout")).open("wb") as out, \
            (output.with_suffix(".stderr")).open("wb") as err:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=out, stderr=err,
                                timeout=120)
    require(result.returncode == 0, f"exact-source build failed: {command}")
    return {"command": command, "exit_code": result.returncode,
            "stdout_path": output.with_suffix(".stdout"),
            "stderr_path": output.with_suffix(".stderr")}


def _build(args, root, env):
    build = root / "build"
    build.mkdir()
    stage = _run_build(STAGE, build / "stage", env)
    classes = build / "classes"
    classes.mkdir()
    sources = [SOURCE / "SustainedSidecars.java", SOURCE / "SustainedPilot.java"]
    javac = [str(args.javac), "--release", "21", "-cp", str(args.baseline),
             "-d", str(classes), *map(str, sources)]
    compiled = _run_build(javac, build / "javac", env)
    harness = build / "sustained-harness.jar"
    _run_build([str(args.jar), "--create", "--file", str(harness),
                "-C", str(classes), "."], build / "harness-jar", env)
    gradle = ["./gradlew", "-p", "consumers/performance", "-I",
              str(SOURCE / "direct.init.gradle"),
              f"-PsustainedHarnessJar={harness}", "writeCandidateClasspath", "--offline"]
    consumer = _run_build(gradle, build / "consumer", env)
    adapter_class = ROOT / "consumers/performance/build/classes/kotlin/main/performance/SustainedDirectPilotKt.class"
    require(adapter_class.is_file(), "sustained Kotlin adapter was not compiled")
    adapter = build / "sustained-direct-adapter.jar"
    _run_build([str(args.jar), "--create", "--file", str(adapter), "-C",
                str(adapter_class.parents[1]), "performance/SustainedDirectPilotKt.class"],
               build / "adapter-jar", env)
    with contextlib.redirect_stdout(io.StringIO()):
        prepare(str(args.java), args.expected_source_commit)
    identity = json.loads(IDENTITY.read_text())
    artifacts = {"core": sha256(STAGING / CORE), "kotlin": sha256(STAGING / API)}
    receipt = {"schema": 1, "status": "built_from_exact_source",
               "source_commit": args.expected_source_commit,
               "source_trees": source_trees(args.expected_source_commit),
               "configuration": "development", "target": "jvm",
               "build_java_home": env["JAVA_HOME"],
               "artifact_sha256": artifacts,
               "stage_command": STAGE, "stage_exit_code": stage["exit_code"],
               "consumer_command": gradle, "consumer_exit_code": consumer["exit_code"],
               "javac_command": javac, "javac_exit_code": compiled["exit_code"],
               "harness_sha256": sha256(harness), "adapter_sha256": sha256(adapter),
               "harness_sources": {str(path): sha256(path) for path in sources},
               "direct_source_sha256": sha256(SOURCE / "SustainedDirectPilot.kt"),
               "init_sha256": sha256(SOURCE / "direct.init.gradle")}
    receipt_path = build / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return identity, harness, adapter, receipt_path, receipt


def capture(args, key):
    policy = manifest()
    require(os.name == "posix" and sys.platform.startswith("linux"),
            "available-host producer requires the validated Linux process probe")
    require(1 <= args.seconds <= 5 and 1 <= args.warmup_seconds <= 5,
            "diagnostic duration must be 1 to 5 seconds")
    root = Path(args.archive).resolve()
    require(not root.exists() or not any(root.iterdir()), "archive is not empty")
    require(source_trees(args.expected_source_commit) == source_trees("HEAD"),
            "exact candidate engine source differs")
    java = Path(args.java).resolve(strict=True)
    javac = Path(args.javac).resolve(strict=True)
    baseline = Path(args.baseline).resolve(strict=True)
    jar = java.parent / "jar"
    require(jar.is_file() and sha256(baseline) == policy["baseline_jar_sha256"],
            "runtime or pinned baseline differs")
    args.java, args.javac, args.jar, args.baseline = java, javac, jar, baseline
    root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["JAVA_HOME"] = str(java.parent.parent)
    for name in FORBIDDEN_JAVA_ENV:
        env.pop(name, None)
    identity, harness, adapter, receipt_path, receipt = _build(args, root, env)
    require_committed_sources(identity, args.expected_source_commit)
    paths = read_paths()
    require(identity["paths"] == {route: [str(path) for path in values]
                                  for route, values in paths.items()},
            "candidate classpath differs")
    sources = [SOURCE / name for name in ("SustainedSidecars.java", "SustainedPilot.java",
                                           "SustainedDirectPilot.kt", "direct.init.gradle")]
    inputs = [java, javac, jar, baseline, harness, adapter, IDENTITY, receipt_path,
              *sources, *[Path(name) for name in identity["sha256"]],
              *[path for values in paths.values() for path in values]]
    inputs = sorted(set(inputs), key=str)
    copied = [snapshot(root, path, f"{i:03d}") for i, path in enumerate(inputs)]
    snapshots = {item["source_path"]: item for item in copied}
    source_hashes = {str(path): hash_path(path) for path in inputs if path.exists()}
    index = {"schema": 1, "route": "sustained-jvm-host-v1",
             "producer_root": str(ROOT),
             "manifest_sha256": sha256(ROOT / "docs/research/performance-manifest-v1.json"),
             "source_commit": args.expected_source_commit,
             "source_trees": source_trees(args.expected_source_commit),
             "host": observed_host(), "seconds": args.seconds,
             "warmup_seconds": args.warmup_seconds,
             "fixture_sha256": fixture_hash(policy),
             "candidate_identity": identity, "build_receipt": receipt,
             "inputs": copied, "captures": []}
    for route in ROUTES:
        folder = root / "runs" / route
        folder.mkdir(parents=True)
        tail = ["separated", "default", "small", "30", str(30 * args.seconds),
                "timing", str(30 * args.warmup_seconds)]
        classpath = ([harness, baseline] if route == "baseline" else
                     [adapter, *paths["direct_kotlin"]] if route == "direct_kotlin" else
                     [harness, *paths["compatibility"]])
        main = "performance.SustainedDirectPilotKt" if route == "direct_kotlin" else "SustainedPilot"
        command = [str(java), *FLAGS, "-cp", os.pathsep.join(map(str, classpath)),
                   main, *tail, route]
        outputs = {name: folder / filename for name, filename in
                   (("raw", "steps.csv"), ("stderr", "stderr.raw"),
                    ("clock", "clock.csv"), ("warmup_clock", "warmup-clock.csv"),
                    ("resource", "resource.csv"), ("provider", "provider.json"),
                    ("run", "run.json"), ("clock_origin", "clock-origin.json"),
                    ("clock_origin_receipt", "clock-origin-receipt.json"))}
        clock_nonce = secrets.token_hex(16)
        run_env = dict(env)
        run_env.update(DYN4K_CLOCK_CSV=str(outputs["clock"]),
                       DYN4K_WARMUP_CLOCK_CSV=str(outputs["warmup_clock"]),
                       DYN4K_CLOCK_ORIGIN_JSON=str(outputs["clock_origin"]),
                       DYN4K_CLOCK_NONCE=clock_nonce,
                       DYN4K_RESOURCE_CSV=str(outputs["resource"]),
                       DYN4K_PROVIDER_JSON=str(outputs["provider"]),
                       DYN4K_RUN_JSON=str(outputs["run"]),
                       DYN4K_SOURCE_COMMIT=args.expected_source_commit,
                       DYN4K_BASELINE_SHA256=policy["baseline_jar_sha256"],
                       DYN4K_ARTIFACT_HASHES_JSON=json.dumps(receipt["artifact_sha256"], sort_keys=True))
        start = time.monotonic_ns()
        with outputs["raw"].open("wb") as out, outputs["stderr"].open("wb") as err:
            process = subprocess.Popen(command, cwd=ROOT, env=run_env, stdout=out, stderr=err)
            observed = None
            for _ in range(200):
                if process.poll() is not None:
                    break
                try:
                    image = observe_process_image(process.pid)
                    if image["sha256"] == sha256(java) and image["executable_path"] == str(java):
                        observed = image
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(0.01)
            if observed is None:
                process.kill()
                process.wait()
                raise ValueError("executed process image was not observed")
            origin = None
            for _ in range(500):
                if outputs["clock_origin"].is_file():
                    try:
                        origin = json.loads(outputs["clock_origin"].read_text())
                    except (OSError, ValueError):
                        pass
                    else:
                        if (set(origin) == {"pid", "runtime_ns", "nonce"} and
                                origin["pid"] == process.pid and
                                type(origin["runtime_ns"]) is int and
                                origin["nonce"] == clock_nonce):
                            break
                        origin = None
                if process.poll() is not None:
                    break
                time.sleep(0.01)
            if origin is None:
                process.kill()
                process.wait()
                raise ValueError("process clock origin was not observed")
            outputs["clock_origin_receipt"].write_text(json.dumps({**origin,
                "method": "host_file_bracket_v1", "host_before_ns": start,
                "host_after_ns": time.monotonic_ns()}, sort_keys=True) + "\n")
            try:
                code = process.wait(timeout=args.seconds + args.warmup_seconds + 30)
                termination = "completed"
            except subprocess.TimeoutExpired:
                process.kill()
                code = process.wait()
                termination = "wall_limit"
        end = time.monotonic_ns()
        image_path = folder / "process-image.json"
        image_path.write_text(json.dumps(observed, sort_keys=True) + "\n")
        record = {"api": route, "scenario_id": f"separated.default.small.30hz.{route}",
                  "seconds": args.seconds, "warmup_seconds": args.warmup_seconds,
                  "mode": "timing", "command": command,
                  "classpath": list(map(str, classpath)), "pid": process.pid,
                  "started_ns": start, "ended_ns": end, "exit_code": code,
                  "termination_reason": termination, "clock_nonce": clock_nonce}
        for stem, path in {**outputs, "process_image_receipt": image_path}.items():
            if path.is_file():
                record[stem + "_path"] = str(path.relative_to(root))
                record[stem + "_sha256"] = sha256(path)
        index["captures"].append(record)
    require(all(Path(path).exists() and hash_path(path) == digest
                for path, digest in source_hashes.items()),
            "source or staged input changed during execution")
    require(all(not Path(item["source_path"]).exists() for item in copied
                if item.get("absent")), "absent classpath input appeared")
    index["signature"] = signature(index, key)
    (root / "archive.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    return verify(root, key, args.expected_source_commit)


def _rows(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def _clock(rows, raw, field):
    require(len(rows) == len(raw), f"{field} sample count differs")
    require([int(row["step"] if field == "clock" else row["warmup_step"])
             for row in rows] == list(range(len(rows))), f"{field} sequence differs")
    require(all(int(row["end_ns"]) > int(row["begin_ns"]) for row in rows),
            f"{field} clock is invalid")
    if field == "clock":
        require(all(int(clock["end_ns"]) - int(clock["begin_ns"]) ==
                    int(step["elapsed_ns"]) for clock, step in zip(rows, raw)),
                "clock and raw elapsed samples differ")


def verify(root, key, expected_commit):
    root = Path(root).resolve(strict=True)
    index = json.loads((root / "archive.json").read_text())
    require(hmac.compare_digest(index.get("signature", ""), signature(index, key)),
            "archive signature differs")
    policy = manifest()
    require(index["schema"] == 1 and index["route"] == "sustained-jvm-host-v1" and
            index["source_commit"] == expected_commit and
            index["source_trees"] == source_trees(expected_commit) and
            index["manifest_sha256"] == sha256(ROOT / "docs/research/performance-manifest-v1.json") and
            index["fixture_sha256"] == fixture_hash(policy),
            "source, manifest, or fixture differs")
    require(1 <= index["seconds"] <= 5 and 1 <= index["warmup_seconds"] <= 5,
            "diagnostic duration differs")
    inputs = {item["source_path"]: item for item in index["inputs"]}
    require(len(inputs) == len(index["inputs"]), "duplicate input")
    producer_root = Path(index["producer_root"])
    require(producer_root.is_absolute(), "producer source root differs")
    producer_source = producer_root / "tools/performance/sustained_jvm"
    producer_identity = producer_root / "consumers/performance/build/candidate-identity.json"
    producer_staging = producer_root / "build/staging-repository"
    for item in index["inputs"]:
        if item.get("absent"):
            continue
        path = root / item["archive_path"]
        require(path.resolve().is_relative_to(root) and
                hash_path(path) == item["sha256"], "archived input bytes differ")
    identity = index["candidate_identity"]
    require(identity["source_commit"] == expected_commit and
            identity["source_trees"] == index["source_trees"] and
            all(inputs.get(name, {}).get("sha256") == digest
                for name, digest in identity["sha256"].items()) and
            json.loads((root / inputs[str(producer_identity)]["archive_path"]).read_text()) == identity,
            "candidate identity differs")
    for path_text, digest in identity["sha256"].items():
        path = Path(path_text)
        if (not path.is_relative_to(producer_root) or path.suffix not in
                (".java", ".kt", ".kts", ".py", ".json")):
            continue
        relative = path.relative_to(producer_root).as_posix()
        blob = subprocess.run(["git", "show", f"{expected_commit}:{relative}"],
                              cwd=ROOT, capture_output=True, check=True).stdout
        require(hashlib.sha256(blob).hexdigest() == digest,
                f"candidate harness source revision differs: {relative}")
    receipt = index["build_receipt"]
    receipt_source = next(item for item in index["inputs"]
                          if item["source_path"].endswith("/build/receipt.json"))
    build_root = Path(receipt_source["source_path"]).parent
    expected_consumer = ["./gradlew", "-p", "consumers/performance", "-I",
                         str(producer_source / "direct.init.gradle"),
                         f"-PsustainedHarnessJar={build_root / 'sustained-harness.jar'}",
                         "writeCandidateClasspath", "--offline"]
    baseline_path = next(source for source, record in inputs.items()
                         if record.get("sha256") == policy["baseline_jar_sha256"])
    javac_path = next(source for source in inputs if source.endswith("/bin/javac"))
    expected_javac = [javac_path, "--release", "21", "-cp", baseline_path,
                      "-d", str(build_root / "classes"),
                      str(producer_source / "SustainedSidecars.java"),
                      str(producer_source / "SustainedPilot.java")]
    require(json.loads((root / receipt_source["archive_path"]).read_text()) == receipt and
            receipt["schema"] == 1 and receipt["status"] == "built_from_exact_source" and
            receipt["source_commit"] == expected_commit and
            receipt["source_trees"] == index["source_trees"] and
            receipt["stage_command"] == STAGE and receipt["stage_exit_code"] == 0 and
            receipt["consumer_command"] == expected_consumer and
            receipt["javac_command"] == expected_javac and
            receipt["target"] == "jvm" and receipt["configuration"] == "development" and
            receipt["build_java_home"] == str(Path(identity["java"]).parent.parent) and
            receipt["consumer_exit_code"] == 0 and receipt["javac_exit_code"] == 0 and
            receipt["artifact_sha256"] == {"core": inputs[str(producer_staging / CORE)]["sha256"],
                                            "kotlin": inputs[str(producer_staging / API)]["sha256"]},
            "exact-source build command or receipt differs")
    require(all(inputs[path]["sha256"] == digest for path, digest in
                receipt["harness_sources"].items()) and
            inputs[str(producer_source / "SustainedDirectPilot.kt")]["sha256"] == receipt["direct_source_sha256"] and
            inputs[str(producer_source / "direct.init.gradle")]["sha256"] == receipt["init_sha256"],
            "harness source receipt differs")
    for path in (producer_source / "SustainedSidecars.java", producer_source / "SustainedPilot.java",
                 producer_source / "SustainedDirectPilot.kt", producer_source / "direct.init.gradle"):
        relative = path.relative_to(producer_root).as_posix()
        committed = subprocess.run(["git", "show", f"{expected_commit}:{relative}"],
                                   cwd=ROOT, capture_output=True)
        if committed.returncode == 0:
            require(hashlib.sha256(committed.stdout).hexdigest() == inputs[str(path)]["sha256"],
                    f"committed sustained harness source differs: {relative}")
    harness = next(item for item in index["inputs"]
                   if item["source_path"].endswith("/build/sustained-harness.jar"))
    adapter = next(item for item in index["inputs"]
                   if item["source_path"].endswith("/build/sustained-direct-adapter.jar"))
    require(harness["sha256"] == receipt["harness_sha256"] and
            adapter["sha256"] == receipt["adapter_sha256"],
            "harness or adapter binary differs")
    java = identity["java"]
    require(inputs[java]["sha256"] == identity["sha256"].get(java, inputs[java]["sha256"]),
            "runtime bytes differ")
    require(len(index["captures"]) == 3 and
            [item["api"] for item in index["captures"]] == list(ROUTES),
            "executed API routes differ")
    for item in index["captures"]:
        route = item["api"]
        require(item["scenario_id"] == f"separated.default.small.30hz.{route}" and
                item["scenario_id"] in {case["id"] for case in policy["scenarios"]} and
                item["seconds"] == index["seconds"] and
                item["warmup_seconds"] == index["warmup_seconds"] and
                item["mode"] == "timing", "scenario or duration differs")
        classpath = ([harness["source_path"], next(source for source in inputs
                      if inputs[source].get("sha256") == policy["baseline_jar_sha256"])]
                     if route == "baseline" else
                     [adapter["source_path"], *identity["paths"]["direct_kotlin"]]
                     if route == "direct_kotlin" else
                     [harness["source_path"], *identity["paths"]["compatibility"]])
        tail = ["separated", "default", "small", "30", str(30 * index["seconds"]),
                "timing", str(30 * index["warmup_seconds"])]
        command = [java, *FLAGS, "-cp", os.pathsep.join(classpath),
                   "performance.SustainedDirectPilotKt" if route == "direct_kotlin" else "SustainedPilot",
                   *tail, route]
        require(item["command"] == command and item["classpath"] == classpath and
                all(path in inputs for path in classpath), "executed command or classpath differs")
        require(type(item["exit_code"]) is int and item["exit_code"] == 0 and
                item["termination_reason"] == "completed", "run exit or termination differs")
        image = json.loads(verified_file(root, item, "process_image_receipt").read_text())
        require(type(item["pid"]) is int and item["pid"] > 0 and
                image["pid"] == item["pid"] and
                item["started_ns"] <= image["observed_ns"] <= item["ended_ns"] and
                image["method"] == PROCESS_IMAGE_METHODS[index["host"]["system"]] and
                image["sha256"] == inputs[java]["sha256"] and
                image["executable_path"] == java,
                "executed process image differs")
        raw_path = verified_file(root, item, "raw")
        validate_csv(raw_path, "separated", "default", "small", 30,
                     30 * index["seconds"], "timing")
        raw = _rows(raw_path)
        stderr = verified_file(root, item, "stderr").read_text()
        require("#fixture_reset_after_warmup=1" in stderr and
                len([line for line in stderr.splitlines() if line and line[0].isdigit()]) ==
                30 * index["warmup_seconds"], "fixture reset or warm-up samples differ")
        measured_clock = _rows(verified_file(root, item, "clock"))
        _clock(measured_clock, raw, "clock")
        warm_clock = _rows(verified_file(root, item, "warmup_clock"))
        require(len(warm_clock) == 30 * index["warmup_seconds"],
                "warm-up clock sample count differs")
        _clock(warm_clock, warm_clock, "warmup_clock")
        validate_process_clock(root, item, warm_clock, measured_clock,
                               image["observed_ns"])
        resource = _rows(verified_file(root, item, "resource"))
        require([row["phase"] for row in resource] ==
                ["empty", "construction"] + ["warmup"] * len(warm_clock) +
                ["measure"] * len(raw) and
                [int(row["step"]) for row in resource[2:2 + len(warm_clock)]] ==
                list(range(len(warm_clock))) and
                [int(row["step"]) for row in resource[2 + len(warm_clock):]] ==
                list(range(len(raw))) and
                all(int(row["heap_used_bytes"]) >= 0 and int(row["rss_bytes"]) >= -1
                    for row in resource), "resource stream differs")
        measured = [row for row in resource if row["phase"] == "measure"]
        require(all(int(row["heap_used_bytes"]) == int(step["heap_used_bytes"]) and
                    int(row["rss_bytes"]) == int(step["rss_bytes"]) and
                    int(row["allocation_bytes"]) == int(step["allocation_bytes"])
                    for row, step in zip(measured, raw)), "resource and raw samples differ")
        provider = json.loads(verified_file(root, item, "provider").read_text())
        require(provider["pid"] == item["pid"] and
                provider["runtime_sha256"] == image["sha256"] and
                provider["source_commit"] == expected_commit and provider["api"] == route and
                provider["artifact_sha256"] == receipt["artifact_sha256"] and
                provider["baseline_sha256"] == policy["baseline_jar_sha256"] and
                provider["loaded_core_sha256"] == (policy["baseline_jar_sha256"] if route == "baseline"
                    else receipt["artifact_sha256"]["core"]) and
                provider["loaded_kotlin_sha256"] == (receipt["artifact_sha256"]["kotlin"]
                    if route == "direct_kotlin" else None) and
                provider["loaded_harness_sha256"] == harness["sha256"] and
                provider["loaded_adapter_sha256"] == (adapter["sha256"]
                    if route == "direct_kotlin" else harness["sha256"]) and
                provider["loaded_fixture_sha256"] == index["fixture_sha256"],
                "loaded provider or resource identity differs")
        run = json.loads(verified_file(root, item, "run").read_text())
        awake = sum(int(row["awake_count"]) > 0 for row in raw)
        require(run["api"] == route and run["mode"] == "timing" and
                run["sample_count"] == len(raw) and
                run["warmup_count"] == len(warm_clock) and
                run["measured_wall_ns"] >= (len(raw) - 1) * 1_000_000_000 // 30 and
                run["measured_wall_ns"] >=
                int(measured_clock[-1]["end_ns"]) - int(measured_clock[0]["begin_ns"]) and
                run["measured_wall_ns"] <= item["ended_ns"] - item["started_ns"] and
                run["status"] == "complete", "run sample or duration differs")
        require(run["active_steps"] == awake and awake > 0,
                "run activity differs")
        require(run["memory_attribution"] == "unvalidated" and
                run["peak_heap_used_bytes"] == max(int(row["heap_used_bytes"]) for row in resource) and
                run["peak_rss_bytes"] == max(int(row["rss_bytes"]) for row in resource),
                "resource summary differs")
    return {"raw_audit": "verified", "qualification": "unpassed", "executed_routes": 3,
            "source_commit": expected_commit,
            "missing_qualification": ["600-second duration", "three fresh repeats per case",
                                      "all 999 scenarios", "validated reference rows",
                                      "calibrated noise", "memory attribution",
                                      "approved optimized harness and policy ceilings"]}


def restore_consumer_build(java, source_commit):
    env = dict(os.environ, JAVA_HOME=str(Path(java).resolve().parent.parent))
    result = subprocess.run(["./gradlew", "-p", "consumers/performance",
                             "writeCandidateClasspath", "--offline", "--rerun-tasks"],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    require(result.returncode == 0, f"consumer build restoration failed: {result.stderr}")
    with contextlib.redirect_stdout(io.StringIO()):
        prepare(str(Path(java).resolve()), source_commit)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("capture", "verify"))
    parser.add_argument("--archive", required=True)
    parser.add_argument("--trusted-key", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--java")
    parser.add_argument("--javac")
    parser.add_argument("--baseline")
    parser.add_argument("--seconds", type=int, default=1)
    parser.add_argument("--warmup-seconds", type=int, default=1)
    args = parser.parse_args()
    try:
        require_external_key(args.trusted_key, [args.archive])
        key = Path(args.trusted_key).read_bytes()
        require(len(key) >= 32, "trusted key is too short")
        if args.command == "capture":
            require(all((args.java, args.javac, args.baseline)),
                    "capture requires java, javac, and baseline")
        if args.command == "capture":
            try:
                result = capture(args, key)
            finally:
                restore_consumer_build(args.java, args.expected_source_commit)
        else:
            result = verify(args.archive, key, args.expected_source_commit)
        print(json.dumps(result, sort_keys=True))
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, TypeError) as exc:
        print(json.dumps({"raw_audit": "unpassed", "qualification": "unpassed",
                          "reason": str(exc)}, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
