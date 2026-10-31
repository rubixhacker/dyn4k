package io.github.rubixhacker.harness.qualification

import java.io.IOException
import java.nio.file.Files
import java.nio.file.Path
import io.github.rubixhacker.harness.contract.Sha256
import java.security.MessageDigest
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * `full_browser_consumer` as the adapter needs it.
 *
 * The constants are the real tables; the two replay calls fail closed naming the unported consumer.
 */
interface FullBrowserConsumerPort {
    val modules: List<String>
    val lanes: Set<String>
    val chromium: Map<String, Pair<Int, String>>
    val javaSha256: String
    val gradleSha256: String

    /** `contract(repository, lane)`: the approved portable selected cases. */
    fun contract(repository: Path, laneId: String): JsonObject

    /** `verify(...)`: the public full browser replay. */
    fun verify(
        repository: Path,
        candidateSha: String,
        laneId: String,
        archive: Path,
        archiveDigest: String,
        browser: Path,
        hashes: JsonObject,
    ): JsonObject

    /** `independent_gates.archive_digest`. */
    fun archiveDigest(archive: Path): String

    /** `independent_gates._json`. */
    fun json(path: Path): JsonElement
}

/** The fail-closed consumer: the public browser replay is `full_browser_consumer.py`. */
object FullBrowserConsumerUnavailable : FullBrowserConsumerPort {
    override val modules: List<String> = FullBrowserAdapterRules.MODULES
    override val lanes: Set<String> = FullBrowserAdapterRules.LANES
    override val chromium: Map<String, Pair<Int, String>> = FullBrowserAdapterRules.CHROMIUM
    override val javaSha256: String = FullBrowserAdapterRules.JAVA_SHA256
    override val gradleSha256: String = FullBrowserAdapterRules.GRADLE_SHA256

    private fun unavailable(): Nothing = throw UnsupportedOperationException(
        "public full browser consumer is not ported: full_browser_consumer.py (contract, verify) " +
            "has no Kotlin counterpart",
    )

    override fun contract(repository: Path, laneId: String): JsonObject = unavailable()

    override fun verify(
        repository: Path,
        candidateSha: String,
        laneId: String,
        archive: Path,
        archiveDigest: String,
        browser: Path,
        hashes: JsonObject,
    ): JsonObject = unavailable()

    override fun archiveDigest(archive: Path): String = ArchiveScan.digest(archive)

    override fun json(path: Path): JsonElement = IndependentGates.json(path)
}

/**
 * `full_browser_adapter.verify_full_browser_staged_consumer`: bind independently signed Chromium
 * expectations to the public browser replay.
 *
 * The caller verifies the audit signature and the staged JS target hashes first; the bundle hashes
 * must come from an independent audit, not from the browser producer receipt.
 */
object FullBrowserAdapter {
    /** `_executable(path, expected, label)`: stream the executable and compare its digest. */
    fun executableBytes(path: Path, expected: String, label: String) {
        if (!Files.isRegularFile(path)) {
            throw IllegalArgumentException("signed $label executable bytes differ")
        }
        val digest = MessageDigest.getInstance("SHA-256")
        Files.newInputStream(path).use { source ->
            val buffer = ByteArray(1024 * 1024)
            while (true) {
                val read = try {
                    source.read(buffer)
                } catch (error: IOException) {
                    throw IllegalArgumentException("signed $label executable bytes differ")
                }
                if (read < 0) break
                digest.update(buffer, 0, read)
            }
        }
        val observed = digest.digest().joinToString("") { "%02x".format(it) }
        if (observed != expected) {
            throw IllegalArgumentException("signed $label executable bytes differ")
        }
    }

    @Suppress("LongParameterList")
    fun verify(
        repository: Path,
        candidateSha: String,
        laneId: String,
        selected: JsonObject,
        archive: Path,
        expected: JsonElement,
        gateResult: JsonElement,
        auditedTargetHashes: JsonElement,
        consumer: FullBrowserConsumerPort = FullBrowserConsumerUnavailable,
        executable: (Path, String, String) -> Unit = ::executableBytes,
    ): JsonObject {
        if (laneId !in consumer.lanes) {
            throw IllegalArgumentException(
                "public full browser verifier does not cover lane: $laneId",
            )
        }
        if (!FullBrowserAdapterRules.isCandidate(candidateSha)) {
            throw IllegalArgumentException("exact browser candidate SHA is invalid")
        }
        val audit = expected as? JsonObject
            ?: throw IllegalArgumentException("signed browser lane audit is missing")
        val hashes = audit["expected_artifact_hashes"] as? JsonObject
        val digests = audit["expected_archive_digests"] as? JsonObject
        val archiveDigest = Py.str(digests?.get("staged-consumer"))
        val runtime = Py.str(audit["expected_runtime_identity"])
        val toolchain = audit["expected_browser_toolchain"] as? JsonObject
        val bundles = audit["expected_browser_bundles"] as? JsonObject
        val hashValues = hashes?.mapValues { (_, value) -> Py.str(value) }
        val hashKeys = hashValues?.keys ?: emptySet()
        val hashDigests = hashValues?.values ?: emptySet<String?>()
        if (hashes == null || hashKeys != consumer.modules.toSet() ||
            hashDigests.any { !FullBrowserAdapterRules.isDigest(it) } ||
            hashes != auditedTargetHashes ||
            !FullBrowserAdapterRules.isDigest(archiveDigest) ||
            runtime.isNullOrEmpty() ||
            toolchain == null || toolchain.keys != FullBrowserAdapterRules.TOOLCHAIN_KEYS ||
            bundles == null || bundles.keys != setOf("core", "facade") ||
            bundles.values.any { !FullBrowserAdapterRules.isDigest(Py.str(it)) }
        ) {
            throw IllegalArgumentException(
                "signed browser artifact, archive, runtime, toolchain, or bundle identity is incomplete",
            )
        }
        val role = laneId.split(":")[2]
        val pinned = consumer.chromium[role]
            ?: throw IllegalArgumentException(
                "signed browser toolchain differs from selected route or pins",
            )
        val major = pinned.first
        val pinnedBrowser = pinned.second
        val javaVersion = Py.str(toolchain["java_version"])
        val browserVersion = Py.str(toolchain["browser_version"])
        if (Py.str(toolchain["java_sha256"]) != consumer.javaSha256 ||
            Py.str(toolchain["gradle_sha256"]) != consumer.gradleSha256 ||
            Py.str(toolchain["browser_sha256"]) != pinnedBrowser ||
            Py.str(toolchain["gradle_version"]) != "9.5.0" ||
            Py.str(toolchain["kgp_version"]) != "2.4.20" ||
            javaVersion == null || !javaVersion.startsWith("openjdk version \"21.") ||
            browserVersion == null ||
            Regex("\\b$major\\.\\d+").find(browserVersion) == null
        ) {
            throw IllegalArgumentException(
                "signed browser toolchain differs from selected route or pins",
            )
        }
        for (key in listOf("java_home", "gradle", "browser", "gradle_user_home")) {
            val value = Py.str(toolchain[key])
            if (value == null || !Path.of(value).isAbsolute) {
                throw IllegalArgumentException("signed browser $key is missing or relative")
            }
        }
        executable(
            Path.of(Py.str(toolchain["java_home"])!!).resolve("bin/java"),
            Py.str(toolchain["java_sha256"])!!,
            "JDK",
        )
        executable(
            Path.of(Py.str(toolchain["gradle"])!!),
            Py.str(toolchain["gradle_sha256"])!!,
            "Gradle",
        )
        executable(
            Path.of(Py.str(toolchain["browser"])!!),
            Py.str(toolchain["browser_sha256"])!!,
            "Chromium",
        )

        val approved = ((consumer.contract(repository, laneId)["cases"] as? kotlinx.serialization.json.JsonArray)
            ?: kotlinx.serialization.json.JsonArray(emptyList()))
            .mapNotNull { Py.str((it as? JsonObject)?.get("id")) }
        val selectedIds = (selected["case_ids"] as? kotlinx.serialization.json.JsonArray)
            ?.mapNotNull { Py.str(it) }
        if (selectedIds != approved) {
            throw IllegalArgumentException(
                "signed browser lane selects a different approved case suite: $laneId",
            )
        }
        val gate = gateResult as? JsonObject
            ?: throw IllegalArgumentException(
                "generic browser staged-consumer gate differs from signed selection",
            )
        if (Py.str(gate["gate"]) != "staged-consumer" ||
            Py.str(gate["status"]) != "PASSED" ||
            gate["complete_selected_suite"] != JsonPrimitive(true) ||
            !Py.equalsInt(gate["selected_cases"], approved.size.toLong()) ||
            Py.str(gate["archive_sha256"]) != archiveDigest
        ) {
            throw IllegalArgumentException(
                "generic browser staged-consumer gate differs from signed selection",
            )
        }

        if (Files.isSymbolicLink(archive) || consumer.archiveDigest(archive) != archiveDigest) {
            throw IllegalArgumentException(
                "signed browser archive digest differs from transported archive",
            )
        }
        val receipt = consumer.json(archive.resolve("receipt.json")) as? JsonObject
            ?: throw IllegalArgumentException("browser runtime or toolchain differs from signed lane")
        if (Py.str(receipt["runtime_identity"]) != runtime ||
            receipt["toolchain"] != toolchain
        ) {
            throw IllegalArgumentException("browser runtime or toolchain differs from signed lane")
        }
        for (short in listOf("core", "facade")) {
            for (name in listOf("karma-selected.js", "linked-executable.js")) {
                val path = archive.resolve(short).resolve(name)
                val observed = try {
                    Sha256.of(Files.readAllBytes(path))
                } catch (error: IOException) {
                    throw IllegalArgumentException(
                        "browser selected bundle differs from independent signed hash",
                    )
                }
                if (observed != Py.str(bundles[short])) {
                    throw IllegalArgumentException(
                        "browser selected bundle differs from independent signed hash",
                    )
                }
            }
        }

        val public = consumer.verify(
            repository,
            candidateSha,
            laneId,
            archive,
            archiveDigest!!,
            Path.of(Py.str(toolchain["browser"])!!),
            hashes,
        )
        val expectedPublic = kotlinx.serialization.json.buildJsonObject {
            put("status", JsonPrimitive("PASSED"))
            put("lane", JsonPrimitive(laneId))
            put("selected_cases", JsonPrimitive(approved.size))
            put("archive_sha256", JsonPrimitive(archiveDigest))
            put("candidate_sha", JsonPrimitive(candidateSha))
        }
        if (public != expectedPublic) {
            throw IllegalArgumentException(
                "public browser verifier differs from signed lane or generic gate",
            )
        }
        return public
    }
}
