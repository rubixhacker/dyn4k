import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from baseline_capture import (angle_failure, baseline_inventory, verify_baseline_jar,
                              verify_case_slices, verify_method_files)
from cases import declared_cases
from receipt import digest


class BaselineCaptureSeamTest(unittest.TestCase):
    def test_archive_rejects_changed_case_slice_and_method_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lane = root / "baseline-jvm"
            (lane / "cases").mkdir(parents=True)
            (lane / "xml").mkdir()
            case_id = "one"
            rows = [{"kind": "inputs", "id": case_id},
                    {"kind": "state", "id": case_id, "step": 1},
                    {"kind": "case-end", "id": case_id}]
            payload = "".join(json.dumps(row) + "\n" for row in rows)
            (lane / "trace.jsonl").write_text(payload)
            case = lane / "cases/one.jsonl"
            case.write_text(payload)
            hashes = verify_case_slices(lane, {case_id})
            self.assertEqual(hashes[case_id], hashlib.sha256(payload.encode()).hexdigest())
            case.write_text(payload.replace('"step": 1', '"step": 2'))
            with self.assertRaisesRegex(Exception, "case slice differs"):
                verify_case_slices(lane, {case_id})
            case.write_text(payload)
            xml = lane / "xml/one.xml"
            log = lane / "gradle-one.log"
            xml.write_text("<testsuite tests=\"1\"/>")
            log.write_text("BUILD SUCCESSFUL")
            method = {"method": "one", "gradle_exit": 0,
                      "xml_sha256": digest(xml), "log_sha256": digest(log)}
            verify_method_files(lane, [method])
            xml.write_text("<testsuite tests=\"0\"/>")
            with self.assertRaisesRegex(Exception, "XML hash"):
                verify_method_files(lane, [method])

    def test_angle_records_early_energy_overflow_and_later_velocity_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / "cases/P-J-Angle-ratio-limits-off--1.0.jsonl"
            case.parent.mkdir()
            rows = [
                {"kind": "state", "id": "P-J-Angle-ratio-limits-off--1.0", "step": 86,
                 "state": {"bodies": [{"kineticEnergy": 1.0}]}},
                {"kind": "state", "id": "P-J-Angle-ratio-limits-off--1.0", "step": 87,
                 "state": {"bodies": [{"kineticEnergy": {"nonfinite": "Infinity"}}]}},
                {"kind": "state", "id": "P-J-Angle-ratio-limits-off--1.0", "step": 171,
                 "state": {"bodies": [{"angularVelocity": {"nonfinite": "-Infinity"}}]}},
            ]
            case.write_text("".join(json.dumps(row) + "\n" for row in rows))
            result = angle_failure(Path(directory))
            self.assertEqual(result["first_nonfinite_step"], 87)
            self.assertEqual(result["first_angular_velocity_nonfinite_step"], 171)
            rows[-1]["step"] = 170
            case.write_text("".join(json.dumps(row) + "\n" for row in rows))
            with self.assertRaisesRegex(Exception, "angular velocity"):
                angle_failure(Path(directory))

    def test_pinned_jar_rejects_changed_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dyn4j-6.0.0.jar"
            path.write_bytes(b"altered baseline")
            with self.assertRaisesRegex(Exception, "pinned dyn4j 6.0.0"):
                verify_baseline_jar(path)

    def test_inventory_rejects_missing_and_zero_case_capture(self):
        cases = declared_cases()
        observed = {case["id"]: {"inputs": 1, "states": case["steps"],
                                 "case_ends": 1, "events": 0, "endpoints": 0,
                                 "tagged_nonfinite_values": 0} for case in cases}
        raw = {"per_case": observed, "input_records": len(cases),
               "completed_cases": len(cases),
               "states": sum(case["steps"] for case in cases)}
        xml = {"tests": 15, "skipped": 0, "failures": 0, "errors": 0}
        baseline_inventory(raw, xml)
        removed = observed.pop(cases[0]["id"])
        with self.assertRaisesRegex(Exception, "case identity"):
            baseline_inventory(raw, xml)
        observed[cases[0]["id"]] = removed
        raw["completed_cases"] = 0
        with self.assertRaisesRegex(Exception, "completed"):
            baseline_inventory(raw, xml)


if __name__ == "__main__":
    unittest.main()
