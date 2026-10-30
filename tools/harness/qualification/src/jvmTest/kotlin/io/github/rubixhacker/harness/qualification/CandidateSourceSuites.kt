package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Sha256
import java.nio.file.Files
import java.nio.file.Path
import kotlin.io.path.writeText
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * `qualify.candidate_source_contract` on a Git checkout.
 *
 * A sources archive must hash committed blob bytes: a working-tree edit, a line-ending
 * substitution, or a replacement object cannot change what the archive is compared against.
 */
val CandidateSourceContract by testSuite {
    test("committed blob bytes win over a changed working tree") {
        withRepository(
            mapOf(
                "dyn4k-core/src/commonMain/kotlin/api/Type.kt" to "class Type\n",
                "dyn4k-core/src/jvmModule/java/module-info.java" to "module dyn4k.core {}\n",
                "dyn4k/src/commonMain/kotlin/api/Other.kt" to "class Other\n",
                ".gitattributes" to "*.kt -text\n",
            ),
        ) { repository ->
            val sha = commit(repository)
            val before = CandidateSource.contract(repository, sha)
            assertEquals(Sha256.of("class Type\n"), before.getValue("dyn4k-core")["commonMain/api/Type.kt"])
            assertEquals(
                Sha256.of("module dyn4k.core {}\n"),
                before.getValue("dyn4k-core")["jvmModule/module-info.java"],
            )
            assertEquals(Sha256.of("class Other\n"), before.getValue("dyn4k")["commonMain/api/Other.kt"])

            repository.resolve("dyn4k-core/src/commonMain/kotlin/api/Type.kt")
                .writeText("class Type\r\nchanged in the working tree\r\n")
            assertEquals(before, CandidateSource.contract(repository, sha))
        }
    }

    test("an uncommitted source file is not part of the contract") {
        withRepository(
            mapOf(
                "dyn4k-core/src/commonMain/kotlin/api/Type.kt" to "class Type\n",
                "dyn4k/src/commonMain/kotlin/api/Other.kt" to "class Other\n",
            ),
        ) { repository ->
            val sha = commit(repository)
            repository.resolve("dyn4k-core/src/commonMain/kotlin/api/Extra.kt")
                .writeText("class Extra\n")
            val contract = CandidateSource.contract(repository, sha)
            assertTrue("commonMain/api/Extra.kt" !in contract.getValue("dyn4k-core"))
        }
    }

    test("a short SHA is rejected") {
        withRepository(
            mapOf(
                "dyn4k-core/src/commonMain/kotlin/api/Type.kt" to "class Type\n",
                "dyn4k/src/commonMain/kotlin/api/Other.kt" to "class Other\n",
            ),
        ) { repository ->
            val sha = commit(repository)
            val error = assertFailsWith<IllegalArgumentException> {
                CandidateSource.contract(repository, sha.take(12))
            }
            assertEquals("candidate source requires full SHA-1 commit and tree IDs", error.message)
        }
    }

    test("two source languages cannot publish one archive path") {
        withRepository(
            mapOf(
                "dyn4k-core/src/commonMain/kotlin/api/Type.kt" to "class Type\n",
                "dyn4k-core/src/commonMain/java/api/Type.kt" to "class Type\n",
                "dyn4k/src/commonMain/kotlin/api/Other.kt" to "class Other\n",
            ),
        ) { repository ->
            val sha = commit(repository)
            val error = assertFailsWith<IllegalArgumentException> {
                CandidateSource.contract(repository, sha)
            }
            assertEquals("duplicate candidate source path: commonMain/api/Type.kt", error.message)
        }
    }

    test("a checkout without one module's sources is rejected") {
        withRepository(
            mapOf("dyn4k-core/src/commonMain/kotlin/api/Type.kt" to "class Type\n"),
        ) { repository ->
            val sha = commit(repository)
            val error = assertFailsWith<IllegalArgumentException> {
                CandidateSource.contract(repository, sha)
            }
            assertEquals("candidate source tree is missing required module sources", error.message)
        }
    }

    test("the working-tree branch publishes only main source sets") {
        val repository = Files.createTempDirectory("candidate-tree")
        try {
            repository.resolve("dyn4k-core/src/commonMain/kotlin/api/Type.kt").also {
                Files.createDirectories(it.parent)
                it.writeText("class Type\n")
            }
            repository.resolve("dyn4k-core/src/commonTest/kotlin/api/TypeTest.kt").also {
                Files.createDirectories(it.parent)
                it.writeText("class TypeTest\n")
            }
            repository.resolve("dyn4k-core/src/jvmModule/java/module-info.java").also {
                Files.createDirectories(it.parent)
                it.writeText("module dyn4k.core {}\n")
            }
            repository.resolve("dyn4k/src/commonMain/kotlin/api/Other.kt").also {
                Files.createDirectories(it.parent)
                it.writeText("class Other\n")
            }
            val contract = CandidateSource.contract(repository, "a".repeat(40))
            assertEquals(setOf("commonMain/api/Type.kt", "jvmModule/module-info.java"),
                contract.getValue("dyn4k-core").keys)
            assertEquals(setOf("commonMain/api/Other.kt"), contract.getValue("dyn4k").keys)
            assertTrue("commonMain/api/TypeTest.kt" !in contract.getValue("dyn4k-core"))
        } finally {
            deleteRecursively(repository)
        }
    }
}

private fun withRepository(files: Map<String, String>, block: (Path) -> Unit) {
    val repository = Files.createTempDirectory("candidate-source")
    try {
        git(repository, "init", "-q")
        for ((path, content) in files) {
            val file = repository.resolve(path)
            Files.createDirectories(file.parent)
            file.writeText(content)
        }
        block(repository)
    } finally {
        deleteRecursively(repository)
    }
}

private fun commit(repository: Path): String {
    git(repository, "add", "-A")
    git(
        repository, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "-qm", "base",
    )
    return git(repository, "rev-parse", "HEAD").trim()
}

internal fun git(repository: Path, vararg arguments: String): String {
    val process = ProcessBuilder(listOf("git", "-C", repository.toString()) + arguments).start()
    val output = process.inputStream.use { it.readBytes() }
    val error = process.errorStream.use { it.readBytes() }
    check(process.waitFor() == 0) {
        "git ${arguments.joinToString(" ")} failed: ${String(error)}"
    }
    return String(output)
}
