import json
import os
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import qualify


class QualificationTests(unittest.TestCase):
    GEOMETRY_CASES = (
        "cleanseReturnsTheExactEmptyListAndASeparateEmptyArray",
        "cleanseCopiesNonemptyListsButKeepsTheirPointsAndMutableResult",
        "cleanseKeepsTheBaselineNullInputErrors",
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

    def test_frozen_host_manifest_names_integrated_geometry_cases(self):
        manifest = json.loads(Path(__file__).with_name("foundation-probes.json").read_text())
        groups = {group["id"]: group for group in manifest["groups"]}
        self.assertEqual(31, len(groups))
        for group_id, prefix, suffix in (
            ("jvm", "", "[jvm]"),
            ("linuxX64", "linuxX64Test.", "[linuxX64]"),
            ("jsNode", "jsNodeTest.", "[js, node]"),
            ("wasmJsNode", "wasmJsNodeTest.", "[wasmJs, node]"),
            ("wasmWasiNode", "wasmWasiNodeTest.", "[wasmWasi, node]"),
            ("androidHost", "", ""),
        ):
            cases = qualify.expected_probe_cases(manifest, groups[group_id])
            self.assertEqual(28, len(cases), group_id)
            self.assertEqual(
                [(f"{prefix}io.github.rubixhacker.dyn4k.GeometryShapeTest", name + suffix)
                 for name in self.GEOMETRY_CASES],
                [case for case in cases if case[0].endswith("GeometryShapeTest")], group_id)
            self.assertEqual([], qualify.expected_probe_cases(manifest, groups["core-" + group_id]))

    def test_expanded_host_probe_rejects_unexpected_geometry_case(self):
        manifest = json.loads(Path(__file__).with_name("foundation-probes.json").read_text())
        group = next(group for group in manifest["groups"] if group["id"] == "jvm")
        cases = qualify.expected_probe_cases(manifest, group)
        self.assertEqual(28, len(cases))
        suite = ET.Element("testsuite", tests="29", failures="0", errors="0", skipped="0")
        for classname, name in cases + [("io.github.rubixhacker.dyn4k.GeometryShapeTest", "unexpected[jvm]")]:
            ET.SubElement(suite, "testcase", classname=classname, name=name, time="0")
        xml = ET.tostring(suite, encoding="unicode")
        with tempfile.TemporaryDirectory() as root:
            previous = Path.cwd()
            os.chdir(root)
            try:
                report = Path("probe.xml")
                report_group = dict(group, report_pattern=str(report))
                command = ["python3", "-c", "from pathlib import Path; Path('probe.xml').write_text(" + repr(xml) + ")"]
                result = qualify.run_probe(command, [str(report)], "a" * 40,
                                           Path(root) / "result.json",
                                           manifest={**manifest, "groups": [report_group]})
                self.assertEqual("PROBE_FAILED", result["status"])
                self.assertEqual(28, result["expected"])
                self.assertEqual(29, result["executed"])
                self.assertIn("unexpected cases", result["reason"])
            finally:
                os.chdir(previous)

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
                {case["id"]: {"command": ["/bin/true"], "result_file": str(result_file)}},
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
                    ["python3", "-c", writer], ["one.xml", "missing.xml"],
                    "a" * 40, Path(root) / "probe.json", manifest=manifest)
                self.assertEqual("PROBE_FAILED", result["status"])
                self.assertIn("missing", result["reason"])
                duplicate = "from pathlib import Path; Path('one.xml').write_text('<testsuite tests=\"2\" skipped=\"0\" failures=\"0\" errors=\"0\"><testcase classname=\"C\" name=\"one\" time=\"0\"/><testcase classname=\"C\" name=\"one\" time=\"0\"/></testsuite>')"
                result = qualify.run_probe(
                    ["python3", "-c", duplicate], ["one.xml"],
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
                ["python3", str(Path(__file__).with_name("qualify.py")), "audit-staging",
                 "--candidate-sha", sha, "--repository", str(repository / "empty-staging"),
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
            self.assertEqual(46, len(audit["errors"]))

    def test_report_refuses_sha_other_than_checkout(self):
        with tempfile.TemporaryDirectory() as root:
            result = subprocess.run(
                ["python3", str(Path(__file__).with_name("qualify.py")), "record",
                 "--candidate-sha", "f" * 40, "--output", str(Path(root) / "report.json")],
                text=True, capture_output=True, check=False)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("checkout", result.stderr)


if __name__ == "__main__":
    unittest.main()
