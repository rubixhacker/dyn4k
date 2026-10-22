import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest


SOURCE = Path(__file__).resolve().parent
JDK21 = Path(os.environ.get("DYN4K_JDI_JDK_HOME", "/tmp/dyn4k-tools/jdk21"))


class JdiWaitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.java = JDK21 / "bin/java"
        cls.javac = JDK21 / "bin/javac"
        if not cls.java.is_file() or not cls.javac.is_file():
            raise unittest.SkipTest("JDK 21 Java and javac are unavailable")
        environment = os.environ.copy()
        environment.pop("OLLAMA_API_KEY", None)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        version = subprocess.run((str(cls.java), "-version"), capture_output=True,
                                 text=True, timeout=10, env=environment)
        if version.returncode or 'version "21.' not in version.stderr:
            raise unittest.SkipTest("JDK 21 Java is unavailable")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path.home())
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environment = os.environ.copy()
        self.environment.pop("OLLAMA_API_KEY", None)
        self.environment["PYTHONDONTWRITEBYTECODE"] = "1"
        self.environment["JAVA_HOME"] = str(JDK21)
        self.environment["TMPDIR"] = str(self.root)
        compiled = subprocess.run((str(self.javac), "--add-modules", "jdk.jdi",
                                   "-d", str(self.root),
                                   str(SOURCE / "RotationJdiProbe.java"),
                                   str(SOURCE / "JdiWaitControl.java")),
                                  env=self.environment, capture_output=True, timeout=30)
        self.assertEqual(compiled.returncode, 0, compiled.stderr.decode())

    def run_control(self, mode, deadline, traced=False):
        output = self.root / mode
        command = [str(self.java), "--add-modules", "jdk.jdi",
                   "-Djava.io.tmpdir=" + str(self.root), "-cp", str(self.root),
                   "RotationJdiProbe", "launch", str(output), str(self.root),
                   "JdiWaitControl " + mode, "JdiWaitControl$Rotation", "540",
                   str(deadline)]
        if traced:
            strace = shutil.which("strace")
            if strace is None:
                self.skipTest("strace is unavailable for the thread trace control")
            command = [strace, "-ff", "-e", "trace=clone,clone3,execve",
                       "-o", str(self.root / "trace"), *command]
        started = time.monotonic()
        result = subprocess.run(command, env=self.environment, capture_output=True,
                                timeout=90)
        return output, result, time.monotonic() - started

    def test_traced_public_cli_completes_with_bounded_thread_members(self):
        output, result, elapsed = self.run_control("normal", 60, traced=True)
        members = list(self.root.glob("trace.*"))
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertLessEqual(len(members), 128, f"{len(members)} trace members in {elapsed:.1f}s")
        self.assertEqual(len((output / "events.tsv").read_text().splitlines()), 540)
        self.assertEqual((output / "complete.txt").read_text().splitlines()[0], "vm-death")
        print(f"traced control: {len(members)} members, 540 calls, {elapsed:.2f} s")

    def test_public_cli_deadline_stops_idle_target(self):
        output, result, elapsed = self.run_control("idle", 1)
        self.assertNotEqual(result.returncode, 0)
        self.assertLess(elapsed, 6)
        self.assertIn(b"Incomplete target observation", result.stderr)
        self.assertFalse((output / "complete.txt").exists())
        print(f"idle deadline control: rejected in {elapsed:.2f} s")

    def test_public_cli_rejects_disconnect_without_vm_death(self):
        output, result, elapsed = self.run_control("disconnect", 5)
        self.assertNotEqual(result.returncode, 0)
        self.assertLess(elapsed, 4)
        self.assertIn(b"Incomplete target observation", result.stderr)
        self.assertFalse((output / "complete.txt").exists())
        print(f"disconnect control: rejected in {elapsed:.2f} s")


if __name__ == "__main__":
    unittest.main()
