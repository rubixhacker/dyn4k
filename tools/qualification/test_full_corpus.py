import csv
import hashlib
import json
import subprocess
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

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
                        "command": ["./gradlew", "--rerun-tasks"] + [
                            f":{module}:{task}" for _, task, _ in full_corpus.HOSTS
                            for module in ("dyn4k-core", "dyn4k")],
                        "exit_code": 0,
                        "reports": {}}
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
        for group_id, minimum_full, selected_count in (("core-jvm", 2444, 1066),
                                                        ("jvm", 61, 47)):
            group = next(item for item in full_corpus.GROUPS if item["id"] == group_id)
            selected_group = next(item for item in probe["groups"] if item["id"] == group_id)
            expected = full_corpus.expected_cases(manifest, group)
            selected = set(qualify.expected_probe_cases(probe, selected_group))
            self.assertGreaterEqual(len(expected), minimum_full)
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
                       "started_ns": time.time_ns(), "command": ["./gradlew", "--rerun-tasks"] + [
                           f":{module}:{task}" for _, task, _ in full_corpus.HOSTS
                           for module in ("dyn4k-core", "dyn4k")],
                       "exit_code": 0, "reports": {}}
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
            self.assertEqual(15015, result["total_cases"])
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


if __name__ == "__main__":
    unittest.main()
