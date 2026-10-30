package io.github.rubixhacker.harness.qualification

import de.infix.testBalloon.framework.core.testSuite
import java.nio.file.Files
import java.nio.file.Path
import kotlin.io.path.writeText
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject

/**
 * `independent_linux_observer.verify` and `_derive`, against reference-generated archives.
 *
 * The reference wrote the event chain and the witness; the port must accept them, derive the
 * identical witness, and reject every recorded tamper with the reference's message.
 */
val ObserverWitnessContract by testSuite {
    val entries = TestVectors.list("observer")

    test("a reference witness verifies and re-derives") {
        val valid = entries.first { it.primitive("name") == "valid witness" }
        withArchive(valid) { root ->
            val (witness, events) = LinuxObserver.verify(root, includeEvents = true)
            assertEquals(11, events.size)
            assertEquals(valid.objectAt("result").objectAt("witness"), witness)
        }
    }

    for (entry in entries.filter { it.primitive("name") != "valid witness" }) {
        test("verify: ${entry.primitive("name")}") {
            val expected = entry.objectAt("result")
            withArchive(entry) { root ->
                val error = assertFailsWith<ObservationError> { LinuxObserver.verify(root) }
                assertEquals(expected.primitive("error"), error.message, entry.primitive("name"))
            }
        }
    }

    test("an event log that does not end with a newline is rejected") {
        withArchive(entries.first()) { root ->
            val path = root.resolve("events.jsonl")
            Files.write(path, Files.readAllBytes(path).dropLast(1).toByteArray())
            val error = assertFailsWith<ObservationError> { LinuxObserver.verify(root) }
            assertEquals("event log is truncated or oversized", error.message)
        }
    }

    test("a witness without its trailing newline is rejected") {
        withArchive(entries.first()) { root ->
            val path = root.resolve("witness.json")
            Files.write(path, Files.readAllBytes(path).dropLast(1).toByteArray())
            val error = assertFailsWith<ObservationError> { LinuxObserver.verify(root) }
            assertEquals("changed witness bytes", error.message)
        }
    }

    test("an event log with a repeated key is rejected") {
        withArchive(entries.first()) { root ->
            val path = root.resolve("events.jsonl")
            path.writeText(Files.readString(path).replaceFirst("\"seq\":1,", "\"seq\":1,\"seq\":1,"))
            val error = assertFailsWith<ObservationError> { LinuxObserver.verify(root) }
            assertEquals("duplicate JSON key: seq", error.message)
        }
    }
}

/** Writes the recorded files of one vector into a fresh directory, then runs [block] on it. */
private fun withArchive(entry: JsonObject, block: (Path) -> Unit) {
    val work = Files.createTempDirectory("observer-verify")
    val root = work.resolve("capture")
    Files.createDirectory(root)
    try {
        for ((name, content) in entry.objectAt("files")) {
            Fs.writeText(root.resolve(name), TestVectors.str(content))
        }
        entry["hardlink"]?.let { link ->
            val name = TestVectors.strOrNull(link) ?: return@let
            Files.createLink(work.resolve("linked.jsonl"), root.resolve(name))
        }
        val argument = if (TestVectors.str(entry["traversal"]) == "true") {
            work.resolve("capture").resolve("..").resolve("capture")
        } else {
            root
        }
        block(argument)
    } finally {
        deleteRecursively(work)
    }
}

/**
 * `_expected`, `_generated_expected`, `_image`, `_stat`, `_identity`, and `EventLog` over this host.
 *
 * These read `/proc` and the filesystem only; the ptrace tracer does not run here.
 */
val LinuxObservationReads by testSuite {
    test("a process image is read from /proc") {
        val pid = ProcessHandle.current().pid()
        val image = LinuxObserver.image(pid)
        assertEquals(pid, Py.int(image["pid"]))
        assertEquals(true, (image["argv"] as JsonArray).isNotEmpty())
        assertEquals(true, Py.SHA64.matches(Py.str(image["executable_sha256"]) ?: ""))
        val stat = LinuxObserver.stat(pid)
        assertEquals(Py.int(image["start_ticks"]), stat.second)
        val identity = LinuxObserver.identity(pid)
        assertEquals(Py.int(identity["start_ticks"]), stat.second)
        assertEquals(LinuxObserver.bootId(), Py.str(identity["boot_id"]))
    }

    test("an expected executable is pinned by digest") {
        val truePath = Path.of("/usr/bin/true").toRealPath()
        val expected = LinuxObserver.expected(listOf("core=$truePath"))
        assertEquals(setOf("core"), expected.keys)
        assertEquals(truePath.toString(), Py.str(expected.getValue("core")["path"]))
        assertEquals(Fs.digest(truePath), Py.str(expected.getValue("core")["sha256"]))
    }

    test("an invalid expected process selection is rejected") {
        for ((specs, message) in listOf(
            listOf("core") to "expected process must be NAME=EXECUTABLE",
            listOf("=x") to "invalid expected process name: ",
            listOf("build=/usr/bin/true") to "invalid expected process name: build",
            listOf("a/b=/usr/bin/true") to "invalid expected process name: a/b",
            listOf("core=/usr/bin/true", "core=/usr/bin/true") to "invalid expected process name: core",
        )) {
            val error = assertFailsWith<ObservationError> { LinuxObserver.expected(specs) }
            assertEquals(message, error.message)
        }
    }

    test("a generated executable must not exist yet") {
        val directory = Files.createTempDirectory("generated-expected")
        try {
            val present = directory.resolve("child")
            Fs.writeText(present, "x")
            val error = assertFailsWith<ObservationError> {
                LinuxObserver.generatedExpected(listOf("child=$present"), emptyMap())
            }
            assertEquals("generated executable already exists: $present", error.message)
            val missing = directory.resolve("later")
            val generated = LinuxObserver.generatedExpected(listOf("child=$missing"), emptyMap())
            assertEquals(missing.toString(), Py.str(generated.getValue("child")["path"]))
            assertEquals(JsonNull, generated.getValue("child")["sha256"])
        } finally {
            deleteRecursively(directory)
        }
    }

    test("a symbolic or hardlinked input is rejected") {
        val directory = Files.createTempDirectory("observer-input")
        try {
            val file = directory.resolve("input.bin")
            Fs.writeText(file, "x")
            val link = directory.resolve("link.bin")
            Files.createSymbolicLink(link, file.fileName)
            val symbolic = assertFailsWith<ObservationError> { LinuxObserver.safeInput(link) }
            assertEquals("input must be one regular, unlinked file: $link", symbolic.message)
            assertEquals(file.toAbsolutePath(), LinuxObserver.safeInput(file))
            val hard = directory.resolve("hard.bin")
            Files.createLink(hard, file)
            val hardlinked = assertFailsWith<ObservationError> { LinuxObserver.safeInput(hard) }
            assertEquals("input must be one regular, unlinked file: $hard", hardlinked.message)
        } finally {
            deleteRecursively(directory)
        }
    }

    test("the event log keeps terminal slots and rejects oversize events") {
        val directory = Files.createTempDirectory("observer-log")
        try {
            val log = ObserverEventLog(directory.resolve("capture"), eventLimit = 8, byteLimit = 8192)
            try {
                repeat(6) { log.add("spawn") }
                val error = assertFailsWith<ObservationError> { log.add("spawn") }
                assertEquals("event limit exceeded", error.message)
                log.add("error")
                log.add("end")
                assertEquals(8, log.count)
            } finally {
                log.close()
            }
            val lines = Files.readAllLines(directory.resolve("capture/events.jsonl"))
            assertEquals(8, lines.size)
            val last = StrictObjectJson.parse(lines.last()) as JsonObject
            assertEquals("end", Py.str(last["kind"]))
            assertEquals(8L, Py.int(last["seq"]))
            val small = assertFailsWith<ObservationError> {
                val limited = ObserverEventLog(
                    directory.resolve("small"), eventLimit = 4096, byteLimit = 5000,
                )
                try {
                    repeat(40) { limited.add("spawn") }
                } finally {
                    limited.close()
                }
            }
            assertEquals("event log byte limit exceeded", small.message)
        } finally {
            deleteRecursively(directory)
        }
    }

    test("an observer output path with traversal is rejected") {
        val directory = Files.createTempDirectory("observer-traversal")
        try {
            val error = assertFailsWith<ObservationError> {
                ObserverEventLog(directory.resolve("..").resolve("escape"))
            }
            assertEquals("observer output uses path traversal", error.message)
        } finally {
            deleteRecursively(directory)
        }
    }
}
