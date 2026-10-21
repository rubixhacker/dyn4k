import copy
import unittest

from witness import verify_stream


CASE = "joint-Revolute-LimitsEnabled-false"
SOURCE = "a" * 64
JAR = "b" * 64
CODE = "c" * 64
MARKER = "d" * 64
ZERO = "0000000000000000"
ONE = "3ff0000000000000"


def fixture():
    calls = []
    markers = []
    for step in range(1, 601):
        for body, branch, caller, code_index in (
            ("b1", "integrate", "org.dyn4j.dynamics.AbstractPhysicsBody.integrate", 17),
            ("b0", None, "org.dyn4j.dynamics.joint.RevoluteJoint.solvePositionConstraints", 31),
            ("b1", None, "org.dyn4j.dynamics.joint.RevoluteJoint.solvePositionConstraints", 47),
        ):
            ordinal = len(calls)
            event = dict(ordinal=ordinal, thread=7, receiver=10 if body == "b0" else 11,
                         method="rotatePivotObserved", caller=caller,
                         caller_code_index=code_index, pre=[ONE, ZERO], trig=[ONE, ZERO],
                         post=[ONE, ZERO], angle_bits=ZERO)
            calls.append(event)
            markers.append(dict(step=step, body_id=body, branch=branch, kind="rotate",
                                pre=event["pre"], trig=event["trig"], post=event["post"],
                                angle_bits=ZERO))
    witness = dict(schema="boolean-rotation-jdi/1", pid=1234, case_id=CASE,
                   source_sha256=SOURCE, jar_sha256=JAR, loaded_code_sha256=CODE,
                   marker_sha256=MARKER, calls=calls)
    expectation = dict(pid=1234, case_id=CASE, source_sha256=SOURCE, jar_sha256=JAR,
                       loaded_code_sha256=CODE, marker_sha256=MARKER, markers=markers,
                       caller_code_indices=[17, 31, 47])
    return witness, expectation


class WitnessTest(unittest.TestCase):
    def test_synthetic_shape_stays_unpassed(self):
        witness, expected = fixture()
        result = verify_stream(witness, expected)
        self.assertEqual(result["status"], "UNPASSED_WORKER_BINDING")
        self.assertEqual(result["qualification"], "UNPASSED")
        self.assertEqual(result["calls_checked"], 1800)

    def test_changed_order_missing_and_extra(self):
        for mutation in (lambda calls: calls.reverse(), lambda calls: calls.pop(),
                         lambda calls: calls.append(copy.deepcopy(calls[-1]))):
            witness, expected = fixture()
            mutation(witness["calls"])
            self.assertEqual(verify_stream(witness, expected)["status"], "FAILED_COVERAGE")

    def test_changed_bits_and_marker(self):
        for target, field, value in (("calls", "pre", [ZERO, ZERO]),
                                     ("calls", "angle_bits", "8000000000000000"),
                                     ("markers", "trig", [ZERO, ZERO])):
            witness, expected = fixture()
            item = witness["calls"][1] if target == "calls" else expected["markers"][1]
            item[field] = value
            self.assertEqual(verify_stream(witness, expected)["status"], "FAILED_ARITHMETIC")

    def test_changed_identity_and_code(self):
        for field in ("pid", "source_sha256", "jar_sha256", "loaded_code_sha256",
                      "marker_sha256", "case_id"):
            witness, expected = fixture()
            witness[field] = "other"
            self.assertEqual(verify_stream(witness, expected)["status"], "FAILED_IDENTITY")

    def test_changed_caller_receiver_and_method(self):
        for field, value in (("caller", "other"), ("caller_code_index", 18),
                             ("receiver", 10), ("method", "rotateObserved")):
            witness, expected = fixture()
            witness["calls"][0][field] = value
            self.assertEqual(verify_stream(witness, expected)["status"], "FAILED_SOURCE_SITE")

    def test_malformed_and_unknown_schema(self):
        witness, expected = fixture()
        witness["calls"][0] = 0
        self.assertEqual(verify_stream(witness, expected)["status"], "FAILED_COVERAGE")
        witness, expected = fixture()
        witness["schema"] = "boolean-rotation-jdi/2"
        self.assertEqual(verify_stream(witness, expected)["status"], "FAILED_SCHEMA")

    def test_missing_independent_caller_locations_stays_unpassed(self):
        witness, expected = fixture()
        del expected["caller_code_indices"]
        self.assertEqual(verify_stream(witness, expected)["status"],
                         "UNPASSED_SOURCE_CALL_SITE")


if __name__ == "__main__":
    unittest.main()
