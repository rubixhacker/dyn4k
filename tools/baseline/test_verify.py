import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("verify.py")
GEOMETRY_SCRIPT = SCRIPT.parents[2] / "scripts/verify-geometry-jvm-api.py"
FOUNDATION_SCRIPT = SCRIPT.parents[2] / "scripts/verify-foundation-jvm-api.py"
FOUNDATION_TYPES = (
    "org.dyn4j.Copyable", "org.dyn4j.Epsilon",
    "org.dyn4j.exception.ArgumentNullException",
    "org.dyn4j.geometry.Vector2", "org.dyn4j.geometry.Vector3",
    "org.dyn4j.geometry.Rotation", "org.dyn4j.geometry.Matrix22",
    "org.dyn4j.geometry.Matrix33", "org.dyn4j.geometry.Transform",
    "org.dyn4j.geometry.Rotatable", "org.dyn4j.geometry.Translatable",
    "org.dyn4j.geometry.Transformable", "org.dyn4j.geometry.Shiftable",
)


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
                "Api.java": "public class Api<T extends Number> implements java.io.Serializable { public static final Companion Companion = new Companion(); public static int size() { return 1; } public void move(int n) {} public T value; public int added() { return 0; } public static class Companion {} }",
            })
            result = command("compare", "--baseline-jar", baseline, "--candidate", candidate)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(json.loads(result.stdout)["missing_types"], [])

    def test_java8_extension_contract_rejects_incompatible_modifiers_and_generics(self):
        cases = {
            "subclass_override": (
                "public class Api { public Number value() { return 1; } }",
                "public class Api { public final Number value() { return 1; } }",
                "public class Consumer extends Api { @Override public Number value() { return 2; } }"),
            "static_hiding": (
                "public class Api { public static int count() { return 1; } }",
                "public class Api { public static final int count() { return 1; } }",
                "public class Consumer extends Api { public static int count() { return 2; } }"),
            "generic_list_override": (
                "public class Api { public java.util.List<? extends Vector2> points() { return null; } }",
                "public class Api { public java.util.List<Vector2> points() { return null; } }",
                "public class Consumer extends Api { @Override public java.util.List<? extends Vector2> points() { return null; } }"),
            "final_type": (
                "public class Api {}", "public final class Api {}",
                "public class Consumer extends Api {}"),
            "constant_field": (
                "public class Api { public static final int KEY = 1; }",
                "public class Api { public static int KEY = 1; }",
                "public class Consumer { int run(int value) { switch (value) { case Api.KEY: return 1; default: return 0; } } }"),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for label, (before, after, consumer) in cases.items():
                with self.subTest(label=label):
                    case = root / label
                    case.mkdir()
                    extra = {"Vector2.java": "public class Vector2 {}"} if label == "generic_list_override" else {}
                    baseline = self.jar(case / "baseline", {"Api.java": before, **extra})
                    candidate = self.jar(case / "candidate", {"Api.java": after, **extra})
                    self.assert_java8_consumer(case, baseline, candidate, consumer)
                    result = command("compare", "--baseline-jar", baseline, "--candidate", candidate)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertTrue(json.loads(result.stdout)["signature_mismatches"])
                    expected_text = {
                        "subclass_override": "public final java.lang.Number value()",
                        "static_hiding": "public static final int count()",
                        "generic_list_override": "java.util.List<Vector2>",
                        "final_type": "public final class Api",
                        "constant_field": "public static int KEY",
                    }[label]
                    self.assertIn(expected_text, result.stdout)

    def test_covariant_bridge_does_not_replace_source_method(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self.jar(root / "baseline", {
                "Parent.java": "public class Parent<T> { public T value() { return null; } }",
                "Api.java": "public class Api extends Parent<String> { @Override public String value() { return \"ok\"; } }",
            })
            candidate = self.jar(root / "candidate", {
                "Parent.java": "public class Parent<T> { public T value() { return null; } }",
                "Api.java": "public class Api extends Parent<String> {}",
            })
            baseline_details = subprocess.run(["javap", "-protected", "-s", "-classpath",
                                               str(baseline), "Api"], check=True,
                                              capture_output=True, text=True).stdout
            self.assertIn("descriptor: ()Ljava/lang/String;", baseline_details)
            self.assertIn("descriptor: ()Ljava/lang/Object;", baseline_details)
            result = command("compare", "--baseline-jar", baseline, "--candidate", candidate,
                             "--only", "Api")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("java.lang.String value()", result.stdout)
            self.assertNotIn("missing public java.lang.Object value()", result.stdout)

    def test_java8_consumer_accepts_wider_access_and_removed_final(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self.jar(root / "baseline", {
                "Api.java": "public class Api { protected static final int count() { return 1; } protected final void move() {} }",
            })
            candidate = self.jar(root / "candidate", {
                "Api.java": "public class Api { public static int count() { return 1; } public void move() {} public int added() { return 2; } }",
            })
            consumer = "public class Consumer { int run(Api api) { api.move(); return Api.count(); } }"
            for archive in (baseline, candidate):
                output = root / ("baseline-classes" if archive == baseline else "candidate-classes")
                compiled = subprocess.run(["javac", "--release", "8", "-classpath", str(archive),
                                           "-d", str(output), str(self.consumer(root, consumer))],
                                          capture_output=True, text=True)
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = command("compare", "--baseline-jar", baseline, "--candidate", candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_transitive_interface_is_source_equivalent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = {
                "Parent.java": "public interface Parent { void move(); }",
                "Child.java": "public interface Child extends Parent {}",
            }
            baseline = self.jar(root / "baseline", {
                **shared, "Api.java": "public class Api implements Child, Parent { public void move() {} }",
            })
            candidate = self.jar(root / "candidate", {
                **shared, "Api.java": "public class Api implements Child { public void move() {} }",
            })
            consumer = self.consumer(root, "public class Consumer { Parent run() { return new Api(); } }")
            for archive in (baseline, candidate):
                compiled = subprocess.run(["javac", "--release", "8", "-classpath", str(archive),
                                           "-d", str(root / ("b" if archive == baseline else "c")),
                                           str(consumer)], capture_output=True, text=True)
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = command("compare", "--baseline-jar", baseline, "--candidate", candidate,
                             "--only", "Api")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @staticmethod
    def consumer(root, source):
        path = root / "Consumer.java"
        path.write_text(source)
        return path

    def test_geometry_cli_rejects_final_and_generic_override_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = "package org.dyn4j.geometry; "
            support = self.geometry_support_sources()
            baseline = self.jar(root / "baseline", {
                "Api.java": package + "public class Api { public java.util.List<? extends Vector2> points() { return null; } public void move() {} }",
                "Vector2.java": package + "public class Vector2 {}",
                **support,
            })
            candidate = self.jar(root / "candidate", {
                "Api.java": package + "public class Api { public java.util.List<Vector2> points() { return null; } public final void move() {} }",
                "Vector2.java": package + "public class Vector2 {}",
                **support,
            })
            consumer = package + "public class Consumer extends Api { @Override public java.util.List<? extends Vector2> points() { return null; } @Override public void move() {} }"
            self.assert_java8_consumer(root, baseline, candidate, consumer)
            result = subprocess.run([sys.executable, str(GEOMETRY_SCRIPT), str(baseline),
                                     str(candidate), "--all-root"], capture_output=True,
                                    text=True)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("<? extends org.dyn4j.geometry.Vector2>", result.stderr)
            self.assertIn("final", result.stderr)

    def test_geometry_cli_accepts_additional_members(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            support = self.geometry_support_sources()
            prefix = "package org.dyn4j.geometry; "
            before = prefix + "public class Api { public void move() {} }"
            after = prefix + "public class Api { public static final Companion Companion = new Companion(); public void move() {} public int added() { return 1; } public static class Companion {} }"
            baseline = self.jar(root / "baseline", {"Api.java": before, **support})
            candidate = self.jar(root / "candidate", {"Api.java": after, **support})
            consumer = self.consumer(root, prefix + "public class Consumer { void run(Api api) { api.move(); } }")
            for archive in (baseline, candidate):
                compiled = subprocess.run(["javac", "--release", "8", "-classpath", str(archive),
                                           "-d", str(root / ("b" if archive == baseline else "c")),
                                           str(consumer)], capture_output=True, text=True)
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([sys.executable, str(GEOMETRY_SCRIPT), str(baseline),
                                     str(candidate), "--all-root"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    @staticmethod
    def geometry_support_sources():
        return {
            "DataContainer.java": "package org.dyn4j; public interface DataContainer {}",
            **{name + ".java": "package org.dyn4j.exception; public class " + name + " {}"
               for name in ("EmptyCollectionException", "InvalidIndexException",
                            "NullElementException", "ValueOutOfRangeException")},
        }

    def assert_java8_consumer(self, root, baseline, candidate, source):
        consumer = root / "Consumer.java"
        consumer.write_text(source)
        for archive, passes in ((baseline, True), (candidate, False)):
            result = subprocess.run(["javac", "--release", "8", "-classpath", str(archive),
                                     "-d", str(root / ("baseline-classes" if passes
                                                       else "candidate-classes")),
                                     str(consumer)], capture_output=True, text=True)
            if passes:
                self.assertEqual(result.returncode, 0, result.stderr)
            else:
                self.assertNotEqual(result.returncode, 0, result.stderr)

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


class FoundationComparatorTests(unittest.TestCase):
    def test_static_hiding_rejects_added_final(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self.foundation_jar(root / "baseline", "public static int count() { return 1; }")
            candidate = self.foundation_jar(root / "candidate", "public static final int count() { return 1; }")
            self.assert_java8_source(root, baseline, candidate,
                                     "package org.dyn4j.geometry; public class Consumer extends Vector2 { public static int count() { return 2; } }",
                                     candidate_passes=False)
            result = subprocess.run([sys.executable, str(FOUNDATION_SCRIPT), str(baseline),
                                     str(candidate)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("public static final int count()", result.stderr)

    def test_package_method_absence_breaks_same_package_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self.foundation_jar(root / "baseline", "void rotate(int angle) {}")
            candidate = self.foundation_jar(root / "candidate", "")
            self.assert_java8_source(root, baseline, candidate,
                                     "package org.dyn4j.geometry; public class Consumer { void run(Vector2 value) { value.rotate(1); } }",
                                     candidate_passes=False)
            result = subprocess.run([sys.executable, str(FOUNDATION_SCRIPT), str(baseline),
                                     str(candidate)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("rotate(int)", result.stderr)

    def test_wider_access_and_removed_method_final_are_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self.foundation_jar(root / "baseline", "protected static final int count() { return 1; }")
            candidate = self.foundation_jar(root / "candidate", "public static int count() { return 1; }")
            self.assert_java8_source(root, baseline, candidate,
                                     "package org.dyn4j.geometry; public class Consumer extends Vector2 { int run() { return Vector2.count(); } }",
                                     candidate_passes=True)
            result = subprocess.run([sys.executable, str(FOUNDATION_SCRIPT), str(baseline),
                                     str(candidate)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    @staticmethod
    def foundation_jar(root, vector_member):
        sources = {}
        for full_name in FOUNDATION_TYPES:
            package, name = full_name.rsplit(".", 1)
            member = vector_member if full_name == "org.dyn4j.geometry.Vector2" else ""
            sources[name + ".java"] = f"package {package}; public class {name} {{ {member} }}"
        return ComparatorTests.jar(root, sources)

    def assert_java8_source(self, root, baseline, candidate, source, candidate_passes):
        consumer = root / "Consumer.java"
        consumer.write_text(source)
        for archive, passes in ((baseline, True), (candidate, candidate_passes)):
            output = root / ("baseline-classes" if archive == baseline else "candidate-classes")
            result = subprocess.run(["javac", "--release", "8", "-classpath", str(archive),
                                     "-d", str(output), str(consumer)], capture_output=True,
                                    text=True)
            if passes:
                self.assertEqual(result.returncode, 0, result.stderr)
            else:
                self.assertNotEqual(result.returncode, 0, result.stderr)


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
