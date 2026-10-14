# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: python3 nominal-rotation-comparator.py EXACT_RAW_GZIP NEW_OUTPUT_DIRECTORY
"""Check frozen nominal rotation outputs; never execute a physics engine."""

from dataclasses import asdict, dataclass
from fractions import Fraction
from hashlib import sha256
from importlib import import_module
from pathlib import Path
import gzip
import json
import platform
import sys
from typing import Final, TypeAlias

numbers = import_module("nominal-rotation-comparator-numbers")
oracle = import_module("nominal-rotation-error-model-certificate")
JSONValue: TypeAlias = str | int | Fraction | bool | None | list["JSONValue"] | dict[str, "JSONValue"]
JSONMap: TypeAlias = dict[str, JSONValue]
RAW_HASH: Final = "4981795bffcd2a0262040acb53c60b20607fea14a2a0c7d79e858ba68e7f2743"
HEADER_HASH: Final = "91f914d3c9993ac238c66e88015861ece560e20333f9e831f3ff4758980b3dd9"
STREAM_HASH: Final = "4a2919c350f61974b8046dd5fe11e0710db37abde26b5db0af909ab4b8d83f78"
ORACLE_HASH: Final = "710b70f0bcc780dd81883ef1d9971b7b6c6b47e78c86a3a5dd07f3d1edb2b97b"
METRICS: Final = ("cosine", "sine", "wrapped_public_angle_rad", "unwrapped_recorder_rad")

def require(condition: bool, reason: str) -> None:
    numbers.require(condition, reason)

def unique_object(pairs: list[tuple[str, JSONValue]]) -> JSONMap:
    result: JSONMap = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key {key}")
        result[key] = value
    return result

def parse_line(line: bytes) -> JSONMap:
    value = json.loads(line, parse_float=numbers.numeric_token, parse_int=numbers.integer_token,
                       parse_constant=numbers.reject_constant, object_pairs_hook=unique_object)
    require(type(value) is dict, "top-level JSON must be object")
    return value

def number(value: JSONValue) -> Fraction:
    require(type(value) in (int, Fraction), "selected numeric field is not a number")
    return Fraction(value)

def body(record: JSONMap) -> JSONMap:
    state = record["state"]
    require(type(state) is dict, "state missing")
    require(type(state["bodies"]) is list and len(state["bodies"]) == 1, "wrong body count")
    require(state["joints"] == [], "unexpected joints")
    selected = state["bodies"][0]
    require(type(selected) is dict and selected["id"] == "b0", "wrong body")
    return selected

def transform(selected: JSONMap, key: str) -> JSONMap:
    value = selected[key]
    require(type(value) is dict, f"missing transform {key}")
    require(set(value) == {"getCost", "getSint", "getRotationAngle", "getTranslation",
                          "getTranslationX", "getTranslationY", "getValues", "isIdentity", "type"},
            "unexpected transform schema")
    require(type(value["isIdentity"]) is bool and value["type"] == "org.dyn4j.geometry.Transform",
            "incorrect transform metadata")
    return value

def exact_copy(previous: JSONMap, prior: JSONMap) -> bool:
    """Numerical equality on the full transform; signed zero is deliberately equivalent."""
    return previous == prior

@dataclass(frozen=True, slots=True)
class MetricResult:
    step: int
    metric: str
    lower: str
    upper: str
    cap: str
    verdict: str

@dataclass(frozen=True, slots=True)
class MetricSummary:
    metric: str
    pass_count: int
    fail_count: int
    inconclusive_count: int
    maximum_upper: str
    maximum_step: int
    first_unpassed_step: int | None

@dataclass(frozen=True, slots=True)
class AuditSummary:
    status: str
    scope: str
    raw_sha256: str
    header_sha256: str
    stream_sha256: str
    input_records: int
    states: int
    events: int
    current_checks: int
    previous_full_transform_checks: int
    previous_full_transform_passes: int
    first_inheritance_failure: int | None
    metrics: list[MetricSummary]
    precision: str
    python: str
    platform: str
    checker_sha256: str
    numeric_helper_sha256: str
    oracle_sha256: str
    comparison_rows_sha256: str
    inheritance_rows_sha256: str
    historical_primitive_status: str
    port_runtime_status: str
    actual_differential_status: str

def audit(raw: Path, destination: Path) -> AuditSummary:
    require(sha256(raw.read_bytes()).hexdigest() == RAW_HASH, "raw gzip hash mismatch")
    base = Path(__file__).parent
    checker_digest = sha256(Path(__file__).read_bytes()).hexdigest()
    helper_digest = sha256((base/"nominal-rotation-comparator-numbers.py").read_bytes()).hexdigest()
    require(sha256((base / "nominal-rotation-error-model-certificate.py").read_bytes()).hexdigest()
            == ORACLE_HASH, "oracle source hash mismatch")
    destination.mkdir(parents=True, exist_ok=False)
    pi_i = oracle.pi_interval()
    pi = numbers.Bounds(Fraction(pi_i.lo, oracle.SCALE), Fraction(pi_i.hi, oracle.SCALE))
    counts = [{"PASS": 0, "FAIL": 0, "INCONCLUSIVE": 0} for _ in METRICS]
    maxima = [Fraction(0) for _ in METRICS]
    maximum_steps = [0 for _ in METRICS]
    first_unpassed: list[int | None] = [None for _ in METRICS]
    states = events = copies = 0
    first_copy_failure: int | None = None
    stream_digest = sha256()
    rows = destination / "comparisons.jsonl"
    inheritance = destination / "inheritance.jsonl"
    with gzip.open(raw, "rb") as source, rows.open("w") as output, inheritance.open("w") as copies_out:
        header = source.readline()
        stream_digest.update(header)
        require(header.endswith(b"\n"), "truncated header")
        require(sha256(header[:-1]).hexdigest() == HEADER_HASH, "header hash mismatch")
        inputs = parse_line(header)
        require(inputs["kind"] == "inputs" and inputs["steps"] == 36000, "wrong input identity/count")
        require(inputs["id"] == "L-free-s1.0-o0.0,0.0-hz60", "wrong fixture")
        require(number(inputs["dt"])/2 == oracle.ALPHA, "wrong encoded dt")
        prior = transform(body(inputs), "transform")
        require(number(prior["getCost"]) == 1 and number(prior["getSint"]) == 0
                and number(prior["getRotationAngle"]) == 0, "wrong initial rotation")
        for line in source:
            stream_digest.update(line)
            require(line.endswith(b"\n"), "truncated record")
            record = parse_line(line)
            if record["kind"] == "event":
                events += 1
                continue
            require(record["kind"] == "state", "unexpected record kind")
            states += 1
            require(type(record["step"]) is int and record["step"] == states <= 36000,
                    "missing/duplicate/out-of-order state")
            selected = body(record)
            current = transform(selected, "transform")
            copied = exact_copy(transform(selected, "previousTransform"), prior)
            copies += int(copied)
            if not copied and first_copy_failure is None:
                first_copy_failure = states
            copies_out.write(json.dumps({"step": states, "full_previous_transform_equal": copied}) + "\n")
            prior = current
            theta_i = oracle.Interval.rational(states*oracle.ALPHA)
            turns = (theta_i.lo + (pi_i.lo+pi_i.hi)//2) // (pi_i.lo+pi_i.hi)
            phase_i = theta_i - oracle.Interval(2*turns*oracle.SCALE, 2*turns*oracle.SCALE) * pi_i
            require(-pi_i.lo < phase_i.lo <= phase_i.hi < pi_i.lo, "ambiguous principal phase")
            sine_i, cosine_i = oracle.sin_cos(phase_i)
            ideal = [numbers.Bounds(Fraction(i.lo, oracle.SCALE), Fraction(i.hi, oracle.SCALE))
                     for i in (cosine_i, sine_i, phase_i)]
            ideal.append(numbers.Bounds.point(states*oracle.ALPHA))
            observed = [number(current[key]) for key in ("getCost", "getSint", "getRotationAngle")]
            observed.append(number(selected["rotationIncrementSum"]))
            for index, (metric, actual, target, cap) in enumerate(zip(
                    METRICS, observed, ideal, numbers.ANALYTIC_CAPS, strict=True)):
                point = numbers.Bounds.point(actual)
                error = (point-target).absolute()
                if index == 2:
                    error = numbers.wrapped_distance(point, target, pi)
                verdict = numbers.classify(error, cap)
                counts[index][verdict] += 1
                if error.hi > maxima[index]:
                    maxima[index], maximum_steps[index] = error.hi, states
                if verdict != "PASS" and first_unpassed[index] is None:
                    first_unpassed[index] = states
                output.write(json.dumps(asdict(MetricResult(states, metric, str(error.lo), str(error.hi),
                                                           str(cap), verdict)), sort_keys=True) + "\n")
    require(states == 36000 and events == 108001, "incomplete stream counts")
    require(stream_digest.hexdigest() == STREAM_HASH, "decompressed stream hash mismatch")
    summaries = [MetricSummary(metric, c["PASS"], c["FAIL"], c["INCONCLUSIVE"], str(maximum), step, first)
                 for metric, c, maximum, step, first in zip(METRICS, counts, maxima, maximum_steps,
                                                           first_unpassed, strict=True)]
    passed = copies == states and all(s.pass_count == states for s in summaries)
    require(checker_digest == sha256(Path(__file__).read_bytes()).hexdigest()
            and helper_digest == sha256((base/"nominal-rotation-comparator-numbers.py").read_bytes()).hexdigest(),
            "checker source changed during execution")
    summary = AuditSummary(
        "PASS" if passed else "UNPASSED", "DIRECT_FROZEN_BASELINE_OUTPUTS_ONLY",
        RAW_HASH, HEADER_HASH, stream_digest.hexdigest(), 1, states, events, states*4, states, copies,
        first_copy_failure, summaries, "outward integer lattice 1e-70; exact Fraction metrics/decoding",
        sys.version, platform.platform(), checker_digest, helper_digest, ORACLE_HASH,
        sha256(rows.read_bytes()).hexdigest(), sha256(inheritance.read_bytes()).hexdigest(),
        "UNQUALIFIED_HIDDEN_CALLS", "UNPASSED", "NOT_RUN_NO_PORT_TRAJECTORY")
    (destination/"manifest.json").write_text(json.dumps(asdict(summary), indent=2) + "\n")
    return summary

if __name__ == "__main__":
    require(len(sys.argv) == 3, "usage: comparator.py EXACT_RAW_GZIP NEW_OUTPUT_DIRECTORY")
    result = audit(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps(asdict(result), indent=2))
    sys.exit(0 if result.status == "PASS" else 1)
