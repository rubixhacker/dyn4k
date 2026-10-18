import copy
import math
import struct
import unittest

from rotation_oracle import verify_operation_marker


def bits(value):
    return struct.pack(">d", value).hex()


def marker():
    return {
        "schema": "portable-rotation-op/2", "method": "observedProbe",
        "sequence": 0, "target_token": 0, "kind": "rotate", "source": "origin",
        "pre": [bits(1.0), bits(0.0)], "trig": [bits(1.0), bits(-0.0)],
        "raw": [bits(1.0), bits(0.0)], "post": [bits(1.0), bits(0.0)],
        "angle_bits": bits(-0.0), "alpha_bits": None,
        "start_angle_bits": None, "end_angle_bits": None,
        "diff_bits": None, "start": [None, None], "end": [None, None],
        "case_id": None, "step": None, "body_id": None,
    }


class OperationMarkerTest(unittest.TestCase):
    def test_executed_rotate_zero_and_adverse_bits(self):
        original = marker()
        self.assertEqual(verify_operation_marker(original)["status"], "PASSED_ARITHMETIC")
        changed = copy.deepcopy(original)
        changed["trig"][1] = bits(0.0)
        self.assertEqual(verify_operation_marker(changed)["status"], "FAILED_ARITHMETIC")
        changed = copy.deepcopy(original)
        changed["raw"][1] = bits(-0.0)
        self.assertEqual(verify_operation_marker(changed)["status"], "FAILED_ARITHMETIC")
        changed = copy.deepcopy(original)
        changed["raw"][0] = bits(math.nextafter(1.0, 0.0))
        self.assertEqual(verify_operation_marker(changed)["status"], "FAILED_ARITHMETIC")

    def test_schema_and_nonfinite_fail_closed(self):
        original = marker()
        for key in ("method", "target_token", "source", "angle_bits", "raw"):
            changed = copy.deepcopy(original)
            changed.pop(key)
            with self.subTest(key=key):
                self.assertEqual(verify_operation_marker(changed)["status"], "FAILED_ARITHMETIC")
        changed = copy.deepcopy(original)
        changed["post"][0] = bits(math.inf)
        self.assertEqual(verify_operation_marker(changed)["status"], "FAILED_ARITHMETIC")

    def test_trig_two_u_boundary_and_subnormal(self):
        original = marker()
        original["angle_bits"] = bits(1e-16)
        original["trig"] = [bits(1.0), bits(1e-16)]
        original["raw"] = [bits(1.0), bits(1e-16)]
        original["post"] = original["raw"][:]
        self.assertEqual(verify_operation_marker(original)["status"], "PASSED_ARITHMETIC")
        changed = copy.deepcopy(original)
        changed["trig"][0] = bits(1.0 + 2 * math.ulp(1.0))
        self.assertEqual(verify_operation_marker(changed)["status"], "FAILED_ARITHMETIC")


if __name__ == "__main__":
    unittest.main()
