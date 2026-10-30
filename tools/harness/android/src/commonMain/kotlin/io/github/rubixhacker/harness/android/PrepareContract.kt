package io.github.rubixhacker.harness.android

/**
 * `tools/android-runtime/prepare.py` (pure half).
 *
 * The Android app compiles copies of the shared JVM consumer sources. One source needs a pinned
 * adaptation: the CollisionModelConsumer version table must gain the ART message entry, and the copy
 * must contain the pinned JVM case exactly once so a drifted upstream table cannot slip through.
 */
object PrepareContract {
    val CONSUMERS = listOf(
        "GeometryConsumer",
        "DetectionConsumer",
        "CollisionModelConsumer",
        "DynamicsConsumer",
        "WorldConsumer",
        "JointConsumer",
        "ContactConsumer",
        "org/dyn4j/geometry/GeometryPackageConsumer",
    )

    const val VERSION = "0.1.0-alpha.1"

    val ANDROID_VERSION_CASE: ByteArray =
        "if (\"1.8\".equals(version)) return null;\n".encodeToByteArray()

    val ANDROID_VERSION_CASE_WITH_ART: ByteArray = (
        "if (\"1.8\".equals(version)) return null;\n" +
            "        if (\"0.9\".equals(version)) return " +
            "\"Attempt to invoke virtual method 'java.lang.String " +
            "java.lang.Class.getName()' on a null object reference\";\n"
        ).encodeToByteArray()

    /** `android_consumer_source`: applies the pinned ART-message adaptation to the CollisionModelConsumer. */
    fun androidConsumerSource(name: String, source: ByteArray): ByteArray {
        if (name != "CollisionModelConsumer") return source
        if (countOccurrences(source, ANDROID_VERSION_CASE) != 1) {
            throw IllegalArgumentException("Android consumer version table differs from pinned JVM source")
        }
        val index = indexOf(source, ANDROID_VERSION_CASE, 0)
        val replaced = ByteArray(
            source.size - ANDROID_VERSION_CASE.size + ANDROID_VERSION_CASE_WITH_ART.size,
        )
        source.copyInto(replaced, 0, 0, index)
        ANDROID_VERSION_CASE_WITH_ART.copyInto(replaced, index)
        source.copyInto(
            replaced,
            index + ANDROID_VERSION_CASE_WITH_ART.size,
            index + ANDROID_VERSION_CASE.size,
            source.size,
        )
        return replaced
    }

    /** The index of [needle] in [haystack] at or after [from], or -1. */
    internal fun indexOf(haystack: ByteArray, needle: ByteArray, from: Int): Int {
        if (needle.size > haystack.size) return -1
        if (needle.isEmpty()) return from
        outer@ for (start in from..haystack.size - needle.size) {
            for (offset in needle.indices) {
                if (haystack[start + offset] != needle[offset]) continue@outer
            }
            return start
        }
        return -1
    }

    /** `bytes.count(needle)`: non-overlapping occurrences. */
    internal fun countOccurrences(haystack: ByteArray, needle: ByteArray): Int {
        if (needle.isEmpty()) return 0
        var count = 0
        var index = indexOf(haystack, needle, 0)
        while (index >= 0) {
            count += 1
            index = indexOf(haystack, needle, index + needle.size)
        }
        return count
    }
}
