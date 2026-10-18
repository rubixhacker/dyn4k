import hashlib
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import run
from cases import declared_cases


class ExtractionTest(unittest.TestCase):
    def test_prospective_cli_requires_external_attestation_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            arguments = ["run.py", "--output", str(output),
                         "--prospective-baseline", str(Path(directory) / "baseline")]
            with patch("sys.argv", arguments), self.assertRaises(SystemExit) as error:
                run.main()
            self.assertEqual(error.exception.code, 2)
            self.assertFalse(output.exists())

    @staticmethod
    def compiler_proof(task, artifact):
        return "NUMERICAL_PROOF_INPUT " + json.dumps({
            "task": task, "path": str(artifact.resolve()),
            "sha256": run.digest(artifact), "bytes": artifact.stat().st_size}) + "\n"

    def test_joint_method_declaration_matches_all_24_source_emissions(self):
        expected = [f"joint-{kind}-{mode}" for kind in
                    ("Angle", "Distance", "Friction", "Motor", "Pin", "Prismatic",
                     "Pulley", "Revolute", "Weld", "Wheel") for mode in ("initial", "active")]
        expected += ["P-JINT-Weld-enabled-equal"]
        expected += [f"P-JINT-Pulley-slack-transition-{segment}" for segment in
                     ("preparation-0", "preparation-1", "main")]
        self.assertEqual([case["id"] for case in declared_cases()[94:118]], expected)

    def test_complete_joint_method_rejects_one_swapped_case(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "evidence"
            output.mkdir()
            ids = [case["id"] for case in declared_cases()[94:118]]
            def xml(order):
                rows = []
                for case_id in order:
                    rows.extend(({"kind": "inputs", "id": case_id},
                                 {"kind": "state", "id": case_id, "step": 1},
                                 {"kind": "case-end", "id": case_id}))
                source = root / "method.xml"
                source.write_text('<?xml version="1.0"?>\n'
                    '<testsuite tests="1" skipped="0" failures="0" errors="0">\n'
                    '<system-out><![CDATA[' +
                    ''.join("NUMERICAL_JSON " + json.dumps(row) + "\n" for row in rows) +
                    ']]></system-out></testsuite>\n')
                return source
            with patch.object(run, "PORTABLE", root):
                trace, _, counts = run.extract_xml("jvm", output,
                    "everyJointWithInitialAndApplicableActiveModes", xml(ids))
                self.assertEqual(counts["completed_cases"], 24)
                self.assertEqual(len(trace.read_text().splitlines()), 72)
                swapped = ids.copy()
                swapped[20], swapped[21] = swapped[21], swapped[20]
                adverse = root / "adverse"
                adverse.mkdir()
                with self.assertRaisesRegex(Exception, "case order"):
                    run.extract_xml("jvm", adverse,
                        "everyJointWithInitialAndApplicableActiveModes", xml(swapped))

    def test_source_identity_rejects_ignored_source_inside_generated_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(("git", "init", "-q", str(root)), check=True)
            (root / ".gitignore").write_text("build/\n**/build/\n__pycache__/\n")
            subprocess.run(("git", "-C", str(root), "add", ".gitignore"), check=True)
            subprocess.run(("git", "-C", str(root), "-c", "user.name=Test",
                            "-c", "user.email=test@example.invalid", "commit", "-qm", "base"), check=True)
            output = root / "tools/numerical/portable/build/generated/Recorder.kt"
            output.parent.mkdir(parents=True)
            output.write_text("generated\n")
            cache = root / "tools/numerical/portable/__pycache__/run.cpython-314.pyc"
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b"generated")
            source = root / "tools/numerical/portable/src/commonMain/kotlin/build/Hidden.kt"
            source.parent.mkdir(parents=True)
            source.write_text("class Hidden\n")
            with patch.object(run, "ROOT", root):
                with self.assertRaisesRegex(run.Rejected, "source tree is dirty"):
                    run.clean_identity()
            source.unlink()
            with patch.object(run, "ROOT", root):
                self.assertEqual(run.clean_identity()[0],
                                 subprocess.check_output(("git", "-C", str(root),
                                                          "rev-parse", "HEAD"), text=True).strip())

    def test_source_identity_rejects_tracked_source_inside_ignored_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(("git", "init", "-q", str(root)), check=True)
            source = root / "tools/numerical/portable/src/build/Hidden.kt"
            source.parent.mkdir(parents=True)
            source.write_text("class Hidden\n")
            subprocess.run(("git", "-C", str(root), "add", "-f",
                            "tools/numerical/portable/src/build/Hidden.kt"), check=True)
            with patch.object(run, "ROOT", root):
                with self.assertRaisesRegex(run.Rejected, "source tree is dirty"):
                    run.clean_identity()

    def test_source_archive_identity_is_stable_across_autocrlf(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(("git", "init", "-q", str(root)), check=True)
            (root / ".gitattributes").write_text("* text=auto\n")
            (root / "README.md").write_bytes(b"first line\nsecond line\n")
            subprocess.run(("git", "-C", str(root), "add", "."), check=True)
            subprocess.run(("git", "-C", str(root), "-c", "user.name=Test", "-c",
                            "user.email=test@example.invalid", "commit", "-qm", "source"), check=True)
            archive_hashes = {}
            with patch.object(run, "ROOT", root):
                for setting in ("false", "true"):
                    subprocess.run(("git", "-C", str(root), "config", "core.autocrlf", setting),
                                   check=True)
                    archive_hashes[setting] = run.clean_identity()[1]
            self.assertEqual(archive_hashes["false"], archive_hashes["true"])

    def test_source_identity_uses_original_commit_despite_same_type_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
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
            subprocess.run(("git", "-C", str(root), "checkout", "-q", original), check=True)
            subprocess.run(("git", "-C", str(root), "replace", original, substitute), check=True)
            canonical = subprocess.check_output(("git", "-C", str(root),
                                                 "--no-replace-objects", "-c",
                                                 "core.autocrlf=false", "archive",
                                                 "--format=tar", original))
            substituted = subprocess.check_output(("git", "-C", str(root), "-c",
                                                   "core.autocrlf=false", "archive",
                                                   "--format=tar", original))
            self.assertNotEqual(canonical, substituted)
            with patch.object(run, "ROOT", root):
                self.assertEqual(run.clean_identity(),
                                 (original, hashlib.sha256(canonical).hexdigest()))
                source.write_text("substituted\n")
                subprocess.run(("git", "-C", str(root), "add", "."), check=True)
                self.assertEqual(subprocess.check_output(("git", "-C", str(root), "status",
                                                         "--porcelain")), b"")
                with self.assertRaisesRegex(run.Rejected, "source tree is dirty"):
                    run.clean_identity()

    def test_unexecuted_android_native_host_is_not_called_unavailable(self):
        self.assertEqual(run.other_lane_status("android-native-x64")[0], "NOT_RUN")
        self.assertEqual(run.other_lane_status("android-device")[0], "NOT_RUN")
        self.assertEqual(run.other_lane_status("ios-arm64")[0], "UNAVAILABLE")
        with tempfile.TemporaryDirectory() as directory:
            receipt = run.absent_lane(Path(directory), "android-native-x64", "a" * 40,
                                      "b" * 64, *run.other_lane_status("android-native-x64"))
            self.assertEqual(receipt["executed_cases"], 0)
            self.assertEqual(receipt["qualification"], "UNPASSED")
            self.assertEqual(json.loads((Path(directory) / "android-native-x64/receipt.json").read_text()),
                             receipt)

    def test_native_receipt_requires_executed_test_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "build/bin/linuxX64/debugTest/test.kexe"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"native-test-binary")
            artifact = root / "dyn4k-core-linuxx64.klib"
            artifact.write_bytes(b"staged native klib")
            log = root / "gradle.log"
            log.write_text("native test passed\n" +
                self.compiler_proof(":compileKotlinLinuxX64", artifact) +
                self.compiler_proof(":compileTestKotlinLinuxX64", artifact) +
                self.compiler_proof(":linkDebugTestLinuxX64", artifact))
            execution = root / "native-exec.log"
            execution.write_text(f'123 execve("{binary}", ["test.kexe"], 0x1) = 0\n')
            with patch.object(run, "PORTABLE", root):
                result = run.runtime("linux-x64", log, execution, dependency=artifact)
                self.assertEqual(result["executable_sha256"], run.digest(binary))
                self.assertEqual(result["executable"], str(binary.resolve()))
                execution.write_text('123 execve("/tmp/other.kexe", [], 0x1) = 0\n')
                with self.assertRaisesRegex(Exception, "executed native test binary"):
                    run.runtime("linux-x64", log, execution, dependency=artifact)
                execution.write_text(
                    f'123 execve("{binary}", ["test.kexe"], 0x1) = 0\n'
                    f'124 execve("{binary}", ["test.kexe"], 0x1) = 0\n')
                with self.assertRaisesRegex(Exception, "one executed native test binary"):
                    run.runtime("linux-x64", log, execution, dependency=artifact)

    def test_compiler_proof_accepts_resolved_publication_bytes_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged = root / "dyn4k-core-linuxx64.klib"
            staged.write_bytes(b"staged native klib")
            resolved = root / "io.github.rubixhacker/dyn4k-core-linuxx64/0.1.0-alpha.1/cache.klib"
            resolved.parent.mkdir(parents=True)
            resolved.write_bytes(staged.read_bytes())
            log = root / "compiler.log"
            tasks = (":compileKotlinLinuxX64", ":compileTestKotlinLinuxX64",
                     ":linkDebugTestLinuxX64")
            log.write_text("".join(self.compiler_proof(task, resolved) for task in tasks))
            proof = run._compiled_dependency_proof("linux-x64", log, staged)
            self.assertEqual([item["task"] for item in proof["tasks"]], list(tasks))
            unrelated = root / "unrelated.klib"
            unrelated.write_bytes(staged.read_bytes())
            log.write_text("".join(self.compiler_proof(task, unrelated) for task in tasks))
            with self.assertRaisesRegex(run.Rejected, "outside staged publication"):
                run._compiled_dependency_proof("linux-x64", log, staged)
            log.write_text("".join(self.compiler_proof(task, resolved) for task in tasks))
            resolved.write_bytes(b"changed resolved bytes")
            with self.assertRaisesRegex(run.Rejected, "compiler input differs"):
                run._compiled_dependency_proof("linux-x64", log, staged)

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
            root = Path(directory)
            staged = root / "dyn4k-core-jvm.jar"
            with zipfile.ZipFile(staged, "w") as archive:
                archive.writestr("org/dyn4j/geometry/Vector2.class", b"staged class")
            staged_sha = run.digest(staged)
            log = root / "gradle.log"
            log.write_text("Starting process 'Gradle Test Executor 1'. Command: " +
                           str(executable) + " -cp worker.jar\n" +
                           "[Loaded org.dyn4j.geometry.Vector2 from " +
                           staged.as_uri() + "]\n")
            execution = root / "worker-exec.log"
            execution.write_text(
                f'123 execve("{executable}", ["java", "GradleWorkerMain"], 0x1) = 0\n'
                f'123 openat(AT_FDCWD, "{staged}", O_RDONLY) = 4\n')
            result = run.runtime("jvm8", log, execution, dependency=staged)
            self.assertEqual(result["dependency"]["worker_open"]["worker_pid"], "123")
            execution.write_text(
                f'123 execve("{executable}", ["java", "GradleWorkerMain"], 0x1) = 0\n'
                f'124 openat(AT_FDCWD, "{staged}", O_RDONLY) = 4\n')
            with self.assertRaisesRegex(run.Rejected, "Java 8 worker.*staged"):
                run.runtime("jvm8", log, execution, dependency=staged)
            execution.write_text(
                f'123 execve("{executable}", ["java", "GradleWorkerMain"], 0x1) = 0\n'
                f'123 openat(AT_FDCWD, "{staged}", O_RDONLY) = 4\n'
                f'124 execve("{executable}", ["java", "GradleWorkerMain"], 0x1) = 0\n')
            with self.assertRaisesRegex(run.Rejected, "one Java 8 worker"):
                run.runtime("jvm8", log, execution, dependency=staged)
        self.assertEqual(result["executable"], str(executable.resolve()))
        self.assertEqual(result["executable_sha256"], run.digest(executable))
        self.assertIn('version "1.8.', result["version"])
        self.assertEqual(result["dependency"]["dependency_sha256"], staged_sha)

    def test_java_8_worker_cannot_certify_jvm_21_route(self):
        executable = Path("/tmp/dyn4k-tools/jdk8/bin/java")
        if not executable.is_file():
            self.skipTest("Java 8 test runtime is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "gradle.log"
            log.write_text("Starting process 'Gradle Test Executor 1'. Command: " +
                           str(executable) + " -cp worker.jar\n")
            with self.assertRaisesRegex(run.Rejected, "Java 21"):
                run.runtime("jvm", log)

    def test_two_worker_commands_cannot_be_certified_as_one_execution(self):
        executable = Path("/tmp/dyn4k-tools/jdk8/bin/java")
        if not executable.is_file():
            self.skipTest("Java 8 test runtime is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "gradle.log"
            log.write_text("".join(
                f"Starting process 'Gradle Test Executor {index}'. Command: " +
                str(executable) + " -cp worker.jar\n" for index in (1, 2)))
            with self.assertRaisesRegex(run.Rejected, "worker command"):
                run.runtime("jvm8", log)

    def test_jvm_worker_without_staged_dependency_proof_is_unpassed(self):
        executable = Path("/tmp/dyn4k-tools/jdk8/bin/java")
        if not executable.is_file():
            self.skipTest("Java 8 test runtime is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "gradle.log"
            log.write_text("Starting process 'Gradle Test Executor 1'. Command: " +
                           str(executable) + " -cp worker.jar\n")
            with self.assertRaisesRegex(run.Rejected, "staged dependency"):
                run.runtime("jvm8", log)

    def test_current_jvm_receipt_requires_loaded_class_proof(self):
        executable = Path("/tmp/dyn4k-tools/jdk21/bin/java")
        if not executable.is_file():
            self.skipTest("Java 21 test runtime is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged = root / "dyn4k-core-jvm.jar"
            with zipfile.ZipFile(staged, "w") as archive:
                archive.writestr("org/dyn4j/geometry/Vector2.class", b"staged class")
            log = root / "gradle.log"
            log.write_text("Starting process 'Gradle Test Executor 1'. Command: " +
                           str(executable) + " -cp " + str(staged) + "\n")
            with self.assertRaisesRegex(run.Rejected, "loaded staged dependency"):
                run.runtime("jvm", log, dependency=staged,
                            proof_dir=root / "process-proof")

    def test_node_receipt_uses_executed_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "node"
            executable.write_text("#!/bin/sh\nprintf 'v99.1.0\\n'\n")
            executable.chmod(0o755)
            artifact = root / "dyn4k-core-js.klib"
            artifact.write_bytes(b"staged js klib")
            bundle = root / "dyn4k-portable-numerical-consumer-test.js"
            bundle.write_text("require('./dyn4k-dyn4k-core.js')\n")
            (root / "dyn4k-dyn4k-core.js").write_text("exports.core = true\n")
            execution = root / "exec.log"
            execution.write_text(f'123 execve("{executable}", ["{executable}", '
                                 f'"{bundle}", "--reporter", "reporter.js"], 0x1) = 0\n')
            log = root / "gradle.log"
            log.write_text("Starting process 'command '" + str(executable) +
                           "''. Command: " + str(executable) + " yarn.js install\n" +
                           "Starting process 'command '" + str(executable) +
                           "''. Command: " + str(executable) + " " + str(bundle) + "\n" +
                           "".join(self.compiler_proof(task, artifact) for task in
                               (":compileKotlinJs", ":compileTestKotlinJs",
                                ":compileTestDevelopmentExecutableKotlinJs")))
            expected_sha = run.digest(executable)
            result = run.runtime("node-js", log, execution, dependency=artifact)
        self.assertEqual(result["executable"], str(executable.resolve()))
        self.assertEqual(result["executable_sha256"], expected_sha)
        self.assertEqual(result["version"], "v99.1.0")
        self.assertEqual(result["bundle"]["process_executions"], 1)

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
                report("P-J-Angle-ratio-limits-off--1.0")
                first = run.extract_xml("jvm", output,
                                        "baselineAngleNegativeRatioRemainsAnIsolatedPhysicalFailure")
                report("long-free-60")
                second = run.extract_xml("jvm", output, "longRunningFreeMotionInvariantScene")
            self.assertEqual(first[0], second[0])
            self.assertEqual(len(first[0].read_text().splitlines()), 6)
            self.assertEqual(first[2]["completed_cases"], 1)
            self.assertEqual(second[2]["completed_cases"], 1)
            self.assertTrue((output / "xml/baselineAngleNegativeRatioRemainsAnIsolatedPhysicalFailure.xml").is_file())
            self.assertTrue((output / "xml/longRunningFreeMotionInvariantScene.xml").is_file())
            self.assertTrue((output / "cases/P-J-Angle-ratio-limits-off--1.0.jsonl").is_file())
            self.assertTrue((output / "cases/long-free-60.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
