import gzip
import json
import tempfile
import unittest
from pathlib import Path

from reference_diagnostic import strict_comparison


class FrozenComparatorSeamTest(unittest.TestCase):
    def test_full_record_fields_signed_zero_and_order(self):
        fixture = {"exact_numeric": ["inputs.value"]}
        baseline = [{"kind": "inputs", "value": -0.0},
                    {"kind": "event", "name": "begin"},
                    {"kind": "event", "name": "end"}]
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "reference.jsonl.gz"
            candidate = Path(directory) / "candidate.jsonl"
            with gzip.open(reference, "wt") as output:
                for row in baseline:
                    output.write(json.dumps(row) + "\n")

            def check(rows):
                candidate.write_text("".join(json.dumps(row) + "\n" for row in rows))
                return strict_comparison(fixture, reference, candidate)

            self.assertEqual(check(baseline)["status"], "PASSED")
            self.assertEqual(check([{**baseline[0], "value": 0.0}, *baseline[1:]])["status"], "FAILED")
            self.assertEqual(check([{**baseline[0], "extra": 1}, *baseline[1:]])["status"], "FAILED")
            self.assertEqual(check([baseline[0], baseline[2], baseline[1]])["status"], "FAILED")
            self.assertEqual(check(baseline[:-1])["status"], "FAILED")
