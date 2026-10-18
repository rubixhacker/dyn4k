import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("journeys.py")
SAMPLES = Path("/tmp/dyn4k-migration-preflight/samples")


class JourneyCommandTest(unittest.TestCase):
    def command(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            text=True, capture_output=True, check=False,
        )

    def run_with_sample_change_after_compilation(self, root, change_sample):
        samples = root / "samples"
        subprocess.run(["git", "clone", "--quiet", "--shared", str(SAMPLES), str(samples)], check=True)
        candidate = root / "candidate"
        script = candidate / "tools/migration/journeys.py"
        script.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT, script)
        subprocess.run(["git", "init", "-q", str(candidate)], check=True)
        subprocess.run(["git", "-C", str(candidate), "add", "."], check=True)
        subprocess.run(["git", "-C", str(candidate), "-c", "user.name=Test", "-c",
                        "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
        javac = root / "javac"
        javac.write_text(
            "#!/bin/sh\n"
            "/tmp/dyn4k-tools/jdk21/bin/javac \"$@\"\n"
            "result=$?\n"
            "if [ \"$result\" -eq 0 ] && [ \"$1\" = \"--release\" ]; then\n"
            "  printf 'x\\n' >> \"$MIGRATION_TEST_COUNTER\"\n"
            "  if [ \"$(wc -l < \"$MIGRATION_TEST_COUNTER\")\" -eq 2 ] && "
            "[ -n \"$MIGRATION_TEST_MUTATE_SOURCE\" ]; then\n"
            "    printf '\\n' >> \"$MIGRATION_TEST_MUTATE_SOURCE\"\n"
            "  fi\n"
            "fi\n"
            "exit \"$result\"\n"
        )
        javac.chmod(0o755)
        output = root / "output"
        source = next(samples.glob("src/main/java/**/*.java"))
        environment = {**os.environ, "MIGRATION_TEST_COUNTER": str(root / "compile-count"),
                       "MIGRATION_TEST_MUTATE_SOURCE": str(source) if change_sample else ""}
        result = subprocess.run([
            sys.executable, str(script), "run-all", "--samples", str(samples),
            "--resolved-root", str(Path("consumers/migration/build/resolved").resolve()),
            "--repository", str(Path("build/staging-repository").resolve()),
            "--instrumentation", str(Path("consumers/migration/build/resolved/instrumentation").resolve()),
            "--output", str(output), "--javac", str(javac),
            "--jdk", "/tmp/dyn4k-tools/jdk21", "--headful-image", "localhost/dyn4k-migration:missing-test-image",
        ], env=environment, capture_output=True, text=True, check=False)
        return result, output, samples

    def test_pinned_samples_have_exact_source_manifest(self):
        result = self.command("inspect-samples", "--samples", SAMPLES)
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(42, report["java_source_count"])
        self.assertEqual(
            "15ce636ac8eec34b24e73bc96270b49a44c94318850050b1e9bc0d930a9c8d58",
            report["manifest_sha256"],
        )

    def test_dirty_sample_checkout_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            copied = Path(temp) / "samples"
            subprocess.run(["git", "clone", "--quiet", "--shared", str(SAMPLES), str(copied)], check=True)
            source = next(copied.glob("src/main/java/**/*.java"))
            source.write_bytes(source.read_bytes() + b"\n")
            result = self.command("inspect-samples", "--samples", copied)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("sample checkout changed", result.stderr)

    def test_unavailable_runtime_records_all_ten_cases(self):
        with tempfile.TemporaryDirectory() as temp:
            result = self.command("unavailable", "--output", temp, "--reason", "no X11 display")
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads((Path(temp) / "summary.json").read_text())
            self.assertEqual(10, len(report["cases"]))
            self.assertEqual({"UNAVAILABLE"}, {case["status"] for case in report["cases"]})
            self.assertTrue(all(case["reason"] == "no X11 display" for case in report["cases"]))

    def test_baseline_uses_pinned_published_jars(self):
        with tempfile.TemporaryDirectory() as temp:
            resolved = Path(temp) / "resolved"
            resolved.mkdir()
            for name in ("dyn4j-6.0.0.jar", "jogl-all-2.3.2.jar", "gluegen-rt-2.3.2.jar"):
                shutil.copy2(Path("/tmp/dyn4k-migration-preflight/lib") / name, resolved / name)
            result = self.command("inspect-artifacts", "--provider", "baseline", "--resolved", resolved)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(3, len(json.loads(result.stdout)["jars"]))
            (resolved / "dyn4j-6.0.0.jar").write_bytes(b"changed")
            result = self.command("inspect-artifacts", "--provider", "baseline", "--resolved", resolved)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("SHA-256", result.stderr)

    def test_candidate_rejects_baseline_provider_and_unstaged_jar(self):
        with tempfile.TemporaryDirectory() as temp:
            resolved = Path(temp) / "resolved"
            staged = Path(temp) / "staged"
            resolved.mkdir()
            staged_jar = staged / "io/github/rubixhacker/dyn4k-core-jvm/0.1.0-alpha.1/dyn4k-core-jvm-0.1.0-alpha.1.jar"
            staged_jar.parent.mkdir(parents=True)
            staged_jar.write_bytes(b"published candidate")
            pom = staged_jar.with_suffix(".pom")
            pom.write_text("<project><groupId>io.github.rubixhacker</groupId>"
                           "<artifactId>dyn4k-core-jvm</artifactId><version>0.1.0-alpha.1</version></project>")
            staged_jar.with_suffix(".module").write_text("{}")
            shutil.copy2(staged_jar, resolved / staged_jar.name)
            for name in ("jogl-all-2.3.2.jar", "gluegen-rt-2.3.2.jar"):
                shutil.copy2(Path("/tmp/dyn4k-migration-preflight/lib") / name, resolved / name)
            result = self.command("inspect-artifacts", "--provider", "candidate",
                                  "--resolved", resolved, "--repository", staged)
            self.assertEqual(0, result.returncode, result.stderr)
            (resolved / staged_jar.name).write_bytes(b"project source output")
            result = self.command("inspect-artifacts", "--provider", "candidate",
                                  "--resolved", resolved, "--repository", staged)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("staged", result.stderr)
            shutil.copy2(staged_jar, resolved / staged_jar.name)
            shutil.copy2(Path("/tmp/dyn4k-migration-preflight/lib/dyn4j-6.0.0.jar"), resolved)
            result = self.command("inspect-artifacts", "--provider", "candidate",
                                  "--resolved", resolved, "--repository", staged)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("duplicate", result.stderr)
            (resolved / "dyn4j-6.0.0.jar").unlink()
            pom.unlink()
            result = self.command("inspect-artifacts", "--provider", "candidate",
                                  "--resolved", resolved, "--repository", staged)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("publication metadata", result.stderr)

    def test_baseline_compiles_all_unchanged_sources_at_java_8(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "compile"
            result = self.command(
                "compile", "--provider", "baseline", "--samples", SAMPLES,
                "--resolved", Path("consumers/migration/build/resolved/baseline").resolve(),
                "--output", output, "--javac", "/tmp/dyn4k-tools/jdk21/bin/javac",
            )
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads((output / "compile.json").read_text())
            self.assertEqual("PASSED", report["status"])
            self.assertEqual(42, report["source_count"])
            self.assertGreater(report["class_count"], 42)
            self.assertEqual(0, report["exit_code"])
            self.assertTrue((output / "javac.log").is_file())

    def test_run_rejects_dirty_candidate_worktree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / "tools/migration/journeys.py"
            script.parent.mkdir(parents=True)
            shutil.copy2(SCRIPT, script)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c",
                            "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
            script.write_bytes(script.read_bytes() + b"\n")
            result = subprocess.run([
                sys.executable, str(script), "run-all", "--samples", str(SAMPLES),
                "--resolved-root", str(root / "resolved"), "--repository", str(root / "staged"),
                "--instrumentation", str(root / "instrumentation"), "--output", str(root / "output"),
                "--jdk", str(root / "jdk"),
            ], capture_output=True, text=True, check=False)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("candidate worktree changed", result.stderr)
            self.assertFalse((root / "output").exists())

    def test_compiler_timeout_records_failed_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            slow_javac = root / "javac"
            slow_javac.write_text("#!/bin/sh\nsleep 5\n")
            slow_javac.chmod(0o755)
            output = root / "compile"
            result = self.command(
                "compile", "--provider", "baseline", "--samples", SAMPLES,
                "--resolved", Path("consumers/migration/build/resolved/baseline").resolve(),
                "--output", output, "--javac", slow_javac, "--timeout-seconds", "0.1",
            )
            self.assertNotEqual(0, result.returncode)
            receipt = json.loads((output / "compile.json").read_text())
            self.assertEqual("FAILED", receipt["status"])
            self.assertEqual("TIMEOUT", receipt["reason"])
            self.assertEqual(124, receipt["exit_code"])
            self.assertIn("PROCESS TIMEOUT", (output / "javac.log").read_text())

    def test_altered_raw_evidence_fails_manifest_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            raw = output / "raw.log"
            raw.write_text("original observation\n")
            (output / "a.log").write_text("earlier evidence\n")
            result = self.command("unavailable", "--output", output, "--reason", "no display")
            self.assertEqual(0, result.returncode, result.stderr)
            summary = json.loads((output / "summary.json").read_text())
            manifest = (output / "evidence.sha256").read_text().splitlines()
            self.assertEqual(2, len(manifest))
            self.assertTrue(manifest[0].endswith("  a.log"))
            self.assertTrue(manifest[1].endswith("  raw.log"))
            self.assertIn("evidence_manifest_sha256", summary)
            self.assertEqual(0, self.command("verify-evidence", "--output", output).returncode)
            raw.write_text("changed observation\n")
            result = self.command("verify-evidence", "--output", output)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("raw evidence changed", result.stderr)

    def test_missing_published_dependency_records_preparation_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "compile"
            result = self.command(
                "compile", "--provider", "baseline", "--samples", SAMPLES,
                "--resolved", Path(temp) / "missing", "--output", output,
            )
            self.assertNotEqual(0, result.returncode)
            receipt = json.loads((output / "compile.json").read_text())
            self.assertEqual("FAILED", receipt["status"])
            self.assertEqual("preparation", receipt["stage"])
            self.assertIn("resolved JAR set is empty", receipt["reason"])

    def test_sample_change_after_compilation_prevents_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            result, output, samples = self.run_with_sample_change_after_compilation(Path(temp), True)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("sample checkout changed", result.stderr)
            for provider in ("baseline", "candidate"):
                self.assertEqual("PASSED", json.loads((output / provider / "compile/compile.json").read_text())["status"])
            self.assertFalse((output / "summary.json").exists())
            receipt = json.loads((output / "sample-check.json").read_text())
            self.assertEqual("FAILED", receipt["status"])
            self.assertEqual("sample checkout changed", receipt["reason"])
            self.assertTrue(subprocess.run(["git", "-C", str(samples), "status", "--porcelain=v1"],
                                           capture_output=True, check=True).stdout)

    def test_stable_sample_after_compilation_writes_verified_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            result, output, samples = self.run_with_sample_change_after_compilation(Path(temp), False)
            self.assertNotEqual(0, result.returncode)
            self.assertTrue((output / "summary.json").is_file(), result.stderr)
            receipt = json.loads((output / "sample-check.json").read_text())
            self.assertEqual("PASSED", receipt["status"])
            self.assertEqual(42, receipt["java_source_count"])
            self.assertEqual("15ce636ac8eec34b24e73bc96270b49a44c94318850050b1e9bc0d930a9c8d58",
                             receipt["manifest_sha256"])
            summary = json.loads((output / "summary.json").read_text())
            self.assertEqual(10, summary["unavailable_cases"])
            self.assertEqual(0, self.command("verify-evidence", "--output", output).returncode)
            self.assertFalse(subprocess.run(["git", "-C", str(samples), "status", "--porcelain=v1"],
                                            capture_output=True, check=True).stdout)


if __name__ == "__main__":
    unittest.main()
