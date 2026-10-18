import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/windows-collision-focus.yml"
HELPER = ROOT / "tools/compatibility/windows_collision_focus.py"
sys.path.insert(0, str(ROOT))
from tools.compatibility import windows_collision_focus as focus


def record(fixture, step, provider):
    fields = (
        "DYN4K_COLLISION_DIAGNOSTIC", "v2", f"provider={provider}",
        f"fixture={fixture}", f"method=method{step % 3}",
        f"phase=phase{step % 2}", f"order=order{step % 2}",
        f"step={step}", f"algorithm=algorithm{step % 2}",
        f"payload.raw={fixture}:{step}:0x1.fffffffffffffp-1",
    )
    return "\t".join(fields)


HISTORICAL_FAILURES = {
    ("CapsuleSliceTest", "detectGjk"),
    ("CapsuleSliceTest", "getClipManifold"),
    ("CirclePolygonTest", "detectGjk"),
    ("CircleSegmentTest", "detectGjk"),
    ("CircleSliceTest", "detectGjk"),
    ("PolygonCapsuleTest", "detectSat"),
    ("PolygonCapsuleTest", "getClipManifold"),
    ("PolygonPolygonTest", "detectSat"),
    ("PolygonPolygonTest", "getClipManifold"),
}


def write_reports(directory, omit=None, original_case_mutation=None):
    native_rows = []
    for fixture_name in (
            "CapsuleSlice", "CirclePolygon", "CircleSegment", "CircleSlice",
            "PolygonCapsule", "PolygonPolygon"):
        for step in range(12):
            native_rows.append(record(fixture_name, step, "dyn4k"))
    for suite, filename in focus.SUITES.items():
        if filename == omit:
            continue
        attributes = {"name": f"{focus.TARGET}.{suite}"}
        root = ET.Element("testsuite", attributes)
        if suite.endswith("WindowsCollisionIntermediateDiagnosticTest"):
            for case in sorted(focus.DIAGNOSTIC_CASES):
                ET.SubElement(root, "testcase", {"name": case})
            output = ET.SubElement(root, "system-out")
            output.text = "\n".join(native_rows)
        else:
            class_name = suite.rsplit(".", 1)[-1]
            case_ids = sorted(focus.ORIGINAL_CASES[suite])
            mutation = original_case_mutation or {}
            if mutation.get("kind") == "empty" and mutation.get("suite") == suite:
                case_ids = []
            elif mutation.get("kind") == "missing" and mutation.get("suite") == suite:
                case_ids.remove(mutation["case"])
            for case_id in case_ids:
                case = ET.SubElement(root, "testcase", {"name": case_id})
                if (mutation.get("kind") == "skipped" and mutation.get("suite") == suite
                        and mutation.get("case") == case_id):
                    ET.SubElement(case, "skipped")
                if (class_name, case_id.split("[", 1)[0]) in HISTORICAL_FAILURES:
                    ET.SubElement(case, "failure", {"message": "preserved assertion failure"})
        ET.ElementTree(root).write(directory / filename, encoding="utf-8", xml_declaration=True)
    java_rows = [row.replace("provider=dyn4k", "provider=dyn4j-6.0.0", 1)
                 for row in native_rows]
    return native_rows, java_rows


def require_workflow_contract(workflow, helper):
    trigger_section = workflow.split("on:\n", 1)[1].split("\npermissions:", 1)[0]
    triggers = [line.strip()[:-1] for line in trigger_section.splitlines()
                if line.startswith("  ") and line.endswith(":")]
    if triggers != ["workflow_dispatch"]:
        raise AssertionError(f"Expected workflow_dispatch only, found {triggers}")
    if "tools/compatibility/windows_collision_focus.py" not in workflow:
        raise AssertionError("The workflow must invoke the shared report validator")
    if "if actual_names != expected_names:" not in helper:
        raise AssertionError("The shared validator must reject an incomplete report set")
    if "len(records) != 72" not in helper:
        raise AssertionError("The shared validator must require 72 rows")
    if "native_identities != java_identities" not in helper:
        raise AssertionError("The shared validator must compare trace identities")
    if "ORIGINAL_CASES" not in helper or "contains skipped cases" not in helper:
        raise AssertionError("The shared validator must check original cases and reject skips")
    if "--collection-status" not in workflow or "--validation-status" not in workflow:
        raise AssertionError("The workflow must record post-Gradle status separately")


class WindowsCollisionFocusWorkflowContractTest(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text()
        self.helper = HELPER.read_text()

    def test_workflow_is_manual_scoped_and_uses_exact_windows_target(self):
        require_workflow_contract(self.workflow, self.helper)
        self.assertIn("runs-on: windows-2025", self.workflow)
        self.assertIn("ref: ${{ github.sha }}", self.workflow)
        self.assertIn("actions/setup-java@v4", self.workflow)
        self.assertIn("java-version: '21'", self.workflow)
        self.assertIn("gradle/actions/setup-gradle@v4", self.workflow)
        self.assertIn(":dyn4k-core:mingwX64Test", self.workflow)
        selected = set(re.findall(r"--tests '([^']+)'", self.workflow))
        expected_classes = set(focus.SUITES)
        self.assertEqual(expected_classes, selected)
        self.assertIn("--no-daemon --rerun-tasks --console=plain", self.workflow)
        self.assertIn("run-java-control.ps1", self.workflow)
        self.assertIn("204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e", self.workflow)
        self.assertIn("058bf6d982a0fb89b54050f929f6ea9dae53b714", self.workflow)

    def test_frozen_original_case_ids_match_all_six_kotlin_test_sources(self):
        for suite, case_ids in focus.ORIGINAL_CASES.items():
            source = ROOT / "dyn4k-core/src/commonTest/kotlin" / Path(*suite.split("."))
            source = source.with_suffix(".kt")
            source_methods = set(re.findall(r"@Test\s+fun\s+(\w+)\s*\(", source.read_text()))
            expected_methods = {case_id.split("[", 1)[0] for case_id in case_ids}
            with self.subTest(suite=suite):
                self.assertEqual(expected_methods, source_methods)

    def test_adversarial_trigger_and_missing_validation_mutations_fail(self):
        with self.assertRaises(AssertionError):
            require_workflow_contract(
                self.workflow.replace("  workflow_dispatch:\n", "  workflow_dispatch:\n  push:\n", 1),
                self.helper,
            )
        with self.assertRaises(AssertionError):
            require_workflow_contract(self.workflow, self.helper.replace(
                "if actual_names != expected_names:", "if actual_names == expected_names:", 1))
        with self.assertRaises(AssertionError):
            require_workflow_contract(self.workflow, self.helper.replace(
                "len(records) != 72", "len(records) != 71", 1))

    def test_empty_skipped_and_missing_original_cases_fail_the_shared_helper(self):
        suite = "org.dyn4j.coverage.collision.shapes.a.CapsuleSliceTest"
        case_id = "detectGjk[mingwX64]"
        scenarios = (
            ("empty", {"kind": "empty", "suite": suite}, "case set mismatch"),
            ("skipped", {"kind": "skipped", "suite": suite, "case": case_id},
             "contains skipped cases"),
            ("missing", {"kind": "missing", "suite": suite, "case": case_id},
             "case set mismatch"),
        )
        for name, mutation, expected_error in scenarios:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                _, java_rows = write_reports(directory, original_case_mutation=mutation)
                java_tsv = directory / "java.tsv"
                java_tsv.write_text("\n".join(java_rows) + "\n", encoding="utf-8")
                result = subprocess.run(
                    [sys.executable, str(HELPER), "validate", "--native-directory", str(directory),
                     "--java-tsv", str(java_tsv), "--native-tsv", str(directory / "native.tsv")],
                    check=False, capture_output=True, text=True,
                )
                self.assertNotEqual(0, result.returncode)
                self.assertIn(expected_error, result.stderr)
                self.assertFalse((directory / "native.tsv").exists())

    def test_shared_workflow_extractor_produces_all_rows_and_exact_identity_parity(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            native_rows, java_rows = write_reports(directory)
            java_tsv = directory / "java.tsv"
            java_tsv.write_text("\n".join(java_rows) + "\n", encoding="utf-8")
            native_tsv = directory / "native.tsv"
            result = subprocess.run(
                [sys.executable, str(HELPER), "validate", "--native-directory", str(directory),
                 "--java-tsv", str(java_tsv), "--native-tsv", str(native_tsv)],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("suites=7 diagnosticCases=6 nativeRows=72 javaRows=72 identityParity=exact",
                          result.stdout)
            self.assertEqual(native_rows, native_tsv.read_text(encoding="utf-8").splitlines())
            failure_count = sum(
                1 for report in directory.glob("TEST-*.xml")
                for case in ET.parse(report).getroot().findall("testcase")
                if case.find("failure") is not None
            )
            self.assertEqual(9, failure_count, "keep the preserved original assertion failures visible")

    def test_actual_workflow_validator_exits_nonzero_when_a_report_is_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            _, java_rows = write_reports(
                directory,
                omit="TEST-mingwX64Test.org.dyn4j.collision.narrowphase.WindowsCollisionIntermediateDiagnosticTest.xml",
            )
            java_tsv = directory / "java.tsv"
            java_tsv.write_text("\n".join(java_rows) + "\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(HELPER), "validate", "--native-directory", str(directory),
                 "--java-tsv", str(java_tsv), "--native-tsv", str(directory / "native.tsv")],
                check=False, capture_output=True, text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("Native XML report set mismatch", result.stderr)
            self.assertFalse((directory / "native.tsv").exists())

    def test_evidence_collection_keeps_failure_and_always_upload_controls(self):
        for evidence in (
                "gradle-console.log", "gradle-exit-code.txt", "java-console.log",
                "java-exit-code.txt", "baseline-source-revision.txt",
                "runner-runtime-identity.txt", "sha256-inventory.txt",
                "collection-status.txt", "validation-status.txt"):
            with self.subTest(evidence=evidence):
                self.assertIn(evidence, self.workflow)
        self.assertIn("if: always()", self.workflow)
        self.assertIn("actions/upload-artifact@v4", self.workflow)
        self.assertIn("if-no-files-found: error", self.workflow)
        self.assertIn("windows_collision_focus.py status", self.workflow)
        self.assertLess(self.workflow.index("run-java-control.ps1"),
                        self.workflow.index("windows_collision_focus.py"))
        self.assertNotIn("full_corpus", self.workflow)
        self.assertNotIn("staging-repository", self.workflow)

    def test_native_report_errors_do_not_short_circuit_later_evidence_collection(self):
        copy_catch = self.workflow.index('"Native XML copy failed for')
        java_control = self.workflow.index("run-java-control.ps1")
        runner_identity = self.workflow.index("runner-runtime-identity.txt")
        inventory = self.workflow.index("sha256-inventory.txt")
        status_decision = self.workflow.index("windows_collision_focus.py status")
        upload = self.workflow.index("Upload Windows collision evidence")
        self.assertLess(copy_catch, java_control)
        self.assertLess(java_control, runner_identity)
        self.assertLess(runner_identity, inventory)
        self.assertLess(inventory, status_decision)
        self.assertLess(status_decision, upload)
        self.assertIn("$collectionStatus = 1", self.workflow[copy_catch:java_control])
        self.assertIn("if: always()", self.workflow[upload:])

    def test_gradle_exit_is_written_once_and_collection_error_fails_final_status(self):
        capture = self.workflow.index("$gradleExit = [string]$LASTEXITCODE")
        raw_write_line = "Set-Content -Path $gradleExitFile -Value $gradleExit"
        raw_write = self.workflow.index(raw_write_line)
        self.assertLess(capture, raw_write)
        self.assertEqual(1, self.workflow.count(raw_write_line))
        self.assertIn("gradle-exit-code.txt", self.workflow)
        self.assertNotIn("$gradleExit =", self.workflow[raw_write:])
        self.assertIn("--gradle-exit-code $gradleExit", self.workflow)

        collector_failure = subprocess.run(
            [sys.executable, str(HELPER), "status", "--gradle-exit-code", "0",
             "--java-exit-code", "0", "--collection-status", "1",
             "--validation-status", "0"],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(1, collector_failure.returncode)
        self.assertIn("gradle=0 java=0 collection=1 validation=0", collector_failure.stdout)

        assertion_failure = subprocess.run(
            [sys.executable, str(HELPER), "status", "--gradle-exit-code", "1",
             "--java-exit-code", "0", "--collection-status", "0",
             "--validation-status", "0"],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(1, assertion_failure.returncode)
        self.assertIn("gradle=1", assertion_failure.stdout)


if __name__ == "__main__":
    unittest.main()
