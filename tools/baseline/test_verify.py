import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tools.baseline import verify


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
    arguments = list(map(str, args))
    if arguments and arguments[0] == "compare":
        baseline = Path(arguments[arguments.index("--baseline-jar") + 1])
        code = ("import sys; from tools.baseline import verify as v; "
                "v.BINARY_SHA256 = sys.argv.pop(1); v.main()")
        invocation = [sys.executable, "-c", code, verify.digest(baseline), *arguments]
    else:
        invocation = [sys.executable, str(SCRIPT), *arguments]
    return subprocess.run(invocation,
                          capture_output=True, text=True)


def slice_command(script, baseline, candidate, *extra):
    code = ("import runpy, sys; "
            f"sys.path.insert(0, {str(SCRIPT.parent)!r}); "
            "import verify; verify.BINARY_SHA256 = sys.argv.pop(1); "
            f"runpy.run_path({str(script)!r}, run_name='__main__')")
    return subprocess.run([sys.executable, "-c", code, verify.digest(baseline),
                           str(baseline), str(candidate), *extra], capture_output=True, text=True)


def foundation_command(baseline, candidate):
    return slice_command(FOUNDATION_SCRIPT, baseline, candidate)


class ComparatorTests(unittest.TestCase):
    def test_baseline_hash_identifies_inventoried_bytes_during_temporary_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self.jar(root / "baseline", {"Api.java": "public class Api {}"})
            original_copy = root / "baseline-original.jar"
            shutil.copyfile(baseline, original_copy)
            candidate = self.jar(root / "candidate", {"Api.java": "public class Api {}"})
            changed = self.jar(root / "changed", {
                "Api.java": "public class Api { public final String helper() { return \"new\"; } }",
            })
            original_hash = verify.digest(baseline)
            original_inventory = verify.jar_types
            calls = 0

            def replace_during_baseline_inventory(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    shutil.copyfile(changed, baseline)
                inventory = original_inventory(*args, **kwargs)
                if calls == 1:
                    shutil.copyfile(original_copy, baseline)
                return inventory

            with patch.object(verify, "BINARY_SHA256", original_hash):
                with patch.object(verify, "jar_types", side_effect=replace_during_baseline_inventory):
                    report = verify.compare_jars(baseline, candidate)
            self.assertEqual(verify.digest(baseline), original_hash)
            self.assertEqual(report["baseline_sha256"], original_hash)
            self.assertEqual(report["signature_mismatches"], [])

    def test_candidate_hash_identifies_inventoried_bytes_during_path_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self.jar(root / "baseline", {"Api.java": "public class Api {}"})
            candidate = root / "candidate.jar"
            shutil.copyfile(baseline, candidate)
            changed = self.jar(root / "changed", {
                "Api.java": "public class Api { public final String helper() { return \"new\"; } }",
            })
            initial_hash = verify.digest(candidate)
            changed_hash = verify.digest(changed)
            original_inventory = verify.jar_types
            calls = 0

            def replace_after_inventory(*args, **kwargs):
                nonlocal calls
                calls += 1
                inventory = original_inventory(*args, **kwargs)
                if calls == 2:
                    shutil.copyfile(changed, candidate)
                return inventory

            with patch.object(verify, "BINARY_SHA256", verify.digest(baseline)):
                with patch.object(verify, "jar_types", side_effect=replace_after_inventory):
                    raced = verify.compare_jars(baseline, candidate)
                direct = verify.compare_jars(baseline, candidate)
            self.assertEqual(calls, 2)
            self.assertNotEqual(initial_hash, changed_hash)
            self.assertEqual(verify.digest(candidate), changed_hash)
            self.assertEqual(raced["candidate_sha256"], initial_hash)
            self.assertEqual(raced["added_member_risks"], [])
            self.assertEqual(len(direct["added_member_risks"]), 1)
            self.assertEqual(direct["added_member_risks"][0]["artifact_sha256"], changed_hash)

    def test_kotlin_style_additions_and_declaration_order_are_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self.jar(root / "baseline", {
                "Api.java": "public final class Api<T extends Number> { public T value; public void move(int n) {} public static int size() { return 1; } }",
                "Helper.java": "class Helper { public void internal() {} }",
            })
            candidate = self.jar(root / "candidate", {
                "Api.java": "public final class Api<T extends Number> implements java.io.Serializable { public static int size() { return 1; } public void move(int n) {} public T value; public int added() { return 0; } }",
                "Helper.java": "class Helper { public void internal() {} }",
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
                "Api.java": "public class Api { public static int count() { return 1; } public void move() {} }",
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

    def test_final_methods_in_final_type_preserve_source_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self.jar(root / "baseline", {
                "Api.java": "public final class Api { public int value() { return 1; } public static int count() { return 1; } public static final int KEY = 1; }",
            })
            candidate = self.jar(root / "candidate", {
                "Api.java": "public final class Api { public final int value() { return 1; } public static final int count() { return 1; } public static final int KEY = 1; }",
            })
            source = "public class Consumer { int run(Api api) { switch (api.value()) { case Api.KEY: return Api.count(); default: return 0; } } }"
            self.assert_java8_consumer_result(root, baseline, candidate, source, True)
            result = command("compare", "--baseline-jar", baseline, "--candidate", candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(len(json.loads(result.stdout)["compatible_differences"]), 2)

    def test_final_type_does_not_relax_field_constant_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self.jar(root / "baseline", {
                "Api.java": "public final class Api { public static final int KEY = 1; }"})
            candidate = self.jar(root / "candidate", {
                "Api.java": "public final class Api { public static int KEY = 1; }"})
            source = "public class Consumer { int run(int value) { switch (value) { case Api.KEY: return 1; default: return 0; } } }"
            self.assert_java8_consumer_result(root, baseline, candidate, source, False)
            result = command("compare", "--baseline-jar", baseline, "--candidate", candidate)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("public static int KEY", result.stdout)

    def test_transitive_generic_interface_requires_substitution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = {"Parent.java": "public interface Parent<T> {}",
                      "Child.java": "public interface Child<U> extends Parent<U> {}"}
            baseline = self.jar(root / "baseline", {**shared,
                "Api.java": "public class Api implements Child<String>, Parent<String> {}"})
            candidate = self.jar(root / "candidate", {**shared,
                "Api.java": "public class Api implements Child<String> {}"})
            wrong = self.jar(root / "wrong", {**shared,
                "Api.java": "public class Api implements Child<Integer> {}"})
            source = "public class Consumer { Parent<String> run(Api value) { return value; } }"
            self.assert_java8_consumer_result(root, baseline, candidate, source, True)
            self.assert_java8_consumer_result(root, baseline, wrong, source, False)
            good = command("compare", "--baseline-jar", baseline, "--candidate", candidate,
                           "--only", "Api")
            bad = command("compare", "--baseline-jar", baseline, "--candidate", wrong,
                          "--only", "Api")
            self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
            self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)

    def test_constructor_list_extends_widens_without_relaxing_methods(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self.jar(root / "baseline", {
                "Api.java": "public abstract class Api<T> { public Api(java.util.List<T> values) {} protected Api(Api<T> other, java.util.List<T> values) {} public void move(java.util.List<T> values) {} }",
            })
            candidate = self.jar(root / "candidate", {
                "Api.java": "public abstract class Api<T> { public Api(java.util.List<? extends T> values) {} protected Api(Api<T> other, java.util.List<? extends T> values) {} public void move(java.util.List<T> values) {} }",
            })
            wrong = self.jar(root / "wrong", {
                "Api.java": "public abstract class Api<T> { public Api(java.util.List<? extends T> values) {} protected Api(Api<T> other, java.util.List<? extends T> values) {} public void move(java.util.List<? extends T> values) {} }",
            })
            source = "import java.util.List; public class Consumer<T> extends Api<T> { Consumer(List<T> values) { super(values); } Consumer(Api<T> other, List<T> values) { super(other, values); } @Override public void move(List<T> values) {} }"
            self.assert_java8_consumer_result(root, baseline, candidate, source, True)
            self.assert_java8_consumer_result(root, baseline, wrong, source, False)
            good = command("compare", "--baseline-jar", baseline, "--candidate", candidate,
                           "--only", "Api")
            bad = command("compare", "--baseline-jar", baseline, "--candidate", wrong,
                          "--only", "Api")
            self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
            self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)

    def test_implicit_object_header_preserves_java8_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self.jar(root / "baseline", {"Api.java": "public class Api {}"})
            candidate = self.jar(root / "candidate", {"Api.java": "public class Api {}"})
            self.assert_java8_consumer_result(root, baseline, candidate,
                                              "public class Consumer extends Api {}", True)
            baseline_names, baseline_signatures = verify.jar_types(baseline, verbose=True)
            candidate_names, candidate_signatures = verify.jar_types(candidate, verbose=True)
            baseline_signatures["Api"] = baseline_signatures["Api"].replace(
                "public class Api\n", "public class Api extends java.lang.Object\n", 1)
            with patch.object(verify, "BINARY_SHA256", verify.digest(baseline)), patch.object(
                    verify, "jar_types", side_effect=[(baseline_names, baseline_signatures),
                                                       (candidate_names, candidate_signatures)]):
                report = verify.compare_jars(baseline, candidate)
            self.assertEqual(report["signature_mismatches"], [])
            self.assertEqual(len(report["compatible_differences"]), 1)

    def assert_java8_consumer_result(self, root, baseline, candidate, source, candidate_passes):
        consumer = self.consumer(root, source)
        for archive, passes in ((baseline, True), (candidate, candidate_passes)):
            result = subprocess.run(["javac", "--release", "8", "-classpath", str(archive),
                                     "-d", str(root / ("baseline-classes" if archive == baseline
                                                       else "candidate-classes")), str(consumer)],
                                    capture_output=True, text=True)
            if passes:
                self.assertEqual(result.returncode, 0, result.stderr)
            else:
                self.assertNotEqual(result.returncode, 0, result.stderr)

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
            result = slice_command(GEOMETRY_SCRIPT, baseline, candidate, "--all-root")
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
            result = slice_command(GEOMETRY_SCRIPT, baseline, candidate, "--all-root")
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
    def test_added_source_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self.foundation_jar(root / "baseline", "")
            candidate = self.foundation_jar(
                root / "candidate", "public final String helper() { return \"candidate\"; }")
            self.assert_java8_source(root, baseline, candidate,
                                     "package org.dyn4j.geometry; public class Consumer extends Vector2 { public int helper() { return 1; } }",
                                     candidate_passes=False)
            result = foundation_command(baseline, candidate)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("added public final java.lang.String helper()", result.stderr)

    def test_static_hiding_rejects_added_final(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self.foundation_jar(root / "baseline", "public static int count() { return 1; }")
            candidate = self.foundation_jar(root / "candidate", "public static final int count() { return 1; }")
            self.assert_java8_source(root, baseline, candidate,
                                     "package org.dyn4j.geometry; public class Consumer extends Vector2 { public static int count() { return 2; } }",
                                     candidate_passes=False)
            result = foundation_command(baseline, candidate)
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
            result = foundation_command(baseline, candidate)
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
            result = foundation_command(baseline, candidate)
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
    def test_source_archive_hash_identifies_checked_bytes_during_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / "checkout"
            source = checkout / "src/main/java/example/Api.java"
            source.parent.mkdir(parents=True)
            source.write_text("package example; public class Api {}\n")
            subprocess.run(["git", "init", "-q", str(checkout)], check=True)
            subprocess.run(["git", "-C", str(checkout), "add", "src"], check=True)
            subprocess.run(["git", "-C", str(checkout), "-c", "user.name=Test",
                            "-c", "user.email=test@example.com", "commit", "-qm", "fixture"], check=True)
            revision = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"],
                                      check=True, capture_output=True, text=True).stdout.strip()
            archive = root / "sources.jar"
            changed = root / "changed.jar"
            with zipfile.ZipFile(archive, "w") as jar:
                jar.writestr("example/Api.java", source.read_bytes())
            with zipfile.ZipFile(changed, "w") as jar:
                jar.writestr("example/Api.java", b"package example; public class Api { int changed; }\n")
            original_hash = verify.digest(archive)
            original_open = zipfile.ZipFile
            replaced = False

            def replace_after_open(*args, **kwargs):
                nonlocal replaced
                opened = original_open(*args, **kwargs)
                if not replaced:
                    changed.replace(archive)
                    replaced = True
                return opened

            with patch.object(verify.zipfile, "ZipFile", side_effect=replace_after_open):
                result = verify.verify_source_inputs(checkout, archive, revision)
            self.assertTrue(replaced)
            self.assertNotEqual(verify.digest(archive), original_hash)
            self.assertEqual(result["source_jar_sha256"], original_hash)
            self.assertTrue(result["source_jar_matches_tracked_bytes"])

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


class InventoryIdentityTests(unittest.TestCase):
    def test_inventory_binary_hash_identifies_inventoried_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            production = source / "src/main/java"
            tests = source / "src/test/java"
            production.mkdir(parents=True)
            tests.mkdir(parents=True)
            for index in range(268):
                (production / f"P{index}.java").write_text(f"class P{index} {{}}")
            for index in range(199):
                (tests / f"T{index}.java").write_text(f"class T{index} {{}}")
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(["git", "-C", str(source), "add", "src"], check=True)
            subprocess.run(["git", "-C", str(source), "-c", "user.name=Test",
                            "-c", "user.email=test@example.com", "commit", "-qm", "fixture"], check=True)
            revision = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"],
                                      check=True, capture_output=True, text=True).stdout.strip()
            binary = ComparatorTests.jar(root / "baseline", {"Api.java": "public class Api {}"})
            changed = ComparatorTests.jar(root / "changed", {
                "Api.java": "public class Api { public void extra() {} }",
            })
            original_hash = verify.digest(binary)
            original_inventory = verify.jar_types
            replaced = False

            def replace_after_inventory(*args, **kwargs):
                nonlocal replaced
                result = original_inventory(*args, **kwargs)
                if not replaced:
                    shutil.copyfile(changed, binary)
                    replaced = True
                return result

            with patch.object(verify, "BINARY_SHA256", original_hash):
                with patch.object(verify, "COMMIT", revision):
                    with patch.object(verify, "jar_types", side_effect=replace_after_inventory):
                        report = verify.inventory(source, binary, root / "inventory.json")
            self.assertTrue(replaced)
            self.assertNotEqual(verify.digest(binary), original_hash)
            self.assertEqual(report["baseline"]["binary_sha256"], original_hash)
            self.assertNotIn("sources_sha256", report["baseline"])
            self.assertNotIn("extra()", report["public_protected_jvm_signatures"]["Api"])

    def test_inventory_rejects_test_source_replaced_after_clean_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            production = source / "src/main/java"
            tests = source / "src/test/java"
            production.mkdir(parents=True)
            tests.mkdir(parents=True)
            for index in range(268):
                (production / f"P{index}.java").write_text(f"class P{index} {{}}")
            for index in range(199):
                (tests / f"T{index}.java").write_text(f"class T{index} {{}}")
            target = tests / "T0.java"
            target.write_text("class T0 {} // @Test\n")
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(["git", "-C", str(source), "add", "src"], check=True)
            subprocess.run(["git", "-C", str(source), "-c", "user.name=Test",
                            "-c", "user.email=test@example.com", "commit", "-qm", "fixture"], check=True)
            revision = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"],
                                      check=True, capture_output=True, text=True).stdout.strip()
            binary = ComparatorTests.jar(root / "binary", {"Api.java": "public class Api {}"})
            archive = root / "sources.jar"
            with zipfile.ZipFile(archive, "w") as jar:
                for path in production.glob("*.java"):
                    jar.write(path, path.name)
            with patch.object(verify, "COMMIT", revision), \
                 patch.object(verify, "BINARY_SHA256", verify.digest(binary)), \
                 patch.object(verify, "SOURCES_SHA256", verify.digest(archive)):
                checked = verify.verify_source_inputs(source, archive, revision)
                self.assertTrue(checked["source_inputs_clean"])
                target.write_text("class T0 {} // @Test RACE_MARKER // @Test\n")
                with self.assertRaisesRegex(ValueError, "dirty|differ"):
                    verify.inventory(source, binary, root / "inventory.json")
                target.write_text("class T0 {} // @Test\n")
                report = verify.inventory(source, binary, root / "clean-inventory.json")
                self.assertEqual(report["test_annotations"], 1)


class GitReplacementIdentityTests(unittest.TestCase):
    def inputs(self, root, change_production=False):
        source = root / "source"
        production = source / "src/main/java"
        tests = source / "src/test/java"
        production.mkdir(parents=True)
        tests.mkdir(parents=True)
        for index in range(268):
            (production / f"P{index}.java").write_text(f"class P{index} {{}}\n")
        for index in range(199):
            (tests / f"T{index}.java").write_text(f"class T{index} {{}}\n")
        test = tests / "T0.java"
        test.write_text("class T0 {} // @Test\n")
        archive = root / "sources.jar"
        with zipfile.ZipFile(archive, "w") as jar:
            for path in production.glob("*.java"):
                jar.write(path, path.name)
        git_env = os.environ.copy()
        git_env.pop("GIT_NO_REPLACE_OBJECTS", None)

        def git(*args):
            return subprocess.run(["git", "-C", str(source), *args], check=True,
                                  capture_output=True, text=True, env=git_env).stdout.strip()

        git("init", "-q")
        git("add", "src")
        git("-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-qm", "original")
        original = git("rev-parse", "HEAD")
        test.write_text("class T0 {} // @Test REPLACE_REF_MARKER // @Test\n")
        if change_production:
            (production / "P0.java").write_text("class P0 { int changed; }\n")
        git("add", "src")
        git("-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-qm", "replacement")
        replacement = git("rev-parse", "HEAD")
        git("checkout", "--detach", original)
        git("replace", original, replacement)
        git("reset", "--hard", original)
        self.assertEqual(git("rev-parse", "HEAD"), original)
        self.assertEqual(git("status", "--porcelain=v1", "--", "src"), "")
        self.assertTrue(git("--no-replace-objects", "status", "--porcelain=v1", "--", "src"))
        binary = ComparatorTests.jar(root / "binary", {"Api.java": "public class Api {}"})
        return source, archive, binary, original

    def test_replacement_ref_cannot_authenticate_changed_test_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, archive, _, original = self.inputs(root)
            with patch.object(verify, "COMMIT", original), \
                 patch.object(verify, "SOURCES_SHA256", verify.digest(archive)):
                with self.assertRaisesRegex(ValueError, "dirty|differ"):
                    verify.verify_source_inputs(source, archive, original)

    def test_replacement_ref_cannot_change_test_or_production_inventory(self):
        for changed_production in (False, True):
            with self.subTest(changed_production=changed_production):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    source, _, binary, original = self.inputs(root, changed_production)
                    output = root / "inventory.json"
                    with patch.object(verify, "COMMIT", original), \
                         patch.object(verify, "BINARY_SHA256", verify.digest(binary)):
                        with self.assertRaisesRegex(ValueError, "dirty|differ"):
                            verify.inventory(source, binary, output)
                    self.assertFalse(output.exists())

    def test_replacement_ref_cannot_authenticate_junit_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, _, binary, original = self.inputs(root)
            junit = ComparatorTests.jar(root / "junit", {
                "JUnitCore.java": "package org.junit.runner; public class JUnitCore { public Result run(Class<?>[] classes) { return new Result(); } }",
                "Result.java": "package org.junit.runner; public class Result { public int getRunCount() { return 1; } public int getFailureCount() { return 0; } public int getIgnoreCount() { return 0; } public boolean wasSuccessful() { return true; } public java.util.List<String> getFailures() { return java.util.Collections.emptyList(); } }",
            })
            hamcrest = ComparatorTests.jar(root / "hamcrest", {"Stub.java": "public class Stub {}"})
            cache = root / "cache"
            deps = cache / "deps"
            deps.mkdir(parents=True)
            shutil.copyfile(junit, deps / "junit-4.13.1.jar")
            shutil.copyfile(hamcrest, deps / "hamcrest-core-1.3.jar")
            output = root / "run.json"
            with patch.object(verify, "COMMIT", original), \
                 patch.object(verify, "BINARY_SHA256", verify.digest(binary)), \
                 patch.object(verify, "EXPECTED_CASES", 1):
                with self.assertRaisesRegex(ValueError, "dirty|pinned source .*bytes differ"):
                    verify.execute(source, binary, cache, output)
            self.assertFalse(output.exists())

    def test_checkout_rejects_replacement_worktree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, _, _, original = self.inputs(root)
            cache = root / "cache"
            cache.mkdir()
            checkout = cache / "dyn4j-source"
            shutil.move(source, checkout)
            subprocess.run(["git", "-C", str(checkout), "remote", "add", "origin",
                            str(checkout)], check=True, capture_output=True)
            with patch.object(verify, "COMMIT", original):
                with self.assertRaisesRegex(SystemExit, "dirty|untracked"):
                    verify.checked_out_sources(cache)


class GitWorktreeIdentityTests(unittest.TestCase):
    def inputs(self, root):
        source = root / "source"
        production = source / "src/main/java"
        tests = source / "src/test/java"
        production.mkdir(parents=True)
        tests.mkdir(parents=True)
        for index in range(268):
            (production / f"P{index}.java").write_text(f"class P{index} {{}}\n")
        for index in range(199):
            (tests / f"T{index}.java").write_text(f"class T{index} {{}}\n")
        (tests / "T0.java").write_text("class T0 {} // @Test\n")
        archive = root / "sources.jar"
        with zipfile.ZipFile(archive, "w") as jar:
            for path in production.glob("*.java"):
                jar.write(path, path.name)
        git_env = {key: value for key, value in os.environ.items()
                   if not key.startswith("GIT_")}

        def git(*args, inherited=False):
            return subprocess.run(["git", "-C", str(source), *args], check=True,
                                  capture_output=True, text=True,
                                  env=os.environ.copy() if inherited else git_env).stdout.strip()

        git("init", "-q")
        git("add", "src")
        git("-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-qm", "original")
        revision = git("rev-parse", "HEAD")
        binary = ComparatorTests.jar(root / "binary", {"Api.java": "public class Api {}"})
        junit = ComparatorTests.jar(root / "junit", {
            "JUnitCore.java": "package org.junit.runner; public class JUnitCore { public Result run(Class<?>[] classes) { return new Result(); } }",
            "Result.java": "package org.junit.runner; public class Result { public int getRunCount() { return 1; } public int getFailureCount() { return 0; } public int getIgnoreCount() { return 0; } public boolean wasSuccessful() { return true; } public java.util.List<String> getFailures() { return java.util.Collections.emptyList(); } }",
        })
        hamcrest = ComparatorTests.jar(root / "hamcrest", {"Stub.java": "public class Stub {}"})
        cache = root / "cache"
        deps = cache / "deps"
        deps.mkdir(parents=True)
        shutil.copyfile(junit, deps / "junit-4.13.1.jar")
        shutil.copyfile(hamcrest, deps / "hamcrest-core-1.3.jar")
        return source, archive, binary, cache, revision, git

    def assert_all_gates_reject(self, root, source, archive, binary, cache, revision):
        with patch.object(verify, "COMMIT", revision), \
             patch.object(verify, "SOURCES_SHA256", verify.digest(archive)), \
             patch.object(verify, "BINARY_SHA256", verify.digest(binary)), \
             patch.object(verify, "EXPECTED_CASES", 1):
            with self.assertRaisesRegex(ValueError, "dirty|differ|bytes|regular file"):
                verify.verify_source_inputs(source, archive, revision)
            inventory_output = root / "inventory.json"
            with self.assertRaisesRegex(ValueError, "dirty|differ|bytes|regular file"):
                verify.inventory(source, binary, inventory_output)
            self.assertFalse(inventory_output.exists())
            run_output = root / "run.json"
            with self.assertRaisesRegex(ValueError, "dirty|differ|bytes|regular file"):
                verify.execute(source, binary, cache, run_output)
            self.assertFalse(run_output.exists())

    def test_redirected_worktree_cannot_hide_actual_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, archive, binary, cache, revision, git = self.inputs(root)
            alternate = root / "alternate"
            shutil.copytree(source / "src", alternate / "src")
            (source / "src/main/java/P0.java").write_text("class P0 { int changed; }\n")
            with patch.dict(os.environ, {"GIT_WORK_TREE": str(alternate)}):
                self.assertEqual(git("status", "--porcelain=v1", "--", "src",
                                     inherited=True), "")
                self.assertTrue(git("--work-tree", str(source), "status",
                                    "--porcelain=v1", "--", "src", inherited=True))
                self.assert_all_gates_reject(root, source, archive, binary, cache, revision)

    def test_assume_unchanged_production_cannot_hide_actual_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, archive, binary, cache, revision, git = self.inputs(root)
            git("update-index", "--assume-unchanged", "src/main/java/P0.java")
            (source / "src/main/java/P0.java").write_text("class P0 { int changed; }\n")
            self.assertEqual(git("status", "--porcelain=v1", "--", "src"), "")
            self.assert_all_gates_reject(root, source, archive, binary, cache, revision)

    def test_assume_unchanged_test_cannot_hide_actual_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, archive, binary, cache, revision, git = self.inputs(root)
            git("update-index", "--assume-unchanged", "src/test/java/T0.java")
            (source / "src/test/java/T0.java").write_text("class T0 {} // @Test @Test\n")
            self.assertEqual(git("status", "--porcelain=v1", "--", "src"), "")
            self.assert_all_gates_reject(root, source, archive, binary, cache, revision)

    def test_clean_assume_unchanged_files_remain_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, archive, binary, cache, revision, git = self.inputs(root)
            git("update-index", "--assume-unchanged", "src/main/java/P0.java",
                "src/test/java/T0.java")
            with patch.object(verify, "COMMIT", revision), \
                 patch.object(verify, "SOURCES_SHA256", verify.digest(archive)), \
                 patch.object(verify, "BINARY_SHA256", verify.digest(binary)), \
                 patch.object(verify, "EXPECTED_CASES", 1):
                self.assertTrue(verify.verify_source_inputs(source, archive, revision)["source_inputs_clean"])
                report = verify.inventory(source, binary, root / "inventory.json")
                self.assertEqual(report["test_annotations"], 1)
                run = verify.execute(source, binary, cache, root / "run.json")
                self.assertEqual(run["actual_executed_cases"], 1)

    def test_redirecting_git_environment_cannot_change_clean_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, archive, _, _, revision, _ = self.inputs(root)
            alternate = root / "alternate"
            alternate.mkdir()
            poison = {
                "GIT_DIR": str(alternate),
                "GIT_WORK_TREE": str(alternate),
                "GIT_COMMON_DIR": str(alternate),
                "GIT_INDEX_FILE": str(alternate / "index"),
                "GIT_OBJECT_DIRECTORY": str(alternate / "objects"),
                "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(alternate / "objects"),
                "GIT_NAMESPACE": "other",
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "core.worktree",
                "GIT_CONFIG_VALUE_0": str(alternate),
            }
            with patch.dict(os.environ, poison), \
                 patch.object(verify, "SOURCES_SHA256", verify.digest(archive)):
                self.assertTrue(verify.verify_source_inputs(source, archive, revision)["source_inputs_clean"])

    def test_source_check_rejects_worktree_change_during_archive_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, archive, _, _, revision, _ = self.inputs(root)
            target = source / "src/main/java/P0.java"
            original_open = verify.zipfile.ZipFile

            def change_after_open(*args, **kwargs):
                opened = original_open(*args, **kwargs)
                target.write_text("class P0 { int changed; }\n")
                return opened

            with patch.object(verify, "SOURCES_SHA256", verify.digest(archive)), \
                 patch.object(verify.zipfile, "ZipFile", side_effect=change_after_open):
                with self.assertRaisesRegex(ValueError, "dirty|pinned source bytes differ"):
                    verify.verify_source_inputs(source, archive, revision)

    def test_inventory_rejects_hidden_worktree_change_during_binary_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, _, binary, _, revision, git = self.inputs(root)
            target = source / "src/main/java/P0.java"
            git("update-index", "--assume-unchanged", "src/main/java/P0.java")
            original_inventory = verify.jar_types

            def change_after_binary_read(*args, **kwargs):
                result = original_inventory(*args, **kwargs)
                target.write_text("class P0 { int changed; }\n")
                return result

            output = root / "inventory.json"
            with patch.object(verify, "COMMIT", revision), \
                 patch.object(verify, "BINARY_SHA256", verify.digest(binary)), \
                 patch.object(verify, "jar_types", side_effect=change_after_binary_read):
                with self.assertRaisesRegex(ValueError, "pinned source bytes differ"):
                    verify.inventory(source, binary, output)
            self.assertFalse(output.exists())

    def test_symlinked_java_file_is_not_a_clean_regular_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, archive, binary, cache, revision, git = self.inputs(root)
            target = source / "src/main/java/P0.java"
            outside = root / "outside.java"
            outside.write_bytes(target.read_bytes())
            git("update-index", "--assume-unchanged", "src/main/java/P0.java")
            target.unlink()
            target.symlink_to(outside)
            self.assertEqual(git("status", "--porcelain=v1", "--", "src"), "")
            self.assert_all_gates_reject(root, source, archive, binary, cache, revision)

    def test_checkout_cannot_write_to_inherited_worktree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, _, _, _, original, git = self.inputs(root)
            newer = "class P0 { int newer; }\n"
            (source / "src/main/java/P0.java").write_text(newer)
            git("add", "src/main/java/P0.java")
            git("-c", "user.name=Test", "-c", "user.email=test@example.com",
                "commit", "-qm", "newer")
            cache = root / "checkout-cache"
            cache.mkdir()
            checkout = cache / "dyn4j-source"
            shutil.move(source, checkout)
            alternate = root / "alternate"
            shutil.copytree(checkout / "src", alternate / "src")
            subprocess.run(["git", "-C", str(checkout), "remote", "add", "origin",
                            str(checkout)], check=True, capture_output=True)
            with patch.object(verify, "COMMIT", original), \
                 patch.dict(os.environ, {"GIT_WORK_TREE": str(alternate)}):
                self.assertEqual(verify.checked_out_sources(cache), checkout)
            self.assertEqual((alternate / "src/main/java/P0.java").read_text(), newer)
            self.assertEqual((checkout / "src/main/java/P0.java").read_text(), "class P0 {}\n")


class BaselineRunIdentityTests(unittest.TestCase):
    @staticmethod
    def inputs(root):
        source = root / "source"
        test = source / "src/test/java/ExampleTest.java"
        test.parent.mkdir(parents=True)
        test.write_text('public class ExampleTest { static { System.out.println("ORIGINAL_MARKER"); } // @Test\n}\n')
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "add", "src"], check=True)
        subprocess.run(["git", "-C", str(source), "-c", "user.name=Test",
                        "-c", "user.email=test@example.com", "commit", "-qm", "fixture"], check=True)
        revision = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"],
                                  check=True, capture_output=True, text=True).stdout.strip()
        binary = ComparatorTests.jar(root / "binary", {"Api.java": "public class Api {}"})
        junit = ComparatorTests.jar(root / "junit", {
            "JUnitCore.java": "package org.junit.runner; public class JUnitCore { public Result run(Class<?>[] classes) { return new Result(); } }",
            "Result.java": "package org.junit.runner; public class Result { public int getRunCount() { return 1; } public int getFailureCount() { return 0; } public int getIgnoreCount() { return 0; } public boolean wasSuccessful() { return true; } public java.util.List<String> getFailures() { return java.util.Collections.emptyList(); } }",
        })
        hamcrest = ComparatorTests.jar(root / "hamcrest", {"Stub.java": "public class Stub {}"})
        cache = root / "cache"
        deps = cache / "deps"
        deps.mkdir(parents=True)
        junit_dest = deps / "junit-4.13.1.jar"
        shutil.copyfile(junit, junit_dest)
        shutil.copyfile(hamcrest, deps / "hamcrest-core-1.3.jar")
        return source, test, binary, cache, junit_dest, deps / "hamcrest-core-1.3.jar", revision

    def test_run_report_dependency_hash_identifies_executed_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, _, binary, cache, junit, hamcrest, revision = self.inputs(root)
            original_hash = verify.digest(junit)
            original_run = subprocess.run
            replaced = False

            def replace_after_test_run(command, *args, **kwargs):
                nonlocal replaced
                result = original_run(command, *args, **kwargs)
                if command[0] == "java" and "BaselineJUnitReport" in command and not replaced:
                    shutil.copyfile(hamcrest, junit)
                    replaced = True
                return result

            with patch.object(verify, "BINARY_SHA256", verify.digest(binary)):
                with patch.object(verify, "EXPECTED_CASES", 1):
                    with patch.object(verify, "COMMIT", revision):
                        with patch.object(verify.subprocess, "run", side_effect=replace_after_test_run):
                            report = verify.execute(source, binary, cache, root / "run.json")
            self.assertTrue(replaced)
            self.assertNotEqual(verify.digest(junit), original_hash)
            self.assertEqual(report["junit_sha256"], original_hash)
            self.assertIn("ORIGINAL_MARKER", report["output"])

    def test_run_rejects_source_changed_after_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, test, binary, cache, _, _, revision = self.inputs(root)
            original_hash = verify.digest(test)
            original_run = verify.run
            replaced = False

            def replace_before_compile(command, **kwargs):
                nonlocal replaced
                if command[0] == "javac" and not replaced:
                    test.write_text('public class ExampleTest { static { System.out.println("CHANGED_MARKER"); } // @Test\n}\n')
                    replaced = True
                return original_run(command, **kwargs)

            with patch.object(verify, "BINARY_SHA256", verify.digest(binary)):
                with patch.object(verify, "EXPECTED_CASES", 1):
                    with patch.object(verify, "COMMIT", revision):
                        with patch.object(verify, "run", side_effect=replace_before_compile):
                            with self.assertRaisesRegex(ValueError, "dirty|pinned source|source bytes"):
                                verify.execute(source, binary, cache, root / "run.json")
            self.assertTrue(replaced)
            self.assertNotEqual(verify.digest(test), original_hash)
            self.assertFalse((root / "run.json").exists())

    def test_run_report_rejects_source_outside_pinned_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, test, binary, cache, _, _, revision = self.inputs(root)
            test.write_text('public class ExampleTest { static { System.out.println("CHANGED_MARKER"); } // @Test\n}\n')
            with patch.object(verify, "BINARY_SHA256", verify.digest(binary)):
                with patch.object(verify, "COMMIT", revision):
                    with patch.object(verify, "EXPECTED_CASES", 1):
                        with self.assertRaisesRegex(ValueError, "dirty|pinned source"):
                            verify.execute(source, binary, cache, root / "run.json")


if __name__ == "__main__":
    unittest.main()
