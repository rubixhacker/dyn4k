package io.github.rubixhacker.harness.performance

import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import java.io.File
import java.nio.file.Paths

/** Where the repository keeps the performance inputs, resolved from the working directory. */
object PerformanceLayout {
    /**
     * The repository root: the nearest directory at or above the working directory that holds
     * `tools/performance/BaselinePilot.java`. The Gradle entry points run from the root, and the
     * walk keeps them working when a caller starts them from a subdirectory.
     */
    fun repositoryRoot(start: File = File("").absoluteFile): File {
        var candidate: File? = start
        while (candidate != null) {
            if (File(candidate, "tools/performance/BaselinePilot.java").isFile) return candidate
            candidate = candidate.parentFile
        }
        return start
    }

    fun manifestFile(root: File): File = File(root, "docs/research/performance-manifest-v1.json")

    /** `measure.HERE`: the directory holding the Java harness sources. */
    fun harnessSources(root: File): File = File(root, "tools/performance")

    /** `measure.HERE / "BaselinePilot.java"`, whose digest the reports record. */
    fun harnessSource(root: File): File = File(harnessSources(root), "BaselinePilot.java")

    /** `candidate_runner.IDENTITY`. */
    fun candidateIdentity(root: File): File =
        File(root, "consumers/performance/build/candidate-identity.json")

    /** `candidate_runner.PATHS`. */
    fun candidatePaths(root: File): File =
        File(root, "consumers/performance/build/candidate-paths.tsv")

    /** `candidate_runner.STAGING`. */
    fun stagingRepository(root: File): File = File(root, "build/staging-repository")
}

/**
 * The candidate staging repository and its identity record: `candidate_runner.py` `prepare`,
 * `verify_hashes`, `read_paths`, and `check_route`, plus `verify_candidate_archive.verify_identity`.
 *
 * `ccd_route_trace.capture` cannot run without these, so they live here rather than staying in
 * Python. Every path is derived from the repository root instead of a baked-in absolute path.
 */
class CandidateStaging(val root: File) {
    private val files = PathFileSystem()

    /** `candidate_runner.ROOT / "consumers" / "performance"`. */
    val consumer: File get() = File(root, "consumers/performance")

    /** `candidate_runner.STAGING`. */
    val staging: File get() = PerformanceLayout.stagingRepository(root)

    /** `candidate_runner.PATHS`. */
    val pathsFile: File get() = PerformanceLayout.candidatePaths(root)

    /** `candidate_runner.IDENTITY`. */
    val identityFile: File get() = PerformanceLayout.candidateIdentity(root)

    /** The source files whose digests the identity record pins, as `candidate_runner.prepare` lists them. */
    val sourceFiles: List<String> = listOf(
        "consumers/performance/build.gradle.kts",
        "consumers/performance/src/main/java/performance/ProviderIdentity.java",
        "consumers/performance/src/main/kotlin/performance/DirectFixture.kt",
        "consumers/performance/src/main/kotlin/performance/DirectPilot.kt",
        "docs/research/performance-manifest-v1.json",
        "tools/performance/BaselinePilot.java",
        "tools/performance/candidate_runner.py",
    )

    /** `verify_candidate_archive.SOURCE_FILES`, the subset `verify_identity` re-hashes from git. */
    val verifiedSourceFiles: List<String> = sourceFiles

    /** `candidate_runner.git(...).stdout.strip()`. */
    fun git(vararg arguments: String): String = String(gitBytes(*arguments), Charsets.UTF_8).trim()

    /** `candidate_runner.git(...).stdout`, undecoded, for digests over committed blobs. */
    fun gitBytes(vararg arguments: String): ByteArray {
        val command = listOf("git") + arguments
        val process = ProcessBuilder(command).directory(root).redirectErrorStream(false).start()
        val output = process.inputStream.readBytes()
        val error = process.errorStream.readBytes().decodeToString()
        val code = process.waitFor()
        if (code != 0) {
            throw IllegalStateException(
                "Command '${command}' returned non-zero exit status $code.: $error".trimEnd(),
            )
        }
        return output
    }

    /** `candidate_runner.source_trees`. */
    fun sourceTrees(commit: String): JsonObject = buildJsonObject {
        for (name in listOf("dyn4k-core", "dyn4k")) put(name, git("rev-parse", "$commit:$name"))
    }

    /** `candidate_runner.read_paths`, with the staging paths resolved to absolute strings. */
    fun readPaths(): Map<String, List<String>> =
        CandidateRunner.readPaths(pathsFile.readText()).mapValues { (_, values) ->
            values.map { File(root, it).absoluteFile.toPath().normalize().toString() }
        }

    /** `candidate_runner.hash_path`. */
    fun hashPath(path: String): String = CandidateRunner.hashPath(files, path)

    /**
     * `candidate_runner.prepare`: checks both staged routes, proves the engine sources match the
     * requested commit, hashes the classpath and the pinned sources, and writes the identity.
     */
    fun prepare(java: String, sourceCommit: String, stdout: java.io.PrintStream): JsonObject {
        val paths = readPaths()
        for ((route, values) in paths) {
            CandidateRunner.checkRoute(route, values, staging.absolutePath)
        }
        if (git("status", "--porcelain", "--", "dyn4k", "dyn4k-core").isNotEmpty()) {
            throw IllegalArgumentException("engine sources have uncommitted changes")
        }
        val trees = sourceTrees(sourceCommit)
        if (trees != sourceTrees("HEAD")) {
            throw IllegalArgumentException("staged engine source revision differs from current tree")
        }
        val process = ProcessBuilder(java, "-version").redirectErrorStream(false).start()
        val version = process.errorStream.readBytes().decodeToString().trim()
        process.waitFor()

        val allPaths = paths.values.flatten().toSet()
        val missing = allPaths.filter { !File(it).exists() }.sorted()
        if (missing.any { PerformancePaths.suffix(it) == ".jar" }) {
            throw IllegalArgumentException("candidate classpath has a missing artifact")
        }
        val observed = LinkedHashMap<String, String>()
        for (path in allPaths.filter { File(it).exists() }) {
            observed[path] = hashPath(path)
        }
        if (!File(consumer, "build/classes/kotlin/main/performance/DirectPilotKt.class").isFile) {
            throw IllegalArgumentException("direct Kotlin entry point is missing")
        }
        if (!File(consumer, "build/classes/java/compatibility/BaselinePilot.class").isFile) {
            throw IllegalArgumentException("Java compatibility entry point is missing")
        }
        val core = File(staging, CandidateRunner.coreArtifact).absolutePath
        val api = File(staging, CandidateRunner.apiArtifact).absolutePath
        if (observed[core] == PerformanceManifest.BASELINE_JAR_SHA256) {
            throw IllegalArgumentException("core artifact matches the upstream binary")
        }
        for (relative in sourceFiles) {
            val path = File(root, relative).absolutePath
            observed[path] = hashPath(path)
        }

        val identity = buildJsonObject {
            put("schema", 1)
            put("source_commit", git("rev-parse", sourceCommit))
            put("source_trees", trees)
            put("staging_repository", staging.absoluteFile.toPath().normalize().toString())
            put("java", Paths.get(java).toAbsolutePath().normalize().toString())
            put("java_version", version)
            put("java_flags", JsonArray(CandidateRunner.flags.map { JsonPrimitive(it) }))
            put(
                "paths",
                buildJsonObject {
                    for ((route, values) in paths) {
                        put(route, JsonArray(values.map { JsonPrimitive(it) }))
                    }
                },
            )
            put("absent_classpath_paths", JsonArray(missing.map { JsonPrimitive(it) }))
            put(
                "sha256",
                buildJsonObject { for ((path, digest) in observed) put(path, digest) },
            )
            put(
                "entrypoints",
                buildJsonObject {
                    put("direct_kotlin", CandidateRunner.entrypoints.getValue("direct_kotlin"))
                    put("compatibility", CandidateRunner.entrypoints.getValue("compatibility"))
                },
            )
            put("qualification", "unpassed")
        }
        identityFile.parentFile?.mkdirs()
        identityFile.writeText(PythonJson.renderIndented(identity, sortKeys = true) + "\n")
        stdout.println(
            PythonJson.render(
                buildJsonObject {
                    put("identity", identityFile.absolutePath)
                    put("source_commit", identity.str("source_commit"))
                    put("core_sha256", observed.getValue(core))
                    put("api_sha256", observed.getValue(api))
                },
            ),
        )
        return identity
    }

    /**
     * `verify_candidate_archive.verify_identity`: the recorded identity must name this exact
     * commit, this exact staging repository, and digests that still match both git and the disk.
     */
    fun verifyIdentity(identity: JsonObject) {
        val commit = identity.str("source_commit")
        require(
            identity["schema"]?.jsonPrimitive?.content == "1" &&
                identity.str("qualification") == "unpassed" &&
                identity.getValue("java_flags") == JsonArray(CandidateRunner.flags.map { JsonPrimitive(it) }) &&
                identity.getValue("entrypoints") == buildJsonObject {
                    put("direct_kotlin", "performance.DirectPilotKt")
                    put("compatibility", "BaselinePilot")
                },
            "candidate runtime or entrypoint identity differs",
        )
        require(
            commit.length == 40 && commit.all { it in "0123456789abcdef" },
            "source commit is not an exact SHA",
        )
        try {
            require(
                git("rev-parse", "--verify", "$commit^{commit}") == commit,
                "source commit differs",
            )
            val trees = sourceTrees(commit)
            require(
                identity.getValue("source_trees") == trees &&
                    trees == sourceTrees("HEAD"),
                "source trees differ from the exact commit",
            )
            require(
                git("status", "--porcelain", "--", "dyn4k", "dyn4k-core").isEmpty(),
                "engine source worktree differs from the exact commit",
            )
            require(
                identity.str("staging_repository") == staging.absoluteFile.toPath().normalize().toString(),
                "staging repository differs",
            )
            val routes = readPaths()
            val recordedPaths = identity.getValue("paths").jsonObject
            require(
                routes.keys == recordedPaths.keys && routes.all { (route, values) ->
                    JsonArray(values.map { JsonPrimitive(it) }) == recordedPaths.getValue(route)
                },
                "resolved classpaths differ",
            )
            for ((route, values) in routes) {
                CandidateRunner.checkRoute(route, values, staging.absolutePath)
            }
            require(
                File(staging, CandidateRunner.coreArtifact).isFile &&
                    File(staging, CandidateRunner.apiArtifact).isFile,
                "staged JVM artifacts are unavailable",
            )
            val java = File(identity.str("java"))
            require(java.isFile, "recorded Java runtime is unavailable")
            val process = ProcessBuilder(java.absolutePath, "-version").redirectErrorStream(false).start()
            val version = process.errorStream.readBytes().decodeToString().trim()
            process.waitFor()
            require(version == identity.str("java_version"), "recorded Java runtime differs")

            val allPaths = routes.values.flatten().toSet()
            val missing = allPaths.filter { !File(it).exists() }.toSet()
            require(
                identity.getValue("absent_classpath_paths").jsonArray.map { it.jsonPrimitive.content }
                    .toSet() == missing &&
                    missing.none { PerformancePaths.suffix(it) == ".jar" },
                "resolved classpath contains an unavailable artifact",
            )
            val expected = (allPaths - missing) +
                verifiedSourceFiles.map { File(root, it).absolutePath }
            val recorded = identity.getValue("sha256").jsonObject.keys
            require(recorded == expected, "source or artifact hash path differs")
            for (relative in verifiedSourceFiles) {
                val path = File(root, relative).absolutePath
                val recordedDigest = identity.getValue("sha256").jsonObject.getValue(path).jsonPrimitive.content
                val committed = Sha256.of(gitBytes("show", "$commit:$relative"))
                require(
                    recordedDigest == committed && hashPath(path) == recordedDigest,
                    "source hash differs: $relative",
                )
            }
            for (path in allPaths - missing) {
                require(
                    hashPath(path) == identity.getValue("sha256").jsonObject.getValue(path).jsonPrimitive.content,
                    "artifact or classpath hash differs: $path",
                )
            }
        } catch (error: java.io.IOException) {
            throw IllegalArgumentException("source or artifact verification unavailable: $error")
        } catch (error: IllegalStateException) {
            throw IllegalArgumentException("source or artifact verification unavailable: ${error.message}")
        } catch (error: NoSuchElementException) {
            throw IllegalArgumentException("source or artifact verification unavailable: $error")
        }
    }

    /** The staged classpath and entry point a candidate route executes, from the identity record. */
    fun candidateRoute(identity: JsonObject, route: String): Pair<String, String> {
        val paths = identity.getValue("paths").jsonObject.getValue(route).jsonArray
            .map { it.jsonPrimitive.content }
        val entrypoint = identity.getValue("entrypoints").jsonObject.getValue(route).jsonPrimitive.content
        return paths.joinToString(File.pathSeparator) to entrypoint
    }

    private fun require(condition: Boolean, message: String) {
        if (!condition) throw IllegalArgumentException(message)
    }
}
