import json
import math
import os
import subprocess
import sys
import tempfile
import types
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


class CanonicalCurrentSourceTest(unittest.TestCase):
    @staticmethod
    def archive_hash(commit, autocrlf):
        environment = dict(os.environ, GIT_CONFIG_COUNT="1",
                           GIT_CONFIG_KEY_0="core.autocrlf",
                           GIT_CONFIG_VALUE_0=autocrlf)
        archive = subprocess.run(["git", "archive", "--format=tar", commit],
                                 cwd=receipt.ROOT, env=environment,
                                 capture_output=True, check=True).stdout
        return receipt.sha256(archive)

    def test_current_source_hash_is_canonical_across_git_configs(self):
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=receipt.ROOT,
                                capture_output=True, check=True, text=True).stdout.strip()
        canonical = self.archive_hash(commit, "false")
        raw_windows = self.archive_hash(commit, "true")
        self.assertNotEqual(canonical, raw_windows)
        for autocrlf in ("false", "true"):
            environment = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.autocrlf",
                           "GIT_CONFIG_VALUE_0": autocrlf}
            with self.subTest(autocrlf=autocrlf), patch.dict(os.environ, environment):
                self.assertEqual(receipt.source_hash(), canonical)
                self.assertEqual(receipt.source_hash(commit), canonical)
                self.assertNotEqual(receipt.source_hash(commit), raw_windows)

    def test_current_source_rejects_invalid_or_noncommit_revision(self):
        tree = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=receipt.ROOT,
                              capture_output=True, check=True, text=True).stdout.strip()
        for revision in ("HEAD", None, "f" * 40, tree,
                         "f5053629d68dc134092434310c3d130ee1c0d9b5"):
            with self.subTest(revision=revision), self.assertRaises(compare.Rejected):
                receipt.source_hash(revision)

    def test_receipt_rejects_raw_windows_source_hash(self):
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=receipt.ROOT,
                                capture_output=True, check=True, text=True).stdout.strip()
        stale = dict.fromkeys(receipt.RECEIPT_FIELDS, "unused")
        stale.update(fixture_key="tiny", candidate_commit=commit,
                     source_hash_method="SHA-256 of git archive --format=tar HEAD",
                     source_sha256=self.archive_hash(commit, "true"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            path.write_text(json.dumps(stale))
            args = types.SimpleNamespace(receipt=path, fixture="tiny")
            environment = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.autocrlf",
                           "GIT_CONFIG_VALUE_0": "true"}
            with patch.dict(os.environ, environment), \
                 patch.object(receipt, "clean_commit", return_value=commit), \
                 self.assertRaisesRegex(compare.Rejected, "source hash is stale"):
                receipt.verify(args, {"counts": {}}, {})

    def test_current_source_archive_command_failure_is_rejected(self):
        original = receipt.run

        def failed_archive(*args):
            if "archive" in args:
                raise subprocess.CalledProcessError(1, args)
            return original(*args)

        with patch.object(receipt, "run", side_effect=failed_archive), \
             self.assertRaisesRegex(compare.Rejected, "source archive unavailable"):
            receipt.source_hash()


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
        fixture = {"counts": {"state": 1, "outer-endpoint": 1}, "inner_per_outer": 1}
        trace = self.root / "endpoint.jsonl"
        state = {"bodies": [], "x": 0.0}
        for value, accepted in ((-0.0, True), (False, False), (0.001, False)):
            rows = [{"kind": "state", "step": 1, "state": state},
                    {"kind": "outer-endpoint", "step": 1, "outerStep": 1,
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
                   "inner_per_outer": 1,
                   "physical_phase_ceilings_m": {"rest": 0.0}}
        trace = self.root / "physical-endpoint.jsonl"
        state = {"bodies": [], "x": 0.0}
        with patch.object(sleep_physical.physical, "phases_for_fixture",
                          return_value=[("rest", 1, 1)]), \
             patch.object(sleep_physical.physical, "depth_for_state",
                          return_value=Fraction(0)):
            for value, accepted in ((-0.0, True), (False, False), (0.001, False)):
                rows = [{"kind": "state", "step": 1, "state": state},
                        {"kind": "outer-endpoint", "step": 1, "outerStep": 1,
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

    def test_local_endpoint_indices_and_input_scope(self):
        fixture = {"counts": {"state": 2, "outer-endpoint": 1},
                   "start_step": 10, "inner_per_outer": 2}
        rows = [{"kind": "inputs", "id": "changed", "value": 123},
                {"kind": "state", "step": 11, "state": {"bodies": [], "x": 0.0}},
                {"kind": "state", "step": 12, "state": {"bodies": [], "x": 0.0}},
                {"kind": "outer-endpoint", "step": 12, "outerStep": 1,
                 "state": {"bodies": [], "x": -0.0}}]
        trace = self.root / "local-indices.jsonl"

        def inspect():
            trace.write_text("".join(json.dumps(row) + "\n" for row in rows))
            return same_run.inspect(fixture, trace)

        self.assertEqual(inspect()["endpoint_copies"], 1)
        for index, field, value in ((1, "step", 12), (1, "step", True),
                                    (2, "step", 13), (2, "step", True),
                                    (3, "step", 11), (3, "step", True),
                                    (3, "outerStep", 2), (3, "outerStep", True)):
            original = rows[index][field]
            rows[index][field] = value
            with self.subTest(index=index, field=field, value=value), self.assertRaises(compare.Rejected):
                inspect()
            rows[index][field] = original
            del rows[index][field]
            with self.subTest(index=index, field=field, value="missing"), self.assertRaises(compare.Rejected):
                inspect()
            rows[index][field] = original
        for group in (None, 0, True, -1):
            changed = dict(fixture)
            if group is None:
                changed.pop("inner_per_outer")
            else:
                changed["inner_per_outer"] = group
            with self.subTest(group=group), self.assertRaises(compare.Rejected):
                same_run.inspect(changed, trace)
        rows[2], rows[3] = rows[3], rows[2]
        with self.assertRaises(compare.Rejected):
            inspect()
        rows[2], rows[3] = rows[3], rows[2]
        rows[0]["value"] = 456
        self.assertEqual(inspect()["endpoint_copies"], 1)

    def test_physical_endpoint_indices(self):
        fixture = {"counts": {"state": 2, "outer-endpoint": 1},
                   "start_step": 10, "inner_per_outer": 2,
                   "physical_phase_ceilings_m": {"rest": 0.0}}
        rows = [{"kind": "state", "step": 11, "state": {"bodies": [], "x": 0.0}},
                {"kind": "state", "step": 12, "state": {"bodies": [], "x": 0.0}},
                {"kind": "outer-endpoint", "step": 12, "outerStep": 1,
                 "state": {"bodies": [], "x": -0.0}}]
        trace = self.root / "physical-indices.jsonl"

        def audit():
            trace.write_text("".join(json.dumps(row) + "\n" for row in rows))
            return sleep_physical.audit(trace, fixture)

        with patch.object(sleep_physical.physical, "phases_for_fixture",
                          return_value=[("rest", 1, 2)]), \
             patch.object(sleep_physical.physical, "depth_for_state",
                          return_value=Fraction(0)):
            self.assertEqual(audit()["endpoint_mappings"], 1)
            for index, field, value in ((0, "step", 12), (0, "step", True),
                                        (1, "step", 13), (1, "step", True),
                                        (2, "step", 11), (2, "step", True),
                                        (2, "outerStep", 2), (2, "outerStep", True)):
                original = rows[index][field]
                rows[index][field] = value
                with self.subTest(index=index, field=field, value=value), self.assertRaises(compare.Rejected):
                    audit()
                rows[index][field] = original
                del rows[index][field]
                with self.subTest(index=index, field=field, value="missing"), self.assertRaises(compare.Rejected):
                    audit()
                rows[index][field] = original
            for group in (None, 0, True, -1):
                changed = dict(fixture)
                if group is None:
                    changed.pop("inner_per_outer")
                else:
                    changed["inner_per_outer"] = group
                with self.subTest(group=group), self.assertRaises(compare.Rejected):
                    sleep_physical.audit(trace, changed)
            rows[1], rows[2] = rows[2], rows[1]
            with self.assertRaises(compare.Rejected):
                audit()

    def test_same_run_cli_reports_unbound_scope(self):
        from contextlib import redirect_stdout
        from io import StringIO

        output = StringIO()
        with patch.object(sys, "argv", ["same_run.py", "--fixture", "tiny", "--trace", "unused"]), \
             patch.object(same_run, "load_fixture", return_value={}), \
             patch.object(same_run, "inspect", return_value={"states": 1}), \
             redirect_stdout(output), self.assertRaises(SystemExit) as exit_code:
            same_run.main()
        self.assertEqual(exit_code.exception.code, 0)
        self.assertEqual(json.loads(output.getvalue())["scope"], "UNBOUND_DIAGNOSTIC")
        output = StringIO()
        with patch.object(sys, "argv", ["same_run.py", "--fixture", "tiny", "--trace", "unused"]), \
             patch.object(same_run, "load_fixture", return_value={}), \
             patch.object(same_run, "inspect", side_effect=compare.Rejected("invalid")), \
             redirect_stdout(output), self.assertRaises(SystemExit) as exit_code:
            same_run.main()
        self.assertEqual(exit_code.exception.code, 1)
        self.assertEqual(json.loads(output.getvalue())["scope"], "UNBOUND_DIAGNOSTIC")

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
