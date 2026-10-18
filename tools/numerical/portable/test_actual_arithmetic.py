import copy
import json
import struct
import unittest
from xml.sax.saxutils import escape

from actual_arithmetic import CaptureRejected, expected_case_ids, verify_capture
from test_rotation_marker import marker


def xml_for(lines, method="captureGeometry"):
    output = "\n".join(lines) + "\n"
    return (f'<testsuite tests="1" skipped="0" failures="0" errors="0">'
            f'<testcase classname="portable.ProspectiveArithmeticTest" name="{method}[jvm]"/>'
            f'<system-out>{escape(output)}</system-out></testsuite>').encode()


def fixture():
    operation = marker()
    operation["method"] = "geometryCollisionBoundaryAndScale"
    case_id = "geometry-boundary-s0-o0-d0"
    operation.update(case_id=case_id, step=1, body_id="b0")
    identity = ["3ff0000000000000", "0000000000000000"]
    state_body = {"id": "b0", "transform": {"getCost": 1.0, "getSint": 0.0}}
    rows = [
        "NUMERICAL_JSON " + json.dumps({"kind": "inputs", "id": case_id,
                                        "steps": 1,
                                        "setup": {"bodies": [{"id": "b0"}]},
                                        "initial": {"bodies": [state_body]}}),
        "PROSPECTIVE_ROTATION_JSON " + json.dumps(operation),
        "NUMERICAL_JSON " + json.dumps({"kind": "state", "id": case_id,
                                        "step": 1, "order": 0,
                                        "state": {"bodies": [state_body]}}),
        "PROSPECTIVE_BINDING_JSON " + json.dumps({
            "kind": "body-step", "case_id": case_id, "step": 1,
            "bodies": [{"body_id": "b0", "calls": 1,
                        "pre": identity, "post": identity}],
            "temporary_calls": 0}),
        "NUMERICAL_JSON " + json.dumps({"kind": "case-end", "id": case_id,
                                        "steps": 1}),
    ]
    return rows


class ActualArithmeticTest(unittest.TestCase):
    def test_zero_call_body_step_is_required_and_matches_state(self):
        rows = fixture()
        rows.pop(1)
        receipt = json.loads(rows[2].split(" ", 1)[1])
        receipt["bodies"][0]["calls"] = 0
        rows[2] = "PROSPECTIVE_BINDING_JSON " + json.dumps(receipt)
        expected = ["geometry-boundary-s0-o0-d0"]
        result = verify_capture(xml_for(rows), "captureGeometry", expected)
        self.assertEqual(result["operations_verified"], 0)
        self.assertEqual(result["body_step_receipts"], 1)
        for changed in (rows[:2] + rows[3:],
                        [*rows[:2], rows[2].replace('"calls": 0', '"calls": 1'),
                         rows[3]]):
            with self.assertRaises(CaptureRejected):
                verify_capture(xml_for(changed), "captureGeometry", expected)

    def test_temporary_operation_is_counted_without_body_identity(self):
        rows = fixture()
        operation = json.loads(rows[1].split(" ", 1)[1])
        operation["body_id"] = None
        rows[1] = "PROSPECTIVE_ROTATION_JSON " + json.dumps(operation)
        receipt = json.loads(rows[3].split(" ", 1)[1])
        receipt["bodies"][0]["calls"] = 0
        receipt["temporary_calls"] = 1
        rows[3] = "PROSPECTIVE_BINDING_JSON " + json.dumps(receipt)
        result = verify_capture(xml_for(rows), "captureGeometry",
                                ["geometry-boundary-s0-o0-d0"])
        self.assertEqual(result["temporary_operations"], 1)
        receipt["temporary_calls"] = 0
        rows[3] = "PROSPECTIVE_BINDING_JSON " + json.dumps(receipt)
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(rows), "captureGeometry",
                           ["geometry-boundary-s0-o0-d0"])

    def test_listener_callback_alone_cannot_select_reset(self):
        rows = fixture()
        callback = {"kind": "event", "id": "geometry-boundary-s0-o0-d0",
                    "step": 1, "order": 0, "name": "toi.payload.bodies",
                    "payload": {"bodies": [0, 0], "time": 0.5}}
        selection = {"kind": "toi-accepted", "case_id": "geometry-boundary-s0-o0-d0",
                     "step": 1, "body_ids": ["b0", "b0"],
                     "reset_body_ids": ["b0"], "time_bits": "3fe0000000000000"}
        rows.insert(1, "NUMERICAL_JSON " + json.dumps(callback))
        rows.insert(2, "PROSPECTIVE_BINDING_JSON " + json.dumps(selection))
        state = json.loads(rows[4].split(" ", 1)[1])
        state["order"] = 1
        rows[4] = "NUMERICAL_JSON " + json.dumps(state)
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(rows), "captureGeometry",
                           ["geometry-boundary-s0-o0-d0"])
        selection["time_bits"] = "3fd0000000000000"
        rows[2] = "PROSPECTIVE_BINDING_JSON " + json.dumps(selection)
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(rows), "captureGeometry",
                           ["geometry-boundary-s0-o0-d0"])

    def test_same_target_chain_rejects_reordered_operations(self):
        rows = fixture()
        first = json.loads(rows[1].split(" ", 1)[1])
        second = copy.deepcopy(first)
        second["sequence"] = 1
        second["angle_bits"] = struct.pack(">d", 1e-16).hex()
        second["trig"] = [struct.pack(">d", 1.0).hex(), second["angle_bits"]]
        second["raw"] = second["trig"][:]
        second["post"] = second["trig"][:]
        second["case_id"] = first["case_id"]
        second["step"] = first["step"]
        second["body_id"] = first["body_id"]
        rows.insert(2, "PROSPECTIVE_ROTATION_JSON " + json.dumps(second))
        receipt = json.loads(rows[4].split(" ", 1)[1])
        receipt["bodies"][0]["calls"] = 2
        receipt["bodies"][0]["post"] = second["post"]
        rows[4] = "PROSPECTIVE_BINDING_JSON " + json.dumps(receipt)
        state = json.loads(rows[3].split(" ", 1)[1])
        state["state"]["bodies"][0]["transform"]["getSint"] = 1e-16
        rows[3] = "NUMERICAL_JSON " + json.dumps(state)
        expected = ["geometry-boundary-s0-o0-d0"]
        self.assertEqual(verify_capture(xml_for(rows), "captureGeometry", expected)
                         ["operations_verified"], 2)
        first["sequence"] = 1
        second["sequence"] = 0
        rows[1] = "PROSPECTIVE_ROTATION_JSON " + json.dumps(second)
        rows[2] = "PROSPECTIVE_ROTATION_JSON " + json.dumps(first)
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(rows), "captureGeometry", expected)

    def test_bound_case_step_and_body_must_match_trace(self):
        rows = fixture()
        operation = json.loads(rows[1].split(" ", 1)[1])
        rows[1] = "PROSPECTIVE_ROTATION_JSON " + json.dumps(operation)
        expected = ["geometry-boundary-s0-o0-d0"]
        bound = verify_capture(xml_for(rows), "captureGeometry", expected)
        self.assertEqual(bound["operations_verified"], 1)
        self.assertEqual(bound["body_bound_operations"], 1)
        for field, value in (("case_id", "other"), ("step", 2), ("body_id", "b9")):
            changed = copy.deepcopy(operation)
            changed[field] = value
            rows[1] = "PROSPECTIVE_ROTATION_JSON " + json.dumps(changed)
            with self.subTest(field=field), self.assertRaises(CaptureRejected):
                verify_capture(xml_for(rows), "captureGeometry", expected)

    def test_case_inventory_is_complete(self):
        mapping = expected_case_ids()
        self.assertEqual(len(mapping), 15)
        self.assertEqual(sum(map(len, mapping.values())), 332)
        self.assertEqual(len(mapping["captureJoints"]), 24)
        self.assertEqual(len(mapping["captureCcd"]), 12)
        self.assertEqual(len(set().union(*(set(ids) for ids in mapping.values()))), 332)
        self.assertEqual(len(set().union(*(set(ids) for ids in mapping.values())) -
                             {case for ids in mapping.values() for case in ids
                              if case.startswith("contacts-") or case == "long-free-60" or
                              case.startswith("P-JINT-")}), 318)

    def test_public_capture_seam_verifies_binding_without_case_qualification(self):
        result = verify_capture(xml_for(fixture()), "captureGeometry",
                                ["geometry-boundary-s0-o0-d0"])
        self.assertEqual(result["status"], "VERIFIED_ARITHMETIC_BINDING")
        self.assertEqual(result["qualification"], "UNPASSED")
        self.assertEqual(result["cases"], 1)
        self.assertEqual(result["operations_verified"], 1)
        self.assertEqual(result["steps"], 1)

    def test_missing_extra_reordered_and_wrong_method_fail(self):
        original = fixture()
        expected = ["geometry-boundary-s0-o0-d0"]
        for rows in (original[:-1], original + original[-1:],
                     [original[1], original[0], *original[2:]]):
            with self.subTest(rows=rows):
                with self.assertRaises(CaptureRejected):
                    verify_capture(xml_for(rows), "captureGeometry", expected)
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(original, "captureJoints"), "captureGeometry", expected)
        changed = copy.deepcopy(original)
        changed[1] = changed[1].replace('"sequence": 0', '"sequence": 1')
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(changed), "captureGeometry", expected)
        changed = copy.deepcopy(original)
        changed[1] = changed[1].replace('"body_id": "b0"',
                                        '"body_id": "b0", "body_id": "b0"')
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(changed), "captureGeometry", expected)
        changed = copy.deepcopy(original)
        state = json.loads(changed[2].split(" ", 1)[1])
        state["order"] = 2
        changed[2] = "NUMERICAL_JSON " + json.dumps(state)
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(changed), "captureGeometry", expected)
        changed = copy.deepcopy(original)
        changed.insert(2, "NUMERICAL_JSON " + json.dumps({
            "kind": "unknown", "id": expected[0], "step": 1, "order": 0}))
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(changed), "captureGeometry", expected)

    def test_adverse_operation_and_nonfinite_fail(self):
        rows = fixture()
        operation = json.loads(rows[1].split(" ", 1)[1])
        operation["raw"][0] = "7ff0000000000000"
        rows[1] = "PROSPECTIVE_ROTATION_JSON " + json.dumps(operation)
        with self.assertRaises(CaptureRejected):
            verify_capture(xml_for(rows), "captureGeometry",
                           ["geometry-boundary-s0-o0-d0"])


if __name__ == "__main__":
    unittest.main()
