from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from guard_hosted_runners import scan


VALID = (
    "name: Windows and Linux\n"
    "on: workflow_dispatch\n"
    "jobs:\n"
    "  linux:\n"
    "    runs-on: ubuntu-latest\n"
    "    steps:\n"
    "      - run: true\n"
    "  windows:\n"
    "    runs-on: windows-2025\n"
    "    steps:\n"
    "      - run: true\n"
)


class HostedRunnerGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workflows = self.root / ".github" / "workflows"
        self.workflows.mkdir(parents=True)

    def write(self, name: str, source: str) -> None:
        (self.workflows / name).write_text(source, encoding="utf-8")

    def test_valid_linux_and_windows_workflow(self) -> None:
        self.write("valid.yml", VALID)
        self.assertEqual((1, []), scan(self.root))

    def test_documented_ubuntu_arm_runner(self) -> None:
        self.write("arm.yml", VALID.replace("ubuntu-latest", "ubuntu-24.04-arm"))
        self.assertEqual((1, []), scan(self.root))

    def test_self_hosted_mac_mini_runner(self) -> None:
        self.write("macmini.yml", VALID.replace("windows-2025", "mac-mini"))
        self.assertEqual((1, []), scan(self.root))

    def test_self_hosted_mac_mini_label_is_not_a_hosted_macos_label(self) -> None:
        self.write("macmini.yml", VALID.replace("windows-2025", "mac-mini"))
        errors = scan(self.root)[1]
        self.assertFalse(any("macOS hosted label" in error for error in errors))

    def test_unknown_ubuntu_arm_runner_is_rejected(self) -> None:
        self.write("unknown.yml", VALID.replace("ubuntu-latest", "ubuntu-24.04-arm64"))
        self.assertTrue(any("explicit Linux/Windows" in error for error in scan(self.root)[1]))

    def test_new_workflow_is_scanned(self) -> None:
        self.write("valid.yml", VALID)
        self.write("new.yaml", VALID.replace("windows-2025", "macos-26"))
        count, errors = scan(self.root)
        self.assertEqual(2, count)
        self.assertTrue(any("new.yaml" in error and "macOS hosted label" in error for error in errors))

    def test_direct_macos_label(self) -> None:
        self.write("direct.yml", VALID.replace("windows-2025", "macos-26"))
        self.assertTrue(scan(self.root)[1])

    def test_matrix_row_with_macos_label(self) -> None:
        source = VALID.replace(
            "    runs-on: windows-2025",
            "    strategy:\n      matrix:\n        runner: [windows-2025, macos-26]\n    runs-on: ${{ matrix.runner }}",
        )
        self.write("matrix.yml", source)
        errors = scan(self.root)[1]
        self.assertTrue(any("macOS hosted label" in error for error in errors))
        self.assertTrue(any("runs-on" in error for error in errors))

    def test_from_json_branch_with_macos_label(self) -> None:
        source = VALID.replace(
            "    runs-on: windows-2025",
            "    runs-on: ${{ fromJSON(inputs.branch && '[\"windows-2025\"]' || '[\"macos-26\"]') }}",
        )
        self.write("branch.yml", source)
        self.assertTrue(any("macOS hosted label" in error for error in scan(self.root)[1]))

    def test_user_controlled_runner_expression(self) -> None:
        self.write("input.yml", VALID.replace("windows-2025", "${{ inputs.runner }}"))
        self.assertTrue(any("runs-on" in error for error in scan(self.root)[1]))

    def test_duplicate_jobs_key_fails_closed(self) -> None:
        self.write("duplicate.yml", VALID + "jobs : {hidden: {runs-on: ${{ inputs.runner }}}}\n")
        self.assertTrue(any("one block-style jobs section" in error for error in scan(self.root)[1]))

    def test_missing_runner_fails_closed(self) -> None:
        self.write("missing.yml", VALID.replace("    runs-on: windows-2025\n", ""))
        self.assertTrue(any("exactly one explicit runs-on" in error for error in scan(self.root)[1]))


if __name__ == "__main__":
    unittest.main()
