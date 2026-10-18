import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import capture_actual
from actual_arithmetic import CaptureRejected


class CaptureSourceGuardTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR", str(Path.home())))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        subprocess.run(("git", "init", "-q"), cwd=self.root, check=True)
        (self.root / ".gitignore").write_text(
            "**/build/\n.gradle/\n.kotlin/\n__pycache__/\n"
            "kotlin-js-store/\n*.ignored.kt\n")
        source = self.root / "tools/numerical/portable/src/commonTest/kotlin/portable"
        source.mkdir(parents=True)
        (source / "Tracked.kt").write_text("package portable\n")
        subprocess.run(("git", "add", "."), cwd=self.root, check=True)
        subprocess.run(("git", "-c", "user.name=Capture Test", "-c",
                        "user.email=capture-test@example.invalid", "commit", "-qm",
                        "fixture"), cwd=self.root, check=True)
        root = patch.object(capture_actual, "ROOT", self.root)
        root.start()
        self.addCleanup(root.stop)

    def test_capture_writes_canonical_source_before_failed_stage(self):
        subprocess.run(("git", "-C", str(self.root), "config", "core.autocrlf", "true"),
                       check=True)
        converted = capture_actual.git("archive", "--format=tar", "HEAD")
        canonical = capture_actual.git("-c", "core.autocrlf=false", "archive",
                                       "--format=tar", "HEAD")
        self.assertNotEqual(converted, canonical)
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR", str(Path.home())))
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "capture"
        jdk = Path(temporary.name) / "jdk"
        (jdk / "bin").mkdir(parents=True)
        (jdk / "bin/java").write_bytes(b"test executable")
        real_run = subprocess.run

        def stop_before_execution(command, *args, **kwargs):
            if command[0] == "git":
                return real_run(command, *args, **kwargs)
            return SimpleNamespace(returncode=1)

        with patch.object(capture_actual, "JDK21", jdk), \
                patch.object(capture_actual, "expected_case_ids", return_value={"method": []}), \
                patch.object(capture_actual.subprocess, "run", side_effect=stop_before_execution):
            with self.assertRaisesRegex(CaptureRejected, "publication failed"):
                capture_actual.run_capture("method", output)
        self.assertEqual((output / "source.tar").read_bytes(), canonical)
        self.assertFalse((output / "receipt.json").exists())

    def test_capture_source_tar_ignores_same_type_commit_replacement(self):
        original = capture_actual.git("rev-parse", "HEAD").decode().strip()
        source = self.root / "tools/numerical/portable/src/commonTest/kotlin/portable/Tracked.kt"
        source.write_text("package portable\nclass Substitute\n")
        subprocess.run(("git", "add", "."), cwd=self.root, check=True)
        subprocess.run(("git", "-c", "user.name=Capture Test", "-c",
                        "user.email=capture-test@example.invalid", "commit", "-qm",
                        "substitute"), cwd=self.root, check=True)
        substitute = capture_actual.git("rev-parse", "HEAD").decode().strip()
        subprocess.run(("git", "checkout", "-q", original), cwd=self.root, check=True)
        subprocess.run(("git", "replace", original, substitute), cwd=self.root, check=True)
        canonical = capture_actual.git("--no-replace-objects", "-c",
                                       "core.autocrlf=false", "archive", "--format=tar",
                                       original)
        substituted = capture_actual.git("-c", "core.autocrlf=false", "archive",
                                         "--format=tar", original)
        self.assertNotEqual(canonical, substituted)
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR", str(Path.home())))
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "capture"
        jdk = Path(temporary.name) / "jdk"
        (jdk / "bin").mkdir(parents=True)
        (jdk / "bin/java").write_bytes(b"test executable")
        real_run = subprocess.run

        def stop_before_execution(command, *args, **kwargs):
            if command[0] == "git":
                return real_run(command, *args, **kwargs)
            return SimpleNamespace(returncode=1)

        with patch.object(capture_actual, "JDK21", jdk), \
                patch.object(capture_actual, "expected_case_ids", return_value={"method": []}), \
                patch.object(capture_actual.subprocess, "run", side_effect=stop_before_execution):
            with self.assertRaisesRegex(CaptureRejected, "publication failed"):
                capture_actual.run_capture("method", output)
        self.assertEqual((output / "source.tar").read_bytes(), canonical)
        self.assertFalse((output / "receipt.json").exists())
        source.write_text("package portable\nclass Substitute\n")
        subprocess.run(("git", "add", "."), cwd=self.root, check=True)
        self.assertEqual(capture_actual.git("status", "--porcelain"), b"")
        with self.assertRaisesRegex(CaptureRejected, "target source is not clean"):
            capture_actual.clean_source()

    def test_only_exact_generated_roots_are_exempt(self):
        for relative in ("build/cache/generated.bin", ".gradle/cache/state.bin",
                         "dyn4k-core/build/classes/Generated.class",
                         "tools/numerical/portable/build/classes/Generated.class",
                         "tools/numerical/portable/__pycache__/cases.pyc"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"generated")
        self.assertEqual(capture_actual.clean_source(),
                         capture_actual.git("rev-parse", "HEAD").decode().strip())

    def test_ignored_kotlin_under_source_build_is_rejected(self):
        self.assertEqual(capture_actual.clean_source(),
                         capture_actual.git("rev-parse", "HEAD").decode().strip())
        for relative in ("tools/numerical/portable/src/commonTest/kotlin/portable/"
                         "build/Injected.kt",
                         "tools/numerical/portable/src/commonMain/kotlin/"
                         "build/generated/Shadow.kt",
                         "tools/numerical/portable/src/commonTest/kotlin/portable/"
                         "Injected.ignored.kt"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("package portable\nclass Injected\n")
            self.assertEqual(capture_actual.git("status", "--porcelain",
                                                "--untracked-files=all"), b"")
            with self.subTest(relative=relative), self.assertRaises(CaptureRejected):
                capture_actual.clean_source()
            path.unlink()
            self.assertEqual(capture_actual.clean_source(),
                             capture_actual.git("rev-parse", "HEAD").decode().strip())


if __name__ == "__main__":
    unittest.main()
