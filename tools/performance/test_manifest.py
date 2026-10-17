import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("manifest.py")
CCD_FIXTURE = SCRIPT.parents[2] / "docs/research/performance-ccd-fixture-v2.json"


class ManifestContractTest(unittest.TestCase):
    def test_ccd_fixture_revision_links_to_unchanged_manifest(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "validate-ccd-fixture", str(CCD_FIXTURE)],
            capture_output=True, text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        fixture = json.loads(CCD_FIXTURE.read_text())
        self.assertEqual("performance-ccd-v2", fixture["version"])
        self.assertEqual(27, len(fixture["workload_ids"]))
        self.assertEqual("zero_based_creation_index", fixture["body_hash"]["algorithm"])

    def test_ccd_fixture_revision_rejects_changed_rule_or_base_hash(self):
        for change in ("body_hash", "base_manifest_sha256"):
            with self.subTest(change=change):
                fixture = json.loads(CCD_FIXTURE.read_text())
                if change == "body_hash":
                    fixture["body_hash"]["algorithm"] = "object_identity"
                else:
                    fixture[change] = "0" * 64
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "validate-ccd-fixture", "-"],
                    input=json.dumps(fixture), capture_output=True, text=True,
                )
                self.assertNotEqual(0, result.returncode)

    def test_public_manifest_command_covers_approved_matrix(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "emit"],
            capture_output=True,
            text=True,
            check=True,
        )
        manifest = json.loads(result.stdout)
        self.assertEqual(1, manifest["version"])
        self.assertEqual(21, len(manifest["targets"]))
        self.assertEqual(28, len(manifest["runtime_rows"]))
        self.assertEqual(5, len(manifest["families"]))
        self.assertEqual([30, 60, 120], manifest["rates_hz"])
        self.assertEqual(
            {"baseline", "direct_kotlin", "compatibility"},
            set(manifest["api_surfaces"]),
        )
        self.assertTrue(all(row["environment_status"] == "unavailable" for row in manifest["runtime_rows"]))
        self.assertTrue(all(row["representative_hardware"] is None for row in manifest["runtime_rows"]))

    def test_validate_rejects_missing_runtime_row(self):
        manifest = json.loads(subprocess.check_output([sys.executable, str(SCRIPT), "emit"]))
        manifest["runtime_rows"].pop()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "validate", "-"],
            input=json.dumps(manifest),
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, result.returncode)

    def test_validate_rejects_changed_minimum_or_build(self):
        manifest = json.loads(subprocess.check_output([sys.executable, str(SCRIPT), "emit"]))
        manifest["runtime_rows"][0]["minimum_policy"] = "Java 11"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "validate", "-"],
            input=json.dumps(manifest), capture_output=True, text=True,
        )
        self.assertNotEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
