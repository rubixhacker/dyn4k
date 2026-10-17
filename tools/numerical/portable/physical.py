import math

from receipt import Rejected, exact, records


def nominal_free(trace):
    checked = 0
    maxima = {"positionX_m": 0.0, "positionY_m": 0.0, "rotation_rad": 0.0,
              "energy": 0.0, "momentumX": 0.0, "momentumY": 0.0,
              "angularMomentumCenter": 0.0}
    initial = None
    failures = []
    failure_count = 0
    try:
        for row in records(trace):
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
    if checked == 0:
        failures.append({"reason": "no long-free state executed"})
    return {"status": "FAILED" if failures else "PASSED", "checked": checked,
            "failed_samples": failure_count,
            "maxima": maxima, "first_failures": failures[:20],
            "scope": "diagnostic analytical free-motion checks; frozen input parity is separate"}
