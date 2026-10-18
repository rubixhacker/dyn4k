import csv
import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import full_corpus
import qualify


class FullCorpusGateTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        core = self.root / "dyn4k-core/src/commonTest/kotlin"
        sources = (
            ("org.dyn4j.geometry", "FoundationPackageBridgeTest",
             "rotationHelpersKeepIdentityAndReturnIndependentCopies"),
            ("org.dyn4j.coverage.world.core", "PhysicsWorldCoreCoverageTest", "world"),
            ("org.dyn4j.coverage.dynamics.joint", "DistanceJointCoreCoverageTest", "joint"),
            ("org.dyn4j.coverage.collision.detection", "GjkCoverageTest", "detection"),
            ("org.dyn4j.coverage", "DiagnosticTest", "supplemental"),
        )
        for package, classname, method in sources:
            source = core / Path(*package.split(".")) / (classname + ".kt")
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(f"package {package}\nclass {classname} {{ @Test fun {method}() {{}} }}\n")
            if method == "world":
                self.source = source
        facade = self.root / "dyn4k/src/commonTest/kotlin/dyn4k/FacadeTest.kt"
        facade.parent.mkdir(parents=True)
        facade.write_text("package dyn4k\nclass FacadeTest { @Test fun bridge() {} }\n")
        jvm = self.root / "dyn4k/src/jvmTest/kotlin/dyn4k/JvmTest.kt"
        jvm.parent.mkdir(parents=True)
        jvm.write_text("package dyn4k\nclass JvmTest { @Test fun nativeOnly() {} }\n")
        self.cases = full_corpus.scan_sources(self.root)
        self.assertEqual(7, len(self.cases))
        self.mappings = [{"original": "org.dyn4j.WorldTest#world",
                          "original_source": "src/test/java/org/dyn4j/WorldTest.java",
                          "original_sha256": "a" * 64, "original_line": 1,
                          "disposition": "PORTABLE",
                          "classname": "org.dyn4j.coverage.world.core.PhysicsWorldCoreCoverageTest",
                          "method": "world", "review": "fixture"}]
        self.manifest = full_corpus.make_manifest(self.cases, self.mappings,
                                                 repository=self.root)
        self.sha = "a" * 40
        self.reports = {}
        self.binding = {"candidate_sha": self.sha,
                        "manifest_sha256": full_corpus.canonical_digest(self.manifest),
                        "source_tree_sha256": self.manifest["source_tree_sha256"],
                        "started_ns": time.time_ns(),
                        "command": list(full_corpus.GRADLE_COMMAND),
                        "exit_code": 0,
                        "reports": {}}
        self.log = self.root / "gradle.log"
        self.log.write_text("\n".join([*(f"> Task {task}" for task in full_corpus.GRADLE_COMMAND[6:]),
                                        "BUILD SUCCESSFUL", ""]))
        self.binding["log"] = str(self.log)
        self.binding["log_sha256"] = full_corpus.digest(self.log.read_bytes())
        self.binding["environment"] = full_corpus.capture_environment(self.root)
        self.artifacts = []
        for module in ("dyn4k-core", "dyn4k"):
            artifact = self.root / module / "build" / "fixture.class"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(module.encode())
            self.artifacts.append(artifact)
        self.binding["artifacts"] = [
            {"module": path.parts[-3], "path": path.relative_to(self.root).as_posix(),
             "sha256": full_corpus.digest(path.read_bytes())} for path in self.artifacts]
        for group in full_corpus.GROUPS:
            path = self.root / (group["id"] + ".xml")
            self.reports[group["id"]] = [path]
            self.write_xml(group)
        self.rebind()

    def write_xml(self, group, omitted=None, duplicate=None, extra=None,
                  state=None, renamed=None, renamed_method=None):
        expected = full_corpus.expected_cases(self.manifest, group)
        cases = [case for case in expected if case != omitted]
        if duplicate is not None:
            cases.append(duplicate)
        if extra is not None:
            cases.append(extra)
        if renamed is not None:
            cases = [("dyn4k.Unknown", name) if case == renamed else case
                     for case in cases for name in [case[1]]]
        if renamed_method is not None:
            cases = [(classname, "other" + group["suffix"])
                     if case == renamed_method else case
                     for case in cases for classname in [case[0]]]
        suite = ET.Element("testsuite", tests=str(len(cases)),
                           failures=str(int(state == "failure")),
                           errors=str(int(state == "error")),
                           skipped=str(int(state == "skipped")), time="0")
        for classname, name in cases:
            case = ET.SubElement(suite, "testcase", classname=classname, name=name, time="0")
            if state and (classname, name) == (extra or cases[-1]):
                ET.SubElement(case, state)
        self.reports[group["id"]][0].write_bytes(ET.tostring(suite))

    def rebind(self):
        self.binding["finished_ns"] = time.time_ns()
        for group_id, paths in self.reports.items():
            self.binding["reports"][group_id] = {
                str(path.relative_to(self.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in paths}

    def check(self):
        return full_corpus.verify_reports(self.root, self.manifest, self.sha,
                                          self.binding, self.reports, mapping=self.mappings)

    def test_source_derived_case_map_passes_and_keeps_platform_cases_separate(self):
        result = self.check()
        self.assertEqual("PASSED", result["status"])
        self.assertEqual(37, result["total_cases"])
        self.assertEqual(1, result["platform_only_cases"])

    def test_extracted_archive_relocates_all_bound_bytes_and_rejects_changes(self):
        archive = self.root / "archive"
        full_corpus.package_archive(self.root, archive, self.manifest, self.mappings,
                                    self.sha, self.binding, self.reports)
        moved = self.root / "relocated"
        tar = self.root / "archive.tar.gz"
        with tarfile.open(tar, "w:gz", format=tarfile.PAX_FORMAT) as output:
            output.add(archive, arcname=".")
        moved.mkdir()
        with tarfile.open(tar, "r:gz") as source:
            source.extractall(moved, filter="data")
        for item in self.binding["artifacts"]:
            self.assertTrue((moved / "evidence" / item["path"]).is_file())
        for bound in self.binding["reports"].values():
            for name in bound:
                self.assertTrue((moved / "evidence" / name).is_file())
        for path in [self.log, *self.artifacts,
                     *(path for paths in self.reports.values() for path in paths)]:
            path.unlink()
        relocated = full_corpus.verify_archive(moved, self.root, self.sha,
                                               require_checkout=False)
        self.assertEqual("PASSED", relocated["status"], relocated["problems"])
        self.assertEqual("UNPASSED", full_corpus.verify_archive(
            moved, self.root, "b" * 40, require_checkout=False)["status"])
        report = moved / "evidence" / self.reports["core-jvm"][0].relative_to(self.root)
        original = report.read_bytes()
        report.write_bytes(original + b"changed")
        self.assertEqual("UNPASSED", full_corpus.verify_archive(
            moved, self.root, self.sha, require_checkout=False)["status"])
        report.write_bytes(original)
        artifact = moved / "evidence" / self.binding["artifacts"][0]["path"]
        artifact.unlink()
        self.assertEqual("UNPASSED", full_corpus.verify_archive(
            moved, self.root, self.sha, require_checkout=False)["status"])

    def test_fake_gradle_command_and_missing_or_changed_log_fail(self):
        baseline = list(self.binding["command"])
        for command in (["true", *baseline[1:]], baseline[:-1],
                        [*baseline, baseline[-1]], [*baseline[:-2], *reversed(baseline[-2:])]):
            self.binding["command"] = command
            self.assertEqual("UNPASSED", self.check()["status"])
        self.binding["command"] = baseline
        self.binding["log"] = str(self.root / "absent.log")
        self.binding["log_sha256"] = "0" * 64
        self.assertEqual("UNPASSED", self.check()["status"])
        self.binding["log"] = str(self.log)
        self.binding["log_sha256"] = full_corpus.digest(self.log.read_bytes())
        self.log.write_text("changed\n")
        self.assertEqual("UNPASSED", self.check()["status"])
        self.binding["log_sha256"] = full_corpus.digest(self.log.read_bytes())
        self.assertEqual("UNPASSED", self.check()["status"])

    def test_runtime_receipt_requires_environment_and_built_artifact_bytes(self):
        self.binding.pop("environment", None)
        self.binding.pop("artifacts", None)
        result = self.check()
        self.assertEqual("UNPASSED", result["status"])
        self.assertTrue(any("environment" in p for p in result["problems"]))
        self.assertTrue(any("artifact" in p for p in result["problems"]))

    def test_runtime_receipt_rejects_changed_tool_and_artifact(self):
        self.binding["environment"]["machine"] = "wrong-machine"
        self.assertEqual("UNPASSED", self.check()["status"])
        self.binding["environment"] = full_corpus.capture_environment(self.root)
        self.artifacts[0].write_bytes(b"changed artifact")
        self.assertEqual("UNPASSED", self.check()["status"])

    def test_nested_test_declaration_keeps_its_enclosing_class_identity(self):
        path = self.root / "dyn4k-core/src/commonTest/kotlin/org/dyn4j/NestedTest.kt"
        path.write_text("package org.dyn4j\nclass Outer { class Inner { @Test fun nested() {} } }\n")
        nested = next(case for case in full_corpus.scan_sources(self.root)
                      if case["method"] == "nested")
        self.assertEqual("org.dyn4j.Outer$Inner", nested["classname"])
        self.assertEqual(2, nested["line"])
        self.assertEqual(6, len(nested["hosts"]))

    def test_missing_unselected_world_joint_and_detection_fail_independently(self):
        group = full_corpus.GROUPS[0]
        for classname, method in (("org.dyn4j.coverage.world.core.PhysicsWorldCoreCoverageTest", "world"),
                                  ("org.dyn4j.coverage.dynamics.joint.DistanceJointCoreCoverageTest", "joint"),
                                  ("org.dyn4j.coverage.collision.detection.GjkCoverageTest", "detection")):
            with self.subTest(method=method):
                self.write_xml(group, omitted=(classname, method + "[jvm]"))
                self.rebind()
                self.assertEqual("UNPASSED", self.check()["status"])
                selected = ("org.dyn4j.geometry.FoundationPackageBridgeTest",
                            "rotationHelpersKeepIdentityAndReturnIndependentCopies[jvm]")
                self.assertIn(selected, self.report_cases(self.reports[group["id"]][0]))
                self.write_xml(group)

    def report_cases(self, path):
        return {(case.get("classname"), case.get("name"))
                for case in ET.parse(path).getroot().iter("testcase")}

    def test_identity_and_outcome_mutations_fail(self):
        group = full_corpus.GROUPS[0]
        identity = ("org.dyn4j.coverage.world.core.PhysicsWorldCoreCoverageTest", "world[jvm]")
        for change in ("rename", "rename_method", "duplicate", "extra", "skip_extra",
                       "fail_extra", "error_extra"):
            with self.subTest(change=change):
                options = {
                    "rename": {"renamed": identity},
                    "rename_method": {"renamed_method": identity},
                    "duplicate": {"duplicate": identity},
                    "extra": {"extra": ("org.dyn4j.Other", "unexpected[jvm]")},
                    "skip_extra": {"extra": ("org.dyn4j.Other", "unexpected[jvm]"), "state": "skipped"},
                    "fail_extra": {"extra": ("org.dyn4j.Other", "unexpected[jvm]"), "state": "failure"},
                    "error_extra": {"extra": ("org.dyn4j.Other", "unexpected[jvm]"), "state": "error"},
                }[change]
                self.write_xml(group, **options)
                self.rebind()
                self.assertEqual("UNPASSED", self.check()["status"])
                self.write_xml(group)

    def test_changed_source_hash_and_candidate_or_report_binding_fail(self):
        self.source.write_text(self.source.read_text() + "\n")
        self.assertEqual("UNPASSED", self.check()["status"])
        self.source.write_text(self.source.read_text()[:-1])
        changed_map = [dict(self.mappings[0], original_sha256="b" * 64)]
        self.assertEqual("UNPASSED", full_corpus.verify_reports(
            self.root, self.manifest, self.sha, self.binding, self.reports,
            mapping=changed_map)["status"])
        self.binding["candidate_sha"] = "b" * 40
        self.assertEqual("UNPASSED", self.check()["status"])
        self.binding["candidate_sha"] = self.sha
        self.assertEqual("UNPASSED", full_corpus.verify_reports(
            self.root, self.manifest, "b" * 40, self.binding, self.reports,
            mapping=self.mappings)["status"])
        self.binding["source_tree_sha256"] = "c" * 64
        self.assertEqual("UNPASSED", self.check()["status"])
        self.binding["source_tree_sha256"] = self.manifest["source_tree_sha256"]
        self.binding["reports"]["core-jvm"]["core-jvm.xml"] = "0" * 64
        self.assertEqual("UNPASSED", self.check()["status"])
        self.rebind()
        self.binding["started_ns"] = time.time_ns() + 1
        self.assertEqual("UNPASSED", self.check()["status"])

    def test_frozen_full_inventory_exceeds_bounded_selected_probe(self):
        repository = Path(__file__).resolve().parents[2]
        manifest = json.loads((repository / "tools/qualification/full-common-corpus.json").read_text())
        probe = json.loads((repository / "tools/qualification/foundation-probes.json").read_text())
        self.assertGreaterEqual(manifest["counts"]["total_methods"], 2505)
        self.assertEqual(2258, manifest["counts"]["reviewed_source_linked_methods"])
        self.assertEqual(32, manifest["counts"]["jvm_only_original_identities"])
        self.assertEqual(full_corpus.make_manifest(full_corpus.scan_sources(repository),
                         manifest["original_mappings"], production=True,
                         repository=repository), manifest)
        selected_groups = [group for group in probe["groups"]
                           if group["id"] in {item["id"] for item in full_corpus.GROUPS}]
        self.assertEqual(6668, sum(len(qualify.expected_probe_cases(probe, group))
                                   for group in selected_groups))
        for selected_group in selected_groups:
            full_group = next(group for group in full_corpus.GROUPS
                              if group["id"] == selected_group["id"])
            self.assertTrue(set(qualify.expected_probe_cases(probe, selected_group)).issubset(
                full_corpus.expected_cases(manifest, full_group)), selected_group["id"])
        linux_group = next(group for group in full_corpus.GROUPS
                           if group["id"] == "core-linuxX64")
        self.assertIn(("linuxX64Test.org.dyn4j.coverage.world.core.CollisionWorldCoreCoverageTest",
                       "createSuccess[linuxX64]"),
                      full_corpus.expected_cases(manifest, linux_group))
        for group_id, selected_count in (("core-jvm", 1066), ("jvm", 47)):
            group = next(item for item in full_corpus.GROUPS if item["id"] == group_id)
            selected_group = next(item for item in probe["groups"] if item["id"] == group_id)
            expected = full_corpus.expected_cases(manifest, group)
            selected = set(qualify.expected_probe_cases(probe, selected_group))
            self.assertEqual(selected_count, len(selected))
            self.assertLess(selected, expected)
        unselected = full_corpus.expected_cases(manifest, full_corpus.GROUPS[0]) - set(
            qualify.expected_probe_cases(probe, probe["groups"][0]))
        for area in ("world", "joint", "collision"):
            self.assertTrue(any(area in classname.lower() for classname, _ in unselected), area)

    def test_full_source_map_rejects_each_unselected_area_in_complete_synthetic_xml(self):
        repository = Path(__file__).resolve().parents[2]
        manifest = json.loads((repository / "tools/qualification/full-common-corpus.json").read_text())
        with (repository / "tools/qualification/full-common-original-map.tsv").open(newline="") as stream:
            mapping = list(csv.DictReader(stream, delimiter="\t"))
        selected_manifest = json.loads((repository / "tools/qualification/foundation-probes.json").read_text())
        selected = set(qualify.expected_probe_cases(selected_manifest,
                       next(group for group in selected_manifest["groups"]
                            if group["id"] == "core-jvm")))
        candidate = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"],
                                            text=True).strip()
        with tempfile.TemporaryDirectory(dir=repository) as directory:
            reports = {}
            binding = {"candidate_sha": candidate,
                       "manifest_sha256": full_corpus.canonical_digest(manifest),
                       "source_tree_sha256": manifest["source_tree_sha256"],
                       "started_ns": time.time_ns(), "command": list(full_corpus.GRADLE_COMMAND),
                       "exit_code": 0, "reports": {}}
            log = Path(directory) / "gradle.log"
            log.write_text("\n".join([*(f"> Task {task}" for task in full_corpus.GRADLE_COMMAND[6:]),
                                      "BUILD SUCCESSFUL", ""]))
            binding["log"] = str(log)
            binding["log_sha256"] = full_corpus.digest(log.read_bytes())
            binding["environment"] = full_corpus.capture_environment(repository)
            binding["artifacts"] = []
            for module in ("dyn4k-core", "dyn4k"):
                artifact = Path(directory) / (module + ".class")
                artifact.write_bytes(module.encode())
                binding["artifacts"].append({
                    "module": module,
                    "path": artifact.relative_to(repository).as_posix(),
                    "sha256": full_corpus.digest(artifact.read_bytes())})
            for group in full_corpus.GROUPS:
                cases = sorted(full_corpus.expected_cases(manifest, group))
                suite = ET.Element("testsuite", tests=str(len(cases)), failures="0",
                                   errors="0", skipped="0", time="0")
                for classname, name in cases:
                    ET.SubElement(suite, "testcase", classname=classname, name=name, time="0")
                path = Path(directory) / (group["id"] + ".xml")
                path.write_bytes(ET.tostring(suite))
                reports[group["id"]] = [path]
                binding["reports"][group["id"]] = {
                    str(path.relative_to(repository)): hashlib.sha256(path.read_bytes()).hexdigest()}
            binding["finished_ns"] = time.time_ns()
            result = full_corpus.verify_reports(repository, manifest, candidate, binding,
                                                reports, mapping=mapping)
            self.assertEqual("PASSED", result["status"], result["problems"])
            self.assertEqual(sum(len(full_corpus.expected_cases(manifest, group))
                                 for group in full_corpus.GROUPS), result["total_cases"])
            swapped = [dict(row) for row in mapping]
            clear = next(row for row in swapped if row["original"] == "org.dyn4j.AVLTreeTest#clear")
            contains = next(row for row in swapped if row["original"] == "org.dyn4j.AVLTreeTest#contains")
            clear["method"], contains["method"] = contains["method"], clear["method"]
            swapped_manifest = full_corpus.make_manifest(full_corpus.scan_sources(repository),
                                                         swapped, production=True,
                                                         repository=repository)
            self.assertEqual(manifest["counts"], swapped_manifest["counts"])
            self.assertTrue(all(full_corpus.expected_cases(manifest, group) ==
                                full_corpus.expected_cases(swapped_manifest, group)
                                for group in full_corpus.GROUPS))
            binding["manifest_sha256"] = full_corpus.canonical_digest(swapped_manifest)
            mutant = full_corpus.verify_reports(repository, swapped_manifest, candidate, binding,
                                                reports, mapping=swapped)
            self.assertEqual("UNPASSED", mutant["status"])
            self.assertTrue(any("reviewed pair" in p or "candidate commit" in p
                                for p in mutant["problems"]), mutant["problems"])
            binding["manifest_sha256"] = full_corpus.canonical_digest(manifest)
            untracked_map = Path(directory) / "map.tsv"
            untracked_manifest = Path(directory) / "manifest.json"
            untracked_map.write_bytes((repository / "tools/qualification/full-common-original-map.tsv").read_bytes())
            untracked_manifest.write_bytes((repository / "tools/qualification/full-common-corpus.json").read_bytes())
            for paths in ({"mapping_path": untracked_map}, {"manifest_path": untracked_manifest}):
                mutant = full_corpus.verify_reports(repository, manifest, candidate, binding,
                                                    reports, mapping=mapping, **paths)
                self.assertEqual("UNPASSED", mutant["status"])
                self.assertTrue(any("alternate candidate input" in p for p in mutant["problems"]))
            for path, argument in ((untracked_map, "mapping_path"),
                                   (untracked_manifest, "manifest_path")):
                path.write_bytes(path.read_bytes() + b"\n")
                mutant = full_corpus.verify_reports(repository, manifest, candidate, binding,
                                                    reports, mapping=mapping, **{argument: path})
                self.assertTrue(any("candidate commit bytes differ" in p
                                    for p in mutant["problems"]), mutant["problems"])
            core_path = reports["core-jvm"][0]
            original_xml = core_path.read_bytes()
            available = full_corpus.expected_cases(manifest, full_corpus.GROUPS[0]) - selected
            for area in ("world", "joint", "collision"):
                missing = next(case for case in sorted(available)
                               if area in case[0].lower())
                suite = ET.fromstring(original_xml)
                victim = next(case for case in suite.findall("testcase")
                              if (case.get("classname"), case.get("name")) == missing)
                suite.remove(victim)
                suite.set("tests", str(int(suite.get("tests")) - 1))
                core_path.write_bytes(ET.tostring(suite))
                binding["reports"]["core-jvm"][str(core_path.relative_to(repository))] = hashlib.sha256(
                    core_path.read_bytes()).hexdigest()
                binding["finished_ns"] = time.time_ns()
                self.assertTrue(selected.issubset(self.report_cases(core_path)))
                result = full_corpus.verify_reports(repository, manifest, candidate, binding,
                                                    reports, mapping=mapping)
                self.assertEqual("UNPASSED", result["status"], area)
                self.assertTrue(any("missing" in problem for problem in result["problems"]), area)
            core_path.write_bytes(original_xml)

    def test_untracked_common_main_is_rejected_before_and_after_run_and_by_verify(self):
        repository = Path(__file__).resolve().parents[2]
        upstream = Path(os.environ["DYN4K_UPSTREAM_SOURCE"])
        revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"],
                                           text=True).strip()
        self.assertEqual(full_corpus.ORIGINAL_REVISION, revision)
        with tempfile.TemporaryDirectory() as directory:
            upstream_fixture = Path(directory) / "upstream"
            subprocess.run(["git", "clone", "--quiet", "--depth=1", "-c", "core.autocrlf=false",
                            upstream.resolve().as_uri(), str(upstream_fixture)], check=True)
            cloned_revision = subprocess.check_output(
                ["git", "-C", str(upstream_fixture), "rev-parse", "HEAD"], text=True).strip()
            self.assertEqual(full_corpus.ORIGINAL_REVISION, cloned_revision)
            clone = Path(directory) / "candidate"
            subprocess.run(["git", "clone", "--quiet", "--depth=1", "-c", "core.autocrlf=false",
                            repository.as_uri(),
                            str(clone)], check=True)
            candidate = subprocess.check_output(["git", "-C", str(clone), "rev-parse", "HEAD"],
                                                text=True).strip()
            manifest = json.loads((clone / full_corpus.MANIFEST_PATH).read_text())
            with (clone / full_corpus.MAP_PATH).open(newline="") as stream:
                mapping = list(csv.DictReader(stream, delimiter="\t"))
            for relative in (".omo/session.json", "kotlin-js-store/package.json",
                             ".gradle/cache.bin", "build/generated.bin",
                             ".pytest_cache/cache.bin",
                             "dyn4k-core/build/generated/src/Cache.kt"):
                output = clone / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"generated")
            started = time.time_ns()
            log = clone / "dyn4k-core/build/qualification/gradle.log"
            log.parent.mkdir(parents=True)
            log_text = "\n".join([*(f"> Task {task}" for task in full_corpus.GRADLE_COMMAND[6:]),
                                  "BUILD SUCCESSFUL", ""])
            log.write_text(log_text)
            artifacts = []
            for module in ("dyn4k-core", "dyn4k"):
                path = clone / module / "build/qualification/fixture.class"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(module.encode())
                artifacts.append(path)
            xml_bytes = {}
            reports = {}
            for group in full_corpus.GROUPS:
                suite_cases = sorted(full_corpus.expected_cases(manifest, group))
                suite = ET.Element("testsuite", tests=str(len(suite_cases)), failures="0",
                                   errors="0", skipped="0", time="0")
                for classname, name in suite_cases:
                    ET.SubElement(suite, "testcase", classname=classname, name=name, time="0")
                path = clone / group["pattern"].replace("TEST-*.xml", "TEST-full.xml")
                path.parent.mkdir(parents=True, exist_ok=True)
                xml_bytes[path] = ET.tostring(suite)
                path.write_bytes(xml_bytes[path])
                reports[group["id"]] = [path]
            finished = time.time_ns()
            binding = {"candidate_sha": candidate,
                       "manifest_sha256": full_corpus.canonical_digest(manifest),
                       "source_tree_sha256": manifest["source_tree_sha256"],
                       "started_ns": started, "finished_ns": finished,
                       "command": list(full_corpus.GRADLE_COMMAND), "exit_code": 0,
                       "log": str(log), "log_sha256": full_corpus.digest(log.read_bytes()),
                       "environment": full_corpus.capture_environment(clone),
                       "artifacts": full_corpus.capture_artifacts(clone, started, finished),
                       "reports": {group_id: {
                           str(path.relative_to(clone)): full_corpus.digest(path.read_bytes())
                           for path in paths} for group_id, paths in reports.items()}}
            def verify():
                return full_corpus.verify_reports(
                    clone, manifest, candidate, binding, reports, mapping=mapping,
                    upstream=upstream_fixture, require_checkout=True)
            positive = verify()
            self.assertEqual("PASSED", positive["status"], positive["problems"])
            self.assertEqual(sum(len(full_corpus.expected_cases(manifest, group))
                                 for group in full_corpus.GROUPS), positive["total_cases"])
            self.assertEqual([], full_corpus.candidate_checkout_problems(clone, candidate))
            binding_file = Path(directory) / "binding.json"
            result_file = Path(directory) / "result.json"
            run_log = Path(directory) / "run.log"
            argv = ["full_corpus.py", "run", "--repository", str(clone),
                    "--candidate-sha", candidate,
                    "--manifest", str(clone / full_corpus.MANIFEST_PATH),
                    "--mapping", str(clone / full_corpus.MAP_PATH),
                    "--upstream", str(upstream_fixture), "--binding", str(binding_file),
                    "--output", str(result_file), "--log", str(run_log), "--",
                    *full_corpus.GRADLE_COMMAND]
            original_run = subprocess.run
            def forbid_gradle(command, *args, **kwargs):
                if command == full_corpus.GRADLE_COMMAND:
                    raise AssertionError("Gradle started with untracked candidate source")
                return original_run(command, *args, **kwargs)
            source_paths = (
                "dyn4k-core/src/commonMain/kotlin/.pytest_cache/UntrackedCandidateCode.kt",
                "dyn4k-core/src/commonMain/kotlin/org/dyn4j/UntrackedCandidateCode.kt",
            )
            for relative in source_paths:
                with self.subTest(source=relative):
                    source = clone / relative
                    source.parent.mkdir(parents=True, exist_ok=True)
                    source.write_text("package org.dyn4j\nclass UntrackedCandidateCode\n")
                    standalone = verify()
                    self.assertEqual("UNPASSED", standalone["status"], standalone["problems"])
                    self.assertTrue(any(relative in problem for problem in standalone["problems"]),
                                    standalone["problems"])
                    with mock.patch.object(full_corpus.sys, "argv", argv), \
                            mock.patch.object(full_corpus.subprocess, "run", side_effect=forbid_gradle):
                        with self.assertRaisesRegex(ValueError, "UntrackedCandidateCode.kt"):
                            full_corpus.main()
                    source.unlink()

                    def emit_synthetic_run(command, *args, **kwargs):
                        if command == full_corpus.GRADLE_COMMAND:
                            source.write_text("package org.dyn4j\nclass UntrackedCandidateCode\n")
                            for path, raw in xml_bytes.items():
                                path.write_bytes(raw)
                            for path in artifacts:
                                path.write_bytes(path.parent.parent.parent.name.encode())
                            return subprocess.CompletedProcess(command, 0, log_text)
                        return original_run(command, *args, **kwargs)
                    with mock.patch.object(full_corpus.sys, "argv", argv), \
                            mock.patch.object(full_corpus.subprocess, "run", side_effect=emit_synthetic_run):
                        self.assertEqual(1, full_corpus.main())
                    result = json.loads(result_file.read_text())
                    self.assertEqual("UNPASSED", result["status"], result["problems"])
                    self.assertTrue(any(relative in problem for problem in result["problems"]),
                                    result["problems"])
                    source.unlink()
                    binding["finished_ns"] = time.time_ns()
                    clean_again = verify()
                    self.assertEqual("PASSED", clean_again["status"], clean_again["problems"])
            for relative in ("dyn4k-core/src/commonTest/kotlin/Extra.kt",
                             "dyn4k/src/commonMain/kotlin/Extra.kt",
                             "buildSrc/src/main/kotlin/Extra.kt", "gradle/extra.gradle.kts",
                             "scripts/extra.py", "local.properties"):
                with self.subTest(relative=relative):
                    path = clone / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("candidate input\n")
                    problems = full_corpus.candidate_checkout_problems(clone, candidate)
                    self.assertTrue(any(relative in problem for problem in problems), problems)
                    path.unlink()
            source = clone / source_paths[1]
            source.write_text("package org.dyn4j\nclass UntrackedCandidateCode\n")
            exclude = clone / ".git/info/exclude"
            exclude.write_text(exclude.read_text() + "\n" + source.relative_to(clone).as_posix() + "\n")
            ignored_problems = full_corpus.candidate_checkout_problems(clone, candidate)
            self.assertTrue(any("UntrackedCandidateCode.kt" in problem
                                for problem in ignored_problems), ignored_problems)


if __name__ == "__main__":
    unittest.main()
