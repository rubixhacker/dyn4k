import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import ledger
from ledger import validate
from module_probe import EXPORTS, descriptor, probe


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
            "module": {"id": "module-info.java", "source_file": "src/main/java/module-info.java",
                       "sha256": sha("module org.dyn4j { exports p; }"), "name": "org.dyn4j",
                       "exports": ["p"], "fixture_sha256": {"module-info.java": sha("requires org.dyn4j"),
                                                           "example/Main.java": sha("consumer")}},
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
            "module": {**self.reference["module"], "candidate": None, "evidence": []},
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
        self.assertEqual(result["missing_counterparts"], 5)
        for kind in ("module-descriptor", "named-module-consumer", "java8-classpath"):
            self.assertTrue(any(f"unrun {kind}" in gap for gap in result["gaps"]))

    def test_omitted_module_obligation_fails(self):
        self.check_invalid(lambda value: value.pop("module"))

    def test_fabricated_module_pass_fails(self):
        def forge(value):
            value["module"]["evidence"] = [{"kind": "named-module-consumer", "status": "passed",
                                                "report": "missing.json", "report_sha256": "0" * 64}]
        self.check_invalid(forge)

    def test_module_descriptor_and_fixture_identity_cannot_change(self):
        self.check_invalid(lambda value: value["module"].update(name="dyn4k.core.jvm"))
        self.check_invalid(lambda value: value["module"].update(exports=[]))
        self.check_invalid(lambda value: value["module"]["fixture_sha256"].update({"module-info.java": "stale"}))

    def test_forged_modular_consumer_report_cannot_replace_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jar = root / "candidate.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
            value = copy.deepcopy(self.ledger)
            candidate = {"identity": "org.dyn4j", "commit": "a" * 40,
                         "artifact": "candidate.jar", "artifact_sha256": hashlib.sha256(jar.read_bytes()).hexdigest()}
            value["module"]["candidate"] = candidate
            report = {"schema_version": 1, "kind": "named-module-consumer",
                      "baseline": self.reference["baseline"], "candidate_identity": "org.dyn4j",
                      "candidate_commit": candidate["commit"], "artifact_sha256": candidate["artifact_sha256"],
                      "source_sha256": self.reference["module"]["sha256"],
                      "fixture_sha256": self.reference["module"]["fixture_sha256"],
                      "dependencies": [],
                      "observed": {"passed": True, "compile_release": 9, "compile_exit_code": 0,
                                   "run_exit_code": 0, "output": "Named module consumer passed\n",
                                   "java_version": "openjdk version \"21\""}}
            path = root / "report.json"
            path.write_text(json.dumps(report))
            value["module"]["evidence"] = [{"kind": "named-module-consumer", "status": "passed",
                                              "report": "report.json",
                                              "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]
            result = validate(value, self.reference, root, "a" * 40)
            self.assertTrue(any("recorded pass differs from executed probe" in error
                                for error in result["invalid"]), result)

    def test_modern_runtime_cannot_satisfy_java8_classpath_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "not Java 8"):
                probe(Path(directory) / "candidate.jar", "java8-classpath", java8_java=Path(sys.executable))

    @unittest.skipUnless(os.environ.get("DYN4K_BASELINE_JAR"), "pinned baseline JAR not supplied")
    def test_pinned_baseline_named_module_fixture(self):
        jar = Path(os.environ["DYN4K_BASELINE_JAR"])
        self.assertEqual(hashlib.sha256(jar.read_bytes()).hexdigest(),
                         "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e")
        observed = descriptor(jar)
        self.assertEqual(observed["name"], "org.dyn4j")
        self.assertEqual(set(observed["exports"]), EXPORTS)
        self.assertTrue(observed["passed"])
        self.assertTrue(probe(jar, "named-module-consumer")["passed"])

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

    def test_baseline_run_hashes_require_exact_test_and_resource_inputs(self):
        tests = {"src/test/java/p/ATest.java": sha("test")}
        resources = {"src/test/resources/p/data.dat": sha("data")}
        expected = tests | resources
        ledger.require_baseline_test_inputs(expected, tests, resources)
        near_misses = [
            expected | {"src/test/java/p/ATest.java": sha("changed")},
            {"src/test/java/p/OtherTest.java": sha("test"), **resources},
            {**tests, "src/test/resources/p/other.dat": sha("data")},
            expected | {"src/test/resources/p/extra.dat": sha("extra")},
        ]
        for observed in near_misses:
            with self.subTest(observed=observed):
                with self.assertRaisesRegex(ValueError, "test input hashes"):
                    ledger.require_baseline_test_inputs(observed, tests, resources)

    def test_signature_report_cannot_claim_portable_kind_or_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "candidate.jar"
            artifact.write_bytes(b"candidate")
            value = copy.deepcopy(self.ledger)
            item = value["declarations"][0]
            candidate = {"identity": "p.A", "commit": "a" * 40,
                         "artifact": "candidate.jar", "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
            item["candidate"] = candidate
            report = {"kind": "java-signature", "target": "linuxX64", "baseline": self.reference["baseline"],
                      "candidate_identity": candidate["identity"], "candidate_commit": candidate["commit"],
                      "artifact_sha256": candidate["artifact_sha256"],
                      "source_sha256": self.reference["production"][item["source_file"]],
                      "passed_identities": [item["id"]], "command": ["java", "Runner"],
                      "expected_cases": 1, "actual_executed_cases": 1, "failures": 0, "ignored": 0,
                      "process_exit_code": 0, "output": "ACTUAL_TESTS=1\nFAILURES=0\nIGNORED=0\n"}
            path = root / "report.json"
            path.write_text(json.dumps(report))
            record = {"kind": "common-portable", "target": "linuxX64", "status": "passed",
                      "report": "report.json", "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            item["evidence"] = [record]
            self.assertTrue(validate(value, self.reference, root, "a" * 40)["invalid"])
            report["kind"] = "common-portable"
            report["target"] = "jvm"
            path.write_text(json.dumps(report))
            record["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertTrue(validate(value, self.reference, root, "a" * 40)["invalid"])
            report["target"] = "linuxX64"
            path.write_text(json.dumps(report))
            record["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            valid = validate(value, self.reference, root, "a" * 40)
            self.assertEqual(valid["invalid"], [])
            self.assertFalse(any(item["id"] in gap and "unrun common-portable" in gap for gap in valid["gaps"]))

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
            report = {"kind": "java-test", "target": "jvm", "baseline": self.reference["baseline"],
                      "candidate_identity": "p.ATest",
                      "candidate_commit": "a" * 40, "artifact_sha256": candidate["artifact_sha256"],
                      "source_sha256": item["sha256"], "passed_identities": [item["id"]],
                      "command": ["java", "Runner"], "expected_cases": 1,
                      "actual_executed_cases": 1, "failures": 0, "ignored": 0,
                      "process_exit_code": 0,
                      "output": "ACTUAL_TESTS=1\nFAILURES=0\nIGNORED=0\n"}
            path = root / "report.json"
            path.write_text(json.dumps(report))
            item["evidence"] = [{"kind": "java-test", "target": "jvm", "status": "passed", "report": "report.json",
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
