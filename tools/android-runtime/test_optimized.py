import unittest
import tempfile
from pathlib import Path

import optimized_evidence
import run_optimized


CASE = "io.github.rubixhacker.dyn4k.optimized.OptimizedJourneyTest#appSideWorldAndSubclassCallbacks"
RAW = "\n".join((
    "INSTRUMENTATION_STATUS: class=io.github.rubixhacker.dyn4k.optimized.OptimizedJourneyTest",
    "INSTRUMENTATION_STATUS: test=appSideWorldAndSubclassCallbacks",
    "INSTRUMENTATION_STATUS_CODE: 1",
    "INSTRUMENTATION_STATUS: class=io.github.rubixhacker.dyn4k.optimized.OptimizedJourneyTest",
    "INSTRUMENTATION_STATUS: test=appSideWorldAndSubclassCallbacks",
    "INSTRUMENTATION_STATUS_CODE: 0",
    "INSTRUMENTATION_RESULT: stream=",
    "OK (1 test)",
    "INSTRUMENTATION_CODE: -1",
    "",
))
PROVIDER = "io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1\nio.github.rubixhacker:dyn4k-core-android:0.1.0-alpha.1\n"
MAPPING = "\n".join((
    "io.github.rubixhacker.dyn4k.optimized.OptimizedConsumer$CountingWorld -> a:",
    "    1:2:java.lang.String io.github.rubixhacker.dyn4k.optimized.OptimizedConsumer.run():42:42 -> x",
    "org.dyn4j.geometry.Vector2 -> b:",
    "org.dyn4j.dynamics.Body -> c:",
    "org.dyn4j.world.World -> R8$$REMOVED$$CLASS$$16:",
))
USAGE = "org.dyn4j.geometry.CircleDetector\nio.github.rubixhacker.dyn4k.optimized.OptimizedConsumer\n"
DEX = {"La;", "Lb;", "Lc;"}


class OptimizedEvidenceTest(unittest.TestCase):
    def test_accepts_installed_app_case_and_narrow_r8_evidence(self):
        optimized_evidence.validate_installed_case(RAW, 0, CASE)
        optimized_evidence.validate_provider(PROVIDER)
        optimized_evidence.validate_r8("-keep class io.github.rubixhacker.dyn4k.optimized.OptimizedActivity { *; }\n",
                                           MAPPING, USAGE, DEX)

    def test_rejects_zero_executed_tests(self):
        with self.assertRaises(ValueError):
            optimized_evidence.validate_installed_case("OK (0 tests)\nINSTRUMENTATION_CODE: -1\n", 0, CASE)

    def test_rejects_wrong_provider(self):
        with self.assertRaisesRegex(ValueError, "provider"):
            optimized_evidence.validate_provider(PROVIDER + "org.dyn4j:dyn4j:6.0.0\n")

    def test_rejects_engine_wide_keep_rules(self):
        with self.assertRaisesRegex(ValueError, "broad keep"):
            optimized_evidence.validate_r8("-keep class org.dyn4j.** { *; }\n", MAPPING, USAGE, DEX)

    def test_rejects_engine_and_facade_subtree_keep_rules(self):
        for rule in ("-keep class org.dyn4j.geometry.** { *; }\n",
                     "-keep class org.dyn4j.world.collision.** { *; }\n",
                     "-keep class io.github.rubixhacker.dyn4k.geometry.** { *; }\n"):
            with self.subTest(rule=rule), self.assertRaisesRegex(ValueError, "broad keep"):
                optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_rejects_access_modified_package_keep_rules(self):
        narrow = "-keep class io.github.rubixhacker.dyn4k.optimized.OptimizedActivity { public <init>(); public void onCreate(android.os.Bundle); }\n"
        optimized_evidence.validate_r8(narrow, MAPPING, USAGE, DEX)
        for rule in ("-keep public class org.dyn4j.geometry.** { *; }\n",
                     "-keep public class io.github.rubixhacker.dyn4k.geometry.** { *; }\n",
                     "-keep,allowoptimization public class org.dyn4j.world.collision.** { *; }\n",
                     "-keep,allowoptimization public final class io.github.rubixhacker.dyn4k.geometry.** { *; }\n"):
            with self.subTest(rule=rule), self.assertRaisesRegex(ValueError, "broad keep"):
                optimized_evidence.validate_r8(narrow + rule, MAPPING, USAGE, DEX)

    def test_rejects_interface_and_enum_subtree_keeps(self):
        for targeted in ("-keep class io.github.rubixhacker.dyn4k.optimized.OptimizedActivity { public <init>(); }\n",
                         "-keep public interface org.dyn4j.world.PhysicsWorld { *; }\n",
                         "-keep enum org.dyn4j.geometry.MassType { *; }\n"):
            with self.subTest(targeted=targeted):
                optimized_evidence.validate_r8(targeted, MAPPING, USAGE, DEX)
        for rule in ("-keep interface org.dyn4j.** { *; }\n",
                     "-keep public interface org.dyn4j.** { *; }\n",
                     "-keep public interface io.github.rubixhacker.dyn4k.** { *; }\n",
                     "  -keep,allowoptimization\tpublic interface org.dyn4j.world.** { *; }\n",
                     "-keep\tpublic\tinterface\tio.github.rubixhacker.dyn4k.geometry.** { *; }\n",
                     "-keep enum org.dyn4j.** { *; }\n",
                     "-keep,allowoptimization  enum  io.github.rubixhacker.dyn4k.geometry.** { *; }\n"):
            with self.subTest(rule=rule), self.assertRaisesRegex(ValueError, "broad keep"):
                optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_rejects_annotation_and_member_package_keeps(self):
        for rule in ("-keep @interface org.dyn4j.** { *; }\n",
                     "-keep @interface io.github.rubixhacker.dyn4k.** { *; }\n",
                     "-keepclassmembers class org.dyn4j.** { *; }\n",
                     "-keepclassmembers class io.github.rubixhacker.dyn4k.** { *; }\n"):
            with self.subTest(rule=rule), self.assertRaisesRegex(ValueError, "broad keep"):
                optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_rejects_broad_class_member_and_name_directives(self):
        for directive in ("keep", "keepclassmembers", "keepclasseswithmembers", "keepnames",
                          "keepclassmembernames", "keepclasseswithmembernames"):
            for selector in ("org.dyn4j.**", "org.dyn4j.geometry.*",
                             "io.github.rubixhacker.dyn4k.**", "io.github.rubixhacker.dyn4k.optimized.*",
                             "kotlin.**"):
                rule = f"-{directive},allowoptimization public @interface {selector} {{ *; }}\n"
                with self.subTest(rule=rule), self.assertRaisesRegex(ValueError, "broad keep"):
                    optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_rejects_global_star_class_selectors(self):
        with self.assertRaisesRegex(ValueError, "broad keep"):
            optimized_evidence.validate_r8("-keep class * { *; }\n", MAPPING, USAGE, DEX)
        for directive in ("keep", "keepclassmembers", "keepclasseswithmembers", "keepnames",
                          "keepclassmembernames", "keepclasseswithmembernames"):
            for kind in ("class", "interface", "enum", "@interface"):
                rule = f"-{directive},allowoptimization public {kind} * {{ *; }}\n"
                with self.subTest(rule=rule), self.assertRaisesRegex(ValueError, "broad keep"):
                    optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_accepts_metadata_and_path_options(self):
        for rule in ("-keepattributes **\n", "-keepdirectories **\n",
                     "-keeppackagenames org.dyn4j.**\n", "-keepparameternames\n"):
            with self.subTest(rule=rule):
                optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_rejects_negated_class_selectors(self):
        for directive in ("keep", "keepclassmembers", "keepclasseswithmembers",
                          "keepnames", "keepclassmembernames", "keepclasseswithmembernames"):
            for selector in ("!android.**", "!io.github.rubixhacker.dyn4k.optimized.OptimizedActivity"):
                rule = f"-{directive} class {selector} {{ *; }}\n"
                with self.subTest(rule=rule), self.assertRaisesRegex(ValueError, "broad keep"):
                    optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_rejects_global_field_wildcards_in_member_families(self):
        for directive in ("keepclassmembers", "keepclasseswithmembers",
                          "keepclassmembernames", "keepclasseswithmembernames"):
            for member in ("*** *;", "% *;", "public *** *;"):
                rule = f"-{directive} class * {{ {member} }}\n"
                with self.subTest(rule=rule), self.assertRaisesRegex(ValueError, "broad keep"):
                    optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_rejects_multiline_field_and_method_wildcards(self):
        for member in ("public *** *;", "protected % *;", "public void *(...);",
                       "private *** get*(...);"):
            rule = f"-keepclassmembers,allowoptimization\n class *\n {{\n   {member}\n }}\n"
            with self.subTest(member=member), self.assertRaisesRegex(ValueError, "broad keep"):
                optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_rejects_global_member_type_wildcards_with_exact_names(self):
        for member in ("% x;", "public *** x;", "*** onCreate();"):
            rule = f"-keepclassmembers class * {{ {member} }}\n"
            with self.subTest(member=member), self.assertRaisesRegex(ValueError, "broad keep"):
                optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_accepts_generated_enum_member_type_wildcards(self):
        rule = "-keepclassmembers enum * { public static **[] values(); public static ** valueOf(java.lang.String); }\n"
        optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_rejects_same_line_conditional_and_following_keep(self):
        activity = "io.github.rubixhacker.dyn4k.optimized.OptimizedActivity"
        rules = (
            f"-if class {activity} -keep class org.dyn4j.** {{ *; }}",
            f"-if class {activity} -keepclassmembers class * {{ *** *; }}",
            f"-keep class {activity} {{ <init>(); }} -keepclassmembers class * {{ *** *; }}",
        )
        for rule in rules:
            with self.subTest(rule=rule), self.assertRaisesRegex(ValueError, "broad keep"):
                optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_rejects_same_line_keep_variants_after_complete_block(self):
        activity = "io.github.rubixhacker.dyn4k.optimized.OptimizedActivity"
        narrow = f"-keep class {activity} {{ <init>(); }}"
        for kind in ("class", "interface", "enum", "@interface"):
            for selector in ("org.dyn4j.**", "io.github.rubixhacker.dyn4k.**", "*"):
                rule = f"{narrow} -keep,allowoptimization public {kind} {selector} {{ *; }}"
                with self.subTest(rule=rule), self.assertRaisesRegex(ValueError, "broad keep"):
                    optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)
        for join in ("\n", " ", ""):
            rule = f"{narrow}{join}-keepclassmembers class * {{ *** *; }}"
            with self.subTest(join=join), self.assertRaisesRegex(ValueError, "broad keep"):
                optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)
        for prefix in ("-keepattributes Signature ", "-dontwarn android.** "):
            rule = prefix + "-keepclassmembers class * { *** *; }"
            with self.subTest(prefix=prefix), self.assertRaisesRegex(ValueError, "broad keep"):
                optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_accepts_narrow_same_line_conditional_and_comments(self):
        activity = "io.github.rubixhacker.dyn4k.optimized.OptimizedActivity"
        rule = (f"# -keep class org.dyn4j.** {{ *; }}\n"
                f"-if class {activity} -keep class {activity} {{ <init>(); }} "
                f"-keepattributes Signature # -keepclassmembers class * {{ *** *; }}\n")
        optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_parses_complete_conditional_member_block_before_consequent(self):
        activity = "io.github.rubixhacker.dyn4k.optimized.OptimizedActivity"
        condition = f"-if class {activity} {{ public <init>(); }}"
        narrow = f"-keep class {activity} {{ <init>(); }}"
        for join in (" ", "\n", ""):
            with self.subTest(join=join):
                optimized_evidence.validate_r8(condition + join + narrow, MAPPING, USAGE, DEX)
                with self.assertRaisesRegex(ValueError, "broad keep"):
                    optimized_evidence.validate_r8(
                        condition + join + "-keepclassmembers class * { *** *; }", MAPPING, USAGE, DEX)

    def test_rejects_ambiguous_or_incomplete_effective_blocks(self):
        activity = "io.github.rubixhacker.dyn4k.optimized.OptimizedActivity"
        for rule in (f"-if class {activity}",
                     f"-keep class {activity} {{ <init>();",
                     f"-keep class {activity} {{ <init>(); {{ }}",
                     f"-keep class {activity} {{ <init>(); }} trailing",
                     f"-keep class {activity} {{ bogus int field; }}",
                     "-keepattributes Signature { -keepclassmembers class * { *** *; } }",
                     f"-keepclassmembers class * {{ public void exact(); }} -if class {activity}"):
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_rejects_enum_wildcard_user_overloads(self):
        for member in ("public static *** values(...);", "public static *** valueOf(...);",
                       "public static *** values();", "public static **[] values(int);",
                       "public static **[] values(...);", "public static ** valueOf(...);",
                       "public static ** valueOf(int);", "public static **[] valueOf(java.lang.String);",
                       "public static int values(int);", "public static int valueOf(int);"):
            rule = f"-keepclassmembers enum * {{ {member} }}"
            with self.subTest(member=member), self.assertRaisesRegex(ValueError, "broad keep"):
                optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_rejects_global_selectors_with_engine_ancestry_or_broad_members(self):
        for rule in ("-keep class * extends org.dyn4j.world.World { *; }\n",
                     "-keep @org.dyn4j.JvmFieldBridge class * { *; }\n",
                     "-keepclassmembers class * { public int exact; *; }\n",
                     "-keepclassmembers class * { <methods>; }\n",
                     "-keepclassmembers class * { public void *(); }\n"):
            with self.subTest(rule=rule), self.assertRaisesRegex(ValueError, "broad keep"):
                optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_accepts_exact_class_with_wildcard_annotation_filter(self):
        optimized_evidence.validate_r8("-keep @* class org.dyn4j.geometry.Vector2 { *; }\n",
                                       MAPPING, USAGE, DEX)

    def test_fails_closed_on_unsupported_effective_selectors(self):
        for rule in ("-keepfuture class org.dyn4j.geometry.Vector2 { *; }\n",
                     "-keep class { *; }\n",
                     "-keep class org.dyn4j.geometry.Vector2 Broken { *; }\n",
                     "-keepclassmembers class *\n"):
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_rejects_multiline_global_member_blanket(self):
        rule = "-keepclassmembers,allowoptimization\n public class\n *\n { *; }\n"
        with self.assertRaisesRegex(ValueError, "broad keep"):
            optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_rejects_multiline_and_parent_namespace_wildcards(self):
        for rule in ("-keepclassmembers,allowoptimization\n  public @interface\n  org.dyn4j.** { *; }\n",
                     "-keepclasseswithmembers\tclass\n  io.github.rubixhacker.dyn4k.**\n  { *; }\n",
                     "-keep class org.** { *; }\n",
                     "-keep class io.github.** { *; }\n",
                     "-keepclassmembers class **.geometry.* { *; }\n",
                     "-keep class org.**.geometry.* { *; }\n",
                     "-keep class ** { *; }\n"):
            with self.subTest(rule=rule), self.assertRaisesRegex(ValueError, "broad keep"):
                optimized_evidence.validate_r8(rule, MAPPING, USAGE, DEX)

    def test_accepts_comments_warnings_and_targeted_keeps(self):
        configuration = "\n".join((
            "# -keep class org.dyn4j.** { *; }",
            "-dontwarn org.dyn4j.** # -keepclassmembers class org.dyn4j.** { *; }",
            "-keep class io.github.rubixhacker.dyn4k.optimized.OptimizedActivity { public <init>(); }",
            "-keep public interface org.dyn4j.world.PhysicsWorld { *; }",
            "-keep enum org.dyn4j.geometry.MassType { *; }",
            "-keep @interface org.dyn4j.JvmFieldBridge { *; }",
            "-keepclassmembers class org.dyn4j.geometry.Vector2 { *; }",
            "-keep @android.support.annotation.Keep class * { *; }",
            "-keepclassmembers enum * { public static **[] values(); }",
            "-keepattributes **",
            "",
        ))
        optimized_evidence.validate_r8(configuration, MAPPING, USAGE, DEX)

    def test_rejects_missing_mapping_usage_or_bytecode(self):
        for mapping, usage, dex in (("", USAGE, DEX), (MAPPING, "", DEX),
                                    (MAPPING, USAGE, set()),
                                    (MAPPING.replace("org.dyn4j.world.World -> R8$$REMOVED$$CLASS$$16:", ""), USAGE, DEX),
                                    (MAPPING.replace("OptimizedConsumer.run()", "OptimizedConsumer.missing()"), USAGE, DEX)):
            with self.subTest(mapping=mapping, usage=usage, dex=dex), self.assertRaises(ValueError):
                optimized_evidence.validate_r8("-keep class io.github.rubixhacker.dyn4k.optimized.OptimizedActivity { *; }\n",
                                               mapping, usage, dex)

    def test_snapshot_rejects_changed_build_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "mapping.txt"
            snapshot = Path(directory) / "retained-mapping.txt"
            source.write_text(MAPPING)
            with self.assertRaisesRegex(ValueError, "changed"):
                run_optimized.snapshot_artifact(source, snapshot, "0" * 64)
            self.assertFalse(snapshot.exists())
