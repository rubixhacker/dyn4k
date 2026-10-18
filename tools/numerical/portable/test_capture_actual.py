import os
import subprocess
import tempfile
import unittest
from pathlib import Path
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
