import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare
import physical

from receipt import load_fixture, verify


def audit(trace, fixture):
    phases = physical.phases_for_fixture(fixture)
    start_step = fixture.get("start_step", 0)
    if type(start_step) is not int or start_step < 0:
        raise compare.Rejected("invalid fixture start step")
    phase_index = 0
    checked = failed = endpoints = 0
    first_failure = None
    previous_state = None
    for _, row in compare.records(trace):
        if row["kind"] == "outer-endpoint":
            endpoints += 1
            if (not compare.same_run_alias(row["state"], previous_state) or
                not compare.endpoint_index_matches(row, fixture, checked, endpoints)):
                raise compare.Rejected("endpoint is not a copy of the current inner state")
        if row["kind"] != "state":
            continue
        checked += 1
        if type(row.get("step")) is not int or row["step"] != start_step + checked:
            raise compare.Rejected("candidate state sequence differs")
        previous_state = row["state"]
        while checked > phases[phase_index][2]:
            phase_index += 1
        phase = phases[phase_index][0]
        depth = physical.depth_for_state(previous_state)
        ceiling = Fraction(str(fixture["physical_phase_ceilings_m"][phase]))
        if depth > ceiling:
            failed += 1
            if first_failure is None:
                first_failure = {"step": checked, "phase": phase,
                                 "depth_m": str(depth), "ceiling_m": str(ceiling)}
    if checked != fixture["counts"]["state"] or endpoints != fixture["counts"].get("outer-endpoint", 0):
        raise compare.Rejected("candidate state or endpoint count differs")
    return {"status": "PHYSICAL_FAILED" if failed else "PHYSICAL_PASSED",
            "states": checked, "failed": failed, "endpoint_mappings": endpoints,
            "first_failure": first_failure}


def main():
    parser = argparse.ArgumentParser(description="Audit candidate sleep/wake represented geometry")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--receipt")
    parser.add_argument("--diagnostic", action="store_true")
    args = parser.parse_args()
    if bool(args.receipt) == args.diagnostic:
        parser.error("choose one of --receipt or --diagnostic")
    try:
        fixture = load_fixture(args.fixture, Path(__file__).resolve().parents[1] / "fixtures.json")
        if args.receipt:
            verify(args, fixture, compare.check_counts(compare.records(args.trace), fixture, reference=False))
        result = audit(args.trace, fixture)
        result["scope"] = "RECEIPT_BOUND_CANDIDATE_JVM" if args.receipt else "UNBOUND_DIAGNOSTIC"
    except (compare.Rejected, OSError, KeyError, TypeError, ValueError, IndexError) as error:
        result = {"status": "INVALID", "reason": str(error)}
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "PHYSICAL_PASSED" else
                     2 if result["status"] == "PHYSICAL_FAILED" else 1)


if __name__ == "__main__":
    main()
