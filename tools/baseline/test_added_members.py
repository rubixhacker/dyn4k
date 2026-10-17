import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.baseline import verify


SCRIPT = Path(__file__).with_name("verify.py")


def make_jar(root, sources, synthetic_method=None):
    root.mkdir()
    paths = []
    for name, source in sources.items():
        path = root / name
        path.write_text(source)
        paths.append(str(path))
    classes = root / "classes"
    classes.mkdir()
    subprocess.run(["javac", "--release", "8", "-d", str(classes), *paths],
                   check=True, capture_output=True)
    if synthetic_method:
        class_name, method_name = synthetic_method
        path = classes / (class_name + ".class")
        path.write_bytes(mark_synthetic(path.read_bytes(), method_name))
    archive = root / "library.jar"
    subprocess.run(["jar", "cf", str(archive), "-C", str(classes), "."],
                   check=True, capture_output=True)
    return archive


def mark_synthetic(binary, target):
    data = bytearray(binary)
    offset = 8
    count = struct.unpack_from(">H", data, offset)[0]
    offset += 2
    names = {}
    index = 1
    while index < count:
        tag = data[offset]
        offset += 1
        if tag == 1:
            size = struct.unpack_from(">H", data, offset)[0]
            offset += 2
            names[index] = data[offset:offset + size].decode()
            offset += size
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            offset += 4
        elif tag in (5, 6):
            offset += 8
            index += 1
        elif tag in (7, 8, 16, 19, 20):
            offset += 2
        elif tag == 15:
            offset += 3
        else:
            raise ValueError(f"unknown constant pool tag {tag}")
        index += 1
    offset += 6
    interfaces = struct.unpack_from(">H", data, offset)[0]
    offset += 2 + 2 * interfaces

    def skip_members(position):
        number = struct.unpack_from(">H", data, position)[0]
        position += 2
        for _ in range(number):
            position += 6
            attributes = struct.unpack_from(">H", data, position)[0]
            position += 2
            for _ in range(attributes):
                size = struct.unpack_from(">I", data, position + 2)[0]
                position += 6 + size
        return position

    offset = skip_members(offset)
    number = struct.unpack_from(">H", data, offset)[0]
    offset += 2
    found = False
    for _ in range(number):
        name = names[struct.unpack_from(">H", data, offset + 2)[0]]
        if name == target:
            flags = struct.unpack_from(">H", data, offset)[0]
            struct.pack_into(">H", data, offset, flags | 0x1000)
            found = True
        offset += 6
        attributes = struct.unpack_from(">H", data, offset)[0]
        offset += 2
        for _ in range(attributes):
            size = struct.unpack_from(">I", data, offset + 2)[0]
            offset += 6 + size
    if not found:
        raise ValueError(f"method {target} not found")
    return bytes(data)


def test_compare_command(baseline, candidate, *extra, fixture_hash=None):
    code = ("import sys; from tools.baseline import verify as v; "
            "v.BINARY_SHA256 = sys.argv.pop(1); ")
    if fixture_hash is not None:
        code += f"v.REQUIRED_FIXTURE_SHA256 = {{'test': {fixture_hash!r}}}; "
    code += "v.main()"
    return subprocess.run([sys.executable, "-c", code, verify.digest(baseline),
                           "compare", "--baseline-jar", str(baseline),
                           "--candidate", str(candidate), *map(str, extra)],
                            capture_output=True, text=True)


def compare(baseline, candidate):
    result = test_compare_command(baseline, candidate)
    return result, json.loads(result.stdout)


def compile_source(root, archive, source, label):
    path = root / "Consumer.java"
    path.write_text(source)
    output = root / label
    output.mkdir(exist_ok=True)
    return subprocess.run(["javac", "--release", "8", "-cp", str(archive),
                           "-d", str(output), str(path)], capture_output=True, text=True)


class AddedMemberTests(unittest.TestCase):
    def test_private_nested_members_do_not_create_external_source_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = make_jar(root / "baseline", {"World.java":
                "package p; public class World { private static class WarmStartHandler {} }"})
            candidate = make_jar(root / "candidate", {"World.java":
                "package p; public class World { private static class WarmStartHandler { public final String helper() { return null; } } }"})
            details = subprocess.run(["javap", "-p", "-v", "-cp", str(baseline),
                                      "p.World$WarmStartHandler"], check=True,
                                     capture_output=True, text=True).stdout
            self.assertIn("InnerClasses:\n  private", details)
            source = "package p; public class Consumer extends World { public String helper() { return null; } }"
            self.assertEqual(compile_source(root, baseline, source, "baseline-classes").returncode, 0)
            self.assertEqual(compile_source(root, candidate, source, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(report["added_member_risks"], [])
            omitted = make_jar(root / "omitted", {"World.java":
                "package p; public class World {}"})
            self.assertEqual(compile_source(root, omitted, source, "omitted-classes").returncode, 0)
            result, report = compare(baseline, omitted)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(report["inventory_errors"], [])

    def test_hyphenated_jvm_method_is_not_java_source_member(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = make_jar(root / "baseline", {"Api.java": "public class Api {}"})
            candidate = make_jar(root / "candidate", {"Api.java":
                "public class Api { public final String fooBarX() { return null; } }"})
            classes = root / "candidate/classes/Api.class"
            classes.write_bytes(classes.read_bytes().replace(b"fooBarX", b"foo-bar"))
            subprocess.run(["jar", "cf", str(candidate), "-C", str(classes.parent), "."],
                           check=True, capture_output=True)
            details = subprocess.run(["javap", "-p", "-cp", str(candidate), "Api"],
                                     check=True, capture_output=True, text=True).stdout
            self.assertIn("foo-bar()", details)
            source = "public class Consumer extends Api { public String fooBarX() { return null; } }"
            self.assertEqual(compile_source(root, baseline, source, "baseline-classes").returncode, 0)
            self.assertEqual(compile_source(root, candidate, source, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(report["added_member_risks"], [])

    def test_generated_java_identifiers_remain_source_risks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            other = "package q; public class Other { public static Object Companion = new Object(); public static Object getEntries() { return null; } }"
            baseline = make_jar(root / "baseline", {"Api.java": "package p; public class Api {}",
                                                     "Mode.java": "package p; public enum Mode { ONE; }",
                                                     "Other.java": other})
            candidate = make_jar(root / "candidate", {"Api.java":
                "package p; public class Api { public static Object Companion = new Object(); }",
                "Mode.java": "package p; public enum Mode { ONE; public static Object getEntries() { return null; } }",
                "Other.java": other})
            source = "import static p.Api.*; import static p.Mode.*; import static q.Other.*; public class Consumer { Object value = Companion; Object run() { return getEntries(); } }"
            self.assertEqual(compile_source(root, baseline, source, "baseline-classes").returncode, 0)
            self.assertNotEqual(compile_source(root, candidate, source, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertTrue(any("Companion" in item["declaration"] for item in report["added_member_risks"]))
            self.assertTrue(any("getEntries()" in item["declaration"] for item in report["added_member_risks"]))

    def test_duplicate_dependency_path_cannot_hide_two_snapshots_under_one_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = make_jar(root / "library", {"Api.java": "public final class Api {}"})
            dependency = make_jar(root / "dependency", {"Helper.java": "public class Helper {}"})
            with patch.object(verify, "BINARY_SHA256", verify.digest(archive)):
                report = verify.compare_jars(archive, archive, dependencies=[dependency, dependency])
            self.assertIn(f"duplicate dependency JAR: {dependency}", report["inventory_errors"])

    def test_dependency_replacement_cannot_change_reported_member_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = make_jar(root / "baseline", {
                "Parent.java": "public class Parent<T> {}",
                "Api.java": "public class Api extends Parent<String> {}",
            })
            candidate = root / "candidate.jar"
            subprocess.run(["jar", "cf", str(candidate), "-C",
                            str(root / "baseline/classes"), "Api.class"], check=True,
                           capture_output=True)
            dependency = make_jar(root / "dependency", {
                "Parent.java": "public class Parent<T> { public final String helper() { return \"new\"; } }",
            })
            replacement = root / "replacement.jar"
            subprocess.run(["jar", "cf", str(replacement), "-C",
                            str(root / "baseline/classes"), "Parent.class"], check=True,
                           capture_output=True)
            original_hash = verify.digest(dependency)
            replacement_hash = verify.digest(replacement)
            original_gate = verify.added_member_gate
            replaced = False

            def replace_before_member_lookup(*args, **kwargs):
                nonlocal replaced
                if not replaced:
                    shutil.copyfile(replacement, dependency)
                    replaced = True
                return original_gate(*args, **kwargs)

            with patch.object(verify, "BINARY_SHA256", verify.digest(baseline)):
                with patch.object(verify, "added_member_gate", side_effect=replace_before_member_lookup):
                    report = verify.compare_jars(baseline, candidate, only={"Api"},
                                                 dependencies=[dependency])
            self.assertTrue(replaced)
            self.assertNotEqual(original_hash, replacement_hash)
            self.assertEqual(verify.digest(dependency), replacement_hash)
            self.assertEqual(report["dependency_sha256"][str(dependency)], original_hash)
            self.assertTrue(any("helper()" in risk["declaration"]
                                for risk in report["added_member_risks"]))

    def test_fixture_replacement_cannot_change_compiled_source_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = make_jar(root / "baseline", {
                "Api.java": "public class Api { public String value() { return \"base\"; } }",
            })
            candidate = make_jar(root / "candidate", {
                "Api.java": "public class Api { public final String value() { return \"new\"; } }",
            })
            fixture = root / "Child.java"
            fixture.write_text("public class Child extends Api { @Override public String value() { return \"child\"; } }\n")
            approved_hash = verify.digest(fixture)
            original_run = subprocess.run
            replaced = False

            def replace_before_javac(command, *args, **kwargs):
                nonlocal replaced
                if command[0] == "javac" and not replaced:
                    fixture.write_text("public class Child {}\n")
                    replaced = True
                return original_run(command, *args, **kwargs)

            with patch.object(verify, "BINARY_SHA256", verify.digest(baseline)):
                with patch.object(verify, "REQUIRED_FIXTURE_SHA256", {"approved": approved_hash}):
                    with patch.object(verify.subprocess, "run", side_effect=replace_before_javac):
                        report = verify.compare_jars(baseline, candidate,
                                                     fixtures=[fixture], require_fixture=True)
            self.assertTrue(replaced)
            self.assertNotEqual(verify.digest(fixture), approved_hash)
            self.assertEqual(report["fixture_errors"], [])
            self.assertEqual(report["fixture_results"][0]["source_sha256"], approved_hash)
            self.assertEqual(report["fixture_results"][0]["baseline_exit_code"], 0)
            self.assertNotEqual(report["fixture_results"][0]["candidate_exit_code"], 0)
            self.assertEqual(report["fixture_failures"], [str(fixture)])

    def test_unrelated_required_fixture_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = make_jar(root / "library", {"Api.java": "public final class Api {}"})
            fixture = root / "Fixture.java"
            fixture.write_text("public class Fixture {}")
            results, failures, errors = verify.fixture_audit(
                archive, [fixture], True, str(archive))
            self.assertEqual(len(results), 1)
            self.assertEqual(failures, [])
            self.assertTrue(any("required" in error and "fixture" in error
                                for error in errors), errors)

    def test_compare_cli_rejects_unpinned_baseline_jar(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = make_jar(root / "library", {"Api.java": "public final class Api {}"})
            result = subprocess.run([sys.executable, str(SCRIPT), "compare", "--baseline-jar",
                                     str(archive), "--candidate", str(archive)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("baseline SHA-256", result.stderr)

    def test_comparison_function_rejects_unpinned_baseline_jar(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = make_jar(root / "library", {"Api.java": "public final class Api {}"})
            with self.assertRaisesRegex(ValueError, "baseline SHA-256"):
                verify.compare_jars(archive, archive)

    def test_new_final_override_of_inherited_generic_method_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = {"Parent.java":
                      "public class Parent<T> { public T value() { return null; } }"}
            baseline = make_jar(root / "baseline", {**shared,
                "Api.java": "public class Api extends Parent<String> {}"})
            candidate = make_jar(root / "candidate", {**shared,
                "Api.java": "public class Api extends Parent<String> { @Override public final String value() { return \"x\"; } }"})
            source = "public class Consumer extends Api { @Override public String value() { return \"child\"; } }"
            self.assertEqual(compile_source(root, baseline, source, "baseline-classes").returncode, 0)
            self.assertNotEqual(compile_source(root, candidate, source, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertTrue(any(risk["candidate_type"] == "Api" and
                                "final" in risk["declaration"] and "value()" in risk["declaration"]
                                for risk in report["added_member_risks"]))

    def test_new_field_hiding_inherited_constant_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = {"Parent.java": "public class Parent { public static final int KEY = 1; }"}
            baseline = make_jar(root / "baseline", {**shared,
                "Api.java": "public class Api extends Parent {}"})
            candidate = make_jar(root / "candidate", {**shared,
                "Api.java": "public class Api extends Parent { public static int KEY = 2; }"})
            source = "public class Consumer { int run(int x) { switch (x) { case Api.KEY: return 1; default: return 0; } } }"
            self.assertEqual(compile_source(root, baseline, source, "baseline-classes").returncode, 0)
            self.assertNotEqual(compile_source(root, candidate, source, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertTrue(any(risk["candidate_type"] == "Api" and
                                risk["kind"] == "field" and "KEY" in risk["declaration"]
                                for risk in report["added_member_risks"]))

    def test_final_type_ambiguous_added_overload_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = make_jar(root / "baseline", {"Api.java":
                "public final class Api { public String value(String input) { return input; } }"})
            candidate = make_jar(root / "candidate", {"Api.java":
                "public final class Api { public String value(String input) { return input; } public String value(Integer input) { return null; } }"})
            source = "public class Consumer { String run(Api api) { return api.value(null); } }"
            self.assertEqual(compile_source(root, baseline, source, "baseline-classes").returncode, 0)
            self.assertNotEqual(compile_source(root, candidate, source, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertTrue(any("value(java.lang.Integer)" in risk["declaration"]
                                for risk in report["added_member_risks"]))

    def test_final_type_added_static_field_can_ambiguous_wildcard_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = {"Other.java": "package q; public final class Other { public static final int PIN = 1; }"}
            baseline = make_jar(root / "baseline", {**shared,
                "Api.java": "package p; public final class Api {}"})
            candidate = make_jar(root / "candidate", {**shared,
                "Api.java": "package p; public final class Api { public static final int PIN = 2; }"})
            source = "import static p.Api.*; import static q.Other.*; public class Consumer { int value = PIN; }"
            self.assertEqual(compile_source(root, baseline, source, "baseline-classes").returncode, 0)
            self.assertNotEqual(compile_source(root, candidate, source, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertTrue(any(risk["candidate_type"] == "p.Api" and
                                risk["kind"] == "field" and "PIN" in risk["declaration"]
                                for risk in report["added_member_risks"]))

    def test_package_private_type_same_package_extension_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = make_jar(root / "baseline", {"Api.java": "package p; class Api {}"})
            candidate = make_jar(root / "candidate", {"Api.java":
                "package p; class Api { public final String helper() { return \"api\"; } }"})
            source = "package p; public class Consumer extends Api { public String helper() { return \"child\"; } }"
            self.assertEqual(compile_source(root, baseline, source, "baseline-classes").returncode, 0)
            self.assertNotEqual(compile_source(root, candidate, source, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertTrue(any(risk["candidate_type"] == "p.Api" and
                                "helper()" in risk["declaration"]
                                for risk in report["added_member_risks"]))

    def test_missing_package_private_type_fails_same_package_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = make_jar(root / "baseline", {"Api.java": "package p; class Api {}"})
            candidate = make_jar(root / "candidate", {"Other.java": "package p; public class Other {}"})
            source = "package p; public class Consumer extends Api {}"
            self.assertEqual(compile_source(root, baseline, source, "baseline-classes").returncode, 0)
            self.assertNotEqual(compile_source(root, candidate, source, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertTrue(any("p.Api" in error for error in report["inventory_errors"]))

    def test_anonymous_and_package_info_classes_are_not_source_types(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = make_jar(root / "baseline", {
                "Api.java": "package p; public class Api { public Runnable helper = new Runnable() { public void run() {} }; }",
                "package-info.java": "@Deprecated package p;",
            })
            candidate = make_jar(root / "candidate", {"Api.java":
                "package p; public class Api { public Runnable helper = null; }"})
            source = "package p; public class Consumer { Runnable value = new Api().helper; }"
            self.assertEqual(compile_source(root, baseline, source, "baseline-classes").returncode, 0)
            self.assertEqual(compile_source(root, candidate, source, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(report["inventory_errors"], [])

    def test_six_baseline_valid_helpers_expose_declared_and_inherited_additions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = {
                "Epa.java": "public class Epa {}",
                "BaseWorld.java": "public class BaseWorld<T> {}",
                "World.java": "public class World<T> extends BaseWorld<T> {}",
                "Rotation.java": "public class Rotation { protected double cost; }",
                "Force.java": "public class Force {}",
                "DetectResult.java": "public class DetectResult<T> {}",
                "VertexClusterReduction.java": "public class VertexClusterReduction {}",
            }
            after = dict(before)
            after.update({
                "Epa.java": "public class Epa { protected final int maxIterationsField() { return 1; } }",
                "BaseWorld.java": "public class BaseWorld<T> { protected final T settingsField() { return null; } }",
                "Rotation.java": "public class Rotation { protected double cost; public double costValue() { return cost; } }",
                "Force.java": "public class Force { public final Object rawForce$io_github_rubixhacker_dyn4k_core() { return null; } }",
                "DetectResult.java": "public class DetectResult<T> { protected final T bodyField() { return null; } }",
                "VertexClusterReduction.java": "public class VertexClusterReduction { public double getClusterTolerance() { return 0; } }",
            })
            baseline = make_jar(root / "baseline", before)
            candidate = make_jar(root / "candidate", after)
            consumer = "public class Consumer { static class Detector extends Epa { public String maxIterationsField() { return \"x\"; } } static class Simulation extends World<String> { public String settingsField() { return \"x\"; } } static class Turn extends Rotation { public String costValue() { return \"x\"; } } static class AppliedForce extends Force { public String rawForce$io_github_rubixhacker_dyn4k_core() { return \"x\"; } } static class Detection extends DetectResult<String> { public String bodyField() { return \"x\"; } } static class Simplifier extends VertexClusterReduction { public String getClusterTolerance() { return \"x\"; } } }"
            self.assertEqual(compile_source(root, baseline, consumer, "baseline-classes").returncode, 0)
            self.assertNotEqual(compile_source(root, candidate, consumer, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            risks = report["added_member_risks"]
            for name in ("maxIterationsField", "settingsField", "costValue",
                         "rawForce$io_github_rubixhacker_dyn4k_core", "bodyField",
                         "getClusterTolerance"):
                self.assertTrue(any(name in item["declaration"] for item in risks), name)
            inherited = [item for item in risks if item["candidate_type"] == "World"
                         and "settingsField" in item["declaration"]]
            self.assertEqual(len(inherited), 1)
            self.assertEqual(inherited[0]["declaring_type"], "BaseWorld")

    def test_added_constructor_null_ambiguity_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = make_jar(root / "baseline", {"CopyException.java":
                "public class CopyException extends RuntimeException { public CopyException(Class<?> source, Class<?> copy) {} }"})
            candidate = make_jar(root / "candidate", {"CopyException.java":
                "public class CopyException extends RuntimeException { public CopyException(Class<?> source, Class<?> copy) {} public CopyException(String source, String copy) {} }"})
            source = "public class Consumer { CopyException make() { return new CopyException(null, null); } }"
            self.assertEqual(compile_source(root, baseline, source, "baseline-classes").returncode, 0)
            self.assertNotEqual(compile_source(root, candidate, source, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertTrue(any("CopyException(java.lang.String, java.lang.String)" in item["declaration"]
                                for item in report["added_member_risks"]))

    def test_package_method_field_name_and_static_hiding_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = {"Api.java": "package p; public class Api { protected int value; }"}
            after = {"Api.java": "package p; public class Api { protected int value; int value() { return 1; } public static final int count() { return 1; } }"}
            baseline = make_jar(root / "baseline", before)
            candidate = make_jar(root / "candidate", after)
            source = "package p; public class Consumer extends Api { String value() { return \"x\"; } public static int count() { return 2; } }"
            self.assertEqual(compile_source(root, baseline, source, "baseline-classes").returncode, 0)
            self.assertNotEqual(compile_source(root, candidate, source, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertTrue(any("value()" in item["declaration"] for item in report["added_member_risks"]))
            self.assertTrue(any("count()" in item["declaration"] for item in report["added_member_risks"]))

    def test_final_type_private_and_harmless_overload_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = make_jar(root / "baseline", {"Api.java":
                "public final class Api { public int value() { return 1; } }"})
            candidate = make_jar(root / "candidate", {"Api.java":
                "public final class Api { public int value() { return 1; } public int value(int n) { return n; } private int helper() { return 2; } }"})
            source = "public class Consumer { int run(Api api) { return api.value(); } }"
            self.assertEqual(compile_source(root, baseline, source, "baseline-classes").returncode, 0)
            self.assertEqual(compile_source(root, candidate, source, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(report["added_member_risks"], [])

    def test_private_helper_in_subclassable_type_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = make_jar(root / "baseline", {"Api.java": "public class Api {}"})
            candidate = make_jar(root / "candidate", {"Api.java":
                "public class Api { private int helper() { return 1; } }"})
            source = "public class Consumer extends Api { public String helper() { return \"ok\"; } }"
            self.assertEqual(compile_source(root, baseline, source, "baseline-classes").returncode, 0)
            self.assertEqual(compile_source(root, candidate, source, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(report["added_member_risks"], [])

    def test_synthetic_helper_hides_source_but_not_runtime_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = make_jar(root / "baseline", {"Api.java": "public class Api {}"})
            candidate = make_jar(root / "candidate", {"Api.java":
                "public class Api { public final String helper() { return \"api\"; } }"},
                synthetic_method=("Api", "helper"))
            details = subprocess.run(["javap", "-v", "-p", "-cp", str(candidate), "Api"],
                                     check=True, capture_output=True, text=True).stdout
            self.assertIn("ACC_PUBLIC, ACC_FINAL, ACC_SYNTHETIC", details)
            source = "public class Consumer extends Api { public String helper() { return \"child\"; } public static void main(String[] args) { System.out.println(new Consumer().helper()); } }"
            self.assertEqual(compile_source(root, baseline, source, "baseline-classes").returncode, 0)
            self.assertEqual(compile_source(root, candidate, source, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(report["added_member_risks"], [])
            runtime = subprocess.run(["java", "-cp", str(root / "baseline-classes") + ":" +
                                      str(candidate), "Consumer"], capture_output=True, text=True)
            self.assertNotEqual(runtime.returncode, 0)
            self.assertIn("IncompatibleClassChangeError", runtime.stderr)

    def test_inherited_generic_override_is_not_an_added_method(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = make_jar(root / "baseline", {
                "Parent.java": "public class Parent<T> { public T value() { return null; } }",
                "Api.java": "public class Api extends Parent<String> {}",
            })
            candidate = make_jar(root / "candidate", {
                "Parent.java": "public class Parent<T> { public T value() { return null; } }",
                "Api.java": "public class Api extends Parent<String> { @Override public String value() { return \"ok\"; } }",
            })
            source = "public class Consumer extends Api { @Override public String value() { return \"child\"; } }"
            self.assertEqual(compile_source(root, baseline, source, "baseline-classes").returncode, 0)
            self.assertEqual(compile_source(root, candidate, source, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(any("value()" in item["declaration"]
                                 for item in report["added_member_risks"]))

    def test_required_fixture_cannot_be_skipped_or_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = make_jar(root / "baseline", {"Api.java": "public final class Api {}"})
            candidate = make_jar(root / "candidate", {"Api.java": "public final class Api {}"})
            skipped = test_compare_command(baseline, candidate, "--require-fixture")
            self.assertEqual(skipped.returncode, 1)
            self.assertIn("skipped", json.loads(skipped.stdout)["fixture_errors"][0])
            missing = test_compare_command(baseline, candidate, "--require-fixture",
                                           "--fixture", root / "missing.java")
            self.assertEqual(missing.returncode, 1)
            self.assertIn("missing", json.loads(missing.stdout)["fixture_errors"][0])
            empty = root / "empty.java"
            empty.write_text("")
            no_source = test_compare_command(baseline, candidate, "--require-fixture",
                                             "--fixture", empty)
            self.assertEqual(no_source.returncode, 1)
            self.assertIn("empty", json.loads(no_source.stdout)["fixture_errors"][0])
            fixture = root / "Consumer.java"
            fixture.write_text("public class Consumer { Api value; }")
            present = test_compare_command(baseline, candidate, "--require-fixture",
                                           "--fixture", fixture,
                                           fixture_hash=verify.digest(fixture))
            self.assertEqual(present.returncode, 0, present.stdout + present.stderr)
            self.assertEqual(len(json.loads(present.stdout)["fixture_results"]), 1)

    def test_empty_candidate_inventory_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = make_jar(root / "baseline", {"Api.java": "public class Api {}"})
            empty = root / "empty"
            empty.mkdir()
            candidate = root / "empty.jar"
            subprocess.run(["jar", "cf", str(candidate), "-C", str(empty), "."],
                           check=True, capture_output=True)
            result = test_compare_command(baseline, candidate)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("empty baseline or candidate class-file inventory", result.stderr)

    def test_package_constructor_inventory_is_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = {"Api.java": "package p; public class Api { Api() {} }"}
            baseline = make_jar(root / "baseline", source)
            candidate = make_jar(root / "candidate", source)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(report["inventory_errors"], [])

    def test_method_type_parameter_does_not_inherit_class_substitution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = {"Parent.java":
                      "public class Parent<T> { public <T> T convert(T value) { return value; } }"}
            baseline = make_jar(root / "baseline", {**shared,
                "Api.java": "public class Api extends Parent<String> {}"})
            candidate = make_jar(root / "candidate", {**shared,
                "Api.java": "public class Api extends Parent<String> { public final String convert(String value) { return value; } }"})
            source = "public class Consumer extends Api { public String convert(String value) { return value; } }"
            self.assertEqual(compile_source(root, baseline, source, "baseline-classes").returncode, 0)
            self.assertNotEqual(compile_source(root, candidate, source, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertTrue(any("convert(java.lang.String)" in item["declaration"]
                                for item in report["added_member_risks"]))

    def test_method_type_parameter_preserves_unshadowed_class_substitution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = make_jar(root / "baseline", {
                "Parent.java": "public class Parent<T> { public <U> T convert(U value) { return null; } }",
                "Api.java": "public class Api extends Parent<String> {}",
            })
            candidate = make_jar(root / "candidate", {
                "Parent.java": "public class Parent<T> { public <U> T convert(U value) { return null; } }",
                "Api.java": "public class Api extends Parent<String> { @Override public <U> String convert(U value) { return \"ok\"; } }",
            })
            source = "public class Consumer extends Api { @Override public <U> String convert(U value) { return \"child\"; } }"
            self.assertEqual(compile_source(root, baseline, source, "baseline-classes").returncode, 0)
            self.assertEqual(compile_source(root, candidate, source, "candidate-classes").returncode, 0)
            result, report = compare(baseline, candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(any("convert(" in item["declaration"]
                                 for item in report["added_member_risks"]))


if __name__ == "__main__":
    unittest.main()
