package io.github.rubixhacker.harness.android

/**
 * `tools/android-runtime/android_corpus.py` (pure half).
 *
 * The full Android app installs every frozen portable common case and executes it through the shared
 * corpus executor, so its inputs are derived from the complete suite manifest: one TSV row per case and
 * one R8 keep rule per test class plus the pinned journey and reflective filter entries.
 */

/** One frozen suite case: identity, owner, and which lane it runs on. */
class SuiteCase(
    val id: String,
    val module: String,
    val classname: String,
    val method: String,
    val scope: String,
)

object AndroidCorpus {
    const val MANIFEST = "tools/qualification/full-suite-manifest.json"

    val MODULES = listOf("dyn4k-core", "dyn4k")

    const val FULL_GENERATED = "consumers/android-runtime/full/build/generated"

    val JAVA_JOURNEYS = listOf(
        "GeometryConsumer", "DetectionConsumer", "CollisionModelConsumer",
        "DynamicsConsumer", "WorldConsumer", "JointConsumer", "ContactConsumer",
    )

    const val KOTLIN_JOURNEY = "io.github.rubixhacker.dyn4k.full.FullKotlinJourney"

    val REFLECTIVE_FILTER_TYPES = listOf(
        "CollisionModelConsumer\$RootFilter", "CollisionModelConsumer\$ChildFilter",
        "CollisionModelConsumer\$OtherFilter",
        "org.dyn4j.collision.CollisionModelTest\$RootFilter",
        "org.dyn4j.collision.CollisionModelTest\$ChildFilter",
        "org.dyn4j.collision.CollisionModelTest\$OtherFilter",
        "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest\$Parent",
        "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest\$Child",
        "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest\$Sibling",
        "org.dyn4j.coverage.collision.model.FilterFixtureCoverageTest\$Unrelated",
    )

    const val X86_DEXOPT_METHOD =
        "-keepclassmembers class org.dyn4j.geometry.Matrix22 { public double normMax(); }"

    val FINGERPRINTS: Map<String, String> = linkedMapOf(
        "36" to "google/sdk_gphone64_x86_64/emu64xa:16/BE4B.251210.005/14574095:user/release-keys",
        "37" to "google/sdk_gphone64_x86_64/emu64xa:17/CE2A.260420.019/15611780:user/release-keys",
    )

    /** `case_id`. */
    fun caseId(case: SuiteCase): String = case.module + ":" + case.classname + "#" + case.method

    /**
     * `full_app_inputs`: the case TSV asset and the R8 keep file, as the Python function returns them.
     */
    fun fullAppInputs(suite: List<SuiteCase>): Map<String, ByteArray> {
        val portable = suite.filter { it.scope == "portable" }
        val caseLines = portable
            .map { listOf(caseId(it), it.classname, it.method).joinToString("\t") }
            .toMutableList()
        caseLines += JAVA_JOURNEYS.map { name -> "external-java:$name#main\t$name\tmain" }
        caseLines += "external-kotlin:$KOTLIN_JOURNEY#run\t$KOTLIN_JOURNEY\trun"
        val rules = mutableListOf(
            "-keepattributes RuntimeVisibleAnnotations,AnnotationDefault,InnerClasses," +
                "EnclosingMethod,Signature",
            "-keep class io.github.rubixhacker.dyn4k.full.FullCorpusExecutor " +
                "{ public static java.util.List runAll(android.content.Context); }",
            "-keep class io.github.rubixhacker.dyn4k.full.FullActivity " +
                "{ public <init>(); public void onCreate(android.os.Bundle); }",
        )
        rules += portable.map { it.classname }.distinct().sorted()
            .map { "-keep,allowoptimization class $it { *; }" }
        rules += X86_DEXOPT_METHOD
        rules += JAVA_JOURNEYS.map {
            "-keep class $it { public static void main(java.lang.String[]); }"
        }
        rules += REFLECTIVE_FILTER_TYPES.map { "-keep,allowobfuscation class $it" }
        rules += "-keep class $KOTLIN_JOURNEY { public static void run(); }"
        return linkedMapOf(
            "case_asset" to (caseLines.joinToString("\n") + "\n").encodeToByteArray(),
            "keep_rules" to (rules.joinToString("\n") + "\n").encodeToByteArray(),
        )
    }
}
