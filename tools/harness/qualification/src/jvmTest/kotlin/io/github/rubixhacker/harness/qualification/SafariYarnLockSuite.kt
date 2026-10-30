package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * `tools/qualification/safari_yarn_lock.py`, first slice: the pure contract and the POSIX source
 * and process helpers.
 *
 * The suite is the reference's own expectations where a value is computed
 * (`SafariYarnLockVectors`, generated at the recorded revision); the host cases build their own
 * checkout so no Python runs.
 */
val SafariYarnLockContract by testSuite {
    test("the frozen lock, package, and context contract matches the reference") {
        val vector = SafariYarnLockVectors
        assertEquals(vector.TRACKED_LOCK, SafariYarnLockRules.TRACKED_LOCK)
        assertEquals(vector.GENERATED_LOCK, SafariYarnLockRules.GENERATED_LOCK)
        assertEquals(vector.SOURCE_INPUTS, SafariYarnLockRules.SOURCE_INPUTS)
        assertEquals(vector.REQUIRED_PACKAGES, SafariYarnLockRules.REQUIRED_PACKAGES)
        assertEquals(vector.REQUIRED_PACKAGE_INPUTS, SafariYarnLockRules.REQUIRED_PACKAGE_INPUTS)
        assertEquals(vector.CONTEXT_ROOTS, SafariYarnLockRules.CONTEXT_ROOTS)
        assertEquals(vector.LOCK_ERROR_LINE, SafariYarnLockRules.LOCK_ERROR_LINE)
        assertEquals(vector.HOSTED_TASK_MARKERS, SafariYarnLockRules.HOSTED_TASK_MARKERS)
        assertEquals(
            vector.CONTEXT_BOUNDS,
            listOf(
                SafariYarnLockRules.CONTEXT_MAX_FILES,
                SafariYarnLockRules.CONTEXT_MAX_FILE_BYTES,
                SafariYarnLockRules.CONTEXT_MAX_TOTAL_BYTES,
                SafariYarnLockRules.CONTEXT_MAX_ENTRIES,
                SafariYarnLockRules.CONTEXT_MAX_DEPTH,
                SafariYarnLockRules.CONTEXT_MAX_SECONDS,
                SafariYarnLockRules.CONTEXT_MAX_LAUNCHES,
                SafariYarnLockRules.CONTEXT_MAX_RAW_ENTRIES,
                SafariYarnLockRules.CONTEXT_MAX_UPLOAD_BYTES,
                SafariYarnLockRules.CONTEXT_MAX_INVENTORY_BYTES,
            ),
        )
        assertEquals(vector.MAX_FILE_BYTES, SafariYarnLockRules.MAX_FILE_BYTES)
        assertEquals(vector.MAX_PACKAGES, SafariYarnLockRules.MAX_PACKAGES)
        assertEquals(vector.MAX_PROCESS_SECONDS, SafariYarnLockRules.MAX_PROCESS_SECONDS)
        assertEquals(vector.MAX_DRAIN_SECONDS, SafariYarnLockRules.MAX_DRAIN_SECONDS)
        assertEquals(
            vector.WINDOWS_KILL_JOB_ON_CLOSE,
            SafariYarnLockRules.WINDOWS_KILL_JOB_ON_CLOSE,
        )
        assertEquals(
            vector.WINDOWS_CREATE_SUSPENDED,
            SafariYarnLockRules.WINDOWS_CREATE_SUSPENDED,
        )
        // The port substitutes Kotlin sources for the archived Python tools; the ledger keeps the
        // launch script and the archived workflow document at their own paths.
        assertTrue("tools/qualification/safari-launch.sh" in SafariYarnLockRules.HOSTED_SOURCE_INPUTS)
        assertTrue(
            SafariYarnLockRules.HOSTED_SOURCE_INPUTS.none { it.endsWith("full_hosted.py") },
            "the port must not archive the Python full_hosted module",
        )
        assertTrue(
            SafariYarnLockRules.HOSTED_SOURCE_INPUTS.any { it.endsWith("FullHosted.kt") },
        )
    }

    test("the hosted archive inventory matches the reference for both configurations") {
        for ((configuration, expected) in SafariYarnLockVectors.HOSTED_EXPECTED_FILES) {
            val sourceInputs = listOf(SafariYarnLockRules.TRACKED_LOCK) +
                SafariYarnLockRules.SOURCE_INPUTS +
                SafariYarnLockRules.HOSTED_SOURCE_INPUTS
            assertEquals(
                expected,
                SafariYarnLockRules.hostedExpectedFiles(
                    configuration,
                    SafariYarnLockRules.TRACKED_LOCK,
                    SafariYarnLockRules.GENERATED_LOCK,
                    sourceInputs,
                    SafariYarnLockRules.REQUIRED_PACKAGE_INPUTS,
                ),
                configuration,
            )
        }
    }

    test("the hosted task markers carry the lock-store outcome") {
        assertEquals(
            SafariYarnLockVectors.MARKERS_PASSED,
            SafariYarnLockRules.hostedTaskMarkers(0L),
        )
        assertEquals(
            SafariYarnLockVectors.MARKERS_FAILED,
            SafariYarnLockRules.hostedTaskMarkers(1L),
        )
        assertEquals(
            SafariYarnLockVectors.MARKERS_FAILED,
            SafariYarnLockRules.hostedTaskMarkers(null),
        )
    }

    test("the Safari capture timeout and output overflow predicates match the reference") {
        for (case in SafariYarnLockVectors.TIMEOUT_CASES) {
            assertEquals(
                case.expected,
                SafariYarnLockRules.safariCaptureTimeout(case.stdout, case.stderr),
                "timeout ${case.label}",
            )
        }
        for (case in SafariYarnLockVectors.OVERFLOW_CASES) {
            assertEquals(
                case.expected,
                SafariYarnLockRules.safariOutputOverflow(case.stdout, case.stderr),
                "overflow ${case.label}",
            )
        }
    }

    test("the hosted command is the exact Safari source command") {
        for ((configuration, expected) in SafariYarnLockVectors.FULL_HOSTED_COMMANDS) {
            assertEquals(
                expected,
                SafariYarnLockRules.fullHostedCommand(
                    "/repo",
                    "/tmp/qualification.init.gradle",
                    configuration,
                    "a".repeat(32),
                ),
                configuration,
            )
        }
    }

    test("the lock failure signature accepts only the Yarn plugin mismatch") {
        for (case in SafariYarnLockVectors.LOCK_SIGNATURE_CASES) {
            assertEquals(
                case.expected,
                SafariYarnLockHost.lockFailureSignature(case.stderr),
                case.label,
            )
        }
    }

    test("a diagnostic source read rejects escaping, symbolic, and oversized inputs") {
        safariTemp { root ->
            hostedGit(root, "init", "-q")
            Files.writeString(root.resolve("build.gradle.kts"), "plugins {}\n")
            Files.createDirectories(root.resolve("kotlin-js-store"))
            Files.writeString(root.resolve("kotlin-js-store/yarn.lock"), "# lock\n")
            Files.createSymbolicLink(root.resolve("linked.txt"), root.resolve("build.gradle.kts"))
            assertEquals("plugins {}\n", String(SafariYarnLockHost.sourceBytes(root, "build.gradle.kts")))
            assertEquals(
                "unsafe source path: ../escape",
                assertFailsWith<IllegalArgumentException> {
                    SafariYarnLockHost.sourcePath(root, "../escape")
                }.message,
            )
            assertEquals(
                "symlink source path or ancestor: linked.txt",
                assertFailsWith<IllegalArgumentException> {
                    SafariYarnLockHost.sourcePath(root, "linked.txt")
                }.message,
            )
            val copied = SafariYarnLockHost.copyFile(
                root, "kotlin-js-store/yarn.lock", root.resolve("archive"), "tracked",
            )
            assertEquals(
                "tracked/kotlin-js-store/yarn.lock",
                Py.str(copied["path"]),
            )
            assertEquals(
                SafariYarnLockHost.sourceDigest(root, "kotlin-js-store/yarn.lock"),
                Py.str(copied["sha256"]),
            )
        }
    }

    test("the candidate gate rejects a foreign commit and a dirty checkout") {
        safariTemp { root ->
            hostedGit(root, "init", "-q")
            Files.createDirectories(root.resolve("kotlin-js-store"))
            Files.writeString(root.resolve("kotlin-js-store/yarn.lock"), "# lock\n")
            hostedGit(root, "add", ".")
            hostedGit(
                root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "-qm", "base",
            )
            val head = hostedGit(root, "rev-parse", "HEAD").trim()
            SafariYarnLockHost.requireCandidate(root, head)
            assertEquals(
                "candidate SHA differs from checkout",
                assertFailsWith<IllegalArgumentException> {
                    SafariYarnLockHost.requireCandidate(root, "0".repeat(40))
                }.message,
            )
            Files.writeString(root.resolve("extra.txt"), "untracked\n")
            assertEquals(
                "dirty tracked or untracked source checkout",
                assertFailsWith<IllegalArgumentException> {
                    SafariYarnLockHost.requireCandidate(root, head)
                }.message,
            )
        }
    }

    test("the lock task reports a bounded drain and a deadline kill") {
        safariTemp { root ->
            hostedGit(root, "init", "-q")
            Files.writeString(root.resolve("README.md"), "fixture\n")
            val output = root.resolve("evidence")
            val quick = SafariYarnLockHost.runLockTask(
                root,
                output,
                listOf("sh", "-c", "printf 'one\\ntwo\\n'; printf 'err\\n' >&2; exit 3"),
                windows = false,
            )
            assertEquals("3", Py.int(quick["exit_code"]!!).toString())
            assertEquals(false, Py.truthy(quick["timed_out"]))
            assertEquals(false, Py.truthy(quick["stream_incomplete"]))
            assertEquals(false, Py.truthy(quick["stdout_truncated"]))
            assertEquals("one\ntwo\n", Files.readString(output.resolve("stdout.txt")))
            assertEquals("err\n", Files.readString(output.resolve("stderr.txt")))
            assertTrue(Py.int(quick["stdout_bytes_seen"]!!) >= 8)
            val stalled = SafariYarnLockHost.runLockTask(
                root,
                root.resolve("stalled"),
                listOf("sh", "-c", "printf 'partial'; sleep 30"),
                deadlineSeconds = 1,
                windows = false,
            )
            assertEquals(true, Py.truthy(stalled["timed_out"]))
            assertEquals("1", Py.int(stalled["deadline_seconds"]!!).toString())
            val oversized = SafariYarnLockHost.runLockTask(
                root,
                root.resolve("oversized"),
                listOf("sh", "-c", "yes x | head -c 12000000"),
                windows = false,
            )
            assertEquals(0L, Py.int(oversized["exit_code"]!!))
            assertEquals(
                SafariYarnLockRules.MAX_FILE_BYTES.toLong(),
                Files.size(root.resolve("oversized/stdout.txt")),
            )
            assertEquals(true, Py.truthy(oversized["stdout_truncated"]))
            assertTrue(
                Py.int(oversized["stdout_bytes_seen"]!!) > SafariYarnLockRules.MAX_FILE_BYTES,
            )
        }
    }

    test("the Windows lock task fails closed") {
        safariTemp { root ->
            val error = assertFailsWith<UnsupportedOperationException> {
                SafariYarnLockHost.runLockTask(root, root.resolve("out"), windows = true)
            }
            assertTrue("Windows job-object runner" in (error.message ?: ""))
        }
    }
}

private fun safariTemp(block: (Path) -> Unit) {
    val root = Files.createTempDirectory("safari-yarn-lock")
    try {
        block(root)
    } finally {
        Files.walk(root).use { walk ->
            walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
        }
    }
}
