package io.github.rubixhacker.harness.qualification

/**
 * The shared adapter layer of the `full_*` consumer family: the pinned tables and pure predicates
 * of `full_android_adapter.py`, `full_browser_adapter.py`, and `full_klib_adapter.py`.
 *
 * The adapters bind independently signed lane expectations to the public consumer replays. The
 * tables below are the exact literals of the three Python adapters and the consumer constants they
 * read (`full_android_consumer.MODULES`, `full_browser_consumer.{MODULES,JAVA_SHA256,
 * GRADLE_SHA256,CHROMIUM,LANES}`, `full_klib_consumer.{MODULES,LOCAL_LANES}`).
 */
object FullAndroidAdapterRules {
    /** `full_android_consumer.MODULES`. */
    val MODULES: List<String> = listOf("dyn4k-core", "dyn4k")

    /** `ROUTES`: lane → (`ro.build.version.sdk`, configuration). */
    val ROUTES: Map<String, Pair<String, String>> = linkedMapOf(
        "android:Android JVM:minimum:debug" to ("21" to "debug"),
        "android:Android JVM:minimum:r8-optimized" to ("21" to "r8-optimized"),
        "android:Android JVM:current:debug" to ("37" to "debug"),
        "android:Android JVM:current:r8-optimized" to ("37" to "r8-optimized"),
    )

    /** `_digest`: a plain 64-hex string, never a number or a boolean. */
    fun isDigest(value: String?): Boolean = value != null && Py.SHA64.matches(value)

    fun isCandidate(value: String?): Boolean = value != null && Py.SHA40.matches(value)
}

object FullBrowserAdapterRules {
    /** `full_browser_consumer.MODULES`. */
    val MODULES: List<String> = listOf("dyn4k-core", "dyn4k")

    const val JAVA_SHA256 = "2a207f5e7d075afa01d97f8048389a64432a44c4a5af0f5e77d6e286ec5f401d"
    const val GRADLE_SHA256 = "b88b6fc9f41fba7bf456a3f8255ee5b7c6c379202ca13f68c3feecebcbc7bd8b"

    /** `CHROMIUM`: role → (major, pinned executable SHA-256). */
    val CHROMIUM: Map<String, Pair<Int, String>> = linkedMapOf(
        "minimum" to (119 to "c81049295247b6892c802dcad33dcab0a0337fce31800f923f51bdb0c07e6d11"),
        "current" to (155 to "b866a2964538c825538c454de4867973b926650da57ec12dc3328807d768247b"),
    )

    /** `LANES`, built from target × family × role × mode exactly as the producer builds it. */
    val LANES: Set<String> = buildSet {
        for (target in listOf("js", "wasmJs")) {
            for (family in listOf("Chromium", "Firefox", "Safari")) {
                for (role in listOf("minimum", "current")) {
                    for (mode in listOf("development", "production")) {
                        add("$target:$family:$role:$mode")
                    }
                }
            }
        }
    }

    /** `TOOLCHAIN_KEYS`: the exact signed toolchain inventory. */
    val TOOLCHAIN_KEYS: Set<String> = setOf(
        "java_home", "java_version", "java_sha256", "gradle", "gradle_sha256",
        "gradle_version", "kgp_version", "browser", "browser_sha256",
        "browser_version", "gradle_user_home",
    )

    fun isDigest(value: String?): Boolean = value != null && Py.SHA64.matches(value)

    fun isCandidate(value: String?): Boolean = value != null && Py.SHA40.matches(value)
}

object FullKlibAdapterRules {
    /** `full_klib_consumer.MODULES`. */
    val MODULES: List<String> = listOf("dyn4k-core", "dyn4k")

    /** `full_klib_consumer.LOCAL_LANES`: the eight lanes the public KLIB verifier covers. */
    val LOCAL_LANES: Set<String> = buildSet {
        for (version in listOf("minimum", "current")) {
            for (mode in listOf("debug-g", "optimized-opt")) {
                add("linuxX64:Linux x64:$version:$mode")
            }
        }
        for (version in listOf("minimum", "current")) {
            for (mode in listOf("development", "production")) {
                add("js:Node.js:$version:$mode")
            }
        }
    }

    val TOOLCHAIN_KEYS: Set<String> = setOf(
        "java_home", "java_version", "java_sha256", "gradle_version",
        "gradle_sha256", "node_version", "node_sha256", "gradle_user_home",
        "kgp_version", "kotlin_native",
    )

    val NATIVE_KEYS: Set<String> = setOf(
        "home", "version", "executable_sha256", "compiler_sha256",
    )

    fun isDigest(value: String?): Boolean = value != null && Py.SHA64.matches(value)
}
