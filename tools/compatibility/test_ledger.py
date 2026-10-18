import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from collections import Counter
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
            "declarations": {"p.A|type": ("src/main/java/p/A.java", "public class p.A", None),
                             "p.A|run|()V": ("src/main/java/p/A.java", "public void run(); descriptor: ()V",
                                               ["ACC_PUBLIC"])},
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
                              **({"flags": flags} if flags is not None else {}),
                              "candidate": None, "evidence": []}
                             for key, (source, signature, flags) in self.reference["declarations"].items()],
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
                                            "target": "jvm", "report": "missing.json",
                                            "report_sha256": "0" * 64}]
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
                                              "target": "jvm",
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
        self.assertTrue(probe(jar, "named-module-consumer",
                              expected_provider_sha256="204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e")["passed"])

    @unittest.skipUnless(all(os.environ.get(name) for name in
                             ("DYN4K_BASELINE_SOURCE", "DYN4K_BASELINE_JAR", "DYN4K_BASELINE_SOURCES_JAR")),
                         "pinned baseline inputs not supplied")
    def test_pinned_reference_uses_plain_inventory_and_parses_declarations(self):
        expected = ledger.reference(
            Path(os.environ["DYN4K_BASELINE_SOURCE"]),
            Path(os.environ["DYN4K_BASELINE_JAR"]),
            Path(os.environ["DYN4K_BASELINE_SOURCES_JAR"]),
            Path("docs/verification/baseline-inventory.json"),
            Path("docs/verification/baseline-run.json"),
        )
        self.assertEqual(len(expected["production"]), 268)
        self.assertEqual(len(expected["tests"]), 199)
        self.assertEqual(len(expected["declarations"]), 3508)
        by_parameters = {}
        for identity, (_, _, flags) in expected["declarations"].items():
            owner_and_member, _, descriptor = identity.rpartition("|")
            if descriptor.startswith("("):
                parameters = descriptor.split(")", 1)[0] + ")"
                by_parameters.setdefault((owner_and_member, parameters), []).append(flags)
        collisions = [flags for flags in by_parameters.values() if len(flags) > 1]
        self.assertEqual(Counter(len(flags) for flags in collisions), {2: 64, 3: 20, 4: 4})
        self.assertEqual(sum(len(flags) - 1 for flags in collisions), 116)
        self.assertEqual(sum("ACC_BRIDGE" in flags for groups in by_parameters.values()
                             for flags in groups), 133)
        self.assertEqual(sum("ACC_BRIDGE" in flags for groups in by_parameters.values()
                             if len(groups) == 1 for flags in groups), 17)
        self.assertEqual(expected["declarations"]["org.dyn4j.AVLTree|org.dyn4j.AVLTree|()V"],
                         ("src/main/java/org/dyn4j/AVLTree.java",
                          "public org.dyn4j.AVLTree(); descriptor: ()V", ["ACC_PUBLIC"]))
        self.assertEqual(expected["declarations"]["org.dyn4j.Epsilon|compute|()D"],
                         ("src/main/java/org/dyn4j/Epsilon.java",
                          "public static double compute(); descriptor: ()D", ["ACC_PUBLIC"]))
        self.assertEqual(expected["declarations"]["org.dyn4j.collision.narrowphase.MinkowskiSum|getSupportPoint|(Lorg/dyn4j/geometry/Vector2;)Lorg/dyn4j/geometry/Vector2;"],
                         ("src/main/java/org/dyn4j/collision/narrowphase/MinkowskiSum.java",
                          "public final org.dyn4j.geometry.Vector2 getSupportPoint(org.dyn4j.geometry.Vector2); "
                          "descriptor: (Lorg/dyn4j/geometry/Vector2;)Lorg/dyn4j/geometry/Vector2;",
                          ["ACC_PUBLIC"]))
        bridge = "org.dyn4j.collision.broadphase.CollisionBodyAABBProducer|compute|(Ljava/lang/Object;)Lorg/dyn4j/geometry/AABB;"
        self.assertEqual(expected["declarations"][bridge],
                         ("src/main/java/org/dyn4j/collision/broadphase/CollisionBodyAABBProducer.java",
                          "public org.dyn4j.geometry.AABB compute(java.lang.Object); descriptor: "
                          "(Ljava/lang/Object;)Lorg/dyn4j/geometry/AABB;",
                          ["ACC_PUBLIC", "ACC_BRIDGE", "ACC_SYNTHETIC"]))
        typed = "org.dyn4j.collision.AxisAlignedBounds|copy|()Lorg/dyn4j/collision/AxisAlignedBounds;"
        copy_bridge = "org.dyn4j.collision.AxisAlignedBounds|copy|()Lorg/dyn4j/Copyable;"
        self.assertEqual(expected["declarations"][typed][2], ["ACC_PUBLIC"])
        self.assertEqual(expected["declarations"][copy_bridge][2],
                         ["ACC_PUBLIC", "ACC_BRIDGE", "ACC_SYNTHETIC"])
        candidate = json.loads(Path("tools/compatibility/declaration-ledger.json").read_text())
        pinned = copy.deepcopy(candidate)
        pinned.pop("candidate_source", None)
        pinned.pop("review_receipts", None)
        pinned["module"].pop("reason", None)
        pinned["module"]["candidate"] = None
        pinned["module"]["evidence"] = []
        for section in ("production", "tests", "declarations"):
            for item in pinned[section]:
                item.pop("disposition", None)
                item.pop("reason", None)
                item["candidate"] = None
                item["evidence"] = []
        recorded = ledger.generate(expected)
        self.assertEqual(pinned, recorded)
        self.assertEqual(validate(recorded, expected, Path.cwd())["invalid"], [])

        missing = copy.deepcopy(recorded)
        missing["declarations"].pop(0)
        self.assertIn("declarations: omitted org.dyn4j.AVLTree|type",
                      validate(missing, expected, Path.cwd())["invalid"])

        wrong_declaration = copy.deepcopy(recorded)
        wrong_declaration["declarations"][1]["signature"] = "public org.dyn4j.AVLTree(); descriptor: (I)V"
        self.assertIn("declarations: changed org.dyn4j.AVLTree|org.dyn4j.AVLTree|()V",
                      validate(wrong_declaration, expected, Path.cwd())["invalid"])

        wrong_source = copy.deepcopy(recorded)
        wrong_source["declarations"][1]["source_file"] = "src/main/java/org/dyn4j/BinarySearchTree.java"
        self.assertIn("declarations: changed org.dyn4j.AVLTree|org.dyn4j.AVLTree|()V",
                      validate(wrong_source, expected, Path.cwd())["invalid"])

        wrong_provenance = copy.deepcopy(recorded)
        wrong_provenance["production"][0]["sha256"] = "0" * 64
        self.assertTrue(any("changed source SHA-256" in error for error in
                            validate(wrong_provenance, expected, Path.cwd())["invalid"]))

        for identity in (typed, copy_bridge):
            with self.subTest(removed=identity):
                missing_method = copy.deepcopy(recorded)
                missing_method["declarations"] = [item for item in missing_method["declarations"]
                                                  if item["id"] != identity]
                self.assertIn(f"declarations: omitted {identity}",
                              validate(missing_method, expected, Path.cwd())["invalid"])

        wrong_return = copy.deepcopy(recorded)
        next(item for item in wrong_return["declarations"] if item["id"] == typed)["id"] = (
            "org.dyn4j.collision.AxisAlignedBounds|copy|()Ljava/lang/Object;")
        return_errors = validate(wrong_return, expected, Path.cwd())["invalid"]
        self.assertIn(f"declarations: omitted {typed}", return_errors)
        self.assertIn("declarations: unexpected org.dyn4j.collision.AxisAlignedBounds|copy|()Ljava/lang/Object;",
                      return_errors)

        wrong_bridge = copy.deepcopy(recorded)
        next(item for item in wrong_bridge["declarations"] if item["id"] == copy_bridge)["flags"] = ["ACC_PUBLIC"]
        self.assertIn(f"declarations: changed {copy_bridge}",
                      validate(wrong_bridge, expected, Path.cwd())["invalid"])

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
            forged = validate(value, self.reference, root, "a" * 40)
            self.assertTrue(forged["invalid"], forged)
            self.assertTrue(any(item["id"] in gap and "unrun common-portable" in gap for gap in forged["gaps"]))

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

    def test_executed_jvm_declaration_report_passes_and_stale_report_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "p" / "A.java"
            source.parent.mkdir()
            source.write_text("package p; public class A { public void run() {} }\n")
            classes = root / "classes"
            classes.mkdir()
            subprocess.run(["javac", "-d", str(classes), str(source)], check=True, capture_output=True)
            artifact = root / "candidate.jar"
            subprocess.run(["jar", "cf", str(artifact), "-C", str(classes), "."], check=True, capture_output=True)
            expected = copy.deepcopy(self.reference)
            expected["declarations"]["p.A|type"] = ("src/main/java/p/A.java", "public class p.A {", None)
            value = copy.deepcopy(self.ledger)
            item = value["declarations"][0]
            item["signature"] = "public class p.A {"
            candidate = {"identity": item["id"], "commit": "a" * 40,
                         "artifact": "candidate.jar", "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
            item["candidate"] = candidate
            observed = ledger.execution_probe.signature(item, artifact, ledger.oracle)
            self.assertEqual(observed["actual_executed_cases"], 1)
            self.assertIn("public class p.A", observed["raw_stdout"])
            report = {"schema_version": 2, "probe": "javap-signature-v1", "kind": "java-signature",
                      "target": "jvm", "baseline": expected["baseline"],
                      "candidate_identity": candidate["identity"], "candidate_commit": candidate["commit"],
                      "artifact_sha256": candidate["artifact_sha256"],
                      "source_sha256": expected["production"][item["source_file"]],
                      "passed_identities": [item["id"]], "execution": observed, **observed}
            path = root / "report.json"
            path.write_text(json.dumps(report))
            item["evidence"] = [{"kind": "java-signature", "target": "jvm", "status": "passed",
                                 "report": "report.json", "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]
            valid = validate(value, expected, root, "a" * 40)
            self.assertEqual(valid["invalid"], [], valid)
            self.assertFalse(any(item["id"] in gap and "unrun java-signature" in gap for gap in valid["gaps"]))
            for field, changed in (("output", observed["output"] + "FORGED GREEN\n"),
                                   ("command", ["java", "Runner"]),
                                   ("actual_executed_cases", 2), ("expected_cases", 2),
                                   ("expected_cases", True),
                                   ("execution", {**observed, "expected_cases": True}),
                                   ("failures", 1), ("ignored", 1),
                                   ("raw_stdout", "fabricated output")):
                with self.subTest(field=field):
                    stale_report = {**report, field: changed}
                    path.write_text(json.dumps(stale_report))
                    item["evidence"][0]["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                    stale = validate(value, expected, root, "a" * 40)
                    self.assertTrue(any("differs from executed probe" in error for error in stale["invalid"]), stale)
            report["source_sha256"] = sha("stale source")
            path.write_text(json.dumps(report))
            item["evidence"][0]["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            stale_source = validate(value, expected, root, "a" * 40)
            self.assertTrue(any("execution identity" in error for error in stale_source["invalid"]), stale_source)

    def test_executed_member_report_binds_artifact_and_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "p" / "A.java"
            source.parent.mkdir()
            source.write_text("package p; public class A { public void run() {} }\n")
            classes = root / "classes"
            classes.mkdir()
            subprocess.run(["javac", "-d", str(classes), str(source)], check=True, capture_output=True)
            artifact = root / "candidate.jar"
            subprocess.run(["jar", "cf", str(artifact), "-C", str(classes), "."], check=True, capture_output=True)
            expected = copy.deepcopy(self.reference)
            source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
            expected["production"]["src/main/java/p/A.java"] = source_sha
            value = copy.deepcopy(self.ledger)
            value["production"][0]["sha256"] = source_sha
            item = value["declarations"][1]
            candidate = {"identity": item["id"], "commit": "a" * 40,
                         "artifact": "candidate.jar", "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
            item["candidate"] = candidate
            observed = ledger.execution_probe.signature(item, artifact, ledger.oracle)
            self.assertEqual((observed["actual_executed_cases"], observed["failures"]), (1, 0))
            report = {"schema_version": 2, "probe": "javap-signature-v1", "kind": "java-signature",
                      "target": "jvm", "baseline": expected["baseline"],
                      "candidate_identity": candidate["identity"], "candidate_commit": candidate["commit"],
                      "artifact_sha256": candidate["artifact_sha256"], "source_sha256": source_sha,
                      "passed_identities": [item["id"]], "execution": observed, **observed}
            path = root / "report.json"
            path.write_text(json.dumps(report))
            item["evidence"] = [{"kind": "java-signature", "target": "jvm", "status": "passed",
                                 "report": "report.json", "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]
            self.assertEqual(validate(value, expected, root, "a" * 40)["invalid"], [])

            original = artifact.read_bytes()
            artifact.write_bytes(original + b"changed")
            self.assertTrue(any("candidate artifact is missing or changed" in error for error in
                                validate(value, expected, root, "a" * 40)["invalid"]))
            with self.assertRaisesRegex(ValueError, "candidate artifact"):
                ledger.execution_probe.signature(item, artifact, ledger.oracle)
            artifact.write_bytes(original)

            report["source_sha256"] = sha("wrong source")
            path.write_text(json.dumps(report))
            item["evidence"][0]["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertTrue(any("execution identity" in error for error in
                                validate(value, expected, root, "a" * 40)["invalid"]))

    def test_bridge_probe_requires_its_full_descriptor_and_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "p" / "A.java"
            source.parent.mkdir()
            source.write_text("package p; interface Copyable<T> { T copy(); } "
                              "public class A implements Copyable<A> { public A copy() { return this; } }\n")
            classes = root / "classes"
            classes.mkdir()
            subprocess.run(["javac", "-d", str(classes), str(source)], check=True, capture_output=True)
            artifact = root / "candidate.jar"
            subprocess.run(["jar", "cf", str(artifact), "-C", str(classes), "."], check=True, capture_output=True)
            item = {"id": "p.A|copy|()Ljava/lang/Object;",
                    "signature": "public java.lang.Object copy(); descriptor: ()Ljava/lang/Object;",
                    "flags": ["ACC_PUBLIC", "ACC_BRIDGE", "ACC_SYNTHETIC"],
                    "candidate": {"identity": "p.A|copy|()Ljava/lang/Object;",
                                  "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}}
            observed = ledger.execution_probe.signature(item, artifact, ledger.oracle)
            self.assertEqual((observed["actual_executed_cases"], observed["failures"]), (1, 0))
            item["id"] = item["candidate"]["identity"] = "p.A|copy|()Lp/A;"
            item["signature"] = "public p.A copy(); descriptor: ()Lp/A;"
            item["flags"] = ["ACC_PUBLIC"]
            self.assertEqual(ledger.execution_probe.signature(item, artifact, ledger.oracle)["failures"], 0)
            item["signature"] = "public java.lang.Object copy(); descriptor: ()Ljava/lang/Object;"
            self.assertEqual(ledger.execution_probe.signature(item, artifact, ledger.oracle)["failures"], 1)

    def test_covariant_method_and_bridge_are_separate_declarations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "p" / "A.java"
            source.parent.mkdir()
            source.write_text("package p; interface Copyable<T> { T copy(); } "
                              "public class A implements Copyable<A> { public A copy() { return this; } }\n")
            classes = root / "classes"
            classes.mkdir()
            subprocess.run(["javac", "-d", str(classes), str(source)], check=True, capture_output=True)
            artifact = root / "candidate.jar"
            subprocess.run(["jar", "cf", str(artifact), "-C", str(classes), "."], check=True, capture_output=True)
            plain = subprocess.run(["javap", "-classpath", str(artifact), "-protected", "-s", "p.A"],
                                   check=True, capture_output=True, text=True).stdout
            verbose = subprocess.run(["javap", "-classpath", str(artifact), "-protected", "-s", "-v", "p.A"],
                                     check=True, capture_output=True, text=True).stdout
            _, members = ledger.execution_probe.declarations(plain, verbose, ledger.oracle)
            self.assertEqual(members[("copy", "()Lp/A;")],
                             ("public p.A copy(); descriptor: ()Lp/A;", ["ACC_PUBLIC"]))
            self.assertEqual(members[("copy", "()Ljava/lang/Object;")],
                             ("public java.lang.Object copy(); descriptor: ()Ljava/lang/Object;",
                              ["ACC_PUBLIC", "ACC_BRIDGE", "ACC_SYNTHETIC"]))

    def test_ordinary_method_cannot_impersonate_bridge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "p" / "A.java"
            source.parent.mkdir()
            source.write_text("package p; public class A { public Object copy() { return this; } }\n")
            classes = root / "classes"
            classes.mkdir()
            subprocess.run(["javac", "-d", str(classes), str(source)], check=True, capture_output=True)
            artifact = root / "candidate.jar"
            subprocess.run(["jar", "cf", str(artifact), "-C", str(classes), "."], check=True, capture_output=True)
            item = {"id": "p.A|copy|()Ljava/lang/Object;", "signature":
                    "public java.lang.Object copy(); descriptor: ()Ljava/lang/Object;",
                    "flags": ["ACC_PUBLIC", "ACC_BRIDGE", "ACC_SYNTHETIC"],
                    "candidate": {"identity": "p.A|copy|()Ljava/lang/Object;",
                                  "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}}
            observed = ledger.execution_probe.signature(item, artifact, ledger.oracle)
            self.assertEqual((observed["actual_executed_cases"], observed["failures"]), (0, 1))

    @unittest.skipUnless(os.environ.get("DYN4K_BASELINE_JAR"), "pinned baseline JAR not supplied")
    def test_baseline_jar_cannot_be_candidate_or_direct_probe(self):
        baseline_jar = Path(os.environ["DYN4K_BASELINE_JAR"])
        self.assertEqual(hashlib.sha256(baseline_jar.read_bytes()).hexdigest(), ledger.oracle.BINARY_SHA256)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "candidate.jar"
            artifact.write_bytes(baseline_jar.read_bytes())
            for section in ("production", "tests", "declarations"):
                with self.subTest(section=section):
                    value = copy.deepcopy(self.ledger)
                    item = value[section][0]
                    item["candidate"] = {"identity": item["id"], "commit": "a" * 40,
                                         "artifact": "candidate.jar",
                                         "artifact_sha256": ledger.oracle.BINARY_SHA256}
                    result = validate(value, self.reference, root, "a" * 40)
                    self.assertTrue(any("baseline JAR" in error for error in result["invalid"]), result)
            item = {"id": "org.dyn4j.AVLTree|type", "signature": "public class org.dyn4j.AVLTree<E> {",
                    "candidate": {"identity": "org.dyn4j.AVLTree|type",
                                  "artifact_sha256": ledger.oracle.BINARY_SHA256}}
            with self.assertRaisesRegex(ValueError, "baseline JAR"):
                ledger.execution_probe.signature(item, artifact, ledger.oracle)

    def test_fabricated_generic_green_reports_have_no_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "candidate.jar"
            artifact.write_bytes(b"candidate")
            for section, kind, target in (("declarations", "java-signature", "jvm"),
                                          ("declarations", "common-portable", "linuxX64"),
                                          ("tests", "java-test", "jvm")):
                with self.subTest(kind=kind):
                    value = copy.deepcopy(self.ledger)
                    item = value[section][0]
                    item["candidate"] = {"identity": item["id"], "commit": "a" * 40,
                                         "artifact": "candidate.jar",
                                         "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
                    source = item["source_file"] if section == "declarations" else item["id"]
                    source_hash = self.reference["production" if section == "declarations" else "tests"][source]
                    report = {"kind": kind, "target": target, "baseline": self.reference["baseline"],
                              "candidate_identity": item["id"], "candidate_commit": "a" * 40,
                              "artifact_sha256": item["candidate"]["artifact_sha256"],
                              "source_sha256": source_hash, "passed_identities": [item["id"]],
                              "command": ["java", "Runner"], "expected_cases": 1,
                              "actual_executed_cases": 1, "failures": 0, "ignored": 0,
                              "process_exit_code": 0,
                              "output": "ACTUAL_TESTS=1\nFAILURES=0\nIGNORED=0\n"}
                    path = root / "report.json"
                    path.write_text(json.dumps(report))
                    item["evidence"] = [{"kind": kind, "target": target, "status": "passed",
                                         "report": "report.json", "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]
                    result = validate(value, self.reference, root, "a" * 40)
                    self.assertTrue(result["invalid"], result)
                    self.assertTrue(any(item["id"] in gap and f"unrun {kind}" in gap for gap in result["gaps"]))
                    if kind != "java-signature":
                        report.update(schema_version=2, probe="javap-signature-v1", execution={})
                        path.write_text(json.dumps(report))
                        item["evidence"][0]["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                        unsupported = validate(value, self.reference, root, "a" * 40)
                        self.assertTrue(any("no allowlisted executable probe" in error
                                            for error in unsupported["invalid"]), unsupported)

    def test_ignored_and_unapproved_exception_remain_unpassed(self):
        for status in ("missing", "ignored", "unapproved_exception", "unrun"):
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
            self.assertTrue(valid["invalid"], valid)
            self.assertTrue(any(item["id"] in gap and "unrun java-test" in gap for gap in valid["gaps"]))
            report["output"] = "ACTUAL_TESTS=1\nFAILURES=0\nIGNORED=1\n"
            path.write_text(json.dumps(report))
            item["evidence"][0]["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertTrue(validate(value, self.reference, root, "a" * 40)["invalid"])


if __name__ == "__main__":
    unittest.main()
