import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import duplicate_provider
import independent_gates
import qualify


ROOT = Path(__file__).resolve().parents[2]
HEAD = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                               text=True).strip()


class DuplicateProviderCaptureTests(unittest.TestCase):
    def test_failing_gradle_diagnostic_binds_graph_source_and_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / "staging"
            hashes = {}
            for module in qualify.MODULES:
                artifact = staging / qualify.target_binary_path(module, "jvm")
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_bytes((module + " staged bytes").encode())
                hashes[module] = hashlib.sha256(artifact.read_bytes()).hexdigest()
            audit = root / "audit.json"
            audit.write_text(json.dumps({"candidate_sha": HEAD, "status": "PASSED",
                                         "artifacts": []}))
            graph = (b"> Task :dependencies\norg.dyn4j:dyn4j:6.0.0\n"
                     b"io.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1\nBUILD SUCCESSFUL\n")
            failure = (b"> Task :verifySingleProvider FAILED\n"
                       b"duplicate org.dyn4j provider: exclude org.dyn4j:dyn4j\nBUILD FAILED\n")

            def run(command, **_):
                if command[0] == "java":
                    return subprocess.CompletedProcess(command, 0, b"", b"openjdk version 21\n")
                if "dependencies" in command:
                    return subprocess.CompletedProcess(command, 0, graph)
                return subprocess.CompletedProcess(command, 1, failure)

            output = root / "provider"
            with (mock.patch.object(qualify, "require_clean_checkout"),
                  mock.patch.object(qualify, "verify_audit_against_staging"),
                  mock.patch.object(qualify, "target_binary_hashes",
                                    return_value={"jvm": hashes}),
                  mock.patch.object(duplicate_provider, "run_command", side_effect=run)):
                receipt = duplicate_provider.run_capture(ROOT, HEAD, staging, audit, output)
            self.assertEqual("PASSED", receipt["status"])
            self.assertEqual(1, receipt["process"]["exit_code"])
            self.assertEqual(hashes, receipt["artifact_hashes"])
            self.assertEqual(HEAD, receipt["candidate_sha"])
            self.assertRegex(independent_gates._inventory(output, receipt), r"[0-9a-f]{64}")
            lane = independent_gates.load_approved_manifest(ROOT)["lanes"][duplicate_provider.LANE]
            observed = independent_gates.evaluate_gate(
                "duplicate-provider", output, HEAD, duplicate_provider.LANE, lane, ROOT,
                hashes, receipt["runtime_identity"], independent_gates.archive_digest(output))
            self.assertEqual("PASSED", observed["status"])
            (output / "graph.log").write_bytes(graph + b"forged")
            changed = independent_gates.evaluate_gate(
                "duplicate-provider", output, HEAD, duplicate_provider.LANE, lane, ROOT,
                hashes, receipt["runtime_identity"], independent_gates.archive_digest(output))
            self.assertEqual("FAILED", changed["status"])
            def zero_exit(command, **kwargs):
                result = run(command, **kwargs)
                if command[-1] == "verifySingleProvider":
                    return subprocess.CompletedProcess(command, 0, result.stdout)
                return result
            with (mock.patch.object(qualify, "require_clean_checkout"),
                  mock.patch.object(qualify, "verify_audit_against_staging"),
                  mock.patch.object(qualify, "target_binary_hashes",
                                    return_value={"jvm": hashes}),
                  mock.patch.object(duplicate_provider, "run_command", side_effect=zero_exit)):
                forged = duplicate_provider.run_capture(ROOT, HEAD, staging, audit,
                                                        root / "zero-exit")
            self.assertEqual("FAILED", forged["status"])
            self.assertEqual(0, forged["process"]["exit_code"])


if __name__ == "__main__":
    unittest.main()
