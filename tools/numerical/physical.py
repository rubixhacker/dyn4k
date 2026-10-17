import argparse
import json
from fractions import Fraction

from compare import Rejected, audit_reference, load_fixture, records


def depth_for_state(state):
    bodies = state["bodies"]
    if len(bodies) != 2 or [body["id"] for body in bodies] != ["b0", "b1"]:
        raise Rejected("floor or square identity differs")
    floor = bodies[0]["transform"]
    square = bodies[1]["transform"]
    if (floor["getCost"] != 1 or floor["getSint"] != 0 or
        floor["getTranslation"] != [0, -0.25]):
        raise Rejected("fixed floor pose differs")
    x, y = square["getTranslation"]
    cosine, sine = square["getCost"], square["getSint"]
    extent = (abs(Fraction.from_float(float(cosine))) +
              abs(Fraction.from_float(float(sine)))) / 2
    if abs(Fraction.from_float(float(x))) + extent > 10:
        raise Rejected("square leaves finite floor span")
    return max(Fraction(0), extent - Fraction.from_float(float(y)))


def phases_for_fixture(fixture):
    if "physical_phases_steps" in fixture:
        phases = fixture["physical_phases_steps"]
    elif "physical_phases_inner_steps" in fixture:
        phases = fixture["physical_phases_inner_steps"]
    elif "physical_phases_by_hz" in fixture:
        hz = fixture["id"].rsplit("hz", 1)[1]
        phases = fixture["physical_phases_by_hz"][hz]
    else:
        raise Rejected("no approved physical phase schedule")
    current = 1
    for name, first, last in phases:
        if first != current or last < first or name not in fixture["physical_phase_ceilings_m"]:
            raise Rejected("physical phase schedule has a gap")
        current = last + 1
    if current - 1 != fixture["counts"]["state"]:
        raise Rejected("physical phase schedule does not cover every state")
    return phases


def audit_physical(fixture, reference):
    baseline = audit_reference(fixture, reference)
    if baseline["status"] != "PASSED":
        return {"status": "INVALID", "reason": baseline["reason"]}
    try:
        phases = phases_for_fixture(fixture)
        phase_index = 0
        checked = failed = 0
        first_failure = None
        for _, row in records(reference):
            if row["kind"] != "state":
                continue
            step = row["step"]
            while step > phases[phase_index][2]:
                phase_index += 1
            phase = phases[phase_index][0]
            depth = depth_for_state(row["state"])
            ceiling = Fraction(str(fixture["physical_phase_ceilings_m"][phase]))
            checked += 1
            if depth > ceiling:
                failed += 1
                if first_failure is None:
                    first_failure = {"step": step, "phase": phase,
                                     "depth_m": str(depth), "ceiling_m": str(ceiling)}
        return {"status": "PHYSICAL_FAILED" if failed else "PHYSICAL_PASSED",
                "scope": "FROZEN_BASELINE_REPRESENTED_GEOMETRY_ONLY",
                "states": checked, "failed": failed,
                "endpoint_mappings": fixture["counts"].get("outer-endpoint", 0),
                "first_failure": first_failure}
    except (Rejected, KeyError, IndexError, TypeError, ValueError) as error:
        return {"status": "INVALID", "reason": str(error)}


def main():
    parser = argparse.ArgumentParser(description="Audit frozen sleep/wake represented geometry")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--reference", required=True)
    args = parser.parse_args()
    outcome = audit_physical(load_fixture(args.fixture), args.reference)
    print(json.dumps(outcome, sort_keys=True))
    raise SystemExit(0 if outcome["status"] == "PHYSICAL_PASSED" else
                     2 if outcome["status"] == "PHYSICAL_FAILED" else 1)


if __name__ == "__main__":
    main()
