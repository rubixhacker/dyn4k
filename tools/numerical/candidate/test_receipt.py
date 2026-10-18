import json
import math
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare
import receipt
import same_run
import sleep_physical


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

    def test_literal_instrumented_callback_is_not_a_state_snapshot(self):
        fixture = {"counts": {"state": 0, "instrumented-callback": 1}}
        rows = [(0, {"kind": "instrumented-callback", "event": "experimental-input-binding",
                     "values": ["pinned source", "experiment declaration"]})]
        with patch.object(compare, "records", return_value=iter(rows)):
            self.assertEqual(same_run.inspect(fixture, self.root / "unused"),
                             {"states": 0, "endpoint_copies": 0, "instrumented_callbacks": 1})
        rows[0][1]["values"] = [1]
        with patch.object(compare, "records", return_value=iter(rows)):
            with self.assertRaisesRegex(compare.Rejected, "unrecognized instrumented callback value"):
                same_run.inspect(fixture, self.root / "unused")

    def test_local_endpoint_copy_uses_finite_numeric_values(self):
        fixture = {"counts": {"state": 1, "outer-endpoint": 1}}
        trace = self.root / "endpoint.jsonl"
        state = {"bodies": [], "x": 0.0}
        for value, accepted in ((-0.0, True), (False, False), (0.001, False)):
            rows = [{"kind": "state", "step": 1, "state": state},
                    {"kind": "outer-endpoint", "step": 1,
                     "state": {"bodies": [], "x": value}}]
            trace.write_text("".join(json.dumps(row) + "\n" for row in rows))
            with self.subTest(value=value):
                if accepted:
                    self.assertEqual(same_run.inspect(fixture, trace)["endpoint_copies"], 1)
                else:
                    with self.assertRaisesRegex(compare.Rejected, "outer endpoint is not a state copy"):
                        same_run.inspect(fixture, trace)
        rows[1]["state"] = {"bodies": []}
        trace.write_text("".join(json.dumps(row) + "\n" for row in rows))
        with self.assertRaisesRegex(compare.Rejected, "outer endpoint is not a state copy"):
            same_run.inspect(fixture, trace)
        rows[1]["state"] = state
        rows[1]["step"] = True
        trace.write_text("".join(json.dumps(row) + "\n" for row in rows))
        with self.assertRaisesRegex(compare.Rejected, "outer endpoint is not a state copy"):
            same_run.inspect(fixture, trace)

    def test_physical_endpoint_copy_uses_finite_numeric_values(self):
        fixture = {"counts": {"state": 1, "outer-endpoint": 1},
                   "physical_phase_ceilings_m": {"rest": 0.0}}
        trace = self.root / "physical-endpoint.jsonl"
        state = {"bodies": [], "x": 0.0}
        with patch.object(sleep_physical.physical, "phases_for_fixture",
                          return_value=[("rest", 1, 1)]), \
             patch.object(sleep_physical.physical, "depth_for_state",
                          return_value=Fraction(0)):
            for value, accepted in ((-0.0, True), (False, False), (0.001, False)):
                rows = [{"kind": "state", "step": 1, "state": state},
                        {"kind": "outer-endpoint", "step": 1,
                         "state": {"bodies": [], "x": value}}]
                trace.write_text("".join(json.dumps(row) + "\n" for row in rows))
                with self.subTest(value=value):
                    if accepted:
                        self.assertEqual(sleep_physical.audit(trace, fixture)["endpoint_mappings"], 1)
                    else:
                        with self.assertRaisesRegex(compare.Rejected, "endpoint is not a copy"):
                            sleep_physical.audit(trace, fixture)
            rows[1]["state"] = state
            rows[1]["step"] = True
            trace.write_text("".join(json.dumps(row) + "\n" for row in rows))
            with self.assertRaisesRegex(compare.Rejected, "endpoint is not a copy"):
                sleep_physical.audit(trace, fixture)

    def test_receipt_uses_recorder_process_and_loaded_engine(self):
        trace = self.root / "trace.jsonl.gz"
        artifact = self.root / "candidate.jar"
        loaded = self.root / "loaded.jar"
        command = self.root / "java"
        artifact.write_bytes(b"candidate")
        loaded.write_bytes(b"candidate")
        command.write_bytes(b"actual launcher")
        stamp = {key: "known" for key in receipt.RUNTIME_FIELDS}
        stamp.update(process_command=str(command), engine_location=loaded.as_uri())
        with patch.object(receipt, "ARTIFACT", artifact):
            with self.assertRaisesRegex(compare.Rejected, "stamp is missing"):
                receipt.runtime_identity(trace)
            (self.root / "runtime.json").write_text(json.dumps(stamp))
            bound = receipt.runtime_identity(trace)
            self.assertEqual(bound["process_command_sha256"], receipt.sha256(command.read_bytes()))
            loaded.write_bytes(b"different provider")
            with self.assertRaisesRegex(compare.Rejected, "loaded engine differs"):
                receipt.runtime_identity(trace)


if __name__ == "__main__":
    unittest.main()
