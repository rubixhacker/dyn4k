import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import run
from jdk8_test_runtime import selected_test_jdk8_home
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
            method = "baselineAngleNegativeRatioRemainsAnIsolatedPhysicalFailure"
            name = f"portable.PortableMatrixTest.{method}"
            binary.write_text("#!/bin/sh\n" +
                f"printf '[ RUN      ] {name}\\n'\n" +
                "printf 'NUMERICAL_JSON {\"kind\":\"inputs\",\"id\":\"P-J-Angle-ratio-limits-off--1.0\"}\\n'\n" +
                f"printf '[       OK ] {name} (1 ms)\\n'\n" +
                "printf '[  PASSED  ] 1 tests.\\n'\n")
            binary.chmod(0o755)
            artifact = root / "dyn4k-core-linuxx64.klib"
            artifact.write_bytes(b"staged native klib")
            lane = root / "lane"
            lane.mkdir()
            log = lane / f"gradle-{method}.log"
            started = time.time_ns() - 1_000_000_000
            log.write_text(f"NUMERICAL_BUILD_STARTED_NS {started}\n" +
                self.compiler_proof(":compileKotlinLinuxX64", artifact) +
                self.compiler_proof(":compileTestKotlinLinuxX64", artifact) +
                self.compiler_proof(":linkDebugTestLinuxX64", artifact))
            if run.shutil.which("strace") is None:
                self.skipTest("strace is unavailable")
            with patch.object(run, "PORTABLE", root):
                execution = run.run_native_method(method, lane, binary, os.environ.copy())
                result = run.runtime("linux-x64", log, execution, dependency=artifact)
                self.assertEqual(result["executable_sha256"], run.digest(binary))
                self.assertEqual(result["executable"], str(binary.resolve()))
                self.assertEqual(result["worker_command"], run.native_command(method, binary))
                captured = execution.read_text()
                execution.write_text(captured.replace(str(binary), "/tmp/other.kexe"))
                with self.assertRaisesRegex(Exception, "executed native test binary"):
                    run.runtime("linux-x64", log, execution, dependency=artifact)
                execution.write_text(captured + captured)
                with self.assertRaisesRegex(Exception, "one executed native test binary"):
                    run.runtime("linux-x64", log, execution, dependency=artifact)
                execution.write_text(captured)
                binary.write_text(binary.read_text() + "# replaced\n")
                self.assertNotEqual(run.runtime("linux-x64", log, execution,
                                    dependency=artifact), result)
                log.write_text(log.read_text().replace(str(started), str(time.time_ns())))
                with self.assertRaisesRegex(run.Rejected, "stale"):
                    run.runtime("linux-x64", log, execution, dependency=artifact)

    def test_native_stream_replay_rejects_incomplete_and_mutated_output(self):
        method = "baselineAngleNegativeRatioRemainsAnIsolatedPhysicalFailure"
        name = f"portable.PortableMatrixTest.{method}"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "native.log"
            xml = root / "method.xml"
            complete = (f"[ RUN      ] {name}\n"
                        'NUMERICAL_JSON {"kind":"inputs","id":"P-J-Angle-ratio-limits-off--1.0"}\n'
                        'NUMERICAL_JSON {"kind":"case-end","id":"P-J-Angle-ratio-limits-off--1.0"}\n'
                        f"[       OK ] {name} (1 ms)\n"
                        "[  PASSED  ] 1 tests.\n")
            raw.write_text(complete)
            run.native_stream_xml(method, raw, xml, create=True)
            self.assertEqual(run.native_stream_xml(method, raw, xml), 2)
            evidence = root / "evidence"
            evidence.mkdir()
            archived = evidence / "xml" / f"{method}.xml"
            archived.parent.mkdir()
            run.native_stream_xml(method, raw, archived, create=True)
            trace, attributes, counts = run.extract_xml("linux-x64", evidence, method, archived)
            self.assertEqual(attributes["tests"], "1")
            self.assertEqual(counts["completed_cases"], 1)
            self.assertEqual(len(trace.read_text().splitlines()), 2)
            for changed in (complete.removesuffix("\n"), complete.replace("[       OK ]", "[  FAILED  ]"),
                            complete.replace(name, "portable.PortableMatrixTest.other"),
                            complete.replace("[  PASSED  ] 1 tests.\n", "")):
                raw.write_text(changed)
                with self.assertRaises(run.Rejected):
                    run.native_stream_xml(method, raw, xml)
            raw.write_text(complete.replace("P-J-Angle", "P-J-Other"))
            with self.assertRaisesRegex(run.Rejected, "XML differs"):
                run.native_stream_xml(method, raw, xml)
            raw.write_text(complete)
            xml.write_bytes(xml.read_bytes()[:-10])
            with self.assertRaisesRegex(run.Rejected, "XML differs"):
                run.native_stream_xml(method, raw, xml)
            wrong = root / "wrong.xml"
            raw.write_text(complete.replace("P-J-Angle", "P-J-Other"))
            run.native_stream_xml(method, raw, wrong, create=True)
            wrong_evidence = root / "wrong-evidence"
            wrong_evidence.mkdir()
            with self.assertRaisesRegex(run.Rejected, "case order"):
                run.extract_xml("linux-x64", wrong_evidence, method, wrong)

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
            log.write_text("".join(self.compiler_proof(task, resolved) for task in
                                   (*tasks, tasks[-1])))
            with self.assertRaisesRegex(run.Rejected, "task sequence differs"):
                run._compiled_dependency_proof("linux-x64", log, staged)
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

    def test_traced_jvm8_method_uses_local_in_process_compiler(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(run.shutil, "which", return_value="/usr/bin/strace"):
            lane = Path(directory)
            method = "freeMotionForcesDampingAndRestitution"
            jdk8 = selected_test_jdk8_home()
            command, execution_log = run.method_command("jvm8", method, lane, jdk8)
            self.assertEqual(command[:7], ["/usr/bin/strace", "-f", "-s", "65535",
                                           "-e", "trace=process,openat", "-o"])
            self.assertEqual(command[7], str(execution_log))
            self.assertEqual(execution_log, lane / f"native-exec-{method}.log")
            self.assertEqual(command.count("-Pkotlin.compiler.execution.strategy=in-process"), 1)
            self.assertIn(f"portable.PortableMatrixTest.{method}", command)
            self.assertIn("-PportableJvm8=true", command)
            self.assertIn("-Dorg.gradle.java.installations.paths=" + str(jdk8), command)
            self.assertIn("--init-script", command)
            ordinary, ordinary_log = run.method_command("jvm", method, lane)
            self.assertIsNone(ordinary_log)
            self.assertNotIn("-Pkotlin.compiler.execution.strategy=in-process", ordinary)
            native, native_log = run.method_command("linux-x64", method, lane)
            self.assertIsNone(native_log)
            self.assertIn(":linkDebugTestLinuxX64", native)
            self.assertNotIn("--tests", native)
            self.assertNotIn("linuxX64Test", native)
            node, node_log = run.method_command("node-js", method, lane)
            self.assertIsNone(node_log)
            self.assertIn(":jsTestTestDevelopmentExecutableCompileSync", node)
            self.assertNotIn("--tests", node)
            self.assertEqual(node.count("-Pkotlin.compiler.execution.strategy=in-process"), 0)
            for host in ("node-wasm-js", "node-wasm-wasi"):
                traced, trace_log = run.method_command(host, method, lane)
                self.assertIsNone(trace_log)
                self.assertIn(":wasmJsTestTestDevelopmentExecutableCompileSync" if
                              host == "node-wasm-js" else
                              ":compileTestDevelopmentExecutableKotlinWasmWasi", traced)
                self.assertNotIn("--tests", traced)
                self.assertEqual(traced.count("-Pkotlin.compiler.execution.strategy=in-process"), 1)

    def test_traced_method_rejects_missing_tracer_and_unknown_method(self):
        with patch.object(run.shutil, "which", return_value=None):
            with self.assertRaisesRegex(run.Rejected, "strace is unavailable"):
                run.method_command("jvm8", "freeMotionForcesDampingAndRestitution",
                                   Path("/tmp/unused"), selected_test_jdk8_home())
        with self.assertRaisesRegex(run.Rejected, "unknown numerical matrix method"):
            run.method_command("jvm8", "unrecorded", Path("/tmp/unused"))
        with self.assertRaisesRegex(run.Rejected, "explicit Java 8 home"):
            run.method_command("jvm8", "freeMotionForcesDampingAndRestitution",
                               Path("/tmp/unused"))

    def test_java8_requires_real_home_and_direct_classpath(self):
        jdk8 = selected_test_jdk8_home()
        self.assertEqual(run.selected_jdk8_home(jdk8), jdk8)
        with tempfile.TemporaryDirectory() as directory:
            missing_home = Path(directory) / "missing-jdk"
            for invalid in (None, Path("relative"), missing_home):
                with self.subTest(invalid=invalid), self.assertRaises(run.Rejected):
                    run.selected_jdk8_home(invalid)
        with tempfile.TemporaryDirectory() as directory:
            response = Path(directory) / "worker.args"
            response.write_text("-cp /classes")
            with self.assertRaisesRegex(run.Rejected, "argument file is unsupported"):
                run._java_classpath([str(jdk8 / "bin/java"), "@" + str(response)], "jvm8")

    def test_java8_test_runtime_is_explicit_and_fails_on_wrong_version(self):
        with patch.dict(os.environ, {"DYN4K_TEST_JDK8_HOME": ""}):
            with self.assertRaisesRegex(RuntimeError, "DYN4K_TEST_JDK8_HOME"):
                selected_test_jdk8_home()
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "synthetic-jdk"
            binary = home / "bin"
            binary.mkdir(parents=True)
            java = binary / "java"
            javac = binary / "javac"
            java.write_text('#!/bin/sh\nprintf \'openjdk version "21.0.1"\\n\' >&2\n')
            javac.write_text("#!/bin/sh\nprintf 'javac 21.0.1\\n' >&2\n")
            java.chmod(0o755)
            javac.chmod(0o755)
            with patch.dict(os.environ, {"DYN4K_TEST_JDK8_HOME": str(home.resolve())}):
                with self.assertRaisesRegex(RuntimeError, "wrong java version"):
                    selected_test_jdk8_home()

    def test_java_8_worker_open_proof_requires_staged_jar_in_worker_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged = root / "dyn4k-core-jvm.jar"
            staged.write_bytes(b"staged")
            other = root / "dyn4k-core-other.jar"
            other.write_bytes(b"other")
            executable = Path("/tmp/dyn4k-tools/jdk8/bin/java")
            execution = root / "native-exec.log"
            prefix = (f'123 execve("{executable}", ["java", "GradleWorkerMain"], 0x1) = 0\n'
                      '123 clone(child_stack=NULL, flags=CLONE_VM) = 124\n')
            execution.write_text(prefix +
                                 f'124 openat(AT_FDCWD, "{staged}", O_RDONLY) = 4\n')
            command = [str(executable)]
            proof = run._java_worker_open_proof(command, staged, execution)
            self.assertEqual(proof["worker_pid"], "123")
            self.assertEqual(proof["opened_artifact_sha256"], run.digest(staged))
            interrupted = (f'123 execve("{executable}", ["java", "GradleWorkerMain"], 0x1) = 0\n'
                           '123 clone3({flags=CLONE_THREAD} <unfinished ...>\n'
                           '123 <... clone3 resumed> => {parent_tid=[124]}, 88) = 124\n')
            execution.write_text(interrupted +
                                 f'124 openat(AT_FDCWD, "{staged}", O_RDONLY) = 4\n')
            self.assertEqual(run._java_worker_open_proof(command, staged, execution)["worker_pid"],
                             "123")
            execution.write_text(interrupted.replace(
                '123 clone3({flags=CLONE_THREAD} <unfinished ...>\n', '') +
                f'124 openat(AT_FDCWD, "{staged}", O_RDONLY) = 4\n')
            with self.assertRaisesRegex(run.Rejected, "only the staged dependency"):
                run._java_worker_open_proof(command, staged, execution)
            execution.write_text(prefix +
                                 f'124 openat(AT_FDCWD, "{other}", O_RDONLY) = 4\n')
            with self.assertRaisesRegex(run.Rejected, "only the staged dependency"):
                run._java_worker_open_proof(command, staged, execution)

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

    def test_java_21_banner_cannot_certify_jvm_8_route(self):
        executable = Path("/tmp/dyn4k-tools/jdk21/bin/java")
        if not executable.is_file():
            self.skipTest("Java 21 test runtime is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "gradle.log"
            log.write_text("Starting process 'Gradle Test Executor 1'. Command: " +
                           str(executable) + " -cp worker.jar\n")
            with patch.dict(os.environ, {"JAVA_TOOL_OPTIONS": "-verbose:class"}):
                with self.assertRaisesRegex(run.Rejected, "Java 8"):
                    run.runtime("jvm8", log)

    def test_java_version_probe_accepts_retained_banner_shape(self):
        java8 = subprocess.CompletedProcess(["java", "-version"], 0,
            stdout="[Opened /tmp/dyn4k-tools/jdk8/jre/lib/rt.jar]\n"
                   "[Loaded java.lang.Object from /tmp/dyn4k-tools/jdk8/jre/lib/rt.jar]\n",
            stderr="Picked up JAVA_TOOL_OPTIONS: -Djava.io.tmpdir=/tmp/numerical -verbose:class\n"
                   'openjdk version "1.8.0_504"\n'
                   "OpenJDK Runtime Environment (Temurin)(build 1.8.0_504-b01)\n"
                   "OpenJDK 64-Bit Server VM (Temurin)(build 25.504-b01, mixed mode)\n")
        self.assertEqual(run._java_version_line(java8), 'openjdk version "1.8.0_504"')
        java21 = subprocess.CompletedProcess(["java", "-version"], 0,
            stdout="[0.008s][info][class,load] java.lang.Object source: shared objects file\n",
            stderr="Picked up JAVA_TOOL_OPTIONS: -Djava.io.tmpdir=/tmp/numerical -verbose:class\n"
                   'openjdk version "21.0.12.1" 2026-08-18 LTS\n'
                   "OpenJDK Runtime Environment Temurin-21.0.12.1+1 (build 21.0.12.1+1-LTS)\n"
                   "OpenJDK 64-Bit Server VM Temurin-21.0.12.1+1 (build 21.0.12.1+1-LTS)\n")
        self.assertEqual(run._java_version_line(java21),
                         'openjdk version "21.0.12.1" 2026-08-18 LTS')

    def test_java_version_probe_rejects_missing_malformed_and_conflicting_lines(self):
        banner = "Picked up JAVA_TOOL_OPTIONS: -verbose:class\n"
        failures = (
            (0, banner, "absent"),
            (0, banner + 'openjdk version 1.8.0_504\n', "malformed"),
            (0, banner + 'openjdk version "1.8.0_504"\n'
             'openjdk version "21.0.12.1"\n', "multiple"),
            (0, "unrecognized diagnostic\n" + 'openjdk version "1.8.0_504"\n',
             "preamble"),
            (1, 'openjdk version "1.8.0_504"\n', "failed"),
        )
        for exit_code, output, reason in failures:
            with self.subTest(reason=reason), self.assertRaisesRegex(run.Rejected, reason):
                run._java_version_line(subprocess.CompletedProcess(
                    ["java", "-version"], exit_code, stdout="", stderr=output))

    def test_java_version_probe_rejects_reviewed_malformed_output(self):
        malformed = (
            'openjdk version "21.0.12.1" 2026-99-99 LTS\n',
            'openjdk version "21.0.12.1"\nOpenJDK Runtime Environment garbage\n',
            'openjdk version "21.0.12.1"\nOpenJDK 64-Bit Server VM garbage\n',
        )
        for output in malformed:
            with self.subTest(output=output), self.assertRaises(run.Rejected):
                run._java_version_line(subprocess.CompletedProcess(
                    ["java", "-version"], 0, stdout="", stderr=output))

    def test_real_java_8_version_banner_keeps_worker_identity(self):
        executable = Path("/tmp/dyn4k-tools/jdk8/bin/java")
        if not executable.is_file():
            self.skipTest("Java 8 test runtime is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged = root / "dyn4k-core-jvm.jar"
            with zipfile.ZipFile(staged, "w") as archive:
                archive.writestr("org/dyn4j/geometry/Vector2.class", b"staged class")
            log = root / "gradle.log"
            log.write_text("Starting process 'Gradle Test Executor 1'. Command: " +
                           str(executable) + " -cp " + str(staged) + "\n" +
                           "[Loaded org.dyn4j.geometry.Vector2 from " +
                           staged.as_uri() + "]\n")
            execution = root / "native-exec.log"
            execution.write_text(
                f'123 execve("{executable}", ["java", "GradleWorkerMain"], 0x1) = 0\n'
                f'123 openat(AT_FDCWD, "{staged}", O_RDONLY) = 4\n')
            with patch.dict(os.environ, {"JAVA_TOOL_OPTIONS": "-verbose:class"}):
                result = run.runtime("jvm8", log, execution, dependency=staged)
            self.assertEqual(result["version"], 'openjdk version "1.8.0_504"')
            self.assertEqual(result["executable"], str(executable.resolve()))
            self.assertEqual(result["dependency"]["worker_open"]["worker_pid"], "123")

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


class DetachedNativeBundleTest(unittest.TestCase):
    def test_copied_archive_replays_without_producer_build_or_cache(self):
        if run.shutil.which("strace") is None:
            self.skipTest("strace is unavailable")
        method = "baselineAngleNegativeRatioRemainsAnIsolatedPhysicalFailure"
        case_id = "detached-case"
        name = f"portable.PortableMatrixTest.{method}"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            producer = root / "producer"
            verifier = root / "verifier"
            subprocess.run(("git", "init", "-q", str(producer)), check=True)
            (producer / ".gitignore").write_text("build/\n**/build/\n")
            subprocess.run(("git", "-C", str(producer), "add", ".gitignore"), check=True)
            subprocess.run(("git", "-C", str(producer), "-c", "user.name=Test",
                            "-c", "user.email=test@example.invalid", "commit", "-qm", "source"),
                           check=True)
            subprocess.run(("git", "clone", "-q", "--local", str(producer), str(verifier)),
                           check=True)
            portable = producer / "tools/numerical/portable"
            staged = producer / "build/staging-repository/io/github/rubixhacker"
            output = root / "producer-archive"
            lane = output / "linux-x64"
            lane.mkdir(parents=True)
            cache = root / "producer-cache/.gradle/caches/modules-2/files-2.1" / \
                "io.github.rubixhacker/dyn4k-core-linuxx64" / run.VERSION / ("a" * 40) / \
                f"dyn4k-core-linuxX64Main-{run.VERSION}.klib"
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b"staged native klib")
            target_name = run.artifact_relative_paths("linux-x64")["target"]
            staged_files = {}
            for filename in run._publication_names():
                path = staged / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(cache.read_bytes() if filename == target_name else
                                 filename.encode())
                staged_files[filename] = run.digest(path)
            publication_log = output / "publication.log"
            publication_log.write_text("published\n")
            binary = portable / "build/bin/linuxX64/debugTest/test.kexe"
            binary.parent.mkdir(parents=True)
            binary.write_text("#!/bin/sh\n" +
                f"printf '[ RUN      ] {name}\\n'\n" +
                f"printf 'NUMERICAL_JSON {{\"kind\":\"inputs\",\"id\":\"{case_id}\"}}\\n'\n" +
                f"printf 'NUMERICAL_JSON {{\"kind\":\"state\",\"id\":\"{case_id}\",\"step\":1}}\\n'\n" +
                f"printf 'NUMERICAL_JSON {{\"kind\":\"case-end\",\"id\":\"{case_id}\"}}\\n'\n" +
                f"printf '[       OK ] {name} (1 ms)\\n'\n" +
                "printf '[  PASSED  ] 1 tests.\\n'\n")
            binary.chmod(0o755)
            with patch.multiple(run, ROOT=producer, PORTABLE=portable, STAGED=staged,
                                MATRIX_METHODS=(method,), MATRIX_METHOD_CASE_COUNTS=(1,)), \
                    patch.object(run, "declared_cases", return_value=[{"id": case_id}]):
                commit, source_sha256 = run.clean_identity()
                publication = {"candidate_commit": commit, "source_sha256": source_sha256,
                               "artifact_sha256": staged_files,
                               "publication_log_sha256": run.digest(publication_log)}
                (output / "publication.json").write_text(json.dumps(publication))
                manifest = run.start_native_bundle(output, lane, commit, source_sha256)
                started = time.time_ns() - 1_000_000_000
                log = lane / f"gradle-{method}.log"
                log.write_text(f"NUMERICAL_BUILD_STARTED_NS {started}\n" +
                    "".join("NUMERICAL_PROOF_INPUT " + json.dumps({
                        "task": task, "path": str(cache.resolve()),
                        "sha256": run.digest(cache), "bytes": cache.stat().st_size}) + "\n"
                        for task in (":compileKotlinLinuxX64", ":compileTestKotlinLinuxX64",
                                     ":linkDebugTestLinuxX64")))
                execution = run.run_native_method(method, lane, binary, os.environ.copy())
                trace, _, counts = run.extract_xml("linux-x64", lane, method,
                                                  lane / "xml" / f"{method}.xml")
                process = run.runtime("linux-x64", log, execution, staged / target_name)
                run.retain_native_method(lane / "producer-bundle", manifest, method, process)
                bundle_hash = run.finish_native_bundle(lane, manifest)
                artifact_sha = {role: run.digest(staged / filename) for role, filename in
                                run.artifact_relative_paths("linux-x64").items()}
                identity = {**run.runtime_identity(process), "method_executions": 1,
                            "dependency_sha256": artifact_sha["target"],
                            "method_process_sha256": hashlib.sha256(json.dumps(
                                [process], sort_keys=True).encode()).hexdigest()}
                method_result = {"method": method, "gradle_exit": 0, "cases": 1,
                                 "log_sha256": run.digest(log),
                                 "execution_log_sha256": run.digest(execution),
                                 "xml_sha256": run.digest(lane / "xml" / f"{method}.xml"),
                                 "process": process}
                result = {"methods": [method_result], "artifact_sha256": artifact_sha,
                          "runtime": identity, "raw_counts": counts,
                          "native_bundle_sha256": bundle_hash}
                receipt = {"runtime": identity, "artifact_sha256": artifact_sha,
                           "artifact_paths": {role: str(staged / filename) for role, filename in
                                              run.artifact_relative_paths("linux-x64").items()},
                           "trace_sha256": run.digest(trace),
                           "counts": {"executed_cases": 1}}
                (lane / "result.json").write_text(json.dumps(result))
                (lane / "receipt.json").write_text(json.dumps(receipt))
            detached = root / "detached-archive"
            shutil.copytree(output, detached)
            (producer / "build").rename(root / "hidden-producer-build")
            (portable / "build").rename(root / "hidden-producer-native-build")
            (root / "producer-cache").rename(root / "hidden-producer-cache")
            self.assertFalse(binary.exists())
            self.assertFalse(cache.exists())
            self.assertFalse((verifier / "build").exists())

            def check_receipt(sealed, captured_trace, cases, captured_identity, artifacts):
                self.assertEqual(sealed["trace_sha256"], run.digest(captured_trace))
                self.assertEqual(captured_identity.runtime, sealed["runtime"])
                self.assertEqual(captured_identity.artifact_sha256, sealed["artifact_sha256"])
                self.assertEqual(sealed["artifact_paths"],
                                 {role: str(path) for role, path in artifacts.items()})
                self.assertEqual(len(cases), 1)

            with patch.multiple(run, ROOT=verifier,
                                PORTABLE=verifier / "tools/numerical/portable",
                                STAGED=verifier / "build/staging-repository/io/github/rubixhacker",
                                MATRIX_METHODS=(method,), MATRIX_METHOD_CASE_COUNTS=(1,)), \
                    patch.object(run, "declared_cases", return_value=[{"id": case_id}]), \
                    patch.object(run, "verify_receipt", side_effect=check_receipt):
                with patch("sys.argv", ["run.py", "--verify-linux-native-existing",
                                        "--output", str(detached)]), redirect_stdout(io.StringIO()) as printed:
                    self.assertEqual(run.main(), 0)
                self.assertEqual(json.loads(printed.getvalue())["status"],
                                 "PASSED_PRODUCER_REPLAY")

                def mutated(label, action, reason):
                    copy = root / label
                    shutil.copytree(detached, copy)
                    action(copy)
                    with self.assertRaisesRegex(run.Rejected, reason):
                        run.verify_linux_native_archive(copy)

                def change_manifest(copy, action):
                    path = copy / "linux-x64/producer-bundle/manifest.json"
                    data = json.loads(path.read_text())
                    action(data)
                    path.write_text(json.dumps(data))
                    result_path = copy / "linux-x64/result.json"
                    recorded = json.loads(result_path.read_text())
                    recorded["native_bundle_sha256"] = run.digest(path)
                    result_path.write_text(json.dumps(recorded))

                mutated("changed-binary", lambda copy: (copy / "linux-x64/producer-bundle/methods" /
                        method / "test.kexe").write_bytes(b"replaced"), "executable bytes differ")
                mutated("changed-klib", lambda copy: (copy / "linux-x64/producer-bundle/inputs" /
                        f"{artifact_sha['target']}.klib").write_bytes(b"replaced"), "compiler input bytes differ")
                mutated("changed-publication", lambda copy: (copy /
                        "linux-x64/producer-bundle/publications" / target_name).write_bytes(b"replaced"),
                        "staged publication bytes differ")

                def change_command(copy):
                    log_path = copy / "linux-x64" / f"native-exec-{method}.log"
                    log_path.write_text(log_path.read_text().replace(name, "portable.PortableMatrixTest.other"))
                    result_path = copy / "linux-x64/result.json"
                    recorded = json.loads(result_path.read_text())
                    recorded["methods"][0]["execution_log_sha256"] = run.digest(log_path)
                    result_path.write_text(json.dumps(recorded))

                mutated("changed-command", change_command, "method command differs")
                def replace_with_symlink(copy):
                    path = copy / "linux-x64/producer-bundle/inputs" / \
                        f"{artifact_sha['target']}.klib"
                    path.unlink()
                    path.symlink_to(root / "hidden-producer-cache")

                mutated("linked-klib", replace_with_symlink, "bundle path is a symlink")
                def link_raw_stream(copy):
                    path = copy / "linux-x64" / f"native-output-{method}.log"
                    path.unlink()
                    path.symlink_to(root / "hidden-producer-cache")

                mutated("linked-raw-stream", link_raw_stream, "bundle path is a symlink")
                mutated("unsafe-manifest-path", lambda copy: change_manifest(copy, lambda data:
                    data["methods"][method]["binary"].update(bundle_path="../escape")),
                    "executable bundle identity differs")
                mutated("wrong-producer-binary", lambda copy: change_manifest(copy, lambda data:
                    data["methods"][method]["binary"].update(original_path="/tmp/other.kexe")),
                    "executable bundle identity differs")
                mutated("wrong-producer-platform", lambda copy: change_manifest(copy, lambda data:
                    data["platform"].update(machine="other")), "bundled process hash differs")
                mutated("wrong-binary-mtime", lambda copy: change_manifest(copy, lambda data:
                    data["methods"][method]["binary"].update(mtime_ns=time.time_ns())),
                    "bundled process hash differs")
                mutated("unsafe-cache-origin", lambda copy: change_manifest(copy, lambda data:
                    data["methods"][method]["compiler_inputs"].update({
                        "/etc/passwd": next(iter(data["methods"][method]["compiler_inputs"].values()))})),
                    "compiler input origin differs")
                mutated("missing-test-event", lambda copy: (copy / "linux-x64" /
                        f"native-output-{method}.log").write_text(
                            (copy / "linux-x64" / f"native-output-{method}.log").read_text().replace(
                                "[  PASSED  ] 1 tests.\n", "")), "event stream is incomplete")
                without_execution = root / "missing-execution"
                shutil.copytree(detached, without_execution)
                (without_execution / "linux-x64" / f"native-exec-{method}.log").unlink()
                with patch("sys.argv", ["run.py", "--verify-linux-native-existing",
                                        "--output", str(without_execution)]), \
                        redirect_stdout(io.StringIO()) as printed:
                    self.assertEqual(run.main(), 1)
                self.assertEqual(json.loads(printed.getvalue())["status"], "FAILED")


class NodeStreamTest(unittest.TestCase):
    def test_direct_wasm_worker_stream_and_process_are_bound(self):
        method = "baselineAngleNegativeRatioRemainsAnIsolatedPhysicalFailure"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lane = root / "node-wasm-wasi"
            lane.mkdir()
            binary = root / "node"
            binary.write_bytes(b"node executable")
            sources = {name: root / "linked" / name for name in
                       (f"{run.WASM_MODULE}.mjs", f"{run.WASM_MODULE}.wasm",
                        "custom-formatters.js")}
            for source in sources.values():
                source.parent.mkdir(exist_ok=True)
                source.write_bytes(source.name.encode())
            output = ("##teamcity[testStarted name='" + method + "']\n"
                      'NUMERICAL_JSON {"kind":"inputs","id":"case"}\n'
                      "##teamcity[testFinished name='" + method + "']\n").encode()
            def worker(command, **kwargs):
                actual = command[8:]
                kwargs["stdout"].write(output)
                (lane / f"native-exec-{method}.log").write_text(
                    f'1 execve("{binary}", {json.dumps(actual)}, 0x0) = 0\n')
                return subprocess.CompletedProcess(command, 0)
            with patch.object(run, "wasm_payload_paths", return_value=sources), \
                    patch.object(run.shutil, "which", side_effect=["/usr/bin/strace", str(binary)]), \
                    patch.object(run.subprocess, "run", side_effect=worker):
                execution = run.run_wasm_method("node-wasm-wasi", method, lane,
                                                os.environ.copy(), 0)
            self.assertEqual(execution, lane / f"native-exec-{method}.log")
            self.assertEqual((lane / f"native-output-{method}.log").read_bytes(), output)
            self.assertEqual((lane / "producer-bundle" / method / "static/runUnitTests.mjs")
                             .read_bytes(), run.WASM_RUNNER)
            self.assertEqual(run.node_stream_xml(method,
                lane / f"native-output-{method}.log", lane / "xml" / f"{method}.xml"), 1)

    def test_failed_wasm_method_keeps_counts_without_process_key(self):
        method = "defaultContactsFrictionSleepAndWake"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged = root / "staged.klib"
            staged.write_bytes(b"staged")
            def fail(*args, **kwargs):
                return subprocess.CompletedProcess(args[0], 1)
            with patch.multiple(run, MATRIX_METHODS=(method,), MATRIX_METHOD_CASE_COUNTS=(3,)), \
                    patch.object(run, "artifacts", return_value={"target": staged}), \
                    patch.object(run, "retain_wasm_publications"), \
                    patch.object(run, "comparison_coverage", return_value={}), \
                    patch.object(run, "declared_cases", return_value=[]), \
                    patch.object(run, "method_command", return_value=(["gradle"], None)), \
                    patch.object(run.subprocess, "run", side_effect=fail):
                result = run.execute("node-wasm-wasi", root, "a" * 40, "b" * 64, [])
            self.assertEqual(result["failed_methods"], [method])
            self.assertEqual(result["completed_methods"], 0)
            self.assertEqual(result["executed_cases"], 0)
            self.assertNotEqual(result["reason"], "'process'")

    def test_wasm_replay_rejects_linked_trace_and_later_case_with_matching_bytes(self):
        cases = [{"id": "first-case"}, {"id": "later-case"}]
        commit, source = "a" * 40, "b" * 64
        for relative in ("trace.jsonl", "cases/later-case.jsonl"):
            for kind in ("symlink", "hardlink"):
                with self.subTest(relative=relative, kind=kind), \
                        tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    output = root / "archive"
                    lane = output / "node-wasm-js"
                    (lane / "cases").mkdir(parents=True)
                    log = output / "publication.log"
                    log.write_bytes(b"publication\n")
                    (output / "publication.json").write_text(json.dumps({
                        "candidate_commit": commit, "source_sha256": source,
                        "publication_log_sha256": run.digest(log)}))
                    payload = b'{"kind":"inputs","id":"first-case"}\n'
                    trace = lane / "trace.jsonl"
                    trace.write_bytes(payload)
                    for case in cases:
                        (lane / "cases" / f'{case["id"]}.jsonl').write_bytes(payload)
                    receipt = {"trace_sha256": run.digest(trace), "cases_sha256": {
                        case["id"]: run.digest(lane / "cases" / f'{case["id"]}.jsonl')
                        for case in cases}}
                    (lane / "receipt.json").write_text(json.dumps(receipt))
                    (lane / "result.json").write_text(json.dumps({
                        "candidate_commit": commit, "source_sha256": source,
                        "executed_cases": len(cases), "methods": [], "failed_methods": []}))
                    target = lane / relative
                    external = root / "same-recorded-bytes.jsonl"
                    external.write_bytes(target.read_bytes())
                    target.unlink()
                    if kind == "symlink":
                        target.symlink_to(external)
                    else:
                        os.link(external, target)
                    self.assertEqual(run.digest(target), receipt["trace_sha256"] if
                                     relative == "trace.jsonl" else
                                     receipt["cases_sha256"]["later-case"])
                    reason = ("native bundle path is a symlink" if kind == "symlink" else
                              "native bundle file has an external hard link")
                    with patch.object(run, "clean_identity", return_value=(commit, source)), \
                            patch.object(run, "declared_cases", return_value=cases), \
                            self.assertRaisesRegex(run.Rejected, reason):
                        run.verify_wasm_archive(output, "node-wasm-js")

    def _check_relocated_wasm_method(self, host):
        archive = os.environ.get("DYN4K_WASM_ARCHIVE")
        baseline = os.environ.get("DYN4K_WASM_BASELINE")
        attestation = os.environ.get("DYN4K_WASM_ATTESTATION")
        if not archive:
            self.skipTest("set DYN4K_WASM_ARCHIVE to a retained complete archive")
        if not baseline or not attestation:
            self.skipTest("set DYN4K_WASM_BASELINE and DYN4K_WASM_ATTESTATION")
        import baseline_capture
        import prospective_compare
        import receipt
        method = run.MATRIX_METHODS[0]
        source = Path(archive) / host
        captured = json.loads(run._bundle_file(source, "result.json").read_text())
        item = captured["methods"][0]
        self.assertEqual(item["method"], method)
        process = item["process"]
        self.assertFalse(Path(process["worker_command"][1]).exists())
        relatives = [f"gradle-{method}.log", f"native-exec-{method}.log",
                     f"native-output-{method}.log", f"xml/{method}.xml",
                     f"producer-bundle/{method}/static/runUnitTests.mjs"]
        relatives += [f"producer-bundle/{method}/kotlin/{name}"
                      for name in run.wasm_payload_paths(host)]
        case = declared_cases()[0]
        relatives += ["receipt.json", f"cases/{case['id']}.jsonl"]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            lane = output / host
            for relative in relatives:
                original = run._bundle_file(source, relative)
                copied = lane / relative
                copied.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, copied)
                self.assertEqual(run.digest(copied), run.digest(original))
            for relative in ("publication.json", "publication.log"):
                original = run._bundle_file(source.parent, relative)
                shutil.copy2(original, output / relative)
                self.assertEqual(run.digest(output / relative), run.digest(original))
            shutil.copy2(lane / f"cases/{case['id']}.jsonl", lane / "trace.jsonl")
            proof = run.runtime(host, lane / f"gradle-{method}.log",
                                lane / f"native-exec-{method}.log",
                                run.artifacts(host)["target"])
            self.assertEqual(proof, process)
            original_execution = (lane / f"native-exec-{method}.log").read_text()
            (lane / f"native-exec-{method}.log").write_text(
                original_execution.replace(process["worker_command"][1],
                                           process["worker_command"][1] + ".changed"))
            with self.assertRaisesRegex(run.Rejected, "direct Wasm worker command differs"):
                run.runtime(host, lane / f"gradle-{method}.log",
                            lane / f"native-exec-{method}.log",
                            run.artifacts(host)["target"])
            (lane / f"native-exec-{method}.log").write_text(original_execution)
            runner = lane / f"producer-bundle/{method}/static/runUnitTests.mjs"
            original_runner = runner.read_bytes()
            runner.write_bytes(original_runner + b"\n")
            with self.assertRaisesRegex(run.Rejected, "direct Wasm method or runner identity differs"):
                run.runtime(host, lane / f"gradle-{method}.log",
                            lane / f"native-exec-{method}.log",
                            run.artifacts(host)["target"])
            runner.write_bytes(original_runner)

            def check_bounded_identity(_receipt, _publication, _commit, _source,
                                       _artifacts, runtime_proof):
                expected = hashlib.sha256(json.dumps([process], sort_keys=True).encode()).hexdigest()
                self.assertEqual(runtime_proof["method_process_sha256"], expected)
                self.assertEqual(runtime_proof["method_executions"], 1)
                self.assertEqual(runtime_proof["executable_sha256"], process["executable_sha256"])

            with patch.object(run, "MATRIX_METHODS", (method,)), \
                    patch.object(run, "clean_identity", return_value=(
                        captured["candidate_commit"], captured["source_sha256"])), \
                    patch.object(prospective_compare, "declared_cases", return_value=[case]), \
                    patch.object(baseline_capture, "verify_attestation", return_value={
                        "case_map_sha256": "bounded", "source_sha256": "bounded"}), \
                    patch.object(baseline_capture, "fixture_source_sha256",
                                 return_value="bounded"), \
                    patch.object(prospective_compare, "verify_baseline_manifest"), \
                    patch.object(prospective_compare, "verify_baseline_bytes"), \
                    patch.object(prospective_compare, "verify_policy_catalog"), \
                    patch.object(prospective_compare, "verify_candidate_identity",
                                 side_effect=check_bounded_identity), \
                    patch.object(receipt, "verify"), \
                    patch.object(baseline_capture, "verify_case_slices"):
                comparison = prospective_compare.compare_host(
                    Path(baseline), lane, [], Path(attestation))
            self.assertEqual(comparison["cases"], 1)
            self.assertEqual(comparison["results"][0]["case_id"], case["id"])
            self.assertEqual(comparison["results"][0]["status"],
                             "PASSED_NUMERICAL_POLICY")
            self.assertEqual(comparison["results"][0]["qualification"], "UNPASSED")

    def test_relocated_wasm_js_method_preserves_recorded_process_proof(self):
        self._check_relocated_wasm_method("node-wasm-js")

    def test_relocated_wasm_wasi_method_preserves_recorded_process_proof(self):
        self._check_relocated_wasm_method("node-wasm-wasi")

    def test_retained_node_inputs_replay_after_producer_files_are_removed(self):
        method = "geometryCollisionBoundaryAndScale"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            producer = root / "producer"
            bundle = producer / "build/kotlin/dyn4k-portable-numerical-consumer-test.js"
            core = bundle.with_name("dyn4k-dyn4k-core.js")
            artifact = producer / "build/staging/dyn4k-core-js.klib"
            modules = producer / "cache/node_modules"
            runner = {index: modules / name for index, name in
                      ((2, "source-map-support/register.js"), (3, "mocha/bin/mocha.js"),
                       (8, "kotlin-web-helpers/dist/mocha-kotlin-reporter.js"),
                       (10, "kotlin-web-helpers/dist/kotlin-test-nodejs-runner.js"))}
            for path in (bundle, core, artifact, *runner.values()):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(path.name.encode())
            binary = root / "selected-node"
            binary.write_bytes(b"selected Node binary")
            command = [str(binary), "--require", str(runner[2]), str(runner[3]),
                       str(bundle), "--include", f"portable.PortableMatrixTest.{method}",
                       "--reporter", str(runner[8]), "--require", str(runner[10]),
                       "--timeout", "90m"]
            process = {"worker_command": command, "executable_sha256": run.digest(binary),
                       "dependency": {"artifact": str(artifact),
                                      "artifact_sha256": run.digest(artifact)},
                       "bundle": {"command_bundle": str(bundle),
                                  "payload_sha256": {str(bundle): run.digest(bundle),
                                                     str(core): run.digest(core)}},
                       "runner_module_sha256": {str(path): run.digest(path)
                                                for path in runner.values()}}
            lane = root / "archive/node-js"
            lane.mkdir(parents=True)
            manifest_sha = run.retain_node_bundle(lane, method, process)
            selected = {"node": run.digest(binary), "artifact": run.digest(artifact),
                        "bundle": run.digest(bundle), "core": run.digest(core)}
            shutil.rmtree(producer)
            frozen = run.load_node_bundle(lane, method, process, manifest_sha, binary, selected)
            self.assertEqual(run.digest(frozen["artifact"]), selected["artifact"])
            self.assertEqual(len(frozen["files"]), 7)
            with self.assertRaisesRegex(run.Rejected, "externally selected Node core hash differs"):
                run.load_node_bundle(lane, method, process, manifest_sha, binary,
                                     {**selected, "core": "0" * 64})

    def test_direct_stream_rejects_other_or_duplicate_method_events(self):
        method = "geometryCollisionBoundaryAndScale"
        start = "##teamcity[testStarted name='geometryCollisionBoundaryAndScale']\n"
        finish = "##teamcity[testFinished name='geometryCollisionBoundaryAndScale']\n"
        row = 'NUMERICAL_JSON {"kind":"inputs","id":"geometry-boundary-s0-o0-d0"}\n'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "raw.log"
            for index, events in enumerate((start + row + finish + "##teamcity[testStarted name='laterJob']\n",
                           "##teamcity[testStarted name='otherMethod']\n" + start + row + finish,
                           start + row + finish + "##teamcity[testFinished name='otherMethod']\n",
                           start + start + row + finish,
                           start + row + finish + finish,
                           start + row + finish + "##teamcity[testFailed name='otherMethod']\n",
                           start + row + finish + "##teamcity[testIgnored name='otherMethod']\n",
                           start + row,
                           row + finish)):
                with self.subTest(events=events):
                    source.write_text(events)
                    with self.assertRaises(run.Rejected):
                        run.node_stream_xml(method, source, Path(directory) / f"report-{index}.xml", create=True)

    def test_full_execute_passes_direct_xml_even_when_gradle_xml_exists(self):
        method = "geometryCollisionBoundaryAndScale"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lane = root / "capture/node-js"
            direct = lane / "xml" / f"{method}.xml"
            stale = root / "build/test-results/jsNodeTest/TEST-portable.PortableMatrixTest.xml"
            stale.parent.mkdir(parents=True)
            stale.write_text("stale")
            staged = root / "staged.klib"
            staged.write_text("staged")
            execution = lane / f"native-exec-{method}.log"
            def direct_worker(*args):
                direct.parent.mkdir(parents=True)
                direct.write_text("direct")
                execution.write_text("worker")
                return execution
            class ReachedDirectXml(Exception):
                pass
            def inspect_xml(host, output, selected, source):
                self.assertEqual(source, direct)
                raise ReachedDirectXml
            with patch.multiple(run, PORTABLE=root, MATRIX_METHODS=(method,)), \
                    patch.object(run, "artifacts", return_value={"target": staged}), \
                    patch.object(run, "comparison_coverage", return_value={}), \
                    patch.object(run, "declared_cases", return_value=[]), \
                    patch.object(run, "method_command", return_value=(["true"], None)), \
                    patch.object(run, "run_node_method", side_effect=direct_worker), \
                    patch.object(run.time, "time_ns", return_value=0), \
                    patch.object(run, "extract_xml", side_effect=inspect_xml):
                with self.assertRaises(ReachedDirectXml):
                    run.execute("node-js", root / "capture", "a" * 40, "b" * 64, [])

    def test_focused_capture_rechecks_source_after_worker(self):
        method = "geometryCollisionBoundaryAndScale"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged = root / "staged.klib"
            staged.write_bytes(b"staged")
            trace = root / "trace.jsonl"
            trace.write_text("rows")
            (root / "exec.log").write_text("worker")
            counts = {"completed_cases": 1, "states": 1}
            attributes = {"name": "portable.PortableMatrixTest", "tests": "1",
                          "skipped": "0", "failures": "0", "errors": "0"}
            def focused_worker(selected, lane, env, modules):
                xml = lane / "xml" / f"{selected}.xml"
                xml.parent.mkdir(parents=True)
                xml.write_text("report")
                (lane / f"native-output-{selected}.log").write_text("output")
                return root / "exec.log"
            def focused_extract(host, lane, selected, xml):
                return trace, attributes, counts
            with patch.object(run, "clean_identity", side_effect=[("a" * 40, "b" * 64),
                                                                   ("a" * 40, "c" * 64)]), \
                    patch.object(run, "artifacts", return_value={"target": staged}), \
                    patch.object(run, "method_command", return_value=(["true"], None)), \
                    patch.object(run, "run_node_method", side_effect=focused_worker), \
                    patch.object(run, "extract_xml", side_effect=focused_extract), \
                    patch.object(run, "runtime", return_value={}), \
                    patch.object(run, "method_case_ids", return_value=["case"]), \
                    patch("baseline_capture.verify_xml_trace"), \
                    patch("baseline_capture.verify_case_slices", return_value={"case": "hash"}):
                with self.assertRaisesRegex(run.Rejected, "source identity differs"):
                    run.capture_node_method(root / "capture", method, root / "modules")
            self.assertFalse((root / "capture/result.json").exists())

    def test_file_backed_node_stream_replays_and_rejects_failed_test(self):
        method = "defaultContactsFrictionSleepAndWake"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "node-output.log"
            xml = Path(directory) / "method.xml"
            source.write_text(
                "##teamcity[testStarted name='defaultContactsFrictionSleepAndWake' flowId='7']\n"
                'NUMERICAL_JSON {"kind":"inputs","id":"contacts-default-30"}\n'
                'NUMERICAL_JSON {"kind":"case-end","id":"contacts-default-30"}\n'
                "##teamcity[testFinished name='defaultContactsFrictionSleepAndWake' duration='1' flowId='7']\n")
            self.assertEqual(run.node_stream_xml(method, source, xml, create=True), 2)
            self.assertEqual(run.node_stream_xml(method, source, xml), 2)
            xml.write_bytes(xml.read_bytes().replace(b'contacts-default-30', b'contacts-default-60', 1))
            with self.assertRaisesRegex(run.Rejected, "Node XML differs"):
                run.node_stream_xml(method, source, xml)
            source.write_text(source.read_text().replace("testFinished", "testFailed"))
            with self.assertRaisesRegex(run.Rejected, "Node test failed or skipped"):
                run.node_stream_xml(method, source, Path(directory) / "failed.xml", create=True)


if __name__ == "__main__":
    unittest.main()
