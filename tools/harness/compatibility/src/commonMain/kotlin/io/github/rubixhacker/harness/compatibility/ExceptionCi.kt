package io.github.rubixhacker.harness.compatibility

import kotlinx.serialization.json.JsonObject

/**
 * The exception-serialization reports of `tools/compatibility/exception_ci.py`.
 *
 * Ported: the frozen constants, `validate_exception_report`, and `seal_exception`.
 *
 * Not ported: `public_projection` (runs `javap` over two archives and writes the projection),
 * `mutate_uid` (rewrites a class inside the JAR; see `ExceptionCiHost`), `execute`, and `main`.
 */
object ExceptionCi {
    const val FIXTURE = "tools/compatibility/fixtures/exception_serialization"
    const val GOLDEN = "tools/compatibility/exception-public-api-projection.json"
    const val DRIVER_SHA = "f0c76b86ca0f7e9b8eeeeb8265d51a0f627148578fc4d4baacdd1e6bab1038e1"
    const val PROBE_SHA = "7ea22a8470adac3d78591bb4eaa872cb2f700e737c038d78e93031143a8e85b1"
    const val BASELINE_SHA = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
    const val STDLIB_SHA = "2226de463d309d4a5500a481320b3dea515a6981dcae1def531fbc158884e25f"

    val UIDS: Map<String, Long> = linkedMapOf(
        "ArgumentNullException" to 7104871716542808869L,
        "CopyException" to 2434249738746680073L,
        "EmptyCollectionException" to 3188055341987092721L,
        "SameObjectException" to -2844289260493601312L,
        "InvalidIndexException" to 1297019115982655104L,
        "ValueOutOfRangeException" to -7115378379246433066L,
        "ObjectAlreadyExistsException" to 3414084132509765709L,
        "ObjectAlreadyOwnedException" to -7471557485578931121L,
        "NullElementException" to 4560521220204618552L,
    )

    val CASES = listOf(
        "ArgumentNullException",
        "CopyException",
        "EmptyCollectionException",
        "SameObjectException",
        "InvalidIndexException",
        "ObjectAlreadyExistsException",
        "ObjectAlreadyOwnedException",
        "NullElementException-index",
        "NullElementException-name",
        "ValueOutOfRangeException-int",
        "ValueOutOfRangeException-double",
        "ValueOutOfRangeException-bound-int",
        "ValueOutOfRangeException-bound-double",
        "ValueOutOfRangeException-pair-int",
        "ValueOutOfRangeException-pair-double",
    )

    val PROVIDERS = listOf("baseline", "jvm", "android")
    val RUNTIMES = listOf("jdk8", "jdk21")

    private val SERIAL_VERSION = Regex(
        "^  private static final long serialVersionUID = (-?\\d+)l;$",
        RegexOption.MULTILINE,
    )

    /**
     * Replays the fixture report: every provider hash, constructor case, UID, process, stream, and
     * payload must match the pinned baseline.
     */
    fun validateExceptionReport(
        files: CorpusFiles,
        report: JsonObject,
        output: String,
        providerHashes: Map<String, String>,
        probeHash: String,
        driverHash: String,
        stdlibHash: String,
    ) {
        if (report.textOrNull("passed") != "true" ||
            report.integerOrNull("failure_count") != 0L ||
            report.textOrNull("baseline_sha256") != providerHashes["baseline"] ||
            report.textOrNull("probe_sha256") != probeHash ||
            report.textOrNull("driver_sha256") != driverHash ||
            report.textOrNull("stdlib_sha256") != stdlibHash
        ) {
            throw IllegalArgumentException("exception fixture status or input hashes differ")
        }
        val providers = report["providers"].objectOrNull()
        if (providers == null || providers.keys.toSet() != PROVIDERS.toSet() ||
            PROVIDERS.any { providers[it].objectOrNull()?.textOrNull("sha256") != providerHashes[it] }
        ) {
            throw IllegalArgumentException("exception fixture provider hashes differ")
        }
        val cases = report["cases"].arrayOrNull()?.mapNotNull { it.textOrNull() }
        if (cases != CASES) {
            throw IllegalArgumentException("exception constructor inventory differs")
        }
        val compiles = report["compiles"].objectOrNull()
        if (compiles == null || compiles.keys.toSet() != PROVIDERS.toSet() ||
            PROVIDERS.any { compiles[it].objectOrNull()?.integerOrNull("exit") != 0L }
        ) {
            throw IllegalArgumentException("exception fixture compiler or runtime failed")
        }
        val versions = report["versions"].objectOrNull()
        if (versions == null || versions.keys.toSet() != RUNTIMES.toSet() ||
            RUNTIMES.any { versions[it].objectOrNull()?.integerOrNull("exit") != 0L }
        ) {
            throw IllegalArgumentException("exception fixture compiler or runtime failed")
        }
        val identities = report["identities"].arrayOrNull()
        val expectedIdentityKeys = PROVIDERS.flatMap { provider ->
            UIDS.keys.map { name -> provider to "org.dyn4j.exception.$name" }
        }.toSet()
        if (identities == null || identities.size != 27) {
            throw IllegalArgumentException("exception private UID inventory is incomplete")
        }
        val observedIdentityKeys = mutableSetOf<Pair<String?, String?>>()
        for (element in identities) {
            val row = element.objectOrNull()
                ?: throw IllegalArgumentException("exception private UID identity differs")
            val key = row.textOrNull("provider") to row.textOrNull("type")
            val name = row.textOrNull("type").orEmpty().removePrefix("org.dyn4j.exception.")
            val uid = UIDS[name]
            val stdout = row.textOrNull("stdout").orEmpty()
            if (key in observedIdentityKeys || key !in expectedIdentityKeys ||
                uid == null || row.integerOrNull("expected") != uid ||
                row.integerOrNull("exit") != 0L ||
                row.textOrNull("matches") != "true" ||
                SERIAL_VERSION.findAll(stdout).map { it.groupValues[1] }.toList() != listOf(uid.toString())
            ) {
                throw IllegalArgumentException("exception private UID identity differs")
            }
            observedIdentityKeys.add(key)
        }
        if (observedIdentityKeys != expectedIdentityKeys) {
            throw IllegalArgumentException("exception private UID identities are incomplete")
        }
        val runs = report["runs"].arrayOrNull()
        if (runs == null || runs.size != 636) {
            throw IllegalArgumentException("exception process matrix is incomplete")
        }
        val expectedIds = RUNTIMES.flatMap { runtime -> PROVIDERS.map { runtime to it } }.toSet()
        val expectedWrites = RUNTIMES.flatMap { runtime ->
            PROVIDERS.flatMap { provider -> CASES.map { Triple(runtime, provider, it) } }
        }.toSet()
        val expectedReads = mutableSetOf<List<String?>>()
        for (writerRuntime in RUNTIMES) {
            for (writerProvider in PROVIDERS) {
                for (case in CASES) {
                    for (readerRuntime in RUNTIMES) {
                        for (readerProvider in PROVIDERS) {
                            expectedReads.add(
                                listOf(writerRuntime, writerProvider, case, readerRuntime, readerProvider),
                            )
                        }
                    }
                }
            }
        }
        val ids = mutableSetOf<Pair<String?, String?>>()
        val writes = mutableSetOf<Triple<String?, String?, String?>>()
        val reads = mutableSetOf<List<String?>>()
        val baselineOutputs = mutableMapOf<Pair<String?, String?>, String?>()
        for (element in runs) {
            val row = element.objectOrNull()
                ?: throw IllegalArgumentException("exception process failed or did not match baseline")
            if (row.integerOrNull("exit") != 0L || row.textOrNull("matches") != "true") {
                throw IllegalArgumentException("exception process failed or did not match baseline")
            }
            when (row.textOrNull("operation")) {
                "ids" -> {
                    val key = row.textOrNull("runtime") to row.textOrNull("provider")
                    val expected = buildString {
                        for ((name, uid) in UIDS) append("$name=$uid\n")
                    }
                    if (!ids.add(key) || key !in expectedIds || row.textOrNull("stdout") != expected) {
                        throw IllegalArgumentException("exception effective UID process differs")
                    }
                }
                "write" -> {
                    val key = Triple(
                        row.textOrNull("writer_runtime"),
                        row.textOrNull("writer_provider"),
                        row.textOrNull("case"),
                    )
                    if (key in writes || key !in expectedWrites ||
                        row.textOrNull("runtime") != key.first ||
                        row.textOrNull("provider") != key.second
                    ) {
                        throw IllegalArgumentException("exception writer process differs")
                    }
                    val command = row["command"].arrayOrNull()
                    val stream = joinPath(output, "${key.first}-${key.second}-${key.third}.ser")
                    if (command == null || command.size < 2 ||
                        command.takeLast(2).map { it.textOrNull() } != listOf(stream, key.third) ||
                        !files.isFile(stream) ||
                        files.digest(stream) != row.textOrNull("stream_sha256")
                    ) {
                        throw IllegalArgumentException("exception serialized stream is missing or changed")
                    }
                    val stdout = row.textOrNull("stdout").orEmpty()
                    val expectedType = key.third.orEmpty().substringBefore("-")
                    if (!stdout.startsWith("TYPE=org.dyn4j.exception.$expectedType\nMESSAGE=") ||
                        "\nCAUSE=java.lang.IllegalStateException:cause\n" !in stdout ||
                        "\nSUPPRESSED=java.lang.IllegalArgumentException:suppressed\n" !in stdout ||
                        !stdout.endsWith("\nSTACK=Example:run:Example.java:12\n")
                    ) {
                        throw IllegalArgumentException("exception writer payload is incomplete")
                    }
                    writes.add(key)
                    if (key.second == "baseline") {
                        baselineOutputs[key.first to key.third] = stdout
                    }
                }
                "read" -> {
                    val key = listOf(
                        row.textOrNull("writer_runtime"),
                        row.textOrNull("writer_provider"),
                        row.textOrNull("case"),
                        row.textOrNull("runtime"),
                        row.textOrNull("provider"),
                    )
                    if (!reads.add(key) || key !in expectedReads) {
                        throw IllegalArgumentException("exception reader process differs")
                    }
                }
                else -> throw IllegalArgumentException("unknown exception process operation")
            }
        }
        if (ids != expectedIds || writes != expectedWrites || reads != expectedReads) {
            throw IllegalArgumentException("exception process keys are missing or duplicated")
        }
        val expectedStreams = expectedWrites.map { "${it.first}-${it.second}-${it.third}.ser" }.toSet()
        val observedStreams = files.directFiles(output).filter { it.endsWith(".ser") }.toSet()
        if (observedStreams != expectedStreams) {
            throw IllegalArgumentException("exception serialized stream set differs")
        }
        for (element in runs) {
            val row = element.objectOrNull() ?: continue
            if (row.textOrNull("operation") == "write" || row.textOrNull("operation") == "read") {
                val key = row.textOrNull("writer_runtime") to row.textOrNull("case")
                if (row.textOrNull("stdout") != baselineOutputs[key]) {
                    throw IllegalArgumentException("exception payload differs from pinned baseline")
                }
            }
        }
    }

    /**
     * Hashes every raw file the exception summary names, refusing any missing, changed, or
     * unexpected file. The returned map is sorted by relative path.
     */
    fun sealException(
        files: CorpusFiles,
        output: String,
        expected: Map<String, String>,
        summarySha: String,
        goldenSha256: String,
    ): Map<String, String> {
        val summaryPath = joinPath(output, "result.json")
        if (!files.isFile(summaryPath) || files.digest(summaryPath) != summarySha) {
            throw IllegalArgumentException("exception summary is missing or changed before upload")
        }
        val summary = UniqueJson.parse(files.readText(summaryPath)).objectOrNull()
            ?: throw IllegalArgumentException("exception gate did not pass for the staged archives")
        if (summary.textOrNull("status") != "PASSED" ||
            summary["providers"].objectOrNull()?.stringEntries() != expected
        ) {
            throw IllegalArgumentException("exception gate did not pass for the staged archives")
        }
        val paths = linkedMapOf<String, String>()
        paths["result.json"] = summaryPath
        val fixtureRelative = "fixture/result.json"
        val fixturePath = joinPath(output, fixtureRelative)
        val fixtureSha = summary["fixture"].objectOrNull()?.textOrNull("report_sha256")
        if (!files.isFile(fixturePath) || files.digest(fixturePath) != fixtureSha) {
            throw IllegalArgumentException("exception fixture report is missing or changed")
        }
        val fixture = UniqueJson.parse(files.readText(fixturePath)).objectOrNull()
            ?: throw IllegalArgumentException("exception fixture report is missing or changed")
        validateExceptionReport(
            files,
            fixture,
            joinPath(output, "fixture"),
            expected,
            PROBE_SHA,
            DRIVER_SHA,
            STDLIB_SHA,
        )
        paths[fixtureRelative] = fixturePath
        for ((provider, archiveHash) in expected) {
            val relative = "fixture/$provider.jar"
            val frozen = joinPath(output, relative)
            if (!files.isFile(frozen) || files.digest(frozen) != archiveHash) {
                throw IllegalArgumentException("exception frozen $provider archive differs")
            }
            paths[relative] = frozen
        }
        for (stream in files.directFiles(joinPath(output, "fixture"))) {
            if (stream.endsWith(".ser")) {
                paths["fixture/$stream"] = joinPath(joinPath(output, "fixture"), stream)
            }
        }

        val publicRelative = "public-api/result.json"
        val publicPath = joinPath(output, publicRelative)
        val publicSha = summary["public_api"].objectOrNull()?.textOrNull("report_sha256")
        if (!files.isFile(publicPath) || files.digest(publicPath) != publicSha) {
            throw IllegalArgumentException("exception public API report is missing or changed")
        }
        val public = UniqueJson.parse(files.readText(publicPath)).objectOrNull()
            ?: throw IllegalArgumentException("exception public API report is missing or changed")
        if (public.textOrNull("reference_sha256") != goldenSha256 ||
            public["observations"].objectOrNull()?.size != 18
        ) {
            throw IllegalArgumentException("exception public API reference or count differs")
        }
        paths[publicRelative] = publicPath
        val expectedKeys = (listOf("jvm", "android").flatMap { provider ->
            UIDS.keys.map { name -> "$provider:org.dyn4j.exception.$name" }
        }).toSet()
        val observations = public["observations"].objectOrNull()
        if (observations == null || observations.keys != expectedKeys) {
            throw IllegalArgumentException("exception public API observation keys differ")
        }
        val expectedPublic = mutableSetOf<String>()
        for ((key, expectedHash) in observations.stringEntries()) {
            val provider = key.substringBefore(":")
            val name = key.substringAfter(":")
            val file = joinPath(output, "public-api/$provider-${name.substringAfterLast(".")}.txt")
            if (!files.isFile(file) || files.digest(file) != expectedHash) {
                throw IllegalArgumentException("exception public API output is missing or changed")
            }
            expectedPublic.add(fileName(file))
            paths["public-api/${fileName(file)}"] = file
        }
        val observedPublic = files.directFiles(joinPath(output, "public-api"))
            .filter { it.endsWith(".txt") }
            .toSet()
        if (observedPublic != expectedPublic) {
            throw IllegalArgumentException("exception public API output file set differs")
        }

        val uidRelative = "uid-adverse/result.json"
        val uidPath = joinPath(output, uidRelative)
        val uid = summary["adverse"].objectOrNull()?.get("uid").objectOrNull()
            ?: throw IllegalArgumentException("exception UID adverse report is missing or changed")
        if (!files.isFile(uidPath) || files.digest(uidPath) != uid.textOrNull("report_sha256")) {
            throw IllegalArgumentException("exception UID adverse report is missing or changed")
        }
        val uidReport = UniqueJson.parse(files.readText(uidPath)).objectOrNull()
            ?: throw IllegalArgumentException("exception UID adverse report is missing or changed")
        if (uidReport.textOrNull("passed") != "false" ||
            uidReport.integerOrNull("failure_count") != uid.integerOrNull("failure_count") ||
            uidReport["runs"].arrayOrNull()?.size != 636
        ) {
            throw IllegalArgumentException("exception UID adverse control differs")
        }
        paths[uidRelative] = uidPath
        val adversarial = listOf(
            "uid-mutant.jar" to uid.textOrNull("mutant_sha256"),
            "payload-mutant.ser" to
                summary["adverse"].objectOrNull()?.get("payload").objectOrNull()?.textOrNull("mutant_sha256"),
            "payload-adverse.log" to
                summary["adverse"].objectOrNull()?.get("payload").objectOrNull()?.textOrNull("read_log_sha256"),
        )
        for ((relative, expectedHash) in adversarial) {
            val path = joinPath(output, relative)
            if (!files.isFile(path) || files.digest(path) != expectedHash) {
                throw IllegalArgumentException("exception adverse raw file differs: $relative")
            }
            paths[relative] = path
        }
        return sortedByCodePoint(paths.keys).associateWith { paths.getValue(it) }
    }

    private fun JsonObject.stringEntries(): Map<String, String> =
        keys.associateWith { key -> getValue(key).textOrNull().orEmpty() }
}
