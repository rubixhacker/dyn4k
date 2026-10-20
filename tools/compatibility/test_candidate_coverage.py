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
from pathlib import Path
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


class JavaCorpusTemporaryDirectoryTests(unittest.TestCase):
    def java_temp_directory(self, output):
        return java_corpus.java_temp_directory(output)

    def test_runtime_command_uses_created_output_owned_temp_directory(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as parent:
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
        with tempfile.TemporaryDirectory(dir=ROOT) as parent:
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

    def test_replay_directory_is_created_under_the_worktree_and_cleaned(self):
        with java_corpus.replay_temp_directory(ROOT) as directory:
            replay = Path(directory)
            self.assertTrue(replay.is_dir())
            self.assertEqual(replay.parent, ROOT.resolve())
        self.assertFalse(replay.exists())


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
