package io.github.rubixhacker.harness.android

import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/** The build log identity record, including the daemon log it points at. */
data class BuildLogIdentity(
    val path: String,
    val sha256: String,
    val daemonLogPath: String,
    val daemonLogSha256: String,
    val javaHome: String,
    val javaVersion: String,
    val gradleVersion: String,
) {
    fun toJson(): JsonObject = buildJsonObject {
        put("path", JsonPrimitive(path))
        put("sha256", JsonPrimitive(sha256))
        put(
            "daemon_log",
            buildJsonObject {
                put("path", JsonPrimitive(daemonLogPath))
                put("sha256", JsonPrimitive(daemonLogSha256))
            },
        )
        put("java_home", JsonPrimitive(javaHome))
        put("java_version", JsonPrimitive(javaVersion))
        put("gradle_version", JsonPrimitive(gradleVersion))
    }
}

/** The real host operations behind `current_java`. */
object JvmBuildHost : BuildHost {
    override fun environment(name: String): String? = System.getenv(name)

    override fun isFile(path: String): Boolean = Files.isRegularFile(Path.of(path))

    override fun javaVersion(binary: String): String {
        val process = ProcessBuilder(binary, "-version").redirectErrorStream(false).start()
        val error = process.errorStream.bufferedReader().use { it.readText() }
        val output = process.inputStream.bufferedReader().use { it.readText() }
        if (process.waitFor() != 0) {
            throw IllegalStateException("command failed: $binary -version: $output$error")
        }
        return error
    }
}

object BuildIdentityFiles {
    private val DAEMON_LOG = Regex("""(?m)The daemon log file: (\S+/daemon-\d+\.out\.log)${'$'}""")

    /** `build_log_identity`: the validated build identity plus the daemon log it names. */
    fun buildLogIdentity(path: Path, requireMarker: Boolean = false): BuildLogIdentity {
        val raw = path.toFile().readText()
        val validated = BuildIdentity.validateBuildJdk(raw, requireMarker = requireMarker)
        val matches = DAEMON_LOG.findAll(raw).map { it.groupValues[1] }.toList()
        if (matches.size != 1) {
            throw IllegalArgumentException("Gradle daemon log identity missing")
        }
        val daemon = Path.of(matches[0])
        val daemonRaw = daemon.toFile().readText()
        val expected = Regex(
            "javaHome=" + pyRegexEscape(BuildIdentity.JDK_HOME) + ",javaVersion=21(?:,|\\b)",
        )
        if (!expected.containsMatchIn(daemonRaw)) {
            throw IllegalArgumentException("wrong raw Gradle daemon javaHome or version")
        }
        return BuildLogIdentity(
            path = posix(path),
            sha256 = sha256(path),
            daemonLogPath = posix(daemon),
            daemonLogSha256 = sha256(daemon),
            javaHome = validated.javaHome,
            javaVersion = validated.javaVersion,
            gradleVersion = validated.gradleVersion,
        )
    }

    /** `verify_build_log_identity`: the recorded identity still describes the log on disk. */
    fun verifyBuildLogIdentity(record: JsonObject, requireMarker: Boolean = false): JsonObject {
        val path = record.textOrNull("path")
            ?: throw IllegalArgumentException("build JDK log identity changed")
        if (buildLogIdentity(Path.of(path), requireMarker = requireMarker).toJson() != record) {
            throw IllegalArgumentException("build JDK log identity changed")
        }
        return record
    }
}
