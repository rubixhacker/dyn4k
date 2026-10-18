import re
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/windows-collision-focus.yml"


class WindowsCollisionFocusWorkflowContractTest(unittest.TestCase):
    def test_manual_windows_job_checks_out_exact_sha_and_runs_only_focused_classes(self):
        workflow = WORKFLOW.read_text()
        self.assertIn("on:\n  workflow_dispatch:\n", workflow)
        self.assertLess(workflow.index("on:\n"), workflow.index("permissions:"))
        self.assertIn("runs-on: windows-2025", workflow)
        self.assertIn("ref: ${{ github.sha }}", workflow)
        self.assertIn("actions/setup-java@v4", workflow)
        self.assertIn("java-version: '21'", workflow)
        self.assertIn("gradle/actions/setup-gradle@v4", workflow)
        self.assertIn(":dyn4k-core:mingwX64Test", workflow)

        expected = {
            "org.dyn4j.collision.narrowphase.WindowsCollisionIntermediateDiagnosticTest",
            "org.dyn4j.coverage.collision.shapes.a.CapsuleSliceTest",
            "org.dyn4j.coverage.collision.shapes.a.CirclePolygonTest",
            "org.dyn4j.coverage.collision.shapes.a.CircleSegmentTest",
            "org.dyn4j.coverage.collision.shapes.a.CircleSliceTest",
            "org.dyn4j.coverage.collision.shapes.a.PolygonCapsuleTest",
            "org.dyn4j.coverage.collision.shapes.a.PolygonPolygonTest",
        }
        selected = set(re.findall(r"--tests '([^']+)'", workflow))
        self.assertEqual(expected, selected)
        self.assertIn("--no-daemon --rerun-tasks --console=plain", workflow)
        self.assertIn("run-java-control.ps1", workflow)
        self.assertIn("204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e", workflow)
        self.assertIn("058bf6d982a0fb89b54050f929f6ea9dae53b714", workflow)

    def test_workflow_retains_raw_evidence_and_uploads_after_failures(self):
        workflow = WORKFLOW.read_text()
        for evidence in (
                "gradle-console.log", "gradle-exit-code.txt", "java-console.log",
                "java-exit-code.txt", "baseline-source-revision.txt",
                "runner-runtime-identity.txt", "sha256-inventory.txt"):
            with self.subTest(evidence=evidence):
                self.assertIn(evidence, workflow)
        self.assertIn("if: always()", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("if-no-files-found: error", workflow)
        self.assertIn("throw \"Focused controls failed: native=$nativeExit java=$javaExit\"", workflow)
        self.assertNotIn("full_corpus", workflow)
        self.assertNotIn("staging-repository", workflow)


if __name__ == "__main__":
    unittest.main()
