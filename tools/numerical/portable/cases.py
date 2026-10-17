def declared_cases():
    cases = []
    for scale_index, scale in enumerate((0.01, 1.0, 100.0)):
        for origin_index, (ox, oy) in enumerate(((0.0, 0.0), (1000.0, 1000.0), (-1000.0, 1000.0),
                                                  (1000000.0, -1000000.0), (-1000000.0, 1000000.0))):
            for delta_index, delta in enumerate((-1e-8, -1e-12, 0.0, 1e-12, 1e-8)):
                cases.append({"id": f"geometry-boundary-s{scale_index}-o{origin_index}-d{delta_index}",
                              "family": "geometry-collision", "profile": "default", "hz": 60,
                              "steps": 1, "input": {"scale": scale, "origin": [ox, oy],
                                                    "delta": delta, "signedZero": -0.0}})
    cases.append({"id": "motion-forces-60", "family": "free-motion", "profile": "default",
                  "hz": 60, "steps": 600, "input": {"force": [1.0, 0.0], "torque": 0.25,
                                                     "damping": 0.1, "durationSeconds": 10}})
    for hz in (30, 60, 120):
        for restitution_index, restitution in enumerate((0.0, 0.5, 1.0)):
            cases.append({"id": f"motion-restitution-e{restitution_index}-{hz}", "family": "free-motion",
                          "profile": "default", "hz": hz, "steps": 10 * hz,
                          "input": {"restitution": restitution, "gravity": [0.0, -9.8],
                                    "durationSeconds": 10}})
    for hz in (30, 60, 120):
        cases.append({"id": f"contacts-default-{hz}", "family": "contacts-friction-sleep-wake",
                      "profile": "default", "hz": hz, "steps": 600 * hz,
                      "input": {"impulse": [1.0, 0.0], "actionStep": 300 * hz + 1,
                                "gravity": [0.0, -9.8], "friction": 0.5}})
    for outer_hz, group in ((30, 4), (60, 2), (120, 1)):
        for repetition in (1, 2):
            cases.append({"id": f"contacts-configured-{outer_hz}-r{repetition}",
                          "family": "contacts-friction-sleep-wake", "profile": "configured",
                          "hz": 120, "steps": 72000, "outer_group": group,
                          "input": {"outerHz": outer_hz, "repetition": repetition, "innerHz": 120,
                                    "linearTolerance": 1 / 4096, "positionIterations": 8,
                                    "impulse": [1.0, 0.0], "actionStep": 36001}})
    for joint_type in ("Angle", "Distance", "Friction", "Motor", "Pin", "Prismatic", "Pulley", "Revolute", "Weld", "Wheel"):
        for mode in ("initial", "active"):
            cases.append({"id": f"joint-{joint_type}-{mode}", "family": "joints-limits-motors",
                          "profile": "default", "hz": 60, "steps": 600,
                          "input": {"jointType": joint_type, "mode": mode, "durationSeconds": 10}})
    cases.append({"id": "P-JINT-Weld-enabled-equal", "family": "joints-limits-motors",
                  "profile": "frozen-weld-pulley", "hz": 60, "steps": 600,
                  "input": {"jointType": "Weld", "limits": [0.0, 0.0], "offCenterForce": [0.0, -10.0]}})
    for segment, steps in (("preparation-0", 1), ("preparation-1", 2), ("main", 600)):
        cases.append({"id": f"P-JINT-Pulley-slack-transition-{segment}",
                      "family": "joints-limits-motors", "profile": "frozen-weld-pulley",
                      "hz": 60, "steps": steps,
                      "input": {"jointType": "Pulley", "segment": segment,
                                "sourceVelocity": [0.0, 10.0] if segment != "preparation-0" else [0.0, 0.0]}})
    cases.append({"id": "P-J-Angle-ratio-limits-off--1.0", "family": "joints-limits-motors",
                  "profile": "baseline-failed", "hz": 60, "steps": 600,
                  "input": {"jointType": "Angle", "ratio": -1.0, "limitsEnabled": False}})
    for hz in (30, 60, 120):
        for shape in ("circle", "pentagon"):
            for mode in ("ALL", "NONE"):
                cases.append({"id": f"ccd-{shape}-{mode}-{hz}", "family": "ccd",
                              "profile": "default", "hz": hz, "steps": hz,
                              "input": {"shape": shape, "mode": mode, "speed": -120.0,
                                        "durationSeconds": 1}})
    cases.append({"id": "long-free-60", "family": "long-running-invariant",
                  "profile": "default", "hz": 60, "steps": 36000,
                  "input": {"velocity": [0.25, -0.125], "angularVelocity": 0.5,
                            "durationSeconds": 600}})
    for case in cases:
        case["require_setup"] = True
        case["min_step_events"] = 1
        case["expected_actions"] = []
        if case["id"] == "motion-forces-60":
            case["expected_actions"] = list(range(1, 61))
        elif case["id"].startswith("contacts-default-"):
            case["expected_actions"] = [case["input"]["actionStep"]]
        elif case["id"].startswith("contacts-configured-"):
            case["expected_actions"] = [36001]
        elif case["id"].startswith("joint-") and case["input"]["mode"] == "active":
            case["expected_actions"] = [201, 401]
        elif case["id"] == "P-JINT-Pulley-slack-transition-main":
            case["expected_actions"] = [201, 401]
    return cases
