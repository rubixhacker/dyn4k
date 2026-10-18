import json
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import qualify
import independent_adapter


class QualificationTests(unittest.TestCase):
    GEOMETRY_CASES = (
        "cleanseReturnsTheExactEmptyListAndASeparateEmptyArray",
        "cleanseCopiesNonemptyListsButKeepsTheirPointsAndMutableResult",
        "cleanseKeepsTheBaselineNullInputErrors",
        "geometryExceptionsSupportCommonSubclasses",
        "geometryGettersDispatchThroughBaseTypes",
        "boundsShareTheCompatibilityObjectAndCopyIndependently",
        "projectedIntervalsRetainTheBaselineBoundaryRules",
        "rayPreservesItsLiveStartAndCopiesBothVectors",
        "combinedMassKeepsItsMutableCenterAndFixedModes",
        "circleQueriesUseOneMutableShapeThroughBothApis",
        "polygonExposesLiveVerticesAndKeepsItsCopyIndependent",
        "rectangleProjectsAndCopiesAfterRotation",
        "triangleUsesItsBaselineContainmentRule",
        "segmentQueriesAndStaticIntersectionAgreeWithWorkedCoordinates",
        "linkKeepsNeighborIdentityAndRejectsDirectTransform",
        "curvedShapesSupportQueriesThroughBothApis",
        "halfEllipseRetainsItsLiveEllipseCenterAcrossTranslation",
        "sliceRetainsItsLiveCircleCenterAndQueriesItsArc",
        "geometryFactoriesConstructEveryCurvedBaselineShape",
    )

    def run_synthetic_probe(self, selected, observed, failures=(), errors=(), skipped=()):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous = Path.cwd()
            os.chdir(root)
            try:
                suite = ET.Element(
                    "testsuite", tests=str(len(observed)),
                    failures=str(sum(identity in failures for identity in observed)),
                    errors=str(sum(identity in errors for identity in observed)),
                    skipped=str(sum(identity in skipped for identity in observed)), time="0")
                for identity in observed:
                    case = ET.SubElement(suite, "testcase", classname=identity[0],
                                         name=identity[1], time="0")
                    if identity in failures:
                        ET.SubElement(case, "failure")
                    if identity in errors:
                        ET.SubElement(case, "error")
                    if identity in skipped:
                        ET.SubElement(case, "skipped")
                (root / "fixture.xml").write_bytes(ET.tostring(suite))
                command = [sys.executable, "-c", "from pathlib import Path; "
                           "Path('probe.xml').write_bytes(Path('fixture.xml').read_bytes())"]
                group = {"id": "synthetic", "report_pattern": "probe.xml",
                         "cases": [{"classname": classname, "name": name}
                                   for classname, name in selected]}
                self.assertLess(sum(len(part) + 1 for part in command), 8191)
                return qualify.run_probe(command, ["probe.xml"], "a" * 40,
                                         root / "result.json",
                                         manifest={"kind": "foundation-probe",
                                                   "groups": [group]})
            finally:
                os.chdir(previous)

    def test_frozen_host_manifest_names_integrated_geometry_cases(self):
        manifest = json.loads(Path(__file__).with_name("foundation-probes.json").read_text())
        groups = {group["id"]: group for group in manifest["groups"]}
        self.assertEqual(37, len(groups))
        for group_id, prefix, suffix in (
            ("jvm", "", "[jvm]"),
            ("linuxX64", "linuxX64Test.", "[linuxX64]"),
            ("jsNode", "jsNodeTest.", "[js, node]"),
            ("wasmJsNode", "wasmJsNodeTest.", "[wasmJs, node]"),
            ("wasmWasiNode", "wasmWasiNodeTest.", "[wasmWasi, node]"),
            ("androidHost", "", ""),
        ):
            cases = qualify.expected_probe_cases(manifest, groups[group_id])
            self.assertEqual(47 if group_id == "jvm" else 45, len(cases), group_id)
            self.assertEqual(
                [(f"{prefix}io.github.rubixhacker.dyn4k.GeometryShapeTest", name + suffix)
                 for name in self.GEOMETRY_CASES],
                [case for case in cases if case[0].endswith("GeometryShapeTest")], group_id)
            self.assertIn((f"{prefix}org.dyn4j.geometry.GeometryCopyExtensionTest",
                           "curvedShapeCopiesDispatchVectorCopiesAndKeepIndependentState" + suffix),
                          cases)
            self.assertEqual(1066, len(qualify.expected_probe_cases(
                manifest, groups["core-" + group_id])))
            self.assertEqual(3, len(qualify.expected_probe_cases(
                manifest, groups["consumer-" + group_id])))

        selected_group_ids = (
            "core-jvm", "jvm", "core-linuxX64", "linuxX64",
            "core-jsNode", "jsNode", "core-wasmJsNode", "wasmJsNode",
            "core-wasmWasiNode", "wasmWasiNode", "core-androidHost", "androidHost",
        )
        self.assertEqual(6668, sum(
            len(qualify.expected_probe_cases(manifest, groups[group_id]))
            for group_id in selected_group_ids))

    def test_frozen_core_manifest_names_integrated_epsilon_on_every_host(self):
        manifest = json.loads(Path(__file__).with_name("foundation-probes.json").read_text())
        groups = {group["id"]: group for group in manifest["groups"]}
        core_groups = [group for group in groups.values() if group["id"].startswith("core-")]
        self.assertEqual(12, len(core_groups))
        for group in core_groups:
            prefix = group["classname"].removesuffix(
                "org.dyn4j.geometry.FoundationPackageBridgeTest")
            epsilon = (prefix + "org.dyn4j.coverage.epsilon.UpstreamEpsilonCoverageTest",
                       "compute" + group["name_suffix"])
            cases = qualify.expected_probe_cases(manifest, group)
            self.assertEqual(1066, len(cases), group["id"])
            self.assertEqual(1, cases.count(epsilon), group["id"])
            collision = (prefix + "org.dyn4j.collision.CollisionModelTest",
                         "copyExceptionFromNamesPreservesMessage" + group["name_suffix"])
            self.assertEqual(1, cases.count(collision), group["id"])

    def test_frozen_core_probe_rejects_missing_renamed_and_skipped_selected_cases(self):
        manifest = json.loads(Path(__file__).with_name("foundation-probes.json").read_text())
        core = next(group for group in manifest["groups"] if group["id"] == "core-jvm")
        cases = qualify.expected_probe_cases(manifest, core)
        self.assertEqual(1066, len(cases))
        with tempfile.TemporaryDirectory() as root:
            previous = Path.cwd()
            os.chdir(root)
            try:
                for change in ("missing", "renamed", "skipped"):
                    observed = list(cases)
                    if change == "missing":
                        observed.pop()
                    elif change == "renamed":
                        classname, _ = observed[-1]
                        observed[-1] = (classname, "renamed[jvm]")
                    suite = ET.Element(
                        "testsuite",
                        tests=str(len(observed)),
                        failures="0",
                        errors="0",
                        skipped=str(int(change == "skipped")),
                        time="0",
                    )
                    for index, (classname, name) in enumerate(observed):
                        case = ET.SubElement(
                            suite, "testcase", classname=classname, name=name, time="0")
                        if change == "skipped" and index == 0:
                            ET.SubElement(case, "skipped")
                    report = Path("core.xml")
                    Path("fixture.xml").write_bytes(ET.tostring(suite))
                    command = [
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('core.xml').write_bytes(Path('fixture.xml').read_bytes())",
                    ]
                    self.assertLess(sum(len(part) + 1 for part in command), 8191)
                    result = qualify.run_probe(
                        command,
                        [str(report)],
                        "a" * 40,
                        Path(root) / (change + ".json"),
                        manifest={
                            "kind": "foundation-probe",
                            "case_names": manifest["case_names"],
                            "case_sets": manifest["case_sets"],
                            "groups": [{**core, "report_pattern": str(report)}],
                        },
                    )
                    self.assertEqual("PROBE_FAILED", result["status"], change)
                    self.assertEqual(1066, result["expected"], change)
                    self.assertIn(
                        "skipped cases" if change == "skipped" else "missing selected",
                        result["reason"],
                        change,
                    )
            finally:
                os.chdir(previous)

    def test_frozen_dyn_manifest_names_integrated_polygon_extension(self):
        manifest = json.loads(Path(__file__).with_name("foundation-probes.json").read_text())
        groups = [group for group in manifest["groups"]
                  if group["id"] in ("jvm", "linuxX64", "jsNode", "wasmJsNode",
                                     "wasmWasiNode", "androidHost", "macosArm64",
                                     "iosSimulatorArm64", "tvosSimulatorArm64",
                                     "watchosSimulatorArm64", "iosX64", "mingwX64")]
        self.assertEqual(12, len(groups))
        for group in groups:
            prefix = group["classname"].removesuffix(
                "io.github.rubixhacker.dyn4k.FoundationTest")
            cases = qualify.expected_probe_cases(manifest, group)
            self.assertEqual(47 if group["id"] == "jvm" else 45,
                             len(cases), group["id"])
            for name in ("subclassCanUseItsOwnHelperAndInheritedAlgorithm",
                         "sameSignatureHelperCannotChangePropertyOrSimplification"):
                expected = (prefix + "io.github.rubixhacker.dyn4k.PolygonSubclassExtensionTest",
                            name + group["name_suffix"])
                self.assertEqual(1, cases.count(expected), group["id"])

    def test_frozen_manifest_names_integrated_foundation_and_staged_consumer(self):
        manifest = json.loads(Path(__file__).with_name("foundation-probes.json").read_text())
        groups = {group["id"]: group for group in manifest["groups"]}
        for group in (group for group in groups.values() if group["id"].startswith("core-")):
            prefix = group["classname"].removesuffix(
                "org.dyn4j.geometry.FoundationPackageBridgeTest")
            cases = qualify.expected_probe_cases(manifest, group)
            self.assertEqual(1066, len(cases), group["id"])
            for classname, names in (
                ("FoundationExtraMethodsParityTest", (
                    "rotationKeepsFieldBasedMathAndGetterDispatch",
                    "transformKeepsFieldBasedFactoryAndGetterDispatch")),
                ("Vector2NormalizationParityTest", (
                    "normalizeUsesOneReciprocalAndMutatesTheSameVector",
                    "getNormalizedUsesOneReciprocalAndReturnsANewVector",
                    "normalizeReadsFieldsWithoutCallingOverriddenMagnitude",
                    "getNormalizedCallsOverriddenMagnitudeOnTheSource",
                    "zeroThresholdLeavesMutableVectorAndReturnsFreshZeroCopy",
                    "invalidMagnitudeKeepsTheBaselineFloatingPointBehavior")),
            ):
                for name in names:
                    expected = (prefix + "org.dyn4j.geometry." + classname,
                                name + group["name_suffix"])
                    self.assertEqual(1, cases.count(expected), group["id"])
        consumers = [group for group in groups.values()
                     if group["id"].startswith("consumer-")]
        self.assertEqual(13, len(consumers))
        for group in consumers:
            cases = qualify.expected_probe_cases(manifest, group)
            self.assertEqual(3, len(cases), group["id"])
            base_class, base_name = cases[0]
            expected = (base_class.replace("StagedGeometryTest", "StagedFoundationExtraMethodsTest"),
                        "publishedAliasesRetainKotlinHelpersAndGetterOverrides" +
                        base_name.removeprefix("namedConstructorsResolveFromPublishedCommonAndPlatformVariants"))
            self.assertEqual(1, cases.count(expected), group["id"])

    def test_expanded_host_probe_accepts_extra_passing_full_report_case(self):
        manifest = json.loads(Path(__file__).with_name("foundation-probes.json").read_text())
        group = next(group for group in manifest["groups"] if group["id"] == "jvm")
        cases = qualify.expected_probe_cases(manifest, group)
        self.assertEqual(47, len(cases))
        suite = ET.Element("testsuite", tests="48", failures="0", errors="0", skipped="0")
        for classname, name in cases + [("io.github.rubixhacker.dyn4k.GeometryShapeTest", "unexpected[jvm]")]:
            ET.SubElement(suite, "testcase", classname=classname, name=name, time="0")
        with tempfile.TemporaryDirectory() as root:
            previous = Path.cwd()
            os.chdir(root)
            try:
                report = Path("probe.xml")
                report_group = dict(group, report_pattern=str(report))
                Path("fixture.xml").write_bytes(ET.tostring(suite))
                command = [sys.executable, "-c", "from pathlib import Path; "
                           "Path('probe.xml').write_bytes(Path('fixture.xml').read_bytes())"]
                result = qualify.run_probe(command, [str(report)], "a" * 40,
                                           Path(root) / "result.json",
                                           manifest={**manifest, "groups": [report_group]})
                self.assertEqual("PROBE_PASSED", result["status"])
                self.assertEqual(47, result["expected"])
                self.assertEqual(47, result["executed"])
                self.assertEqual(48, result["reported"])
                self.assertEqual({"jvm": 47, "reported": 48},
                                 {"jvm": result["groups"][0]["executed"],
                                  "reported": result["groups"][0]["reported"]})
            finally:
                os.chdir(previous)

    def test_full_report_allows_extra_passing_cases_without_counting_them_selected(self):
        selected = [("Selected", "one"), ("Selected", "two")]
        result = self.run_synthetic_probe(
            selected, [*selected, ("Supplemental", "pass")])
        self.assertEqual("PROBE_PASSED", result["status"])
        self.assertEqual((2, 2, 3),
                         (result["expected"], result["executed"], result["reported"]))
        self.assertEqual({"expected": 2, "executed": 2, "reported": 3,
                          "failures": 0, "errors": 0, "skipped": 0},
                         {key: result["groups"][0][key]
                          for key in ("expected", "executed", "reported", "failures",
                                      "errors", "skipped")})

    def test_full_report_rejects_a_missing_selected_case(self):
        selected = [("Selected", "one"), ("Selected", "two")]
        result = self.run_synthetic_probe(selected, [selected[0]])
        self.assertEqual("PROBE_FAILED", result["status"])
        self.assertEqual((2, 1, 1),
                         (result["expected"], result["executed"], result["reported"]))
        self.assertIn("missing selected", result["reason"])

    def test_full_report_rejects_a_changed_selected_identity(self):
        selected = [("Selected", "one"), ("Selected", "two")]
        result = self.run_synthetic_probe(
            selected, [selected[0], ("Selected", "renamed-two")])
        self.assertEqual("PROBE_FAILED", result["status"])
        self.assertEqual((2, 1, 2),
                         (result["expected"], result["executed"], result["reported"]))
        self.assertIn("missing selected", result["reason"])

    def test_full_report_rejects_a_duplicate_selected_case(self):
        selected = [("Selected", "one"), ("Selected", "two")]
        result = self.run_synthetic_probe(
            selected, [selected[0], selected[0], selected[1]])
        self.assertEqual("PROBE_FAILED", result["status"])
        self.assertEqual((2, 1, 3),
                         (result["expected"], result["executed"], result["reported"]))
        self.assertIn("duplicate cases", result["reason"])

    def test_full_report_rejects_failing_error_and_skipped_extra_cases(self):
        selected = [("Selected", "one"), ("Selected", "two")]
        failed = ("Unknown", "failed")
        errored = ("Unknown", "error")
        skipped = ("Unknown", "skipped")
        result = self.run_synthetic_probe(
            selected, [*selected, failed, errored, skipped],
            failures=(failed,), errors=(errored,), skipped=(skipped,))
        self.assertEqual("PROBE_FAILED", result["status"])
        self.assertEqual((2, 2, 5),
                         (result["expected"], result["executed"], result["reported"]))
        self.assertEqual((1, 1, 1),
                         (result["failures"], result["errors"], result["skipped"]))
        self.assertIn("failed, errored, or skipped", result["reason"])

    def test_contract_covers_all_targets_and_runtime_families(self):
        rows = qualify.matrix()
        self.assertEqual(28, len(rows))
        self.assertEqual(21, len({row["target"] for row in rows}))
        self.assertEqual(112, len(qualify.expand(rows)))
        self.assertIn("watchosDeviceArm64", {row["target"] for row in rows})
        self.assertIn("Safari", {row["runtime"] for row in rows})
        self.assertEqual("18.2", next(row["minimum"] for row in rows if row["target"] == "js" and row["runtime"] == "Safari"))

    def test_missing_evidence_cannot_pass(self):
        case = qualify.expand(qualify.matrix())[0]
        self.assertEqual("NOT_RUN", qualify.evaluate(case, None)["status"])
        self.assertEqual("UNAVAILABLE", qualify.evaluate(case, {"unavailable_reason": "no device"})["status"])
        self.assertEqual("FAILED", qualify.evaluate(case, {"candidate_sha": "bad", "expected": 4, "executed": 4, "failures": 0})["status"])
        self.assertEqual("FAILED", qualify.evaluate(case, {"candidate_sha": "a" * 40, "expected": 4, "executed": 3, "failures": 0})["status"])

    def test_duplicate_provider_is_diagnosed(self):
        with tempfile.TemporaryDirectory() as root:
            graph = Path(root) / "dependencies.txt"
            graph.write_text("+--- io.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1\n\\--- org.dyn4j:dyn4j:6.0.0\n")
            with self.assertRaisesRegex(ValueError, "duplicate org.dyn4j provider"):
                qualify.check_providers(graph.read_text())

    def test_executor_failure_cannot_return_success(self):
        self.assertFalse(qualify.execution_succeeded({
            "jvm:Java:minimum:default": {
                "error": "command failed or result file missing",
                "exit_code": 1,
            }
        }))
        self.assertTrue(qualify.execution_succeeded({
            "jvm:Java:minimum:default": {
                "expected": 1,
                "executed": 1,
                "failures": 0,
                "skipped": 0,
                "exit_code": 0,
                "invocation_id": "a" * 32,
            }
        }))
        self.assertFalse(qualify.execution_succeeded({
            "jvm:Java:minimum:default": {"unavailable_reason": "no runtime"}
        }))
        self.assertFalse(qualify.execution_succeeded({
            "jvm:Java:minimum:default": {"exit_code": 0}
        }))

    def test_candidate_identity_and_counts_are_required(self):
        case = qualify.expand(qualify.matrix())[0]
        evidence = {"candidate_sha": "a" * 40, "artifact_sha256": "b" * 64,
                    "runtime_identity": "OpenJDK 8u472", "runtime_version": "8u472", "expected": 2,
                    "executed": 2, "failures": 0, "skipped": 0,
                    "consumer": "PASSED", "suite": "complete",
                    "target": case["target"], "runtime": case["runtime"],
                    "version": case["version"], "configuration": case["configuration"]}
        target_hashes = {case["target"]: {evidence["artifact_sha256"]}}
        self.assertNotEqual("PASSED", qualify.evaluate(
            case, evidence, evidence["candidate_sha"], target_hashes)["status"])
        other_target_hashes = {case["target"]: {"c" * 64}}
        self.assertEqual("FAILED", qualify.evaluate(
            case, evidence, evidence["candidate_sha"], other_target_hashes)["status"])
        for field, value in (("expected", 0), ("skipped", 1), ("consumer", "NOT_RUN"),
                             ("artifact_sha256", ""), ("runtime_version", ""),
                             ("configuration", "wrong")):
            changed = dict(evidence, **{field: value})
            self.assertEqual("FAILED", qualify.evaluate(case, changed)["status"])

    def test_noop_cannot_reuse_prior_result(self):
        case = qualify.expand(qualify.matrix())[0]
        with tempfile.TemporaryDirectory() as root:
            result_file = Path(root) / "lane.json"
            result_file.write_text(json.dumps({"candidate_sha": "a" * 40}))
            observed = qualify.execute_plan(
                {case["id"]: {"command": [sys.executable, "-c", "pass"],
                              "result_file": str(result_file)}},
                "a" * 40, Path(root) / "execution.json")
            self.assertIn("error", observed[case["id"]])
            self.assertFalse(result_file.exists())
            self.assertEqual(1, len(list(Path(root).glob("lane.json.previous-*"))))

    def test_probe_rejects_missing_group_and_duplicate_cases(self):
        with tempfile.TemporaryDirectory() as root:
            previous = Path.cwd()
            os.chdir(root)
            try:
                manifest = {"kind": "foundation-probe", "groups": [
                    {"id": "present", "report_pattern": "one.xml",
                     "cases": [{"classname": "C", "name": "one"}]},
                    {"id": "missing", "report_pattern": "missing.xml",
                     "cases": [{"classname": "C", "name": "two"}]},
                ]}
                writer = "from pathlib import Path; Path('one.xml').write_text('<testsuite tests=\"1\" skipped=\"0\" failures=\"0\" errors=\"0\"><testcase classname=\"C\" name=\"one\" time=\"0\"/></testsuite>')"
                result = qualify.run_probe(
                    [sys.executable, "-c", writer], ["one.xml", "missing.xml"],
                    "a" * 40, Path(root) / "probe.json", manifest=manifest)
                self.assertEqual("PROBE_FAILED", result["status"])
                self.assertIn("missing", result["reason"])
                duplicate = "from pathlib import Path; Path('one.xml').write_text('<testsuite tests=\"2\" skipped=\"0\" failures=\"0\" errors=\"0\"><testcase classname=\"C\" name=\"one\" time=\"0\"/><testcase classname=\"C\" name=\"one\" time=\"0\"/></testsuite>')"
                result = qualify.run_probe(
                    [sys.executable, "-c", duplicate], ["one.xml"],
                    "a" * 40, Path(root) / "duplicate.json",
                    manifest={"kind": "foundation-probe", "groups": [manifest["groups"][0]]})
                self.assertEqual("PROBE_FAILED", result["status"])
            finally:
                os.chdir(previous)

    def test_probe_manifest_names_each_added_tree_case(self):
        manifest = {"case_names": ["foundation"]}
        group = {"classname": "dyn4k.FoundationTest", "name_suffix": "[jvm]",
                 "additional_classname": "dyn4k.TreeTest",
                 "additional_case_names": ["inserts", "removes"]}
        self.assertEqual([
            ("dyn4k.FoundationTest", "foundation[jvm]"),
            ("dyn4k.TreeTest", "inserts[jvm]"),
            ("dyn4k.TreeTest", "removes[jvm]"),
        ], qualify.expected_probe_cases(manifest, group))

    def test_full_lane_needs_selected_runtime_suite_and_both_target_binaries(self):
        case = qualify.expand(qualify.matrix())[0]
        sha = "a" * 40
        evidence = {**case, "candidate_sha": sha, "artifact_sha256": "b" * 64,
                    "runtime_identity": "arbitrary", "runtime_version": "wrong",
                    "expected": 2, "executed": 2, "failures": 0, "skipped": 0,
                    "consumer": "PASSED", "suite": "complete"}
        self.assertEqual("FAILED", qualify.evaluate(case, evidence, sha)["status"])
        self.assertIn("manifest", qualify.evaluate(case, evidence, sha)["reason"])

    def test_frozen_full_lane_rejects_runtime_binary_and_case_substitution(self):
        case = qualify.expand(qualify.matrix())[0]
        sha = "a" * 40
        suite = {"schema": 1, "kind": "complete-port", "id": "frozen-five",
                 "areas": ["geometry", "collision", "dynamics", "joints", "compatibility"],
                 "cases": [{"id": area + ":worked", "area": area} for area in
                           ("geometry", "collision", "dynamics", "joints", "compatibility")]}
        hashes = {"dyn4k-core": "b" * 64, "dyn4k": "c" * 64}
        audit = {"candidate_sha": sha, "status": "PASSED", "artifacts": [
            {"path": qualify.target_binary_path(module, case["target"]), "sha256": value}
            for module, value in hashes.items()]}
        candidate = {"schema": 1, "candidate_sha": sha,
                     "suite_manifest_sha256": qualify.manifest_digest(suite),
                     "audit_manifest_sha256": qualify.manifest_digest(audit),
                     "lanes": {case["id"]: {
                         "runtime_identity": "pinned JDK 8 image", "runtime_version": "8u472",
                         "configuration": case["configuration"], "suite_id": suite["id"],
                         "artifact_hashes": hashes}}}
        evidence = {**case, "candidate_sha": sha,
                    "runtime_identity": "pinned JDK 8 image", "runtime_version": "8u472",
                    "suite_id": suite["id"], "expected": 5, "executed": 5,
                    "failures": 0, "skipped": 0, "consumer": "PASSED",
                    "artifact_hashes": hashes, "invocation_id": "d" * 32,
                    "candidate_manifest_sha256": qualify.manifest_digest(candidate),
                    "suite_manifest_sha256": qualify.manifest_digest(suite),
                    "audit_manifest_sha256": qualify.manifest_digest(audit),
                    "exit_code": 0, "command": ["/bin/true"],
                    "case_results": [{"id": item["id"], "status": "PASSED"}
                                     for item in suite["cases"]]}
        self.assertEqual("PASSED", qualify.evaluate(
            case, evidence, sha, candidate, suite, audit)["status"])
        for changed in (
            {**evidence, "runtime_version": "not-the-selected-version"},
            {**evidence, "artifact_hashes": {**hashes, "dyn4k-core": "e" * 64}},
            {**evidence, "artifact_hashes": {**hashes, "dyn4k": "e" * 64}},
            {**evidence, "case_results": evidence["case_results"][:-1]},
            {**evidence, "case_results": evidence["case_results"][:-1] + evidence["case_results"][:1]},
            {**evidence, "expected": 2, "executed": 2},
            {**evidence, "case_results": evidence["case_results"] +
             [{"id": "extra", "status": "PASSED", "value": float("nan")}]},
            {**evidence, "case_results": [{**evidence["case_results"][0], "value": float("nan")}] +
             evidence["case_results"][1:]},
            {**evidence, "candidate_manifest_sha256": "e" * 64},
        ):
            self.assertEqual("FAILED", qualify.evaluate(
                case, changed, sha, candidate, suite, audit)["status"])
        self.assertEqual("FAILED", qualify.evaluate(
            case, evidence, sha, candidate, suite,
            {**audit, "status": "FAILED"})["status"])

    def test_dirty_tracked_checkout_rejects_matching_head(self):
        with tempfile.TemporaryDirectory() as root:
            repository = Path(root)
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            source = repository / "build.gradle.kts"
            source.write_text("version = 1\n")
            subprocess.run(["git", "-C", str(repository), "add", "build.gradle.kts"], check=True)
            subprocess.run(["git", "-C", str(repository), "-c", "user.name=Test",
                            "-c", "user.email=test@example.invalid", "commit", "-qm", "base"], check=True)
            sha = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
            qualify.require_clean_checkout(repository, sha)
            source.write_text("version = 2\n")
            with self.assertRaisesRegex(ValueError, "dirty"):
                qualify.require_clean_checkout(repository, sha)

    def test_untracked_inputs_reject_matching_head_but_generated_outputs_do_not(self):
        with tempfile.TemporaryDirectory() as root:
            repository = Path(root)
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            (repository / ".gitignore").write_text("build/\nlocal.properties\n")
            subprocess.run(["git", "-C", str(repository), "add", ".gitignore"], check=True)
            subprocess.run(["git", "-C", str(repository), "-c", "user.name=Test",
                            "-c", "user.email=test@example.invalid", "commit", "-qm", "base"], check=True)
            sha = subprocess.check_output(
                ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
            for generated in ("build/generated/Unexpected.kt",
                              "dyn4k/build/generated/Unexpected.kt",
                              "consumers/qualification/portable/build/generated/Unexpected.kt",
                              "tools/qualification/__pycache__/qualify.pyc",
                              "kotlin-js-store/yarn.lock",
                              "consumers/qualification/portable/kotlin-js-store/yarn.lock"):
                path = repository / generated
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("generated\n")
            qualify.require_clean_checkout(repository, sha)
            for relevant in ("src/commonMain/kotlin/Unexpected.kt",
                             "src/commonMain/kotlin/build/Unexpected.kt",
                             "extra.gradle.kts", "local.properties"):
                path = repository / relevant
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("input\n")
                with self.assertRaisesRegex(ValueError, "dirty|untracked"):
                    qualify.require_clean_checkout(repository, sha)
                path.unlink()
            qualify.require_clean_checkout(repository, sha)

    def test_forged_audit_cannot_replace_staged_files(self):
        with tempfile.TemporaryDirectory() as root:
            fake = {"candidate_sha": "a" * 40, "status": "PASSED", "artifacts": []}
            with self.assertRaisesRegex(ValueError, "staged audit"):
                qualify.verify_audit_against_staging(fake, Path(root))

    def test_empty_staging_emits_failed_audit_for_every_publication(self):
        with tempfile.TemporaryDirectory() as root:
            repository = Path(root)
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            marker = repository / "README.md"
            marker.write_text("Empty staging fixture.\n")
            subprocess.run(["git", "-C", str(repository), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repository), "-c", "user.name=Test",
                            "-c", "user.email=test@example.invalid", "commit", "-qm", "base"], check=True)
            sha = subprocess.check_output(
                ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
            output = repository / "audit.json"
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("qualify.py")), "audit-staging",
                 "--candidate-sha", sha, "--repository", str(repository / "empty-staging"),
                 *(item for target in sorted(qualify.matrix_targets()) for item in ("--target", target)),
                 "--stage-receipt", str(repository / "empty-staging/.qualification/receipt.json"),
                 "--stage-console", str(repository / "empty-staging/.qualification/stage.log"),
                 "--output", str(output)], cwd=repository, text=True,
                capture_output=True, check=False)
            self.assertEqual(1, result.returncode, result.stderr)
            audit = json.loads(output.read_text())
            self.assertEqual(sha, audit["candidate_sha"])
            self.assertEqual("FAILED", audit["status"])
            self.assertEqual([], audit["artifacts"])
            expected_publications = {
                f"{qualify.target_publication_name(module, target)}: staged POM or Gradle metadata missing"
                for module in qualify.MODULES
                for target in {row["target"] for row in qualify.matrix()}
            }
            self.assertTrue(expected_publications.issubset(set(audit["errors"])))
            self.assertEqual(51, len(audit["errors"]))
            self.assertTrue(any("candidate source tree invalid" in error for error in audit["errors"]))
            self.assertTrue(all(f"{module}: root API documentation artifact missing" in audit["errors"]
                                for module in qualify.MODULES))

    def test_report_refuses_sha_other_than_checkout(self):
        with tempfile.TemporaryDirectory() as root:
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("qualify.py")), "record",
                 "--candidate-sha", "f" * 40, "--output", str(Path(root) / "report.json")],
                text=True, capture_output=True, check=False)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("checkout", result.stderr)

    def test_record_rejects_unverified_full_hosted_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            (repository / "README.md").write_text("fixture\n")
            subprocess.run(["git", "-C", str(repository), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repository), "-c", "user.name=Test",
                            "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
            sha = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"],
                                          text=True).strip()
            bundle = repository / "build/full"
            bundle.mkdir(parents=True)
            (bundle / "receipt.json").write_text(json.dumps({
                "schema": 1, "kind": "hosted-full-common-corpus",
                "candidate_sha": sha, "target": "macosArm64",
                "status": "FULL_COMMON_PASSED", "configurations": [],
            }))
            result = subprocess.run([
                sys.executable, str(Path(__file__).with_name("qualify.py")), "record",
                "--candidate-sha", sha, "--full-hosted-bundle", str(bundle),
                "--output", str(repository / "build/matrix.json"),
            ], cwd=repository, text=True, capture_output=True, check=False)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("full hosted", result.stderr.lower())

    def test_full_hosted_mapping_keeps_server_and_simulator_on_current_lanes(self):
        def receipt(target, runtime):
            return {"target": target, "runtime": runtime,
                    "runner_os": "Windows" if target == "mingwX64" else "macOS",
                    "runner_arch": "ARM64", "runner_name": "fixture-runner",
                    "artifact_hashes": {module: "a" * 64 for module in qualify.MODULES},
                    "manifest_sha256": "b" * 64,
                    "source_tree_sha256": "c" * 64,
                    "map_sha256": "d" * 64,
                    "reviewed_pairs_sha256": "e" * 64,
                    "configurations": [{"configuration": config,
                                        "source": [{"module": "dyn4k-core",
                                                    "case_ids": [str(n) for n in range(2465)]},
                                                   {"module": "dyn4k",
                                                    "case_ids": [str(n) for n in range(58)]}],
                                        "consumer": {"case_ids": ["one", "two", "three"]}}
                                       for config in ("debug-g", "optimized-opt")]}

        server = receipt("mingwX64", {"os_version": "10.0.26100.1"})
        mapped = qualify.full_hosted_lane(server, "f" * 64)
        self.assertEqual("Windows x64", mapped["runtime"])
        self.assertEqual("10.0.26100.1", mapped["runtime_version"])
        self.assertTrue(all(":current:" in lane for lane in mapped["configuration_lanes"]))
        self.assertTrue(all(":minimum:" not in lane for lane in mapped["configuration_lanes"]))
        self.assertTrue(all(item["complete_lane_status"] == "NOT_RUN"
                            for item in mapped["observed_cases"]))

        selected = {"udid": "simulator-1", "runtime": "com.apple.CoreSimulator.SimRuntime.iOS-26-0"}
        simulator = receipt("iosSimulatorArm64", {"simulators": {"iOS": [selected]}})
        simulator["selected_simulator"] = selected
        for config in simulator["configurations"]:
            config["simulator_udid"] = selected["udid"]
        mapped = qualify.full_hosted_lane(simulator, "f" * 64)
        self.assertTrue(all(lane.startswith("iosSimulatorArm64:iOS simulator ARM64:")
                            for lane in mapped["configuration_lanes"]))
        self.assertFalse(any("iOS physical" in lane for lane in mapped["configuration_lanes"]))
        simulator["configurations"][0]["simulator_udid"] = "another-device"
        with self.assertRaisesRegex(ValueError, "simulator"):
            qualify.full_hosted_lane(simulator, "f" * 64)

    def test_complete_suite_selects_portable_and_jvm_only_cases_per_lane(self):
        native = next(case for case in qualify.expand(qualify.matrix())
                      if case["target"] == "macosArm64")
        jvm = next(case for case in qualify.expand(qualify.matrix())
                   if case["target"] == "jvm")
        suite = {"schema": 1, "kind": "complete-port", "id": "fixture-scopes",
                 "areas": ["geometry", "collision", "dynamics", "joints", "compatibility"],
                 "cases": [{"id": area, "area": area, "scope": "portable"}
                           for area in ("geometry", "collision", "dynamics", "joints", "compatibility")]
                          + [{"id": "jvm-only", "area": "compatibility", "scope": "jvm-only"}],
                 "lanes": {native["id"]: {"case_scopes": ["portable"],
                                          "required_gates": ["staged-consumer"]},
                           jvm["id"]: {"case_scopes": ["portable", "jvm-only"],
                                       "required_gates": ["java-source-compatibility"]}},
                 "global_gates": ["publication-contract"]}
        self.assertEqual(5, len(qualify.full_suite_cases(suite, native["id"])))
        self.assertEqual(6, len(qualify.full_suite_cases(suite, jvm["id"])))
        with self.assertRaisesRegex(ValueError, "lane"):
            qualify.full_suite_cases(suite, "unlisted")

    def test_complete_suite_rejects_wrong_reviewed_corpus_binding(self):
        repository = Path(__file__).resolve().parents[2]
        suite = {"schema": 1, "kind": "complete-port", "id": "wrong-corpus",
                 "bindings": {"corpus_sha256": "0" * 64}, "cases": [], "lanes": {}}
        with self.assertRaisesRegex(ValueError, "corpus"):
            qualify.validate_complete_suite_bindings(suite, repository)

    def test_complete_suite_matches_source_and_approved_binding(self):
        repository = Path(__file__).resolve().parents[2]
        relative = "tools/qualification/full-suite-manifest.json"
        approved = repository / relative
        raw = (approved.read_bytes() if approved.is_file() else subprocess.check_output(
            ["git", "-C", str(repository), "show",
             f"6f983ad3a36bdc549c32f5d0883b0a47b28e1963:{relative}"]))
        suite = json.loads(raw)
        self.assertEqual("9aa2f50dd3c38129a70f4ed042f2b7ae5a90d4234def40d70520aad13f36b3fc",
                         qualify.APPROVED_COMPLETE_SUITE_SHA256)
        qualify.validate_complete_suite_bindings(suite, repository)

        import copy
        changes = (
            lambda changed: changed["cases"][0].update(area="geometry" if
                changed["cases"][0]["area"] != "geometry" else "dynamics"),
            lambda changed: changed["lanes"][next(iter(changed["lanes"]))].update(
                required_gates=["staged-consumer"]),
            lambda changed: changed["independent_gates"]["staged-consumer"].update(
                requirement="weakened"),
            lambda changed: changed.update(global_gates=["publication-contract"]),
        )
        for change in changes:
            altered = copy.deepcopy(suite)
            change(altered)
            with self.assertRaisesRegex(ValueError, "complete suite"):
                qualify.validate_complete_suite_bindings(altered, repository)

    def test_complete_suite_seal_binds_originals_and_world_runtime_helper(self):
        import full_suite_manifest

        repository = Path(__file__).resolve().parents[2]
        suite = json.loads((repository / full_suite_manifest.MANIFEST_PATH).read_text())
        corpus = json.loads((repository / full_suite_manifest.CORPUS_PATH).read_text())
        self.assertEqual(2526, len(suite["cases"]))
        self.assertEqual(2526, len({case["id"] for case in suite["cases"]}))
        self.assertEqual(2526, len(corpus["cases"]))
        self.assertEqual(2385, len(corpus["original_mappings"]))
        self.assertEqual(2385, len({row["original"] for row in corpus["original_mappings"]}))
        self.assertEqual(202, len(corpus["source_files"]))
        self.assertEqual("9aa2f50dd3c38129a70f4ed042f2b7ae5a90d4234def40d70520aad13f36b3fc",
                         qualify.manifest_digest(suite))
        full_suite_manifest.validate_manifest(suite, repository)
        qualify.validate_complete_suite_bindings(suite, repository)

        with mock.patch.object(qualify, "APPROVED_COMPLETE_SUITE_SHA256",
                               "60e91e7cab9dcf1c1ccb41eb25fefd6c1579ad147996bb40d94f7fcba91017a3"):
            with self.assertRaisesRegex(ValueError, "independently reviewed manifest"):
                qualify.validate_complete_suite_bindings(suite, repository)

        helper = "dyn4k-core/src/jsTest/kotlin/org/dyn4j/world/WorldNestedViewRuntime.kt"
        self.assertIn(helper, {item["path"] for item in corpus["source_files"]})
        copied = [full_suite_manifest.CORPUS_PATH,
                  "tools/qualification/full-common-original-map.tsv",
                  "tools/qualification/full-common-reviewed-pairs.tsv"]
        copied += [item["path"] for item in corpus["source_files"]]
        copied += [path for paths in full_suite_manifest.GATE_SOURCES.values()
                   for path in paths]
        with tempfile.TemporaryDirectory() as scratch:
            clone = Path(scratch)
            for relative in set(copied):
                target = clone / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((repository / relative).read_bytes())
            full_suite_manifest.validate_manifest(suite, clone)
            changed = clone / helper
            changed.write_bytes(changed.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "source"):
                full_suite_manifest.validate_manifest(suite, clone)

    def test_full_lane_requires_each_independent_gate_receipt(self):
        case = next(row for row in qualify.expand(qualify.matrix())
                    if row["target"] == "macosArm64")
        sha = "a" * 40
        suite = {"schema": 1, "kind": "complete-port", "id": "fixture-gates",
                 "areas": ["geometry", "collision", "dynamics", "joints", "compatibility"],
                 "cases": [{"id": area, "area": area, "scope": "portable"} for area in
                           ("geometry", "collision", "dynamics", "joints", "compatibility")],
                 "lanes": {case["id"]: {"case_scopes": ["portable"],
                                        "required_gates": ["staged-consumer"]}},
                 "global_gates": ["publication-contract"]}
        hashes = {module: "b" * 64 for module in qualify.MODULES}
        audit = {"candidate_sha": sha, "status": "PASSED", "artifacts": [
            {"path": qualify.target_binary_path(module, case["target"]), "sha256": value}
            for module, value in hashes.items()]}
        candidate = {"schema": 1, "candidate_sha": sha,
                     "suite_manifest_sha256": qualify.manifest_digest(suite),
                     "audit_manifest_sha256": qualify.manifest_digest(audit),
                     "lanes": {case["id"]: {"runtime_identity": "fixture-runner",
                                                 "runtime_version": "26.6.2",
                                                 "configuration": case["configuration"],
                                                 "suite_id": suite["id"],
                                                 "artifact_hashes": hashes}}}
        evidence = {**case, "candidate_sha": sha, "runtime_identity": "fixture-runner",
                    "runtime_version": "26.6.2", "expected": 5, "executed": 5,
                    "failures": 0, "skipped": 0, "consumer": "PASSED",
                    "suite_id": suite["id"], "artifact_hashes": hashes,
                    "invocation_id": "d" * 32, "exit_code": 0, "command": ["fixture"],
                    "candidate_manifest_sha256": qualify.manifest_digest(candidate),
                    "suite_manifest_sha256": qualify.manifest_digest(suite),
                    "audit_manifest_sha256": qualify.manifest_digest(audit),
                    "case_results": [{"id": area, "status": "PASSED"} for area in
                                     ("geometry", "collision", "dynamics", "joints", "compatibility")]}
        self.assertEqual("FAILED", qualify.evaluate(
            case, evidence, sha, candidate, suite, audit)["status"])
        gates = {name: {"status": "PASSED", "receipt_sha256": "e" * 64}
                 for name in ("staged-consumer", "publication-contract")}
        self.assertEqual("PASSED", qualify.evaluate(
            case, {**evidence, "gate_results": gates}, sha, candidate, suite, audit)["status"])
        gates["publication-contract"] = {"status": "NOT_RUN"}
        self.assertEqual("FAILED", qualify.evaluate(
            case, {**evidence, "gate_results": gates}, sha, candidate, suite, audit)["status"])

    def test_production_manifest_cannot_use_self_reported_gate_receipts(self):
        results = [{"id": "macosArm64:macOS ARM64:current:debug-g", "status": "PASSED"}]
        independent_adapter.apply(results, {}, {})
        self.assertEqual("FAILED", results[0]["status"])
        self.assertIn("independent raw gate archives", results[0]["reason"])


if __name__ == "__main__":
    unittest.main()
