package io.github.rubixhacker.harness.performance

import io.github.rubixhacker.harness.contract.Sha256

/** `tools/performance/candidate_runner.py`: candidate artifacts, routes, and their identities. */
object CandidateRunner {
    const val VERSION: String = "0.1.0-alpha.1"

    val coreArtifact: String =
        "io/github/rubixhacker/dyn4k-core-jvm/$VERSION/dyn4k-core-jvm-$VERSION.jar"
    val apiArtifact: String = "io/github/rubixhacker/dyn4k-jvm/$VERSION/dyn4k-jvm-$VERSION.jar"

    val flags: List<String> = listOf("-Xms256m", "-Xmx2g", "-XX:+UseG1GC")

    val entrypoints: Map<String, String> = mapOf(
        "direct_kotlin" to "performance.DirectPilotKt",
        "compatibility" to "BaselinePilot",
    )

    /**
     * `candidate_runner.hash_path`: a file digests to its bytes; a directory digests each file's
     * relative path followed by its raw digest, in sorted path order.
     */
    fun hashPath(files: PerformanceFileSystem, path: String): String {
        val normalized = PerformancePaths.normalize(path)
        if (files.isFile(normalized)) {
            return Sha256.of(files.readBytes(normalized))
        }
        if (files.isDirectory(normalized)) {
            val digest = Sha256Stream()
            for (relative in files.walkFiles(normalized).sorted()) {
                digest.update(relative.encodeToByteArray())
                digest.update(hexToBytes(hashPath(files, PerformancePaths.join(normalized, relative))))
            }
            return digest.hexDigest()
        }
        throw IllegalArgumentException("missing candidate path: $path")
    }

    /** `candidate_runner.verify_hashes`: every recorded path must still carry its recorded digest. */
    fun verifyHashes(files: PerformanceFileSystem, expected: Map<String, String>) {
        for ((name, digest) in expected) {
            if (hashPath(files, name) != digest) throw IllegalArgumentException("stale candidate path: $name")
        }
    }

    /** `candidate_runner.read_paths`: the two staged candidate routes and their classpaths. */
    fun readPaths(text: String): Map<String, List<String>> {
        val rows = text.split("\n").filter { it.isNotEmpty() }.map { line ->
            val separator = line.indexOf('\t')
            if (separator < 0) listOf(line) else listOf(line.substring(0, separator), line.substring(separator + 1))
        }
        if (rows.size != 2 || rows.map { it[0] }.toSet() != setOf("direct_kotlin", "compatibility")) {
            throw IllegalArgumentException("missing candidate route")
        }
        return rows.associate { row -> row[0] to row[1].split(":") }
    }

    /**
     * `candidate_runner.check_route`: a route may present the staged artifacts it is allowed to
     * present, and nothing from upstream dyn4j or from outside the staging repository.
     */
    fun checkRoute(route: String, paths: List<String>, stagingRoot: String) {
        val resolved = paths.map { PerformancePaths.normalize(it) }
        val root = PerformancePaths.normalize(stagingRoot)
        val core = PerformancePaths.normalize(PerformancePaths.join(root, coreArtifact))
        val api = PerformancePaths.normalize(PerformancePaths.join(root, apiArtifact))
        when (route) {
            "direct_kotlin" -> {
                if (resolved.count { it == core } != 1 || resolved.count { it == api } != 1) {
                    throw IllegalArgumentException("direct Kotlin route lacks its staged API and core artifacts")
                }
            }
            "compatibility" -> {
                if (resolved.count { it == core } != 1 || api in resolved) {
                    throw IllegalArgumentException("Java compatibility route has a missing or crossed provider")
                }
            }
            else -> throw IllegalArgumentException("unknown candidate route: $route")
        }
        if (resolved.any {
                PerformancePaths.name(it).startsWith("dyn4j-") && PerformancePaths.suffix(it) == ".jar"
            }
        ) {
            throw IllegalArgumentException("upstream dyn4j artifact is on a candidate route")
        }
        if (resolved.any { path ->
                PerformancePaths.suffix(path) == ".jar" &&
                    "rubixhacker" in PerformancePaths.parts(path) &&
                    !PerformancePaths.isRelativeTo(path, root)
            }
        ) {
            throw IllegalArgumentException("candidate artifact came from outside the staging repository")
        }
    }

    private fun hexToBytes(hex: String): ByteArray =
        ByteArray(hex.length / 2) { index ->
            hex.substring(index * 2, index * 2 + 2).toInt(16).toByte()
        }
}

/**
 * Incremental SHA-256, so `hash_path` can digest a directory as `digest.update(...)` calls
 * without materialising the concatenation.
 */
class Sha256Stream {
    private val buffer = okio.Buffer()

    fun update(bytes: ByteArray) {
        buffer.write(bytes)
    }

    fun hexDigest(): String = buffer.readByteString().sha256().hex()
}
