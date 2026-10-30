package io.github.rubixhacker.harness.host

import java.io.File

/**
 * Checkout rules of `qualify.require_clean_checkout`.
 *
 * A candidate is usable only when HEAD equals the recorded commit, no tracked file is modified,
 * and no untracked input exists. Generated build output does not count as an input.
 */
object CleanCheckout {
    private val gradleRoots = listOf(
        "",
        "dyn4k/",
        "dyn4k-core/",
        "consumers/qualification/",
        "consumers/qualification/portable/",
    )

    private val generatedDirectories = listOf("build", ".gradle", ".kotlin")

    private val generatedPrefixes: List<String> =
        gradleRoots.flatMap { root -> generatedDirectories.map { directory -> "$root$directory/" } } +
            listOf("tools/qualification/__pycache__/")

    private val generatedFiles = setOf(
        "kotlin-js-store/yarn.lock",
        "consumers/qualification/portable/kotlin-js-store/yarn.lock",
    )

    /** Throws when the checkout cannot back candidate evidence. */
    fun require(repository: File, candidateSha: String) {
        val head = run(repository, "rev-parse", "HEAD").trim()
        if (head != candidateSha) {
            throw IllegalArgumentException("candidate SHA differs from checkout $head")
        }
        val tracked = run(repository, "status", "--porcelain=v1", "--untracked-files=no")
        if (tracked.isNotBlank()) {
            throw IllegalArgumentException(
                "dirty tracked checkout invalidates candidate evidence: ${tracked.trim()}",
            )
        }
        val untracked = run(repository, "ls-files", "--others", "-z")
        val relevant = untracked.split('\u0000')
            .filter { it.isNotEmpty() && it !in generatedFiles && generatedPrefixes.none { prefix -> it.startsWith(prefix) } }
        if (relevant.isNotEmpty()) {
            throw IllegalArgumentException(
                "untracked checkout inputs invalidate candidate evidence: ${relevant.take(5).joinToString(", ")}",
            )
        }
    }

    private fun run(repository: File, vararg arguments: String): String {
        val process = ProcessBuilder(listOf("git", "-C", repository.absolutePath) + arguments)
            .redirectErrorStream(false)
            .start()
        val output = process.inputStream.bufferedReader().use { it.readText() }
        val error = process.errorStream.bufferedReader().use { it.readText() }
        val status = process.waitFor()
        if (status != 0) {
            throw IllegalStateException("git ${arguments.joinToString(" ")} failed: ${error.trim()}")
        }
        return output
    }
}
