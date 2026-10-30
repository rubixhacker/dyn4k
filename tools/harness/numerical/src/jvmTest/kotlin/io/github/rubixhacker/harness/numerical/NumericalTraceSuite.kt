package io.github.rubixhacker.harness.numerical

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Sha256
import java.nio.file.Files
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

/**
 * The host half of `receipt`: trace reading, artifact digests, and the build configuration
 * digest. Python computes the same values in `receipt.records`, `receipt.digest` and
 * `receipt.seal`.
 */
val NumericalTraceContract by testSuite {
    test("a trace line keeps its newline so error positions match CPython") {
        val failure = assertFailsWith<Rejected> { records(listOf("{\"a\":\n")) }
        assertEquals("line 1: Expecting value: line 2 column 1 (char 6)", failure.message)
        assertEquals(
            "line 1: Expecting value: line 1 column 6 (char 5)",
            assertFailsWith<Rejected> { records(listOf("{\"a\":")) }.message,
        )
        assertEquals(1, records(listOf("{\"a\":1}\n")).size)
    }

    test("a file without a final newline is rejected") {
        val directory = Files.createTempDirectory("numerical-trace")
        try {
            val path = directory.resolve("trace.jsonl")
            Files.writeString(path, "{\"a\":1}\n{\"a\":2}")
            val failure = assertFailsWith<Rejected> { NumericalTrace.linesOf(path) }
            assertEquals("line 2 has no newline", failure.message)
            Files.writeString(path, "{\"a\":1}\n{\"a\":2}\n")
            assertEquals(2, NumericalTrace.recordsOf(path).size)
        } finally {
            directory.toFile().deleteRecursively()
        }
    }

    test("the build configuration digest joins each file with a NUL separator") {
        val directory = Files.createTempDirectory("numerical-build")
        try {
            Files.writeString(directory.resolve("settings.gradle.kts"), "rootProject.name = \"x\"\n")
            Files.writeString(directory.resolve("build.gradle.kts"), "plugins {}\n")
            val expected = "settings.gradle.kts".toByteArray() + byteArrayOf(0) +
                "rootProject.name = \"x\"\n".toByteArray() +
                "build.gradle.kts".toByteArray() + byteArrayOf(0) + "plugins {}\n".toByteArray()
            assertEquals(expected.toList(), NumericalTrace.buildConfigData(directory).toList())
            assertEquals(
                Sha256.of(expected),
                NumericalTrace.buildConfigSha256(directory),
            )
        } finally {
            directory.toFile().deleteRecursively()
        }
    }

    test("an artifact digest is the streaming SHA-256 of its bytes") {
        val directory = Files.createTempDirectory("numerical-digest")
        try {
            val artifact = directory.resolve("jvm.jar")
            Files.write(artifact, "staged artifact".toByteArray())
            assertEquals(Sha256.of("staged artifact"), NumericalTrace.digest(artifact))
        } finally {
            directory.toFile().deleteRecursively()
        }
    }
}
