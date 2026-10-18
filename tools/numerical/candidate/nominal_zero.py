import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare


ZERO_PATHS = ["state.state.bodies[].force[]", "state.state.bodies[].torque",
              "state.state.bodies[].accumulatedForce[]",
              "state.state.bodies[].accumulatedTorque"]
TIMESTEP_VALUES = {
    "getDeltaTime": float.fromhex("0x1.1111111111111p-6"),
    "getPrevousDeltaTime": float.fromhex("0x1.1111111111111p-6"),
    "getInverseDeltaTime": float.fromhex("0x1.e000000000000p+5"),
    "getPreviousInverseDeltaTime": float.fromhex("0x1.e000000000000p+5"),
    "getDeltaTimeRatio": float.fromhex("0x1.0000000000000p+0"),
}
TIMESTEP_PATHS = ["event.payload[]." + field for field in TIMESTEP_VALUES]
STEP_METHODS = ("begin", "updatePerformed", "postSolve", "end")


def with_rules(fixture):
    if fixture["key"] != "nominal-free-motion":
        raise compare.Rejected("nominal zero rule scope differs")
    if "zero_numeric" in fixture and fixture["zero_numeric"] != ZERO_PATHS:
        raise compare.Rejected("nominal zero rule scope differs")
    exact = list(fixture.get("exact_numeric", []))
    for path in TIMESTEP_PATHS:
        if path not in exact:
            exact.append(path)
    return {**fixture, "zero_numeric": list(ZERO_PATHS), "exact_numeric": exact}


def check_timestep(row):
    if row.get("listener") != "StepListener" or not any(
            ".StepListener." + method + "(" in row.get("method", "")
            for method in STEP_METHODS):
        raise compare.Rejected("nominal callback identity differs")
    payload = row.get("payload")
    if type(payload) is not list or len(payload) != 2 or type(payload[0]) is not dict:
        raise compare.Rejected("nominal timestep payload schema differs")
    step = payload[0]
    if set(step) != set(TIMESTEP_VALUES) | {"type"} or step["type"] != "org.dyn4j.dynamics.TimeStep":
        raise compare.Rejected("nominal timestep schema differs")
    for field, expected in TIMESTEP_VALUES.items():
        value = step[field]
        if type(value) not in (int, float) or not math.isfinite(value) or value != expected:
            raise compare.Rejected("nominal timestep " + field + " differs")
    return len(TIMESTEP_VALUES)


def check_body(body):
    checks = 0
    for name, length in (("force", 2), ("torque", None),
                         ("accumulatedForce", 2), ("accumulatedTorque", None)):
        if name not in body:
            raise compare.Rejected("missing nominal zero field: " + name)
        field = body[name]
        if length is not None:
            if type(field) is not list or len(field) != length:
                raise compare.Rejected("invalid nominal zero vector: " + name)
            values = field
        else:
            values = [field]
        for value in values:
            if type(value) is not float or not math.isfinite(value) or \
                    struct.pack(">d", value) != b"\x00" * 8:
                raise compare.Rejected("nominal field is not positive binary64 zero: " + name)
            checks += 1
    return checks


def audit_trace(path, expected_states, expected_callbacks):
    states = checks = callbacks = timestep_checks = 0
    for _, row in compare.records(path):
        if row["kind"] == "event":
            callbacks += 1
            timestep_checks += check_timestep(row)
            continue
        if row["kind"] != "state":
            continue
        states += 1
        bodies = row["state"]["bodies"]
        if type(bodies) is not list or len(bodies) != 1:
            raise compare.Rejected("nominal body count differs")
        checks += check_body(bodies[0])
    if states != expected_states or callbacks != expected_callbacks:
        raise compare.Rejected("nominal state or callback count differs")
    return {"states": states, "positive_zero_checks": checks,
            "timestep_callbacks": callbacks, "exact_timestep_checks": timestep_checks}


def audit_pair(reference, candidate, expected_states, expected_callbacks):
    return {"reference": audit_trace(reference, expected_states, expected_callbacks),
            "candidate": audit_trace(candidate, expected_states, expected_callbacks)}


def compare_pair(fixture, reference, candidate, receipt_path, source, artifact, commit):
    checks = audit_pair(reference, candidate, fixture["counts"]["state"],
                        fixture["counts"]["event"])
    outcome = compare.compare(with_rules(fixture), reference, candidate, receipt_path,
                              source, artifact, commit)
    outcome["nominal_positive_zero"] = {
        provider: {key: check[key] for key in ("states", "positive_zero_checks")}
        for provider, check in checks.items()}
    outcome["nominal_timestep"] = {
        provider: {key: check[key] for key in ("timestep_callbacks", "exact_timestep_checks")}
        for provider, check in checks.items()}
    return outcome
