#!/usr/bin/env python3
import argparse
import csv
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from candidate_runner import (FLAGS, IDENTITY, ROOT, hash_path,
                              read_paths, source_trees, verify_hashes)
from manifest import manifest
from measure import compile_harness, sha256, validate_csv
from sustained_archive import (PROCESS_IMAGE_METHODS, observed_host, observe_process_image,
                               require, require_external_key, signature)


ROUTES = ("baseline", "direct_kotlin", "compatibility")


def require_committed_sources(identity, commit):
    for name, digest in identity["sha256"].items():
        path = Path(name)
        if not path.is_relative_to(ROOT) or path.suffix not in (".java", ".kt", ".kts", ".py", ".json"):
            continue
        relative = path.relative_to(ROOT).as_posix()
        blob = subprocess.run(["git", "show", f"{commit}:{relative}"], cwd=ROOT,
                              capture_output=True, check=True).stdout
        require(hashlib.sha256(blob).hexdigest() == digest,
                f"candidate harness source revision differs: {relative}")


def snapshot(root, source, name):
    source = Path(source)
    if not source.exists():
        return {"source_path": str(source), "absent": True}
    target = root / "inputs" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        shutil.copyfile(source, target)
    digest = hash_path(source)
    require(hash_path(target) == digest, "input changed while snapshotting")
    return {"source_path": str(source), "archive_path": str(target.relative_to(root)),
            "sha256": digest, "directory": source.is_dir()}


def capture(args, key):
    policy = manifest()
    scenario = next(item for item in policy["scenarios"] if item["id"] ==
                    "separated.default.small.30hz.baseline")
    require(1 <= args.seconds <= 5 and 1 <= args.warmup_seconds <= 5,
            "bounded diagnostic duration must be 1 to 5 seconds")
    root = Path(args.archive).resolve()
    require(not root.exists() or not any(root.iterdir()), "archive is not empty")
    require(source_trees(args.expected_source_commit) == source_trees("HEAD"),
            "exact candidate engine source differs")
    identity = json.loads(IDENTITY.read_text())
    require(identity["source_commit"] == args.expected_source_commit and
            identity["source_trees"] == source_trees("HEAD") and
            identity["paths"] == {route: [str(path) for path in paths]
                                  for route, paths in read_paths().items()},
            "candidate staging identity differs")
    require_committed_sources(identity, args.expected_source_commit)
    verify_hashes(identity["sha256"])
    java = Path(args.java).resolve(strict=True)
    javac = Path(args.javac).resolve(strict=True)
    baseline = Path(args.baseline).resolve(strict=True)
    require(str(java) == identity["java"] and
            sha256(baseline) == policy["baseline_jar_sha256"],
            "runtime or pinned baseline differs")
    root.mkdir(parents=True, exist_ok=True)
    (root / "baseline-build").mkdir()
    classes = compile_harness(str(javac), baseline, root / "baseline-build")
    paths = read_paths()
    input_paths = [java, javac, baseline, classes, IDENTITY, Path(sys.executable)]
    input_paths += [Path(path) for path in identity["sha256"]]
    input_paths += [path for values in paths.values() for path in values]
    input_paths = sorted(set(input_paths), key=str)
    inputs = [snapshot(root, path, f"{i:03d}") for i, path in enumerate(input_paths)]
    source_hashes = {str(path): hash_path(path) for path in input_paths if path.exists()}
    index = {"schema": 1, "route": "bounded-jvm-diagnostic-v1",
             "manifest_sha256": sha256(ROOT / "docs/research/performance-manifest-v1.json"),
             "source_commit": args.expected_source_commit,
             "source_trees": source_trees("HEAD"), "host": observed_host(),
             "scenario_id": scenario["id"], "seconds": args.seconds,
             "warmup_seconds": args.warmup_seconds,
             "candidate_identity": identity, "inputs": inputs, "captures": []}
    for route in ROUTES:
        folder = root / "runs" / route
        folder.mkdir(parents=True)
        tail = ["separated", "default", "small", "30", str(30 * args.seconds),
                "timing", str(30 * args.warmup_seconds)]
        command = ([str(java), *FLAGS, "-cp", os.pathsep.join((str(classes), str(baseline))),
                    "BaselinePilot", *tail] if route == "baseline" else
                   [sys.executable, str(ROOT / "tools/performance/candidate_runner.py"),
                    *tail, route])
        raw, stderr = folder / "steps.csv", folder / "stderr.raw"
        clock, warm_clock = folder / "clock.csv", folder / "warmup-clock.csv"
        env = dict(os.environ)
        env.update(DYN4K_CLOCK_CSV=str(clock), DYN4K_WARMUP_CLOCK_CSV=str(warm_clock))
        start = time.monotonic_ns()
        with raw.open("wb") as output, stderr.open("wb") as error:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=output, stderr=error)
            image = None
            for _ in range(200):
                if process.poll() is not None:
                    break
                try:
                    observed = observe_process_image(process.pid)
                    if (observed["sha256"] == sha256(java) and
                            observed["executable_path"] == str(java)):
                        image = observed
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(0.01)
            try:
                code = process.wait(timeout=args.seconds + args.warmup_seconds + 30)
            except subprocess.TimeoutExpired:
                process.kill()
                code = process.wait()
        end = time.monotonic_ns()
        receipt = folder / "process-image.json"
        if image is not None:
            receipt.write_text(json.dumps(image, sort_keys=True) + "\n")
        record = {"api": route, "command": command, "pid": process.pid,
                  "started_ns": start, "ended_ns": end, "exit_code": code,
                  "process_image_receipt_path": str(receipt.relative_to(root)) if image else None,
                  "process_image_receipt_sha256": sha256(receipt) if image else None,
                  "raw_path": str(raw.relative_to(root)), "raw_sha256": sha256(raw),
                  "stderr_path": str(stderr.relative_to(root)),
                  "stderr_sha256": sha256(stderr),
                  "clock_path": str(clock.relative_to(root)) if clock.exists() else None,
                  "clock_sha256": sha256(clock) if clock.exists() else None,
                  "warmup_clock_path": str(warm_clock.relative_to(root)) if warm_clock.exists() else None,
                  "warmup_clock_sha256": sha256(warm_clock) if warm_clock.exists() else None}
        index["captures"].append(record)
    require(all(Path(path).exists() and hash_path(path) == digest
                for path, digest in source_hashes.items()),
            "input bytes changed during execution")
    require(all(not Path(item["source_path"]).exists() for item in inputs
                if item.get("absent")), "absent classpath input appeared during execution")
    index["signature"] = signature(index, key)
    (root / "archive.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    return verify(root, key, args.expected_source_commit)


def verified_file(root, record, stem):
    name = record.get(stem + "_path")
    require(isinstance(name, str) and name and not Path(name).is_absolute() and
            ".." not in Path(name).parts, f"missing {stem} stream")
    path = (root / name).resolve(strict=True)
    require(path.is_relative_to(root) and path.is_file() and
            sha256(path) == record[stem + "_sha256"], f"{stem} bytes differ")
    return path


def verify(root, key, expected_commit):
    root = Path(root).resolve(strict=True)
    index = json.loads((root / "archive.json").read_text())
    require(hmac.compare_digest(index.get("signature", ""), signature(index, key)),
            "archive signature differs")
    require(index["route"] == "bounded-jvm-diagnostic-v1" and
            index["source_commit"] == expected_commit and
            index["source_trees"] == source_trees(expected_commit) and
            index["manifest_sha256"] == sha256(ROOT / "docs/research/performance-manifest-v1.json") and
            index["scenario_id"] == "separated.default.small.30hz.baseline" and
            index["scenario_id"] in {item["id"] for item in manifest()["scenarios"]},
            "source, manifest, or scenario differs")
    require(1 <= index["seconds"] <= 5 and 1 <= index["warmup_seconds"] <= 5,
            "bounded duration differs")
    for item in index["inputs"]:
        if item.get("absent"):
            continue
        path = root / item["archive_path"]
        require(path.resolve().is_relative_to(root) and
                hash_path(path) == item["sha256"], "archived input bytes differ")
    identity = index["candidate_identity"]
    require(identity["source_commit"] == expected_commit and
            identity["source_trees"] == index["source_trees"],
            "candidate identity differs")
    require_committed_sources(identity, expected_commit)
    inputs = {item["source_path"]: item for item in index["inputs"]}
    require(len(inputs) == len(index["inputs"]) and
            json.loads((root / inputs[str(IDENTITY)]["archive_path"]).read_text()) == identity and
            all(inputs.get(path, {}).get("sha256") == digest
                for path, digest in identity["sha256"].items()),
            "candidate identity or classpath bytes differ")
    require([item["api"] for item in index["captures"]] == list(ROUTES),
            "three executed JVM routes are incomplete")
    runtime = inputs[identity["java"]]
    baseline = next(item for item in index["inputs"]
                    if item.get("sha256") == manifest()["baseline_jar_sha256"])
    classes = next(item for item in index["inputs"]
                   if item.get("source_path", "").endswith("/baseline-build/classes"))
    python = next(item for item in index["inputs"]
                  if item.get("source_path") in ("/usr/bin/python3", sys.executable))
    runner = str(ROOT / "tools/performance/candidate_runner.py")
    require(inputs[runner]["sha256"] == identity["sha256"][runner],
            "candidate runner source differs")
    missing_sidecars = []
    for item in index["captures"]:
        raw = verified_file(root, item, "raw")
        stderr = verified_file(root, item, "stderr").read_text()
        receipt = json.loads(verified_file(root, item, "process_image_receipt").read_text())
        require(type(item["exit_code"]) is int and item["exit_code"] == 0 and
                type(item["pid"]) is int and item["pid"] > 0 and
                item["started_ns"] <= receipt["observed_ns"] <= item["ended_ns"] and
                receipt["pid"] == item["pid"] and
                receipt["method"] == PROCESS_IMAGE_METHODS[index["host"]["system"]] and
                receipt["sha256"] == runtime["sha256"] and
                receipt["executable_path"] == identity["java"],
                "executed process image differs")
        tail = ["separated", "default", "small", "30", str(30 * index["seconds"]),
                "timing", str(30 * index["warmup_seconds"])]
        expected_command = ([identity["java"], *FLAGS, "-cp",
                             os.pathsep.join((classes["source_path"], baseline["source_path"])),
                             "BaselinePilot", *tail] if item["api"] == "baseline" else
                            [python["source_path"], runner, *tail, item["api"]])
        require(item["command"] == expected_command,
                "executed fixture command differs")
        validate_csv(raw, "separated", "default", "small", 30, 30 * index["seconds"], "timing")
        warm = [line for line in stderr.splitlines() if line and line[0].isdigit()]
        require(len(warm) == 30 * index["warmup_seconds"], "warm-up samples incomplete")
        absent = []
        if "#fixture_reset_after_warmup=1" not in stderr:
            absent.append("fixture_reset")
        for stem, count in (("clock", 30 * index["seconds"]),
                            ("warmup_clock", 30 * index["warmup_seconds"])):
            if item.get(stem + "_path") is None:
                absent.append(stem)
            else:
                with verified_file(root, item, stem).open(newline="") as stream:
                    rows = list(csv.DictReader(stream))
                require(len(rows) == count and all(int(row["end_ns"]) > int(row["begin_ns"])
                                                   for row in rows), f"{stem} samples incomplete")
        absent.extend(("provider", "attributed_memory", "build_receipt"))
        missing_sidecars.append({"api": item["api"], "fields": absent})
    return {"raw_audit": "verified", "qualification": "unpassed",
            "reason": "bounded diagnostic: duration, reference environment, provider and memory attribution unqualified",
            "executed_routes": 3, "source_commit": expected_commit,
            "scenario_id": index["scenario_id"],
            "missing_sustained_sidecars": missing_sidecars}


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
        result = capture(args, key) if args.command == "capture" else verify(
            args.archive, key, args.expected_source_commit)
        print(json.dumps(result, sort_keys=True))
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"raw_audit": "unpassed", "qualification": "unpassed",
                          "reason": str(exc)}, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
