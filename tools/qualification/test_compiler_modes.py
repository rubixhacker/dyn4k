import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import compiler_modes


class CompilerModesTest(unittest.TestCase):
    def test_public_native_replay_rejects_resealed_debug_compile_log(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "staged").mkdir()
            marker = output / "staged/marker"
            marker.write_bytes(b"metadata")
            (output / "elf").mkdir()
            artifacts = {}
            for name in ("dyn4k-core-test-elf", "dyn4k-test-elf", "staged-consumer-elf"):
                path = output / "elf" / (name + ".kexe")
                path.write_bytes(b"\x7fELF" + name.encode())
                artifacts[name] = compiler_modes.record_file(output, path)
            (output / "logs").mkdir()

            def process(name, command, raw):
                log = output / "logs" / name
                log.write_text(raw)
                return {"command": command, "exit_code": 0, "log": str(log),
                        "log_sha256": compiler_modes.digest(log)}

            manifest = {"source_tree_sha256": "fixture", "cases": []}
            candidate = compiler_modes.subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=compiler_modes.ROOT, text=True).strip()
            tree = compiler_modes.subprocess.check_output(
                ["git", "rev-parse", "HEAD^{tree}"], cwd=compiler_modes.ROOT,
                text=True).strip()
            consumer_elf = output / artifacts["staged-consumer-elf"]["path"]
            consumer = {"count": 4, "elf": artifacts["staged-consumer-elf"], "source": {},
                        "compile": process("consumer-compile.log",
                            [str(compiler_modes.ROOT / "gradlew"), "-p",
                             str(output / "external-native-consumer"), "--offline", "--no-daemon",
                             "--max-workers=1", "--rerun-tasks", "--console=plain",
                             "linkReleaseTestLinuxX64"],
                            "> Task :linkReleaseTestLinuxX64\nBUILD SUCCESSFUL in 1s\n"),
                        "process": process("consumer-test.log", [str(consumer_elf)], "four cases\n")}
            receipt = {"candidate_sha": candidate, "tree_sha": tree,
                       "source_tree_sha256": "fixture",
                       "manifest_sha256": compiler_modes.full_corpus.canonical_digest(manifest),
                       "target": "linuxX64", "mode": "optimized", "status": "PASSED",
                       "staged_files": {"staged/marker": compiler_modes.digest(marker)},
                       "artifacts": artifacts, "flags": ["linkReleaseTestLinuxX64"],
                       "runtime": {"host": "fixture"},
                       "processes": [process("build.log", ["gradlew"], "build\n")],
                       "reports": [{"module": module, "count": 0,
                                    "process": process(module + ".log", ["test"], "zero\n")}
                                   for module in compiler_modes.MODULES],
                       "consumers": [consumer]}
            receipt_path = output / "receipt.json"
            receipt_path.write_text(json.dumps(receipt))
            with (patch.object(compiler_modes, "checked_source", return_value=manifest),
                  patch.object(compiler_modes, "native_environment",
                               return_value={"host": "fixture"}),
                  patch.object(compiler_modes, "build_evidence_problems", return_value=[]),
                  patch.object(compiler_modes, "native_cases",
                               side_effect=lambda log, expected: len(expected))):
                self.assertEqual("PASSED", compiler_modes.replay(
                    output, candidate, "linuxX64", "optimized")["status"])
                debug_log = output / "logs/consumer-debug.log"
                debug_log.write_text("> Task :linkDebugTestLinuxX64\nBUILD SUCCESSFUL in 1s\n")
                consumer["compile"]["log"] = str(debug_log)
                consumer["compile"]["log_sha256"] = compiler_modes.digest(debug_log)
                receipt_path.write_text(json.dumps(receipt))
                result = compiler_modes.replay(output, candidate, "linuxX64", "optimized")
                self.assertIn("Native staged consumer link log differs", result["problems"])
                compile_log = output / "logs/consumer-compile.log"
                compile_log.write_text(debug_log.read_text())
                consumer["compile"]["log"] = str(compile_log)
                consumer["compile"]["log_sha256"] = compiler_modes.digest(compile_log)
                receipt_path.write_text(json.dumps(receipt))
                result = compiler_modes.replay(output, candidate, "linuxX64", "optimized")
                self.assertIn("Native staged consumer link log differs", result["problems"])
                compile_log.write_text("> Task :linkReleaseTestLinuxX64\n")
                consumer["compile"]["log_sha256"] = compiler_modes.digest(compile_log)
                receipt_path.write_text(json.dumps(receipt))
                result = compiler_modes.replay(output, candidate, "linuxX64", "optimized")
                self.assertIn("Native staged consumer link log differs", result["problems"])

    def test_public_jvm_replay_survives_missing_build_dirs_and_checks_test_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "logs").mkdir()
            (output / "xml").mkdir()
            (output / "staged").mkdir()
            artifacts = {}
            for module in compiler_modes.MODULES:
                archive = output / "staged" / (module + ".jar")
                archive.write_bytes(module.encode())
                artifacts[module] = compiler_modes.record_file(output, archive)
            compiled_tests = {}
            for module in compiler_modes.MODULES:
                directory_path = output / "test-classes" / module / "kotlin"
                directory_path.mkdir(parents=True)
                binary = directory_path / "example" / (module + ".class")
                binary.parent.mkdir()
                binary.write_bytes(b"compiled " + module.encode())
                compiled_tests[module] = [{"source": f"{module}/build/classes/kotlin/jvm/test",
                                           "path": directory_path.relative_to(output).as_posix(),
                                           "files": {binary.relative_to(directory_path).as_posix():
                                                     compiler_modes.digest(binary)}}]

            def process(name, command):
                log = output / "logs" / name
                log.write_text("completed\n")
                return {"command": command, "exit_code": 0, "log": str(log),
                        "log_sha256": compiler_modes.digest(log)}

            manifest = {"source_tree_sha256": "fixture", "original_mappings": [],
                        "cases": [{"module": module, "hosts": ["jvm"],
                                   "classname": f"example.{module}", "method": "case"}
                                  for module in compiler_modes.MODULES]}
            candidate = compiler_modes.subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=compiler_modes.ROOT, text=True).strip()
            tree = compiler_modes.subprocess.check_output(
                ["git", "rev-parse", "HEAD^{tree}"], cwd=compiler_modes.ROOT,
                text=True).strip()
            reports = []
            for runtime in compiler_modes.JDK:
                for module in compiler_modes.MODULES:
                    xml = output / "xml" / f"{module}-{runtime}.xml"
                    xml.write_text("one case\n")
                    classpath = [output / compiled_tests[module][0]["path"],
                                 output / compiled_tests["dyn4k-core"][0]["path"],
                                 output / artifacts["dyn4k-core"]["path"],
                                 output / artifacts["dyn4k"]["path"],
                                 output / "helper-classes"]
                    command = [str(compiler_modes.JDK[runtime] / "bin/java"), "-cp",
                               ":".join(map(str, classpath)), "PinnedCorpusReport", str(xml),
                               f"example.{module}"]
                    reports.append({"kind": "full-common", "module": module,
                                    "runtime": runtime, "count": 1,
                                    "file": compiler_modes.record_file(output, xml),
                                    "process": process(f"{module}-{runtime}.log", command)})
                xml = output / "xml" / f"original-{runtime}.xml"
                xml.write_text("one original case\n")
                command = [str(compiler_modes.JDK[runtime] / "bin/java"), "-cp",
                           ":".join(map(str, [output / "original-classes",
                                               output / artifacts["dyn4k-core"]["path"],
                                               output / "helper-classes"])),
                           "PinnedCorpusReport", str(xml), "example.Original"]
                reports.append({"kind": "unchanged-java", "runtime": runtime, "count": 1,
                                "file": compiler_modes.record_file(output, xml),
                                "process": process(f"original-{runtime}.log", command)})
            receipt = {"candidate_sha": candidate, "tree_sha": tree,
                       "source_tree_sha256": "fixture",
                       "manifest_sha256": compiler_modes.full_corpus.canonical_digest(manifest),
                       "target": "jvm", "mode": "default", "status": "PASSED", "flags": [],
                       "artifacts": artifacts, "compiled_tests": compiled_tests,
                       "staged_files": {item["path"]: item["sha256"]
                                        for item in artifacts.values()},
                       "dependencies": {},
                       "runtimes": {runtime: {"id": "pinned"}
                                    for runtime in compiler_modes.JDK},
                       "original_compile": {}, "reports": reports,
                       "processes": [process("build.log", ["gradlew"]),
                                     process("helper.log", ["javac"])],
                       "consumers": [{"runtime": runtime, "classes": [], "source": {}}
                                     for runtime in compiler_modes.JDK]}
            receipt_path = output / "receipt.json"
            receipt_path.write_text(json.dumps(receipt))
            empty_author_root = output / "empty-author-root"
            empty_author_root.mkdir()
            with (patch.object(compiler_modes, "checked_source", return_value=manifest),
                  patch.object(compiler_modes, "ROOT", empty_author_root),
                  patch.object(compiler_modes.subprocess, "check_output",
                               return_value=tree + "\n"),
                  patch.object(compiler_modes, "jvm_dependencies", return_value=[]),
                  patch.object(compiler_modes, "original_classes",
                               return_value=([], ["example.Original"])),
                  patch.object(compiler_modes, "original_compile_evidence_problems",
                               return_value=[]),
                  patch.object(compiler_modes, "jvm_consumer_evidence_problems",
                               return_value=[]),
                  patch.object(compiler_modes, "verify_xml", return_value=1),
                  patch.object(compiler_modes, "verify_original_xml", return_value=1),
                  patch.object(compiler_modes, "runtime_identity",
                               return_value={"id": "pinned"}),
                  patch.object(compiler_modes, "build_evidence_problems", return_value=[])):
                result = compiler_modes.replay(output, candidate, "jvm", "default")
                self.assertEqual("PASSED", result["status"], result["problems"])
                reports[0]["process"]["command"][2] = "/other/tests:" + reports[0]["process"]["command"][2]
                receipt_path.write_text(json.dumps(receipt))
                self.assertEqual("UNPASSED", compiler_modes.replay(
                    output, candidate, "jvm", "default")["status"])
                reports[0]["process"]["command"][2] = reports[0]["process"]["command"][2].removeprefix("/other/tests:")
                receipt_path.write_text(json.dumps(receipt))
                binary = output / compiled_tests["dyn4k-core"][0]["path"] / "example/dyn4k-core.class"
                binary.write_bytes(b"altered test bytecode")
                self.assertEqual("UNPASSED", compiler_modes.replay(
                    output, candidate, "jvm", "default")["status"])

    def test_compiled_test_snapshot_survives_author_build_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            author = base / "author"
            output = base / "receipt"
            output.mkdir()
            for module in compiler_modes.MODULES:
                binary = author / module / "build/classes/kotlin/jvm/test/example/Test.class"
                binary.parent.mkdir(parents=True)
                binary.write_bytes(module.encode())
            with patch.object(compiler_modes, "ROOT", author):
                snapshot = compiler_modes.snapshot_jvm_test_classes(output)
            compiler_modes.shutil.rmtree(author)
            self.assertEqual([], compiler_modes.compiled_test_evidence_problems(
                output, snapshot))

    def test_mode_flags_are_explicit(self):
        self.assertEqual([], compiler_modes.jvm_flags("default"))
        self.assertEqual(["-Xno-optimize"], compiler_modes.jvm_flags("no-optimize"))
        with self.assertRaises(ValueError):
            compiler_modes.jvm_flags("-Xint")
        self.assertEqual("JVM compiler flags :dyn4k-core: [-Xno-optimize]",
                         compiler_modes.gradle_flag_line("dyn4k-core", ["-Xno-optimize"]))

    def test_full_case_accounting_rejects_missing_extra_and_skipped(self):
        expected = {("example.Core", "first"), ("example.Core", "second")}
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "TEST-Core.xml"
            report.write_text('<testsuite tests="2" failures="0" errors="0" skipped="0" time="1">'
                              '<testcase classname="example.Core" name="first" time="0"/>'
                              '<testcase classname="example.Core" name="second" time="0"/>'
                              '</testsuite>')
            self.assertEqual(2, compiler_modes.verify_xml([report], expected))
            report.write_text(report.read_text().replace('name="second"', 'name="extra"'))
            with self.assertRaises(ValueError):
                compiler_modes.verify_xml([report], expected)
            report.write_text(report.read_text().replace('name="extra"', 'name="second"')
                              .replace('skipped="0"', 'skipped="1"'))
            with self.assertRaises(ValueError):
                compiler_modes.verify_xml([report], expected)

    def test_replay_rejects_wrong_mode_and_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "core.jar"
            archive.write_bytes(b"compiled default")
            receipt = {"mode": "default", "artifacts": {"core": {
                "path": "core.jar", "sha256": compiler_modes.digest(archive)}}}
            (root / "receipt.json").write_text(json.dumps(receipt))
            self.assertEqual([], compiler_modes.check_artifacts(root, receipt, "default"))
            self.assertTrue(compiler_modes.check_artifacts(root, receipt, "no-optimize"))
            archive.write_bytes(b"compiled no-optimize")
            self.assertTrue(compiler_modes.check_artifacts(root, receipt, "default"))

    def test_native_log_requires_every_reported_case(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "native.log"
            log.write_text("[ RUN      ] example.Core.first\n"
                           "[       OK ] example.Core.first (0 ms)\n"
                           "[  PASSED  ] 1 tests.\n")
            self.assertEqual(1, compiler_modes.native_cases(log, {"example.Core.first"}))
            with self.assertRaises(ValueError):
                compiler_modes.native_cases(log, {"example.Core.second"})
            log.write_text(log.read_text().replace("1 tests", "2 tests"))
            with self.assertRaises(ValueError):
                compiler_modes.native_cases(log, {"example.Core.first"})

    def test_unchanged_java_identity_count_detects_wrong_method(self):
        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory) / "original.xml"
            xml.write_text('<testsuite tests="2" failures="0" errors="0" skipped="0">'
                           '<testcase classname="example.Core" name="first"/>'
                           '<testcase classname="example.Core" name="second[variant@abc]"/>'
                           '</testsuite>')
            rows = [{"original": "example.Core#first"},
                    {"original": "example.Core#second[variant]"}]
            self.assertEqual(2, compiler_modes.verify_original_xml(xml, rows))
            xml.write_text(xml.read_text().replace('name="first"', 'name="wrong"'))
            with self.assertRaises(ValueError):
                compiler_modes.verify_original_xml(xml, rows)

    def test_build_log_rejects_forged_native_configuration(self):
        tasks = compiler_modes.native_build_tasks("debug")
        process = {"command": ["gradlew", "--offline", "--no-daemon", "--max-workers=1",
                               "--rerun-tasks", "--console=plain", *tasks], "exit_code": 0}
        raw = "\n".join(f"> Task {task}" for task in tasks) + "\nBUILD SUCCESSFUL\n"
        self.assertEqual([], compiler_modes.build_evidence_problems(process, raw,
                                                                     "linuxX64", "debug"))
        self.assertTrue(compiler_modes.build_evidence_problems(process, raw,
                                                                 "linuxX64", "optimized"))

    def test_build_log_rejects_forged_jvm_flag(self):
        tasks = compiler_modes.jvm_build_tasks()
        process = {"command": ["gradlew", "--offline", "--no-daemon", "--max-workers=1",
                               "--rerun-tasks", "--console=plain", "-PjvmCompilerMode=no-optimize",
                               *tasks], "exit_code": 0}
        raw = "\n".join(f"> Task {task}" for task in tasks) + "\nBUILD SUCCESSFUL\n"
        for module in compiler_modes.MODULES:
            raw += f"> Task :{module}:compileKotlinJvm\n"
            raw += compiler_modes.gradle_flag_line(module, ["-Xno-optimize"]) + "\n"
        self.assertEqual([], compiler_modes.build_evidence_problems(process, raw,
                                                                     "jvm", "no-optimize"))
        self.assertTrue(compiler_modes.build_evidence_problems(process, raw, "jvm", "default"))

    def test_native_consumer_replay_rejects_resealed_mode_and_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            executable = output / "elf/staged-consumer-optimized.kexe"
            executable.parent.mkdir()
            executable.write_bytes(b"\x7fELF retained consumer")
            artifact = {"path": "elf/staged-consumer-optimized.kexe",
                        "sha256": compiler_modes.digest(executable)}
            project = output / "external-native-consumer"
            compile_log = output / "logs/consumer-compile.log"
            compile_log.parent.mkdir()
            compile_log.write_text("> Task :linkReleaseTestLinuxX64\nBUILD SUCCESSFUL in 1s\n")
            consumer = {
                "elf": artifact,
                "compile": {"command": [str(compiler_modes.ROOT / "gradlew"), "-p", str(project),
                                        "--offline", "--no-daemon", "--max-workers=1",
                                        "--rerun-tasks", "--console=plain",
                                        "linkReleaseTestLinuxX64"],
                            "exit_code": 0, "log": str(compile_log),
                            "log_sha256": compiler_modes.digest(compile_log)},
                "process": {"command": [str(executable)]},
            }
            self.assertEqual([], compiler_modes.native_consumer_command_problems(
                output, consumer, artifact, "optimized"))
            consumer["compile"]["command"][-1] = "linkDebugTestLinuxX64"
            self.assertTrue(compiler_modes.native_consumer_command_problems(
                output, consumer, artifact, "optimized"))
            consumer["compile"]["command"][-1] = "linkReleaseTestLinuxX64"
            consumer["process"]["command"] = ["/bin/false"]
            self.assertTrue(compiler_modes.native_consumer_command_problems(
                output, consumer, artifact, "optimized"))

    def test_original_javac_replay_rejects_resealed_command_exit_and_log(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            log = output / "compile-originals.log"
            stdout = output / "compile-originals.stdout"
            stderr = output / "compile-originals.stderr"
            stdout.write_bytes(b"")
            stderr.write_bytes(b"javac warning\n")
            log.write_bytes(stdout.read_bytes() + stderr.read_bytes())
            command = ["/pinned/jdk8/bin/javac", "@original-sources.args"]
            process = {"command": command.copy(), "exit_code": 0,
                       "log": str(log), "log_sha256": compiler_modes.digest(log),
                       "stdout": str(stdout), "stdout_sha256": compiler_modes.digest(stdout),
                       "stderr": str(stderr), "stderr_sha256": compiler_modes.digest(stderr)}
            self.assertEqual([], compiler_modes.compile_process_problems(
                process, command, log, split_streams=True))
            process["command"] = ["/other/javac", "@original-sources.args"]
            self.assertTrue(compiler_modes.compile_process_problems(
                process, command, log, split_streams=True))
            process["command"] = command
            process["exit_code"] = 1
            self.assertTrue(compiler_modes.compile_process_problems(
                process, command, log, split_streams=True))
            process["exit_code"] = 0
            log.write_bytes(b"resealed log\n")
            process["log_sha256"] = compiler_modes.digest(log)
            self.assertTrue(compiler_modes.compile_process_problems(
                process, command, log, split_streams=True))

    def test_original_javac_replay_binds_all_199_sources_and_staged_jar(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            archive = output / "staged/core.jar"
            dependency = output / "dependency.jar"
            sources, _ = compiler_modes.original_classes()
            self.assertEqual(199, len(sources))
            argfile = output / "original-sources.args"
            argfile.write_text("\n".join('"' + str(path) + '"' for path in sources))
            log = output / "logs/compile-originals.log"
            log.parent.mkdir()
            stdout = log.with_suffix(".stdout")
            stderr = log.with_suffix(".stderr")
            for path in (log, stdout, stderr):
                path.write_bytes(b"")
            command = [str(compiler_modes.JDK["java8"] / "bin/javac"),
                       "-source", "8", "-target", "8", "-encoding", "UTF-8",
                       "-cp", str(archive) + ":" + str(dependency), "-d",
                       str(output / "original-classes"), "@" + str(argfile)]
            process = {"command": command, "exit_code": 0, "log": str(log),
                       "log_sha256": compiler_modes.digest(log),
                       "stdout": str(stdout), "stdout_sha256": compiler_modes.digest(stdout),
                       "stderr": str(stderr), "stderr_sha256": compiler_modes.digest(stderr)}
            record = {"process": process, "argfile": compiler_modes.record_file(output, argfile),
                      "source_count": 199}
            self.assertEqual([], compiler_modes.original_compile_evidence_problems(
                output, record, archive, [dependency]))
            argfile.write_text("\n".join('"' + str(path) + '"' for path in sources[:-1]))
            record["argfile"] = compiler_modes.record_file(output, argfile)
            self.assertTrue(compiler_modes.original_compile_evidence_problems(
                output, record, archive, [dependency]))
            argfile.write_text("\n".join('"' + str(path) + '"' for path in sources))
            record["argfile"] = compiler_modes.record_file(output, argfile)
            process["command"][8] = str(output / "wrong.jar")
            self.assertTrue(compiler_modes.original_compile_evidence_problems(
                output, record, archive, [dependency]))

    def test_original_javac_failure_retains_compile_record(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            log = output / "logs/compile-originals.log"
            failure = {"command": ["javac"], "exit_code": 1, "log": str(log)}
            receipt = {}
            with patch.object(compiler_modes, "execute", return_value=failure):
                with self.assertRaises(ValueError):
                    compiler_modes.run_originals(output, output / "staged/core.jar", "java8",
                                                 [], output / "helper-classes", [], receipt)
            self.assertEqual(199, receipt["original_compile"]["source_count"])
            self.assertEqual(failure, receipt["original_compile"]["process"])

    def test_split_compile_capture_hashes_stdout_and_stderr(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            log = output / "compile.log"
            process = compiler_modes.execute(
                [compiler_modes.sys.executable, "-c",
                 "import sys;print('out');print('err', file=sys.stderr)"],
                log, cwd=output, split_streams=True)
            self.assertEqual(b"out\n", log.with_suffix(".stdout").read_bytes())
            self.assertEqual(b"err\n", log.with_suffix(".stderr").read_bytes())
            self.assertEqual([], compiler_modes.compile_process_problems(
                process, process["command"], log, split_streams=True))

    def test_jvm_consumer_replay_rejects_resealed_compile_and_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            project = output / "external-jvm-consumer"
            core = output / "staged/core.jar"
            facade = output / "staged/facade.jar"
            dependency = output / "stdlib.jar"
            artifacts = {"dyn4k-core": {"path": "staged/core.jar"},
                         "dyn4k": {"path": "staged/facade.jar"}}
            compile_log = output / "logs/consumer-compile-java8.log"
            compile_log.parent.mkdir()
            compile_log.write_text("> Task :compileKotlin\n> Task :compileJava\n"
                                   "> Task :classes\nBUILD SUCCESSFUL in 1s\n")
            execution_log = output / "logs/consumer-java8.log"
            execution_log.write_text("STAGED_CONSUMER_PASSED kotlin=2 java=1\n")
            compile_command = [str(compiler_modes.ROOT / "gradlew"), "-p", str(project),
                               "--offline", "--no-daemon", "--max-workers=1",
                               "--rerun-tasks", "--console=plain", "classes"]
            execution_command = [str(compiler_modes.JDK["java8"] / "bin/java"), "-cp",
                                 ":".join([str(project / "build/classes/kotlin/main"),
                                           str(project / "build/classes/java/main"),
                                           str(core), str(facade), str(dependency)]),
                                 "qualification.ConsumerKt"]
            consumer = {"runtime": "java8",
                        "compile": {"command": compile_command.copy(), "exit_code": 0,
                                    "log": str(compile_log),
                                    "log_sha256": compiler_modes.digest(compile_log)},
                        "process": {"command": execution_command.copy(), "exit_code": 0,
                                    "log": str(execution_log),
                                    "log_sha256": compiler_modes.digest(execution_log)}}
            self.assertEqual([], compiler_modes.jvm_consumer_evidence_problems(
                output, consumer, artifacts, [dependency]))
            consumer["compile"]["command"][-1] = "help"
            self.assertTrue(compiler_modes.jvm_consumer_evidence_problems(
                output, consumer, artifacts, [dependency]))
            consumer["compile"]["command"][-1] = "classes"
            consumer["compile"]["exit_code"] = 1
            self.assertTrue(compiler_modes.jvm_consumer_evidence_problems(
                output, consumer, artifacts, [dependency]))
            consumer["compile"]["exit_code"] = 0
            compile_log.write_text("BUILD FAILED\n")
            consumer["compile"]["log_sha256"] = compiler_modes.digest(compile_log)
            self.assertTrue(compiler_modes.jvm_consumer_evidence_problems(
                output, consumer, artifacts, [dependency]))
            compile_log.write_text("> Task :compileKotlin\n> Task :compileJava\n"
                                   "> Task :classes\nBUILD SUCCESSFUL in 1s\n")
            consumer["compile"]["log_sha256"] = compiler_modes.digest(compile_log)
            consumer["process"]["command"] = ["/bin/false"]
            self.assertTrue(compiler_modes.jvm_consumer_evidence_problems(
                output, consumer, artifacts, [dependency]))

    def test_jvm_corpus_replay_binds_java8_and_mode_jars(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            core = output / "staged/core.jar"
            facade = output / "staged/facade.jar"
            dependency = output / "stdlib.jar"
            artifacts = {"dyn4k-core": {"path": "staged/core.jar"},
                         "dyn4k": {"path": "staged/facade.jar"}}
            manifest = {"cases": [{"module": "dyn4k-core", "hosts": ["jvm"],
                                   "classname": "example.Core", "method": "one"}]}
            compiled_tests = {"dyn4k-core": [{"path": "test-classes/dyn4k-core/kotlin"}]}
            retained = output / compiled_tests["dyn4k-core"][0]["path"]
            classpath = [retained, retained,
                         core, facade, dependency, output / "helper-classes"]
            report = {"kind": "full-common", "module": "dyn4k-core", "runtime": "java8",
                      "file": {"path": "xml/dyn4k-core-java8.xml"},
                      "process": {"command": [str(compiler_modes.JDK["java8"] / "bin/java"),
                                              "-cp", ":".join(map(str, classpath)),
                                              "PinnedCorpusReport",
                                              str(output / "xml/dyn4k-core-java8.xml"),
                                              "example.Core"]}}
            self.assertEqual([], compiler_modes.jvm_report_command_problems(
                output, report, manifest, artifacts, [dependency], compiled_tests))
            report["process"]["command"][0] = str(compiler_modes.JDK["current"] / "bin/java")
            self.assertTrue(compiler_modes.jvm_report_command_problems(
                output, report, manifest, artifacts, [dependency], compiled_tests))
            report["process"]["command"][0] = str(compiler_modes.JDK["java8"] / "bin/java")
            report["process"]["command"][2] = report["process"]["command"][2].replace(
                str(core), str(output / "other-mode-core.jar"))
            self.assertTrue(compiler_modes.jvm_report_command_problems(
                output, report, manifest, artifacts, [dependency], compiled_tests))


if __name__ == "__main__":
    unittest.main()
