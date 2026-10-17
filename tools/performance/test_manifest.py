import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("manifest.py")


class ManifestContractTest(unittest.TestCase):
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
