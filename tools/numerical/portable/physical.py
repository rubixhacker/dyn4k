import math
import runpy
import sys
from fractions import Fraction
from pathlib import Path

from receipt import Rejected, exact, records


APPROVED_DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APPROVED_DIRECTORY))
sys.dont_write_bytecode = True
from compare import Rejected as ApprovedRejected, load_fixture

APPROVED_PHYSICAL = runpy.run_path(str(APPROVED_DIRECTORY / "physical.py"), run_name="approved_physical")


def nominal_free(trace, expected_steps=36000):
    checked = 0
    maxima = {"positionX_m": 0.0, "positionY_m": 0.0, "rotation_rad": 0.0,
              "energy": 0.0, "momentumX": 0.0, "momentumY": 0.0,
              "angularMomentumCenter": 0.0}
    initial = None
    failures = []
    failure_count = 0
    try:
        for row in records(trace, allow_tagged_nonfinite=True):
            if row.get("kind") != "state" or row.get("id") != "long-free-60":
                continue
            checked += 1
            step = row["step"]
            body, = row["state"]["bodies"]
            if initial is None:
                initial = (body["kineticEnergy"], body["linearMomentum"], body["angularMomentumCenter"])
            expected_time = step / 60
            dx = abs(body["worldCenter"][0] - 0.25 * expected_time)
            dy = abs(body["worldCenter"][1] + 0.125 * expected_time)
            dr = abs(body["rotationIncrementSum"] - 0.5 * expected_time)
            maxima["positionX_m"] = max(maxima["positionX_m"], dx)
            maxima["positionY_m"] = max(maxima["positionY_m"], dy)
            maxima["rotation_rad"] = max(maxima["rotation_rad"], dr)
            maxima["energy"] = max(maxima["energy"], abs(body["kineticEnergy"] - initial[0]))
            maxima["momentumX"] = max(maxima["momentumX"], abs(body["linearMomentum"][0] - initial[1][0]))
            maxima["momentumY"] = max(maxima["momentumY"], abs(body["linearMomentum"][1] - initial[1][1]))
            maxima["angularMomentumCenter"] = max(maxima["angularMomentumCenter"], abs(body["angularMomentumCenter"] - initial[2]))
            if (dx > 1e-10 or dy > 1e-10 or dr > 6e-8 or
                not exact(body["velocity"], [0.25, -0.125]) or
                not exact(body["angularVelocity"], 0.5) or
                any(not math.isfinite(value) for value in maxima.values())):
                failure_count += 1
                if len(failures) < 20:
                    failures.append({"step": step, "positionX_m": dx, "positionY_m": dy,
                                     "rotation_rad": dr})
    except (Rejected, KeyError, TypeError, ValueError) as error:
        failures.append({"reason": str(error)})
    if checked != expected_steps:
        failures.append({"reason": f"expected {expected_steps} long-free states; executed {checked}"})
    return {"status": "FAILED" if failures else "PASSED", "checked": checked,
            "failed_samples": failure_count,
            "maxima": maxima, "first_failures": failures[:20],
            "scope": "diagnostic analytical free-motion checks; frozen input parity is separate"}


def sleep_wake(trace):
    return sleep_wake_rows(records(trace, allow_tagged_nonfinite=True))


def sleep_wake_rows(rows, keys=None):
    if keys is None:
        keys = ([f"default-sleep-{hz}" for hz in (30, 60, 120)] +
                [f"configured-{hz}-r{repetition}" for hz in (30, 60, 120) for repetition in (1, 2)])
    fixtures = {key: load_fixture(key) for key in keys}
    phases = {key: APPROVED_PHYSICAL["phases_for_fixture"](fixture)
              for key, fixture in fixtures.items()}
    reports = {key: {"status": "NOT_RUN", "states": 0, "failed": 0,
                     "first_failure": None, "maximum_depth_m": "0"} for key in keys}
    positions = {key: 0 for key in keys}
    maxima = {key: Fraction(0) for key in keys}
    try:
        for row in rows:
            if row.get("kind") != "state":
                continue
            case_id = row.get("id", "")
            key = ("default-sleep-" + case_id.rsplit("-", 1)[1]
                   if case_id.startswith("contacts-default-") else
                   case_id.removeprefix("contacts-") if case_id.startswith("contacts-configured-") else None)
            if key is None:
                continue
            if key not in reports:
                continue
            report = reports[key]
            step = row["step"]
            if step != report["states"] + 1:
                raise Rejected(f"{key}: missing physical state")
            schedule = phases[key]
            while step > schedule[positions[key]][2]:
                positions[key] += 1
            phase = schedule[positions[key]][0]
            depth = APPROVED_PHYSICAL["depth_for_state"](row["state"])
            ceiling = Fraction(str(fixtures[key]["physical_phase_ceilings_m"][phase]))
            report["states"] += 1
            maxima[key] = max(maxima[key], depth)
            if depth > ceiling:
                report["failed"] += 1
                if report["first_failure"] is None:
                    report["first_failure"] = {"step": step, "phase": phase,
                                               "depth_m": str(depth), "ceiling_m": str(ceiling)}
        for key, report in reports.items():
            report["maximum_depth_m"] = str(maxima[key])
            if report["states"] != fixtures[key]["counts"]["state"]:
                report["status"] = "INVALID"
                report["reason"] = "physical state count differs"
            else:
                report["status"] = "PHYSICAL_FAILED" if report["failed"] else "PHYSICAL_PASSED"
    except (Rejected, ApprovedRejected, KeyError, IndexError, TypeError, ValueError, ZeroDivisionError) as error:
        for key, report in reports.items():
            report["maximum_depth_m"] = str(maxima[key])
        return {"status": "INVALID", "reason": str(error), "cases": reports,
                "qualification": "UNPASSED"}
    overall = ("INVALID" if any(item["status"] == "INVALID" for item in reports.values()) else
               "PHYSICAL_FAILED" if any(item["status"] == "PHYSICAL_FAILED" for item in reports.values()) else
               "PHYSICAL_PASSED")
    return {"status": overall,
            "scope": "APPROVED_REPRESENTED_GEOMETRY_DIAGNOSTIC",
            "cases": reports, "qualification": "UNPASSED"}
