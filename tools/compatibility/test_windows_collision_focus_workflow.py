import re
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/windows-collision-focus.yml"
EXPECTED_REPORTS = {
    "TEST-org.dyn4j.coverage.collision.shapes.a.CapsuleSliceTest.xml",
    "TEST-org.dyn4j.coverage.collision.shapes.a.CirclePolygonTest.xml",
    "TEST-org.dyn4j.coverage.collision.shapes.a.CircleSegmentTest.xml",
    "TEST-org.dyn4j.coverage.collision.shapes.a.CircleSliceTest.xml",
    "TEST-org.dyn4j.coverage.collision.shapes.a.PolygonCapsuleTest.xml",
    "TEST-org.dyn4j.coverage.collision.shapes.a.PolygonPolygonTest.xml",
    "TEST-org.dyn4j.collision.narrowphase.WindowsCollisionIntermediateDiagnosticTest.xml",
}
EXPECTED_CLASSES = {
    "org.dyn4j.collision.narrowphase.WindowsCollisionIntermediateDiagnosticTest",
    "org.dyn4j.coverage.collision.shapes.a.CapsuleSliceTest",
    "org.dyn4j.coverage.collision.shapes.a.CirclePolygonTest",
    "org.dyn4j.coverage.collision.shapes.a.CircleSegmentTest",
    "org.dyn4j.coverage.collision.shapes.a.CircleSliceTest",
    "org.dyn4j.coverage.collision.shapes.a.PolygonCapsuleTest",
    "org.dyn4j.coverage.collision.shapes.a.PolygonPolygonTest",
}


def require_workflow_contract(workflow):
    trigger_section = workflow.split("on:\n", 1)[1].split("\npermissions:", 1)[0]
    triggers = re.findall(r"(?m)^  ([a-z_]+):\s*$", trigger_section)
    if triggers != ["workflow_dispatch"]:
        raise AssertionError(f"Expected workflow_dispatch only, found {triggers}")
    for report in EXPECTED_REPORTS:
        if report not in workflow:
            raise AssertionError(f"Missing required report identity: {report}")
        suite_class = report.removeprefix("TEST-").removesuffix(".xml")
        if f"= '{suite_class}'" not in workflow:
            raise AssertionError(f"Missing exact XML suite identity: {suite_class}")
    required_controls = (
        "if ($xmlFiles.Count -ne 7)",
        "Expected exactly one same-run suite report",
        "Expected 72 same-run native v2 records",
        "Diagnostic suite must contain the six focused test cases",
        "Native and Java v2 identity sets do not match exactly",
        "mingwX64-collision-diagnostics.tsv",
        "$nativeExit = 1",
        'throw "Focused controls failed: native=$nativeExit java=$javaExit"',
    )
    for control in required_controls:
        if control not in workflow:
            raise AssertionError(f"Missing workflow validation: {control}")


def require_artifacts(expected, produced):
    missing = set(expected) - set(produced)
    if missing:
        raise AssertionError(f"Required artifacts are missing: {sorted(missing)}")


class WindowsCollisionFocusWorkflowContractTest(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text()

    def test_manual_job_checks_out_exact_sha_and_runs_only_focused_classes(self):
        require_workflow_contract(self.workflow)
        self.assertIn("runs-on: windows-2025", self.workflow)
        self.assertIn("ref: ${{ github.sha }}", self.workflow)
        self.assertIn("actions/setup-java@v4", self.workflow)
        self.assertIn("java-version: '21'", self.workflow)
        self.assertIn("gradle/actions/setup-gradle@v4", self.workflow)
        self.assertIn(":dyn4k-core:mingwX64Test", self.workflow)
        selected = set(re.findall(r"--tests '([^']+)'", self.workflow))
        self.assertEqual(EXPECTED_CLASSES, selected)
        self.assertIn("--no-daemon --rerun-tasks --console=plain", self.workflow)
        self.assertIn("run-java-control.ps1", self.workflow)
        self.assertIn("204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e", self.workflow)
        self.assertIn("058bf6d982a0fb89b54050f929f6ea9dae53b714", self.workflow)

    def test_trigger_and_suite_record_guards_reject_mutations(self):
        with self.subTest("added push trigger"):
            with self.assertRaises(AssertionError):
                require_workflow_contract(self.workflow.replace(
                    "  workflow_dispatch:\n", "  workflow_dispatch:\n  push:\n", 1))
        with self.subTest("missing suite identity"):
            with self.assertRaises(AssertionError):
                require_workflow_contract(self.workflow.replace(
                    "TEST-org.dyn4j.coverage.collision.shapes.a.CapsuleSliceTest.xml", "", 1))
        with self.subTest("missing trace count validation"):
            with self.assertRaises(AssertionError):
                require_workflow_contract(self.workflow.replace(
                    "Expected 72 same-run native v2 records", "Removed native row guard", 1))

    def test_synthetic_missing_report_is_a_failure_not_an_upload_success(self):
        produced = EXPECTED_REPORTS - {
            "TEST-org.dyn4j.collision.narrowphase.WindowsCollisionIntermediateDiagnosticTest.xml"
        }
        with self.assertRaisesRegex(AssertionError, "Required artifacts are missing"):
            require_artifacts(EXPECTED_REPORTS, produced)
        require_workflow_contract(self.workflow)
        self.assertIn("if: always()", self.workflow)
        self.assertIn("actions/upload-artifact@v4", self.workflow)
        self.assertIn("if-no-files-found: error", self.workflow)

    def test_provenance_and_paired_trace_checks_are_explicit(self):
        task = self.workflow.index(":dyn4k-core:mingwX64Test")
        cleanup = self.workflow.index("Remove-Item -LiteralPath $results -Recurse -Force")
        self.assertLess(cleanup, task)
        for evidence in (
                "gradle-console.log", "gradle-exit-code.txt", "java-console.log",
                "java-exit-code.txt", "baseline-source-revision.txt",
                "runner-runtime-identity.txt", "sha256-inventory.txt"):
            with self.subTest(evidence=evidence):
                self.assertIn(evidence, self.workflow)
        self.assertIn("mingwX64-collision-diagnostics.tsv", self.workflow)
        self.assertIn("nativeKeys.Count -ne 72", self.workflow)
        self.assertIn("javaKeys.Count -ne 72", self.workflow)
        self.assertIn("foreach ($file in $xmlFiles)", self.workflow)
        self.assertIn("Native XML copy failed", self.workflow)
        self.assertIn("Native XML read/validation failed", self.workflow)
        self.assertIn("Trace validation failed", self.workflow)
        self.assertNotIn("full_corpus", self.workflow)
        self.assertNotIn("staging-repository", self.workflow)


if __name__ == "__main__":
    unittest.main()
