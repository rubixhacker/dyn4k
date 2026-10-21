import os
import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from loaded_code import verify_jar_code, verify_probe_code
from witness import read_probe_events


class LoadedCodeTest(unittest.TestCase):
    def setUp(self):
        root = os.environ.get("BOOLEAN_JDI_TOY_ROOT")
        if not root:
            self.skipTest("No retained JDK21 toy output supplied")
        self.root = Path(root)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name) / "probe"
        shutil.copytree(self.root / "toy-1", self.output)
        self.class_bytes = (self.root / "classes/ToyRotation.class").read_bytes()

    def status(self, class_bytes=None):
        return verify_probe_code(self.output, class_bytes or self.class_bytes,
                                 "ToyRotation")["status"]

    def test_real_toy_loaded_code_matches(self):
        self.assertEqual(self.status(), "MATCHED_JDI_LOADED_CODE")

    def test_alternate_provider_constant_pool_rejects(self):
        self.assertIn(b"ToyRotation", self.class_bytes)
        changed = self.class_bytes.replace(b"ToyRotation", b"BoyRotation")
        self.assertEqual(self.status(changed), "FAILED_LOADED_CODE_BYTES")

    def test_changed_and_missing_method_bytes_reject(self):
        method = self.output / "method-0.bin"
        method.write_bytes(method.read_bytes() + b"\x00")
        self.assertEqual(self.status(), "FAILED_LOADED_CODE_BYTES")
        method.unlink()
        self.assertEqual(self.status(), "FAILED_LOADED_CODE_INVENTORY")

    def test_duplicate_method_row_and_extra_file_reject(self):
        manifest = self.output / "methods.tsv"
        lines = manifest.read_text().splitlines()
        manifest.write_text("\n".join(lines + lines[:1]) + "\n")
        self.assertEqual(self.status(), "FAILED_LOADED_CODE_INVENTORY")
        manifest.write_text("\n".join(lines) + "\n")
        alias = lines[1].split("\t")
        alias[2] = lines[0].split("\t")[2]
        manifest.write_text("\n".join([lines[0], "\t".join(alias), *lines[2:]]) + "\n")
        self.assertEqual(self.status(), "FAILED_LOADED_CODE_INVENTORY")
        manifest.write_text("\n".join(lines) + "\n")
        (self.output / "method-999.bin").write_bytes(b"")
        self.assertEqual(self.status(), "FAILED_LOADED_CODE_INVENTORY")

    def test_changed_loader_identity_rejects(self):
        identity = self.output / "class.txt"
        lines = identity.read_text().splitlines()
        identity.write_text("\n".join(lines[:2] + ["0"]) + "\n")
        self.assertEqual(self.status(), "FAILED_LOADED_CODE_IDENTITY")

    def test_jar_hash_and_loaded_provider(self):
        jar = Path(self.temporary.name) / "toy.jar"
        with zipfile.ZipFile(jar, "w") as archive:
            archive.writestr("ToyRotation.class", self.class_bytes)
        digest = hashlib.sha256(jar.read_bytes()).hexdigest()
        self.assertEqual(verify_jar_code(self.output, jar, digest, "ToyRotation")["status"],
                         "MATCHED_JDI_LOADED_CODE")
        self.assertEqual(verify_jar_code(self.output, jar, "0" * 64, "ToyRotation")["status"],
                         "FAILED_JAR_IDENTITY")
        with zipfile.ZipFile(jar, "w") as archive:
            archive.writestr("ToyRotation.class",
                             self.class_bytes.replace(b"ToyRotation", b"BoyRotation"))
        digest = hashlib.sha256(jar.read_bytes()).hexdigest()
        self.assertEqual(verify_jar_code(self.output, jar, digest, "ToyRotation")["status"],
                         "FAILED_LOADED_CODE_BYTES")

    def test_toy_entry_exit_fields_and_signed_zero(self):
        calls = read_probe_events(self.output, 3)
        self.assertEqual([row["caller"] for row in calls],
                         ["ToyRotation.integrate", "ToyRotation.solvePositionConstraints",
                          "ToyRotation.solvePositionConstraints"])
        self.assertEqual([row["angle_bits"] for row in calls],
                         ["0000000000000000", "8000000000000000", "0000000000000000"])

    def test_missing_changed_and_reordered_events_reject(self):
        events = self.output / "events.tsv"
        rows = events.read_text().splitlines()
        for changed in (rows[:2], rows + rows[-1:], [rows[1], rows[0], rows[2]],
                        [rows[0].replace("0000000000000000", "invalid", 1), *rows[1:]]):
            events.write_text("\n".join(changed) + "\n")
            with self.assertRaises(ValueError):
                read_probe_events(self.output, 3)
        events.write_text("\n".join(rows) + "\n")
        (self.output / "complete.txt").unlink()
        with self.assertRaises(OSError):
            read_probe_events(self.output, 3)


if __name__ == "__main__":
    unittest.main()
