import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare


TOOL = Path(__file__).with_name("receipt.py")


class ReceiptConsumerTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "catalog.json").write_text(json.dumps({
            "profiles": {"tiny": {}},
            "fixtures": [{"key": "tiny", "profile": "tiny", "id": "tiny",
                          "counts": {"inputs": 1, "state": 1}}],
        }))

    def inspect(self, rows):
        trace = self.root / "trace.jsonl"
        trace.write_text("".join(rows))
        return subprocess.run(
            [sys.executable, str(TOOL), "inspect", "--catalog", str(self.root / "catalog.json"),
             "--fixture", "tiny", "--trace", str(trace)],
            text=True, capture_output=True, check=False,
        )

    def test_signed_zero_survives_record_parsing(self):
        result = self.inspect([
            '{"kind":"inputs","id":"tiny","value":-0.0}\n',
            '{"kind":"state","step":1,"state":{"value":-0.0}}\n',
        ])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["executed_counts"], {"inputs": 1, "state": 1})
        parsed = compare.parse('{"value":-0.0}'.encode())
        self.assertEqual(math.copysign(1.0, parsed["value"]), -1.0)
        self.assertFalse(compare.same_value(parsed["value"], 0.0))

    def test_missing_extra_duplicate_nonfinite_and_unknown_records_are_rejected(self):
        valid = ['{"kind":"inputs","id":"tiny"}\n',
                 '{"kind":"state","step":1,"state":{}}\n']
        cases = [
            valid[:1],
            valid + [valid[1]],
            ['{"kind":"inputs","id":"tiny","id":"tiny"}\n', valid[1]],
            [valid[0], '{"kind":"state","step":1,"state":{"x":NaN}}\n'],
            [valid[0], '{"kind":"unknown"}\n', valid[1]],
        ]
        for rows in cases:
            with self.subTest(rows=rows):
                result = self.inspect(rows)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(json.loads(result.stdout)["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
