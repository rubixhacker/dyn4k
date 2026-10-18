import base64
import hashlib
import io
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
import zlib
from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest import mock

import full_hosted
import qualify
import test_publication
from test_safari_yarn_lock import git_oid, replace_loose_object, write_loose_object


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

    def make_staged_binary_sha1_leading_zero(self, repository, target):
        binary = (repository / "build/staging-repository" /
                  qualify.target_binary_path("dyn4k-core", target))
        with zipfile.ZipFile(binary) as original:
            members = {name: original.read(name) for name in original.namelist()}
        for nonce in range(256):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                for name, contents in members.items():
                    archive.writestr(name, contents + str(nonce).encode()
                                     if name == "default/ir/bodies.knb" else contents)
            contents = buffer.getvalue()
            digest = hashlib.sha1(contents).hexdigest()
            if digest.startswith("0") and not digest.startswith("00"):
                break
        else:
            self.fail("could not create a synthetic leading-zero KLIB")
        binary.write_bytes(contents)
        binary.with_name(binary.name + ".sha256").write_text(
            hashlib.sha256(contents).hexdigest() + "\n")
        metadata_path = binary.with_suffix(".module")
        metadata = json.loads(metadata_path.read_text())
        for variant in metadata["variants"]:
            for reference in variant.get("files", []):
                if reference["url"] == binary.name:
                    reference["size"] = len(contents)
                    for algorithm in ("sha512", "sha256", "sha1", "md5"):
                        reference[algorithm] = hashlib.new(algorithm, contents).hexdigest()
        metadata_path.write_text(json.dumps(metadata))
        metadata_path.with_name(metadata_path.name + ".sha256").write_text(
            full_hosted.sha256(metadata_path) + "\n")
        return hashlib.sha1(contents).hexdigest()

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

    @staticmethod
    def safari_diagnostic_rows():
        # Exact system-out from the retained 5758 JS browser XML (source XML SHA-256
        # 95e8a8e550b3cf6172f97cc74453595da3e0d9d68e43a31fed9be5acf1285a56).
        fixture = (Path(__file__).parent / "fixtures/safari-v2-diagnostics.b85").read_bytes()
        output = zlib.decompress(base64.b85decode(b"".join(fixture.splitlines())))
        if hashlib.sha256(output).hexdigest() != \
                "b3b22a31a8d4b9581bb44c4763474eb0c857e075564b763cbb6fd92c631bcf54":
            raise ValueError("real browser diagnostic fixture bytes differ")
        return output.decode("utf-8").splitlines(keepends=True)

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

    def failed_safari_source_reports(self, repository):
        started = time.time_ns()
        expected = {}
        paths = {}
        for module in qualify.MODULES:
            report = (repository / module / "build/test-results/jsBrowserTest/TEST-all.xml")
            report.parent.mkdir(parents=True)
            if module == "dyn4k-core":
                classname = full_hosted.SAFARI_DIAGNOSTIC_CLASS
                methods = tuple(full_hosted.SAFARI_DIAGNOSTIC_CASES)
                expected[module] = {(classname, method) for method in methods}
                suite = ET.Element("testsuite", tests=str(len(methods)), failures="0",
                                   errors="0", skipped="0", time="1")
                for method in methods:
                    actual = "capsuleSliceUnexpected" if method == "capsuleSlice" else method
                    ET.SubElement(suite, "testcase", classname=f"jsBrowserTest.{classname}",
                                  name=f"{actual}[js, browser, Safari26.6.2, MacOS10.15.7]",
                                  time="0.1")
                ET.SubElement(suite, "system-out").text = "".join(
                    self.safari_diagnostic_rows())
            else:
                classname = "org.dyn4j.geometry.ExampleTest"
                expected[module] = {(classname, "works")}
                suite = ET.Element("testsuite", tests="1", failures="0", errors="0",
                                   skipped="0", time="1")
                ET.SubElement(suite, "testcase", classname=f"jsBrowserTest.{classname}",
                              name="works[js, browser, Safari26.6.2, MacOS10.15.7]",
                              time="0.1")
            report.write_bytes(ET.tostring(suite))
            paths[module] = report
        process = {"command": ["gradlew", "--rerun-tasks", ":dyn4k-core:jsBrowserTest",
                               ":dyn4k:jsBrowserTest",
                               "-PqualificationInvocationId=" + "1" * 32],
                   "pid": os.getpid(), "exit_code": 0,
                   "invocation_id": "1" * 32, "started_ns": started,
                   "finished_ns": time.time_ns()}
        return expected, paths, process

    def test_failed_safari_identity_retains_unverified_source_xml_in_archive(self):
        for configuration in full_hosted.CONFIGS["jsSafari"]:
            with self.subTest(configuration=configuration):
                repository = self.root / f"source-{configuration}"
                expected, paths, process = self.failed_safari_source_reports(repository)
                output = self.root / f"output-{configuration}"
                folder = output / configuration
                folder.mkdir(parents=True)
                lane = {"configuration": configuration, "source_process": process}
                with mock.patch.object(full_hosted, "expected_cases",
                                       side_effect=lambda unused, module: expected[module]):
                    with self.assertRaisesRegex(ValueError,
                                                "Safari diagnostic case identities differ"):
                        full_hosted.copy_reports(repository, "jsSafari", folder, process, {},
                                                 "26.6.2", diagnostic=lane)
                diagnostic = lane["source_xml_diagnostic"]
                self.assertEqual("UNVERIFIED", diagnostic["status"])
                self.assertEqual("Safari diagnostic case identities differ",
                                 diagnostic["validation_error"])
                self.assertEqual(process["pid"], diagnostic["source_pid"])
                self.assertEqual(process["invocation_id"], diagnostic["invocation_id"])
                self.assertEqual(set(paths), {item["module"] for item in diagnostic["reports"]})
                for item in diagnostic["reports"]:
                    retained = folder / item["path"]
                    original = paths[item["module"]]
                    self.assertEqual(original.read_bytes(), retained.read_bytes())
                    self.assertEqual(full_hosted.sha256(original), item["sha256"])
                    self.assertEqual(original.stat().st_mtime_ns, item["modified_ns"])
                    self.assertTrue(item["path"].startswith("diagnostic/source-xml/"))
                lane.update(status="FAILED", reason=diagnostic["validation_error"])
                receipt = {"schema": 2, "kind": "hosted-full-common-corpus",
                           "candidate_sha": "a" * 40, "target": "jsSafari", "status": "FAILED",
                           "configurations": [lane]}
                receipt["files"] = full_hosted.archive_inventory(output)
                (output / "receipt.json").write_text(json.dumps(receipt))
                archive = self.root / f"failed-{configuration}.tar"
                full_hosted.package_archive(output, archive)
                with tarfile.open(archive, "r") as packed:
                    archived = json.load(packed.extractfile("receipt.json"))
                    self.assertEqual("FAILED", archived["status"])
                    self.assertEqual("UNVERIFIED", archived["configurations"][0]
                                     ["source_xml_diagnostic"]["status"])
                    for item in diagnostic["reports"]:
                        member = packed.extractfile(f"{configuration}/{item['path']}")
                        self.assertEqual(paths[item["module"]].read_bytes(), member.read())
                with self.assertRaisesRegex(ValueError, "not a completed target"):
                    full_hosted.verify_transport_archive(archive, "a" * 40, "jsSafari")

    def test_failed_safari_identity_diagnostic_rejects_unsafe_source_xml(self):
        for mutation in ("stale", "symlink", "oversized", "crowded",
                         "failed-process", "missing-invocation"):
            with self.subTest(mutation=mutation):
                repository = self.root / f"unsafe-{mutation}"
                expected, paths, process = self.failed_safari_source_reports(repository)
                report = paths["dyn4k"]
                if mutation == "stale":
                    os.utime(report, ns=(process["started_ns"] - 1,
                                         process["started_ns"] - 1))
                elif mutation == "symlink":
                    outside = self.root / "outside.xml"
                    outside.write_bytes(report.read_bytes())
                    report.unlink()
                    report.symlink_to(outside)
                elif mutation == "oversized":
                    with report.open("wb") as stream:
                        stream.truncate(32 * 1024 * 1024 + 1)
                    process["finished_ns"] = time.time_ns()
                elif mutation == "crowded":
                    for index in range(129):
                        (report.parent / f"extra-{index:03d}.txt").write_bytes(b"x")
                elif mutation == "failed-process":
                    process["exit_code"] = 1
                else:
                    process["invocation_id"] = None
                folder = self.root / f"failure-{mutation}" / "development"
                folder.mkdir(parents=True)
                lane = {}
                with mock.patch.object(full_hosted, "expected_cases",
                                       side_effect=lambda unused, module: expected[module]):
                    with self.assertRaisesRegex(ValueError,
                                                "Safari diagnostic case identities differ"):
                        full_hosted.copy_reports(repository, "jsSafari", folder, process, {},
                                                 "26.6.2", diagnostic=lane)
                self.assertEqual("UNAVAILABLE", lane["source_xml_diagnostic"]["status"])
                self.assertFalse((folder / "diagnostic/source-xml").exists())

    def test_failed_safari_identity_rejects_linked_diagnostic_destination(self):
        for configuration in full_hosted.CONFIGS["jsSafari"]:
            with self.subTest(configuration=configuration):
                repository = self.root / f"linked-source-{configuration}"
                expected, _, process = self.failed_safari_source_reports(repository)
                output = self.root / f"linked-output-{configuration}"
                folder = output / configuration
                folder.mkdir(parents=True)
                outside = self.root / f"outside-destination-{configuration}"
                outside.mkdir()
                (folder / "diagnostic").symlink_to(outside, target_is_directory=True)
                lane = {"configuration": configuration, "source_process": process}
                with mock.patch.object(full_hosted, "expected_cases",
                                       side_effect=lambda unused, module: expected[module]):
                    with self.assertRaisesRegex(ValueError,
                                                "Safari diagnostic case identities differ"):
                        full_hosted.copy_reports(repository, "jsSafari", folder, process, {},
                                                 "26.6.2", diagnostic=lane)
                self.assertEqual("UNAVAILABLE", lane["source_xml_diagnostic"]["status"])
                self.assertEqual([], list(outside.iterdir()))
                self.assertFalse((folder / "diagnostic").is_symlink())
                lane.update(status="FAILED", reason="Safari diagnostic case identities differ")
                receipt = {"schema": 2, "kind": "hosted-full-common-corpus",
                           "candidate_sha": "a" * 40, "target": "jsSafari", "status": "FAILED",
                           "configurations": [lane]}
                receipt["files"] = full_hosted.archive_inventory(output)
                (output / "receipt.json").write_text(json.dumps(receipt))
                archive = self.root / f"linked-failed-{configuration}.tar"
                full_hosted.package_archive(output, archive)
                with tarfile.open(archive, "r") as packed:
                    archived = json.load(packed.extractfile("receipt.json"))
                    self.assertEqual("FAILED", archived["status"])
                    self.assertEqual("UNAVAILABLE", archived["configurations"][0]
                                     ["source_xml_diagnostic"]["status"])

    @unittest.skipIf(os.name == "nt", "POSIX directory exchange control")
    def test_failed_safari_identity_rejects_exchanged_diagnostic_parent(self):
        repository = self.root / "exchanged-source"
        expected, _, process = self.failed_safari_source_reports(repository)
        output = self.root / "exchanged-output"
        folder = output / "development"
        folder.mkdir(parents=True)
        diagnostic = folder / "diagnostic"
        outside = self.root / "exchanged-outside"
        lane = {"configuration": "development", "source_process": process}
        rename = os.rename
        exchanged = []

        def exchange_before_publish(source, target, *args, **kwargs):
            if (not exchanged and isinstance(source, str)
                    and source.startswith(".source-xml-") and target == "source-xml"
                    and "src_dir_fd" in kwargs):
                exchanged.append(True)
                diagnostic.rename(outside)
                diagnostic.symlink_to(outside, target_is_directory=True)
            return rename(source, target, *args, **kwargs)

        with mock.patch.object(full_hosted, "expected_cases",
                               side_effect=lambda unused, module: expected[module]), \
                mock.patch.object(full_hosted.os, "rename",
                                  side_effect=exchange_before_publish):
            with self.assertRaisesRegex(ValueError,
                                        "Safari diagnostic case identities differ"):
                full_hosted.copy_reports(repository, "jsSafari", folder, process, {},
                                         "26.6.2", diagnostic=lane)
        self.assertTrue(exchanged)
        self.assertEqual("UNAVAILABLE", lane["source_xml_diagnostic"]["status"])
        self.assertEqual([], list(outside.rglob("*.xml")))
        self.assertFalse(diagnostic.is_symlink())
        receipt = {"schema": 2, "kind": "hosted-full-common-corpus",
                   "candidate_sha": "a" * 40, "target": "jsSafari", "status": "FAILED",
                   "configurations": [lane]}
        receipt["files"] = full_hosted.archive_inventory(output)
        (output / "receipt.json").write_text(json.dumps(receipt))
        archive = self.root / "exchanged-failed.tar"
        full_hosted.package_archive(output, archive)
        with tarfile.open(archive, "r") as packed:
            self.assertEqual("FAILED", json.load(packed.extractfile("receipt.json"))["status"])

    def test_public_safari_route_stages_and_archives_source_and_consumer_reporters(self):
        source_tree = Path(__file__).resolve().parents[2]
        alias = self.root / "temporary-path-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.root = alias
        for configuration in ("development", "production", "missing", "symlink"):
            with self.subTest(configuration=configuration):
                repository = (self.root / f"source-{configuration}").resolve()
                consumer = repository / "consumers/qualification/portable"
                for project in ("dyn4k-core", "dyn4k"):
                    (repository / project).mkdir(parents=True)
                consumer.mkdir(parents=True)
                for relative in ("tools/qualification/safari-karma-reporter.js",
                                 "tools/qualification/safari_reporter.py"):
                    destination = repository / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_tree / relative, destination)
                for relative in (full_hosted.MAPPING, full_hosted.PAIRS):
                    destination = repository / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text("fixture\n")
                (repository / "build.gradle.kts").write_text(
                    'kotlin("multiplatform") version "2.4.20"\n'
                    'id("com.android.kotlin.multiplatform.library") version "9.3.1"\n')
                (repository / "gradlew").write_text("#!/bin/sh\n")
                subprocess.run(["git", "init", "-q", str(repository)], check=True)
                subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
                subprocess.run(["git", "-C", str(repository), "-c", "user.name=Fixture",
                                "-c", "user.email=fixture@example.invalid", "commit", "-qm",
                                "candidate"], check=True)
                candidate = subprocess.check_output(
                    ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
                fragment = full_hosted.safari_reporter.committed_fragment(repository, candidate)

                def generated_config(project, package, mode):
                    build_root = consumer if project == "consumer" else repository
                    root = consumer if project == "consumer" else repository / project
                    folder = build_root / "build/js/packages" / package
                    folder.mkdir(parents=True, exist_ok=True)
                    runner = str(build_root / "build/js/node_modules/kotlin-web-helpers/dist"
                                 / "kotlin-test-karma-runner.js")
                    selected = (str(root / "build/compileSync/js/test/testProductionExecutable"
                                    / "kotlin" / f"{package}.js") if mode == "production"
                                else str(folder / "kotlin" / f"{package}.js"))
                    settings = {"singleRun": True, "autoWatch": False,
                                "basePath": str(folder), "files": [runner, selected],
                                "frameworks": ["webpack-output", "mocha", "webpack"],
                                "client": {"args": []}, "browsers": ["Safari"],
                                "customLaunchers": {}, "failOnFailingTestSuite": False,
                                "failOnEmptyTestSuite": False,
                                "reporters": ["karma-kotlin-reporter"],
                                "preprocessors": {runner: ["webpack", "sourcemap"],
                                                  selected: ["webpack", "sourcemap"]},
                                "proxies": {}, "webpackCopy": []}
                    config_prefix = (
                        "\nmodule.exports = function(config) {\n\nconfig.set("
                        + json.dumps(settings) + ");"
                        + full_hosted.safari_reporter.APPROVED_GENERATOR_TAIL).encode("utf-8")
                    (folder / "karma.conf.js").write_bytes(config_prefix + fragment + b"\n}\n")
                    product, selected_product, _, _ = full_hosted.safari_product_paths(
                        root, mode, project)
                    product.parent.mkdir(parents=True, exist_ok=True)
                    product.write_bytes(b"linked")
                    selected_product.parent.mkdir(parents=True, exist_ok=True)
                    selected_product.write_bytes(b"linked")
                    if (configuration == "symlink" and project == "dyn4k-core"
                            and not folder.is_symlink()):
                        outside = self.root / "outside-symlink-generated"
                        folder.rename(outside)
                        folder.symlink_to(outside, target_is_directory=True)

                calls = []

                def command(command, cwd, destination, invocation_id=None):
                    started = time.time_ns()
                    destination.mkdir(parents=True, exist_ok=True)
                    (destination / "stdout.txt").write_text("BUILD SUCCESSFUL\n")
                    (destination / "stderr.txt").write_text("")
                    calls.append(destination.name)
                    if destination.name == "source":
                        for module in ("dyn4k-core", "dyn4k"):
                            self.assertEqual(fragment,
                                (repository / module / "karma.config.d"
                                 / "qualification-safari-reporter.js").read_bytes())
                            if configuration != "missing" or module == "dyn4k-core":
                                generated_config(module, f"dyn4k-{module}-test",
                                                 destination.parent.name)
                        self.assertFalse((consumer / "karma.config.d").exists())
                    elif destination.name == "consumer":
                        staged = consumer / "karma.config.d/qualification-safari-reporter.js"
                        self.assertEqual(fragment, staged.read_bytes())
                        self.assertFalse((repository / "dyn4k-core/karma.config.d").exists())
                        self.assertFalse((repository / "dyn4k/karma.config.d").exists())
                        generated_config("consumer", "dyn4k-staged-portable-consumer-test",
                                         destination.parent.name)
                        if configuration == "production":
                            staged.write_bytes(b"config.plugins = [];\n")
                    return {"command": command, "pid": 123, "exit_code": 0,
                            "started_ns": started, "finished_ns": time.time_ns(),
                            "stdout_sha256": full_hosted.sha256(destination / "stdout.txt"),
                            "stderr_sha256": full_hosted.sha256(destination / "stderr.txt")}

                def tasks(process, folder, target, mode, modules):
                    if modules == ("",):
                        raise ValueError("fixture stops after Safari consumer capture")

                hashes = {"dyn4k-core": "a" * 64, "dyn4k": "b" * 64}
                output = self.root / f"archive-{configuration}"
                manifest = {"source_files": [], "source_tree_sha256": "c" * 64}
                runtime = {"system": "Darwin", "machine": "arm64", "java_version": "21.0.12",
                           "safari_version": "26.6.2"}
                with mock.patch.object(full_hosted, "__file__", str(repository /
                                       "tools/qualification/full_hosted.py")), \
                        mock.patch.object(full_hosted, "INPUTS", (
                            "tools/qualification/safari-karma-reporter.js",
                            "tools/qualification/safari_reporter.py")), \
                        mock.patch.object(full_hosted, "load_corpus", return_value=manifest), \
                        mock.patch.object(full_hosted.hosted, "discover_runtime", return_value=runtime), \
                        mock.patch.object(full_hosted.hosted, "runtime_status",
                                          return_value=("READY", "")), \
                        mock.patch.object(full_hosted.hosted, "gradle_wrapper",
                                          return_value=str(repository / "gradlew")), \
                        mock.patch.object(full_hosted.hosted, "tool_version", return_value="9.5.0"), \
                        mock.patch.object(full_hosted, "run_command", side_effect=command), \
                        mock.patch.object(full_hosted.hosted, "target_hashes", return_value=hashes), \
                        mock.patch.object(full_hosted.artifact, "capture_staging",
                                          return_value=({}, None, {"js": hashes}, {})), \
                        mock.patch.object(full_hosted, "capture_dokka_output"), \
                        mock.patch.object(full_hosted, "copy_reports", return_value=[]), \
                        mock.patch.object(full_hosted, "require_test_tasks", side_effect=tasks):
                    receipt = full_hosted.run("jsSafari", candidate, output)
                self.assertEqual((["stage", "source", "source"] if configuration == "missing"
                                  else ["stage", "source", "source"] if configuration == "symlink"
                                  else ["stage", "source", "consumer", "source", "consumer"]),
                                 calls)
                self.assertEqual("FAILED", receipt["status"])
                for lane in receipt["configurations"]:
                    if configuration == "symlink":
                        self.assertTrue(lane["reason"].startswith(
                            "Safari generated Karma config is absent or unsafe:") or
                            lane["reason"].startswith("unsafe Safari path or file type:"),
                            lane["reason"])
                        self.assertEqual("CLEAN", lane["safari_reporter_stage"]
                                         ["source"]["status"])
                        self.assertTrue((repository / "build/js/packages"
                                         / "dyn4k-dyn4k-core-test").is_symlink())
                        self.assertFalse((output / lane["configuration"] / "karma-config"
                                          / "dyn4k-core/karma.conf.js").exists())
                    else:
                        self.assertIn(("Safari generated Karma config is absent"
                                       if configuration == "missing" else
                                       "staged Safari consumer reporter changed"
                                       if configuration == "production" else
                                       "fixture stops after Safari consumer capture"),
                                      lane["reason"])
                    for module in (() if configuration == "symlink" else
                                   ("dyn4k-core",) if configuration == "missing" else
                                   ("dyn4k-core", "dyn4k") if configuration == "production"
                                   else ("dyn4k-core", "dyn4k", "consumer")):
                        self.assertIn(fragment,
                            (output / lane["configuration"] / "karma-config"
                             / module / "karma.conf.js").read_bytes())
                    if configuration == "production":
                        self.assertEqual(b"config.plugins = [];\n",
                            (output / lane["configuration"] / "forensic/safari-reporter"
                             / "consumers/qualification/portable"
                             / "qualification-safari-reporter.js").read_bytes())
                        self.assertEqual("CHANGED", lane["safari_reporter_stage"]["consumer"]
                                         ["status"])
                for root in (repository / "dyn4k-core", repository / "dyn4k", consumer):
                    self.assertFalse((root / "karma.config.d").exists())

    def test_committed_manifest_bytes_reject_source_drift(self):
        file = self.root / "tools/qualification/full-common-corpus.json"
        file.parent.mkdir(parents=True)
        file.write_bytes(b"sealed")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", str(file)], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit", "-qm",
                        "sealed source"], check=True)
        candidate = git_oid(self.root, "HEAD")
        self.assertEqual(b"sealed", full_hosted.committed_input(
            self.root, candidate, full_hosted.MANIFEST))
        file.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "candidate source differs"):
            full_hosted.committed_input(self.root, candidate, full_hosted.MANIFEST)

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

    def test_mac_product_selects_direct_executable_beside_dsym(self):
        for configuration, mode in (("debug-g", "debugTest"),
                                    ("optimized-opt", "releaseTest")):
            with self.subTest(configuration=configuration):
                project = self.root / configuration
                directory = project / "build/bin/macosArm64" / mode
                direct = directory / "test.kexe"
                dwarf = (directory / "test.kexe.dSYM/Contents/Resources/DWARF/test.kexe")
                started = time.time_ns()
                direct.parent.mkdir(parents=True)
                direct.write_bytes(b"linked executable")
                dwarf.parent.mkdir(parents=True)
                dwarf.write_bytes(b"DWARF debug symbols")
                process = {"started_ns": started, "finished_ns": time.time_ns(),
                           "invocation_id": "synthetic", "exit_code": 0}
                diagnostic_root = self.root / f"failed-{configuration}"
                diagnostic = diagnostic_root / "product-inventory.json"
                selected = full_hosted.collect_test_products(
                    {"dyn4k-core": project}, "macosArm64", configuration,
                    process, diagnostic, diagnostic_root)
                self.assertEqual(str(direct), selected["dyn4k-core"]["path"])
                self.assertEqual(full_hosted.sha256(direct),
                                 selected["dyn4k-core"]["sha256"])
                self.assertNotEqual(full_hosted.sha256(dwarf),
                                    selected["dyn4k-core"]["sha256"])
                self.assertFalse(diagnostic.exists())
                with self.assertRaisesRegex(ValueError, "predates invocation"):
                    full_hosted.test_products(
                        project, "macosArm64", configuration,
                        {"started_ns": direct.stat().st_mtime_ns + 1,
                         "finished_ns": process["finished_ns"] + 1})
                wrong_configuration = ("optimized-opt" if configuration == "debug-g"
                                       else "debug-g")
                for wrong_target, wrong_mode in (("iosArm64", configuration),
                                                 ("macosArm64", wrong_configuration)):
                    with self.assertRaisesRegex(ValueError, "exactly one"):
                        full_hosted.test_products(project, wrong_target, wrong_mode, process)

                duplicate = directory / "duplicate.kexe"
                duplicate.write_bytes(b"second direct executable")
                with self.assertRaisesRegex(ValueError, "exactly one.*product inventory"):
                    full_hosted.collect_test_products(
                        {"dyn4k-core": project}, "macosArm64", configuration,
                        process, diagnostic, diagnostic_root)
                self.assertTrue(diagnostic.exists())
                entries = json.loads(diagnostic.read_text())["projects"]["dyn4k-core"]["entries"]
                self.assertIn(dwarf.relative_to(project).as_posix(),
                              {entry["path"] for entry in entries})
                duplicate.unlink()
                direct.unlink()
                with self.assertRaisesRegex(ValueError, "exactly one"):
                    full_hosted.test_products(project, "macosArm64", configuration, process)

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

    def test_missing_safari_product_retains_compiler_and_karma_layouts(self):
        repository = self.root / "repository"
        project = repository / "dyn4k-core"
        package = repository / "build/js/packages/dyn4k-dyn4k-core-test"
        bundle = package / "kotlin/dyn4k-dyn4k-core-test.js"
        bundle.parent.mkdir(parents=True)
        bundle.write_bytes(b"Karma development input")
        alternate = (project / "build/compileSync/js/test/testProductionExecutable"
                     / "alternate/dyn4k-dyn4k-core-test.js")
        alternate.parent.mkdir(parents=True)
        alternate.write_bytes(b"Mac layout candidate")
        output = self.root / "failed-safari"
        output.mkdir()
        (output / "receipt.json").write_text("{}")
        process = {"started_ns": 1, "finished_ns": time.time_ns() + 10**9,
                   "invocation_id": "safari-invocation", "exit_code": 0}
        for mode in ("development", "production"):
            diagnostic = output / mode / "product-inventory-source.json"
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "product inventory"):
                full_hosted.collect_test_products(
                    {"dyn4k-core": project}, "jsSafari", mode, process,
                    diagnostic, output)
            record = json.loads(diagnostic.read_text())["projects"]["dyn4k-core"]
            self.assertEqual(str(project / "build/compileSync/js/test" /
                                 ("testDevelopmentExecutable" if mode == "development"
                                  else "testProductionExecutable") / "kotlin" /
                                 "dyn4k-dyn4k-core-test.js"), record["expected"])
            self.assertEqual(str(bundle if mode == "development" else record["expected"]),
                             record["karma_input"])
            roots = record["roots"]
            self.assertIn("compiler", roots)
            self.assertIn("karma_package", roots)
            self.assertEqual(full_hosted.sha256(bundle), next(
                entry["sha256"] for entry in roots["karma_package"]["entries"]
                if entry["path"].endswith("/kotlin/dyn4k-dyn4k-core-test.js")))
            self.assertIn(str(alternate), {str(project / entry["path"])
                for entry in roots["compiler"]["entries"] if entry["kind"] == "file"})
        archive = self.root / "failed-safari.tar"
        full_hosted.package_archive(output, archive)
        with tarfile.open(archive) as packed:
            self.assertIn("development/product-inventory-source.json", packed.getnames())
            self.assertIn("production/product-inventory-source.json", packed.getnames())

    def test_safari_product_inventory_does_not_follow_symlinked_package(self):
        repository = self.root / "repository"
        project = repository / "dyn4k-core"
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "secret.js").write_bytes(b"outside")
        package = repository / "build/js/packages/dyn4k-dyn4k-core-test"
        package.parent.mkdir(parents=True)
        package.symlink_to(outside, target_is_directory=True)
        record = full_hosted.product_inventory(project, "jsSafari", "development",
                                               "dyn4k-core")
        self.assertFalse(record["roots"]["karma_package"]["present"])
        self.assertTrue(record["roots"]["karma_package"]["unsafe_symlink"])
        self.assertEqual([], record["roots"]["karma_package"]["entries"])
        self.assertEqual("UNSAFE", record["observations"]["karma_input"]["status"])

    def test_crowded_safari_inventory_keeps_exact_inputs_with_bounded_work(self):
        repository = self.root / "repository"
        project = repository / "dyn4k-core"
        compiler = project / "build/compileSync/js/test"
        crowded = compiler / "aaa"
        crowded.mkdir(parents=True)
        for index in range(200):
            (crowded / f"file-{index:03d}.js").write_bytes(b"noise")
        expected = (compiler / "testProductionExecutable/kotlin"
                    / "dyn4k-dyn4k-core-test.js")
        expected.parent.mkdir(parents=True)
        expected.write_bytes(b"intended product")
        duplicate = expected.with_name("unrelated-test.js")
        duplicate.write_bytes(b"other product")
        original_scandir = os.scandir
        case = self

        def bounded_scandir(directory):
            entries = original_scandir(directory)
            if Path(directory) != crowded:
                return entries

            class GuardedEntries:
                count = 0

                def __enter__(self):
                    return self

                def __exit__(self, *_):
                    entries.close()

                def __iter__(self):
                    return self

                def __next__(self):
                    if self.count >= 129:
                        case.fail("Safari diagnostic enumerated beyond the listing bound")
                    self.count += 1
                    return next(entries)

            return GuardedEntries()

        process = {"started_ns": 1, "finished_ns": time.time_ns() + 10**9,
                   "invocation_id": "crowded", "exit_code": 0}
        output = self.root / "failed"
        output.mkdir()
        diagnostic = output / "production/product-inventory-source.json"
        with mock.patch.object(os, "scandir", bounded_scandir):
            with self.assertRaisesRegex(ValueError, "exactly one.*product inventory"):
                full_hosted.collect_test_products(
                    {"dyn4k-core": project}, "jsSafari", "production", process,
                    diagnostic, output, {"dyn4k-core": str(expected)})
        record = json.loads(diagnostic.read_text())["projects"]["dyn4k-core"]
        self.assertTrue(record["roots"]["compiler"]["truncated"])
        self.assertLessEqual(len(record["roots"]["compiler"]["entries"]), 128)
        self.assertEqual("HASHED", record["observations"]["expected"]["hash_status"])
        self.assertEqual(full_hosted.sha256(expected),
                         record["observations"]["expected"]["sha256"])
        self.assertEqual(full_hosted.sha256(expected),
                         record["observations"]["karma_input"]["sha256"])
        expected.unlink()
        missing = full_hosted.product_inventory(project, "jsSafari", "production",
                                                "dyn4k-core")
        self.assertEqual("MISSING", missing["observations"]["expected"]["status"])
        expected.symlink_to(self.root / "outside.js")
        unsafe = full_hosted.product_inventory(project, "jsSafari", "production",
                                               "dyn4k-core")
        self.assertEqual("UNSAFE", unsafe["observations"]["expected"]["status"])
        expected.unlink()
        with expected.open("wb") as stream:
            stream.truncate(256 * 1024 * 1024 + 1)
        too_large = full_hosted.product_inventory(project, "jsSafari", "production",
                                                  "dyn4k-core")
        self.assertEqual("TOO_LARGE",
                         too_large["observations"]["expected"]["hash_status"])

    def test_safari_product_requires_exact_compiler_and_karma_bytes(self):
        repository = self.root / "repository"
        project = repository / "dyn4k-core"
        compiler = (project / "build/compileSync/js/test/testDevelopmentExecutable/kotlin"
                    / "dyn4k-dyn4k-core-test.js")
        karma = (repository / "build/js/packages/dyn4k-dyn4k-core-test/kotlin"
                 / "dyn4k-dyn4k-core-test.js")
        compiler.parent.mkdir(parents=True)
        karma.parent.mkdir(parents=True)
        started = time.time_ns()
        compiler.write_bytes(b"same product")
        karma.write_bytes(b"same product")
        process = {"started_ns": started, "finished_ns": time.time_ns() + 10**9}
        selected = full_hosted.test_products(project, "jsSafari", "development", process,
                                             str(karma), "dyn4k-core")
        self.assertEqual(str(compiler), selected["path"])
        self.assertEqual(str(karma), selected["karma_input"]["path"])
        for mutation in ("unrelated", "duplicate", "compiler-symlink", "karma-symlink",
                         "compiler-stale", "karma-stale", "different-bytes", "missing"):
            with self.subTest(mutation=mutation):
                compiler.unlink(missing_ok=True)
                karma.unlink(missing_ok=True)
                compiler.write_bytes(b"same product")
                karma.write_bytes(b"same product")
                if mutation == "unrelated":
                    compiler.rename(compiler.with_name("unrelated-test.js"))
                elif mutation == "duplicate":
                    compiler.with_name("unrelated-test.js").write_bytes(b"other")
                elif mutation == "compiler-symlink":
                    compiler.unlink()
                    compiler.symlink_to(karma)
                elif mutation == "karma-symlink":
                    karma.unlink()
                    karma.symlink_to(compiler)
                elif mutation == "compiler-stale":
                    os.utime(compiler, ns=(started - 1, started - 1))
                elif mutation == "karma-stale":
                    os.utime(karma, ns=(started - 1, started - 1))
                elif mutation == "different-bytes":
                    karma.write_bytes(b"substituted")
                elif mutation == "missing":
                    compiler.unlink()
                with self.assertRaises(ValueError):
                    full_hosted.test_products(project, "jsSafari", "development", process,
                                              str(karma), "dyn4k-core")
                compiler.with_name("unrelated-test.js").unlink(missing_ok=True)
        compiler.write_bytes(b"same product")
        karma.write_bytes(b"same product")
        observed = full_hosted.test_products(project, "jsSafari", "development", process,
                                             str(karma), "dyn4k-core")
        karma.write_bytes(b"changed after observation")
        with self.assertRaisesRegex(ValueError, "changed after observation"):
            full_hosted.archive_test_product(observed, self.root / "archive", "development",
                                             "dyn4k-core", "jsSafari")
        production = (project / "build/compileSync/js/test/testProductionExecutable/kotlin"
                      / "dyn4k-dyn4k-core-test.js")
        production.parent.mkdir(parents=True)
        production.write_bytes(b"production")
        self.assertEqual(str(production), full_hosted.test_products(
            project, "jsSafari", "production", process, str(production),
            "dyn4k-core")["karma_input"]["path"])

    def test_safari_product_selects_app_with_kotlin_test_runtime_helper(self):
        for configuration in ("development", "production"):
            for name in ("dyn4k-core", "dyn4k"):
                with self.subTest(configuration=configuration, name=name):
                    repository = self.root / configuration / name / "repository"
                    project = repository / name
                    compiler, karma, _, _ = full_hosted.safari_product_paths(
                        project, configuration, name)
                    compiler.parent.mkdir(parents=True)
                    karma.parent.mkdir(parents=True, exist_ok=True)
                    started = time.time_ns()
                    compiler.write_bytes(b"app test bundle")
                    if karma != compiler:
                        karma.write_bytes(b"app test bundle")
                    helper = compiler.with_name("kotlin-kotlin-test.js")
                    helper.write_bytes(b"Kotlin test runtime helper")
                    self.assertEqual({f"dyn4k-{name}-test.js", "kotlin-kotlin-test.js"},
                                     {path.name for path in compiler.parent.iterdir()})
                    process = {"started_ns": started,
                               "finished_ns": time.time_ns() + 10**9}
                    selected = full_hosted.test_products(
                        project, "jsSafari", configuration, process, str(karma), name)
                    self.assertEqual(str(compiler), selected["path"])
                    self.assertEqual(full_hosted.sha256(compiler), selected["sha256"])

                    extra = compiler.with_name("unrelated-test.js")
                    extra.write_bytes(b"extra app")
                    with self.assertRaisesRegex(ValueError, "exactly one"):
                        full_hosted.test_products(project, "jsSafari", configuration,
                                                  process, str(karma), name)
                    extra.unlink()

                    helper.unlink()
                    helper.symlink_to(compiler)
                    with self.assertRaisesRegex(ValueError, "runtime helper.*unsafe"):
                        full_hosted.test_products(project, "jsSafari", configuration,
                                                  process, str(karma), name)
                    helper.unlink()

                    helper.mkdir()
                    with self.assertRaisesRegex(ValueError, "runtime helper.*unsafe"):
                        full_hosted.test_products(project, "jsSafari", configuration,
                                                  process, str(karma), name)
                    helper.rmdir()
                    helper.write_bytes(b"Kotlin test runtime helper")

                    compiler.write_bytes(b"substituted app")
                    if karma == compiler:
                        os.utime(compiler, ns=(started - 1, started - 1))
                        reason = "predates invocation"
                    else:
                        reason = "bytes differ"
                    with self.assertRaisesRegex(ValueError, reason):
                        full_hosted.test_products(project, "jsSafari", configuration,
                                                  process, str(karma), name)

                    compiler.unlink()
                    compiler.symlink_to(karma if karma != compiler else helper)
                    with self.assertRaisesRegex(ValueError, "path is unsafe"):
                        full_hosted.test_products(project, "jsSafari", configuration,
                                                  process, str(karma), name)
                    compiler.unlink()
                    with self.assertRaisesRegex(ValueError, "exactly one"):
                        full_hosted.test_products(project, "jsSafari", configuration,
                                                  process, str(karma), name)

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
        safari = "/Users/runner/work/dyn4k/dyn4k/dyn4k-core/build/test.js"
        self.assertEqual(PurePosixPath(safari), full_hosted.original_path("jsSafari", safari))
        with self.assertRaisesRegex(ValueError, "original path"):
            full_hosted.original_path("tvosSimulatorArm64",
                                      r"C:\Users\runneradmin\AppData\Local\Temp\gradle-home")

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

    def test_graph_accepts_exact_staged_bytes_from_gradle_cache(self):
        target = "mingwX64" if os.name == "nt" else "macosArm64"
        other_target = "macosArm64" if target == "mingwX64" else "mingwX64"
        core_name = qualify.target_publication_name("dyn4k-core", target)
        other_core_name = qualify.target_publication_name("dyn4k-core", other_target)
        staging = self.root / "staging-repository"
        graph_folder = self.root / "graph"
        graph_folder.mkdir()
        hashes = {}
        artifacts = []
        for module in qualify.MODULES:
            name = qualify.target_publication_name(module, target)
            binary = staging / qualify.target_binary_path(module, target)
            binary.parent.mkdir(parents=True, exist_ok=True)
            contents = (module + " staged bytes").encode()
            if module == "dyn4k-core":
                for nonce in range(256):
                    candidate = contents + str(nonce).encode()
                    if hashlib.sha1(candidate).hexdigest().startswith("0"):
                        contents = candidate
                        break
                else:
                    self.fail("could not create leading-zero staged bytes")
                self.assertTrue(hashlib.sha1(contents).hexdigest().startswith("0"))
            binary.write_bytes(contents)
            hashes[module] = full_hosted.sha256(binary)
            cache = (self.root / "gradle-home/caches/modules-2/files-2.1" /
                     qualify.GROUP / name / qualify.VERSION /
                     hashlib.sha1(binary.read_bytes()).hexdigest() /
                     f"{module}-{target}Main-{qualify.VERSION}.klib")
            cache.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(binary, cache)
            artifacts.append({"component": f"{qualify.GROUP}:{name}:{qualify.VERSION}",
                              "file": str(cache), "name": cache.name,
                              "size": cache.stat().st_size, "sha256": full_hosted.sha256(cache)})
        graph = {"configuration": f"{target}CompileKlibraries",
                 "gradle_user_home": str(self.root / "gradle-home"),
                 "components": [item["component"] for item in artifacts] +
                 [f"{qualify.GROUP}:{module}:{qualify.VERSION}" for module in qualify.MODULES] +
                 ["org.jetbrains.kotlin:kotlin-stdlib:2.4.20", "root project :"],
                 "artifacts": artifacts}

        def observe(value):
            (graph_folder / "stdout.txt").write_text(
                "DYN4K_RESOLVED_GRAPH=" + json.dumps(value) + "\n")
            return full_hosted.parse_graph(graph_folder, {"exit_code": 0}, target,
                                           hashes, staging, self.root / "gradle-home")

        self.assertEqual(graph, observe(graph))
        mutations = (
            (lambda value: value["artifacts"][0].update(sha256="0" * 64), "artifact differs"),
            (lambda value: value["artifacts"][0].update(component="wrong:module:1"),
             "lacks staged target"),
            (lambda value: value["components"].append(
                f"{qualify.GROUP}:unexpected:{qualify.VERSION}"), "dependency graph"),
            (lambda value: value["artifacts"].append({**value["artifacts"][0],
                "component": f"{qualify.GROUP}:unexpected:{qualify.VERSION}"}),
             "staged target"),
            (lambda value: value["artifacts"][0].update(
                file=str(self.root / "outside" / ".." / "outside.klib")),
             "original path"),
            (lambda value: value["artifacts"][0].update(file=str(self.root / "copied.klib"),
                                                        name="copied.klib"),
             "artifact differs"),
            (lambda value: value["artifacts"][0].update(file=value["artifacts"][0]["file"].replace(
                core_name, other_core_name)), "artifact differs"),
            (lambda value: value["artifacts"][0].update(file=value["artifacts"][0]["file"].replace(
                Path(value["artifacts"][0]["file"]).parts[-2], "f" * 40)), "cache digest"),
            (lambda value: value["artifacts"][0].update(file=value["artifacts"][0]["file"].replace(
                str(self.root / "gradle-home"), str(self.root / "other-gradle-home"))),
             "Gradle user home"),
            (lambda value: value.pop("gradle_user_home"), "Gradle user home"),
            (lambda value: value["artifacts"][0].update(name="wrong.klib"),
             "artifact identity"),
            (lambda value: value["components"].remove(
                f"{qualify.GROUP}:dyn4k-core:{qualify.VERSION}"), "dependency graph"),
            (lambda value: value["components"].append(value["components"][0]),
             "dependency graph"),
        )
        for change, error in mutations:
            with self.subTest(error=error):
                changed = json.loads(json.dumps(graph))
                change(changed)
                with self.assertRaisesRegex(ValueError, error):
                    observe(changed)

    def test_windows_graph_requires_windows_cache_path_identity(self):
        target = "mingwX64"
        staging = r"C:\staging-repository"
        home = PureWindowsPath(r"C:\Users\runner\.gradle")
        captured = self.root / "windows-staged"
        graph_folder = self.root / "windows-graph"
        graph_folder.mkdir()
        hashes = {}
        artifacts = []
        for module in qualify.MODULES:
            name = qualify.target_publication_name(module, target)
            binary = captured / qualify.target_binary_path(module, target)
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_bytes((module + " staged Windows bytes").encode())
            hashes[module] = full_hosted.sha256(binary)
            cache = (home / "caches/modules-2/files-2.1" / qualify.GROUP / name /
                     qualify.VERSION / hashlib.sha1(binary.read_bytes()).hexdigest() /
                     f"{module}-{target}Main-{qualify.VERSION}.klib")
            artifacts.append({"component": f"{qualify.GROUP}:{name}:{qualify.VERSION}",
                              "file": str(cache), "name": cache.name,
                              "size": binary.stat().st_size, "sha256": hashes[module]})
        graph = {"configuration": f"{target}CompileKlibraries",
                 "gradle_user_home": str(home),
                 "components": [item["component"] for item in artifacts] +
                 [f"{qualify.GROUP}:{module}:{qualify.VERSION}" for module in qualify.MODULES],
                 "artifacts": artifacts}

        def observe(value):
            (graph_folder / "stdout.txt").write_text(
                "DYN4K_RESOLVED_GRAPH=" + json.dumps(value) + "\n")
            return full_hosted.parse_graph(graph_folder, {"exit_code": 0}, target,
                                           hashes, staging, home, captured)

        self.assertEqual(graph, observe(graph))
        mutations = (
            (lambda value: value["artifacts"][0].update(file="/tmp/copied.klib"),
             "original path"),
            (lambda value: value["artifacts"][0].update(file=str(home / "caches" /
                                                         ".." / "escape.klib")),
             "original path"),
            (lambda value: value["artifacts"][0].update(file=value["artifacts"][0]["file"].replace(
                PureWindowsPath(value["artifacts"][0]["file"]).parts[-2], "f" * 40)),
             "cache digest"),
            (lambda value: value["artifacts"][0].update(file=value["artifacts"][0]["file"].replace(
                str(home), r"D:\other-gradle-home")), "Gradle user home"),
            (lambda value: value["artifacts"][0].update(component="wrong:module:1"),
             "lacks staged target"),
        )
        for change, error in mutations:
            with self.subTest(error=error):
                changed = json.loads(json.dumps(graph))
                change(changed)
                with self.assertRaisesRegex(ValueError, error):
                    observe(changed)

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
        evidence = evidence.resolve()
        actual_repository = Path(__file__).resolve().parents[2]
        repository = evidence / "checkout"
        cache_home = evidence / "gradle-home"
        repository.mkdir()
        output = evidence / "full"
        unresolved_alias_parent = evidence / "RUNNER~1"
        unresolved_alias_parent.mkdir()
        alias_output = unresolved_alias_parent / ".." / "full"
        self.assertNotEqual(str(alias_output), str(output))
        self.assertEqual(output, alias_output.resolve())
        target = "tvosSimulatorArm64"
        simulator = "00000000-0000-0000-0000-000000000001"
        (repository / "LICENSE.md").write_bytes(b"Fixture license\n")
        for module in qualify.MODULES:
            source = repository / module / "src/commonMain/kotlin/api/Type.kt"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"// Fixture notice\npackage api\nclass Type\n")
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
                        "consumers/qualification/portable/build.gradle.kts",
                        "consumers/qualification/portable/settings.gradle.kts"], check=True)
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
                leading_digest = self.make_staged_binary_sha1_leading_zero(repository, target)
                self.assertEqual(40, len(leading_digest))
                self.assertTrue(leading_digest.startswith("0") and
                                not leading_digest.startswith("00"))
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
                    cached = (cache_home / "caches/modules-2/files-2.1" /
                              qualify.GROUP / name / qualify.VERSION /
                              (hashlib.sha1(binary.read_bytes()).hexdigest().lstrip("0")
                               if module == "dyn4k-core" else
                               hashlib.sha1(binary.read_bytes()).hexdigest()) /
                              f"{module}-{target}Main-{qualify.VERSION}.klib")
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(binary, cached)
                    artifacts.append({"component": f"{qualify.GROUP}:{name}:{qualify.VERSION}",
                                      "file": str(cached), "name": cached.name,
                                      "size": cached.stat().st_size,
                                      "sha256": full_hosted.sha256(cached)})
                graph = {"configuration": f"{target}CompileKlibraries",
                         "gradle_user_home": str(cache_home),
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
                  "GRADLE_USER_HOME": str(cache_home),
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
                mock.patch.object(full_hosted, "run_command",
                                  side_effect=synthetic_command) as command_runner, \
                mock.patch.object(full_hosted.artifact, "capture_staging",
                                  wraps=full_hosted.artifact.capture_staging) as capture, \
                mock.patch.dict(os.environ, runner):
            emitted = full_hosted.run(target, candidate, alias_output)
            if os.name == "nt":
                self.assertEqual("FAILED", emitted["status"])
                self.assertEqual(2, len(emitted["configurations"]))
                for lane in emitted["configurations"]:
                    self.assertEqual("original path is not absolute or safe",
                                     lane.get("reason"))
                    self.assertIn("source", lane)
                    self.assertIn("consumer", lane)
                    self.assertIn("graph_process", lane)
                    self.assertNotIn("consumer_graph", lane)
                with self.assertRaisesRegex(ValueError,
                                            "full hosted receipt is not a completed target"):
                    full_hosted.verify_raw_files(output, emitted)
                return
            self.assertEqual("FULL_COMMON_PASSED", emitted["status"], emitted.get("reason"))
            self.assertEqual(str(output), emitted["archive_root"])
            self.assertEqual(2, len(emitted["configurations"]))
            self.assertEqual(candidate, capture.call_args.args[3])
            self.assertEqual(output, capture.call_args.args[1])
            for lane in emitted["configurations"]:
                folder = output / lane["configuration"]
                self.assertIn(str(folder / "qualification.init.gradle"),
                              lane["source_process"]["command"])
                self.assertIn(str(folder / "qualification-graph.init.gradle"),
                              lane["graph_process"]["command"])
            self.assertEqual(52, len([item for item in emitted["files"]
                                      if item["path"].startswith("staged/")]))
            self.assertEqual(2, load.call_count)
            receipt = qualify.load_json_strict(output / "receipt.json")
            self.assertEqual(emitted, receipt)
            self.assertEqual(str(cache_home), receipt["gradle_user_home"])
            self.assertEqual(str(cache_home),
                             receipt["gradle_user_home_override"])
            full_hosted.verify_raw_files(output, receipt)
            archive = evidence / "full.tar"
            full_hosted.package_archive(output, archive)
            transported = full_hosted.verify_transport_archive(archive, candidate, target)
            self.assertEqual(receipt, transported)

            def corrupt_cached_command(command, cwd, destination, invocation_id=None):
                process = synthetic_command(command, cwd, destination, invocation_id)
                if destination.name == "graph":
                    line = next(line for line in (destination / "stdout.txt").read_text().splitlines()
                                if line.startswith("DYN4K_RESOLVED_GRAPH="))
                    observed = json.loads(line.removeprefix("DYN4K_RESOLVED_GRAPH="))
                    Path(observed["artifacts"][0]["file"]).write_bytes(b"wrong cached bytes")
                return process

            shutil.rmtree(repository / "build/staging-repository")
            command_runner.side_effect = corrupt_cached_command
            failed_cache = full_hosted.run(target, candidate, evidence / "adverse-cache-producer")
            self.assertEqual("FAILED", failed_cache["status"])
            self.assertTrue(failed_cache["configurations"], failed_cache.get("reason"))
            self.assertEqual("resolved dependency changed after graph observation",
                             failed_cache["configurations"][0]["reason"])
            command_runner.side_effect = synthetic_command

            adverse_cache = evidence / "adverse-cache-bytes"
            shutil.copytree(output, adverse_cache)
            cache_receipt = qualify.load_json_strict(adverse_cache / "receipt.json")
            resolved = (adverse_cache /
                        cache_receipt["configurations"][0]["resolved_artifacts"][0]["archive_path"])
            modified_ns = resolved.stat().st_mtime_ns
            resolved.write_bytes(b"wrong cached artifact bytes")
            os.utime(resolved, ns=(modified_ns, modified_ns))
            cache_receipt["files"] = full_hosted.archive_inventory(adverse_cache)
            (adverse_cache / "receipt.json").write_text(json.dumps(cache_receipt, sort_keys=True))
            with self.assertRaisesRegex(ValueError, "resolved dependency artifact bytes"):
                full_hosted.verify_raw_files(adverse_cache, cache_receipt)
            adverse_cache_archive = evidence / "adverse-cache-bytes.tar"
            full_hosted.package_archive(adverse_cache, adverse_cache_archive)
            with self.assertRaisesRegex(ValueError, "resolved dependency artifact bytes"):
                full_hosted.verify_transport_archive(adverse_cache_archive, candidate, target)

            wrong_root = evidence / "different-root"
            wrong_receipt = json.loads(json.dumps(receipt))
            wrong_receipt["archive_root"] = str(wrong_root)
            with self.assertRaisesRegex(
                    ValueError, "test or graph init script is unbound") as wrong_root_error:
                full_hosted.verify_raw_files(output, wrong_receipt)
            adverse_root = evidence / "adverse-different-root"
            shutil.copytree(output, adverse_root)
            (adverse_root / "receipt.json").write_text(
                json.dumps(wrong_receipt, sort_keys=True) + "\n")
            adverse_root_archive = evidence / "adverse-different-root.tar"
            full_hosted.package_archive(adverse_root, adverse_root_archive)
            with self.assertRaisesRegex(
                    ValueError, "test or graph init script is unbound") as wrong_tar_error:
                full_hosted.verify_transport_archive(adverse_root_archive, candidate, target)

            clean = evidence / "replay-other-parent/clean-checkout"
            clean.parent.mkdir()
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

            def reseal_cache_path(label, change, home=None):
                adverse = evidence / f"adverse-{label}"
                shutil.copytree(output, adverse)
                changed = qualify.load_json_strict(adverse / "receipt.json")
                if home is not None:
                    changed["gradle_user_home"] = home
                for lane in (changed["configurations"] if home is not None
                             else changed["configurations"][:1]):
                    stdout = adverse / lane["configuration"] / "graph/stdout.txt"
                    modified_ns = stdout.stat().st_mtime_ns
                    lines = stdout.read_text().splitlines(keepends=True)
                    for index, line in enumerate(lines):
                        if line.startswith("DYN4K_RESOLVED_GRAPH="):
                            graph = json.loads(line.removeprefix("DYN4K_RESOLVED_GRAPH="))
                            artifacts = graph["artifacts"] if home is not None else graph["artifacts"][:1]
                            for artifact in artifacts:
                                artifact["file"] = change(artifact["file"])
                            if home is not None:
                                graph["gradle_user_home"] = home
                            lines[index] = "DYN4K_RESOLVED_GRAPH=" + json.dumps(graph) + "\n"
                            break
                    else:
                        self.fail("synthetic graph observation is absent")
                    stdout.write_text("".join(lines))
                    os.utime(stdout, ns=(modified_ns, modified_ns))
                    lane["consumer_graph"] = graph
                    for archived, artifact in zip(lane["resolved_artifacts"], graph["artifacts"]):
                        archived["file"] = artifact["file"]
                    lane["graph_process"]["stdout_sha256"] = full_hosted.sha256(stdout)
                changed["files"] = full_hosted.archive_inventory(adverse)
                (adverse / "receipt.json").write_text(json.dumps(changed, sort_keys=True))
                packed = evidence / f"adverse-{label}.tar"
                full_hosted.package_archive(adverse, packed)
                return adverse, packed, changed

            wrong_digest = reseal_cache_path(
                "cache-digest", lambda path: path.replace(Path(path).parts[-2], "f" * 40))
            extra_zero = reseal_cache_path(
                "cache-extra-zero", lambda path: path.replace(
                    Path(path).parts[-2], "00" + Path(path).parts[-2]))
            wrong_home = reseal_cache_path(
                "cache-home", lambda path: path.replace(
                    str(evidence / "gradle-home"), str(evidence / "unrecorded-gradle-home")))
            resealed_home = reseal_cache_path(
                "cache-home-resealed", lambda path: path.replace(
                    str(evidence / "gradle-home"), str(evidence / "unrecorded-gradle-home")),
                str(evidence / "unrecorded-gradle-home"))
            for label, (bad_directory, bad_tar, bad_receipt), error in (
                    ("cache-digest", wrong_digest, "cache digest"),
                    ("cache-extra-zero", extra_zero, "cache digest"),
                    ("cache-home", wrong_home, "Gradle user home"),
                    ("cache-home-resealed", resealed_home, "Gradle user home"),
                    ("cache-bytes", (adverse_cache, adverse_cache_archive, cache_receipt),
                     "resolved dependency artifact bytes")):
                with self.subTest(cache_provenance=label):
                    with self.assertRaisesRegex(ValueError, error):
                        full_hosted.verify_raw_files(bad_directory, bad_receipt)
                    with self.assertRaisesRegex(ValueError, error):
                        full_hosted.verify_transport_archive(bad_tar, candidate, target)
                    for prefix, bundle in ((directory_command[:-1], bad_directory),
                                           (command[:-1], bad_tar)):
                        result = subprocess.run([*prefix, str(bundle)], cwd=clean,
                                                capture_output=True, text=True)
                        self.assertNotEqual(0, result.returncode)
                        self.assertIn(error, result.stderr)
                    for bundle in (bad_directory, bad_tar):
                        result = subprocess.run([*artifact_command, str(bundle)], cwd=clean,
                                                capture_output=True, text=True)
                        self.assertEqual(1, result.returncode)
                        self.assertIn("full hosted archive failed", result.stderr)
                    rejected = subprocess.run([
                        sys.executable, str(clean / "tools/qualification/qualify.py"), "record",
                        "--candidate-sha", candidate, "--full-hosted-bundle", str(bad_tar),
                        "--output", str(evidence / f"qualification-{label}.json")],
                        cwd=clean, capture_output=True, text=True)
                    self.assertEqual(2, rejected.returncode)
                    self.assertIn("full hosted receipt failed", rejected.stderr)
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
            for rejected_bundle in (adverse_cache, adverse_cache_archive,
                                    adverse_dokka, adverse_dokka_archive,
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
            cache_home = evidence / "outside-checkout-gradle-home"
            relative_override = "../outside-checkout-gradle-home"
            self.assertEqual(cache_home, (repository / relative_override).resolve())
            self.assertNotEqual(cache_home, (clean / relative_override).resolve())
            relative_output = evidence / "relative-home-full"
            shutil.rmtree(repository / "build/staging-repository")
            with mock.patch.dict(os.environ, {"GRADLE_USER_HOME": relative_override}):
                relative_receipt = full_hosted.run(target, candidate, relative_output)
            self.assertEqual("FULL_COMMON_PASSED", relative_receipt["status"],
                             relative_receipt.get("reason"))
            self.assertEqual(relative_override, relative_receipt["gradle_user_home_override"])
            self.assertEqual(str(cache_home), relative_receipt["gradle_user_home"])
            full_hosted.verify_raw_files(relative_output, relative_receipt)
            relative_archive = evidence / "relative-home-full.tar"
            full_hosted.package_archive(relative_output, relative_archive)
            self.assertEqual(relative_receipt,
                             full_hosted.verify_transport_archive(relative_archive, candidate, target))
            for command_prefix, bundle in ((directory_command[:-1], relative_output),
                                           (command[:-1], relative_archive)):
                accepted = subprocess.run([*command_prefix, str(bundle)], cwd=clean,
                                          capture_output=True, text=True)
                self.assertEqual(0, accepted.returncode, accepted.stderr)
            for bundle in (relative_output, relative_archive):
                accepted = subprocess.run([*artifact_command, str(bundle)], cwd=clean,
                                          capture_output=True, text=True)
                self.assertEqual(0, accepted.returncode, accepted.stderr)
            relative_report = evidence / "relative-home-qualification.json"
            accepted_record = subprocess.run([
                sys.executable, str(clean / "tools/qualification/qualify.py"), "record",
                "--candidate-sha", candidate, "--full-hosted-bundle", str(relative_archive),
                "--output", str(relative_report)], cwd=clean, capture_output=True, text=True)
            self.assertEqual(1, accepted_record.returncode, accepted_record.stderr)
            relative_qualification = qualify.load_json_strict(relative_report)
            self.assertEqual(112, relative_qualification["total"])
            self.assertEqual(0, relative_qualification["counts"]["PASSED"])
            self.assertEqual(112, relative_qualification["counts"]["NOT_RUN"])

            for label, key, value in (
                    ("cwd", "repository_root", str(evidence / "other/checkout")),
                    ("override", "gradle_user_home_override", "../other-gradle-home"),
                    ("home", "gradle_user_home", str(evidence / "other-gradle-home"))):
                with self.subTest(relative_home_mutation=label):
                    altered_output = evidence / f"adverse-relative-{label}"
                    shutil.copytree(relative_output, altered_output)
                    altered = qualify.load_json_strict(altered_output / "receipt.json")
                    altered[key] = value
                    (altered_output / "receipt.json").write_text(json.dumps(altered, sort_keys=True))
                    altered_archive = evidence / f"adverse-relative-{label}.tar"
                    full_hosted.package_archive(altered_output, altered_archive)
                    with self.assertRaisesRegex(ValueError, "Gradle user home differs"):
                        full_hosted.verify_raw_files(altered_output, altered)
                    with self.assertRaisesRegex(ValueError, "Gradle user home differs"):
                        full_hosted.verify_transport_archive(altered_archive, candidate, target)
                    for command_prefix, bundle in ((directory_command[:-1], altered_output),
                                                   (command[:-1], altered_archive)):
                        rejected = subprocess.run([*command_prefix, str(bundle)], cwd=clean,
                                                  capture_output=True, text=True)
                        self.assertNotEqual(0, rejected.returncode)
                        self.assertIn("Gradle user home differs", rejected.stderr)
                    for bundle in (altered_output, altered_archive):
                        rejected = subprocess.run([*artifact_command, str(bundle)], cwd=clean,
                                                  capture_output=True, text=True)
                        self.assertEqual(1, rejected.returncode)
                        self.assertIn("full hosted archive failed", rejected.stderr)
                    rejected_record = subprocess.run([
                        sys.executable, str(clean / "tools/qualification/qualify.py"), "record",
                        "--candidate-sha", candidate, "--full-hosted-bundle", str(altered_archive),
                        "--output", str(evidence / f"adverse-relative-{label}-qualification.json")],
                        cwd=clean, capture_output=True, text=True)
                    self.assertEqual(2, rejected_record.returncode)
                    self.assertIn("full hosted receipt failed", rejected_record.stderr)
            (evidence / "evidence.json").write_text(json.dumps({
                "synthetic": True, "real_hosted_runtime": False,
                "corpus_loader": "real_source_derived_candidate",
                "candidate_input_count": len(full_hosted.INPUTS),
                "reviewed_source_file_count": len(manifest["source_files"]),
                "candidate_sha": candidate, "target": target,
                "output_alias": str(alias_output),
                "archive_root": receipt["archive_root"],
                "different_root_rejection": str(wrong_root_error.exception),
                "different_root_tar_rejection": str(wrong_tar_error.exception),
                "different_root_archive_sha256": full_hosted.sha256(adverse_root_archive),
                "staged_files": 52, "configurations": list(full_hosted.CONFIGS[target]),
                "source_cases_per_configuration": {module: len(full_hosted.expected_cases(manifest, module))
                                                   for module in qualify.MODULES},
                "consumer_cases_per_configuration": len(consumer_cases),
                "positive_archive_sha256": full_hosted.sha256(archive),
                "relative_home_override": relative_override,
                "relative_home_observed": relative_receipt["gradle_user_home"],
                "relative_home_archive_sha256": full_hosted.sha256(relative_archive),
                "relative_home_qualification_lanes": relative_qualification["total"],
                "relative_home_passed_lanes": relative_qualification["counts"]["PASSED"],
                "cache_bytes_archive_sha256": full_hosted.sha256(adverse_cache_archive),
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

    def full_archive(self, target="mingwX64"):
        repository = Path(__file__).resolve().parents[2]
        manifest = json.loads((repository / full_hosted.MANIFEST).read_text())
        consumer_manifest = json.loads((repository / "tools/qualification/foundation-probes.json").read_text())
        safari = target == "jsSafari"
        artifact_target = "js" if safari else target
        now = time.time_ns()
        stage_window = (now - 60 * 10**9, now + 60 * 10**9)
        windows = {}
        boundary = stage_window[1]
        for configuration in full_hosted.CONFIGS[target]:
            for phase in ("source", "consumer", "graph"):
                windows[(configuration, phase)] = (boundary, boundary + 10 * 10**9)
                boundary += 10 * 10**9
        original_repository = ("/Users/runner/work/dyn4k/dyn4k" if safari
                               else r"C:\runner\work\dyn4k")
        original_archive = ("/Users/runner/work/_temp/full" if safari
                            else r"C:\runner\temp\full")
        original_home = ("/Users/runner" if safari else r"C:\runner")
        receipt = {"schema": 2, "kind": "hosted-full-common-corpus", "target": target,
                   "status": "FULL_COMMON_PASSED",
                   "manifest_sha256": full_hosted.canonical_hash(manifest),
                   "source_tree_sha256": manifest["source_tree_sha256"],
                   "map_sha256": full_hosted.sha256(repository / full_hosted.MAPPING),
                   "reviewed_pairs_sha256": full_hosted.sha256(repository / full_hosted.PAIRS),
                   "runtime": {"system": "Darwin" if safari else "Windows",
                               "machine": "arm64" if safari else "AMD64",
                               "os_version": "26.0" if safari else "10.0.26100",
                               "xcode_version": "26.4.1" if safari else None,
                               "safari_version": "26.6.2" if safari else None,
                               "safaridriver_version": "safaridriver 26.6.2" if safari else None,
                               "java_version": "21.0.1",
                               "gradle_version": "9.5.0", "kgp_declared_version": "2.4.20",
                               "agp_declared_version": "9.3.1"},
                   "github_run_id": "123", "github_job": "hosted-native", "runner_name": "runner",
                   "runner_os": "macOS" if safari else "Windows",
                   "runner_arch": "ARM64" if safari else "X64",
                   "archive_root": original_archive,
                   "repository_root": original_repository,
                   "runner_home": original_home,
                   "gradle_user_home_override": None,
                   "staging_repository": str(full_hosted.original_path(target, original_repository)
                                             / "build/staging-repository"),
                   "gradle_user_home": str(full_hosted.original_path(target, original_home)
                                           / ".gradle"),
                   "configurations": [], "artifact_hashes": {}}

        def write(path, data):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data if isinstance(data, bytes) else data.encode())
            parts = path.relative_to(self.root).parts
            if parts[0] == "stage":
                window = stage_window
            elif parts[0] in full_hosted.CONFIGS[target] and len(parts) > 2:
                phase = parts[1]
                if phase in ("xml", "executables", "karma-inputs"):
                    phase = "consumer" if parts[2] == "consumer" else "source"
                if phase == "karma-config":
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
            original_root = full_hosted.original_path(target, receipt["repository_root"])
            original_output = full_hosted.original_path(target, receipt["archive_root"])
            wrapper = str(original_root / ("gradlew" if safari else "gradlew.bat"))
            if invocation is None:
                command = [wrapper, "--rerun-tasks", *[task for module in qualify.MODULES for task in (
                    f":{module}:publishKotlinMultiplatformPublicationToStagingRepository",
                    f":{module}:publish{artifact_target[0].upper() + artifact_target[1:]}PublicationToStagingRepository")]]
            else:
                command = [wrapper, "--rerun-tasks", task,
                           f"-PqualificationInvocationId={invocation}"]
                if folder.name == "source":
                    command += [f":dyn4k:{full_hosted.SOURCE_TASK[target]}",
                                "--init-script", str(original_output /
                                                       folder.parent.name / "qualification.init.gradle")]
                    if safari and folder.parent.name == "production":
                        command.append("-PqualificationProduction=true")
                else:
                    command += ["-p", str(original_root /
                                          "consumers/qualification/portable"),
                                f"-PqualificationRepository={receipt['staging_repository']}"]
                if safari and folder.name == "consumer":
                    command += ["--init-script", str(original_output /
                                folder.parent.name / "qualification.init.gradle"),
                                "-PqualificationSafari=true"]
                if folder.name == "graph":
                    command += ["--init-script", str(original_output /
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
        test_publication.PublicationAuditTests().stage(self.candidate_repository,
                                                       (artifact_target,))
        self.align_synthetic_docs(self.candidate_repository, artifact_target)
        for relative in full_hosted.INPUTS:
            destination = self.candidate_repository / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repository / relative, destination)
        subprocess.run(["git", "init", "-q", str(self.candidate_repository)], check=True)
        subprocess.run(["git", "-C", str(self.candidate_repository), "config",
                        "core.autocrlf", "false"], check=True)
        subprocess.run(["git", "-C", str(self.candidate_repository), "add", "LICENSE.md",
                        "dyn4k-core/src", "dyn4k/src", "tools", "build.gradle.kts",
                        "consumers/qualification/portable/build.gradle.kts",
                        "consumers/qualification/portable/settings.gradle.kts"], check=True)
        subprocess.run(["git", "-C", str(self.candidate_repository), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "commit", "-qm", "candidate"],
                       check=True)
        receipt["candidate_sha"] = subprocess.check_output(
            ["git", "-C", str(self.candidate_repository), "rev-parse", "HEAD"],
            text=True).strip()
        receipt["staged_gav"], _, staged_hashes, receipt["staged_content_contract"] = (
            full_hosted.artifact.capture_staging(self.candidate_repository, self.root,
                                                 [artifact_target], receipt["candidate_sha"]))
        receipt["artifact_hashes"] = staged_hashes[artifact_target]
        receipt["stage"] = process(self.root / "stage", None,
                                   ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
                                   "> Task :dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository")
        full_hosted.capture_dokka_output(self.candidate_repository, self.root, receipt)
        group = next(group for group in consumer_manifest["groups"]
                     if group["id"] == f"consumer-{target}")
        consumer_cases = qualify.expected_probe_cases(consumer_manifest, group)
        for index, config in enumerate(full_hosted.CONFIGS[target]):
            folder = self.root / config
            invocation = f"{index + 1:032x}"
            write(folder / "qualification.init.gradle", full_hosted.init_script(target, config))
            write(folder / "qualification-graph.init.gradle", full_hosted.graph_script(target))
            link = "Release" if config == "optimized-opt" else "Debug"
            if safari:
                source_tasks = "\n".join(
                    (f"> Task :{module}:jsTestTestProductionExecutableCompileSync\n"
                     if config == "production" else "") + f"> Task :{module}:jsBrowserTest"
                    for module in qualify.MODULES)
                consumer_tasks = (("> Task :jsTestTestProductionExecutableCompileSync\n"
                                   if config == "production" else "") + "> Task :jsBrowserTest")
            else:
                source_tasks = "\n".join(f"> Task :{module}:link{link}TestMingwX64\n> Task :{module}:mingwX64Test" for module in qualify.MODULES)
                consumer_tasks = f"> Task :link{link}TestMingwX64\n> Task :mingwX64Test"
            lane = {"configuration": config, "status": "FULL_COMMON_PASSED",
                    "invocation_id": invocation,
                    "source_process": process(folder / "source", invocation,
                                              f":dyn4k-core:{full_hosted.SOURCE_TASK[target]}", source_tasks),
                    "consumer_process": process(folder / "consumer", invocation,
                                                full_hosted.SOURCE_TASK[target], consumer_tasks),
                    "source": [], "source_executables": {}}
            for module in qualify.MODULES:
                cases = [(f"jsBrowserTest.{name}" if safari else f"mingwX64Test.{name}",
                          f"{method}[js, browser, Safari26.6.2, MacOS10.15.7]" if safari
                          else f"{method}[mingwX64]")
                         for name, method in full_hosted.expected_cases(manifest, module)]
                suite = ET.Element("testsuite", tests=str(len(cases)), failures="0", errors="0",
                                   skipped="0", time="1")
                for classname, method in cases:
                    ET.SubElement(suite, "testcase", classname=classname, name=method, time="0.1")
                if safari and module == "dyn4k-core":
                    ET.SubElement(suite, "system-out").text = "".join(
                        self.safari_diagnostic_rows())
                report = write(folder / "xml" / module / "TEST-all.xml", ET.tostring(suite))
                checked = full_hosted.read_reports(
                    [report], full_hosted.expected_cases(manifest, module), target,
                    *windows[(config, "source")])
                checked["module"] = module
                checked["reports"][0]["path"] = f"xml/{module}/TEST-all.xml"
                lane["source"].append(checked)
                package = f"dyn4k-{module}-test"
                filename = f"{package}.js" if safari else "test.exe"
                product = write(folder / "executables" / module / filename,
                                b"test-" + module.encode())
                executable_parent = (full_hosted.original_path(target, receipt["repository_root"])
                                     / module / "build/compileSync/js/test" /
                                     ("testProductionExecutable" if config == "production"
                                      else "testDevelopmentExecutable") / "kotlin") if safari else (
                                     PureWindowsPath(receipt["repository_root"]) / module / "build/bin" /
                                     target / ("releaseTest" if config == "optimized-opt"
                                               else "debugTest"))
                lane["source_executables"][module] = {"archive_path": product.relative_to(self.root).as_posix(),
                    "sha256": full_hosted.sha256(product), "size": product.stat().st_size,
                    "path": str(executable_parent / filename),
                    "modified_ns": product.stat().st_mtime_ns}
            suite = ET.Element("testsuite", tests=str(len(consumer_cases)), failures="0", errors="0",
                               skipped="0", time="1")
            for classname, method in consumer_cases:
                ET.SubElement(suite, "testcase", classname=classname, name=method, time="0.1")
            report = write(folder / "xml/consumer/TEST-all.xml", ET.tostring(suite))
            lane["consumer"] = full_hosted.read_consumer_reports([report], set(consumer_cases),
                                                                    lane["consumer_process"])
            lane["consumer"]["reports"][0]["path"] = "xml/consumer/TEST-all.xml"
            consumer_filename = ("dyn4k-staged-portable-consumer-test.js" if safari else "test.exe")
            product = write(folder / "executables/consumer" / consumer_filename,
                            b"test-consumer")
            consumer_parent = (full_hosted.original_path(target, receipt["repository_root"])
                               / "consumers/qualification/portable/build/compileSync/js/test" /
                               ("testProductionExecutable" if config == "production"
                                else "testDevelopmentExecutable") / "kotlin") if safari else (
                               PureWindowsPath(receipt["repository_root"]) /
                               "consumers/qualification/portable/build/bin" / target /
                               ("releaseTest" if config == "optimized-opt" else "debugTest"))
            lane["consumer_executable"] = {"archive_path": product.relative_to(self.root).as_posix(),
                "sha256": full_hosted.sha256(product), "size": product.stat().st_size,
                "path": str(consumer_parent / consumer_filename),
                "modified_ns": product.stat().st_mtime_ns}
            artifacts = []
            for module in qualify.MODULES:
                name = qualify.target_publication_name(module, artifact_target)
                binary = self.root / "staged" / qualify.target_binary_path(module, artifact_target)
                artifacts.append({"component": f"{qualify.GROUP}:{name}:{qualify.VERSION}",
                                  "file": str(full_hosted.original_path(target, receipt["staging_repository"])
                                              / qualify.target_binary_path(module, artifact_target)),
                                  "name": binary.name, "size": binary.stat().st_size,
                                  "sha256": full_hosted.sha256(binary)})
            graph = {"configuration": "jsCompileClasspath" if safari else "mingwX64CompileKlibraries",
                     "gradle_user_home": receipt["gradle_user_home"],
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
                    "dyn4k-core" if "dyn4k-core" in item["name"] else "dyn4k", artifact_target)
                name = f"{config}/resolved-artifacts/{graph_index:03d}-{item['name']}"
                full_hosted.archive_copy(source, self.root, name)
                lane["resolved_artifacts"].append({**item, "archive_path": name})
            if safari:
                fragment = (repository /
                            "tools/qualification/safari-karma-reporter.js").read_text()
                fragment_sha = hashlib.sha256(fragment.encode()).hexdigest()
                lane["safari_reporter_stage"] = {
                    "source": {"status": "CLEAN", "source_sha256": fragment_sha,
                               "projects": {"dyn4k-core": "CLEAN", "dyn4k": "CLEAN"},
                               "forensic": []},
                    "consumer": {"status": "CLEAN", "source_sha256": fragment_sha,
                                 "projects": {"consumers/qualification/portable": "CLEAN"},
                                 "forensic": []}}
                lane["safari_karma_configs"] = {}
                original_root = full_hosted.original_path(target, receipt["repository_root"])
                for name, project, package in (
                        ("dyn4k-core", Path("dyn4k-core"), "dyn4k-dyn4k-core-test"),
                        ("dyn4k", Path("dyn4k"), "dyn4k-dyn4k-test"),
                        ("consumer", Path("consumers/qualification/portable"),
                         "dyn4k-staged-portable-consumer-test")):
                    project_root = original_root / project
                    build_root = (project_root if name == "consumer" else original_root)
                    package_root = build_root / "build/js/packages" / package
                    runner = str(build_root / "build/js/node_modules/kotlin-web-helpers/dist"
                                 / "kotlin-test-karma-runner.js")
                    selected = (project_root / "build/compileSync/js/test" /
                                ("testProductionExecutable" if config == "production"
                                 else "testDevelopmentExecutable") / "kotlin" / f"{package}.js"
                                if config == "production" else
                                package_root / "kotlin" / f"{package}.js")
                    settings = {"singleRun": True, "autoWatch": False,
                                "basePath": str(package_root),
                                "files": [runner, str(selected)],
                                "frameworks": ["webpack-output", "mocha", "webpack"],
                                "client": {"args": []}, "browsers": ["Safari"],
                                "customLaunchers": {}, "failOnFailingTestSuite": False,
                                "failOnEmptyTestSuite": False,
                                "reporters": ["karma-kotlin-reporter"],
                                "preprocessors": {runner: ["webpack", "sourcemap"],
                                                  str(selected): ["webpack", "sourcemap"]},
                                "proxies": {}, "webpackCopy": []}
                    generated = ("\nmodule.exports = function(config) {\n\nconfig.set("
                                 + json.dumps(settings) + ");"
                                 + full_hosted.safari_reporter.APPROVED_GENERATOR_TAIL
                                 + fragment + "\n}\n")
                    archived = write(folder / "karma-config" / name / "karma.conf.js", generated)
                    lane["safari_karma_configs"][name] = {
                        "path": archived.relative_to(self.root).as_posix(),
                        "sha256": full_hosted.sha256(archived),
                        "size": archived.stat().st_size,
                        "modified_ns": archived.stat().st_mtime_ns,
                        "source_device": archived.stat().st_dev,
                        "source_inode": archived.stat().st_ino,
                        "source_path": str(original_root /
                                           full_hosted.safari_reporter.config_relative(project)),
                        "project": project.as_posix(), "configuration": config,
                        "input_path": str(selected)}
                    executable = (lane["consumer_executable"] if name == "consumer" else
                                  lane["source_executables"][name])
                    selected_archive = write(folder / "karma-inputs" / name / f"{package}.js",
                                             (self.root / executable["archive_path"]).read_bytes())
                    executable["karma_input"] = {
                        "path": str(selected), "status": "REGULAR", "hash_status": "HASHED",
                        "sha256": full_hosted.sha256(selected_archive),
                        "size": selected_archive.stat().st_size,
                        "modified_ns": selected_archive.stat().st_mtime_ns,
                        "archive_path": selected_archive.relative_to(self.root).as_posix()}
            receipt["configurations"].append(lane)
        receipt["files"] = full_hosted.archive_inventory(self.root)
        return receipt, manifest, consumer_manifest

    def reseal_safari_case(self, receipt, group, classname, old_name, new_name):
        self.assertEqual(["development", "production"],
                         [lane["configuration"] for lane in receipt["configurations"]])
        for lane in receipt["configurations"]:
            configuration = lane["configuration"]
            record = (lane["source"][0] if group == "dyn4k-core" else lane["consumer"])
            old_id = f"{classname.removeprefix('jsBrowserTest.')}#{old_name}" if group == "dyn4k-core" \
                else f"{classname}#{old_name}[js, browser, Safari26.6.2, MacOS10.15.7]"
            new_id = old_id.replace(f"#{old_name}", f"#{new_name}", 1)
            self.assertIn(old_id, record["case_ids"])
            record["case_ids"] = sorted(new_id if item == old_id else item
                                        for item in record["case_ids"])
            path = self.root / configuration / "xml" / group / "TEST-all.xml"
            modified_ns = path.stat().st_mtime_ns
            tree = ET.parse(path)
            selected = [case for case in tree.iter("testcase")
                        if case.get("classname") == classname
                        and case.get("name", "").startswith(old_name + "[")]
            self.assertEqual(1, len(selected))
            name = selected[0].get("name")
            selected[0].set("name", new_name + name[len(old_name):])
            tree.write(path)
            os.utime(path, ns=(modified_ns, modified_ns))
            record["reports"][0]["sha256"] = full_hosted.sha256(path)
        receipt["files"] = full_hosted.archive_inventory(self.root)

    def assert_safari_parsed_case_rejected(self, receipt, manifest, consumer,
                                           expected_reason):
        archive = self.root.parent / (self.root.name + "-parsed-case.tar")
        self.addCleanup(archive.unlink, missing_ok=True)
        (self.root / "receipt.json").write_text(json.dumps(receipt))
        full_hosted.package_archive(self.root, archive)
        with mock.patch.object(full_hosted, "load_corpus", return_value=json.loads(
                (self.candidate_repository / full_hosted.MANIFEST).read_text())):
            tar_reason = ("source or manifest hash differs" if expected_reason.startswith(
                "parsed source") else "staged consumer cases are missing")
            with self.assertRaisesRegex(ValueError, tar_reason):
                full_hosted.verify_transport_archive(
                    archive, receipt["candidate_sha"], "jsSafari",
                    candidate_repository=self.candidate_repository)
        with self.assertRaisesRegex(ValueError, expected_reason):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer,
                                         candidate_repository=self.candidate_repository)

    def test_windows_fixture_source_archive_matches_candidate_with_autocrlf(self):
        config = self.root / "global-gitconfig"
        config.write_text("[core]\n\tautocrlf = true\n")
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(config)}):
            receipt, manifest, consumer = self.full_archive()
            full_hosted.verify_raw_files(
                self.root, receipt, manifest, consumer,
                candidate_repository=self.candidate_repository)

    def test_public_safari_archive_verifies_exact_reporter_and_rejects_resealed_mutations(self):
        receipt, manifest, consumer = self.full_archive("jsSafari")
        with mock.patch.object(full_hosted, "load_corpus", return_value=manifest):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer,
                                         candidate_repository=self.candidate_repository)
            (self.root / "receipt.json").write_text(json.dumps(receipt))
            archive = self.root.parent / (self.root.name + "-safari.tar")
            self.addCleanup(archive.unlink, missing_ok=True)
            full_hosted.package_archive(self.root, archive)
            full_hosted.verify_transport_archive(
                archive, receipt["candidate_sha"], "jsSafari",
                candidate_repository=self.candidate_repository)
        self.assertEqual([2465, 58], [item["executed"] for item in
                         receipt["configurations"][0]["source"]])
        self.assertEqual(3, receipt["configurations"][0]["consumer"]["executed"])
        fragment = (self.candidate_repository /
                    "tools/qualification/safari-karma-reporter.js").read_bytes()
        for name in ("dyn4k-core", "dyn4k", "consumer"):
            config = self.root / "development/karma-config" / name / "karma.conf.js"
            original = config.read_bytes()
            timestamp = config.stat().st_mtime_ns
            for mutation in ("missing", "altered", "wrong-module",
                             "provider-clear", "bracket-chrome"):
                with self.subTest(module=name, mutation=mutation):
                    changed = json.loads(json.dumps(receipt))
                    if mutation == "missing":
                        config.unlink()
                    elif mutation == "altered":
                        config.write_bytes(original.replace(fragment, b"// absent reporter\n"))
                    elif mutation == "provider-clear":
                        config.write_bytes(original.replace(
                            fragment, b"config.plugins = [];\n" + fragment))
                    elif mutation == "bracket-chrome":
                        config.write_bytes(original.replace(
                            fragment, b"config['set']({browsers: ['ChromeHeadless']});\n"
                            + fragment))
                    else:
                        config.write_bytes(original.replace(
                            b"/build/js/packages/dyn4k-", b"/build/js/packages/other-", 1))
                    if config.exists():
                        os.utime(config, ns=(timestamp, timestamp))
                        record = changed["configurations"][0]["safari_karma_configs"][name]
                        record["sha256"] = full_hosted.sha256(config)
                        record["size"] = config.stat().st_size
                    changed["files"] = full_hosted.archive_inventory(self.root)
                    try:
                        with self.assertRaises(ValueError):
                            full_hosted.verify_raw_files(
                                self.root, changed, manifest, consumer,
                                candidate_repository=self.candidate_repository)
                        if ((name == "dyn4k-core" and mutation == "altered")
                                or (name == "dyn4k" and mutation in (
                                    "provider-clear", "bracket-chrome"))):
                            (self.root / "receipt.json").write_text(json.dumps(changed))
                            full_hosted.package_archive(self.root, archive)
                            with mock.patch.object(full_hosted, "load_corpus", return_value=manifest):
                                with self.assertRaises(ValueError):
                                    full_hosted.verify_transport_archive(
                                        archive, changed["candidate_sha"], "jsSafari",
                                        candidate_repository=self.candidate_repository)
                    finally:
                        config.write_bytes(original)
                        os.utime(config, ns=(timestamp, timestamp))
                        (self.root / "receipt.json").write_text(json.dumps(receipt))
            for mutation in ("stage-sha", "stage-missing"):
                with self.subTest(module=name, mutation=mutation):
                    changed = json.loads(json.dumps(receipt))
                    phase = "consumer" if name == "consumer" else "source"
                    stage = changed["configurations"][0]["safari_reporter_stage"][phase]
                    if mutation == "stage-sha":
                        stage["source_sha256"] = "0" * 64
                    else:
                        stage["projects"].pop("consumers/qualification/portable"
                                              if name == "consumer" else name)
                    with self.assertRaisesRegex(ValueError, "Safari reporter staging"):
                        full_hosted.verify_raw_files(
                            self.root, changed, manifest, consumer,
                            candidate_repository=self.candidate_repository)

    def test_public_safari_directory_and_tar_accept_canonical_parsed_inventories(self):
        receipt, manifest, consumer = self.full_archive("jsSafari")
        full_hosted.verify_raw_files(self.root, receipt, manifest, consumer,
                                     candidate_repository=self.candidate_repository)
        archive = self.root.parent / (self.root.name + "-canonical-parsed.tar")
        self.addCleanup(archive.unlink, missing_ok=True)
        (self.root / "receipt.json").write_text(json.dumps(receipt))
        full_hosted.package_archive(self.root, archive)
        with mock.patch.object(full_hosted, "load_corpus", return_value=manifest):
            full_hosted.verify_transport_archive(
                archive, receipt["candidate_sha"], "jsSafari",
                candidate_repository=self.candidate_repository)
        self.assertEqual([2465, 58], [item["executed"]
                         for item in receipt["configurations"][0]["source"]])
        self.assertEqual(3, receipt["configurations"][0]["consumer"]["executed"])

    def test_public_safari_directory_and_tar_bind_all_real_diagnostic_identities(self):
        receipt, manifest, consumer = self.full_archive("jsSafari")
        rows = self.safari_diagnostic_rows()
        self.assertEqual(72, len(rows))
        self.assertEqual(72, len(set(rows)))
        self.assertIn("0@-9223372036854775808", rows[0])
        full_hosted.verify_raw_files(self.root, receipt, manifest, consumer,
                                     candidate_repository=self.candidate_repository)
        archive = self.root.parent / (self.root.name + "-diagnostic.tar")
        self.addCleanup(archive.unlink, missing_ok=True)
        for index, lane in enumerate(receipt["configurations"]):
            report = self.root / lane["configuration"] / "xml/dyn4k-core/TEST-all.xml"
            original = report.read_bytes()
            modified_ns = report.stat().st_mtime_ns
            for mutation in ("deleted", "duplicate", "truncated", "truncated-tail",
                             "truncated-transform", "wrong-zero-sign",
                             "wrong-fixture",
                             "wrong-method", "wrong-phase", "wrong-order", "wrong-step"):
                with self.subTest(configuration=lane["configuration"], mutation=mutation):
                    changed = json.loads(json.dumps(receipt))
                    suite = ET.fromstring(original)
                    output = suite.find("system-out")
                    actual = output.text.splitlines(keepends=True)
                    self.assertEqual(72, len(actual))
                    if mutation == "deleted":
                        del actual[17]
                    elif mutation == "duplicate":
                        actual[17] = actual[16]
                    elif mutation == "truncated":
                        actual[17] = actual[17].split("\tepa.replay.depthMatchesResult=", 1)[0]
                    elif mutation == "truncated-tail":
                        actual[4] = actual[4].rsplit("manifold.point.0.id=", 1)[0] + \
                            "manifold.point.0.id=indexed:3\n"
                    elif mutation == "truncated-transform":
                        fields = actual[0].split("\t")
                        transform = next(i for i, field in enumerate(fields)
                                         if field.startswith("a.transform="))
                        fields[transform] = "a.transform=1"
                        actual[0] = "\t".join(fields)
                    elif mutation == "wrong-zero-sign":
                        fields = actual[0].split("\t")
                        transform = next(i for i, field in enumerate(fields)
                                         if field.startswith("a.transform="))
                        values = fields[transform].split("=", 1)[1].split(",")
                        values[values.index("0@0")] = "-0@0"
                        fields[transform] = "a.transform=" + ",".join(values)
                        actual[0] = "\t".join(fields)
                    else:
                        old, new = {
                            "wrong-fixture": ("fixture=CirclePolygon", "fixture=CircleSlice"),
                            "wrong-method": ("method=detectGjk", "method=detectSat"),
                            "wrong-phase": ("phase=center", "phase=shifted"),
                            "wrong-order": ("order=forward", "order=reverse"),
                            "wrong-step": ("step=0", "step=1"),
                        }[mutation]
                        actual[12 if mutation == "wrong-fixture" else 0] = actual[
                            12 if mutation == "wrong-fixture" else 0].replace(old, new, 1)
                    output.text = "".join(actual)
                    report.write_bytes(ET.tostring(suite))
                    os.utime(report, ns=(modified_ns, modified_ns))
                    record = changed["configurations"][index]["source"][0]["reports"][0]
                    record["sha256"] = full_hosted.sha256(report)
                    changed["files"] = full_hosted.archive_inventory(self.root)
                    try:
                        with self.assertRaisesRegex(ValueError, "Safari diagnostic"):
                            full_hosted.verify_raw_files(
                                self.root, changed, manifest, consumer,
                                candidate_repository=self.candidate_repository)
                        if mutation in ("deleted", "duplicate", "truncated", "truncated-tail",
                                        "truncated-transform", "wrong-zero-sign"):
                            (self.root / "receipt.json").write_text(json.dumps(changed))
                            full_hosted.package_archive(self.root, archive)
                            with mock.patch.object(full_hosted, "load_corpus",
                                                   return_value=manifest):
                                with self.assertRaisesRegex(ValueError, "Safari diagnostic"):
                                    full_hosted.verify_transport_archive(
                                        archive, changed["candidate_sha"], "jsSafari",
                                        candidate_repository=self.candidate_repository)
                    finally:
                        report.write_bytes(original)
                        os.utime(report, ns=(modified_ns, modified_ns))
        (self.root / "receipt.json").write_text(json.dumps(receipt))
        full_hosted.package_archive(self.root, archive)
        with mock.patch.object(full_hosted, "load_corpus", return_value=manifest):
            full_hosted.verify_transport_archive(
                archive, receipt["candidate_sha"], "jsSafari",
                candidate_repository=self.candidate_repository)

    def test_public_safari_rejects_resealed_noncanonical_zero(self):
        receipt, manifest, consumer = self.full_archive("jsSafari")
        rows = self.safari_diagnostic_rows()
        self.assertEqual(72, len(rows))
        self.assertEqual(72, len(set(rows)))
        archive = self.root.parent / (self.root.name + "-noncanonical-zero.tar")
        self.addCleanup(archive.unlink, missing_ok=True)
        full_hosted.verify_raw_files(self.root, receipt, manifest, consumer,
                                     candidate_repository=self.candidate_repository)
        (self.root / "receipt.json").write_text(json.dumps(receipt))
        full_hosted.package_archive(self.root, archive)
        with mock.patch.object(full_hosted, "load_corpus", return_value=manifest):
            full_hosted.verify_transport_archive(
                archive, receipt["candidate_sha"], "jsSafari",
                candidate_repository=self.candidate_repository)

        for index, lane in enumerate(receipt["configurations"]):
            report = self.root / lane["configuration"] / "xml/dyn4k-core/TEST-all.xml"
            original = report.read_bytes()
            modified_ns = report.stat().st_mtime_ns
            self.assertEqual("".join(rows), ET.fromstring(original).findtext("system-out"))
            for value in ("1e-999@0", "1e-999@-9223372036854775808",
                          "0e999@0", "0e999@-9223372036854775808",
                          "0.0@0", "0.0@-9223372036854775808",
                          "0e-999@0", "-0.0@-9223372036854775808"):
                with self.subTest(configuration=lane["configuration"], value=value):
                    changed = json.loads(json.dumps(receipt))
                    suite = ET.fromstring(original)
                    output = suite.find("system-out")
                    actual = output.text.splitlines(keepends=True)
                    self.assertEqual(rows, actual)
                    fields = actual[0].split("\t")
                    transform = next(i for i, field in enumerate(fields)
                                     if field.startswith("a.transform="))
                    values = fields[transform].split("=", 1)[1].split(",")
                    values[values.index("0@0")] = value
                    fields[transform] = "a.transform=" + ",".join(values)
                    actual[0] = "\t".join(fields)
                    self.assertEqual(72, len(set(actual)))
                    output.text = "".join(actual)
                    try:
                        report.write_bytes(ET.tostring(suite))
                        os.utime(report, ns=(modified_ns, modified_ns))
                        changed["configurations"][index]["source"][0]["reports"][0][
                            "sha256"] = full_hosted.sha256(report)
                        changed["files"] = full_hosted.archive_inventory(self.root)
                        errors = []
                        try:
                            full_hosted.verify_raw_files(
                                self.root, changed, manifest, consumer,
                                candidate_repository=self.candidate_repository)
                        except ValueError as error:
                            errors.append(str(error))
                        (self.root / "receipt.json").write_text(json.dumps(changed))
                        full_hosted.package_archive(self.root, archive)
                        with mock.patch.object(full_hosted, "load_corpus",
                                               return_value=manifest):
                            try:
                                full_hosted.verify_transport_archive(
                                    archive, changed["candidate_sha"], "jsSafari",
                                    candidate_repository=self.candidate_repository)
                            except ValueError as error:
                                errors.append(str(error))
                        self.assertEqual(2, len(errors), errors)
                        self.assertTrue(all("Safari diagnostic" in error for error in errors),
                                        errors)
                    finally:
                        report.write_bytes(original)
                        os.utime(report, ns=(modified_ns, modified_ns))

    def test_safari_real_rows_reject_incomplete_nested_v2_values(self):
        rows = self.safari_diagnostic_rows()
        suite = ET.Element("testsuite")
        for method in ("capsuleSlice", "circlePolygon", "circleSegment", "circleSlice",
                       "polygonCapsule", "polygonPolygon"):
            ET.SubElement(suite, "testcase", classname=
                          "jsBrowserTest.org.dyn4j.collision.narrowphase."
                          "WindowsCollisionIntermediateDiagnosticTest",
                          name=f"{method}[js, browser, Safari26.6.2, MacOS10.15.7]")
        output = ET.SubElement(suite, "system-out")
        output.text = "".join(rows)
        full_hosted.check_safari_diagnostic_suite(suite)
        self.assertTrue(any("\ta.foci.world=null\t" in row for row in rows))
        self.assertTrue(any("\tepa.replay.simplex=\t" in row for row in rows))
        mutations = (
            ("a.shape.local", "kind=Capsule|center=1"),
            ("a.polygon.edgeArithmetic", "0:1"),
            ("a.foci.world", "1"),
            ("a.axes.withB", "1"),
            ("clip.probe.feature.a", "point:0:1"),
            ("sat.candidates", "x"),
            ("sat.winner.preOrientation", "1"),
            ("epa.replay.epsilon", "1"),
            ("epa.replay.simplex", "1"),
            ("epa.iteration.records", "1"),
            ("epa.edge.a", "1"),
            ("manifold.normal", "1"),
            ("manifold.point.0.position", "1"),
        )
        for key, invalid in mutations:
            with self.subTest(field=key):
                changed = rows.copy()
                index = next(i for i, row in enumerate(changed)
                             if any(field.startswith(key + "=") and field != key + "=na"
                                    and field != key + "=null" and field != key + "="
                                    for field in row.split("\t")))
                fields = changed[index].split("\t")
                field_index = next(i for i, field in enumerate(fields)
                                   if field.startswith(key + "="))
                fields[field_index] = f"{key}={invalid}"
                changed[index] = "\t".join(fields)
                output.text = "".join(changed)
                with self.assertRaisesRegex(ValueError, "Safari diagnostic"):
                    full_hosted.check_safari_diagnostic_suite(suite)
        for key, original, invalid in (
                ("a.foci.world", "null", "nul"),
                ("a.axes.withB", "null", "nul"),
                ("epa.edge.a", "na", "n"),
                ("epa.replay.simplex", "", ";"),
                ("epa.iteration.records", "", ":")):
            with self.subTest(field=key, original=original):
                changed = rows.copy()
                index = next(i for i, row in enumerate(changed)
                             if f"\t{key}={original}\t" in row)
                changed[index] = changed[index].replace(
                    f"\t{key}={original}\t", f"\t{key}={invalid}\t", 1)
                output.text = "".join(changed)
                with self.assertRaisesRegex(ValueError, "Safari diagnostic"):
                    full_hosted.check_safari_diagnostic_suite(suite)
        changed = rows.copy()
        changed[0] = changed[0].replace("a.transform=1@4607182418800017408,",
                                        "a.transform=1@1,", 1)
        output.text = "".join(changed)
        with self.assertRaisesRegex(ValueError, "Safari diagnostic"):
            full_hosted.check_safari_diagnostic_suite(suite)
        keys = {field.split("=", 1)[0] for row in rows for field in row.split("\t")
                if "=" in field}
        for key in sorted(keys):
            with self.subTest(malformed_field=key):
                changed = rows.copy()
                index = next(i for i, row in enumerate(changed)
                             if any(field.startswith(key + "=") for field in row.split("\t")))
                fields = changed[index].split("\t")
                field_index = next(i for i, field in enumerate(fields)
                                   if field.startswith(key + "="))
                fields[field_index] = f"{key}=x"
                changed[index] = "\t".join(fields)
                output.text = "".join(changed)
                with self.assertRaisesRegex(ValueError, "Safari diagnostic"):
                    full_hosted.check_safari_diagnostic_suite(suite)

    def test_safari_v2_number_requires_explicit_zero_sign_to_match_raw_bits(self):
        for value in ("0@0", "0@-9223372036854775808",
                      "-0@-9223372036854775808", "1@4607182418800017408",
                      "5e-324@1", "-5e-324@-9223372036854775807",
                      "NaN@9221120237041090560", "Infinity@9218868437227405312",
                      "-Infinity@-4503599627370496"):
            with self.subTest(value=value):
                full_hosted.safari_v2_number(value, "a.transform")
        for value in ("-0@0", "-0.0@0", "-0e2@0", "1@1",
                      "1e-999@0", "1e-999@-9223372036854775808",
                      "-1e-999@0", "-1e-999@-9223372036854775808",
                      "0e999@0", "0e999@-9223372036854775808",
                      "0.0@0", "0.0@-9223372036854775808",
                      "0e-999@0", "-0.0@-9223372036854775808",
                      "1e999@9218868437227405312",
                      "-1e999@-4503599627370496"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "Safari diagnostic"):
                    full_hosted.safari_v2_number(value, "a.transform")

    def test_public_safari_archive_rejects_resealed_product_substitutions(self):
        receipt, manifest, consumer = self.full_archive("jsSafari")
        full_hosted.verify_raw_files(self.root, receipt, manifest, consumer,
                                     candidate_repository=self.candidate_repository)
        for mode_index in range(2):
            for name in ("dyn4k-core", "consumer"):
                for mutation, reason in (("unrelated", "Safari compiler executable differs"),
                                         ("changed-input", "Safari Karma input bytes"),
                                         ("missing-input", "missing or unsafe archive file")):
                    with self.subTest(configuration=mode_index, name=name, mutation=mutation):
                        changed = json.loads(json.dumps(receipt))
                        lane = changed["configurations"][mode_index]
                        product = (lane["consumer_executable"] if name == "consumer" else
                                   lane["source_executables"][name])
                        selected = product["karma_input"]
                        input_file = self.root / selected["archive_path"]
                        product_file = self.root / product["archive_path"]
                        original_input = input_file.read_bytes()
                        input_time = input_file.stat().st_mtime_ns
                        unrelated = product_file.with_name("unrelated-test.js")
                        try:
                            if mutation == "unrelated":
                                product_file.rename(unrelated)
                                product["path"] = str(full_hosted.original_path(
                                    "jsSafari", product["path"]).with_name(
                                    "unrelated-test.js"))
                                product["archive_path"] = unrelated.relative_to(self.root).as_posix()
                            elif mutation == "changed-input":
                                input_file.write_bytes(b"different executed bundle")
                                os.utime(input_file, ns=(input_time, input_time))
                                selected["sha256"] = full_hosted.sha256(input_file)
                                selected["size"] = input_file.stat().st_size
                            else:
                                input_file.unlink()
                            changed["files"] = full_hosted.archive_inventory(self.root)
                            with self.assertRaisesRegex(ValueError, reason):
                                full_hosted.verify_raw_files(
                                    self.root, changed, manifest, consumer,
                                    candidate_repository=self.candidate_repository)
                        finally:
                            if mutation == "unrelated":
                                unrelated.rename(product_file)
                            else:
                                input_file.write_bytes(original_input)
                                os.utime(input_file, ns=(input_time, input_time))

    def test_public_safari_rejects_fabricated_parsed_source_case_in_both_modes(self):
        receipt, manifest, consumer = self.full_archive("jsSafari")
        archived_sha = full_hosted.sha256(self.root / "inputs" / full_hosted.MANIFEST)
        altered = json.loads(json.dumps(manifest))
        selected = [case for case in altered["cases"]
                    if case["classname"] == "org.dyn4j.UpstreamAVLTreeCoverageTest"
                    and case["method"] == "clear" and case["module"] == "dyn4k-core"]
        self.assertEqual(1, len(selected))
        selected[0]["method"] = "unexecutedFabricatedCase"
        receipt["manifest_sha256"] = full_hosted.canonical_hash(altered)
        self.reseal_safari_case(receipt, "dyn4k-core",
                                "jsBrowserTest.org.dyn4j.UpstreamAVLTreeCoverageTest",
                                "clear", "unexecutedFabricatedCase")
        self.assertEqual(archived_sha, full_hosted.sha256(
            self.root / "inputs" / full_hosted.MANIFEST))
        self.assertEqual(archived_sha, full_hosted.sha256(
            self.candidate_repository / full_hosted.MANIFEST))
        self.assert_safari_parsed_case_rejected(receipt, altered, consumer,
                                                "parsed source manifest differs")

    def test_public_safari_rejects_fabricated_parsed_consumer_case_in_both_modes(self):
        receipt, manifest, consumer = self.full_archive("jsSafari")
        relative = "tools/qualification/foundation-probes.json"
        archived_sha = full_hosted.sha256(self.root / "inputs" / relative)
        altered = json.loads(json.dumps(consumer))
        group = next(item for item in altered["groups"] if item["id"] == "consumer-jsSafari")
        selected = [case for case in group["cases"]
                    if case["name"].startswith("namedConstructorsResolveFromPublished")]
        self.assertEqual(1, len(selected))
        selected[0]["name"] = selected[0]["name"].replace(
            "namedConstructorsResolveFromPublishedCommonAndPlatformVariants",
            "unexecutedFabricatedConsumerCase", 1)
        self.reseal_safari_case(receipt, "consumer",
                                "jsBrowserTest.qualification.StagedGeometryTest",
                                "namedConstructorsResolveFromPublishedCommonAndPlatformVariants",
                                "unexecutedFabricatedConsumerCase")
        self.assertEqual(archived_sha, full_hosted.sha256(self.root / "inputs" / relative))
        self.assertEqual(archived_sha, full_hosted.sha256(self.candidate_repository / relative))
        self.assert_safari_parsed_case_rejected(receipt, manifest, altered,
                                                "parsed consumer manifest differs")

    def test_public_safari_directory_and_tar_reject_duplicate_unrelated_source_entry(self):
        receipt, manifest, consumer = self.full_archive("jsSafari")
        archive = self.root.parent / (self.root.name + "-duplicate-source.tar")
        self.addCleanup(archive.unlink, missing_ok=True)
        with mock.patch.object(full_hosted, "load_corpus", return_value=manifest):
            full_hosted.verify_raw_files(self.root, receipt, manifest, consumer,
                                         candidate_repository=self.candidate_repository)
            (self.root / "receipt.json").write_text(json.dumps(receipt))
            full_hosted.package_archive(self.root, archive)
            full_hosted.verify_transport_archive(
                archive, receipt["candidate_sha"], "jsSafari",
                candidate_repository=self.candidate_repository)
        tree = git_oid(self.candidate_repository,
                       f"{receipt['candidate_sha']}:tools/qualification")
        raw = subprocess.check_output(["git", "-C", str(self.candidate_repository),
                                       "cat-file", "tree", tree])
        first_end = raw.index(b"\0") + 21
        self.assertNotIn(b"safari-karma-reporter.js\0", raw[:first_end])
        write_loose_object(self.candidate_repository, tree, raw + raw[:first_end], "tree")
        with mock.patch.object(full_hosted, "load_corpus", return_value=manifest):
            with self.assertRaisesRegex(ValueError, "identity differs"):
                full_hosted.verify_raw_files(self.root, receipt, manifest, consumer,
                                             candidate_repository=self.candidate_repository)
            with self.assertRaisesRegex(ValueError, "identity differs"):
                full_hosted.verify_transport_archive(
                    archive, receipt["candidate_sha"], "jsSafari",
                    candidate_repository=self.candidate_repository)

    def test_public_safari_directory_and_tar_reject_corrupt_manifest_blob(self):
        receipt, manifest, consumer = self.full_archive("jsSafari")
        relative = full_hosted.MANIFEST
        source = self.candidate_repository / relative
        altered = source.read_bytes() + b"\n"
        source.write_bytes(altered)
        subprocess.run(["git", "-C", str(self.candidate_repository), "add", relative],
                       check=True)
        subprocess.run(["git", "-C", str(self.candidate_repository), "-c",
                        "user.name=Test", "-c", "user.email=test@example.invalid",
                        "commit", "-qm", "alternate manifest bytes"], check=True)
        changed = git_oid(self.candidate_repository, "HEAD")
        subprocess.run(["git", "-C", str(self.candidate_repository), "checkout", "-q",
                        "--detach", receipt["candidate_sha"]], check=True)
        source.write_bytes(altered)
        replace_loose_object(self.candidate_repository, git_oid(
            self.candidate_repository, f"{receipt['candidate_sha']}:{relative}"),
            git_oid(self.candidate_repository, f"{changed}:{relative}"), "blob")
        subprocess.run(["git", "-C", str(self.candidate_repository), "update-index",
                        "--assume-unchanged", relative], check=True)
        (self.root / "inputs" / relative).write_bytes(altered)
        receipt["files"] = full_hosted.archive_inventory(self.root)
        archive = self.root.parent / (self.root.name + "-corrupt-manifest.tar")
        self.addCleanup(archive.unlink, missing_ok=True)
        (self.root / "receipt.json").write_text(json.dumps(receipt))
        full_hosted.package_archive(self.root, archive)
        with mock.patch.object(full_hosted, "load_corpus", return_value=manifest):
            with self.assertRaisesRegex(ValueError, "object identity differs"):
                full_hosted.verify_raw_files(self.root, receipt, manifest, consumer,
                                             candidate_repository=self.candidate_repository)
            with self.assertRaisesRegex(ValueError, "object identity differs"):
                full_hosted.verify_transport_archive(
                    archive, receipt["candidate_sha"], "jsSafari",
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
