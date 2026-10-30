package io.github.rubixhacker.harness.compatibility

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Sha256
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertFailsWith

/** The repository filesystem, used only to hold the port against the frozen sources on disk. */
private class JvmCorpusFiles : CorpusFiles {
    override fun isSymlink(path: String): Boolean = Files.isSymbolicLink(Path.of(path))
    override fun isFile(path: String): Boolean = Files.isRegularFile(Path.of(path))
    override fun digest(path: String): String = Sha256.of(Files.readAllBytes(Path.of(path)))
    override fun readText(path: String): String = Files.readString(Path.of(path))

    override fun filesBelow(root: String): List<String> {
        val base = Path.of(root)
        val result = mutableListOf<String>()
        Files.walk(base).use { stream ->
            val iterator = stream.iterator()
            while (iterator.hasNext()) {
                val path = iterator.next()
                if (Files.isRegularFile(path)) result.add(base.relativize(path).toString())
            }
        }
        return result
    }
}

internal fun repositoryRoot(): Path {
    var directory: Path? = Path.of("").toAbsolutePath()
    while (directory != null) {
        if (Files.isRegularFile(directory.resolve("docs/specs/harness-port.md"))) return directory
        directory = directory.parent
    }
    error("repository root not found from ${Path.of("").toAbsolutePath()}")
}

/**
 * The repository half of `test_world_ci.py` case 1: the twelve frozen World sources on disk still
 * hash to the frozen inventory, and a changed expectation is rejected.
 */
val WorldCiRepositoryContract by testSuite {
    test("frozen world sources on disk match the frozen inventory") {
        val root = repositoryRoot()
        val files = JvmCorpusFiles()
        WorldCi.validateSources(files, root.resolve(WorldCi.SOURCE_ROOT).toString(), WorldCi.SOURCE_SHA)

        val changed = WorldCi.SOURCE_SHA.toMutableMap().apply {
            put("WorldListSemanticsConsumer.java", "0".repeat(64))
        }
        val thrown = assertFailsWith<IllegalArgumentException> {
            WorldCi.validateSources(files, root.resolve(WorldCi.SOURCE_ROOT).toString(), changed)
        }
        kotlin.test.assertEquals(
            "World source differs: WorldListSemanticsConsumer.java",
            thrown.message,
        )
    }
}
