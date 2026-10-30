package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.Sha256
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import kotlin.io.path.isRegularFile

/**
 * `qualify.candidate_source_contract` and `qualify.expected_source_entries`.
 *
 * When the candidate is a Git checkout, the contract hashes committed blob bytes rather than
 * working-tree bytes, so line-ending or archive substitutions cannot change a sources archive.
 */
object CandidateSource {
    private val OBJECT_ID = Regex("[0-9a-f]{40}")
    private val SIZE_FIELD = Regex("0|[1-9][0-9]*")
    private val SOURCE_SUFFIXES = setOf(".kt", ".java")

    /** Returns the SHA-256 of every published source file of each module. */
    fun contract(repository: Path, candidateSha: String): Map<String, Map<String, String>> {
        val sourceFiles = LinkedHashMap<String, ByteArray>()
        if (Files.exists(repository.resolve(".git"))) {
            readGitSources(repository, candidateSha, sourceFiles)
        } else {
            readWorkingTreeSources(repository, sourceFiles)
        }

        val result = LinkedHashMap<String, MutableMap<String, String>>()
        for (module in Qualification.modules) result[module] = LinkedHashMap()
        for ((path, contents) in sourceFiles) {
            if (path == MODULE_DESCRIPTOR) {
                result.getValue("dyn4k-core")["jvmModule/module-info.java"] = Sha256.of(contents)
                continue
            }
            val parts = path.split('/')
            if (parts.size < 6 ||
                parts[0] !in Qualification.modules ||
                parts[1] != "src" ||
                !parts[2].endsWith("Main") ||
                parts[3] != "kotlin" && parts[3] != "java"
            ) {
                continue
            }
            val module = parts[0]
            val sourceSet = parts[2]
            val jarPath = (listOf(sourceSet) + parts.drop(4)).joinToString("/")
            if (jarPath in result.getValue(module)) {
                throw IllegalArgumentException("duplicate candidate source path: $jarPath")
            }
            result.getValue(module)[jarPath] = Sha256.of(contents)
        }
        if (result.values.any { it.isEmpty() }) {
            throw IllegalArgumentException("candidate source tree is missing required module sources")
        }
        return result.mapValues { (_, value) -> value.toMap() }
    }

    /** `qualify.expected_source_entries`: the published subset of one module's source contract. */
    fun expectedEntries(
        sourceContract: Map<String, Map<String, String>>,
        module: String,
        target: String?,
    ): Map<String, String> {
        val sourceSets = SourceSets.forPublication(module, target)
        val sources = sourceContract[module] ?: emptyMap()
        val result = LinkedHashMap<String, String>()
        for ((path, sha) in sources) {
            val first = path.substringBefore('/')
            if (first in sourceSets ||
                (module == "dyn4k-core" && target == "jvm" && path == "jvmModule/module-info.java")
            ) {
                result[path] = sha
            }
        }
        return result
    }

    private const val MODULE_DESCRIPTOR = "dyn4k-core/src/jvmModule/java/module-info.java"

    private class Entry(val path: String, val oid: ByteArray, val kind: ByteArray)

    private fun readGitSources(repository: Path, candidateSha: String, into: MutableMap<String, ByteArray>) {
        val revision = git(
            repository,
            listOf("rev-parse", "--show-object-format", "$candidateSha^{tree}"),
        )
        val newline = revision.indexOf('\n'.code.toByte())
        val objectFormat = if (newline < 0) revision else revision.copyOfRange(0, newline)
        val rootTree = (
            if (newline < 0) ByteArray(0) else revision.copyOfRange(newline + 1, revision.size)
            ).toString(StandardCharsets.ISO_8859_1).trim().toByteArray(StandardCharsets.ISO_8859_1)
        if (!objectFormat.contentEquals("sha1".toByteArray()) ||
            !OBJECT_ID.matches(candidateSha) ||
            !OBJECT_ID.matches(rootTree.toString(StandardCharsets.ISO_8859_1))
        ) {
            throw IllegalArgumentException("candidate source requires full SHA-1 commit and tree IDs")
        }

        val tree = git(
            repository,
            listOf(
                "ls-tree", "-r", "-t", "-z", "--full-tree", candidateSha, "--",
                "dyn4k-core/src", "dyn4k/src",
            ),
        )
        val blobs = mutableListOf<Entry>()
        val trees = mutableListOf<Entry>()
        for (entry in splitNul(tree)) {
            if (entry.isEmpty()) continue
            val separator = entry.indexOf('\t'.code.toByte())
            if (separator < 0) throw IllegalArgumentException("candidate source tree is invalid")
            val metadata = entry.copyOfRange(0, separator).toString(StandardCharsets.ISO_8859_1).split(' ')
                .filter { it.isNotEmpty() }
            if (metadata.size != 3) throw IllegalArgumentException("candidate source tree is invalid")
            val mode = metadata[0].toByteArray(StandardCharsets.ISO_8859_1)
            val kind = metadata[1].toByteArray(StandardCharsets.ISO_8859_1)
            val oid = metadata[2].toByteArray(StandardCharsets.ISO_8859_1)
            val path = entry.copyOfRange(separator + 1, entry.size).toString(StandardCharsets.UTF_8)
            if (kind.contentEquals("tree".toByteArray())) {
                if (!mode.contentEquals("040000".toByteArray()) ||
                    !OBJECT_ID.matches(oid.toString(StandardCharsets.ISO_8859_1))
                ) {
                    throw IllegalArgumentException("candidate source tree is invalid: $path")
                }
                trees.add(Entry(path, oid, kind))
            }
            if (path.endsWith(".kt") || path.endsWith(".java")) {
                if (!mode.contentEquals("100644".toByteArray()) && !mode.contentEquals("100755".toByteArray()) ||
                    !kind.contentEquals("blob".toByteArray())
                ) {
                    throw IllegalArgumentException("candidate source is not a regular file: $path")
                }
                blobs.add(Entry(path, oid, kind))
            }
        }

        val objects = mutableListOf<Entry>()
        objects.addAll(blobs)
        objects.add(Entry("candidate commit", candidateSha.toByteArray(StandardCharsets.US_ASCII), "commit".toByteArray()))
        objects.add(Entry("root tree", rootTree, "tree".toByteArray()))
        objects.addAll(trees)

        val request = objects.joinToString("") { it.oid.toString(StandardCharsets.US_ASCII) + "\n" }
        val contents = git(repository, listOf("cat-file", "--batch"), request.toByteArray(StandardCharsets.US_ASCII))
        var position = 0
        for (entry in objects) {
            val label = "candidate source ${entry.kind.toString(StandardCharsets.US_ASCII)}"
            val headerStart = position
            while (position < contents.size && contents[position] != '\n'.code.toByte()) position++
            val header = contents.copyOfRange(headerStart, position)
            if (position < contents.size) position++
            val prefix = entry.oid + " ".toByteArray() + entry.kind + " ".toByteArray()
            if (!startsWith(header, prefix)) {
                throw IllegalArgumentException("$label is invalid: ${entry.path}")
            }
            val sizeField = header.copyOfRange(prefix.size, header.size).toString(StandardCharsets.US_ASCII)
            if (!SIZE_FIELD.matches(sizeField)) {
                throw IllegalArgumentException("$label is invalid: ${entry.path}")
            }
            val size = sizeField.toInt()
            if (position + size > contents.size) {
                throw IllegalArgumentException("$label is incomplete: ${entry.path}")
            }
            val source = contents.copyOfRange(position, position + size)
            position += size
            if (position >= contents.size || contents[position] != '\n'.code.toByte()) {
                throw IllegalArgumentException("$label is incomplete: ${entry.path}")
            }
            position++
            val identity = Sha1.gitObject(entry.kind, source)
            if (!identity.contentEquals(entry.oid)) {
                throw IllegalArgumentException("$label identity differs: ${entry.path}")
            }
            when {
                entry.kind.contentEquals("blob".toByteArray()) -> into[entry.path] = source
                entry.kind.contentEquals("commit".toByteArray()) -> {
                    val breakAt = source.indexOf('\n'.code.toByte())
                    val first = if (breakAt < 0) source else source.copyOfRange(0, breakAt)
                    if (!first.contentEquals("tree ".toByteArray() + rootTree)) {
                        throw IllegalArgumentException("candidate source commit tree differs")
                    }
                }
            }
        }
        if (position < contents.size) {
            throw IllegalArgumentException("candidate source blob response has unexpected data")
        }
    }

    private fun readWorkingTreeSources(repository: Path, into: MutableMap<String, ByteArray>) {
        for (module in Qualification.modules) {
            val sources = repository.resolve(module).resolve("src")
            if (!Files.isDirectory(sources)) continue
            Files.walk(sources).use { stream ->
                for (source in stream) {
                    val relative = sources.relativize(source).toString().replace('\\', '/')
                    val parts = relative.split('/')
                    // `*Main/*/**/*`: at least one directory below a `<name>Main` directory.
                    if (parts.size < 3 || !parts[0].endsWith("Main")) continue
                    if (!source.isRegularFile()) continue
                    if (!parts.last().endsWith(".kt") && !parts.last().endsWith(".java")) continue
                    val path = repository.relativize(source).toString().replace('\\', '/')
                    into[path] = Fs.readBytes(source)
                }
            }
        }
        val descriptor = repository.resolve(MODULE_DESCRIPTOR)
        if (Files.isRegularFile(descriptor)) {
            into[MODULE_DESCRIPTOR] = Fs.readBytes(descriptor)
        }
    }

    private fun startsWith(value: ByteArray, prefix: ByteArray): Boolean {
        if (value.size < prefix.size) return false
        for (index in prefix.indices) if (value[index] != prefix[index]) return false
        return true
    }

    private fun splitNul(value: ByteArray): List<ByteArray> {
        val parts = mutableListOf<ByteArray>()
        var start = 0
        for (index in value.indices) {
            if (value[index] == 0.toByte()) {
                parts.add(value.copyOfRange(start, index))
                start = index + 1
            }
        }
        if (start < value.size) parts.add(value.copyOfRange(start, value.size))
        return parts
    }

    private fun git(repository: Path, arguments: List<String>, input: ByteArray? = null): ByteArray {
        val command = listOf("git", "--no-replace-objects", "-C", repository.toString()) + arguments
        val process = try {
            ProcessBuilder(command).start()
        } catch (error: IOException) {
            throw GitFailure(error.message ?: "git is unavailable")
        }
        process.outputStream.use { stream -> if (input != null) stream.write(input) }
        val output = process.inputStream.use { it.readBytes() }
        val error = process.errorStream.use { it.readBytes() }
        val status = process.waitFor()
        if (status != 0) {
            throw GitFailure(
                "git ${arguments.joinToString(" ")} failed: ${error.toString(StandardCharsets.UTF_8).trim()}",
            )
        }
        return output
    }
}

/** Git object identities, as `hashlib.sha1(kind + b" " + size + b"\0" + source)` computes them. */
internal object Sha1 {
    fun gitObject(kind: ByteArray, source: ByteArray): ByteArray {
        val digest = java.security.MessageDigest.getInstance("SHA-1")
        digest.update(kind)
        digest.update(' '.code.toByte())
        digest.update(source.size.toString().toByteArray(StandardCharsets.US_ASCII))
        digest.update(0.toByte())
        digest.update(source)
        return digest.digest().joinToString("") { "%02x".format(it) }.toByteArray(StandardCharsets.US_ASCII)
    }
}
