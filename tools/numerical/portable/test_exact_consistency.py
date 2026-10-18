import copy
import unittest

from exact_consistency import check_endpoint, check_impulse, check_snapshot, check_time_step


def transform(x, y):
    return {"type": "org.dyn4j.geometry.Transform", "getCost": 1.0,
            "getSint": 0.0, "getRotationAngle": 0.0,
            "getTranslation": [x, y], "getTranslationX": x, "getTranslationY": y,
            "getValues": [1.0, 0.0, x, 0.0, 1.0, y], "isIdentity": False}


def body(index):
    current = transform(0.0, -0.25 if index == 0 else 0.5)
    value = {"id": f"b{index}", "atRest": False, "force": [0.0, 0.0],
             "accumulatedForce": [0.0, 0.0], "torque": 0.0,
             "accumulatedTorque": 0.0, "velocity": [0.0, 0.0],
             "angularVelocity": 0.0, "worldCenter": copy.deepcopy(current["getTranslation"]),
             "fixedOriginPosition": copy.deepcopy(current["getTranslation"]),
             "transform": current, "previousTransform": copy.deepcopy(current),
             "rotationIncrementSum": 0.0, "rotationStepBoundBelowPi": True,
             "rotationTrackingScope": "initial", "fixtures": [{}]}
    value["properties"] = {
        "getForce": copy.deepcopy(value["force"]),
        "getAccumulatedForce": copy.deepcopy(value["accumulatedForce"]),
        "getTorque": value["torque"], "getAccumulatedTorque": value["accumulatedTorque"],
        "getLinearVelocity": copy.deepcopy(value["velocity"]),
        "getAngularVelocity": value["angularVelocity"],
        "getTransform": copy.deepcopy(value["transform"]),
        "getPreviousTransform": copy.deepcopy(value["previousTransform"]),
        "getWorldCenter": copy.deepcopy(value["worldCenter"]), "isAtRest": False,
        "getAngularDamping": 0.0, "getChangeInOrientation": 0.0,
        "getChangeInPosition": [0.0, 0.0], "getFixtureCount": 1,
        "getGravityScale": 1.0, "getLinearDamping": 0.0,
        "getLocalCenter": [0.0, 0.0], "getMass": {"getCenter": [0.0, 0.0]},
        "getRotationDiscRadius": 1.0, "isAtRestDetectionEnabled": True,
        "isBullet": False, "isDynamic": index == 1, "isEnabled": True,
        "isKinematic": False, "isStatic": index == 0,
        "type": "org.dyn4j.dynamics.Body"}
    return value


def snapshot():
    return {"bodies": [body(0), body(1)], "joints": []}


class ApprovedExactConsistencyTest(unittest.TestCase):
    def test_floor_force_alias_previous_and_sleep_controls(self):
        initial = snapshot()
        check_snapshot(initial, "initial")
        current = copy.deepcopy(initial)
        for item in current["bodies"]:
            item.pop("fixtures")
            item.pop("properties")
        check_snapshot(current, "step", initial)
        changes = (
            (lambda state: state["bodies"][0]["force"].__setitem__(0, 0.1), "force"),
            (lambda state: state["bodies"][0]["transform"].__setitem__("getTranslationY", -0.2), "alias"),
            (lambda state: state["bodies"][0]["previousTransform"].__setitem__("getRotationAngle", 0.1), "previous"),
            (lambda state: state["bodies"][1]["velocity"].__setitem__(0, 0.1), "sleep"),
        )
        for change, reason in changes:
            with self.subTest(reason=reason):
                bad = copy.deepcopy(current)
                if reason == "sleep":
                    bad["bodies"][1]["atRest"] = True
                change(bad)
                with self.assertRaisesRegex(Exception, reason):
                    check_snapshot(bad, "step", initial)
        sleeping = copy.deepcopy(current)
        sleeping["bodies"][1]["atRest"] = True
        check_snapshot(sleeping, "step", copy.deepcopy(sleeping))
        drift = copy.deepcopy(sleeping)
        moving = drift["bodies"][1]
        moving["transform"] = transform(1.0, 0.5)
        moving["worldCenter"] = [1.0, 0.5]
        moving["fixedOriginPosition"] = [1.0, 0.5]
        with self.assertRaisesRegex(Exception, "sleep"):
            check_snapshot(drift, "step", sleeping)
        duplicate = copy.deepcopy(initial)
        duplicate["bodies"][1]["properties"]["getForce"] = [0.1, 0.0]
        with self.assertRaisesRegex(Exception, "duplicate"):
            check_snapshot(duplicate, "initial")
        nonfinite = copy.deepcopy(initial)
        nonfinite["bodies"][1]["transform"]["getRotationAngle"] = float("inf")
        with self.assertRaisesRegex(Exception, "nonfinite"):
            check_snapshot(nonfinite, "initial")
        signed_zero = copy.deepcopy(initial)
        signed_zero["bodies"][1]["force"] = [-0.0, 0.0]
        signed_zero["bodies"][1]["properties"]["getForce"] = [-0.0, 0.0]
        check_snapshot(signed_zero, "initial")

    def test_immediate_center_impulse_and_timestep(self):
        before = snapshot()
        before["bodies"][1]["atRest"] = True
        before["bodies"][1]["properties"]["isAtRest"] = True
        after = copy.deepcopy(before)
        dynamic = after["bodies"][1]
        dynamic["atRest"] = False
        dynamic["velocity"] = [1.0, 0.0]
        dynamic["properties"]["isAtRest"] = False
        dynamic["properties"]["getLinearVelocity"] = [1.0, 0.0]
        check_impulse(before, after)
        bad = copy.deepcopy(after)
        bad["bodies"][1]["fixtures"][0]["getFriction"] = 0.6
        with self.assertRaisesRegex(Exception, "impulse"):
            check_impulse(before, bad)
        wrong_velocity = copy.deepcopy(after)
        wrong_velocity["bodies"][1]["velocity"][0] = 0.9
        with self.assertRaisesRegex(Exception, "impulse"):
            check_impulse(before, wrong_velocity)
        first = {"type": "org.dyn4j.dynamics.TimeStep", "getDeltaTime": 1 / 120,
                 "getInverseDeltaTime": 120.0, "getPrevousDeltaTime": 1 / 60,
                 "getPreviousInverseDeltaTime": 60.0, "getDeltaTimeRatio": 0.5}
        check_time_step(first, 120, 1)
        bad_time = {**first, "getDeltaTimeRatio": 1.0}
        with self.assertRaisesRegex(Exception, "timestep"):
            check_time_step(bad_time, 120, 1)

    def test_endpoint_copy_does_not_advance_inner_state(self):
        state = snapshot()
        inner = {"kind": "state", "step": 4, "state": state}
        endpoint = {"kind": "outer-endpoint", "step": 4, "outerStep": 1,
                    "state": copy.deepcopy(state)}
        check_endpoint(endpoint, inner, 30)
        endpoint["state"]["bodies"][1]["velocity"][0] = 0.1
        with self.assertRaisesRegex(Exception, "endpoint"):
            check_endpoint(endpoint, inner, 30)
        endpoint["state"] = copy.deepcopy(state)
        endpoint["outerStep"] = 2
        with self.assertRaisesRegex(Exception, "endpoint"):
            check_endpoint(endpoint, inner, 30)


if __name__ == "__main__":
    unittest.main()
