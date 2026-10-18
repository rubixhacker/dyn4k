import argparse
import gzip
import hashlib
import json
import math
import subprocess
import sys
import types
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import compare

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nominal_zero
import receipt
import exact_consistency


ROOT = Path(__file__).resolve().parents[4]
REVISION = "f5053629d68dc134092434310c3d130ee1c0d9b5"
SOURCES = {
    "nominal-rotation-comparator-numbers.py": "c7955aeb9a6a0a97decaf015f1382b4ac0be0a187f849fc0ad5fdea15fa96c09",
    "nominal-rotation-error-model-certificate.py": "710b70f0bcc780dd81883ef1d9971b7b6c6b47e78c86a3a5dd07f3d1edb2b97b",
}
Invalid = compare.Rejected
_ORACLE = None


def approved_math():
    global _ORACLE
    if _ORACLE is None:
        loaded = []
        for name, expected in SOURCES.items():
            source = subprocess.run(("git", "show", f"{REVISION}:docs/research/{name}"),
                                    cwd=ROOT, check=True, capture_output=True).stdout
            if hashlib.sha256(source).hexdigest() != expected:
                raise Invalid("approved nominal math source differs")
            module_name = "approved_" + name.replace("-", "_").replace(".py", "")
            module = types.ModuleType(module_name)
            sys.modules[module_name] = module
            exec(compile(source, f"{REVISION}:{name}", "exec"), module.__dict__)
            loaded.append(module)
        _ORACLE = tuple(loaded)
    return _ORACLE


def require(condition, message):
    if not condition:
        raise Invalid(message)


def finite(value, label):
    require(type(value) in (int, float) and math.isfinite(value), label + " is not finite numeric")
    return Fraction(value)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def next_row(rows, label):
    try:
        return next(rows)
    except StopIteration as error:
        raise Invalid("missing " + label) from error


def selected_body(row, step):
    require(type(row) is dict and set(row) == {"kind", "step", "state"} and
            row["kind"] == "state" and type(row["step"]) is int and row["step"] == step,
            f"state order or schema differs at step {step}")
    state = row["state"]
    require(type(state) is dict and type(state.get("bodies")) is list and
            len(state["bodies"]) == 1 and state.get("joints") == [],
            f"nominal body or joint count differs at step {step}")
    body = state["bodies"][0]
    require(type(body) is dict and body.get("id") == "b0", f"nominal body identity differs at step {step}")
    return body


def record_failure(summary, field, step, error, cap, verdict="FAIL"):
    if summary["first_failure"] is None:
        summary["first_failure"] = {"field": field, "step": step, "error": str(error),
                                    "cap": str(cap), "verdict": verdict}
    summary["failed"] += 1


def audit_pair(fixture, reference, candidate, per_step):
    numbers, oracle = approved_math()
    require(fixture["id"] == "L-free-s1.0-o0.0,0.0-hz60", "nominal fixture identity differs")
    limits = fixture["analytic_limits"]
    expected_limits = {"position_component_m": 1e-10, "cosine_or_sine": 7e-11,
                       "wrapped_angle_rad": 5e-8, "unwrapped_rotation_rad": 6e-8}
    require(limits == expected_limits, "approved nominal analytic limits differ")
    counts = fixture["counts"]
    require(set(counts) == {"inputs", "event", "state"} and counts["inputs"] == 1 and
            counts["event"] == 3 * counts["state"] + 1 and counts["state"] > 0,
            "nominal record schedule differs")
    dt = Fraction.from_float(float.fromhex("0x1.1111111111111p-6"))
    require(dt / 2 == oracle.ALPHA, "approved nominal angular step differs")
    pi_i = oracle.pi_interval()
    pi = numbers.Bounds(Fraction(pi_i.lo, oracle.SCALE), Fraction(pi_i.hi, oracle.SCALE))
    analytic_caps = (Fraction("7e-11"), Fraction("7e-11"),
                     Fraction("5e-8"), Fraction("6e-8"))
    position = {"analytic_checks": 0, "differential_checks": 0,
                "failed": 0, "first_failure": None}
    velocity = {"constant_checks": 0, "differential_checks": 0,
                "failed": 0, "first_failure": None}
    rotation = {"analytic_checks": 0, "differential_checks": 0,
                "failed": 0, "inconclusive": 0, "first_failure": None}
    zero_checks = {"reference": 0, "candidate": 0}
    events = 0
    per_step = Path(per_step)
    require(not per_step.exists(), "per-step evidence already exists")
    with gzip.open(per_step, "wt", encoding="utf-8") as evidence:
        rows = (compare.records(reference), compare.records(candidate))
        headers = [next_row(source, "nominal input") for source in rows]
        for line, header in headers:
            require(line.endswith(b"\n") and
                    hashlib.sha256(line[:-1]).hexdigest() == fixture["reference"]["input_sha256"] and
                    header.get("kind") == "inputs" and header.get("id") == fixture["id"] and
                    type(header.get("steps")) is int and header["steps"] == counts["state"] and
                    finite(header.get("dt"), "input dt") == dt,
                    "frozen nominal setup/input identity differs")
        prior = [header[1]["state"]["bodies"][0]["transform"] for header in headers]
        for step in range(1, counts["state"] + 1):
            methods = ("begin", "updatePerformed", "postSolve", "end") if step == 1 else (
                "begin", "postSolve", "end")
            for order, method in enumerate(methods):
                pair = [next_row(source, "nominal callback") for source in rows]
                for _, event in pair:
                    require(event.get("kind") == "event" and type(event.get("step")) is int and
                            event["step"] == step and type(event.get("order")) is int and
                            event["order"] == order and ".StepListener." + method + "(" in event.get("method", ""),
                            f"nominal callback sequence differs at step {step}")
                    nominal_zero.check_timestep(event)
                    require(event["payload"][1] == {"world": fixture["id"]},
                            f"nominal callback world differs at step {step}")
                require(compare.same_run_alias(pair[0][1], pair[1][1]),
                        f"nominal callback differs from frozen reference at step {step}")
                events += 1
            pair = [next_row(source, "nominal state") for source in rows]
            bodies = [selected_body(row, step) for _, row in pair]
            current = []
            measured = []
            per_step_result = {"step": step, "position": [], "position_differential": [],
                               "velocity": [], "velocity_differential": [],
                               "rotation_analytic": [], "rotation_differential": []}
            for provider, body in zip(("reference", "candidate"), bodies, strict=True):
                transform = body["transform"]
                require(compare.same_run_alias(body["previousTransform"], prior.pop(0)),
                        f"previous transform differs at step {step}")
                current.append(transform)
                translation = transform["getTranslation"]
                require(type(translation) is list and len(translation) == 2 and
                        compare.same_run_alias(translation, body["worldCenter"]) and
                        compare.same_run_alias(translation, body["fixedOriginPosition"]),
                        f"nominal position aliases differ at step {step}")
                zero_checks[provider] += nominal_zero.check_body(body)
                coordinates = tuple(finite(value, "position") for value in translation)
                for axis, (actual, speed) in enumerate(zip(coordinates,
                        (Fraction(1, 4), Fraction(-1, 8)), strict=True)):
                    error = abs(actual - speed * step * dt)
                    cap = Fraction("1e-10")
                    position["analytic_checks"] += 1
                    per_step_result["position"].append({"provider": provider, "axis": axis,
                                                          "analytic_error": str(error),
                                                          "cap": str(cap),
                                                          "verdict": "PASS" if error <= cap else "FAIL"})
                    if error > cap:
                        record_failure(position, provider + ".analytic." + str(axis), step, error, cap)
                velocities = body["velocity"]
                require(type(velocities) is list and len(velocities) == 2,
                        f"nominal velocity schema differs at step {step}")
                observed_velocity = tuple(finite(value, "velocity") for value in velocities) + (
                    finite(body["angularVelocity"], "angular velocity"),)
                for axis, (actual, expected) in enumerate(zip(observed_velocity,
                        (Fraction(1, 4), Fraction(-1, 8), Fraction(1, 2)), strict=True)):
                    velocity["constant_checks"] += 1
                    per_step_result["velocity"].append({"provider": provider, "axis": axis,
                                                          "error": str(abs(actual - expected)),
                                                          "cap": "0",
                                                          "verdict": "PASS" if actual == expected else "FAIL"})
                    if actual != expected:
                        record_failure(velocity, provider + ".constant." + str(axis), step,
                                       abs(actual - expected), 0)
                measured.append((coordinates, observed_velocity,
                                 tuple(finite(transform[name], name) for name in
                                       ("getCost", "getSint", "getRotationAngle")) +
                                 (finite(body["rotationIncrementSum"], "rotation sum"),)))
            prior = current
            for axis in range(2):
                error = abs(measured[0][0][axis] - measured[1][0][axis])
                cap = Fraction("2e-10")
                position["differential_checks"] += 1
                per_step_result["position_differential"].append({"axis": axis,
                    "error": str(error), "cap": str(cap),
                    "verdict": "PASS" if error <= cap else "FAIL"})
                if error > cap:
                    record_failure(position, "differential." + str(axis), step, error, cap)
            for axis in range(3):
                error = abs(measured[0][1][axis] - measured[1][1][axis])
                velocity["differential_checks"] += 1
                per_step_result["velocity_differential"].append({"axis": axis,
                    "error": str(error), "cap": "0",
                    "verdict": "PASS" if not error else "FAIL"})
                if error:
                    record_failure(velocity, "differential." + str(axis), step, error, 0)
            theta_i = oracle.Interval.rational(step * oracle.ALPHA)
            turns = (theta_i.lo + (pi_i.lo + pi_i.hi) // 2) // (pi_i.lo + pi_i.hi)
            phase_i = theta_i - oracle.Interval(2 * turns * oracle.SCALE,
                                                2 * turns * oracle.SCALE) * pi_i
            require(-pi_i.lo < phase_i.lo <= phase_i.hi < pi_i.lo,
                    f"ambiguous nominal phase at step {step}")
            sine_i, cosine_i = oracle.sin_cos(phase_i)
            ideal = [numbers.Bounds(Fraction(value.lo, oracle.SCALE),
                                    Fraction(value.hi, oracle.SCALE))
                     for value in (cosine_i, sine_i, phase_i)]
            ideal.append(numbers.Bounds.point(step * oracle.ALPHA))
            for provider, (_, _, actual) in zip(("reference", "candidate"), measured, strict=True):
                for index, (value, target, cap) in enumerate(zip(actual, ideal, analytic_caps, strict=True)):
                    error = (numbers.Bounds.point(value) - target).absolute()
                    if index == 2:
                        error = numbers.wrapped_distance(numbers.Bounds.point(value), target, pi)
                    verdict = numbers.classify(error, cap)
                    rotation["analytic_checks"] += 1
                    per_step_result["rotation_analytic"].append({"provider": provider,
                        "metric": index, "lower": str(error.lo), "upper": str(error.hi),
                        "cap": str(cap), "verdict": verdict})
                    if verdict == "FAIL":
                        record_failure(rotation, provider + ".analytic." + str(index), step,
                                       error.lo, cap)
                    elif verdict == "INCONCLUSIVE":
                        rotation["inconclusive"] += 1
                        if rotation["first_failure"] is None:
                            rotation["first_failure"] = {"field": provider + ".analytic." + str(index),
                                "step": step, "lower": str(error.lo), "upper": str(error.hi),
                                "cap": str(cap), "verdict": verdict}
            for index, (left, right, cap) in enumerate(zip(measured[0][2], measured[1][2],
                    numbers.PARITY_CAPS, strict=True)):
                error = (numbers.Bounds.point(left) - numbers.Bounds.point(right)).absolute()
                if index == 2:
                    error = numbers.wrapped_distance(numbers.Bounds.point(left),
                                                      numbers.Bounds.point(right), pi)
                verdict = numbers.classify(error, cap)
                rotation["differential_checks"] += 1
                per_step_result["rotation_differential"].append({"metric": index,
                    "lower": str(error.lo), "upper": str(error.hi), "cap": str(cap),
                    "verdict": verdict})
                if verdict == "FAIL":
                    record_failure(rotation, "differential." + str(index), step, error.lo, cap)
                elif verdict == "INCONCLUSIVE":
                    rotation["inconclusive"] += 1
            evidence.write(json.dumps(per_step_result, sort_keys=True) + "\n")
        for source in rows:
            try:
                next(source)
            except StopIteration:
                pass
            else:
                raise Invalid("extra nominal records")
    result = {"counts": counts, "events_checked": events, "position": position,
              "velocity": velocity, "rotation": rotation,
              "positive_zero_checks": zero_checks,
              "rotation_premises": {"H1": "UNPASSED", "H2": "UNPASSED", "H3": "UNPASSED"},
              "per_step_sha256": file_hash(per_step)}
    result["status"] = ("PHYSICAL_FAILED" if any(item["failed"] for item in
                         (position, velocity, rotation)) else "UNPASSED_PREMISE")
    return result


def verify(args):
    fixture = receipt.load_fixture("nominal-free-motion", ROOT / "tools/numerical/fixtures.json")
    reference = compare.audit_reference(fixture, args.reference)
    require(reference["status"] == "PASSED", "frozen nominal reference differs")
    counts = receipt.inspect(args.trace, fixture)
    if args.diagnostic_result:
        require(args.artifact and args.source_commit, "diagnostic source and artifact are required")
        diagnostic = compare.parse(Path(args.diagnostic_result).read_bytes())
        observed = exact_consistency.identity(args.trace, args.artifact, args.source_commit,
                                               sorted((ROOT / "tools/numerical/candidate/calibration").glob("*.java")) +
                                               [ROOT / "tools/numerical/candidate/runtime/RuntimeStamp.java"])
        require(diagnostic.get("identity") == observed and
                diagnostic.get("comparison", {}).get("status") == "PASSED" and
                diagnostic.get("reference", {}).get("status") == "PASSED",
                "source-bound diagnostic identity or comparison differs")
        bound = compare.parse(Path(args.receipt).read_bytes())
        expected_runtime = dict(observed["runtime"])
        expected_runtime["process_command_sha256"] = observed["process_sha256"]
        expected_runtime["runtime_stamp_sha256"] = observed["runtime_stamp_sha256"]
        require(set(bound) == receipt.RECEIPT_FIELDS and
                bound["source_hash_method"] == "SHA-256 of git archive --format=tar source_commit" and
                bound["artifact_path"] == observed["artifact_path"] and
                bound["build_config_sha256"] == receipt.build_config_hash() and
                bound["runtime"] == expected_runtime,
                "source-bound diagnostic receipt differs")
        compare.load_receipt(args.receipt, args.trace, fixture,
                             observed["source_archive_sha256"], observed["artifact_sha256"],
                             args.source_commit, counts)
        scope = "SOURCE_BOUND_STAGED_JVM_DIAGNOSTIC_NOT_FINAL_BRANCH"
    else:
        bound = receipt.verify(args, fixture, counts)
        scope = "RECEIPT_BOUND_STAGED_JVM_NOMINAL_PHYSICAL"
    runtime = bound["runtime"]
    require(runtime["java_version"].startswith("21.") and
            Path(runtime["process_command"]).resolve() ==
            (Path(args.jdk_home) / "bin/java").resolve(), "candidate process is not pinned JDK 21")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    result = audit_pair(fixture, args.reference, args.trace, output / "per-step.jsonl.gz")
    result.update({"scope": scope,
                   "candidate_commit": bound["candidate_commit"],
                   "source_sha256": bound["source_sha256"],
                   "artifact_sha256": bound["artifact_sha256"],
                   "runtime": runtime, "trace_sha256": bound["trace_sha256"],
                   "reference_trace_sha256": fixture["reference"]["gzip_sha256"],
                   "reference_stream_sha256": fixture["reference"]["stream_sha256"],
                   "input_sha256": fixture["reference"]["input_sha256"],
                   "arithmetic_source_sha256": SOURCES})
    with (output / "result.json").open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(description="Verify the staged nominal free-motion physical trajectory")
    parser.add_argument("--fixture", default="nominal-free-motion")
    parser.add_argument("--trace", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--jdk-home", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--diagnostic-result")
    parser.add_argument("--artifact")
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    try:
        require(args.fixture == "nominal-free-motion", "nominal fixture differs")
        result = verify(args)
    except (Invalid, OSError, KeyError, TypeError, ValueError, subprocess.CalledProcessError) as error:
        result = {"status": "INVALID", "reason": str(error)}
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "PHYSICAL_PASSED" else
                     2 if result["status"] in ("PHYSICAL_FAILED", "UNPASSED_PREMISE") else 1)


if __name__ == "__main__":
    main()
