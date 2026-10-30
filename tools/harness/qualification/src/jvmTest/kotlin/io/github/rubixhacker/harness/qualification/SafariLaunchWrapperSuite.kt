package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import io.github.rubixhacker.harness.contract.CanonicalJson
import io.github.rubixhacker.harness.contract.StrictJson
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.attribute.PosixFilePermissions
import java.util.concurrent.TimeUnit
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * `tools/qualification/safari-launch.sh`: the macOS launcher wrapper and the launch context it
 * writes.
 *
 * The wrapper is the archived shell script, kept at its own path, so these cases run it under the
 * host's `bash` exactly as the reference's POSIX cases do. The reference's two Git Bash cases
 * (`git_bash_from_git`, `bash_executable`) have no counterpart here: the port runs the script
 * through the host shell and has no Git-for-Windows installation detection.
 */
private class WrapperRun(val returncode: Int, val stdout: ByteArray, val stderr: ByteArray)

private fun runWrapper(
    command: List<String>,
    context: Path?,
    pathPrefix: Path? = null,
): WrapperRun {
    val environment = LinkedHashMap(System.getenv())
    if (pathPrefix != null) {
        environment["PATH"] = pathPrefix.toString() +
            java.io.File.pathSeparator + (environment["PATH"] ?: "")
    }
    if (context == null) {
        environment.remove("DYN4K_SAFARI_LAUNCH_CONTEXT")
    } else {
        environment["DYN4K_SAFARI_LAUNCH_CONTEXT"] = context.toString()
    }
    val builder = ProcessBuilder(command)
    builder.environment().clear()
    builder.environment().putAll(environment)
    val process = builder.start()
    val stderrHolder = arrayOfNulls<ByteArray>(1)
    val stderrReader = Thread {
        stderrHolder[0] = process.errorStream.readBytes()
    }
    stderrReader.start()
    val stdout = process.inputStream.readBytes()
    assertTrue(process.waitFor(30, TimeUnit.SECONDS), "the wrapper did not finish")
    stderrReader.join(5_000)
    return WrapperRun(process.exitValue(), stdout, stderrHolder[0] ?: ByteArray(0))
}

private fun launcherSource(): String =
    Files.readString(repositoryRoot().resolve("tools/qualification/safari-launch.sh"))

private fun fixtureBash(root: Path, name: String, body: String): Path {
    val path = root.resolve(name)
    Files.write(path, body.toByteArray(StandardCharsets.UTF_8))
    Files.setPosixFilePermissions(path, PosixFilePermissions.fromString("rwxr-xr-x"))
    return path
}

/** The controlled launcher: the archived script with its macOS tools substituted. */
private fun controlledLauncher(root: Path, name: String, open: Path, extra: Map<String, String>): Path {
    var script = launcherSource()
        .replace("/usr/bin/open", open.toString())
        .replace("/bin/sleep 2", "/bin/sleep 0.01")
    for ((original, replacement) in extra) {
        script = script.replace(original, replacement)
    }
    return fixtureBash(root, name, script)
}

private fun redirectOf(root: Path): Path {
    val path = root.resolve("redirect.html")
    Files.writeString(path, "redirect\n")
    return path
}

private fun contextFiles(context: Path, prefix: String, suffix: String): List<Path> {
    if (!Files.isDirectory(context, LinkOption.NOFOLLOW_LINKS)) return emptyList()
    return Files.newDirectoryStream(context).use { stream ->
        stream.filter {
            val name = it.fileName.toString()
            name.startsWith(prefix) && name.endsWith(suffix)
        }.toList()
    }
}

private fun sampleCount(path: Path): Int =
    String(Files.readAllBytes(path), StandardCharsets.UTF_8).windowed(7).count { it == "sample=" }

/**
 * `wrapper_failure_context`: the bounded, redacted diagnostic an assertion prints.
 *
 * Only counts, categories, and booleans leave the fixture, so a failing case can never echo the
 * environment, a path, or the captured output into the test log.
 */
private fun wrapperFailureContext(result: WrapperRun, context: Path): String {
    val stderr = String(result.stderr, StandardCharsets.UTF_8)
    val stdout = String(result.stdout, StandardCharsets.UTF_8)
    val lowerStderr = stderr.lowercase()
    var stderrCategory = if (stderr.isNotEmpty()) "other" else "empty"
    for ((category, phrases) in listOf(
        "missing_path" to listOf("no such file", "cannot find the path"),
        "command_missing" to listOf("command not found", "is not recognized"),
        "permission" to listOf("permission denied", "access is denied"),
        "syntax" to listOf("syntax error", "unexpected token"),
    )) {
        if (phrases.any { it in lowerStderr }) {
            stderrCategory = category
            break
        }
    }
    val patterns = linkedMapOf(
        "launch" to ("launch-" to ".txt"),
        "redirect" to ("redirect-" to ".html"),
        "process" to ("process-" to ".txt"),
        "open_stdout" to ("open-" to ".stdout"),
        "open_stderr" to ("open-" to ".stderr"),
        "sample_final" to ("sample-state-" to ".txt"),
        "sample_temp" to ("sample-state-" to ".tmp"),
        "outcome" to ("launch-outcome-" to ".txt"),
        "outcome_temp" to ("launch-outcome-" to ".tmp"),
    )
    val launchFilename = Regex("launch-([0-9]{1,10})\\.txt")
    val contextExists = Files.isDirectory(context) && !Files.isSymbolicLink(context)
    val matches = LinkedHashMap<String, List<Path>>()
    for ((key, pattern) in patterns) {
        val candidates = if (contextExists) {
            contextFiles(context, pattern.first, pattern.second)
        } else {
            emptyList()
        }
        val bounded = if (key == "launch") {
            candidates.filter { launchFilename.matches(it.fileName.toString()) }
        } else {
            candidates
        }
        matches[key] = bounded.take(101)
    }
    fun firstBytes(key: String): ByteArray {
        val path = matches[key]?.firstOrNull() ?: return ByteArray(0)
        if (Files.isSymbolicLink(path) || !Files.isRegularFile(path)) return ByteArray(0)
        return try {
            Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS).use {
                it.readNBytes(4096)
            }
        } catch (error: java.io.IOException) {
            ByteArray(0)
        }
    }
    val process = firstBytes("process")
    val launch = firstBytes("launch")
    val outcome = firstBytes("outcome")
    val launchPid = Regex("(?:^|\n)pid=([0-9]{1,10})(?: |\n|$)")
        .find(String(launch, StandardCharsets.ISO_8859_1))
    val launchName = matches["launch"]?.firstOrNull()
        ?.let { launchFilename.matchEntire(it.fileName.toString()) }
    val pidMatches = if (launchPid != null && launchName != null) {
        launchPid.groupValues[1] == launchName.groupValues[1]
    } else {
        null
    }
    val processText = String(process, StandardCharsets.ISO_8859_1)
    val outcomeText = String(outcome, StandardCharsets.ISO_8859_1)
    val detail = buildJsonObject {
        put(
            "returncode",
            if (result.returncode in -999..999) JsonPrimitive(result.returncode) else JsonNull,
        )
        put("stdout_length", JsonPrimitive(minOf(stdout.length, 4097)))
        put("stderr_length", JsonPrimitive(minOf(stderr.length, 4097)))
        put("stderr_category", JsonPrimitive(stderrCategory))
        put("context_exists", JsonPrimitive(contextExists))
        put(
            "files",
            JsonObject(
                LinkedHashMap(matches.mapValues { (_, paths) -> JsonPrimitive(minOf(paths.size, 101)) }),
            ),
        )
        put("launch_pid_matches_name", pidMatches?.let { JsonPrimitive(it) } ?: JsonNull)
        put(
            "process_sample_count",
            JsonPrimitive(
                minOf(Regex("(?m)^sample=").findAll(processText).count(), 101),
            ),
        )
        put(
            "process_markers",
            JsonObject(
                LinkedHashMap(
                    listOf(
                        "sample_state_write_failed",
                        "sample_state_verify_failed",
                        "sample_state_rename_failed",
                        "sample_state_cleanup_failed",
                    ).associateWith { JsonPrimitive(it in processText) },
                ),
            ),
        )
        put("outcome_finished", JsonPrimitive("open_state=finished\n" in outcomeText))
        put("outcome_pending", JsonPrimitive("open_state=pending\n" in outcomeText))
    }
    return CanonicalJson.render(detail)
}

/** The launcher wrapper's POSIX cases: it joins its sampler, records it, and refuses failures. */
val SafariLaunchWrapper by testSuite {
    test("the wrapper joins an early failed launch before returning") {
        val root = Files.createTempDirectory("safari-wrapper")
        try {
            val open = fixtureBash(root, "fake-open", "#!/bin/bash\nexit 23\n")
            val controlled = controlledLauncher(root, "controlled-launch.sh", open, emptyMap())
            val redirect = redirectOf(root)
            val context = root.resolve("launch-context")
            val result = runWrapper(listOf("bash", controlled.toString(), redirect.toString()), context)
            assertEquals(23, result.returncode)
            val state = contextFiles(context, "sample-state-", ".txt")
            assertEquals(1, state.size)
            assertTrue("samples_completed=5" in Files.readString(state[0]))
            assertTrue("sampler_exit=0" in Files.readString(state[0]))
            val process = contextFiles(context, "process-", ".txt")
            assertEquals(1, process.size)
            assertEquals(5, sampleCount(process[0]))
            val normal = runWrapper(listOf("bash", controlled.toString(), redirect.toString()), null)
            assertEquals(23, normal.returncode)
            assertEquals(1, contextFiles(context, "sample-state-", ".txt").size)
        } finally {
            deleteTree(root)
        }
    }

    test("the wrapper rejects a failed sample write and rename") {
        val root = Files.createTempDirectory("safari-wrapper")
        try {
            val open = fixtureBash(root, "fake-open", "#!/bin/bash\nexit 23\n")
            val redirect = redirectOf(root)
            for ((failure, function, original, replacement, marker) in listOf(
                listOf(
                    "write_error",
                    "record_sample() { /usr/bin/printf 'partial'; return 17; }",
                    "/usr/bin/printf 'samples_completed=%s",
                    "record_sample 'samples_completed=%s",
                    "sample_state_write_failed",
                ),
                listOf(
                    "short_write",
                    "record_sample() { /usr/bin/printf 'partial'; }",
                    "/usr/bin/printf 'samples_completed=%s",
                    "record_sample 'samples_completed=%s",
                    "sample_state_verify_failed",
                ),
                listOf(
                    "rename_error",
                    "rename_sample() { return 19; }",
                    "/bin/mv \"\$context/sample-state-\$\$.tmp\" \"\$context/sample-state-\$\$.txt\"",
                    "rename_sample \"\$context/sample-state-\$\$.tmp\" " +
                        "\"\$context/sample-state-\$\$.txt\"",
                    "sample_state_rename_failed",
                ),
            )) {
                val context = root.resolve(failure)
                var script = launcherSource()
                    .replace("/usr/bin/open", open.toString())
                    .replace("/bin/sleep 2", "/bin/sleep 0.01")
                assertTrue(original in script)
                script = script.replace(original, replacement).replace(
                    "set -euo pipefail\n",
                    "set -euo pipefail\n" + function + "\n",
                )
                val controlled = fixtureBash(root, "controlled-$failure.sh", script)
                val result = runWrapper(
                    listOf("bash", controlled.toString(), redirect.toString()),
                    context,
                )
                assertEquals(23, result.returncode, wrapperFailureContext(result, context))
                assertEquals(emptyList(), contextFiles(context, "sample-state-", ".txt"))
                assertEquals(emptyList(), contextFiles(context, "sample-state-", ".tmp"))
                val process = contextFiles(context, "process-", ".txt")
                assertEquals(1, process.size)
                assertTrue(marker in Files.readString(process[0]))
                assertEquals(5, sampleCount(process[0]))
                val outcome = contextFiles(context, "launch-outcome-", ".txt")
                assertEquals(1, outcome.size)
                assertEquals(
                    "open_state=finished\nopen_exit=23\n",
                    Files.readString(outcome[0]),
                )
            }
        } finally {
            deleteTree(root)
        }
    }

    test("the wrapper reports a sampler failure after a successful open") {
        val root = Files.createTempDirectory("safari-wrapper")
        try {
            val open = fixtureBash(root, "fake-open", "#!/bin/bash\nexit 0\n")
            val controlled = controlledLauncher(
                root,
                "controlled-failed-sampler.sh",
                open,
                mapOf(
                    "/usr/bin/printf 'samples_completed=%s" to "record_sample 'samples_completed=%s",
                    "set -euo pipefail\n" to
                        "set -euo pipefail\nrecord_sample() { return 17; }\n",
                ),
            )
            val redirect = redirectOf(root)
            val context = root.resolve("failed-sampler")
            val result = runWrapper(
                listOf("bash", controlled.toString(), redirect.toString()),
                context,
            )
            assertEquals(1, result.returncode, wrapperFailureContext(result, context))
            assertEquals(emptyList(), contextFiles(context, "sample-state-", ".txt"))
            assertEquals(emptyList(), contextFiles(context, "sample-state-", ".tmp"))
            val outcome = contextFiles(context, "launch-outcome-", ".txt")
            assertEquals(1, outcome.size, wrapperFailureContext(result, context))
            assertEquals("open_state=finished\nopen_exit=0\n", Files.readString(outcome[0]))
            val process = contextFiles(context, "process-", ".txt")
            assertEquals(1, process.size)
            assertTrue("sample_state_write_failed" in Files.readString(process[0]))
        } finally {
            deleteTree(root)
        }
    }

    test("the wrapper records a pending open and completed samples") {
        val root = Files.createTempDirectory("safari-wrapper")
        try {
            val open = fixtureBash(root, "fake-open", "#!/bin/bash\nexec /bin/sleep 5\n")
            val controlled = controlledLauncher(
                root,
                "controlled-pending-launch.sh",
                open,
                mapOf(
                    "/usr/bin/printf 'samples_completed=%s" to "record_sample 'samples_completed=%s",
                    "set -euo pipefail\n" to
                        "set -euo pipefail\nrecord_sample() { /bin/sleep 0.15; " +
                        "/usr/bin/printf \"\$@\"; }\n",
                ),
            )
            val redirect = redirectOf(root)
            val context = root.resolve("pending-launch-context")
            val environment = LinkedHashMap(System.getenv())
            environment["DYN4K_SAFARI_LAUNCH_CONTEXT"] = context.toString()
            val builder = ProcessBuilder(
                listOf("bash", controlled.toString(), redirect.toString()),
            )
            builder.environment().clear()
            builder.environment().putAll(environment)
            val process = builder.start()
            try {
                val deadline = System.nanoTime() + 2_000_000_000L
                while (System.nanoTime() < deadline &&
                    contextFiles(context, "sample-state-", ".txt").isEmpty()
                ) {
                    Thread.sleep(10)
                }
                val state = contextFiles(context, "sample-state-", ".txt")
                val outcome = contextFiles(context, "launch-outcome-", ".txt")
                assertEquals(1, state.size)
                assertTrue("samples_completed=5" in Files.readString(state[0]))
                assertEquals(emptyList(), contextFiles(context, "sample-state-", ".tmp"))
                assertEquals(1, outcome.size)
                assertEquals("open_state=pending\n", Files.readString(outcome[0]))
                assertTrue(process.isAlive, "the launcher returned before its open finished")
            } finally {
                process.toHandle().descendants().forEach { it.destroyForcibly() }
                process.destroyForcibly()
                process.waitFor(3, TimeUnit.SECONDS)
                process.inputStream.close()
                process.errorStream.close()
            }
        } finally {
            deleteTree(root)
        }
    }

    test("the failure diagnostic is bounded and redacts the fixture text") {
        val root = Files.createTempDirectory("safari-wrapper")
        try {
            val context = root.resolve("diagnostic-context")
            Files.createDirectories(context)
            val canaries = listOf(
                "SECRET_ENV_CANARY",
                "SECRET_PATH_CANARY",
                "SECRET_STDOUT_CANARY",
                "SECRET_STDERR_CANARY",
            )
            Files.writeString(
                context.resolve("launch-123.txt"),
                "pid=123 ppid=22 input=${canaries[1]}\n${canaries[0]}\n",
            )
            Files.writeString(context.resolve("redirect-123.html"), canaries[1])
            Files.writeString(
                context.resolve("process-123.txt"),
                "sample=1\nsample_state_write_failed\n" + canaries[0],
            )
            Files.writeString(context.resolve("open-123.stdout"), canaries[2])
            Files.writeString(context.resolve("open-123.stderr"), canaries[3])
            val result = WrapperRun(
                1,
                canaries[2].toByteArray(),
                ("No such file or directory " + canaries[3]).toByteArray(),
            )
            val detail = wrapperFailureContext(result, context)
            val parsed = StrictJson.load(detail) as JsonObject
            assertEquals(1L, Py.int(parsed["returncode"]!!))
            assertEquals(1L, Py.int((parsed["files"] as JsonObject)["launch"]!!))
            assertEquals(1L, Py.int((parsed["files"] as JsonObject)["process"]!!))
            assertEquals(0L, Py.int((parsed["files"] as JsonObject)["outcome"]!!))
            assertTrue(
                Py.truthy((parsed["process_markers"] as JsonObject)["sample_state_write_failed"]),
            )
            assertEquals("missing_path", Py.str(parsed["stderr_category"]))
            assertTrue(detail.length <= 1024, "the diagnostic exceeded its byte bound")
            for (canary in canaries) assertFalse(canary in detail, "the diagnostic leaked a canary")
            val failure = kotlin.test.assertFailsWith<AssertionError> {
                assertEquals(23, result.returncode, detail)
            }
            for (canary in canaries) {
                assertFalse(canary in (failure.message ?: ""), "the failure leaked a canary")
            }
            val missing = StrictJson.load(wrapperFailureContext(result, root.resolve("absent")))
                as JsonObject
            assertEquals(false, Py.truthy(missing["context_exists"]))
        } finally {
            deleteTree(root)
        }
    }

    test("the failure diagnostic separates a launch from an outcome") {
        val root = Files.createTempDirectory("safari-wrapper")
        try {
            val context = root.resolve("outcome-first")
            Files.createDirectories(context)
            Files.writeString(context.resolve("launch-outcome-123.txt"), "open_state=pending\n")
            val result = WrapperRun(1, ByteArray(0), ByteArray(0))
            val outcomeOnly = StrictJson.load(wrapperFailureContext(result, context)) as JsonObject
            assertEquals(0L, Py.int((outcomeOnly["files"] as JsonObject)["launch"]!!))
            assertEquals(1L, Py.int((outcomeOnly["files"] as JsonObject)["outcome"]!!))
            assertEquals(JsonNull, outcomeOnly["launch_pid_matches_name"])

            Files.writeString(context.resolve("launch-123.txt"), "pid=123 ppid=22 input=hidden\n")
            Files.writeString(context.resolve("launch-other.txt"), "pid=999\n")
            val outcomeFirst = StrictJson.load(wrapperFailureContext(result, context)) as JsonObject
            assertEquals(1L, Py.int((outcomeFirst["files"] as JsonObject)["launch"]!!))
            assertEquals(1L, Py.int((outcomeFirst["files"] as JsonObject)["outcome"]!!))
            assertEquals(true, Py.truthy(outcomeFirst["launch_pid_matches_name"]))
        } finally {
            deleteTree(root)
        }
    }
    test("the wrapper uses Git Bash when the bare bash cannot run the script") {
        val root = Files.createTempDirectory("safari-gitbash")
        try {
            val gitBin = root.resolve("Git/bin")
            Files.createDirectories(gitBin)
            val gitCommand = gitBin.resolve("git.exe")
            Files.writeString(gitCommand, "fixture")
            val gitBash = fixtureBash(
                root,
                "Git/bin/bash.exe",
                "#!/bin/sh\nexec /bin/bash \"$@\"\n",
            )
            val wrongBin = root.resolve("System32")
            Files.createDirectories(wrongBin)
            Files.writeString(wrongBin.resolve("git.exe"), "fixture")
            val wrongBash = fixtureBash(
                root,
                "System32/bash",
                "#!/bin/sh\nprintf '%*s' 504 ' '\nexit 1\n",
            )
            assertTrue(Files.isExecutable(wrongBash))
            val fakeOpen = fixtureBash(root, "fake-open", "#!/bin/bash\nexit 23\n")
            val redirect = redirectOf(root)
            val controlled = controlledLauncher(root, "controlled-launch.sh", fakeOpen, emptyMap())
            val context = root.resolve("launch-context")
            val wrong = runWrapper(
                listOf(wrongBash.toString(), controlled.toString(), redirect.toString()),
                context,
                wrongBin,
            )
            assertEquals(1, wrong.returncode)
            assertEquals(504, wrong.stdout.size)
            assertFalse(Files.exists(context))
            assertEquals(gitBash, SafariGitBash.gitBashFromGit(gitCommand))
            val gitCmd = root.resolve("Git/cmd/git.exe")
            Files.createDirectories(gitCmd.parent)
            Files.writeString(gitCmd, "fixture")
            assertEquals(gitBash, SafariGitBash.gitBashFromGit(gitCmd))
            assertTrue(
                "Git for Windows" in (
                    kotlin.test.assertFailsWith<IllegalArgumentException> {
                        SafariGitBash.gitBashFromGit(wrongBin.resolve("git.exe"))
                    }.message ?: ""
                    ),
            )
            val correct = runWrapper(
                listOf(gitBash.toString(), controlled.toString(), redirect.toString()),
                context,
                wrongBin,
            )
            assertEquals(23, correct.returncode, wrapperFailureContext(correct, context))
            val detail = StrictJson.load(wrapperFailureContext(correct, context)) as JsonObject
            assertEquals(1L, Py.int((detail["files"] as JsonObject)["launch"]!!))
            assertEquals(1, contextFiles(context, "process-", ".txt").size)
            assertEquals(1, contextFiles(context, "launch-outcome-", ".txt").size)
            Files.delete(gitBash)
            assertTrue(
                "executable is missing" in (
                    kotlin.test.assertFailsWith<java.nio.file.NoSuchFileException> {
                        SafariGitBash.gitBashFromGit(gitCommand)
                    }.message ?: ""
                    ),
            )
        } finally {
            deleteTree(root)
        }
    }

    test("Git Bash from a mingw Git uses the same installation") {
        val root = Files.createTempDirectory("safari-gitbash-mingw")
        try {
            val installation = root.resolve("Git")
            val bash = installation.resolve("bin/bash.exe")
            Files.createDirectories(bash.parent)
            Files.writeString(bash, "Git Bash fixture")
            val other = root.resolve("Other/bin")
            Files.createDirectories(other)
            val otherBash = other.resolve("bash.exe")
            Files.writeString(otherBash, "unrelated Bash")
            for (architecture in listOf("mingw64", "mingw32", "ucrt64")) {
                val git = installation.resolve(architecture).resolve("bin/git.exe")
                Files.createDirectories(git.parent)
                Files.writeString(git, "Git for Windows fixture")
                assertEquals(bash, SafariGitBash.gitBashFromGit(git), architecture)
            }
            Files.delete(bash)
            Files.createSymbolicLink(bash, otherBash)
            assertTrue(
                "leaves Git installation" in (
                    kotlin.test.assertFailsWith<IllegalArgumentException> {
                        SafariGitBash.gitBashFromGit(installation.resolve("mingw64/bin/git.exe"))
                    }.message ?: ""
                    ),
            )
            Files.delete(bash)
            assertTrue(
                "executable is missing" in (
                    kotlin.test.assertFailsWith<java.nio.file.NoSuchFileException> {
                        SafariGitBash.gitBashFromGit(installation.resolve("mingw64/bin/git.exe"))
                    }.message ?: ""
                    ),
            )
            val unexpected = installation.resolve("usr/bin/git.exe")
            Files.createDirectories(unexpected.parent)
            Files.writeString(unexpected, "unexpected layout")
            assertTrue(
                "Git for Windows" in (
                    kotlin.test.assertFailsWith<IllegalArgumentException> {
                        SafariGitBash.gitBashFromGit(unexpected)
                    }.message ?: ""
                    ),
            )
        } finally {
            deleteTree(root)
        }
    }

}

private fun deleteTree(root: Path) {
    if (!Files.exists(root)) return
    Files.walk(root).use { walk ->
        walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
    }
}
