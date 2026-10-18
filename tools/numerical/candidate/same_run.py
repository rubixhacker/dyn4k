import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare

from receipt import load_fixture


def inspect(fixture, trace):
    states = endpoints = callbacks = 0
    previous_state = None
    for _, row in compare.records(trace):
        kind = row.get("kind")
        if kind == "state":
            compare.check_snapshot(row["state"])
            states += 1
            previous_state = row["state"]
        elif kind == "outer-endpoint":
            endpoints += 1
            if (not compare.same_run_alias(row["state"], previous_state) or
                type(row["step"]) is not int or row["step"] != states):
                raise compare.Rejected("outer endpoint is not a state copy")
        elif kind == "instrumented-callback":
            values = row.get("values")
            if not isinstance(values, list):
                raise compare.Rejected("instrumented callback values are missing")
            for value in values:
                if isinstance(value, dict):
                    compare.check_snapshot(value)
                elif not isinstance(value, str):
                    raise compare.Rejected("unrecognized instrumented callback value")
            callbacks += 1
        elif kind == "event":
            for payload in row.get("payload", []):
                if isinstance(payload, dict):
                    compare.check_fixed_body_callback_velocities(payload, fixture)
    if states != fixture["counts"]["state"] or endpoints != fixture["counts"].get("outer-endpoint", 0):
        raise compare.Rejected("state or endpoint count differs")
    if callbacks != fixture["counts"].get("instrumented-callback", 0):
        raise compare.Rejected("instrumented callback count differs")
    return {"states": states, "endpoint_copies": endpoints, "instrumented_callbacks": callbacks}


def main():
    parser = argparse.ArgumentParser(description="Check candidate same-run getters and endpoint copies")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--trace", required=True)
    args = parser.parse_args()
    try:
        fixture = load_fixture(args.fixture, Path(__file__).resolve().parents[1] / "fixtures.json")
        result = {"status": "LOCAL_ALIAS_PASSED", "scope": "CANDIDATE_STAGED_JVM",
                  **inspect(fixture, args.trace)}
    except (compare.Rejected, OSError, KeyError, TypeError, ValueError) as error:
        result = {"status": "LOCAL_ALIAS_FAILED", "reason": str(error)}
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "LOCAL_ALIAS_PASSED" else 1)


if __name__ == "__main__":
    main()
