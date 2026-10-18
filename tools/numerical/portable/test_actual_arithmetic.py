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
    rows = [
        "NUMERICAL_JSON " + json.dumps({"kind": "inputs", "id": case_id,
                                        "steps": 1,
                                        "setup": {"bodies": [{"id": "b0"}]}}),
        "PROSPECTIVE_ROTATION_JSON " + json.dumps(operation),
        "NUMERICAL_JSON " + json.dumps({"kind": "state", "id": case_id,
                                        "step": 1, "state": {}}),
        "NUMERICAL_JSON " + json.dumps({"kind": "case-end", "id": case_id,
                                        "steps": 1}),
    ]
    return rows


class ActualArithmeticTest(unittest.TestCase):
    def test_same_target_chain_rejects_reordered_operations(self):
        rows = fixture()
        first = json.loads(rows[1].split(" ", 1)[1])
        second = copy.deepcopy(first)
        second["sequence"] = 1
        second["angle_bits"] = struct.pack(">d", 1e-16).hex()
        second["trig"] = [struct.pack(">d", 1.0).hex(), second["angle_bits"]]
        second["raw"] = second["trig"][:]
        second["post"] = second["trig"][:]
        rows.insert(2, "PROSPECTIVE_ROTATION_JSON " + json.dumps(second))
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
        operation.update(case_id="geometry-boundary-s0-o0-d0", step=1, body_id="b0")
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

    def test_public_capture_seam_verifies_arithmetic_but_not_target_binding(self):
        result = verify_capture(xml_for(fixture()), "captureGeometry",
                                ["geometry-boundary-s0-o0-d0"])
        self.assertEqual(result["status"], "UNPASSED_TARGET_BINDING")
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
