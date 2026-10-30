package io.github.rubixhacker.harness.android

import de.infix.testBalloon.framework.core.testSuite
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

private const val OPTIMIZED_CASE =
    "io.github.rubixhacker.dyn4k.optimized.OptimizedJourneyTest#appSideWorldAndSubclassCallbacks"

private val OPTIMIZED_RAW = listOf(
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
).joinToString("\n")

private const val OPTIMIZED_PROVIDER =
    "io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1\n" +
        "io.github.rubixhacker:dyn4k-core-android:0.1.0-alpha.1\n"

private val OPTIMIZED_MAPPING = listOf(
    "io.github.rubixhacker.dyn4k.optimized.OptimizedConsumer\$CountingWorld -> a:",
    "    1:2:java.lang.String io.github.rubixhacker.dyn4k.optimized.OptimizedConsumer.run():42:42 -> x",
    "org.dyn4j.geometry.Vector2 -> b:",
    "org.dyn4j.dynamics.Body -> c:",
    "org.dyn4j.world.World -> R8\$\$REMOVED\$\$CLASS\$\$16:",
).joinToString("\n")

private const val OPTIMIZED_USAGE =
    "org.dyn4j.geometry.CircleDetector\n" +
        "io.github.rubixhacker.dyn4k.optimized.OptimizedConsumer\n"

private val OPTIMIZED_DEX = setOf("La;", "Lb;", "Lc;")

private const val ACTIVITY = "io.github.rubixhacker.dyn4k.optimized.OptimizedActivity"

private const val NARROW =
    "-keep class io.github.rubixhacker.dyn4k.optimized.OptimizedActivity " +
        "{ public <init>(); public void onCreate(android.os.Bundle); }\n"

private fun rejectsBroad(rule: String) {
    val failure = assertFailsWith<IllegalArgumentException>(rule) {
        OptimizedEvidence.validateR8(rule, OPTIMIZED_MAPPING, OPTIMIZED_USAGE, OPTIMIZED_DEX)
    }
    assertTrue(failure.message!!.contains("broad keep"), failure.message!!)
}

private fun rejectsAny(rule: String) {
    assertFailsWith<IllegalArgumentException>(rule) {
        OptimizedEvidence.validateR8(rule, OPTIMIZED_MAPPING, OPTIMIZED_USAGE, OPTIMIZED_DEX)
    }
}

private fun accepts(rule: String) {
    OptimizedEvidence.validateR8(rule, OPTIMIZED_MAPPING, OPTIMIZED_USAGE, OPTIMIZED_DEX)
}

/**
 * `tools/android-runtime/test_optimized.py`.
 *
 * The optimized route's evidence is a claim about R8 keep rules: any rule that could pin an engine or
 * facade subtree invalidates it. These cases are the accepted and rejected rule families.
 */
val OptimizedEvidenceContract by testSuite {
    test("accepts installed app case and narrow R8 evidence") {
        OptimizedEvidence.validateInstalledCase(OPTIMIZED_RAW, 0, OPTIMIZED_CASE)
        OptimizedEvidence.validateProvider(OPTIMIZED_PROVIDER)
        accepts(
            "-keep class io.github.rubixhacker.dyn4k.optimized.OptimizedActivity { *; }\n",
        )
    }

    test("rejects zero executed tests") {
        assertFailsWith<IllegalArgumentException> {
            OptimizedEvidence.validateInstalledCase(
                "OK (0 tests)\nINSTRUMENTATION_CODE: -1\n",
                0,
                OPTIMIZED_CASE,
            )
        }
    }

    test("rejects wrong provider") {
        val failure = assertFailsWith<IllegalArgumentException> {
            OptimizedEvidence.validateProvider(OPTIMIZED_PROVIDER + "org.dyn4j:dyn4j:6.0.0\n")
        }
        assertTrue(failure.message!!.contains("provider"))
    }

    test("rejects engine wide keep rules") {
        rejectsBroad("-keep class org.dyn4j.** { *; }\n")
    }

    test("rejects engine and facade subtree keep rules") {
        for (rule in listOf(
            "-keep class org.dyn4j.geometry.** { *; }\n",
            "-keep class org.dyn4j.world.collision.** { *; }\n",
            "-keep class io.github.rubixhacker.dyn4k.geometry.** { *; }\n",
        )) {
            rejectsBroad(rule)
        }
    }

    test("rejects access modified package keep rules") {
        accepts(NARROW)
        for (rule in listOf(
            "-keep public class org.dyn4j.geometry.** { *; }\n",
            "-keep public class io.github.rubixhacker.dyn4k.geometry.** { *; }\n",
            "-keep,allowoptimization public class org.dyn4j.world.collision.** { *; }\n",
            "-keep,allowoptimization public final class io.github.rubixhacker.dyn4k.geometry.** { *; }\n",
        )) {
            rejectsBroad(NARROW + rule)
        }
    }

    test("rejects interface and enum subtree keeps") {
        for (targeted in listOf(
            "-keep class io.github.rubixhacker.dyn4k.optimized.OptimizedActivity { public <init>(); }\n",
            "-keep public interface org.dyn4j.world.PhysicsWorld { *; }\n",
            "-keep enum org.dyn4j.geometry.MassType { *; }\n",
        )) {
            accepts(targeted)
        }
        for (rule in listOf(
            "-keep interface org.dyn4j.** { *; }\n",
            "-keep public interface org.dyn4j.** { *; }\n",
            "-keep public interface io.github.rubixhacker.dyn4k.** { *; }\n",
            "  -keep,allowoptimization\tpublic interface org.dyn4j.world.** { *; }\n",
            "-keep\tpublic\tinterface\tio.github.rubixhacker.dyn4k.geometry.** { *; }\n",
            "-keep enum org.dyn4j.** { *; }\n",
            "-keep,allowoptimization  enum  io.github.rubixhacker.dyn4k.geometry.** { *; }\n",
        )) {
            rejectsBroad(rule)
        }
    }

    test("rejects annotation and member package keeps") {
        for (rule in listOf(
            "-keep @interface org.dyn4j.** { *; }\n",
            "-keep @interface io.github.rubixhacker.dyn4k.** { *; }\n",
            "-keepclassmembers class org.dyn4j.** { *; }\n",
            "-keepclassmembers class io.github.rubixhacker.dyn4k.** { *; }\n",
        )) {
            rejectsBroad(rule)
        }
    }

    test("rejects broad class member and name directives") {
        for (directive in listOf(
            "keep", "keepclassmembers", "keepclasseswithmembers", "keepnames",
            "keepclassmembernames", "keepclasseswithmembernames",
        )) {
            for (selector in listOf(
                "org.dyn4j.**", "org.dyn4j.geometry.*",
                "io.github.rubixhacker.dyn4k.**", "io.github.rubixhacker.dyn4k.optimized.*",
                "kotlin.**",
            )) {
                rejectsBroad(
                    "-$directive,allowoptimization public @interface $selector { *; }\n",
                )
            }
        }
    }

    test("rejects global star class selectors") {
        rejectsBroad("-keep class * { *; }\n")
        for (directive in listOf(
            "keep", "keepclassmembers", "keepclasseswithmembers", "keepnames",
            "keepclassmembernames", "keepclasseswithmembernames",
        )) {
            for (kind in listOf("class", "interface", "enum", "@interface")) {
                rejectsBroad("-$directive,allowoptimization public $kind * { *; }\n")
            }
        }
    }

    test("accepts metadata and path options") {
        for (rule in listOf(
            "-keepattributes **\n",
            "-keepdirectories **\n",
            "-keeppackagenames org.dyn4j.**\n",
            "-keepparameternames\n",
        )) {
            accepts(rule)
        }
    }

    test("rejects negated class selectors") {
        for (directive in listOf(
            "keep", "keepclassmembers", "keepclasseswithmembers",
            "keepnames", "keepclassmembernames", "keepclasseswithmembernames",
        )) {
            for (selector in listOf(
                "!android.**",
                "!io.github.rubixhacker.dyn4k.optimized.OptimizedActivity",
            )) {
                rejectsBroad("-$directive class $selector { *; }\n")
            }
        }
    }

    test("rejects global field wildcards in member families") {
        for (directive in listOf(
            "keepclassmembers", "keepclasseswithmembers",
            "keepclassmembernames", "keepclasseswithmembernames",
        )) {
            for (member in listOf("*** *;", "% *;", "public *** *;")) {
                rejectsBroad("-$directive class * { $member }\n")
            }
        }
    }

    test("rejects multiline field and method wildcards") {
        for (member in listOf(
            "public *** *;", "protected % *;", "public void *(...);",
            "private *** get*(...);",
        )) {
            rejectsBroad(
                "-keepclassmembers,allowoptimization\n class *\n {\n   $member\n }\n",
            )
        }
    }

    test("rejects global member type wildcards with exact names") {
        for (member in listOf("% x;", "public *** x;", "*** onCreate();")) {
            rejectsBroad("-keepclassmembers class * { $member }\n")
        }
    }

    test("accepts generated enum member type wildcards") {
        accepts(
            "-keepclassmembers enum * { public static **[] values(); " +
                "public static ** valueOf(java.lang.String); }\n",
        )
    }

    test("rejects same line conditional and following keep") {
        val rules = listOf(
            "-if class $ACTIVITY -keep class org.dyn4j.** { *; }",
            "-if class $ACTIVITY -keepclassmembers class * { *** *; }",
            "-keep class $ACTIVITY { <init>(); } -keepclassmembers class * { *** *; }",
        )
        for (rule in rules) rejectsBroad(rule)
    }

    test("rejects same line keep variants after complete block") {
        val narrow = "-keep class $ACTIVITY { <init>(); }"
        for (kind in listOf("class", "interface", "enum", "@interface")) {
            for (selector in listOf("org.dyn4j.**", "io.github.rubixhacker.dyn4k.**", "*")) {
                rejectsBroad("$narrow -keep,allowoptimization public $kind $selector { *; }")
            }
        }
        for (join in listOf("\n", " ", "")) {
            rejectsBroad("$narrow$join-keepclassmembers class * { *** *; }")
        }
        for (prefix in listOf("-keepattributes Signature ", "-dontwarn android.** ")) {
            rejectsBroad(prefix + "-keepclassmembers class * { *** *; }")
        }
    }

    test("accepts narrow same line conditional and comments") {
        val rule = "# -keep class org.dyn4j.** { *; }\n" +
            "-if class $ACTIVITY -keep class $ACTIVITY { <init>(); } " +
            "-keepattributes Signature # -keepclassmembers class * { *** *; }\n"
        accepts(rule)
    }

    test("parses complete conditional member block before consequent") {
        val condition = "-if class $ACTIVITY { public <init>(); }"
        val narrow = "-keep class $ACTIVITY { <init>(); }"
        for (join in listOf(" ", "\n", "")) {
            accepts(condition + join + narrow)
            rejectsBroad(condition + join + "-keepclassmembers class * { *** *; }")
        }
    }

    test("rejects ambiguous or incomplete effective blocks") {
        for (rule in listOf(
            "-if class $ACTIVITY",
            "-keep class $ACTIVITY { <init>();",
            "-keep class $ACTIVITY { <init>(); { }}",
            "-keep class $ACTIVITY { <init>(); } trailing",
            "-keep class $ACTIVITY { bogus int field; }",
            "-keepattributes Signature { -keepclassmembers class * { *** *; } }",
            "-keepclassmembers class * { public void exact(); } -if class $ACTIVITY",
        )) {
            rejectsAny(rule)
        }
    }

    test("rejects enum wildcard user overloads") {
        for (member in listOf(
            "public static *** values(...);", "public static *** valueOf(...);",
            "public static *** values();", "public static **[] values(int);",
            "public static **[] values(...);", "public static ** valueOf(...);",
            "public static ** valueOf(int);", "public static **[] valueOf(java.lang.String);",
            "public static int values(int);", "public static int valueOf(int);",
        )) {
            rejectsBroad("-keepclassmembers enum * { $member }")
        }
    }

    test("rejects global selectors with engine ancestry or broad members") {
        for (rule in listOf(
            "-keep class * extends org.dyn4j.world.World { *; }\n",
            "-keep @org.dyn4j.JvmFieldBridge class * { *; }\n",
            "-keepclassmembers class * { public int exact; *; }\n",
            "-keepclassmembers class * { <methods>; }\n",
            "-keepclassmembers class * { public void *(); }\n",
        )) {
            rejectsBroad(rule)
        }
    }

    test("accepts exact class with wildcard annotation filter") {
        accepts("-keep @* class org.dyn4j.geometry.Vector2 { *; }\n")
    }

    test("fails closed on unsupported effective selectors") {
        for (rule in listOf(
            "-keepfuture class org.dyn4j.geometry.Vector2 { *; }\n",
            "-keep class { *; }\n",
            "-keep class org.dyn4j.geometry.Vector2 Broken { *; }\n",
            "-keepclassmembers class *\n",
        )) {
            rejectsAny(rule)
        }
    }

    test("rejects multiline global member blanket") {
        rejectsBroad("-keepclassmembers,allowoptimization\n public class\n *\n { *; }\n")
    }

    test("rejects multiline and parent namespace wildcards") {
        for (rule in listOf(
            "-keepclassmembers,allowoptimization\n  public @interface\n  org.dyn4j.** { *; }\n",
            "-keepclasseswithmembers\tclass\n  io.github.rubixhacker.dyn4k.**\n  { *; }\n",
            "-keep class org.** { *; }\n",
            "-keep class io.github.** { *; }\n",
            "-keepclassmembers class **.geometry.* { *; }\n",
            "-keep class org.**.geometry.* { *; }\n",
            "-keep class ** { *; }\n",
        )) {
            rejectsBroad(rule)
        }
    }

    test("accepts comments warnings and targeted keeps") {
        val configuration = listOf(
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
        ).joinToString("\n")
        accepts(configuration)
    }

    test("rejects missing mapping usage or bytecode") {
        val cases = listOf(
            Triple("", OPTIMIZED_USAGE, OPTIMIZED_DEX),
            Triple(OPTIMIZED_MAPPING, "", OPTIMIZED_DEX),
            Triple(OPTIMIZED_MAPPING, OPTIMIZED_USAGE, emptySet<String>()),
            Triple(
                OPTIMIZED_MAPPING.replace(
                    "org.dyn4j.world.World -> R8\$\$REMOVED\$\$CLASS\$\$16:",
                    "",
                ),
                OPTIMIZED_USAGE,
                OPTIMIZED_DEX,
            ),
            Triple(
                OPTIMIZED_MAPPING.replace("OptimizedConsumer.run()", "OptimizedConsumer.missing()"),
                OPTIMIZED_USAGE,
                OPTIMIZED_DEX,
            ),
        )
        for ((mapping, usage, dex) in cases) {
            assertFailsWith<IllegalArgumentException> {
                OptimizedEvidence.validateR8(NARROW, mapping, usage, dex)
            }
        }
    }

    test("snapshot rejects changed build artifact") {
        withTempDirectory { directory ->
            val source = directory.resolve("mapping.txt")
            val snapshot = directory.resolve("retained-mapping.txt")
            source.toFile().writeText(OPTIMIZED_MAPPING)
            val failure = assertFailsWith<IllegalArgumentException> {
                OptimizedHost.snapshotArtifact(source, snapshot, "0".repeat(64))
            }
            assertTrue(failure.message!!.contains("changed"))
            assertTrue(!java.nio.file.Files.exists(snapshot))
        }
    }

    test("golden optimized mapping records exact descriptors") {
        val mapped = OptimizedEvidence.validateR8(NARROW, OPTIMIZED_MAPPING, OPTIMIZED_USAGE, OPTIMIZED_DEX)
        assertEquals(listOf(
            "io.github.rubixhacker.dyn4k.optimized.OptimizedConsumer\$CountingWorld",
            "org.dyn4j.geometry.Vector2",
            "org.dyn4j.dynamics.Body",
            "org.dyn4j.world.World",
        ), mapped.keys.toList())
        assertEquals("La;", mapped.getValue("io.github.rubixhacker.dyn4k.optimized.OptimizedConsumer\$CountingWorld").descriptor)
        assertEquals("Lb;", mapped.getValue("org.dyn4j.geometry.Vector2").descriptor)
        assertEquals("Lc;", mapped.getValue("org.dyn4j.dynamics.Body").descriptor)
        assertEquals(null, mapped.getValue("org.dyn4j.world.World").descriptor)
    }
}
