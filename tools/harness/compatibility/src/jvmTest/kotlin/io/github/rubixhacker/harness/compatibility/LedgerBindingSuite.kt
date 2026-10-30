package io.github.rubixhacker.harness.compatibility

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okio.ByteString.Companion.decodeBase64
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.util.zip.ZipFile
import kotlin.io.path.createDirectories
import kotlin.io.path.writeText
import kotlin.test.assertEquals

/**
 * The git-backed binding check of `ledger.candidate_source_binding`, replayed against the fixed-date
 * repository the vector records.
 */
val LedgerBindingContract by testSuite {
    test("candidate source binding follows the recorded HEAD") {
        val recorded = Vectors.ledger.obj("binding")
        val root = Files.createTempDirectory("dyn4k-ledger-binding-")
        try {
            val environment = mapOf(
                "GIT_AUTHOR_NAME" to "t",
                "GIT_AUTHOR_EMAIL" to "t@example.com",
                "GIT_COMMITTER_NAME" to "t",
                "GIT_COMMITTER_EMAIL" to "t@example.com",
                "GIT_AUTHOR_DATE" to "2020-01-01T00:00:00 +0000",
                "GIT_COMMITTER_DATE" to "2020-01-01T00:00:00 +0000",
            )
            Processes.run(listOf("git", "init", "-q", root.toString()), check = true)
            root.resolve("file.txt").writeText("first\n", StandardCharsets.UTF_8)
            Processes.run(listOf("git", "-C", root.toString(), "add", "file.txt"), check = true)
            Processes.run(
                listOf("git", "-C", root.toString(), "commit", "-q", "-m", "first"),
                environment = environment,
                check = true,
            )
            val head = Processes.git(root.toString(), "rev-parse", "HEAD")
            val tree = Processes.git(root.toString(), "rev-parse", "HEAD^{tree}")
            assertEquals(recorded.str("head"), head)
            assertEquals(recorded.str("tree"), tree)
            root.resolve("file.txt").writeText("second\n", StandardCharsets.UTF_8)
            Processes.run(
                listOf("git", "-C", root.toString(), "commit", "-qam", "second"),
                environment = environment,
                check = true,
            )
            assertEquals(recorded.str("second"), Processes.git(root.toString(), "rev-parse", "HEAD"))

            for (case in recorded.array("cases").map { it.jsonObject }) {
                val source = case.obj("source")
                val (status, reason) = LedgerHost.candidateSourceBinding(
                    source,
                    case.str("requested"),
                    root.toString(),
                )
                assertEquals(case.str("status"), status, case.str("case"))
                assertEquals(case.textOrNull("reason"), reason, case.str("case"))
            }
        } finally {
            deleteTree(root)
        }
    }
}

/** The UID mutation of `exception_ci.mutate_uid`, checked against the recorded archive contents. */
val ExceptionCiHostContract by testSuite {
    test("uid mutation rewrites exactly the pinned class") {
        val recorded = Vectors.exceptionCi
        val directory = Files.createTempDirectory("dyn4k-uid-")
        try {
            val source = directory.resolve("source.jar")
            Files.write(source, recorded.str("uid_source_base64").decodeBase64()!!.toByteArray())
            val target = directory.resolve("target.jar")
            ExceptionCiHost.mutateUid(source.toString(), target.toString())
            val expected = recorded.obj("mutated_entries").mapValues { it.value.jsonPrimitive.content }
            val observed = ZipFile(target.toFile()).use { archive ->
                archive.entries().asSequence().associate { entry ->
                    entry.name to Sha256.of(archive.getInputStream(entry).use { it.readBytes() })
                }
            }
            assertEquals(expected, observed)
        } finally {
            deleteTree(directory)
        }
    }
}
