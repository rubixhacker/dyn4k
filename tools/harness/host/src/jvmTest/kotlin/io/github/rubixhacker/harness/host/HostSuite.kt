package io.github.rubixhacker.harness.host

import de.infix.testBalloon.framework.core.testSuite
import java.io.File
import java.nio.file.Files
import kotlin.io.path.createDirectories
import kotlin.io.path.writeText
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

private class GitRepository {
    val root: File = Files.createTempDirectory("clean-checkout").toFile()

    init {
        git("init", "-q")
        git("config", "user.email", "harness@example.invalid")
        git("config", "user.name", "Harness")
    }

    fun git(vararg arguments: String): String {
        val process = ProcessBuilder(listOf("git", "-C", root.absolutePath) + arguments)
            .redirectErrorStream(true)
            .start()
        val output = process.inputStream.bufferedReader().use { it.readText() }
        check(process.waitFor() == 0) { "git ${arguments.joinToString(" ")} failed: $output" }
        return output
    }

    fun commitAll(): String {
        git("add", "-A")
        git("commit", "-q", "-m", "candidate")
        return git("rev-parse", "HEAD").trim()
    }

    fun write(relative: String, text: String) {
        val path = root.resolve(relative)
        path.parentFile?.toPath()?.createDirectories()
        path.toPath().writeText(text)
    }
}

val CleanCheckoutContract by testSuite {
    test("a clean checkout passes") {
        val repository = GitRepository()
        repository.write("README.md", "candidate\n")
        val sha = repository.commitAll()
        CleanCheckout.require(repository.root, sha)
    }

    test("a candidate SHA that differs from HEAD is rejected") {
        val repository = GitRepository()
        repository.write("README.md", "candidate\n")
        repository.commitAll()
        val error = assertFailsWith<IllegalArgumentException> {
            CleanCheckout.require(repository.root, "0".repeat(40))
        }
        assertEquals(true, error.message!!.startsWith("candidate SHA differs from checkout "))
    }

    test("a modified tracked file is rejected") {
        val repository = GitRepository()
        repository.write("README.md", "candidate\n")
        val sha = repository.commitAll()
        repository.write("README.md", "changed\n")
        val error = assertFailsWith<IllegalArgumentException> {
            CleanCheckout.require(repository.root, sha)
        }
        assertEquals(true, error.message!!.startsWith("dirty tracked checkout invalidates candidate evidence: "))
    }

    test("an untracked input is rejected") {
        val repository = GitRepository()
        repository.write("README.md", "candidate\n")
        val sha = repository.commitAll()
        repository.write("notes.txt", "input\n")
        val error = assertFailsWith<IllegalArgumentException> {
            CleanCheckout.require(repository.root, sha)
        }
        assertEquals(true, error.message!!.startsWith("untracked checkout inputs invalidate candidate evidence: "))
    }

    test("generated build output is not an input") {
        val repository = GitRepository()
        repository.write("README.md", "candidate\n")
        val sha = repository.commitAll()
        repository.write("build/output.txt", "generated\n")
        repository.write("dyn4k-core/.gradle/state.txt", "generated\n")
        repository.write("tools/qualification/__pycache__/module.cpython-313.pyc", "generated\n")
        CleanCheckout.require(repository.root, sha)
    }
}

val FileDigestContract by testSuite {
    test("file digest matches the in-memory digest") {
        val file = Files.createTempFile("digest", ".bin")
        file.toFile().writeBytes("abc".toByteArray())
        assertEquals(
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            FileDigest.sha256(file),
        )
    }

    test("streamed large file digest is stable") {
        val file = Files.createTempFile("digest-large", ".bin")
        val bytes = ByteArray(4 * 1024 * 1024) { (it * 17).toByte() }
        file.toFile().writeBytes(bytes)
        assertEquals(
            io.github.rubixhacker.harness.contract.Sha256.of(bytes),
            FileDigest.sha256(file),
        )
    }
}
