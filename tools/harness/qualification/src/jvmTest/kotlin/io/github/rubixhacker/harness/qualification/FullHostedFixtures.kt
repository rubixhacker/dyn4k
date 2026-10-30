package io.github.rubixhacker.harness.qualification

import java.io.ByteArrayOutputStream
import java.nio.file.Files
import java.nio.file.Path
import java.security.MessageDigest
import java.util.concurrent.TimeUnit
import java.util.zip.Inflater
import javax.xml.parsers.DocumentBuilderFactory
import kotlin.io.path.writeText
import kotlin.test.assertTrue

/** Fixtures shared by the hosted full-corpus suites. */


internal fun withHostedTemporary(block: (Path) -> Unit) {
    val root = Files.createTempDirectory("full-hosted-runtime")
    try {
        block(root)
    } finally {
        Files.walk(root).use { walk ->
            walk.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
        }
    }
}

internal fun hostedSha1(bytes: ByteArray): String =
    MessageDigest.getInstance("SHA-1").digest(bytes).joinToString("") { "%02x".format(it) }

internal fun renderHostedSuite(suite: org.w3c.dom.Element): String {
    val out = StringBuilder()
    fun write(element: org.w3c.dom.Element) {
        out.append('<').append(element.tagName)
        val attributes = element.attributes
        for (index in 0 until attributes.length) {
            val attribute = attributes.item(index)
            out.append(' ').append(attribute.nodeName).append("=\"")
                .append(
                    attribute.nodeValue
                        .replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace("\"", "&quot;"),
                )
                .append('"')
        }
        val children = element.childNodes
        if (children.length == 0 && element.textContent.isEmpty()) {
            out.append("/>")
            return
        }
        out.append('>')
        for (index in 0 until children.length) {
            when (val node = children.item(index)) {
                is org.w3c.dom.Element -> write(node)
                else -> out.append(
                    (node.nodeValue ?: "")
                        .replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;"),
                )
            }
        }
        out.append("</").append(element.tagName).append('>')
    }
    write(suite)
    return out.toString()
}

/** Writes one JUnit suite and returns the finished modification time. */
internal fun writeHostedSuite(
    path: Path,
    cases: List<Pair<String, String>>,
    skipped: Boolean = false,
    ignored: Boolean = false,
): Long {
    val out = StringBuilder()
    out.append("""<testsuite tests="${cases.size}" failures="0" errors="0" """)
    out.append("""skipped="${if (skipped) 1 else 0}" time="0.1">""")
    for ((classname, name) in cases) {
        out.append("""<testcase classname="$classname" name="$name" time="0.1">""")
        if (skipped) out.append("<skipped/>")
        if (ignored) out.append("<ignored/>")
        out.append("</testcase>")
    }
    out.append("</testsuite>")
    path.writeText(out.toString())
    return Files.getLastModifiedTime(path).to(TimeUnit.NANOSECONDS)
}

/** One transport archive member: its name, bytes, and recorded nanosecond timestamp. */
internal class TarMember(val name: String, val bytes: ByteArray, val mtimeNs: String)

/** Reads every member of a transport archive, so a test can rewrite it. */
internal fun readTarMembers(archive: Path): List<TarMember> {
    val members = mutableListOf<TarMember>()
    Files.newInputStream(archive).use { stream ->
        org.apache.commons.compress.archivers.tar.TarArchiveInputStream(stream).use { packed ->
            while (true) {
                val entry = packed.nextEntry ?: break
                members.add(
                    TarMember(
                        entry.name,
                        packed.readBytes(),
                        entry.extraPaxHeaders["dyn4k.mtime_ns"] ?: "0",
                    ),
                )
            }
        }
    }
    return members
}

/** Writes a transport archive from an explicit member list, duplicates and odd names included. */
internal fun writeTarMembers(archive: Path, members: List<TarMember>) {
    Files.newOutputStream(archive).use { stream ->
        org.apache.commons.compress.archivers.tar.TarArchiveOutputStream(stream).use { packed ->
            packed.setLongFileMode(
                org.apache.commons.compress.archivers.tar.TarArchiveOutputStream.LONGFILE_POSIX,
            )
            packed.setBigNumberMode(
                org.apache.commons.compress.archivers.tar.TarArchiveOutputStream.BIGNUMBER_POSIX,
            )
            for (member in members) {
                val entry = org.apache.commons.compress.archivers.tar.TarArchiveEntry(member.name)
                entry.size = member.bytes.size.toLong()
                entry.addPaxHeader("dyn4k.mtime_ns", member.mtimeNs)
                packed.putArchiveEntry(entry)
                packed.write(member.bytes)
                packed.closeArchiveEntry()
            }
        }
    }
}

internal fun hostedTarNames(archive: Path): Set<String> {
    val names = mutableSetOf<String>()
    Files.newInputStream(archive).use { stream ->
        org.apache.commons.compress.archivers.tar.TarArchiveInputStream(stream).use { packed ->
            while (true) {
                val entry = packed.nextEntry ?: break
                names.add(entry.name)
            }
        }
    }
    return names
}

internal fun hostedGit(repository: Path, vararg arguments: String): String {
    val process = ProcessBuilder(listOf("git", "-C", repository.toString()) + arguments)
        .redirectErrorStream(true)
        .start()
    val output = process.inputStream.use { it.readBytes() }.decodeToString().trim()
    val status = process.waitFor()
    check(status == 0) { "hostedGit ${arguments.joinToString(" ")} failed: $output" }
    return output
}

/**
 * The retained 5,758-case browser XML `system-out` extract.
 *
 * The bytes are the repository fixture `tools/qualification/fixtures/safari-v2-diagnostics.b85`,
 * decoded exactly as the Python suite decodes it: hostedBase85 of the concatenated lines, then zlib. Its
 * SHA-256 is checked against the recorded digest before use.
 */
internal fun hostedDiagnosticRows(): List<String> {
    val fixture = repositoryRoot().resolve("tools/qualification/fixtures/safari-v2-diagnostics.b85")
    val encoded = String(Files.readAllBytes(fixture), Charsets.ISO_8859_1)
        .split('\n')
        .filter { it.isNotEmpty() }
        .joinToString("")
    val decoded = hostedBase85(encoded)
    val raw = hostedInflate(decoded)
    val digest = MessageDigest.getInstance("SHA-256").digest(raw)
        .joinToString("") { "%02x".format(it) }
    check(digest == "b3b22a31a8d4b9581bb44c4763474eb0c857e075564b763cbb6fd92c631bcf54") {
        "real browser diagnostic fixture bytes differ: $digest"
    }
    return FullHostedRules.splitLinesKeepingEnds(raw.decodeToString())
}

internal fun hostedBase85(text: String): ByteArray {
    val alphabet =
        "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#\$%&()*+-;<=>?@^_`{|}~"
    val out = ByteArrayOutputStream()
    var index = 0
    while (index < text.length) {
        val remaining = text.length - index
        val width = if (remaining >= 5) 5 else remaining
        var value = 0L
        for (offset in 0 until 5) {
            val char = if (offset < width) text[index + offset] else '~'
            value = value * 85 + alphabet.indexOf(char)
        }
        val bytes = byteArrayOf(
            ((value shr 24) and 0xFF).toByte(),
            ((value shr 16) and 0xFF).toByte(),
            ((value shr 8) and 0xFF).toByte(),
            (value and 0xFF).toByte(),
        )
        for (offset in 0 until width - 1) out.write(bytes[offset].toInt())
        index += width
    }
    return out.toByteArray()
}

internal fun hostedInflate(bytes: ByteArray): ByteArray {
    val inflater = Inflater()
    val out = ByteArrayOutputStream()
    val buffer = ByteArray(64 * 1024)
    try {
        inflater.setInput(bytes)
        while (!inflater.finished()) {
            val count = inflater.inflate(buffer)
            if (count == 0) {
                if (inflater.needsInput() || inflater.needsDictionary()) break
            } else {
                out.write(buffer, 0, count)
            }
        }
    } finally {
        inflater.end()
    }
    return out.toByteArray()
}

/** Builds the diagnostic case suite the retained rows belong to. */
internal fun hostedDiagnosticSuite(rows: List<String>, repeat: Int): org.w3c.dom.Element {
    val document = javax.xml.parsers.DocumentBuilderFactory.newInstance().newDocumentBuilder().newDocument()
    val suite = document.createElement("testsuite")
    val methods = FullHosted.SAFARI_DIAGNOSTIC_CASES.keys
    for (round in 0 until repeat) {
        for (method in methods) {
            val case = document.createElement("testcase")
            case.setAttribute(
                "classname",
                "jsBrowserTest.${FullHosted.SAFARI_DIAGNOSTIC_CLASS}",
            )
            case.setAttribute(
                "name",
                "$method[js, browser, Safari26.6.2, MacOS10.15.7]",
            )
            case.setAttribute("time", "0.1")
            suite.appendChild(case)
        }
    }
    suite.setAttribute("tests", (methods.size * repeat).toString())
    suite.setAttribute("failures", "0")
    suite.setAttribute("errors", "0")
    suite.setAttribute("skipped", "0")
    suite.setAttribute("time", "1")
    val output = document.createElement("system-out")
    output.appendChild(document.createTextNode(rows.joinToString("").repeat(repeat)))
    suite.appendChild(output)
    return suite
}
