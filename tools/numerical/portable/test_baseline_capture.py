import tempfile
import unittest
from pathlib import Path

from baseline_capture import baseline_inventory, verify_baseline_jar
from cases import declared_cases


class BaselineCaptureSeamTest(unittest.TestCase):
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
