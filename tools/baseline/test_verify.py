import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("verify.py")


def command(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True)


class ComparatorTests(unittest.TestCase):
    def test_kotlin_style_additions_and_declaration_order_are_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self.jar(root / "baseline", {
                "Api.java": "public class Api<T extends Number> { public T value; public void move(int n) {} public static int size() { return 1; } }",
                "Helper.java": "class Helper { public void internal() {} }",
            })
            candidate = self.jar(root / "candidate", {
                "Api.java": "public class Api<T extends Number> implements java.io.Serializable { public static final Companion Companion = new Companion(); public static final int size() { return 1; } public void move(int n) {} public T value; public int added() { return 0; } public static class Companion {} }",
            })
            result = command("compare", "--baseline-jar", baseline, "--candidate", candidate)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(json.loads(result.stdout)["missing_types"], [])

    def test_public_contract_mutations_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline_source = "public class Api<T extends Number> extends Parent { public T value; public static int size() { return 1; } public void move(int n) {} public java.util.List<String> items() { return null; } }"
            baseline = self.jar(root / "baseline", {"Api.java": baseline_source,
                                                     "Parent.java": "public class Parent {}"})
            mutations = {
                "missing_method": baseline_source.replace("public void move(int n) {}", ""),
                "access": baseline_source.replace("public void move", "protected void move"),
                "static": baseline_source.replace("public static int size", "public int size"),
                "final": baseline_source.replace("public void move", "public final void move"),
                "abstract_type": baseline_source.replace("public class Api", "public abstract class Api"),
                "final_type": baseline_source.replace("public class Api", "public final class Api"),
                "generic_bound": baseline_source.replace("T extends Number", "T extends Object"),
                "superclass": baseline_source.replace(" extends Parent", ""),
                "field_type": baseline_source.replace("public T value", "public Number value"),
                "generic_return": baseline_source.replace("List<String>", "List<Integer>"),
            }
            for label, source in mutations.items():
                with self.subTest(label=label):
                    candidate = self.jar(root / label, {"Api.java": source,
                                                         "Parent.java": "public class Parent {}"})
                    result = command("compare", "--baseline-jar", baseline,
                                     "--candidate", candidate)
                    self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
                    report = json.loads(result.stdout)
                    self.assertTrue(report["signature_mismatches"], report)

    @staticmethod
    def jar(root, files):
        root.mkdir()
        for name, source in files.items():
            (root / name).write_text(source)
        classes = root / "classes"
        classes.mkdir()
        subprocess.run(["javac", "--release", "8", "-d", str(classes),
                        *[str(root / name) for name in files]], check=True, capture_output=True)
        archive = root / "library.jar"
        subprocess.run(["jar", "cf", str(archive), "-C", str(classes), "."],
                       check=True, capture_output=True)
        return archive


class RunReportTests(unittest.TestCase):
    def test_incomplete_ignored_and_invalid_results_fail(self):
        good = {"actual_executed_cases": 2385, "failures": 0, "ignored": 0,
                "process_exit_code": 0,
                "output": "ACTUAL_TESTS=2385\nFAILURES=0\nIGNORED=0\n", "stderr": "",
                "compile_release": 8, "harness_class_major": 52,
                "javac_version": "javac 25.0.3", "java_version": "openjdk 25.0.3",
                "test_input_sha256": {"src/test/java/Example.java": "example"}}
        invalid = {
            "incomplete": {"actual_executed_cases": 2384, "output": "ACTUAL_TESTS=2384\nFAILURES=0\nIGNORED=0\n"},
            "ignored": {"ignored": 1, "output": "ACTUAL_TESTS=2385\nFAILURES=0\nIGNORED=1\n"},
            "failed": {"failures": 1, "output": "ACTUAL_TESTS=2385\nFAILURES=1\nIGNORED=0\n"},
            "exit": {"process_exit_code": 1},
            "missing_output": {"output": ""},
            "nonnumeric": {"actual_executed_cases": "2385"},
            "wrong_bytecode": {"harness_class_major": 65},
        }
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "run.json"
            report.write_text(json.dumps(good))
            self.assertEqual(command("check-run", "--report", report).returncode, 0)
            for label, changes in invalid.items():
                with self.subTest(label=label):
                    report.write_text(json.dumps(good | changes))
                    self.assertNotEqual(command("check-run", "--report", report).returncode, 0)


class SourceIntegrityTests(unittest.TestCase):
    def test_dirty_untracked_and_changed_source_archive_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / "checkout"
            source = checkout / "src/main/java/example/Api.java"
            source.parent.mkdir(parents=True)
            source.write_text("package example; public class Api {}\n")
            test = checkout / "src/test/java/example/ApiTest.java"
            test.parent.mkdir(parents=True)
            test.write_text("package example; public class ApiTest {}\n")
            subprocess.run(["git", "init", "-q", str(checkout)], check=True)
            subprocess.run(["git", "-C", str(checkout), "add", "src"], check=True)
            subprocess.run(["git", "-C", str(checkout), "-c", "user.name=Test",
                            "-c", "user.email=test@example.com", "commit", "-qm", "fixture"], check=True)
            revision = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"],
                                      check=True, capture_output=True, text=True).stdout.strip()
            archive = root / "sources.jar"
            with zipfile.ZipFile(archive, "w") as jar:
                jar.writestr("example/Api.java", source.read_bytes())
            args = ("check-source", "--checkout", checkout, "--sources-jar", archive,
                    "--commit", revision)
            self.assertEqual(command(*args).returncode, 0)
            source.write_text("package example; public class Api { int changed; }\n")
            self.assertNotEqual(command(*args).returncode, 0)
            source.write_text("package example; public class Api {}\n")
            untracked = checkout / "src/test/java/example/Extra.java"
            untracked.write_text("class Extra {}\n")
            self.assertNotEqual(command(*args).returncode, 0)
            untracked.unlink()
            with zipfile.ZipFile(archive, "w") as jar:
                jar.writestr("example/Api.java", b"package example; public class Api { int changed; }\n")
            self.assertNotEqual(command(*args).returncode, 0)


if __name__ == "__main__":
    unittest.main()
