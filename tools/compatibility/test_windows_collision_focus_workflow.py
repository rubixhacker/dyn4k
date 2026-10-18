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


def write_reports(directory, omit=None):
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

    def test_shared_workflow_extractor_produces_all_rows_and_exact_identity_parity(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            native_rows, java_rows = write_reports(directory)
            java_tsv = directory / "java.tsv"
            java_tsv.write_text("\n".join(java_rows) + "\n", encoding="utf-8")
            native_tsv = directory / "native.tsv"
            result = subprocess.run(
                [sys.executable, str(HELPER), "--native-directory", str(directory),
                 "--java-tsv", str(java_tsv), "--native-tsv", str(native_tsv)],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("suites=7 diagnosticCases=6 nativeRows=72 javaRows=72 identityParity=exact",
                          result.stdout)
            self.assertEqual(native_rows, native_tsv.read_text(encoding="utf-8").splitlines())

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
                [sys.executable, str(HELPER), "--native-directory", str(directory),
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
                "runner-runtime-identity.txt", "sha256-inventory.txt"):
            with self.subTest(evidence=evidence):
                self.assertIn(evidence, self.workflow)
        self.assertIn("if: always()", self.workflow)
        self.assertIn("actions/upload-artifact@v4", self.workflow)
        self.assertIn("if-no-files-found: error", self.workflow)
        self.assertIn("throw \"Focused controls failed: native=$nativeExit java=$javaExit\"", self.workflow)
        self.assertLess(self.workflow.index("run-java-control.ps1"),
                        self.workflow.index("windows_collision_focus.py"))
        self.assertNotIn("full_corpus", self.workflow)
        self.assertNotIn("staging-repository", self.workflow)


if __name__ == "__main__":
    unittest.main()
