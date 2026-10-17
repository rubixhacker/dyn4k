import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ledger import validate


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.reference = {
            "baseline": {"commit": "source-commit", "binary_sha256": "jar-sha", "sources_sha256": "source-jar-sha"},
            "production": {"src/main/java/p/A.java": sha("class A {}")},
            "tests": {"src/test/java/p/ATest.java": sha("class ATest {}")},
            "declarations": {"p.A|type": ("src/main/java/p/A.java", "public class p.A"),
                             "p.A|run|()V": ("src/main/java/p/A.java", "public void run(); descriptor: ()V")},
        }
        self.ledger = {
            "schema_version": 1, "baseline": copy.deepcopy(self.reference["baseline"]),
            "production": [{"id": path, "sha256": digest, "owner_type": "p.A",
                            "candidate": None, "evidence": []}
                           for path, digest in self.reference["production"].items()],
            "tests": [{"id": path, "sha256": digest, "owner_type": "p.ATest",
                       "candidate": None, "evidence": []}
                      for path, digest in self.reference["tests"].items()],
            "declarations": [{"id": key, "source_file": source, "signature": signature,
                              "candidate": None, "evidence": []}
                             for key, (source, signature) in self.reference["declarations"].items()],
        }

    def check_invalid(self, changed):
        broken = copy.deepcopy(self.ledger)
        changed(broken)
        result = validate(broken, self.reference, Path("."))
        self.assertTrue(result["invalid"], result)

    def test_partial_ledger_is_unpassed(self):
        result = validate(self.ledger, self.reference, Path("."))
        self.assertEqual(result["invalid"], [])
        self.assertFalse(result["passed"])
        self.assertEqual(result["missing_counterparts"], 4)

    def test_omitted_file_declaration_and_test_fail(self):
        for section in ("production", "declarations", "tests"):
            with self.subTest(section=section):
                self.check_invalid(lambda value: value[section].clear())

    def test_duplicate_mapping_fails(self):
        self.check_invalid(lambda value: value["declarations"].append(copy.deepcopy(value["declarations"][0])))
        self.check_invalid(lambda value: value["declarations"][1].update(candidate={"identity": "p.A"})
                           or value["declarations"][0].update(candidate={"identity": "p.A"}))

    def test_stale_source_and_jar_hash_fail(self):
        self.check_invalid(lambda value: value["baseline"].update(binary_sha256="stale"))
        self.check_invalid(lambda value: value["production"][0].update(sha256="stale"))
        self.check_invalid(lambda value: value["baseline"].update(sources_sha256="stale"))

    def test_fabricated_passed_evidence_fails(self):
        self.check_invalid(lambda value: value["tests"][0]["evidence"].append(
            {"kind": "java-test", "status": "passed", "report": "missing.json", "report_sha256": "fake"}))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "run.json"
            report.write_text(json.dumps({"actual_executed_cases": 1, "failures": 0, "ignored": 1,
                                          "process_exit_code": 0}))
            broken = copy.deepcopy(self.ledger)
            broken["tests"][0]["evidence"] = [{"kind": "java-test", "status": "passed", "report": "run.json",
                                                   "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest()}]
            result = validate(broken, self.reference, root)
            self.assertTrue(result["invalid"])

    def test_ignored_and_unapproved_exception_remain_unpassed(self):
        for status in ("ignored", "unapproved_exception", "unrun"):
            with self.subTest(status=status):
                value = copy.deepcopy(self.ledger)
                value["tests"][0]["evidence"] = [{"kind": "java-test", "status": status}]
                result = validate(value, self.reference, Path("."))
                self.assertFalse(result["passed"])
                self.assertTrue(any(status in gap for gap in result["gaps"]))

    def test_matching_counts_do_not_replace_missing_identity(self):
        value = copy.deepcopy(self.ledger)
        value["tests"][0]["id"] = "src/test/java/p/OtherTest.java"
        self.assertTrue(validate(value, self.reference, Path("."))["invalid"])

    def test_report_output_must_match_executed_case_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "test.jar"
            artifact.write_bytes(b"candidate")
            candidate = {"identity": "p.ATest", "commit": "a" * 40,
                         "artifact": "test.jar", "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
            value = copy.deepcopy(self.ledger)
            item = value["tests"][0]
            item["candidate"] = candidate
            report = {"baseline": self.reference["baseline"], "candidate_identity": "p.ATest",
                      "candidate_commit": "a" * 40, "artifact_sha256": candidate["artifact_sha256"],
                      "source_sha256": item["sha256"], "passed_identities": [item["id"]],
                      "command": ["java", "Runner"], "expected_cases": 1,
                      "actual_executed_cases": 1, "failures": 0, "ignored": 0,
                      "process_exit_code": 0,
                      "output": "ACTUAL_TESTS=1\nFAILURES=0\nIGNORED=0\n"}
            path = root / "report.json"
            path.write_text(json.dumps(report))
            item["evidence"] = [{"kind": "java-test", "status": "passed", "report": "report.json",
                                 "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]
            valid = validate(value, self.reference, root, "a" * 40)
            self.assertEqual(valid["invalid"], [])
            self.assertFalse(any(item["id"] in gap and "unrun java-test" in gap for gap in valid["gaps"]))
            report["output"] = "ACTUAL_TESTS=1\nFAILURES=0\nIGNORED=1\n"
            path.write_text(json.dumps(report))
            item["evidence"][0]["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertTrue(validate(value, self.reference, root, "a" * 40)["invalid"])


if __name__ == "__main__":
    unittest.main()
