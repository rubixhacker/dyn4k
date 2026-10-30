package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals

/**
 * The programmatic staging fixture (`StagedPublicationFixture.kt`): the reference's `stage()` tree
 * must audit as `PASSED` for the recorded tuple and for an Apple target the recorded archives do
 * not carry.
 */
val PublicationFixture by testSuite {
    test("the generated staging tree audits as passed for jvm and js") {
        fixtureTemp { root ->
            val tree = stagedPublication(root, listOf("jvm", "js"))
            val audit = StagingAudit.audit(
                tree.staging,
                FIXTURE_CANDIDATE,
                tree.targets,
                root.resolve("LICENSE.md"),
                tree.receipt,
                tree.console,
            )
            assertEquals("PASSED", Py.str(audit["status"]), audit["errors"].toString())
        }
    }

    test("the generated staging tree audits as passed for jvm and iosArm64") {
        fixtureTemp { root ->
            val tree = stagedPublication(root, listOf("jvm", "iosArm64"))
            val audit = StagingAudit.audit(
                tree.staging,
                FIXTURE_CANDIDATE,
                tree.targets,
                root.resolve("LICENSE.md"),
                tree.receipt,
                tree.console,
            )
            assertEquals("PASSED", Py.str(audit["status"]), audit["errors"].toString())
        }
    }
}

private fun fixtureTemp(block: (Path) -> Unit) {
    val root = Files.createTempDirectory("publication-fixture")
    try {
        block(root)
    } finally {
        Files.walk(root).use { walk ->
            walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
        }
    }
}
