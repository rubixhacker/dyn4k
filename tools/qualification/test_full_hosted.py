import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PureWindowsPath
from unittest import mock

import full_hosted
import qualify
import test_publication


class FullHostedTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "TEST-one.xml"
        self.expected = {("org.dyn4j.geometry.ExampleTest", "works")}

    def align_synthetic_docs(self, repository, target):
        staging = repository / "build/staging-repository" / qualify.GROUP.replace(".", "/")
        for module in qualify.MODULES:
            root = staging / module / qualify.VERSION / f"{module}-{qualify.VERSION}-javadoc.jar"
            name = qualify.target_publication_name(module, target)
            target_jar = staging / name / qualify.VERSION / f"{name}-{qualify.VERSION}-javadoc.jar"
            target_jar.write_bytes(root.read_bytes())
            target_jar.with_name(target_jar.name + ".sha256").write_text(
                full_hosted.sha256(target_jar) + "\n")

    def write_suite(self, cases, skipped=False, ignored=False):
        suite = ET.Element("testsuite", tests=str(len(cases)), failures="0", errors="0",
                           skipped="1" if skipped else "0", time="0.1")
        for classname, name in cases:
            case = ET.SubElement(suite, "testcase", classname=classname, name=name,
                                 time="0.1")
            if skipped:
                ET.SubElement(case, "skipped")
            if ignored:
                ET.SubElement(case, "ignored")
        self.path.write_bytes(ET.tostring(suite))
        return time.time_ns()

    def test_native_full_report_requires_exact_source_cases(self):
        name = "macosArm64Test.org.dyn4j.geometry.ExampleTest"
        good = (name, "works[macosArm64]")
        end = self.write_suite([good])
        result = full_hosted.read_reports([self.path], self.expected, "macosArm64", 0, end)
        self.assertEqual(1, result["executed"])
        for cases, marker in (([], "missing"), ([good, good], "duplicate"),
                              ([good, (name, "extra[macosArm64]")], "extra"),
                              ([(name, "works[mingwX64]")], "target")):
            end = self.write_suite(cases)
            with self.assertRaisesRegex(ValueError, marker):
                full_hosted.read_reports([self.path], self.expected, "macosArm64", 0, end)

    def test_failed_skipped_ignored_and_stale_xml_cannot_pass(self):
        good = ("macosArm64Test.org.dyn4j.geometry.ExampleTest", "works[macosArm64]")
        for flags in ({"skipped": True}, {"ignored": True}):
            end = self.write_suite([good], **flags)
            with self.assertRaises(ValueError):
                full_hosted.read_reports([self.path], self.expected, "macosArm64", 0, end)
        end = self.write_suite([good])
        with self.assertRaisesRegex(ValueError, "stale"):
            full_hosted.read_reports([self.path], self.expected, "macosArm64", end + 1,
                                     end + 2)
        suite = ET.parse(self.path)
        ET.SubElement(suite.getroot().find("testcase"), "failure").text = "broken"
        suite.getroot().set("failures", "1")
        suite.write(self.path)
        with self.assertRaisesRegex(ValueError, "failed"):
            full_hosted.read_reports([self.path], self.expected, "macosArm64", 0,
                                     time.time_ns())

    def test_safari_report_requires_browser_runtime_and_exact_case(self):
        good = ("jsBrowserTest.org.dyn4j.geometry.ExampleTest",
                "works[js, browser, Safari26.6.2, MacOS10.15.7]")
        end = self.write_suite([good])
        self.assertEqual(1, full_hosted.read_reports([self.path], self.expected,
                                                      "jsSafari", 0, end)["executed"])
        end = self.write_suite([(good[0], "works[js, node]")])
        with self.assertRaisesRegex(ValueError, "Safari browser identity"):
            full_hosted.read_reports([self.path], self.expected, "jsSafari", 0, end)
        end = self.write_suite([good])
        with self.assertRaisesRegex(ValueError, "browser version differs"):
            full_hosted.read_reports([self.path], self.expected, "jsSafari", 0, end,
                                     "26.6.3")

    def test_committed_manifest_bytes_reject_source_drift(self):
        file = self.root / "tools/qualification/full-common-corpus.json"
        file.parent.mkdir(parents=True)
        file.write_bytes(b"sealed")
        with mock.patch.object(full_hosted.subprocess, "check_output", return_value=b"sealed"):
            self.assertEqual(b"sealed", full_hosted.committed_input(
                self.root, "a" * 40, full_hosted.MANIFEST))
            file.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "candidate source differs"):
                full_hosted.committed_input(self.root, "a" * 40, full_hosted.MANIFEST)

    def test_process_receipt_records_real_pid_and_output_hashes(self):
        process = full_hosted.run_command(
            ["python3", "-c", "import sys; print('out'); print('err', file=sys.stderr)"],
            self.root, self.root / "process")
        self.assertGreater(process["pid"], 0)
        self.assertEqual(0, process["exit_code"])
        self.assertEqual("out\n", (self.root / "process/stdout.txt").read_text())
        self.assertEqual(full_hosted.sha256(self.root / "process/stderr.txt"),
                         process["stderr_sha256"])
        for stream in ("stdout", "stderr"):
            modified = (self.root / "process" / f"{stream}.txt").stat().st_mtime_ns
            self.assertLessEqual(process["started_ns"], modified)
            self.assertLessEqual(modified, process["finished_ns"])

    def test_release_task_and_production_input_are_required(self):
        folder = self.root / "process"
        folder.mkdir()
        process = {"exit_code": 0}
        (folder / "stdout.txt").write_text(
            "> Task :dyn4k-core:mingwX64Test\nBUILD SUCCESSFUL\n")
        with self.assertRaisesRegex(ValueError, "link"):
            full_hosted.require_test_tasks(process, folder, "mingwX64",
                                           "optimized-opt", ("dyn4k-core",))
        (folder / "stdout.txt").write_text(
            "> Task :dyn4k-core:linkReleaseTestMingwX64\n"
            "> Task :dyn4k-core:mingwX64Test\nBUILD SUCCESSFUL\n")
        full_hosted.require_test_tasks(process, folder, "mingwX64", "optimized-opt",
                                       ("dyn4k-core",))
        (folder / "stdout.txt").write_text(
            "> Task :dyn4k-core:linkReleaseTestMingwX64 SKIPPED\n"
            "> Task :dyn4k-core:mingwX64Test SKIPPED\nBUILD SUCCESSFUL\n")
        with self.assertRaisesRegex(ValueError, "execute|link"):
            full_hosted.require_test_tasks(process, folder, "mingwX64", "optimized-opt",
                                           ("dyn4k-core",))
        (folder / "stdout.txt").write_text(
            "> Task :dyn4k-core:jsBrowserTest\nBUILD SUCCESSFUL\n")
        with self.assertRaisesRegex(ValueError, "production"):
            full_hosted.require_test_tasks(process, folder, "jsSafari", "production",
                                           ("dyn4k-core",))

    def test_executable_must_match_configuration_and_invocation(self):
        binary = self.root / "build/bin/mingwX64/releaseTest/test.exe"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"release")
        process = {"started_ns": 0, "finished_ns": time.time_ns()}
        self.assertEqual(full_hosted.sha256(binary), full_hosted.test_products(
            self.root, "mingwX64", "optimized-opt", process)["sha256"])
        diagnostic = self.root / "product-inventory.json"
        products = full_hosted.collect_test_products(
            {"core": self.root}, "mingwX64", "optimized-opt", process,
            diagnostic, self.root)
        self.assertEqual(full_hosted.sha256(binary), products["core"]["sha256"])
        self.assertFalse(diagnostic.exists())
        with self.assertRaisesRegex(ValueError, "exactly one"):
            full_hosted.test_products(self.root, "mingwX64", "debug-g", process)
        with self.assertRaisesRegex(ValueError, "predates"):
            full_hosted.test_products(self.root, "mingwX64", "optimized-opt",
                                      {"started_ns": time.time_ns() + 1,
                                       "finished_ns": time.time_ns() + 2})

    def test_missing_mac_product_retains_bounded_inventory_without_accepting_it(self):
        project = self.root / "dyn4k-core"
        product = project / "build/bin/macosArm64/debugTest/test"
        product.parent.mkdir(parents=True)
        product.write_bytes(b"observed-layout-placeholder")
        output = self.root / "failed-archive"
        output.mkdir()
        (output / "receipt.json").write_text("{}")
        diagnostic = output / "debug-g/product-inventory-source.json"
        process = {"started_ns": 1, "finished_ns": time.time_ns() + 10**9,
                   "invocation_id": "synthetic-invocation", "exit_code": 0}
        with self.assertRaisesRegex(ValueError, "product inventory"):
            full_hosted.collect_test_products(
                {"dyn4k-core": project}, "macosArm64", "debug-g", process,
                diagnostic, output)
        evidence = json.loads(diagnostic.read_text())
        self.assertEqual("macosArm64", evidence["target"])
        self.assertEqual("synthetic-invocation", evidence["invocation_id"])
        files = evidence["projects"]["dyn4k-core"]["entries"]
        self.assertEqual(1, len([item for item in files if item["kind"] == "file"]))
        self.assertEqual("build/bin/macosArm64/debugTest/test",
                         next(item["path"] for item in files if item["kind"] == "file"))
        archive = self.root / "diagnostic.tar"
        full_hosted.package_archive(output, archive)
        with tarfile.open(archive) as packed:
            self.assertIn("debug-g/product-inventory-source.json", packed.getnames())

    def test_product_diagnostic_inventory_has_a_fixed_entry_limit(self):
        project = self.root / "dyn4k-core"
        folder = project / "build/bin/macosArm64/debugTest"
        folder.mkdir(parents=True)
        for index in range(130):
            (folder / f"artifact-{index:03d}").write_bytes(b"product")
        inventory = full_hosted.product_inventory(project, "macosArm64")
        self.assertTrue(inventory["truncated"])
        self.assertEqual(128, len(inventory["entries"]))
        crowded = self.root / "crowded"
        binary = crowded / "build/bin/macosArm64/debugTest/test"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"candidate")
        for index in range(130):
            (crowded / "build/bin" / f"a{index:03d}").mkdir()
        prioritized = full_hosted.product_inventory(crowded, "macosArm64")
        self.assertTrue(prioritized["truncated"])
        self.assertIn(binary.relative_to(crowded).as_posix(),
                      {item["path"] for item in prioritized["entries"]})

    def test_windows_original_paths_are_portable_for_offline_verification(self):
        path = full_hosted.original_path("mingwX64", r"C:\runner\work\staging")
        self.assertEqual(PureWindowsPath(r"C:\runner\work\staging"), path)
        with self.assertRaisesRegex(ValueError, "original path"):
            full_hosted.original_path("mingwX64", "relative/staging")

    def test_reviewed_manifest_selects_all_common_core_and_facade_cases(self):
        manifest_path = Path(__file__).resolve().parents[2] / full_hosted.MANIFEST
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(2465, len(full_hosted.expected_cases(manifest, "dyn4k-core")))
        self.assertEqual(58, len(full_hosted.expected_cases(manifest, "dyn4k")))
        removed = next(case for case in manifest["cases"]
                       if case["module"] == "dyn4k-core" and case["source_set"] == "commonTest")
        reduced = {**manifest, "cases": [case for case in manifest["cases"] if case != removed]}
        with self.assertRaisesRegex(ValueError, "reviewed common corpus count"):
            full_hosted.expected_cases(reduced, "dyn4k-core")

    def test_corpus_input_audit_uses_hosted_generated_output_allowlist(self):
        import full_corpus

        repository = Path(__file__).resolve().parents[2]
        sha = full_hosted.subprocess.check_output(
            ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()

        def corpus_audit(*_args, **kwargs):
            if kwargs.get("check_checkout") is not False:
                return ["untracked candidate input: consumers/qualification/portable/build"]
            return []

        with mock.patch.object(qualify, "require_clean_checkout"), mock.patch.object(
                full_corpus, "candidate_input_problems", side_effect=corpus_audit):
            self.assertEqual(2465, len(full_hosted.expected_cases(
                full_hosted.load_corpus(repository, sha), "dyn4k-core")))

    def test_run_binds_candidate_to_real_staged_publication_audit(self):
        repository = self.root / "checkout"
        repository.mkdir()
        target = "tvosSimulatorArm64"
        staging = test_publication.PublicationAuditTests().stage(repository, (target,))
        self.align_synthetic_docs(repository, target)
        for module in qualify.MODULES:
            (repository / module / "src/commonMain/kotlin/api/Type.kt").write_bytes(
                b"// Fixture notice\npackage api\nclass Type\n")
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "core.autocrlf", "false"],
                       check=True)
        subprocess.run(["git", "-C", str(repository), "add", "LICENSE.md",
                        "dyn4k-core/src", "dyn4k/src"], check=True)
        subprocess.run(["git", "-C", str(repository), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "commit", "-qm", "candidate"],
                       check=True)
        candidate = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"],
                                            text=True).strip()
        for relative in (full_hosted.MAPPING, full_hosted.PAIRS):
            path = repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture\n")
        (repository / "build.gradle.kts").write_text(
            'kotlin("multiplatform") version "2.4.20"\n'
            'id("com.android.kotlin.multiplatform.library") version "9.3.1"\n')
        manifest = {"source_files": [], "source_tree_sha256": "a" * 64}
        runtime = {"java_version": "21.0.12", "simulators": {"tvOS": [
            {"udid": "00000000-0000-0000-0000-000000000001"}]}}
        audit = qualify.audit_staging(staging, candidate, (target,), repository / "LICENSE.md")
        self.assertEqual("PASSED", audit["status"], audit["errors"])

        calls = []
        def stop_after_staging(*_args, **_kwargs):
            calls.append(1)
            if len(calls) == 1:
                return {"exit_code": 0, "started_ns": 1,
                        "finished_ns": time.time_ns() + 10**12,
                        "stdout_sha256": "0" * 64}
            raise ValueError("fixture stops after staging capture")

        captured = []
        original_capture = full_hosted.artifact.capture_staging
        def capture_staging(*args):
            result = original_capture(*args)
            captured.append(result)
            return result

        with mock.patch.object(full_hosted, "__file__", str(repository /
                               "tools/qualification/full_hosted.py")), \
                mock.patch.object(full_hosted, "INPUTS", ()), \
                mock.patch.object(full_hosted, "load_corpus", return_value=manifest), \
                mock.patch.object(full_hosted.hosted, "discover_runtime", return_value=runtime), \
                mock.patch.object(full_hosted.hosted, "runtime_status", return_value=("READY", "")), \
                mock.patch.object(full_hosted.hosted, "gradle_wrapper",
                                  return_value=str(repository / "gradlew")), \
                mock.patch.object(full_hosted.hosted, "tool_version", return_value="9.5.0"), \
                mock.patch.object(full_hosted, "run_command", side_effect=stop_after_staging), \
                mock.patch.object(full_hosted.artifact, "capture_staging",
                                  side_effect=capture_staging) as capture:
            receipt = full_hosted.run(target, candidate, self.root / "captured")
            self.assertEqual(candidate, capture.call_args.args[3])
            self.assertEqual("FAILED", receipt["status"])
            self.assertEqual("fixture stops after staging capture",
                             receipt["configurations"][0]["reason"])
            self.assertEqual(set(qualify.MODULES), set(receipt["artifact_hashes"]))
            self.assertTrue(receipt["staged_gav"])
            self.assertEqual(audit["content_contract"], captured[0][3])
            self.assertEqual(audit["content_contract"], receipt["staged_content_contract"])
            staged = [item for item in full_hosted.archive_inventory(self.root / "captured")
                      if item["path"].startswith("staged/")]
            self.assertEqual(52, len(staged))
            full_hosted.verify_staging(self.root / "captured", {
                "target": target, "staged_gav": receipt["staged_gav"],
                "artifact_hashes": receipt["artifact_hashes"], "files": staged})
            receipt["files"] = full_hosted.archive_inventory(self.root / "captured")
            full_hosted.verify_staged_content(self.root / "captured", receipt, repository)
            name = qualify.target_publication_name("dyn4k-core", target)
            metadata = (self.root / "captured/staged" / qualify.GROUP.replace(".", "/") /
                        name / qualify.VERSION / f"{name}-{qualify.VERSION}-metadata.jar")
            original = metadata.read_bytes()
            metadata.write_bytes(original + b"\n")
            metadata.with_name(metadata.name + ".sha256").write_text(
                full_hosted.sha256(metadata) + "\n")
            with self.assertRaisesRegex(ValueError, "content audit"):
                full_hosted.verify_staged_content(self.root / "captured", receipt, repository)

            calls.clear()
            wrong = full_hosted.run(target, "b" * 40, self.root / "wrong-candidate")
            self.assertEqual("FAILED", wrong["status"])
            self.assertIn("staged publication is partial or invalid", wrong["reason"])
            self.assertNotIn("staged_gav", wrong)

    def test_synthetic_joined_run_replays_complete_apple_receipt(self):
        evidence_parent = os.environ.get("DYN4K_HOSTED_JOINED_EVIDENCE_DIR")
        if evidence_parent:
            parent = Path(evidence_parent)
            parent.mkdir(parents=True, exist_ok=True)
            evidence = Path(tempfile.mkdtemp(prefix="synthetic-joined-", dir=parent))
        else:
            evidence = self.root / "synthetic-joined"
            evidence.mkdir()
        actual_repository = Path(__file__).resolve().parents[2]
        repository = evidence / "checkout"
        repository.mkdir()
        output = evidence / "full"
        target = "tvosSimulatorArm64"
        simulator = "00000000-0000-0000-0000-000000000001"
        (repository / "LICENSE.md").write_bytes(b"Fixture license\n")
        for module in qualify.MODULES:
            source = repository / module / "src/commonMain/kotlin/api/Type.kt"
            source.parent.mkdir(parents=True)
            source.write_text("// Fixture notice\npackage api\nclass Type\n")
        manifest = json.loads((actual_repository / full_hosted.MANIFEST).read_text())
        for item in manifest["source_files"]:
            destination = repository / item["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(actual_repository / item["path"], destination)
            self.assertEqual(item["sha256"], full_hosted.sha256(destination))
        for relative in full_hosted.INPUTS:
            destination = repository / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(actual_repository / relative, destination)
        for helper in ("stage.py", "independent_adapter.py", "full_suite_manifest.py"):
            shutil.copy2(actual_repository / "tools/qualification" / helper,
                         repository / "tools/qualification" / helper)
        shutil.copy2(actual_repository / "gradlew", repository / "gradlew")
        (repository / ".gitattributes").write_bytes(b"*.kt -text\n*.java -text\n")
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "core.autocrlf", "false"],
                       check=True)
        subprocess.run(["git", "-C", str(repository), "add", ".gitattributes", "LICENSE.md", "gradlew",
                        "dyn4k-core/src", "dyn4k/src", "tools", "build.gradle.kts",
                        "consumers/qualification/portable/build.gradle.kts"], check=True)
        subprocess.run(["git", "-C", str(repository), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "commit", "-qm", "candidate"],
                       check=True)
        candidate = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"],
                                            text=True).strip()
        for relative in ("LICENSE.md", *full_hosted.INPUTS):
            self.assertEqual((repository / relative).read_bytes(),
                             full_hosted.committed_input(repository, candidate, relative))

        consumer_manifest = json.loads((repository / "tools/qualification/foundation-probes.json").read_text())
        group = next(item for item in consumer_manifest["groups"]
                     if item["id"] == f"consumer-{target}")
        consumer_cases = qualify.expected_probe_cases(consumer_manifest, group)

        def write(path, data):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data if isinstance(data, bytes) else data.encode())

        def suite(cases):
            root = ET.Element("testsuite", tests=str(len(cases)), failures="0", errors="0",
                              skipped="0", time="1")
            for classname, method in cases:
                ET.SubElement(root, "testcase", classname=classname, name=method, time="0.1")
            return ET.tostring(root)

        def synthetic_command(command, _cwd, destination, invocation_id=None):
            started = time.time_ns()
            kind = destination.name
            configuration = destination.parent.name
            if kind == "stage":
                test_publication.PublicationAuditTests().stage(repository, (target,))
                self.align_synthetic_docs(repository, target)
                stdout = "> Task :dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository\n"
            elif kind == "source":
                mode = "Release" if configuration == "optimized-opt" else "Debug"
                stdout = ""
                for module in qualify.MODULES:
                    stdout += (f"> Task :{module}:link{mode}TestTvosSimulatorArm64\n"
                               f"> Task :{module}:{target}Test\n")
                    cases = [(f"{target}Test.{name}", f"{method}[{target}]")
                             for name, method in full_hosted.expected_cases(manifest, module)]
                    write(repository / module / "build/test-results" / f"{target}Test/TEST-all.xml",
                          suite(cases))
                    binary_mode = "releaseTest" if mode == "Release" else "debugTest"
                    write(repository / module / "build/bin" / target / binary_mode / "test.kexe",
                          f"synthetic-{module}-{configuration}")
            elif kind == "consumer":
                mode = "Release" if configuration == "optimized-opt" else "Debug"
                stdout = f"> Task :link{mode}TestTvosSimulatorArm64\n> Task :{target}Test\n"
                report = repository / group["report_pattern"].replace("TEST-*.xml", "TEST-all.xml")
                write(report, suite(consumer_cases))
                binary_mode = "releaseTest" if mode == "Release" else "debugTest"
                write(repository / "consumers/qualification/portable/build/bin" /
                      target / binary_mode / "consumer.kexe", f"synthetic-consumer-{configuration}")
            else:
                self.assertEqual("graph", kind)
                artifacts = []
                for module in qualify.MODULES:
                    name = qualify.target_publication_name(module, target)
                    binary = repository / "build/staging-repository" / qualify.target_binary_path(module, target)
                    artifacts.append({"component": f"{qualify.GROUP}:{name}:{qualify.VERSION}",
                                      "file": str(binary), "name": binary.name,
                                      "size": binary.stat().st_size,
                                      "sha256": full_hosted.sha256(binary)})
                graph = {"configuration": f"{target}CompileKlibraries",
                         "components": [item["component"] for item in artifacts] +
                         [f"{qualify.GROUP}:{module}:{qualify.VERSION}" for module in qualify.MODULES],
                         "artifacts": artifacts}
                stdout = "DYN4K_RESOLVED_GRAPH=" + json.dumps(graph) + "\n"
            write(destination / "stdout.txt", stdout + "BUILD SUCCESSFUL\n")
            write(destination / "stderr.txt", "")
            finished = time.time_ns()
            return {"command": command, "pid": 42, "exit_code": 0,
                    "invocation_id": invocation_id, "started_ns": started,
                    "finished_ns": finished,
                    "stdout_sha256": full_hosted.sha256(destination / "stdout.txt"),
                    "stderr_sha256": full_hosted.sha256(destination / "stderr.txt")}

        runtime = {"system": "Darwin", "machine": "arm64", "os_version": "26.0",
                   "xcode_version": "26.4.1", "java_version": "21.0.12",
                   "simulators": {"tvOS": [{"udid": simulator,
                                            "runtime": "com.apple.CoreSimulator.SimRuntime.tvOS-26-0"}]}}
        runner = {"GITHUB_RUN_ID": "synthetic-123", "GITHUB_JOB": "synthetic-hosted",
                  "RUNNER_NAME": "synthetic-runner", "RUNNER_OS": "macOS",
                  "RUNNER_ARCH": "ARM64"}
        with mock.patch.object(full_hosted, "__file__", str(repository /
                               "tools/qualification/full_hosted.py")), \
                mock.patch.object(full_hosted, "load_corpus", wraps=full_hosted.load_corpus) as load, \
                mock.patch.object(full_hosted.hosted, "discover_runtime", return_value=runtime), \
                mock.patch.object(full_hosted.hosted, "runtime_status", return_value=("READY", "")), \
                mock.patch.object(full_hosted.hosted, "gradle_wrapper",
                                  return_value=str(repository / "gradlew")), \
                mock.patch.object(full_hosted.hosted, "tool_version", return_value="9.5.0"), \
                mock.patch.object(full_hosted, "run_command", side_effect=synthetic_command), \
                mock.patch.object(full_hosted.artifact, "capture_staging",
                                  wraps=full_hosted.artifact.capture_staging) as capture, \
                mock.patch.dict(os.environ, runner):
            emitted = full_hosted.run(target, candidate, output)
            self.assertEqual("FULL_COMMON_PASSED", emitted["status"], emitted.get("reason"))
            self.assertEqual(2, len(emitted["configurations"]))
            self.assertEqual(candidate, capture.call_args.args[3])
            self.assertEqual(52, len([item for item in emitted["files"]
                                      if item["path"].startswith("staged/")]))
            self.assertEqual(2, load.call_count)
            receipt = qualify.load_json_strict(output / "receipt.json")
            self.assertEqual(emitted, receipt)
            full_hosted.verify_raw_files(output, receipt)
            archive = evidence / "full.tar"
            full_hosted.package_archive(output, archive)
            transported = full_hosted.verify_transport_archive(archive, candidate, target)
            self.assertEqual(receipt, transported)

            clean = evidence / "clean-checkout"
            subprocess.run(["git", "-c", "core.autocrlf=false", "clone", "-q",
                            "--no-local", str(repository), str(clean)], check=True)
            subprocess.run(["git", "-C", str(clean), "config", "core.autocrlf", "false"],
                           check=True)
            subprocess.run(["git", "-C", str(clean), "checkout", "-q", "--detach", candidate],
                           check=True)
            for module in qualify.MODULES:
                self.assertFalse((clean / module / "build/dokka/html").exists())
            command = [sys.executable, str(clean / "tools/qualification/full_hosted.py"),
                       "--verify-tar", "--candidate-sha", candidate, "--target", target,
                       "--archive", str(archive)]
            replay = subprocess.run(command, cwd=clean, capture_output=True, text=True)
            self.assertEqual(0, replay.returncode, replay.stderr)
            self.assertIn('"verified": true', replay.stdout)
            directory_command = [sys.executable,
                                 str(clean / "tools/qualification/full_hosted.py"),
                                 "--verify", "--candidate-sha", candidate,
                                 "--target", target, "--output", str(output)]
            directory_replay = subprocess.run(directory_command, cwd=clean,
                                              capture_output=True, text=True)
            self.assertEqual(0, directory_replay.returncode, directory_replay.stderr)
            artifact_command = [sys.executable,
                                str(clean / "tools/qualification/artifact.py"),
                                "verify", "--candidate-sha", candidate,
                                "--full-hosted", "--output"]
            for bundle in (output, archive):
                ingested = subprocess.run([*artifact_command, str(bundle)], cwd=clean,
                                          capture_output=True, text=True)
                self.assertEqual(0, ingested.returncode, ingested.stderr)
                self.assertEqual("FULL_COMMON_PASSED", json.loads(ingested.stdout)["status"])
            qualification_report = evidence / "qualification.json"
            recorded = subprocess.run([
                sys.executable, str(clean / "tools/qualification/qualify.py"), "record",
                "--candidate-sha", candidate, "--full-hosted-bundle", str(archive),
                "--output", str(qualification_report)], cwd=clean,
                capture_output=True, text=True)
            self.assertEqual(1, recorded.returncode, recorded.stderr)
            self.assertEqual("", recorded.stderr)
            qualification = qualify.load_json_strict(qualification_report)
            self.assertEqual(112, qualification["total"])
            self.assertEqual(0, qualification["counts"]["PASSED"])
            self.assertEqual(1, len(qualification["full_hosted_receipts"]))
            self.assertEqual("FULL_COMMON_PASSED",
                             qualification["full_hosted_receipts"][0]["status"])
            scoped = qualification["full_hosted_receipts"][0]
            self.assertEqual(2, len(scoped["configuration_lanes"]))
            for gate in ("audit_status", "candidate_manifest_status",
                         "complete_suite_status", "release_gate_status"):
                self.assertEqual("NOT_RUN", scoped[gate])
            self.assertEqual({"NOT_RUN"}, {lane["status"] for lane in qualification["lanes"]})
            adverse_order = evidence / "adverse-process-order"
            shutil.copytree(output, adverse_order)
            order_receipt = qualify.load_json_strict(adverse_order / "receipt.json")
            self.assertGreater(order_receipt["stage"]["finished_ns"], 1)
            order_receipt["configurations"][0]["consumer_process"]["started_ns"] = 1
            (adverse_order / "receipt.json").write_text(
                json.dumps(order_receipt, sort_keys=True) + "\n")
            order_archive = evidence / "adverse-process-order.tar"
            full_hosted.package_archive(adverse_order, order_archive)
            with self.assertRaisesRegex(ValueError, "process order"):
                full_hosted.verify_raw_files(adverse_order, order_receipt)
            with self.assertRaisesRegex(ValueError, "process order"):
                full_hosted.verify_transport_archive(order_archive, candidate, target)
            for command_prefix, bundle in ((directory_command[:-1], adverse_order),
                                           (command[:-1], order_archive)):
                result = subprocess.run([*command_prefix, str(bundle)], cwd=clean,
                                        capture_output=True, text=True)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("process order", result.stderr)
            for bundle in (adverse_order, order_archive):
                result = subprocess.run([*artifact_command, str(bundle)], cwd=clean,
                                        capture_output=True, text=True)
                self.assertEqual(1, result.returncode)
                self.assertIn("process order", result.stderr)
            adverse_order_report = evidence / "adverse-process-order-qualification.json"
            order_record = subprocess.run([
                sys.executable, str(clean / "tools/qualification/qualify.py"), "record",
                "--candidate-sha", candidate, "--full-hosted-bundle", str(order_archive),
                "--output", str(adverse_order_report)], cwd=clean,
                capture_output=True, text=True)
            self.assertEqual(2, order_record.returncode)
            self.assertIn("process order", order_record.stderr)
            self.assertFalse(adverse_order_report.exists())
            rogue = clean / "dyn4k-core/build/dokka/html/index.html"
            rogue.parent.mkdir(parents=True)
            rogue.write_text("<html>untracked local replacement</html>")
            replay_with_rogue = subprocess.run(command, cwd=clean, capture_output=True,
                                               text=True)
            self.assertEqual(0, replay_with_rogue.returncode, replay_with_rogue.stderr)

            adverse_dokka = evidence / "adverse-dokka-page"
            shutil.copytree(output, adverse_dokka)
            page = adverse_dokka / "dokka/dyn4k-core/index.html"
            page_mtime = page.stat().st_mtime_ns
            page.write_text("<html>forged archived page</html>")
            os.utime(page, ns=(page_mtime, page_mtime))
            changed_dokka = qualify.load_json_strict(adverse_dokka / "receipt.json")
            changed_dokka["dokka_provenance"]["modules"]["dyn4k-core"]["index.html"] = (
                full_hosted.sha256(page))
            changed_dokka["files"] = full_hosted.archive_inventory(adverse_dokka)
            (adverse_dokka / "receipt.json").write_text(json.dumps(changed_dokka, sort_keys=True))
            with self.assertRaisesRegex(ValueError, "documentation bytes differ"):
                full_hosted.verify_raw_files(adverse_dokka, changed_dokka)
            adverse_dokka_archive = evidence / "adverse-dokka-page.tar"
            full_hosted.package_archive(adverse_dokka, adverse_dokka_archive)
            adverse_replay = subprocess.run([*command[:-1], str(adverse_dokka_archive)],
                                            cwd=clean, capture_output=True, text=True)
            self.assertNotEqual(0, adverse_replay.returncode)
            self.assertIn("documentation bytes differ", adverse_replay.stderr)

            unlisted_dokka = evidence / "adverse-unlisted-dokka"
            shutil.copytree(output, unlisted_dokka)
            (unlisted_dokka / "dokka/dyn4k-core/unlisted.html").write_text("<html>extra</html>")
            unlisted_receipt = qualify.load_json_strict(unlisted_dokka / "receipt.json")
            with self.assertRaisesRegex(ValueError, "unlisted or missing archive member"):
                full_hosted.verify_raw_files(unlisted_dokka, unlisted_receipt)
            unlisted_archive = evidence / "adverse-unlisted-dokka.tar"
            full_hosted.package_archive(unlisted_dokka, unlisted_archive)
            unlisted_replay = subprocess.run([*command[:-1], str(unlisted_archive)],
                                             cwd=clean, capture_output=True, text=True)
            self.assertNotEqual(0, unlisted_replay.returncode)
            self.assertIn("unlisted or missing archive member", unlisted_replay.stderr)

            adverse = evidence / "adverse-source"
            shutil.copytree(output, adverse)
            name = qualify.target_publication_name("dyn4k-core", target)
            source = (adverse / "staged" / qualify.GROUP.replace(".", "/") / name /
                      qualify.VERSION / f"{name}-{qualify.VERSION}-sources.jar")
            source.write_bytes(source.read_bytes() + b"\n")
            source.with_name(source.name + ".sha256").write_text(full_hosted.sha256(source) + "\n")
            changed = qualify.load_json_strict(adverse / "receipt.json")
            changed["files"] = full_hosted.archive_inventory(adverse)
            (adverse / "receipt.json").write_text(json.dumps(changed, sort_keys=True) + "\n")
            with self.assertRaises(ValueError) as directory_error:
                full_hosted.verify_raw_files(adverse, changed)
            adverse_archive = evidence / "adverse-source.tar"
            full_hosted.package_archive(adverse, adverse_archive)
            with self.assertRaises(ValueError) as tar_error:
                full_hosted.verify_transport_archive(adverse_archive, candidate, target)

            adverse_capability = evidence / "adverse-capability"
            shutil.copytree(output, adverse_capability)
            metadata_path = (adverse_capability / "staged" / qualify.GROUP.replace(".", "/") /
                             name / qualify.VERSION / f"{name}-{qualify.VERSION}.module")
            metadata = qualify.load_json_strict(metadata_path)
            metadata["variants"][0]["capabilities"] = [{
                "group": qualify.GROUP, "name": "forged-capability",
                "version": qualify.VERSION,
            }]
            metadata_path.write_text(json.dumps(metadata, sort_keys=True) + "\n")
            metadata_path.with_name(metadata_path.name + ".sha256").write_text(
                full_hosted.sha256(metadata_path) + "\n")
            capability_receipt = qualify.load_json_strict(adverse_capability / "receipt.json")
            capability_receipt["files"] = full_hosted.archive_inventory(adverse_capability)
            (adverse_capability / "receipt.json").write_text(
                json.dumps(capability_receipt, sort_keys=True) + "\n")
            metadata_rejection = ("archived staged publication differs from content audit: .*"
                                  "metadata fields differ from publication contract")
            with self.assertRaisesRegex(ValueError, metadata_rejection) as capability_directory_error:
                full_hosted.verify_raw_files(adverse_capability, capability_receipt)
            capability_archive = evidence / "adverse-capability.tar"
            full_hosted.package_archive(adverse_capability, capability_archive)
            with self.assertRaisesRegex(ValueError, metadata_rejection) as capability_tar_error:
                full_hosted.verify_transport_archive(capability_archive, candidate, target)
            for rejected_bundle in (adverse_dokka, adverse_dokka_archive,
                                    unlisted_dokka, unlisted_archive,
                                    adverse, adverse_archive,
                                    adverse_capability, capability_archive):
                rejected = subprocess.run([*artifact_command, str(rejected_bundle)],
                                          cwd=clean, capture_output=True, text=True)
                self.assertEqual(1, rejected.returncode, rejected_bundle)
                self.assertIn("full hosted archive failed", rejected.stderr)
            adverse_record = subprocess.run([
                sys.executable, str(clean / "tools/qualification/qualify.py"), "record",
                "--candidate-sha", candidate, "--full-hosted-bundle",
                str(adverse_dokka_archive), "--output", str(evidence / "adverse-record.json")],
                cwd=clean, capture_output=True, text=True)
            self.assertEqual(2, adverse_record.returncode)
            self.assertIn("full hosted receipt failed", adverse_record.stderr)
            (evidence / "evidence.json").write_text(json.dumps({
                "synthetic": True, "real_hosted_runtime": False,
                "corpus_loader": "real_source_derived_candidate",
                "candidate_input_count": len(full_hosted.INPUTS),
                "reviewed_source_file_count": len(manifest["source_files"]),
                "candidate_sha": candidate, "target": target,
                "staged_files": 52, "configurations": list(full_hosted.CONFIGS[target]),
                "source_cases_per_configuration": {module: len(full_hosted.expected_cases(manifest, module))
                                                   for module in qualify.MODULES},
                "consumer_cases_per_configuration": len(consumer_cases),
                "positive_archive_sha256": full_hosted.sha256(archive),
                "process_order_archive_sha256": full_hosted.sha256(order_archive),
                "process_order_rejection": order_record.stderr.strip().splitlines()[-1],
                "process_order_qualification_report_written": adverse_order_report.exists(),
                "adverse_archive_sha256": full_hosted.sha256(adverse_archive),
                "adverse_directory_rejection": str(directory_error.exception),
                "adverse_tar_rejection": str(tar_error.exception),
                "capability_archive_sha256": full_hosted.sha256(capability_archive),
                "capability_directory_rejection": str(capability_directory_error.exception),
                "capability_tar_rejection": str(capability_tar_error.exception),
                "clean_checkout_cli": replay.stdout.strip(),
                "clean_checkout_directory_cli": directory_replay.stdout.strip(),
                "qualification_total_lanes": qualification["total"],
                "qualification_passed_lanes": qualification["counts"]["PASSED"],
                "qualification_receipt_status": scoped["status"],
                "rogue_local_dokka_cli": replay_with_rogue.stdout.strip(),
                "dokka_page_archive_sha256": full_hosted.sha256(adverse_dokka_archive),
                "dokka_page_rejection": adverse_replay.stderr.strip().splitlines()[-1],
                "unlisted_dokka_archive_sha256": full_hosted.sha256(unlisted_archive),
                "unlisted_dokka_rejection": unlisted_replay.stderr.strip().splitlines()[-1],
            }, indent=2, sort_keys=True) + "\n")

    def full_archive(self):
        repository = Path(__file__).resolve().parents[2]
        manifest = json.loads((repository / full_hosted.MANIFEST).read_text())
        consumer_manifest = json.loads((repository / "tools/qualification/foundation-probes.json").read_text())
        target = "mingwX64"
        now = time.time_ns()
        stage_window = (now - 60 * 10**9, now + 60 * 10**9)
        windows = {}
        boundary = stage_window[1]
        for configuration in full_hosted.CONFIGS[target]:
            for phase in ("source", "consumer", "graph"):
                windows[(configuration, phase)] = (boundary, boundary + 10 * 10**9)
                boundary += 10 * 10**9
        receipt = {"schema": 2, "kind": "hosted-full-common-corpus", "target": target,
                   "status": "FULL_COMMON_PASSED",
                   "manifest_sha256": full_hosted.canonical_hash(manifest),
                   "source_tree_sha256": manifest["source_tree_sha256"],
                   "map_sha256": full_hosted.sha256(repository / full_hosted.MAPPING),
                   "reviewed_pairs_sha256": full_hosted.sha256(repository / full_hosted.PAIRS),
                   "runtime": {"system": "Windows", "machine": "AMD64",
                               "os_version": "10.0.26100", "java_version": "21.0.1",
                               "gradle_version": "9.5.0", "kgp_declared_version": "2.4.20",
                               "agp_declared_version": "9.3.1"},
                   "github_run_id": "123", "github_job": "hosted-native", "runner_name": "runner",
                   "runner_os": "Windows", "runner_arch": "X64",
                   "archive_root": r"C:\runner\temp\full",
                   "repository_root": r"C:\runner\work\dyn4k",
                   "staging_repository": r"C:\runner\work\dyn4k\build\staging-repository",
                   "configurations": [], "artifact_hashes": {}}

        def write(path, data):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data if isinstance(data, bytes) else data.encode())
            parts = path.relative_to(self.root).parts
            if parts[0] == "stage":
                window = stage_window
            elif parts[0] in full_hosted.CONFIGS[target] and len(parts) > 2:
                phase = parts[1]
                if phase in ("xml", "executables"):
                    phase = "consumer" if parts[2] == "consumer" else "source"
                window = windows.get((parts[0], phase))
            else:
                window = None
            if window:
                modified = (window[0] + window[1]) // 2
                os.utime(path, ns=(modified, modified))
            return path

        def process(folder, invocation, task, output):
            write(folder / "stdout.txt", output + "\nBUILD SUCCESSFUL\n")
            write(folder / "stderr.txt", "")
            wrapper = str(PureWindowsPath(receipt["repository_root"]) / "gradlew.bat")
            if invocation is None:
                command = [wrapper, "--rerun-tasks", *[task for module in qualify.MODULES for task in (
                    f":{module}:publishKotlinMultiplatformPublicationToStagingRepository",
                    f":{module}:publishMingwX64PublicationToStagingRepository")]]
            else:
                command = [wrapper, "--rerun-tasks", task,
                           f"-PqualificationInvocationId={invocation}"]
                if folder.name == "source":
                    command += [f":dyn4k:{full_hosted.SOURCE_TASK[target]}",
                                "--init-script", str(PureWindowsPath(receipt["archive_root"]) /
                                                       folder.parent.name / "qualification.init.gradle")]
                else:
                    command += ["-p", str(PureWindowsPath(receipt["repository_root"]) /
                                          "consumers/qualification/portable"),
                                f"-PqualificationRepository={receipt['staging_repository']}"]
                if folder.name == "graph":
                    command += ["--init-script", str(PureWindowsPath(receipt["archive_root"]) /
                                                     folder.parent.name / "qualification-graph.init.gradle")]
            window = (stage_window if invocation is None
                      else windows[(folder.parent.name, folder.name)])
            return {"command": command, "pid": 42, "exit_code": 0,
                    "invocation_id": invocation, "started_ns": window[0],
                    "finished_ns": window[1],
                    "stdout_sha256": full_hosted.sha256(folder / "stdout.txt"),
                    "stderr_sha256": full_hosted.sha256(folder / "stderr.txt")}

        for path in full_hosted.INPUTS:
            full_hosted.archive_copy(repository / path, self.root, f"inputs/{path}")
        for source in manifest["source_files"]:
            full_hosted.archive_copy(repository / source["path"], self.root,
                                     f"sources/{source['path']}")
        candidate_directory = tempfile.TemporaryDirectory(prefix="candidate-",
                                                          dir=self.root.parent)
        self.addCleanup(candidate_directory.cleanup)
        self.candidate_repository = Path(candidate_directory.name)
        checkout_patch = mock.patch.object(full_hosted, "candidate_checkout",
                                           return_value=self.candidate_repository)
        checkout_patch.start()
        self.addCleanup(checkout_patch.stop)
        test_publication.PublicationAuditTests().stage(self.candidate_repository, (target,))
        self.align_synthetic_docs(self.candidate_repository, target)
        for relative in full_hosted.INPUTS:
            destination = self.candidate_repository / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repository / relative, destination)
        subprocess.run(["git", "init", "-q", str(self.candidate_repository)], check=True)
        subprocess.run(["git", "-C", str(self.candidate_repository), "config",
                        "core.autocrlf", "false"], check=True)
        subprocess.run(["git", "-C", str(self.candidate_repository), "add", "LICENSE.md",
                        "dyn4k-core/src", "dyn4k/src", "tools", "build.gradle.kts",
                        "consumers/qualification/portable/build.gradle.kts"], check=True)
        subprocess.run(["git", "-C", str(self.candidate_repository), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "commit", "-qm", "candidate"],
                       check=True)
        receipt["candidate_sha"] = subprocess.check_output(
            ["git", "-C", str(self.candidate_repository), "rev-parse", "HEAD"],
            text=True).strip()
        receipt["staged_gav"], _, staged_hashes, receipt["staged_content_contract"] = (
            full_hosted.artifact.capture_staging(self.candidate_repository, self.root,
                                                 [target], receipt["candidate_sha"]))
        receipt["artifact_hashes"] = staged_hashes[target]
        receipt["stage"] = process(self.root / "stage", None,
                                   ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
                                   "> Task :dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository")
        full_hosted.capture_dokka_output(self.candidate_repository, self.root, receipt)
        group = next(group for group in consumer_manifest["groups"] if group["id"] == "consumer-mingwX64")
        consumer_cases = qualify.expected_probe_cases(consumer_manifest, group)
        for index, config in enumerate(full_hosted.CONFIGS[target]):
            folder = self.root / config
            invocation = f"{index + 1:032x}"
            write(folder / "qualification.init.gradle", full_hosted.init_script(target, config))
            write(folder / "qualification-graph.init.gradle", full_hosted.graph_script(target))
            link = "Release" if config == "optimized-opt" else "Debug"
            source_tasks = "\n".join(f"> Task :{module}:link{link}TestMingwX64\n> Task :{module}:mingwX64Test" for module in qualify.MODULES)
            consumer_tasks = f"> Task :link{link}TestMingwX64\n> Task :mingwX64Test"
            lane = {"configuration": config, "status": "FULL_COMMON_PASSED",
                    "invocation_id": invocation,
                    "source_process": process(folder / "source", invocation,
                                              ":dyn4k-core:mingwX64Test", source_tasks),
                    "consumer_process": process(folder / "consumer", invocation,
                                                "mingwX64Test", consumer_tasks),
                    "source": [], "source_executables": {}}
            for module in qualify.MODULES:
                cases = [(f"mingwX64Test.{name}", f"{method}[mingwX64]")
                         for name, method in full_hosted.expected_cases(manifest, module)]
                suite = ET.Element("testsuite", tests=str(len(cases)), failures="0", errors="0",
                                   skipped="0", time="1")
                for classname, method in cases:
                    ET.SubElement(suite, "testcase", classname=classname, name=method, time="0.1")
                report = write(folder / "xml" / module / "TEST-all.xml", ET.tostring(suite))
                checked = full_hosted.read_reports(
                    [report], full_hosted.expected_cases(manifest, module), target,
                    *windows[(config, "source")])
                checked["module"] = module
                checked["reports"][0]["path"] = f"xml/{module}/TEST-all.xml"
                lane["source"].append(checked)
                product = write(folder / "executables" / module / "test.exe", b"test-" + module.encode())
                lane["source_executables"][module] = {"archive_path": product.relative_to(self.root).as_posix(),
                    "sha256": full_hosted.sha256(product), "size": product.stat().st_size,
                    "path": str(PureWindowsPath(receipt["repository_root"]) / module / "build/bin" /
                                target / ("releaseTest" if config == "optimized-opt" else "debugTest") /
                                "test.exe"),
                    "modified_ns": product.stat().st_mtime_ns}
            suite = ET.Element("testsuite", tests=str(len(consumer_cases)), failures="0", errors="0",
                               skipped="0", time="1")
            for classname, method in consumer_cases:
                ET.SubElement(suite, "testcase", classname=classname, name=method, time="0.1")
            report = write(folder / "xml/consumer/TEST-all.xml", ET.tostring(suite))
            lane["consumer"] = full_hosted.read_consumer_reports([report], set(consumer_cases),
                                                                    lane["consumer_process"])
            lane["consumer"]["reports"][0]["path"] = "xml/consumer/TEST-all.xml"
            product = write(folder / "executables/consumer/test.exe", b"test-consumer")
            lane["consumer_executable"] = {"archive_path": product.relative_to(self.root).as_posix(),
                "sha256": full_hosted.sha256(product), "size": product.stat().st_size,
                "path": str(PureWindowsPath(receipt["repository_root"]) /
                            "consumers/qualification/portable/build/bin" / target /
                            ("releaseTest" if config == "optimized-opt" else "debugTest") /
                            "test.exe"),
                "modified_ns": product.stat().st_mtime_ns}
            artifacts = []
            for module in qualify.MODULES:
                name = qualify.target_publication_name(module, target)
                binary = self.root / "staged" / qualify.target_binary_path(module, target)
                artifacts.append({"component": f"{qualify.GROUP}:{name}:{qualify.VERSION}",
                                  "file": str(PureWindowsPath(receipt["staging_repository"]) /
                                              qualify.target_binary_path(module, target)),
                                  "name": binary.name, "size": binary.stat().st_size,
                                  "sha256": full_hosted.sha256(binary)})
            graph = {"configuration": "mingwX64CompileKlibraries",
                     "components": [item["component"] for item in artifacts] +
                     [f"{qualify.GROUP}:{module}:{qualify.VERSION}" for module in qualify.MODULES],
                     "artifacts": artifacts}
            lane["graph_process"] = process(folder / "graph", invocation,
                                            "qualificationResolvedGraph",
                                            "DYN4K_RESOLVED_GRAPH=" + json.dumps(graph))
            lane["consumer_graph"] = graph
            lane["resolved_artifacts"] = []
            for graph_index, item in enumerate(artifacts):
                source = self.root / "staged" / qualify.target_binary_path(
                    "dyn4k-core" if "dyn4k-core" in item["name"] else "dyn4k", target)
                name = f"{config}/resolved-artifacts/{graph_index:03d}-{item['name']}"
                full_hosted.archive_copy(source, self.root, name)
                lane["resolved_artifacts"].append({**item, "archive_path": name})
            receipt["configurations"].append(lane)
        receipt["files"] = full_hosted.archive_inventory(self.root)
        return receipt, manifest, consumer_manifest

    def test_windows_fixture_source_archive_matches_candidate_with_autocrlf(self):
        config = self.root / "global-gitconfig"
        config.write_text("[core]\n\tautocrlf = true\n")
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(config)}):
            receipt, manifest, consumer = self.full_archive()
            full_hosted.verify_raw_files(
                self.root, receipt, manifest, consumer,
                candidate_repository=self.candidate_repository)

    def test_resealed_wrong_or_missing_toolchain_fails_directory_and_tar(self):
        receipt, manifest, consumer = self.full_archive()
        archive = self.root.parent / (self.root.name + ".tar")
        self.addCleanup(archive.unlink, missing_ok=True)
        pinned = {key: receipt["runtime"][key] for key in (
            "java_version", "gradle_version", "kgp_declared_version", "agp_declared_version")}
        changes = (("java_version", "17.0.1"), ("gradle_version", "8.0"),
                   ("kgp_declared_version", "1.9.0"), ("agp_declared_version", "8.0"))
        with mock.patch.object(full_hosted, "load_corpus", return_value=manifest):
            for key, wrong in changes + tuple((key, None) for key in pinned):
                with self.subTest(field=key, value=wrong):
                    if wrong is None:
                        receipt["runtime"].pop(key)
                    else:
                        receipt["runtime"][key] = wrong
                    with self.assertRaisesRegex(ValueError, "toolchain"):
                        full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)
                    (self.root / "receipt.json").write_text(json.dumps(receipt))
                    full_hosted.package_archive(self.root, archive)
                    with self.assertRaisesRegex(ValueError, "toolchain"):
                        full_hosted.verify_transport_archive(archive, receipt["candidate_sha"], "mingwX64")
                    receipt["runtime"][key] = pinned[key]

    def test_resealed_stale_process_logs_fail_directory_and_tar(self):
        receipt, manifest, consumer = self.full_archive()
        archive = self.root.parent / (self.root.name + ".tar")
        self.addCleanup(archive.unlink, missing_ok=True)
        paths = ("stage/stdout.txt", "debug-g/source/stderr.txt",
                 "optimized-opt/consumer/stdout.txt", "optimized-opt/graph/stderr.txt")
        with mock.patch.object(full_hosted, "load_corpus", return_value=manifest):
            for name in paths:
                with self.subTest(path=name):
                    path = self.root / name
                    original = path.stat().st_mtime_ns
                    os.utime(path, ns=(0, 0))
                    receipt["files"] = full_hosted.archive_inventory(self.root)
                    with self.assertRaisesRegex(ValueError, "process log timestamp"):
                        full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)
                    (self.root / "receipt.json").write_text(json.dumps(receipt))
                    full_hosted.package_archive(self.root, archive)
                    with self.assertRaisesRegex(ValueError, "process log timestamp"):
                        full_hosted.verify_transport_archive(archive, receipt["candidate_sha"], "mingwX64")
                    os.utime(path, ns=(original, original))
                    receipt["files"] = full_hosted.archive_inventory(self.root)

    def test_complete_archive_rejects_missing_configuration_and_synthetic_xml(self):
        receipt, manifest, consumer = self.full_archive()
        full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)
        removed = receipt["configurations"].pop()
        with self.assertRaisesRegex(ValueError, "configurations"):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)
        receipt["configurations"].append(removed)
        report = self.root / "debug-g/xml/dyn4k-core/TEST-all.xml"
        report.write_text("<testsuite tests='1'/>")
        receipt["files"] = full_hosted.archive_inventory(self.root)
        receipt["configurations"][0]["source"][0]["reports"][0].update(
            sha256=full_hosted.sha256(report), modified_ns=report.stat().st_mtime_ns)
        with self.assertRaisesRegex(ValueError, "XML|cases"):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)

    def test_complete_staged_publication_reaches_directory_and_transport_verifiers(self):
        receipt, manifest, consumer = self.full_archive()
        staged = [item for item in receipt["files"] if item["path"].startswith("staged/")]
        self.assertEqual(48, len(staged))
        full_hosted.verify_raw_files(self.root, receipt, manifest, consumer,
                                     candidate_repository=self.candidate_repository)
        (self.root / "receipt.json").write_text(json.dumps(receipt))
        archive = self.root.parent / (self.root.name + "-complete.tar")
        self.addCleanup(archive.unlink, missing_ok=True)
        full_hosted.package_archive(self.root, archive)
        with mock.patch.object(full_hosted, "load_corpus", return_value=manifest):
            full_hosted.verify_transport_archive(
                archive, receipt["candidate_sha"], "mingwX64",
                candidate_repository=self.candidate_repository)

    def test_resealed_staged_publication_mutations_fail_directory_and_tar(self):
        receipt, manifest, consumer = self.full_archive()
        base = self.root / "staged" / qualify.GROUP.replace(".", "/")
        name = qualify.target_publication_name("dyn4k-core", "mingwX64")
        files = {
            "sources": base / name / qualify.VERSION / f"{name}-{qualify.VERSION}-sources.jar",
            "docs": base / name / qualify.VERSION / f"{name}-{qualify.VERSION}-javadoc.jar",
            "license": base / name / qualify.VERSION / f"{name}-{qualify.VERSION}-license.md",
            "metadata": base / name / qualify.VERSION / f"{name}-{qualify.VERSION}.module",
        }
        archive = self.root.parent / (self.root.name + "-mutated.tar")
        self.addCleanup(archive.unlink, missing_ok=True)
        with mock.patch.object(full_hosted, "load_corpus", return_value=manifest):
            for label, path in files.items():
                for mutation in ("missing", "extra", "changed"):
                    with self.subTest(file=label, mutation=mutation):
                        original = path.read_bytes()
                        sidecar = path.with_name(path.name + ".sha256")
                        original_sidecar = sidecar.read_bytes()
                        extra = path.with_name(path.name + ".extra")
                        try:
                            if mutation == "missing":
                                path.unlink()
                                sidecar.unlink()
                            elif mutation == "extra":
                                extra.write_bytes(b"extra staged publication file")
                            else:
                                if label == "metadata":
                                    metadata = json.loads(original)
                                    metadata["component"]["url"] = "../../wrong/1/wrong.module"
                                    path.write_text(json.dumps(metadata))
                                else:
                                    path.write_bytes(original + b"\n")
                                sidecar.write_text(full_hosted.sha256(path) + "\n")
                            receipt["files"] = full_hosted.archive_inventory(self.root)
                            with self.assertRaises(ValueError):
                                full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)
                            (self.root / "receipt.json").write_text(json.dumps(receipt))
                            full_hosted.package_archive(self.root, archive)
                            with self.assertRaises(ValueError):
                                full_hosted.verify_transport_archive(
                                    archive, receipt["candidate_sha"], "mingwX64")
                        finally:
                            path.write_bytes(original)
                            sidecar.write_bytes(original_sidecar)
                            extra.unlink(missing_ok=True)

    def test_resealed_content_contract_and_wrong_candidate_fail(self):
        receipt, manifest, consumer = self.full_archive()
        contract = receipt.pop("staged_content_contract")
        with self.assertRaisesRegex(ValueError, "content contract is absent"):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)
        receipt["staged_content_contract"] = contract
        sources = receipt["staged_content_contract"]["sources"]["dyn4k-core"]
        original_source = sources["commonMain/api/Type.kt"]
        sources["commonMain/api/Type.kt"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "exact candidate"):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)
        sources["commonMain/api/Type.kt"] = original_source
        receipt["candidate_sha"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "candidate source is unavailable"):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)
        (self.root / "receipt.json").write_text(json.dumps(receipt))
        archive = self.root.parent / (self.root.name + "-wrong-candidate.tar")
        self.addCleanup(archive.unlink, missing_ok=True)
        full_hosted.package_archive(self.root, archive)
        with mock.patch.object(full_hosted, "load_corpus", return_value=manifest):
            with self.assertRaisesRegex(ValueError, "candidate source is unavailable"):
                full_hosted.verify_transport_archive(archive, "b" * 40, "mingwX64")

    def test_resealed_root_docs_contract_must_match_generated_checkout(self):
        receipt, manifest, consumer = self.full_archive()
        module = "dyn4k-core"
        jar = (self.root / "staged" / qualify.GROUP.replace(".", "/") / module /
               qualify.VERSION / f"{module}-{qualify.VERSION}-javadoc.jar")
        with zipfile.ZipFile(jar) as source:
            entries = [(info, source.read(info.filename)) for info in source.infolist()]
        with zipfile.ZipFile(jar, "w") as changed:
            for info, contents in entries:
                changed.writestr(info, b"<html>forged</html>" if info.filename == "index.html"
                                 else contents)
        jar.with_name(jar.name + ".sha256").write_text(full_hosted.sha256(jar) + "\n")
        receipt["staged_content_contract"]["api_docs_sha256"][module] = full_hosted.sha256(jar)
        receipt["files"] = full_hosted.archive_inventory(self.root)
        with self.assertRaisesRegex(ValueError, "Dokka"):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)

    def test_complete_archive_rejects_missing_consumer_graph_and_executable_tamper(self):
        receipt, manifest, consumer = self.full_archive()
        graph = self.root / "optimized-opt/graph/stdout.txt"
        graph_mtime = graph.stat().st_mtime_ns
        graph.write_text("BUILD SUCCESSFUL\n")
        os.utime(graph, ns=(graph_mtime, graph_mtime))
        receipt["files"] = full_hosted.archive_inventory(self.root)
        receipt["configurations"][1]["graph_process"]["stdout_sha256"] = full_hosted.sha256(graph)
        with self.assertRaisesRegex(ValueError, "graph observation"):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)
        receipt, manifest, consumer = self.full_archive()
        product = self.root / "debug-g/executables/dyn4k-core/test.exe"
        product.write_bytes(b"forged")
        receipt["files"] = full_hosted.archive_inventory(self.root)
        with self.assertRaisesRegex(ValueError, "test executable"):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)

    def test_complete_archive_rejects_duplicate_and_unsafe_paths(self):
        receipt, manifest, consumer = self.full_archive()
        receipt["files"].append(dict(receipt["files"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate archive path"):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)
        receipt["files"].pop()
        receipt["files"][0]["path"] = "../escape"
        with self.assertRaisesRegex(ValueError, "unsafe archive path"):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)

    def test_complete_archive_rejects_forged_stage_and_metadata(self):
        receipt, manifest, consumer = self.full_archive()
        receipt["stage"]["exit_code"] = 1
        with self.assertRaisesRegex(ValueError, "process exit"):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)
        receipt["stage"]["exit_code"] = 0
        name = qualify.target_publication_name("dyn4k", "mingwX64")
        path = (self.root / "staged" / qualify.GROUP.replace(".", "/") / name / qualify.VERSION /
                f"{name}-{qualify.VERSION}.pom")
        path.write_text("<project/>")
        receipt["files"] = full_hosted.archive_inventory(self.root)
        with self.assertRaisesRegex(ValueError, "POM identity"):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)

    def test_complete_archive_rejects_missing_consumer_provenance_and_extra_xml(self):
        receipt, manifest, consumer = self.full_archive()
        command = receipt["configurations"][0]["consumer_process"]["command"]
        command[:] = [item for item in command if not item.startswith("-PqualificationRepository=")]
        with self.assertRaisesRegex(ValueError, "repository provenance"):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)
        command.append(f"-PqualificationRepository={receipt['staging_repository']}")
        extra = self.root / "optimized-opt/xml/consumer/TEST-extra.xml"
        extra.write_text("<testsuite tests='0'/>")
        receipt["files"] = full_hosted.archive_inventory(self.root)
        with self.assertRaisesRegex(ValueError, "extra or missing XML"):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)

    def test_resealed_process_windows_reject_each_cross_phase_overlap(self):
        receipt, manifest, consumer = self.full_archive()
        lane = receipt["configurations"][0]
        mutations = (
            (lane["source_process"], "started_ns", receipt["stage"]["finished_ns"] - 1),
            (lane["consumer_process"], "started_ns",
             lane["source_process"]["finished_ns"] - 1),
            (lane["graph_process"], "started_ns",
             lane["consumer_process"]["finished_ns"] - 1),
        )
        for process, field, forged in mutations:
            with self.subTest(process=process["command"]):
                original = process[field]
                process[field] = forged
                try:
                    with self.assertRaisesRegex(ValueError, "process order"):
                        full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)
                finally:
                    process[field] = original
        lane["source_process"]["started_ns"] = 0
        with self.assertRaisesRegex(ValueError, "process exit, identity, or timestamps"):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)

    def test_complete_archive_rejects_resealed_resolved_dependency_bytes(self):
        receipt, manifest, consumer = self.full_archive()
        path = self.root / receipt["configurations"][1]["resolved_artifacts"][0]["archive_path"]
        path.write_bytes(b"forged dependency")
        receipt["files"] = full_hosted.archive_inventory(self.root)
        with self.assertRaisesRegex(ValueError, "resolved dependency artifact bytes"):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer)

    def test_verify_cli_reads_receipt_and_rechecks_archive(self):
        receipt, manifest, _ = self.full_archive()
        (self.root / "receipt.json").write_text(json.dumps(receipt))
        arguments = ["full_hosted.py", "--verify", "--candidate-sha", receipt["candidate_sha"],
                     "--target", "mingwX64", "--output", str(self.root)]
        with mock.patch.object(sys, "argv", arguments), mock.patch.object(
                full_hosted, "load_corpus", return_value=manifest):
            self.assertEqual(0, full_hosted.main())
            receipt["configurations"].pop()
            (self.root / "receipt.json").write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, "configurations"):
                full_hosted.main()

    def test_transport_archive_round_trip_and_duplicate_rejection(self):
        receipt, manifest, _ = self.full_archive()
        (self.root / "receipt.json").write_text(json.dumps(receipt))
        archive = self.root.parent / (self.root.name + ".tar")
        self.addCleanup(archive.unlink, missing_ok=True)
        full_hosted.package_archive(self.root, archive)
        with mock.patch.object(full_hosted, "load_corpus", return_value=manifest):
            full_hosted.verify_transport_archive(archive, receipt["candidate_sha"], "mingwX64")
            arguments = ["full_hosted.py", "--verify-tar", "--candidate-sha", receipt["candidate_sha"],
                         "--target", "mingwX64", "--archive", str(archive)]
            with mock.patch.object(sys, "argv", arguments):
                self.assertEqual(0, full_hosted.main())
        with tarfile.open(archive, "a") as packed:
            info = tarfile.TarInfo("receipt.json")
            info.size = 0
            info.pax_headers = {"dyn4k.mtime_ns": "1"}
            packed.addfile(info)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            full_hosted.verify_transport_archive(archive, receipt["candidate_sha"], "mingwX64")
        full_hosted.package_archive(self.root, archive)
        with tarfile.open(archive, "a") as packed:
            info = tarfile.TarInfo("../escape")
            info.size = 0
            info.pax_headers = {"dyn4k.mtime_ns": "1"}
            packed.addfile(info)
        with self.assertRaisesRegex(ValueError, "unsafe archive path"):
            full_hosted.verify_transport_archive(archive, receipt["candidate_sha"], "mingwX64")
        full_hosted.package_archive(self.root, archive)
        altered_time = self.root.parent / (self.root.name + "-pax.tar")
        self.addCleanup(altered_time.unlink, missing_ok=True)
        with tarfile.open(archive, "r") as source, tarfile.open(altered_time, "w") as changed:
            for member in source:
                stream = source.extractfile(member)
                if member.name == "receipt.json":
                    member.mtime += 1
                    member.pax_headers["mtime"] = str(member.mtime)
                changed.addfile(member, stream)
        with self.assertRaisesRegex(ValueError, "PAX timestamp differs"):
            full_hosted.verify_transport_archive(
                altered_time, receipt["candidate_sha"], "mingwX64")

if __name__ == "__main__":
    unittest.main()
