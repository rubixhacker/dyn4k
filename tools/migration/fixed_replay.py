#!/usr/bin/env python3

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import journeys


IDENTITY = ("sample_revision", "source_manifest_sha256", "power", "angle", "dt",
            "prelude_steps", "steps", "ccd", "observation_stride", "cue_velocity",
            "jvm_identity_hash_mode", "jvm_identity_hash_probe", "jvm_input_arguments",
            "reset_state", "prelude_state", "prelude_pairs")
HASH_MODE = 2
HASH_FLAGS = ["-XX:+UnlockExperimentalVMOptions", "-XX:hashCode=2"]
LIMITS = {"x": (1e-4, "m"), "y": (1e-4, "m"),
          "vx": (1e-3, "m/s"), "vy": (1e-3, "m/s"),
          "angle": (1e-4, "rad"), "omega": (1e-3, "rad/s"),
          "depth": (1e-4, "m"), "time": (1e-6, "step fraction")}
STEP_FIELDS = ("kind", "step", "body_count", "joint_count", "gravity", "bodies", "contacts",
               "toi_events", "ccd_pairs", "ccd_candidates", "contact_begin", "contact_persist", "contact_end",
               "toi_calls", "toi_hits", "toi_listener_hits")
BODY_FIELDS = ("i", "x", "y", "vx", "vy", "angle", "omega", "rest", "bullet", "fixtures",
               "mass", "inertia", "linear_damping", "angular_damping", "identity_hash",
               "fixture_identity_hashes")


def read_stream(path, provider, expected_sha):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows or rows[0].get("kind") != "input":
        raise ValueError(f"{provider} stream lacks input identity")
    header = rows[0]
    if header.get("provider") != provider:
        raise ValueError(f"{provider} stream has wrong provider")
    if header.get("artifact_sha256") != expected_sha:
        return rows, {"path": "input.artifact_sha256", "baseline": expected_sha,
                      "candidate": header.get("artifact_sha256")}
    for key, expected in (("jvm_identity_hash_mode", HASH_MODE),
                          ("jvm_identity_hash_probe", 1),
                          ("jvm_input_arguments", HASH_FLAGS)):
        if header.get(key) != expected:
            return rows, {"path": f"{provider}.input.{key}", "expected": expected,
                          "observed": header.get(key)}
    expected_jar = "dyn4j-6.0.0.jar" if provider == "baseline" else journeys.CANDIDATE_JAR
    for key, expected in (("world_code_source", "file:/work/lib/" + expected_jar),
                          ("java_home", "/jdk")):
        if header.get(key) != expected:
            return rows, {"path": f"{provider}.input.{key}", "expected": expected,
                          "observed": header.get(key)}
    if not isinstance(header.get("java_version"), str) or not header["java_version"].startswith("21."):
        return rows, {"path": f"{provider}.input.java_version", "expected": "JDK 21",
                      "observed": header.get("java_version")}
    for key, step in (("reset_state", -120), ("prelude_state", -1)):
        state = header.get(key)
        if not isinstance(state, dict) or state.get("kind") != "step" or state.get("step") != step:
            return rows, {"path": f"{provider}.input.{key}", "reason": "missing or invalid state"}
    for index, row in enumerate(rows[1:]):
        if row.get("kind") != "step" or row.get("step") != index:
            return rows, {"path": "step.sequence", "expected": index, "observed": row.get("step")}
    if len(rows) != header.get("steps", -1) + 2:
        return rows, {"path": "step.sequence", "expected": header.get("steps", -1) + 1,
                      "observed": len(rows) - 1}
    return rows, None


def finite_tree(value):
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(finite_tree(item) for item in value)
    if isinstance(value, dict):
        return all(finite_tree(item) for item in value.values())
    return True


def whole_count(value):
    return type(value) is int and value >= 0


def body_pair(pair, body_count):
    return (isinstance(pair, list) and len(pair) == 2 and
            all(type(item) is int and 0 <= item < body_count for item in pair))


def validate_step(row, path, contact_counts, toi_count):
    for field in STEP_FIELDS:
        if field not in row:
            return {"path": f"{path}.{field}", "reason": "missing channel"}, toi_count
    for field in ("step", "body_count", "joint_count", "contact_begin", "contact_persist",
                  "contact_end", "toi_calls", "toi_hits", "toi_listener_hits"):
        if type(row[field]) is not int or (field != "step" and row[field] < 0):
            return {"path": f"{path}.{field}", "reason": "invalid count"}, toi_count
    if row["kind"] != "step":
        return {"path": f"{path}.kind", "reason": "invalid state kind"}, toi_count
    if not isinstance(row["gravity"], list) or len(row["gravity"]) != 2 or any(
        type(value) not in (int, float) for value in row["gravity"]
    ):
        return {"path": f"{path}.gravity", "reason": "invalid gravity"}, toi_count
    if not isinstance(row["bodies"], list) or len(row["bodies"]) != row["body_count"]:
        return {"path": f"{path}.bodies", "reason": "body count mismatch"}, toi_count
    for index, body in enumerate(row["bodies"]):
        body_path = f"{path}.bodies[{index}]"
        if not isinstance(body, dict) or body.get("i") != index:
            return {"path": body_path + ".i", "reason": "body order mismatch"}, toi_count
        for field in BODY_FIELDS:
            if field not in body:
                return {"path": f"{body_path}.{field}", "reason": "missing channel"}, toi_count
        for field in ("x", "y", "vx", "vy", "angle", "omega", "mass", "inertia",
                      "linear_damping", "angular_damping"):
            if type(body[field]) not in (int, float):
                return {"path": f"{body_path}.{field}", "reason": "invalid body value"}, toi_count
        for field in ("rest", "bullet"):
            if type(body[field]) is not bool:
                return {"path": f"{body_path}.{field}", "reason": "invalid body flag"}, toi_count
        if not whole_count(body["fixtures"]):
            return {"path": body_path + ".fixtures", "reason": "invalid fixture count"}, toi_count
        if type(body["identity_hash"]) is not int or body["identity_hash"] != 1 or (
            not isinstance(body["fixture_identity_hashes"], list) or
            len(body["fixture_identity_hashes"]) != body["fixtures"] or
            any(type(value) is not int or value != 1 for value in body["fixture_identity_hashes"])
        ):
            return {"path": body_path + ".identity_hash",
                    "reason": "constant identity-hash behavior absent"}, toi_count
    for field in ("ccd_pairs", "ccd_candidates"):
        if not isinstance(row[field], list) or any(
            not body_pair(pair, row["body_count"]) for pair in row[field]
        ):
            return {"path": f"{path}.{field}", "reason": "CCD pair order channel incomplete"}, toi_count
    if not isinstance(row["contacts"], list):
        return {"path": f"{path}.contacts", "reason": "contact events missing"}, toi_count
    for event in row["contacts"]:
        if (not isinstance(event, dict) or not {"kind", "a", "b", "x", "y", "depth"} <= event.keys() or
            event["kind"] not in contact_counts or
            not body_pair([event["a"], event["b"]], row["body_count"]) or
            any(type(event[field]) not in (int, float) for field in ("x", "y", "depth"))
        ):
            return {"path": f"{path}.contacts", "reason": "contact event incomplete"}, toi_count
        contact_counts[event["kind"]] += 1
    if any(row[f"contact_{kind}"] != count for kind, count in contact_counts.items()):
        return {"path": f"{path}.contacts", "reason": "contact counter differs from events"}, toi_count
    if not isinstance(row["toi_events"], list):
        return {"path": f"{path}.toi_events", "reason": "TOI events missing"}, toi_count
    for event in row["toi_events"]:
        if (not isinstance(event, dict) or not {"a", "b", "time"} <= event.keys() or
            not body_pair([event["a"], event["b"]], row["body_count"]) or
            type(event["time"]) not in (int, float)
        ):
            return {"path": f"{path}.toi_events", "reason": "TOI event incomplete"}, toi_count
        toi_count += 1
    if row["toi_listener_hits"] != toi_count:
        return {"path": f"{path}.toi_events", "reason": "TOI counter differs from events"}, toi_count
    return None, toi_count


def missing_channel(rows, provider):
    for key in ("reset_state", "prelude_state"):
        error, _ = validate_step(rows[0][key], f"{provider}.input.{key}",
                                 {"begin": 0, "persist": 0, "end": 0}, 0)
        if error:
            return error
    prelude_pairs = rows[0].get("prelude_pairs")
    if rows[0].get("prelude_steps") != 120 or not isinstance(prelude_pairs, list) or len(prelude_pairs) != 120 or any(
        not isinstance(pairs, list) or any(
            not body_pair(pair, rows[0]["reset_state"]["body_count"]) for pair in pairs
        ) for pairs in prelude_pairs
    ):
        return {"path": f"{provider}.input.prelude_pairs", "reason": "missing or invalid pair order"}
    contact_counts = {"begin": 0, "persist": 0, "end": 0}
    toi_count = 0
    for index, row in enumerate(rows[1:]):
        error, toi_count = validate_step(row, f"{provider}.step[{index}]", contact_counts, toi_count)
        if error:
            return error
    return None


def first_difference(left, right, path="", limits=LIMITS):
    if type(left) is not type(right):
        return {"path": path, "baseline": left, "candidate": right}
    if isinstance(left, dict):
        if left.keys() != right.keys():
            return {"path": path + ".keys", "baseline": sorted(left), "candidate": sorted(right)}
        for key in left:
            difference = first_difference(left[key], right[key], f"{path}.{key}" if path else key, limits)
            if difference:
                return difference
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return {"path": path + ".length", "baseline": len(left), "candidate": len(right)}
        for index, (a, b) in enumerate(zip(left, right)):
            difference = first_difference(a, b, f"{path}[{index}]", limits)
            if difference:
                return difference
        return None
    field = path.rsplit(".", 1)[-1]
    if field in limits and type(left) in (int, float):
        bound, unit = limits[field]
        if abs(left - right) > bound:
            return {"path": path, "baseline": left, "candidate": right,
                    "absolute_difference": abs(left - right), "limit": bound, "unit": unit}
    elif left != right:
        return {"path": path, "baseline": left, "candidate": right}
    return None


def repeatability_difference(first, second):
    if len(first) != len(second):
        return {"path": "step.sequence", "first_count": len(first) - 1,
                "repeat_count": len(second) - 1}
    for index, (left, right) in enumerate(zip(first, second)):
        difference = first_difference(left, right, "input" if index == 0 else f"step[{index - 1}]", {})
        if difference:
            return difference
    return None


def process_identity(stderr):
    markers = [line for line in stderr.splitlines() if line.startswith("REPLAY_PROCESS ")]
    if len(markers) != 1 or " start_ms=" not in markers[0]:
        raise ValueError("replay process identity missing or ambiguous")
    return markers[0]


def ordering_difference(left, right, index):
    for body_index, (body_a, body_b) in enumerate(zip(left["bodies"], right["bodies"])):
        for field in ("identity_hash", "fixture_identity_hashes"):
            difference = first_difference(body_a[field], body_b[field],
                                          f"step[{index}].bodies[{body_index}].{field}", {})
            if difference:
                return difference
    for field in ("ccd_pairs", "ccd_candidates"):
        difference = first_difference(left[field], right[field], f"step[{index}].{field}", {})
        if difference:
            return difference
    return None


def compare(baseline_path, candidate_path, baseline_sha, candidate_sha):
    baseline, bad_baseline = read_stream(baseline_path, "baseline", baseline_sha)
    candidate, bad_candidate = read_stream(candidate_path, "candidate", candidate_sha)
    divergence = bad_baseline or bad_candidate
    if divergence is None:
        divergence = missing_channel(baseline, "baseline") or missing_channel(candidate, "candidate")
    if divergence is None:
        for name, rows in (("baseline", baseline), ("candidate", candidate)):
            if not finite_tree(rows):
                divergence = {"path": name + ".nonfinite", "reason": "non-finite number"}
                break
            if rows[-1]["toi_hits"] <= 0 or rows[-1]["toi_listener_hits"] <= 0:
                divergence = {"path": name + ".ccd_activity", "reason": "no observed TOI hit"}
                break
            if rows[-1]["contact_begin"] <= 0:
                divergence = {"path": name + ".contact_activity", "reason": "no observed contact begin"}
                break
    schema_valid = divergence is None
    if divergence is None:
        for key in IDENTITY:
            if key not in baseline[0] or key not in candidate[0]:
                divergence = {"path": "input." + key, "baseline": baseline[0].get(key),
                              "candidate": candidate[0].get(key)}
                break
            divergence = first_difference(baseline[0][key], candidate[0][key], "input." + key, {})
            if divergence:
                break
    ordering_divergence = None
    if schema_valid and baseline[0]["prelude_pairs"] != candidate[0]["prelude_pairs"]:
        ordering_divergence = first_difference(baseline[0]["prelude_pairs"], candidate[0]["prelude_pairs"],
                                               "input.prelude_pairs", {})
    if divergence is None:
        ignored = {"toi_calls"}
        for index, (a, b) in enumerate(zip(baseline[1:], candidate[1:])):
            step_ordering = ordering_difference(a, b, index)
            if ordering_divergence is None:
                ordering_divergence = step_ordering
            if divergence is None:
                divergence = step_ordering or first_difference(
                    {k: v for k, v in a.items() if k not in ignored},
                    {k: v for k, v in b.items() if k not in ignored}, f"step[{index}]")
    return {"status": "FAILED" if divergence else "PASSED", "first_divergence": divergence,
            "ordering_identity": {"status": ("NOT_RUN" if divergence and not ordering_divergence else
                                            "FAILED" if ordering_divergence else "PASSED"),
                                  "first_divergence": ordering_divergence},
            "compared_observations": min(len(baseline), len(candidate)) - 1,
            "rules": {key: {"absolute": bound, "unit": unit} for key, (bound, unit) in LIMITS.items()},
            "toi_detector_calls": {"baseline": [r.get("toi_calls") for r in baseline[1:]],
                                   "candidate": [r.get("toi_calls") for r in candidate[1:]]}}


def run_fixed(args):
    commit = journeys.require_clean_candidate()
    source = journeys.inspect_samples(args.samples)
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("fixed replay output directory is not empty")
    args.output.mkdir(parents=True)
    report = {"candidate_commit": commit, "source_revision": source["revision"],
              "source_manifest_sha256": source["manifest_sha256"],
              "jdk": str(args.jdk.resolve()), "image": args.headful_image,
              "controls": {"power": args.power, "angle": args.angle, "dt": args.dt,
                           "prelude_steps": 120,
                           "steps": args.steps, "ccd": args.ccd, "observation_stride": 1,
                           "jvm_identity_hash_mode": HASH_MODE},
              "providers": {}, "repeatability": {}, "status": "FAILED"}
    try:
        image = subprocess.run(["podman", "image", "inspect", "--format", "{{.Id}}", args.headful_image],
                               capture_output=True, text=True, timeout=30)
        (args.output / "image-inspect.log").write_text(image.stdout + image.stderr)
        if image.returncode or not image.stdout.strip():
            raise ValueError("headful image unavailable")
        report["image_id"] = image.stdout.strip()
        script = Path(__file__).with_name("run-fixed-scene.sh")
        fixture = journeys.ROOT / "consumers/migration/src/main/java/org/dyn4j/samples/framework/BilliardsReplay.java"
        report["fixture_sha256"] = hashlib.sha256(fixture.read_bytes()).hexdigest()
        report["script_sha256"] = hashlib.sha256(script.read_bytes()).hexdigest()
        for provider in journeys.PROVIDERS:
            directory = args.output / provider
            directory.mkdir()
            resolved = args.resolved_root / provider
            compilation = journeys.compile_samples(provider, args.samples, resolved, args.repository,
                                                   directory / "compile", args.javac)
            if compilation["status"] != "PASSED":
                raise ValueError(provider + " unchanged sample compilation failed: " + str(compilation["reason"]))
            artifacts = journeys.inspect_artifacts(provider, resolved, args.repository)
            primary = "dyn4j-6.0.0.jar" if provider == "baseline" else journeys.CANDIDATE_JAR
            artifact_sha = next(jar["sha256"] for jar in artifacts["jars"] if jar["name"] == primary)
            classes = directory / "compile/classes"
            classpath = os.pathsep.join([str(classes), *map(str, sorted(resolved.glob("*.jar")))])
            javac = [str(args.javac), "--release", "8", "-cp", classpath, "-d", str(classes), str(fixture)]
            (directory / "fixture-command.json").write_text(json.dumps(javac, indent=2) + "\n")
            if journeys.subprocess_log(javac, directory / "fixture-javac.log"):
                raise ValueError(provider + " replay fixture compilation failed")
            dependency_cp = ":".join("/work/lib/" + jar["name"] for jar in artifacts["jars"])
            command = ["podman", "run", "--rm", "--network=none", "--userns=keep-id",
                       "--security-opt", "label=disable", "-v", f"{classes.resolve()}:/work/classes:ro",
                       "-v", f"{resolved.resolve()}:/work/lib:ro",
                       "-v", f"{script.resolve()}:/work/run-fixed-scene.sh:ro",
                       "-v", f"{args.jdk.resolve()}:/jdk:ro", "-e", f"DEPENDENCY_CP={dependency_cp}",
                       args.headful_image, "bash", "/work/run-fixed-scene.sh", provider, artifact_sha,
                       source["manifest_sha256"], str(args.power), str(args.angle),
                       str(args.steps), str(args.dt), args.ccd]
            (directory / "invocation.json").write_text(json.dumps(command, indent=2) + "\n")
            result = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout_seconds)
            stream = directory / "stream.jsonl"
            stream.write_text(result.stdout)
            (directory / "stderr.log").write_text(result.stderr)
            report["providers"][provider] = {"exit_code": result.returncode,
                                             "artifact_sha256": artifact_sha,
                                             "artifacts": artifacts,
                                             "stream_sha256": hashlib.sha256(stream.read_bytes()).hexdigest()}
            if result.returncode:
                raise ValueError(provider + " fixed replay process failed")
            report["providers"][provider]["process_identity"] = process_identity(result.stderr)
            (directory / "repeat-invocation.json").write_text(json.dumps(command, indent=2) + "\n")
            repeat = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout_seconds)
            repeat_stream = directory / "repeat-stream.jsonl"
            repeat_stream.write_text(repeat.stdout)
            (directory / "repeat-stderr.log").write_text(repeat.stderr)
            if repeat.returncode:
                raise ValueError(provider + " repeated fixed replay process failed")
            report["providers"][provider]["repeat_process_identity"] = process_identity(repeat.stderr)
            if report["providers"][provider]["process_identity"] == report["providers"][provider]["repeat_process_identity"]:
                raise ValueError(provider + " repeated replay reused process identity")
            first_rows, first_error = read_stream(stream, provider, artifact_sha)
            repeat_rows, repeat_error = read_stream(repeat_stream, provider, artifact_sha)
            if first_error or repeat_error:
                raise ValueError(provider + " replay identity invalid: " + str(first_error or repeat_error))
            report["providers"][provider]["runtime"] = {
                key: first_rows[0][key] for key in ("world_code_source", "java_home", "java_version",
                                                 "jvm_identity_hash_mode", "jvm_identity_hash_probe",
                                                 "jvm_input_arguments")}
            difference = repeatability_difference(first_rows, repeat_rows)
            report["repeatability"][provider] = {
                "status": "FAILED" if difference else "PASSED",
                "first_divergence": difference,
                "repeat_stream_sha256": hashlib.sha256(repeat_stream.read_bytes()).hexdigest(),
            }
        comparison = compare(args.output / "baseline/stream.jsonl", args.output / "candidate/stream.jsonl",
                             report["providers"]["baseline"]["artifact_sha256"],
                             report["providers"]["candidate"]["artifact_sha256"])
        (args.output / "comparison.json").write_text(json.dumps(comparison, indent=2, allow_nan=False) + "\n")
        report["comparison"] = comparison
        report["status"] = ("PASSED" if comparison["status"] == "PASSED" and
                            all(item["status"] == "PASSED" for item in report["repeatability"].values())
                            else "FAILED")
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, KeyError) as error:
        report["failure"] = str(error)
    try:
        journeys.require_clean_candidate(commit)
        final_source = journeys.inspect_samples(args.samples)
        if final_source["manifest"] != source["manifest"]:
            raise ValueError("sample source changed during fixed replay")
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        report["status"] = "FAILED"
        report["failure"] = str(error)
    journeys.write_summary(args.output, report)
    return report


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    comparison = commands.add_parser("compare")
    comparison.add_argument("--baseline", type=Path, required=True)
    comparison.add_argument("--candidate", type=Path, required=True)
    comparison.add_argument("--output", type=Path, required=True)
    comparison.add_argument("--baseline-sha256", required=True)
    comparison.add_argument("--candidate-sha256", required=True)
    run = commands.add_parser("run")
    run.add_argument("--samples", type=Path, required=True)
    run.add_argument("--resolved-root", type=Path, required=True)
    run.add_argument("--repository", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--jdk", type=Path, required=True)
    run.add_argument("--javac", type=Path, default=Path("javac"))
    run.add_argument("--headful-image", default="localhost/dyn4k-migration:journeys")
    run.add_argument("--power", type=float, default=0.3)
    run.add_argument("--angle", type=float, default=0.05)
    run.add_argument("--steps", type=int, default=240)
    run.add_argument("--dt", type=float, default=1 / 60)
    run.add_argument("--ccd", choices=("ALL", "BULLETS_ONLY", "NONE"), default="ALL")
    run.add_argument("--timeout-seconds", type=float, default=180)
    args = parser.parse_args()
    try:
        if args.command == "run":
            if not math.isfinite(args.power) or args.power <= 0 or not math.isfinite(args.angle) or args.steps <= 0 or not math.isfinite(args.dt) or args.dt <= 0:
                raise ValueError("invalid fixed input")
            report = run_fixed(args)
            print(json.dumps({"status": report["status"], "failure": report.get("failure"),
                              "first_divergence": report.get("comparison", {}).get("first_divergence"),
                              "repeatability": report.get("repeatability")}))
            return 0 if report["status"] == "PASSED" else 1
        report = compare(args.baseline, args.candidate, args.baseline_sha256, args.candidate_sha256)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        print(json.dumps({"status": report["status"], "first_divergence": report["first_divergence"]}))
        return 0 if report["status"] == "PASSED" else 1
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
