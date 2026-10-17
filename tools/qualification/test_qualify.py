import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import qualify


class QualificationTests(unittest.TestCase):
    def test_contract_covers_all_targets_and_runtime_families(self):
        rows = qualify.matrix()
        self.assertEqual(28, len(rows))
        self.assertEqual(21, len({row["target"] for row in rows}))
        self.assertEqual(112, len(qualify.expand(rows)))
        self.assertIn("watchosDeviceArm64", {row["target"] for row in rows})
        self.assertIn("Safari", {row["runtime"] for row in rows})
        self.assertEqual("18.2", next(row["minimum"] for row in rows if row["target"] == "js" and row["runtime"] == "Safari"))

    def test_missing_evidence_cannot_pass(self):
        case = qualify.expand(qualify.matrix())[0]
        self.assertEqual("NOT_RUN", qualify.evaluate(case, None)["status"])
        self.assertEqual("UNAVAILABLE", qualify.evaluate(case, {"unavailable_reason": "no device"})["status"])
        self.assertEqual("FAILED", qualify.evaluate(case, {"candidate_sha": "bad", "expected": 4, "executed": 4, "failures": 0})["status"])
        self.assertEqual("FAILED", qualify.evaluate(case, {"candidate_sha": "a" * 40, "expected": 4, "executed": 3, "failures": 0})["status"])

    def test_duplicate_provider_is_diagnosed(self):
        with tempfile.TemporaryDirectory() as root:
            graph = Path(root) / "dependencies.txt"
            graph.write_text("+--- io.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1\n\\--- org.dyn4j:dyn4j:6.0.0\n")
            with self.assertRaisesRegex(ValueError, "duplicate org.dyn4j provider"):
                qualify.check_providers(graph.read_text())

    def test_executor_failure_cannot_return_success(self):
        self.assertFalse(qualify.execution_succeeded({
            "jvm:Java:minimum:default": {
                "error": "command failed or result file missing",
                "exit_code": 1,
            }
        }))
        self.assertTrue(qualify.execution_succeeded({
            "jvm:Java:minimum:default": {
                "expected": 1,
                "executed": 1,
                "failures": 0,
                "skipped": 0,
                "exit_code": 0,
            }
        }))

    def test_candidate_identity_and_counts_are_required(self):
        case = qualify.expand(qualify.matrix())[0]
        evidence = {"candidate_sha": "a" * 40, "artifact_sha256": "b" * 64,
                    "runtime_identity": "OpenJDK 8u472", "runtime_version": "8u472", "expected": 2,
                    "executed": 2, "failures": 0, "skipped": 0,
                    "consumer": "PASSED", "suite": "complete",
                    "target": case["target"], "runtime": case["runtime"],
                    "version": case["version"], "configuration": case["configuration"]}
        target_hashes = {case["target"]: {evidence["artifact_sha256"]}}
        self.assertEqual("PASSED", qualify.evaluate(
            case, evidence, evidence["candidate_sha"], target_hashes)["status"])
        other_target_hashes = {case["target"]: {"c" * 64}}
        self.assertEqual("FAILED", qualify.evaluate(
            case, evidence, evidence["candidate_sha"], other_target_hashes)["status"])
        for field, value in (("expected", 0), ("skipped", 1), ("consumer", "NOT_RUN"),
                             ("artifact_sha256", ""), ("runtime_version", ""),
                             ("configuration", "wrong")):
            changed = dict(evidence, **{field: value})
            self.assertEqual("FAILED", qualify.evaluate(case, changed)["status"])

    def test_report_refuses_sha_other_than_checkout(self):
        with tempfile.TemporaryDirectory() as root:
            result = subprocess.run(
                ["python3", str(Path(__file__).with_name("qualify.py")), "record",
                 "--candidate-sha", "f" * 40, "--output", str(Path(root) / "report.json")],
                text=True, capture_output=True, check=False)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("checkout", result.stderr)


if __name__ == "__main__":
    unittest.main()
