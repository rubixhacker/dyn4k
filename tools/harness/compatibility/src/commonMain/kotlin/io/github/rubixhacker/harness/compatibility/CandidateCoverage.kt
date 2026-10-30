package io.github.rubixhacker.harness.compatibility

/**
 * The source-mapping helpers of `tools/compatibility/candidate_coverage.py`.
 *
 * Ported: [safeSource], [classSourceFile], and the frozen mapping tables.
 *
 * Not ported: `digest`, `git`, `committed_sha`, `source_record`, `check_source_candidate`,
 * `source_index`, `class_sources`, `materialize`, and `main`. They read git objects, walk the
 * worktree, open the candidate JAR, and verify hashes against a chosen revision; the JVM adapters
 * for those belong in `:host`.
 */
object CandidateCoverage {
    val SOURCE_ROOTS = listOf(
        "dyn4k-core/src/commonMain/kotlin",
        "dyn4k-core/src/jvmMain/kotlin",
    )
    const val MODULE_SOURCE = "dyn4k-core/src/jvmModule/java/module-info.java"

    /** Anonymous behaviours and the source marker that carries them, in Python's order. */
    val ANONYMOUS_BEHAVIORS: Map<String, Pair<String, String>> = linkedMapOf(
        "org.dyn4j.collision.Filter\$1" to
            ("dyn4k-core/src/commonMain/kotlin/org/dyn4j/collision/FiltersAndFixture.kt" to "DEFAULT_FILTER"),
        "org.dyn4j.collision.manifold.ManifoldPointId\$1" to
            ("dyn4k-core/src/commonMain/kotlin/org/dyn4j/collision/manifold/ManifoldModels.kt" to "DISTANCE"),
        "org.dyn4j.world.ValueMixer\$1" to
            ("dyn4k-core/src/commonMain/kotlin/org/dyn4j/world/ValueMixer.kt" to "DEFAULT_MIXER"),
        "org.dyn4j.collision.broadphase.DynamicAABBTree\$1" to
            ("dyn4k-core/src/commonMain/kotlin/org/dyn4j/collision/broadphase/DynamicAABBTree.kt" to "sorted.sortWith"),
    )

    val COMMON_EXPECT_SOURCES: Map<String, Pair<String, String>> = linkedMapOf(
        "org.dyn4j.exception.CopyException" to
            ("dyn4k-core/src/commonMain/kotlin/org/dyn4j/exception/CollisionExceptions.kt" to
                "expect open class CopyException"),
    )

    /** True when [path] is a candidate source path inside one of the declared roots. */
    fun safeSource(path: String): Boolean {
        val parts = pathParts(path)
        return path.isNotEmpty() &&
            !isAbsolutePath(path) &&
            ".." !in parts &&
            (SOURCE_ROOTS.any { path.startsWith(it) } || path == MODULE_SOURCE)
    }

    /**
     * Reads the `SourceFile` attribute of a JVM class file, returning null when the class file
     * carries none. Any structural problem raises `IllegalArgumentException` with the message the
     * Python parser raises.
     */
    fun classSourceFile(data: ByteArray): String? {
        if (data.size < 10 || !data.copyOfRange(0, 4).contentEquals(CLASS_MAGIC)) {
            throw IllegalArgumentException("candidate classfile header is invalid")
        }
        val reader = ClassFileReader(data)
        val pool = arrayOfNulls<String>(reader.u2())
        var index = 1
        while (index < pool.size) {
            val tag = reader.take(1)[0].toInt() and 0xFF
            when {
                tag == 1 -> {
                    val length = reader.u2()
                    pool[index] = reader.take(length).toString(Charsets.UTF_8)
                }
                tag in setOf(3, 4, 9, 10, 11, 12, 17, 18) -> reader.take(4)
                tag in setOf(5, 6) -> {
                    reader.take(8)
                    index++
                }
                tag in setOf(7, 8, 16, 19, 20) -> reader.take(2)
                tag == 15 -> reader.take(3)
                else -> throw IllegalArgumentException("unsupported candidate classfile constant tag: $tag")
            }
            index++
        }

        fun attributes(): List<Pair<String?, ByteArray>> {
            val count = reader.u2()
            return (0 until count).map { pool[reader.u2()] to reader.take(reader.u4()) }
        }

        reader.take(6)
        reader.take(2 * reader.u2())
        repeat(reader.u2()) {
            reader.take(6)
            attributes()
        }
        repeat(reader.u2()) {
            reader.take(6)
            attributes()
        }
        for ((name, value) in attributes()) {
            if (name == "SourceFile") {
                if (value.size != 2) {
                    throw IllegalArgumentException("candidate SourceFile attribute is invalid")
                }
                val poolIndex = ((value[0].toInt() and 0xFF) shl 8) or (value[1].toInt() and 0xFF)
                return pool[poolIndex]
            }
        }
        return null
    }

    private val CLASS_MAGIC = byteArrayOf(0xCA.toByte(), 0xFE.toByte(), 0xBA.toByte(), 0xBE.toByte())

    private class ClassFileReader(private val data: ByteArray) {
        private var cursor = 8

        fun take(size: Int): ByteArray {
            if (cursor + size > data.size) {
                throw IllegalArgumentException("candidate classfile is truncated")
            }
            val value = data.copyOfRange(cursor, cursor + size)
            cursor += size
            return value
        }

        fun u2(): Int {
            val value = take(2)
            return ((value[0].toInt() and 0xFF) shl 8) or (value[1].toInt() and 0xFF)
        }

        fun u4(): Int {
            val value = take(4)
            return ((value[0].toInt() and 0xFF) shl 24) or
                ((value[1].toInt() and 0xFF) shl 16) or
                ((value[2].toInt() and 0xFF) shl 8) or
                (value[3].toInt() and 0xFF)
        }
    }
}
