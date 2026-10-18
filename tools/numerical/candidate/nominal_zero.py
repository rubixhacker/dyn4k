import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare


ZERO_PATHS = ["state.state.bodies[].force[]", "state.state.bodies[].torque",
              "state.state.bodies[].accumulatedForce[]",
              "state.state.bodies[].accumulatedTorque"]


def with_rules(fixture):
    if fixture["key"] != "nominal-free-motion":
        raise compare.Rejected("nominal zero rule scope differs")
    if "zero_numeric" in fixture:
        if fixture["zero_numeric"] != ZERO_PATHS:
            raise compare.Rejected("nominal zero rule scope differs")
        return fixture
    return {**fixture, "zero_numeric": list(ZERO_PATHS)}


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


def audit_trace(path, expected_states):
    states = checks = 0
    for _, row in compare.records(path):
        if row["kind"] != "state":
            continue
        states += 1
        bodies = row["state"]["bodies"]
        if type(bodies) is not list or len(bodies) != 1:
            raise compare.Rejected("nominal body count differs")
        checks += check_body(bodies[0])
    if states != expected_states:
        raise compare.Rejected("nominal state count differs")
    return {"states": states, "positive_zero_checks": checks}


def audit_pair(reference, candidate, expected_states):
    return {"reference": audit_trace(reference, expected_states),
            "candidate": audit_trace(candidate, expected_states)}


def compare_pair(fixture, reference, candidate, receipt_path, source, artifact, commit):
    zero = audit_pair(reference, candidate, fixture["counts"]["state"])
    outcome = compare.compare(with_rules(fixture), reference, candidate, receipt_path,
                              source, artifact, commit)
    outcome["nominal_positive_zero"] = zero
    return outcome
