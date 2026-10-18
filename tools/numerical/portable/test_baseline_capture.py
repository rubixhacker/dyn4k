import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import baseline_capture
import run
from baseline_capture import (angle_failure, baseline_inventory, verify_baseline_jar,
                              verify_archive, verify_case_slices, verify_method_files,
                              verify_attestation, write_attestation)
from cases import declared_cases
from receipt import digest


class BaselineCaptureSeamTest(unittest.TestCase):
    def test_recorder_revision_ignores_same_type_commit_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            subprocess.run(("git", "init", "-q", str(root)), check=True)
            source = root / "source.txt"
            source.write_text("original\n")
            subprocess.run(("git", "-C", str(root), "add", "."), check=True)
            commit = ("git", "-C", str(root), "-c", "user.name=Test", "-c",
                      "user.email=test@example.invalid", "commit", "-qm")
            subprocess.run((*commit, "original"), check=True)
            original = subprocess.check_output(("git", "-C", str(root), "rev-parse", "HEAD"),
                                               text=True).strip()
            source.write_text("substituted\n")
            subprocess.run(("git", "-C", str(root), "add", "."), check=True)
            subprocess.run((*commit, "substitute"), check=True)
            substitute = subprocess.check_output(("git", "-C", str(root), "rev-parse", "HEAD"),
                                                 text=True).strip()
            subprocess.run(("git", "-C", str(root), "replace", original, substitute), check=True)
            output = Path(directory) / "archive"
            output.mkdir()
            with patch.object(run, "ROOT", root), \
                    patch.object(baseline_capture, "verify_baseline_jar"), \
                    patch.object(baseline_capture, "fixture_source_sha256",
                                 return_value="fixture"):
                canonical = hashlib.sha256(baseline_capture.git(
                    "--no-replace-objects", "-c", "core.autocrlf=false", "archive",
                    "--format=tar", original)).hexdigest()
                substituted = hashlib.sha256(baseline_capture.git(
                    "-c", "core.autocrlf=false", "archive", "--format=tar",
                    original)).hexdigest()
                self.assertNotEqual(canonical, substituted)
                result = {"status": "CAPTURED_WITH_FAILED_ANGLE_PHYSICAL",
                          "baseline_jar_sha256": baseline_capture.PINNED_JAR_SHA256,
                          "baseline_source_revision": baseline_capture.PINNED_SOURCE_REVISION,
                          "fixture_source_sha256": "fixture",
                          "candidate_recorder_commit": original,
                          "source_sha256": canonical, "methods": []}
                (output / "result.json").write_text(json.dumps(result))
                with self.assertRaisesRegex(Exception, "baseline method inventory differs"):
                    verify_archive(output, write_verified=False)
                result["source_sha256"] = substituted
                (output / "result.json").write_text(json.dumps(result))
                with self.assertRaisesRegex(Exception, "captured recorder source archive differs"):
                    verify_archive(output, write_verified=False)

    def test_recorder_revision_rejects_tree_even_when_replaced_with_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            subprocess.run(("git", "init", "-q", str(root)), check=True)
            (root / "source.txt").write_text("original\n")
            subprocess.run(("git", "-C", str(root), "add", "."), check=True)
            subprocess.run(("git", "-C", str(root), "-c", "user.name=Test", "-c",
                            "user.email=test@example.invalid", "commit", "-qm", "source"),
                           check=True)
            commit = subprocess.check_output(("git", "-C", str(root), "rev-parse", "HEAD"),
                                             text=True).strip()
            tree = subprocess.check_output(("git", "-C", str(root), "rev-parse", "HEAD^{tree}"),
                                           text=True).strip()
            subprocess.run(("git", "-C", str(root), "update-ref", f"refs/replace/{tree}",
                            commit), check=True)
            self.assertEqual(subprocess.check_output(("git", "-C", str(root), "cat-file",
                                                      "-t", tree)).strip(), b"commit")
            output = Path(directory) / "archive"
            output.mkdir()
            with patch.object(run, "ROOT", root), \
                    patch.object(baseline_capture, "verify_baseline_jar"), \
                    patch.object(baseline_capture, "fixture_source_sha256",
                                 return_value="fixture"):
                source_hash = hashlib.sha256(baseline_capture.git(
                    "--no-replace-objects", "-c", "core.autocrlf=false", "archive",
                    "--format=tar", tree)).hexdigest()
                (output / "result.json").write_text(json.dumps({
                    "status": "CAPTURED_WITH_FAILED_ANGLE_PHYSICAL",
                    "baseline_jar_sha256": baseline_capture.PINNED_JAR_SHA256,
                    "baseline_source_revision": baseline_capture.PINNED_SOURCE_REVISION,
                    "fixture_source_sha256": "fixture", "candidate_recorder_commit": tree,
                    "source_sha256": source_hash, "methods": []}))
                with self.assertRaisesRegex(Exception, "recorder source revision is invalid"):
                    verify_archive(output, write_verified=False)

    def test_recorder_source_archive_is_canonical_for_current_and_historical_commits(self):
        revisions = {
            "8b43f38d60bdee314fde06028b79bf73696d2c08":
                "dee954984cc6064927b03438f180727a0e692259eaa017bae9b034dc7db2e604",
            "cd21a4bd7d6731a096597f97966db9e02b9de448":
                "7958113412c14be8e106706a77871eba4dc8c4e1335c38fd01c7b9e18d26e12d",
        }
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(baseline_capture, "verify_baseline_jar"), \
                patch.object(baseline_capture, "fixture_source_sha256", return_value="fixture"):
            output = Path(directory)
            for revision, canonical in revisions.items():
                result = {"status": "CAPTURED_WITH_FAILED_ANGLE_PHYSICAL",
                          "baseline_jar_sha256": baseline_capture.PINNED_JAR_SHA256,
                          "baseline_source_revision": baseline_capture.PINNED_SOURCE_REVISION,
                          "fixture_source_sha256": "fixture",
                          "candidate_recorder_commit": revision,
                          "source_sha256": canonical, "methods": []}
                for setting in ("false", "true"):
                    with self.subTest(revision=revision, autocrlf=setting), \
                            patch.dict(os.environ, {"GIT_CONFIG_COUNT": "1",
                                                    "GIT_CONFIG_KEY_0": "core.autocrlf",
                                                    "GIT_CONFIG_VALUE_0": setting}):
                        (output / "result.json").write_text(json.dumps(result))
                        with self.assertRaisesRegex(Exception, "baseline method inventory differs"):
                            verify_archive(output, write_verified=False)
                with patch.dict(os.environ, {"GIT_CONFIG_COUNT": "1",
                                            "GIT_CONFIG_KEY_0": "core.autocrlf",
                                            "GIT_CONFIG_VALUE_0": "true"}):
                    converted = hashlib.sha256(baseline_capture.git(
                        "archive", "--format=tar", revision)).hexdigest()
                    self.assertNotEqual(converted, canonical)
                    result["source_sha256"] = converted
                    (output / "result.json").write_text(json.dumps(result))
                    with self.assertRaisesRegex(Exception, "captured recorder source archive differs"):
                        verify_archive(output, write_verified=False)
            for revision in ("abc", None):
                result["candidate_recorder_commit"] = revision
                result["source_sha256"] = revisions["8b43f38d60bdee314fde06028b79bf73696d2c08"]
                (output / "result.json").write_text(json.dumps(result))
                with self.subTest(malformed_revision=revision), \
                        self.assertRaisesRegex(Exception, "recorder source revision is invalid"):
                    verify_archive(output, write_verified=False)
            result["candidate_recorder_commit"] = "0" * 40
            (output / "result.json").write_text(json.dumps(result))
            with self.assertRaisesRegex(Exception, "recorder source revision is unavailable"):
                verify_archive(output, write_verified=False)

    def test_attestation_is_external_current_and_bound_to_original_seal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            root.mkdir()
            evidence = Path(directory) / "attestation.json"
            result = {"status": "CAPTURED_WITH_FAILED_ANGLE_PHYSICAL",
                      "trace_sha256": "a" * 64,
                      "methods": [{"method": name} for name in
                                  baseline_capture.MATRIX_METHODS]}
            seal = {"status": result["status"], "trace_sha256": "a" * 64,
                    "source_sha256": "b" * 64, "fixture_source_sha256": "c" * 64,
                    "baseline_jar_sha256": "d" * 64, "case_sha256": {"one": "e" * 64}}
            (root / "result.json").write_text(json.dumps(result))
            (root / "verified.json").write_text(json.dumps(seal))
            checked = {**seal, "xml_trace_counts": {"input_records": len(declared_cases()),
                       "completed_cases": len(declared_cases()),
                       "states": sum(case["steps"] for case in declared_cases()),
                       "events": 7807250, "endpoints": 252000,
                       "tagged_nonfinite_values": 14532},
                       "method_processes_verified": 15,
                       "captured_process_proofs": 0,
                       "observed_process_sha256": "f" * 64}
            original = digest(root / "verified.json")
            with self.assertRaises(FileNotFoundError):
                verify_attestation(root, evidence)
            with patch.object(baseline_capture, "verify_archive",
                              return_value=checked) as scan:
                written = write_attestation(root, evidence)
            scan.assert_called_once_with(root, write_verified=False)
            self.assertEqual(digest(root / "verified.json"), original)
            with patch.object(baseline_capture, "verify_archive",
                              return_value=checked) as scan, \
                    patch.object(baseline_capture, "_require_raw_archive"):
                self.assertEqual(verify_attestation(root, evidence)["schema"],
                                 "portable-baseline-attestation/1")
            scan.assert_called_once_with(root, write_verified=False)
            self.assertEqual(written["captured_process_proofs"], 0)
            for name, replacement in (
                    ("observed_process_sha256", "0" * 64),
                    ("method_processes_verified", 14),
                    ("method_processes_verified", 15.0),
                    ("captured_process_proofs", 15),
                    ("captured_process_proofs", False),
                    ("xml_trace_counts.events", 0),
                    ("xml_trace_counts.events", 7807250.0),
                    ("xml_trace_counts.endpoints", 0),
                    ("xml_trace_counts.tagged_nonfinite_values", 0)):
                with self.subTest(name=name):
                    changed = json.loads(evidence.read_text())
                    if name.startswith("xml_trace_counts."):
                        changed["xml_trace_counts"][name.split(".")[1]] = replacement
                    else:
                        changed[name] = replacement
                    evidence.write_text(json.dumps(changed))
                    with patch.object(baseline_capture, "verify_archive",
                                      return_value=checked), \
                            patch.object(baseline_capture, "_require_raw_archive"):
                        with self.assertRaisesRegex(Exception, "attestation"):
                            verify_attestation(root, evidence)
                    evidence.write_text(json.dumps(written))
            evidence.write_text("[]")
            with self.assertRaisesRegex(Exception, "malformed"):
                verify_attestation(root, evidence)
            evidence.write_text(json.dumps(written))
            (root / "verified.json").write_text(json.dumps({**seal,
                "trace_sha256": "0" * 64}))
            with self.assertRaisesRegex(Exception, "seal"):
                verify_attestation(root, evidence)
            (root / "verified.json").write_text(json.dumps(seal))
            data = json.loads(evidence.read_text())
            data["verifier_source_sha256"] = "0" * 64
            evidence.write_text(json.dumps(data))
            with self.assertRaisesRegex(Exception, "verifier"):
                verify_attestation(root, evidence)

    def test_attestation_requires_each_raw_dependency_before_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            root.mkdir()
            lane = root / "baseline-jvm"
            (lane / "xml").mkdir(parents=True)
            (lane / "cases").mkdir()
            (root / "dyn4j-6.0.0.jar").write_bytes(b"jar")
            (lane / "trace.jsonl").write_text("")
            for method in baseline_capture.MATRIX_METHODS:
                (lane / "xml" / f"{method}.xml").write_text("")
                (lane / f"gradle-{method}.log").write_text("")
            for case in declared_cases():
                (lane / "cases" / f"{case['id']}.jsonl").write_text("")
            result = {"status": "CAPTURED_WITH_FAILED_ANGLE_PHYSICAL",
                      "trace_sha256": "a" * 64,
                      "methods": [{"method": name} for name in
                                  baseline_capture.MATRIX_METHODS],
                      "raw_counts": {"per_case": {case["id"]: {}
                                                  for case in declared_cases()}}}
            seal = {"status": result["status"], "trace_sha256": result["trace_sha256"],
                    "source_sha256": "b" * 64, "fixture_source_sha256": "c" * 64,
                    "baseline_jar_sha256": "d" * 64, "case_sha256": {"one": "e" * 64}}
            (root / "result.json").write_text(json.dumps(result))
            (root / "verified.json").write_text(json.dumps(seal))
            checked = {**seal, "xml_trace_counts": {"input_records": 332},
                       "method_processes_verified": 15,
                       "captured_process_proofs": 0,
                       "observed_process_sha256": "f" * 64}
            attestation = Path(directory) / "attestation.json"
            with patch.object(baseline_capture, "verify_archive", return_value=checked):
                write_attestation(root, attestation)
            required = [
                root / "dyn4j-6.0.0.jar",
                lane / "trace.jsonl",
                lane / "xml" / f"{baseline_capture.MATRIX_METHODS[0]}.xml",
                lane / f"gradle-{baseline_capture.MATRIX_METHODS[0]}.log",
                lane / "cases" / f"{declared_cases()[0]['id']}.jsonl",
            ]
            with patch.object(baseline_capture, "verify_archive",
                              return_value=checked) as scan:
                verify_attestation(root, attestation)
            scan.assert_called_once_with(root, write_verified=False)
            for file in required:
                with self.subTest(file=file.name):
                    file.unlink()
                    with self.assertRaisesRegex(Exception, "raw archive"):
                        with patch.object(baseline_capture, "verify_archive",
                                          return_value=checked) as scan:
                            verify_attestation(root, attestation)
                        scan.assert_not_called()
                    file.write_text("")

    def test_xml_stream_must_equal_trace_even_after_trace_is_resealed(self):
        with tempfile.TemporaryDirectory() as directory:
            lane = Path(directory)
            (lane / "xml").mkdir()
            case_id = "long-free-60"
            rows = [{"kind": "inputs", "id": case_id},
                    {"kind": "event", "id": case_id, "step": 1, "name": "A"},
                    {"kind": "state", "id": case_id, "step": 1},
                    {"kind": "case-end", "id": case_id}]
            payloads = [json.dumps(row, separators=(",", ":")) for row in rows]
            (lane / "xml/longRunningFreeMotionInvariantScene.xml").write_text(
                '<testsuite tests="1"><system-out><![CDATA[\n' +
                ''.join("NUMERICAL_JSON " + value + "\n" for value in payloads) +
                ']]></system-out></testsuite>\n')
            trace = lane / "trace.jsonl"
            trace.write_text(''.join(value + "\n" for value in payloads))
            counts = {"expected_cases": 1, "input_records": 1, "observed_cases": 1,
                      "completed_cases": 1, "states": 1, "tagged_nonfinite_values": 0,
                      "per_case": {case_id: {"inputs": 1, "events": 1, "states": 1,
                                             "endpoints": 0, "case_ends": 1,
                                             "tagged_nonfinite_values": 0}}}
            methods = [{"method": "longRunningFreeMotionInvariantScene",
                        "completed_cases": 1}]
            self.assertEqual(baseline_capture.verify_xml_trace(lane, methods, counts,
                                                                digest(trace))["events"], 1)
            with self.assertRaisesRegex(Exception, "trace hash"):
                baseline_capture.verify_xml_trace(lane, methods, counts, "0" * 64)
            rows[1]["name"] = "B"
            trace.write_text(''.join(json.dumps(row, separators=(",", ":")) + "\n"
                                     for row in rows))
            with self.assertRaisesRegex(Exception, "XML.*trace"):
                baseline_capture.verify_xml_trace(lane, methods, counts, digest(trace))
            trace.write_text(''.join(value + "\n" for value in payloads))
            counts["per_case"][case_id]["events"] = 0
            with self.assertRaisesRegex(Exception, "per-case"):
                baseline_capture.verify_xml_trace(lane, methods, counts, digest(trace))
            counts["per_case"][case_id]["events"] = 1
            xml = lane / "xml/longRunningFreeMotionInvariantScene.xml"
            xml.write_text(xml.read_text().replace(
                "NUMERICAL_JSON " + payloads[1] + "\n",
                "NUMERICAL_JSON " + payloads[1] + " \n"))
            with self.assertRaisesRegex(Exception, "XML.*trace"):
                baseline_capture.verify_xml_trace(lane, methods, counts, digest(trace))

    def test_unrelated_failed_capture_cannot_be_reclassified(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "result.json").write_text(json.dumps(
                {"status": "FAILED", "reason": "baseline method failed"}))
            with self.assertRaisesRegex(Exception, "unrelated reason"):
                verify_archive(output)

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
