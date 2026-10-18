import hashlib
import json
import os
import subprocess
import tempfile
import time
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
            command, execution_log = run.method_command("jvm8", method, lane)
            self.assertEqual(command[:7], ["/usr/bin/strace", "-f", "-s", "65535",
                                           "-e", "trace=process,openat", "-o"])
            self.assertEqual(command[7], str(execution_log))
            self.assertEqual(execution_log, lane / f"native-exec-{method}.log")
            self.assertEqual(command.count("-Pkotlin.compiler.execution.strategy=in-process"), 1)
            self.assertIn(f"portable.PortableMatrixTest.{method}", command)
            self.assertIn("-PportableJvm8=true", command)
            self.assertIn("-Dorg.gradle.java.installations.paths=/tmp/dyn4k-tools/jdk8", command)
            self.assertIn("--init-script", command)
            ordinary, ordinary_log = run.method_command("jvm", method, lane)
            self.assertIsNone(ordinary_log)
            self.assertNotIn("-Pkotlin.compiler.execution.strategy=in-process", ordinary)
            native, native_log = run.method_command("linux-x64", method, lane)
            self.assertIsNone(native_log)
            self.assertIn(":linkDebugTestLinuxX64", native)
            self.assertNotIn("--tests", native)
            self.assertNotIn("linuxX64Test", native)
            for host in ("node-js", "node-wasm-js", "node-wasm-wasi"):
                traced, trace_log = run.method_command(host, method, lane)
                self.assertEqual(traced[5], "trace=execve")
                self.assertEqual(trace_log, lane / f"native-exec-{method}.log")
                self.assertEqual(traced.count("-Pkotlin.compiler.execution.strategy=in-process"), 1)

    def test_traced_method_rejects_missing_tracer_and_unknown_method(self):
        with patch.object(run.shutil, "which", return_value=None):
            with self.assertRaisesRegex(run.Rejected, "strace is unavailable"):
                run.method_command("jvm8", "freeMotionForcesDampingAndRestitution",
                                   Path("/tmp/unused"))
        with self.assertRaisesRegex(run.Rejected, "unknown numerical matrix method"):
            run.method_command("jvm8", "unrecorded", Path("/tmp/unused"))

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


if __name__ == "__main__":
    unittest.main()
