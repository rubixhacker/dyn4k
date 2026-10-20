from __future__ import annotations

import json
import gzip
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import candidate_coverage
import build_provenance
import ledger
import signature_index
import java_corpus


ROOT = Path(__file__).resolve().parents[2]
JAR = ROOT / "dyn4k-core/build/libs/dyn4k-core-jvm-0.1.0-alpha.1.jar"
ANDROID_ORIGIN = ROOT
ANDROID_JAR = ANDROID_ORIGIN / "dyn4k-core/build/intermediates/aar_main_jar/androidMain/syncAndroidMainLibJars/classes.jar"
sys.path.insert(0, str(ROOT / "tools/qualification"))
import qualify


class JavaCorpusTemporaryDirectoryTests(unittest.TestCase):
    def java_temp_directory(self, output):
        return java_corpus.java_temp_directory(output)

    def parameter_case_inventory(self):
        identities = []
        for owner, method_count in java_corpus.PARAMETER_CLASSES.items():
            for parameter_index in range(5):
                for method_index in range(method_count):
                    name = (f"method{method_index:02d}[Type{parameter_index}@"
                            f"{parameter_index + 1:08x}]")
                    identities.append((owner, name))
        rows = "".join(f'<testcase classname="{owner}" name="{name}"/>'
                       for owner, name in identities)
        xml_body = (f'<testsuite tests="{len(identities)}" failures="0" errors="0" skipped="0">'
                    + rows + "</testsuite>")
        normalized = sorted([list(item) for item in java_corpus.normalized_cases(identities)])
        return identities, xml_body, normalized

    def clean_repository(self, parent):
        repository = Path(parent) / "repository"
        repository.mkdir()
        shutil.copy2(ROOT / ".gitignore", repository / ".gitignore")
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        subprocess.run(["git", "-C", str(repository), "add", ".gitignore"], check=True)
        subprocess.run(["git", "-C", str(repository), "-c", "user.name=Corpus Test",
                        "-c", "user.email=corpus-test@example.invalid", "commit", "-qm",
                        "clean checkout fixture"], check=True)
        candidate_sha = subprocess.check_output(
            ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
        return repository, candidate_sha

    def test_runtime_command_uses_created_output_owned_temp_directory(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR", str(Path.home()))) as parent:
            output = Path(parent) / "capture"
            output.mkdir()
            java_tmp = self.java_temp_directory(output)
            command = java_corpus.runtime_command("/pinned/jdk/bin/java", "pinned-classpath",
                                                  java_tmp, output / "lane.xml", ["p.Test"])

            self.assertTrue(java_tmp.is_dir())
            self.assertEqual(java_tmp.parent, output.resolve())
            self.assertEqual(command[:2], ["/pinned/jdk/bin/java",
                                           f"-Djava.io.tmpdir={java_tmp}"])
            self.assertEqual(command[2:], ["-cp", "pinned-classpath", "LedgerCorpusReport",
                                           str(output / "lane.xml"), "p.Test"])

    def test_java_temp_directory_rejects_missing_output_and_symlink_escape(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR", str(Path.home()))) as parent:
            parent = Path(parent)
            with self.assertRaises(ValueError):
                self.java_temp_directory(parent / "missing")

            output = parent / "capture"
            output.mkdir()
            outside = parent / "outside"
            outside.mkdir()
            (output / "java-tmp").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                self.java_temp_directory(output)

    def test_capture_subprocesses_use_output_owned_tmpdir_for_jdk8_and_21(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR", str(Path.home()))) as parent:
            root = Path(parent)
            source = root / "upstream"
            test_root = source / "src/test/java/p"
            test_root.mkdir(parents=True)
            tests = []
            for index in range(199):
                path = test_root / f"Case{index:03d}.java"
                path.write_text("@Test" if index < 190 else "class Helper {}")
                tests.append({"id": path.relative_to(source).as_posix(), "sha256": "0" * 64})

            deps = {}
            for key in ("baseline", "stdlib", "annotations", "junit", "hamcrest"):
                path = root / f"{key}.jar"
                path.write_bytes(key.encode())
                deps[key] = path
            candidate = root / "candidate.jar"
            candidate.write_bytes(b"candidate")
            case_identities, xml_body, _normalized = self.parameter_case_inventory()
            ledger = {
                "baseline": {"binary_sha256": java_corpus.digest(deps["baseline"])},
                "baseline_test_counts": {"actual_executed_cases": len(case_identities)},
                "tests": tests,
                "candidate_source": {"artifact": "candidate.jar",
                                     "artifact_sha256": java_corpus.digest(candidate),
                                     "revision": "1" * 40, "tree": "2" * 40},
            }
            jdks = {major: root / f"jdk{major}" for major in (8, 21)}
            input_hashes = {"src/test/java/p/Case000.java": "a" * 64}
            runtime_commands = []

            def fake_tool(jdk, name, major):
                return {"path": str(jdk / "bin" / name), "sha256": "b" * 64,
                        "version": f"JDK {major} {name}"}

            def fake_run(command, **_kwargs):
                if "LedgerCorpusReport" in command:
                    runtime_commands.append(command)
                    xml = Path(command[command.index("LedgerCorpusReport") + 1])
                    xml.write_text(xml_body)
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            with patch.object(java_corpus, "checked_inputs", return_value=input_hashes), \
                    patch.object(java_corpus, "tool", side_effect=fake_tool), \
                    patch.object(java_corpus.subprocess, "run", side_effect=fake_run):
                report = java_corpus.capture(ledger, root, source, candidate, deps, jdks,
                                             root / "capture")

            expected_tmp = f"-Djava.io.tmpdir={(root / 'capture/java-tmp').resolve()}"
            self.assertTrue(report["passed"])
            self.assertEqual(len(runtime_commands), 8)
            self.assertTrue(all(command[1] == expected_tmp for command in runtime_commands))
            for major in (8, 21):
                java_path = str(jdks[major] / "bin" / "java")
                self.assertEqual(sum(command[0] == java_path for command in runtime_commands), 4)
            self.assertTrue((root / "capture/java-tmp").is_dir())

    def test_validate_report_replay_stays_ignored_during_clean_checkout_gate(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR", str(Path.home()))) as parent:
            repository, candidate_sha = self.clean_repository(parent)
            build = repository / "build"
            fixture = build / "java-corpus-fixture"
            fixture.mkdir(parents=True)
            source = fixture / "upstream"
            source.mkdir()
            candidate = fixture / "candidate.jar"
            candidate.write_bytes(b"candidate")
            dep_paths = {}
            dependencies = {}
            for key in ("baseline", "stdlib", "annotations", "junit", "hamcrest"):
                path = fixture / f"{key}.jar"
                path.write_bytes(key.encode())
                dep_paths[key] = path
                dependencies[key] = {"path": str(path), "sha256": java_corpus.digest(path)}
            baseline_sha = dependencies["baseline"]["sha256"]
            binding = {"revision": "3" * 40, "tree": "4" * 40,
                       "artifact": "build/java-corpus-fixture/candidate.jar",
                       "artifact_sha256": java_corpus.digest(candidate)}
            normalized_case_ids = [["p.ATest", "runs"]]
            ledger = {"baseline": {"binary_sha256": baseline_sha},
                      "baseline_test_counts": {"actual_executed_cases": 1},
                      "tests": [{"id": "src/test/java/p/ATest.java", "sha256": "5" * 64}],
                      "candidate_source": binding}
            input_hashes = {"src/test/java/p/ATest.java": "5" * 64}
            receipt = build / "java-corpus-receipt.json"
            receipt.write_text("{}\n")
            report_xml_root = build / "java-corpus-xml"
            report_xml_root.mkdir()
            lane_records = {}
            xml_body = ('<testsuite tests="1" failures="0" errors="0" skipped="0">'
                        '<testcase classname="p.ATest" name="runs"/></testsuite>')
            for provider in ("baseline", "candidate"):
                for compiler in (8, 21):
                    for runtime in (8, 21):
                        lane = f"{provider}-javac{compiler}-java{runtime}"
                        xml = report_xml_root / f"{lane}.xml"
                        xml.write_text(xml_body)
                        lane_records[lane] = {"status": "passed",
                                              "xml_sha256": java_corpus.digest(xml)}

            tool_records = {}
            jdks = {}
            for major in (8, 21):
                jdk = build / f"jdk{major}"
                (jdk / "bin").mkdir(parents=True)
                entries = {}
                for name in ("javac", "java"):
                    path = jdk / "bin" / name
                    path.write_text("fixture tool")
                    entries[name] = {"path": str(path), "sha256": "6" * 64,
                                     "version": f"JDK {major} {name}"}
                tool_records[str(major)] = entries
                jdks[major] = jdk
            report = {
                "schema_version": 3, "kind": "java-test", "target": "jvm",
                "probe": "unchanged-junit-xml-v1", "baseline": ledger["baseline"],
                "candidate_commit": binding["revision"], "source_tree": binding["tree"],
                "artifact_sha256": binding["artifact_sha256"],
                "harness_sha256": java_corpus.digest(java_corpus.HARNESS),
                "passed": True, "input_sha256": input_hashes,
                "build_receipt": "build/java-corpus-receipt.json",
                "build_receipt_sha256": java_corpus.digest(receipt),
                "dependencies": dependencies, "tools": tool_records,
                "xml_root": "build/java-corpus-xml",
                "normalized_case_ids": normalized_case_ids,
                "actual_executed_cases_per_lane": 1, "lanes": lane_records,
            }
            replay_outputs = []
            receipt_before = receipt.read_bytes()

            def replay_capture(_ledger, root, _source, _jar, _deps, _jdks, output):
                output = Path(output)
                replay_dir = output.parent
                replay_outputs.append(output)
                output.mkdir(parents=True)
                (output / "sources.args").write_text("representative replay input\n")
                (output / "java-tmp").mkdir()
                qualify.require_clean_checkout(root, candidate_sha)
                self.assertEqual(replay_dir.parent, root / "build")
                return {"passed": True, "input_sha256": input_hashes,
                        "normalized_case_ids": report["normalized_case_ids"],
                        "actual_executed_cases_per_lane": 1}

            qualify.require_clean_checkout(repository, candidate_sha)
            with patch.object(java_corpus, "checked_inputs", return_value=input_hashes), \
                    patch.object(java_corpus, "tool",
                                 side_effect=lambda jdk, name, major: tool_records[str(major)][name]), \
                    patch.object(java_corpus, "normalized_cases",
                                 side_effect=lambda identities: Counter(identities)), \
                    patch.object(java_corpus.build_provenance, "verify", return_value=None), \
                    patch.object(java_corpus, "capture", side_effect=replay_capture):
                error = java_corpus.validate_report(report, ledger, repository, source, candidate)

            self.assertIsNone(error)
            self.assertEqual(len(replay_outputs), 1)
            self.assertFalse(replay_outputs[0].exists())
            self.assertEqual(receipt.read_bytes(), receipt_before)
            qualify.require_clean_checkout(repository, candidate_sha)

    def test_replay_temp_directory_rejects_symlinked_build_parent(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR", str(Path.home()))) as parent:
            root = Path(parent) / "repository"
            root.mkdir()
            with self.assertRaises(ValueError):
                java_corpus.replay_temp_directory(root / "missing")

            outside = Path(parent) / "outside"
            outside.mkdir()
            (root / "build").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                java_corpus.replay_temp_directory(root)


class BuildProvenanceArchiveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR", str(Path.home())))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".gitattributes").write_text("* text=auto\ngradlew -text\n")
        (self.root / ".gitignore").write_text("dyn4k-core/build/\n")
        self.source = b"first line\nsecond line\n"
        (self.root / "README.md").write_bytes(self.source)
        wrapper = self.root / "gradlew"
        wrapper.write_text("#!/bin/sh\nmkdir -p dyn4k-core/build/libs\n"
                           "sha256sum README.md\n"
                           "cp README.md dyn4k-core/build/libs/dyn4k-core-jvm-0.1.0-alpha.1.jar\n")
        wrapper.chmod(0o755)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        self.commit()
        self.historical = candidate_coverage.git(self.root, "rev-parse", "HEAD")
        (self.root / "HISTORY.md").write_bytes(b"later commit\n")
        subprocess.run(["git", "-C", str(self.root), "add", "HISTORY.md"], check=True)
        self.commit()
        self.current = candidate_coverage.git(self.root, "rev-parse", "HEAD")
        self.artifact = self.root / build_provenance.ARTIFACT
        self.artifact.parent.mkdir(parents=True)
        self.artifact.write_bytes(self.source)
        subprocess.run(["git", "-C", str(self.root), "config", "core.autocrlf", "true"], check=True)

    def commit(self):
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Build Test",
                        "-c", "user.email=build-test@example.invalid", "commit", "-qm",
                        "source fixture"], check=True)

    def test_probe_exports_canonical_bytes_for_current_and_historical_source(self):
        expected = hashlib.sha256(self.source).hexdigest()
        for revision in (self.historical, self.current):
            with self.subTest(revision=revision), \
                    patch.dict(os.environ, {"DYN4K_LEDGER_JAVA_HOME": "/tmp/dyn4k-tools/jdk21"}):
                proof = build_provenance.probe(self.root, revision, self.artifact)
                self.assertTrue(proof["passed"], proof.get("reason"))
                self.assertEqual(proof["revision"], revision)
                self.assertEqual(proof["rebuilt_sha256"], expected)
                self.assertIn(expected + "  README.md", proof["build_stdout"])

    def test_replayed_build_rejects_changed_source_pin_and_artifact(self):
        with patch.dict(os.environ, {"DYN4K_LEDGER_JAVA_HOME": "/tmp/dyn4k-tools/jdk21"}):
            proof = build_provenance.probe(self.root, self.current, self.artifact)
            self.assertTrue(proof["passed"])
            source = {"revision": self.current, "tree": proof["source_tree"],
                      "artifact": build_provenance.ARTIFACT,
                      "artifact_sha256": proof["artifact_sha256"]}
            self.assertIsNone(build_provenance.verify(proof, self.root, self.artifact, source))
            for changed in ({**source, "revision": self.historical},
                            {**source, "tree": "0" * 40},
                            {**source, "artifact_sha256": "0" * 64}):
                with self.subTest(changed=changed):
                    self.assertIsNotNone(build_provenance.verify(
                        proof, self.root, self.artifact, changed))
            self.artifact.write_bytes(b"altered candidate artifact\n")
            changed_artifact = build_provenance.probe(self.root, self.current, self.artifact)
            self.assertFalse(changed_artifact["passed"])
            self.assertNotEqual(changed_artifact["rebuilt_sha256"],
                                changed_artifact["artifact_sha256"])

    def test_rebuild_uses_exact_commit_even_with_git_replace_object(self):
        (self.root / "README.md").write_bytes(b"replacement source\n")
        subprocess.run(["git", "-C", str(self.root), "add", "README.md"], check=True)
        self.commit()
        replacement = candidate_coverage.git(self.root, "rev-parse", "HEAD")
        subprocess.run(["git", "-C", str(self.root), "replace", self.current, replacement],
                       check=True)
        expected_tree = candidate_coverage.git(
            self.root, "--no-replace-objects", "rev-parse", f"{self.current}^{{tree}}")
        with patch.dict(os.environ, {"DYN4K_LEDGER_JAVA_HOME": "/tmp/dyn4k-tools/jdk21"}):
            proof = build_provenance.probe(self.root, self.current, self.artifact)
        self.assertTrue(proof["passed"], proof.get("reason"))
        self.assertEqual(proof["source_tree"], expected_tree)
        self.assertEqual(proof["rebuilt_sha256"], hashlib.sha256(self.source).hexdigest())


@unittest.skipUnless(JAR.is_file(), "candidate JVM JAR not built")
class CandidateCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = json.loads((ROOT / "tools/compatibility/declaration-ledger.json").read_text())
        cls.revision = "0681a8cd2e3f12327296a58da68bc8338224ea73"
        cls.materialized = candidate_coverage.materialize(cls.original, ROOT, cls.revision, JAR)
        cls.expected = {
            "baseline": cls.original["baseline"],
            "baseline_test_counts": cls.original["baseline_test_counts"],
            "production": {row["id"]: row["sha256"] for row in cls.original["production"]},
            "tests": {row["id"]: row["sha256"] for row in cls.original["tests"]},
            "declarations": {row["id"]: (row["source_file"], row["signature"], row.get("flags"))
                             for row in cls.original["declarations"]},
            "module": {key: value for key, value in cls.original["module"].items()
                       if key not in {"candidate", "evidence"}},
        }

    def test_source_derived_counterparts_cover_world_joint_and_detection(self):
        result = self.materialized
        self.assertNotIn("review_receipts", result)
        by_id = {item["id"]: item for item in result["declarations"]}
        for prefix in ("org.dyn4j.world.World|type",
                       "org.dyn4j.dynamics.joint.DistanceJoint|type",
                       "org.dyn4j.collision.narrowphase.Gjk|type"):
            counterpart = by_id[prefix]["candidate"]
            self.assertIsNotNone(counterpart, prefix)
            self.assertTrue(counterpart["sources"], prefix)
        self.assertIsNotNone(by_id["org.dyn4j.geometry.package-info|type"]["candidate"])
        self.assertEqual(result["module"]["candidate"]["identity"], "org.dyn4j")

    def test_package_documents_and_anonymous_behavior_have_real_source_counterparts(self):
        result = self.materialized
        production = {row["id"]: row for row in result["production"]}
        declarations = {row["id"]: row for row in result["declarations"]}
        packages = [row for row in result["production"]
                    if row["id"].endswith("/package-info.java")]
        self.assertEqual(len(packages), 16)
        for row in packages:
            self.assertEqual(row["disposition"], "package-documentation-only")
            self.assertIsNotNone(row["candidate"])
            self.assertTrue(row["candidate"]["sources"])
            self.assertEqual(declarations[row["owner_type"] + "|type"]["disposition"],
                             "package-documentation-only")
        anonymous = {
            "org.dyn4j.collision.Filter$1|type": "collision/FiltersAndFixture.kt",
            "org.dyn4j.collision.manifold.ManifoldPointId$1|type": "collision/manifold/ManifoldModels.kt",
            "org.dyn4j.world.ValueMixer$1|type": "world/ValueMixer.kt",
            "org.dyn4j.collision.broadphase.DynamicAABBTree$1|type":
                "collision/broadphase/DynamicAABBTree.kt",
        }
        for identity, suffix in anonymous.items():
            row = declarations[identity]
            self.assertEqual(row["disposition"], "anonymous-behavior-mapped")
            self.assertTrue(any(source["path"].endswith(suffix)
                                for source in row["candidate"]["sources"]))
            self.assertIsNotNone(production[row["source_file"]]["candidate"])
        self.assertEqual(sum(row["candidate"] is not None for row in result["production"]), 268)
        self.assertEqual(sum(row["candidate"] is not None for row in result["declarations"]), 3508)
        copy_exception = declarations["org.dyn4j.exception.CopyException|type"]["candidate"]
        self.assertTrue(any(source["path"].endswith("commonMain/kotlin/org/dyn4j/exception/CollisionExceptions.kt")
                            for source in copy_exception["sources"]))

    def test_materialized_rows_reject_changed_source_and_forged_revision(self):
        result = json.loads(json.dumps(self.materialized))
        item = next(row for row in result["declarations"] if row["id"] == "org.dyn4j.world.World|type")
        self.assertIsNone(candidate_coverage.check_source_candidate(item["candidate"], ROOT))
        item["candidate"]["sources"][0]["sha256"] = "0" * 64
        self.assertIn("source hash", candidate_coverage.check_source_candidate(item["candidate"], ROOT))
        item["candidate"]["sources"][0]["sha256"] = candidate_coverage.digest(
            ROOT / item["candidate"]["sources"][0]["path"])
        original_path = item["candidate"]["sources"][0]["path"]
        item["candidate"]["sources"][0]["path"] = (
            "dyn4k-core/src/commonMain/kotlin/org/dyn4j/world/Removed.kt")
        self.assertIn("source hash", candidate_coverage.check_source_candidate(item["candidate"], ROOT))
        item["candidate"]["sources"][0]["path"] = original_path
        item["candidate"]["commit"] = "0" * 40
        self.assertIn("revision", candidate_coverage.check_source_candidate(item["candidate"], ROOT))

    def test_validator_rejects_changed_source_mapping_and_review_disposition(self):
        for change in ("source", "disposition", "revision"):
            result = json.loads(json.dumps(self.materialized))
            item = next(row for row in result["declarations"]
                        if row["id"] == "org.dyn4j.world.World|type")
            if change == "source":
                item["candidate"]["sources"][0]["sha256"] = "0" * 64
            elif change == "disposition":
                item["disposition"] = "reviewed-exception"
            else:
                result["candidate_source"]["revision"] = "0" * 40
            report = ledger.validate(result, self.expected, ROOT, self.revision)
            self.assertTrue(any(change in message for message in report["invalid"]), change)

    def test_many_to_one_requires_complete_original_id_group(self):
        result = json.loads(json.dumps(self.materialized))
        rows = [row for row in result["production"] if row["candidate"] and
                len(row["candidate"]["mapped_baseline_ids"]) > 1]
        self.assertTrue(rows)
        rows[0]["candidate"]["mapped_baseline_ids"] = [rows[0]["id"]]
        report = ledger.validate(result, self.expected, ROOT, self.revision)
        self.assertTrue(any("mapping group" in message for message in report["invalid"]))

    def test_validator_reports_every_obligation_without_promoting_source_mapping(self):
        report = ledger.validate(self.materialized, self.expected, ROOT, self.revision)
        self.assertEqual(report["invalid"], [])
        self.assertEqual(report["obligation_counts"]["total"], 7486)
        self.assertEqual(report["obligation_counts"]["passed"], 0)
        self.assertEqual(len(report["unpassed_obligations"]), 7486)

    def test_validator_rejects_changed_common_and_raw_review_receipts(self):
        for kind in ("common_corpus", "raw_signature", "portable_links", "android_host"):
            result = json.loads(json.dumps(self.materialized))
            result["review_receipts"] = {kind: {"path": "tools/compatibility/receipts/invalid.json",
                                                 "sha256": "0" * 64}}
            report = ledger.validate(result, self.expected, ROOT, self.revision)
            self.assertTrue(any(kind in message for message in report["invalid"]), report["invalid"])

    def test_candidate_artifact_rebuilds_from_declared_source_revision(self):
        proof = build_provenance.probe(ROOT, self.revision, JAR)
        self.assertTrue(proof["passed"], proof.get("reason"))
        self.assertEqual(proof["artifact_sha256"], candidate_coverage.digest(JAR))
        forged = dict(proof)
        forged["revision"] = self.original["baseline"]["commit"]
        self.assertIsNotNone(build_provenance.check_identity(forged, ROOT, JAR))

    @unittest.skipUnless(ANDROID_JAR.is_file(), "candidate Android host classes JAR unavailable")
    def test_android_classes_rebuild_from_the_same_pinned_source_revision(self):
        proof = build_provenance.probe_variant(ANDROID_ORIGIN, self.revision,
                                               ANDROID_JAR, "android")
        self.assertTrue(proof["passed"], proof.get("reason"))
        self.assertEqual(proof["artifact_sha256"],
                         "2e933e866cad8be8ee889fb4302381e2dd0517d73b3d80d7ed17d016b55ddf13")
        source = {"revision": self.revision, "tree": self.original["candidate_source"]["tree"],
                  "artifact": build_provenance.ANDROID_ARTIFACT,
                  "artifact_sha256": proof["artifact_sha256"]}
        self.assertIsNone(build_provenance.verify_variant(
            proof, ANDROID_ORIGIN, ANDROID_JAR, source, "android"))
        for field, value in (("revision", "0" * 40), ("tree", "0" * 40),
                             ("artifact_sha256", "0" * 64)):
            with self.subTest(field=field):
                changed = {**source, field: value}
                self.assertIsNotNone(build_provenance.verify_variant(
                    proof, ANDROID_ORIGIN, ANDROID_JAR, changed, "android"))
        changed_proof = {**proof, "passed": False}
        self.assertIsNotNone(build_provenance.verify_variant(
            changed_proof, ANDROID_ORIGIN, ANDROID_JAR, source, "android"))

    def test_module_report_uses_pinned_source_revision_after_ledger_only_commit(self):
        materialized = json.loads(json.dumps(self.materialized))
        source = materialized["candidate_source"]
        source["build_receipt"] = "tools/compatibility/receipts/candidate-build-0681a8cd.json"
        source["build_receipt_sha256"] = candidate_coverage.digest(ROOT / source["build_receipt"])
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            ledger_path = Path(directory) / "ledger.json"
            report_path = Path(directory) / "module.json"
            ledger_path.write_text(json.dumps(materialized))
            result = subprocess.run([sys.executable, str(ROOT / "tools/compatibility/module_probe.py"),
                                     "--jar", str(JAR), "--mode", "module-descriptor",
                                     "--ledger", str(ledger_path), "--output", str(report_path)],
                                    cwd=ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(report_path.read_text())["candidate_commit"], self.revision)

    def test_signature_report_attaches_the_build_receipt_used_for_replay(self):
        materialized = json.loads(json.dumps(self.materialized))
        path = ROOT / "tools/compatibility/receipts/jvm-signatures-0681a8cd.json.gz"
        report = json.loads(gzip.decompress(path.read_bytes()))
        signature_index.attach_report(materialized, report, path, ROOT)
        self.assertEqual(materialized["candidate_source"]["build_receipt"],
                         report["build_receipt"])
        self.assertEqual(materialized["candidate_source"]["build_receipt_sha256"],
                         report["build_receipt_sha256"])

    def test_build_receipt_binds_exact_ledger_source_despite_identical_other_jar(self):
        source = self.original["candidate_source"]
        recorded = json.loads((ROOT / source["build_receipt"]).read_text())
        self.assertIsNone(build_provenance.verify(recorded, ROOT, JAR, source))

        other_revision = candidate_coverage.git(ROOT, "rev-parse", "HEAD")
        self.assertNotEqual(other_revision, source["revision"])
        other = build_provenance.probe(ROOT, other_revision, JAR)
        self.assertTrue(other["passed"], other.get("reason"))
        self.assertEqual(other["artifact_sha256"], source["artifact_sha256"])
        self.assertNotEqual(other["source_tree"], source["tree"])
        self.assertEqual(
            build_provenance.verify(other, ROOT, JAR, source),
            "candidate build receipt revision differs from ledger source")

    def test_build_receipt_rejects_each_changed_ledger_identity_field(self):
        source = self.original["candidate_source"]
        recorded = json.loads((ROOT / source["build_receipt"]).read_text())
        for source_key, receipt_key, changed_value in (
                ("tree", "source_tree", "0" * 40),
                ("artifact", "artifact", "other.jar"),
                ("artifact_sha256", "artifact_sha256", "0" * 64)):
            with self.subTest(field=source_key):
                changed = {**source, source_key: changed_value}
                self.assertEqual(
                    build_provenance.verify(recorded, ROOT, JAR, changed),
                    f"candidate build receipt {receipt_key} differs from ledger source")

    def test_pinned_pass_cannot_drop_candidate_source_provenance(self):
        row = next(item for item in self.original["declarations"] if item["id"] == "org.dyn4j.world.World|type")
        passed = next(item for item in row["evidence"] if item["status"] == "passed")
        error = ledger.check_evidence(
            row, passed, ROOT, self.original["baseline"],
            self.expected["production"][row["source_file"]], {},
            {"baseline": self.original["baseline"]}, {})
        self.assertEqual(error, "pinned candidate source provenance is missing")

    def test_legacy_single_signature_cannot_bypass_build_provenance(self):
        row = next(item for item in self.original["declarations"] if item["id"] == "org.dyn4j.world.World|type")
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            report = Path(directory) / "legacy.json"
            report.write_text(json.dumps({"schema_version": 2, "probe": "javap-signature-v1"}))
            record = {"kind": "java-signature", "status": "passed", "target": "jvm",
                      "report": report.relative_to(ROOT).as_posix(),
                      "report_sha256": candidate_coverage.digest(report)}
            error = ledger.check_evidence(
                row, record, ROOT, self.original["baseline"],
                self.expected["production"][row["source_file"]], {}, self.original, {})
            self.assertEqual(error, "pinned candidate pass lacks replayable source and artifact provenance")

    def test_signature_index_replays_real_class_and_rejects_changed_member(self):
        rows = [row for row in self.materialized["declarations"]
                if row["id"].startswith("org.dyn4j.world.World|")]
        index = signature_index.observe(rows, JAR, self.original["production"])
        self.assertTrue(index["outcomes"]["org.dyn4j.world.World|type"]["passed"])
        changed = json.loads(json.dumps(rows))
        member = next(row for row in changed if len(row["id"].split("|")) == 3)
        member["signature"] = "public void missing(); descriptor: ()V"
        adverse = signature_index.observe(changed, JAR, self.original["production"])
        self.assertFalse(adverse["outcomes"][member["id"]]["passed"])

    def test_common_world_joint_detection_cannot_use_jvm_signature_receipt(self):
        for prefix in ("org.dyn4j.world.World|", "org.dyn4j.dynamics.joint.DistanceJoint|",
                       "org.dyn4j.collision.narrowphase.Gjk|"):
            row = next(item for item in self.original["declarations"]
                       if item["id"].startswith(prefix) and len(item["id"].split("|")) == 3
                       and any(record["status"] == "passed" for record in item["evidence"]))
            borrowed = dict(next(record for record in row["evidence"] if record["status"] == "passed"))
            borrowed["kind"] = "common-portable"
            borrowed["target"] = "linuxX64"
            error = ledger.check_evidence(
                row, borrowed, ROOT, self.original["baseline"],
                self.expected["production"][row["source_file"]], {}, self.original, {})
            self.assertIsNotNone(error, row["id"])

    def test_java_xml_requires_exact_original_identity_and_status(self):
        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory) / "cases.xml"
            xml.write_text('<testsuite tests="1" failures="0" errors="0" skipped="0">'
                           '<testcase classname="p.ATest" name="runs"/></testsuite>')
            self.assertEqual(java_corpus.read_xml(xml, 1), [("p.ATest", "runs")])
            xml.write_text('<testsuite tests="1" failures="0" errors="0" skipped="1">'
                           '<testcase classname="p.ATest" name="runs"><skipped/></testcase></testsuite>')
            with self.assertRaises(ValueError):
                java_corpus.read_xml(xml, 1)
            xml.write_text('<testsuite tests="1" failures="0" errors="0" skipped="0">'
                           '<testcase classname="p.ATest" name="other"/></testsuite>')
            self.assertNotEqual(java_corpus.read_xml(xml, 1), [("p.ATest", "runs")])

    def test_module_pass_requires_an_explicit_supported_target(self):
        module = json.loads(json.dumps(self.materialized["module"]))
        module["evidence"] = [{"kind": "module-descriptor", "status": "passed"}]
        invalid, _, _ = ledger.validate_module(module, self.expected["module"],
                                               self.expected["baseline"], ROOT, self.revision)
        self.assertTrue(any("target" in message for message in invalid))

    def test_failed_module_probe_remains_a_valid_unpassed_gap(self):
        module = json.loads(json.dumps(self.materialized["module"]))
        module["evidence"] = [{"kind": "module-descriptor", "status": "failed",
                               "reason": "descriptor differs"}]
        invalid, gaps, passed = ledger.validate_module(
            module, self.expected["module"], self.expected["baseline"], ROOT, self.revision)
        self.assertEqual(invalid, [])
        self.assertEqual(passed, set())
        self.assertTrue(any("failed" in message for message in gaps))

    @unittest.skipUnless(os.environ.get("DYN4K_BASELINE_SOURCE"), "pinned Java source not supplied")
    def test_copied_java_xml_cannot_omit_or_skip_an_original_case(self):
        report_path = ROOT / "tools/compatibility/receipts/java-corpus-0681a8cd/report.json"
        report = json.loads(report_path.read_text())
        original_dir = ROOT / report["xml_root"]
        lane = "candidate-javac8-java8"
        for control in ("identity", "status"):
            changed = json.loads(json.dumps(report))
            with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                target = Path(directory)
                for xml in original_dir.glob("*.xml"):
                    shutil.copy2(xml, target / xml.name)
                xml = target / f"{lane}.xml"
                content = xml.read_text()
                if control == "identity":
                    content = content.replace('name="headIteratorMissing"',
                                              'name="missingOriginalIdentity"', 1)
                else:
                    content = content.replace('skipped="0"', 'skipped="1"', 1)
                xml.write_text(content)
                changed["xml_root"] = target.relative_to(ROOT).as_posix()
                changed["lanes"][lane]["xml_sha256"] = candidate_coverage.digest(xml)
                error = java_corpus.validate_report(
                    changed, self.materialized, ROOT,
                    Path(os.environ["DYN4K_BASELINE_SOURCE"]), JAR)
                self.assertIn("XML or outcome differs" if control == "identity"
                              else "JUnit XML count or status differs", error, control)


if __name__ == "__main__":
    unittest.main()
