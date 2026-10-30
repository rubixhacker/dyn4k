package io.github.rubixhacker.harness.compatibility

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertFailsWith

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
