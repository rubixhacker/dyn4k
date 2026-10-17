import argparse
import gzip
import hashlib
import json
import math
import sys
from itertools import zip_longest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare as approved

from receipt import Rejected, digest, exact, records


CATALOG = Path(__file__).resolve().parents[1] / "fixtures.json"
CHANNELS = ("transform.getTranslation.0", "transform.getTranslation.1",
            "previousTransform.getTranslation.0", "previousTransform.getTranslation.1",
            "velocity.0", "velocity.1", "angularVelocity", "rotationIncrementSum", "atRest")


def channel(body, name):
    value = body
    for part in name.split("."):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def reference_records(path):
    for _, value in approved.records(path):
        yield value


def portable_case_id(fixture_key):
    if fixture_key == "nominal-free-motion":
        return "long-free-60"
    if fixture_key.startswith("default-sleep-"):
        return "contacts-default-" + fixture_key.rsplit("-", 1)[1]
    if fixture_key.startswith("configured-"):
        return "contacts-" + fixture_key
    if fixture_key == "weld-enabled-equal":
        return "P-JINT-Weld-enabled-equal"
    if fixture_key.startswith("pulley-preparation-"):
        return "P-JINT-Pulley-slack-transition-preparation-" + fixture_key.rsplit("-", 1)[1]
    if fixture_key == "pulley-slack-transition":
        return "P-JINT-Pulley-slack-transition-main"
    raise Rejected("portable case mapping is absent")


def diagnostic(fixture_key, reference, portable):
    catalog = json.loads(CATALOG.read_text())
    fixtures = [item for item in catalog["fixtures"] if item["key"] == fixture_key]
    if len(fixtures) != 1:
        raise Rejected("fixture key is absent or duplicated")
    fixture = fixtures[0]
    if digest(reference) != fixture["reference"]["gzip_sha256"]:
        raise Rejected("frozen reference gzip SHA-256 differs")
    with gzip.open(reference, "rb") as stream:
        first = stream.readline()
    if hashlib.sha256(first.rstrip(b"\n")).hexdigest() != fixture["reference"]["input_sha256"]:
        raise Rejected("frozen input line SHA-256 differs")
    ref = iter(reference_records(reference))
    wanted = portable_case_id(fixture_key)
    port = (row for row in records(portable) if row.get("id") == wanted)
    ref_header = next(ref)
    port_header = next(port)
    header_exact = exact(ref_header, port_header)
    events = {"reference": 0, "portable": 0}

    def states(stream, label):
        for row in stream:
            if row.get("kind") in ("event", "instrumented-callback"):
                events[label] += 1
            if row.get("kind") == "state":
                yield row

    checked = 0
    exact_values = 0
    differing_values = 0
    maxima = {name: 0.0 for name in CHANNELS if name != "atRest"}
    first_differences = []
    for baseline, candidate in zip_longest(states(ref, "reference"), states(port, "portable")):
        if baseline is None or candidate is None:
            raise Rejected("state count differs")
        if baseline.get("step") != candidate.get("step"):
            raise Rejected(f"state step differs: {baseline.get('step')} versus {candidate.get('step')}")
        checked += 1
        left_bodies = baseline["state"]["bodies"]
        right_bodies = candidate["state"]["bodies"]
        if len(left_bodies) != len(right_bodies):
            raise Rejected(f"body count differs at step {checked}")
        for index, (left, right) in enumerate(zip(left_bodies, right_bodies)):
            if left["id"] != right["id"]:
                raise Rejected(f"body identity differs at step {checked}")
            for name in CHANNELS:
                a, b = channel(left, name), channel(right, name)
                if exact(a, b):
                    exact_values += 1
                    continue
                differing_values += 1
                if isinstance(a, (int, float)) and isinstance(b, (int, float)) and math.isfinite(a) and math.isfinite(b):
                    if name != "atRest":
                        maxima[name] = max(maxima[name], abs(a - b))
                if len(first_differences) < 20:
                    first_differences.append({"step": checked, "body": index, "channel": name,
                                              "reference": a, "portable": b})
    return {"status": "UNPASSED_INPUT_SCHEMA" if not header_exact else "UNPASSED_EVENT_SCHEMA",
            "fixture_key": fixture_key, "reference_sha256": digest(reference),
            "portable_sha256": digest(portable), "input_header_exact": header_exact,
            "state_steps_compared": checked, "exact_values": exact_values,
            "differing_values": differing_values, "max_absolute_differences": maxima,
            "event_records": events, "first_differences": first_differences,
            "tolerances_applied": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--portable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = diagnostic(args.fixture, args.reference, args.portable)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
