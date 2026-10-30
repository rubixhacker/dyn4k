package io.github.rubixhacker.harness.android

/**
 * `tools/android-runtime/build_identity.py` (pure half).
 *
 * Android evidence is only usable when the Gradle build that produced it ran on the pinned JDK 21 and
 * Gradle 9.5.0. The identity is read from the build log's daemon banner and confirmed by the daemon's
 * own log, so both texts are parsed here; the reads and the `java -version` call are host work.
 */

/** The pinned build identity a log must show. */
class BuildJdk(val javaHome: String, val javaVersion: String, val gradleVersion: String) {
    override fun equals(other: Any?): Boolean =
        other is BuildJdk && other.javaHome == javaHome &&
            other.javaVersion == javaVersion && other.gradleVersion == gradleVersion

    override fun hashCode(): Int = javaHome.hashCode() * 31 + javaVersion.hashCode()
}

/** The host operations `current_java` needs, so the decision can be tested without a JDK. */
interface BuildHost {
    fun environment(name: String): String?

    fun isFile(path: String): Boolean

    /** Runs `<binary> -version` and returns its stderr; throws when the process fails. */
    fun javaVersion(binary: String): String
}

object BuildIdentity {
    const val JDK_HOME = "/tmp/dyn4k-tools/jdk21"
    const val GRADLE_VERSION = "9.5.0"

    private val JAVA_VERSION = Regex("""(?m)^openjdk version "21\.[^\r\n]*""")

    /** `str.count`: non-overlapping occurrences only. */
    private fun pyCount(haystack: String, needle: String): Int {
        var count = 0
        var index = haystack.indexOf(needle)
        while (index >= 0) {
            count += 1
            index = haystack.indexOf(needle, index + needle.length)
        }
        return count
    }

    /** `validate_build_jdk`: the daemon banner names the pinned JDK and Gradle, and the marker is unique. */
    fun validateBuildJdk(raw: String, requireMarker: Boolean = true): BuildJdk {
        val daemon = Regex(
            "(?m)^Starting process 'Gradle build daemon'.*?Command: " +
                "${pyRegexEscape(JDK_HOME)}/bin/java .*?" +
                "org\\.gradle\\.launcher\\.daemon\\.bootstrap\\.GradleDaemon " +
                pyRegexEscape(GRADLE_VERSION) + "${'$'}",
        )
        val marker = "DYN4K_BUILD_JDK javaHome=$JDK_HOME javaVersion=21 " +
            "gradleVersion=$GRADLE_VERSION"
        if (!daemon.containsMatchIn(raw) || "BUILD SUCCESSFUL" !in raw ||
            (requireMarker && pyCount(raw, marker) != 1)
        ) {
            throw IllegalArgumentException("wrong JDK 21 or Gradle 9.5.0 daemon build identity")
        }
        return BuildJdk(JDK_HOME, "21", GRADLE_VERSION)
    }

    /** `current_java`: the pinned JAVA_HOME, the pinned binary, and the one JDK 21 banner it prints. */
    fun currentJava(host: BuildHost): BuildJdk {
        if (host.environment("JAVA_HOME") != JDK_HOME) {
            throw IllegalArgumentException("wrong pinned JAVA_HOME")
        }
        val binary = "$JDK_HOME/bin/java"
        if (!host.isFile(binary)) {
            throw IllegalArgumentException("pinned JDK 21 binary missing")
        }
        val versions = JAVA_VERSION.findAll(host.javaVersion(binary)).map { it.value }.toList()
        if (versions.size != 1) {
            throw IllegalArgumentException("wrong pinned JDK version")
        }
        return BuildJdk(JDK_HOME, versions[0], GRADLE_VERSION)
    }

    /** The single JDK 21 version banner in `java -version` output, or a rejection. */
    fun javaVersionBanner(stderr: String): String {
        val versions = JAVA_VERSION.findAll(stderr).map { it.value }.toList()
        if (versions.size != 1) {
            throw IllegalArgumentException("wrong pinned JDK version")
        }
        return versions[0]
    }
}
