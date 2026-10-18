import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run


class ExtractionTest(unittest.TestCase):
    def test_comparison_coverage_lists_every_unreferenced_case(self):
        coverage = run.comparison_coverage()
        self.assertEqual(coverage["declared_cases"], 332)
        self.assertEqual(coverage["frozen_reference_cases"], 14)
        self.assertEqual(coverage["unreferenced_cases"], 318)
        self.assertEqual(coverage["status"], "UNPASSED_REFERENCE_COVERAGE")
        self.assertEqual(len(coverage["unreferenced_case_ids"]), 318)
        self.assertNotIn("long-free-60", coverage["unreferenced_case_ids"])

    def test_java_8_receipt_uses_executed_test_worker(self):
        executable = Path("/tmp/dyn4k-tools/jdk8/bin/java")
        if not executable.is_file():
            self.skipTest("Java 8 test runtime is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "gradle.log"
            log.write_text("Starting process 'Gradle Test Executor 1'. Command: " +
                           str(executable) + " -cp worker.jar\n")
            result = run.runtime("jvm8", log)
        self.assertEqual(result["executable"], str(executable.resolve()))
        self.assertEqual(result["executable_sha256"], run.digest(executable))
        self.assertIn('version "1.8.', result["version"])

    def test_node_receipt_uses_executed_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "node"
            executable.write_text("#!/bin/sh\nprintf 'v99.1.0\\n'\n")
            executable.chmod(0o755)
            log = root / "gradle.log"
            log.write_text("Starting process 'command '" + str(executable) +
                           "''. Command: " + str(executable) + " test.js\n")
            expected_sha = run.digest(executable)
            result = run.runtime("node-js", log)
        self.assertEqual(result["executable"], str(executable.resolve()))
        self.assertEqual(result["executable_sha256"], expected_sha)
        self.assertEqual(result["version"], "v99.1.0")

    def test_xml_extraction_retains_whole_trace_and_case_slice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "build/test-results/jvmTest"
            results.mkdir(parents=True)
            case_id = "geometry-boundary-s0-o0-d0"
            rows = [{"kind": "inputs", "id": case_id},
                    {"kind": "state", "id": case_id, "step": 1},
                    {"kind": "case-end", "id": case_id}]
            xml = ("<?xml version=\"1.0\"?>\n"
                   "<testsuite tests=\"1\" skipped=\"0\" failures=\"0\" errors=\"0\">\n"
                   "<system-out><![CDATA[" +
                   "".join("NUMERICAL_JSON " + json.dumps(row) + "\n" for row in rows) +
                   "]]></system-out>\n</testsuite>\n")
            (results / "TEST-portable.PortableMatrixTest.xml").write_text(xml)
            output = root / "evidence"
            output.mkdir()
            with patch.object(run, "PORTABLE", root):
                trace, attributes, raw_counts = run.extract_xml("jvm", output)
            self.assertEqual(attributes["tests"], "1")
            self.assertEqual(raw_counts["completed_cases"], 1)
            self.assertEqual(raw_counts["states"], 1)
            self.assertEqual(trace.read_text(), (output / "cases" / f"{case_id}.jsonl").read_text())
            self.assertEqual(len(trace.read_text().splitlines()), 3)
            self.assertTrue((output / "matrix.xml").is_file())

    def test_method_xmls_append_to_one_trace_without_losing_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "build/test-results/jvmTest"
            results.mkdir(parents=True)
            output = root / "evidence"
            output.mkdir()
            def report(case_id):
                rows = [{"kind": "inputs", "id": case_id},
                        {"kind": "state", "id": case_id, "step": 1},
                        {"kind": "case-end", "id": case_id}]
                (results / "TEST-portable.PortableMatrixTest.xml").write_text(
                    '<?xml version="1.0"?>\n'
                    '<testsuite tests="1" skipped="0" failures="0" errors="0">\n'
                    '<system-out><![CDATA[' +
                    ''.join("NUMERICAL_JSON " + json.dumps(row) + "\n" for row in rows) +
                    ']]></system-out>\n</testsuite>\n')
            with patch.object(run, "PORTABLE", root):
                report("geometry-boundary-s0-o0-d0")
                first = run.extract_xml("jvm", output, "geometryCollisionBoundaryAndScale")
                report("long-free-60")
                second = run.extract_xml("jvm", output, "longRunningFreeMotionInvariantScene")
            self.assertEqual(first[0], second[0])
            self.assertEqual(len(first[0].read_text().splitlines()), 6)
            self.assertEqual(first[2]["completed_cases"], 1)
            self.assertEqual(second[2]["completed_cases"], 1)
            self.assertTrue((output / "xml/geometryCollisionBoundaryAndScale.xml").is_file())
            self.assertTrue((output / "xml/longRunningFreeMotionInvariantScene.xml").is_file())
            self.assertTrue((output / "cases/geometry-boundary-s0-o0-d0.jsonl").is_file())
            self.assertTrue((output / "cases/long-free-60.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
