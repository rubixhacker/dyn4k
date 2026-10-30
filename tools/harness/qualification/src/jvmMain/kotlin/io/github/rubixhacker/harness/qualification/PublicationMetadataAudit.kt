package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.PublicationContract
import io.github.rubixhacker.harness.contract.PublicationVariant
import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.VariantAvailableAt
import io.github.rubixhacker.harness.contract.VariantDependency
import java.nio.file.Files
import java.nio.file.Path
import java.security.MessageDigest
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** The errors and the referenced file paths of one Gradle module metadata audit. */
class MetadataAuditResult(val errors: List<String>, val referenced: Set<Path>)

/**
 * `qualify.audit_publication_metadata`.
 *
 * Every accepted variant, attribute, dependency row, and file descriptor is compared against the
 * publication contract, and every advertised checksum is recomputed from the staged bytes.
 */
object PublicationMetadataAudit {
    private val CREATOR = JsonObject(
        mapOf("gradle" to JsonObject(mapOf("version" to JsonPrimitive("9.5.0")))),
    )
    private val STATUS = JsonObject(mapOf("org.gradle.status" to JsonPrimitive("release")))
    private val FILE_FIELDS = setOf("url", "name", "size", "sha512", "sha256", "sha1", "md5")

    fun audit(base: Path, module: String, target: String?, data: JsonElement?): MetadataAuditResult {
        val name = if (target == null) module else Qualification.targetPublicationName(module, target)
        val errors = mutableListOf<String>()
        val metadata = data as? JsonObject

        if (metadata == null || Py.str(metadata["formatVersion"]) != "1.1") {
            errors.add("$name: Gradle metadata formatVersion differs from publication contract")
        }
        if (metadata == null || metadata.keys != setOf("formatVersion", "createdBy", "component", "variants")) {
            errors.add("$name: Gradle metadata fields differ from publication contract")
        }
        if (metadata != null && metadata["createdBy"] != CREATOR) {
            errors.add("$name: Gradle metadata creator differs from publication contract")
        }

        val expectedComponent = linkedMapOf<String, String>(
            "group" to Qualification.GROUP,
            "module" to module,
            "version" to Qualification.VERSION,
        )
        if (target != null) {
            expectedComponent["url"] = "../../$module/${Qualification.VERSION}/$module-${Qualification.VERSION}.module"
        }
        val component = metadata?.get("component") as? JsonObject
        if (component == null || expectedComponent.any { (key, value) -> Py.str(component[key]) != value }) {
            errors.add("$name: Gradle component coordinate differs from publication contract")
        }
        if (component != null) {
            if (component.keys != expectedComponent.keys + "attributes") {
                errors.add("$name: Gradle component metadata fields differ from publication contract")
            }
            if (component["attributes"] != STATUS) {
                errors.add("$name: Gradle component status differs from publication contract")
            }
        }
        if (target == null && component != null && "url" in component) {
            errors.add("$name: root Gradle component has a parent URL")
        }

        val variants = metadata?.get("variants")
        if (variants !is JsonArray || variants.any { it !is JsonObject }) {
            return MetadataAuditResult(
                errors + "$name: Gradle variants are invalid",
                emptySet(),
            )
        }

        val actual = LinkedHashMap<String?, JsonObject>()
        for (variant in variants) {
            val item = variant as JsonObject
            actual[Py.str(item["name"])] = item
        }
        val contract = PublicationContract.variants(module, target)
        if (actual.size != variants.size || actual.keys.filterNotNull().toSet() != contract.keys) {
            val missing = contract.keys - actual.keys.filterNotNull().toSet()
            val extra = actual.keys.filter { it == null || it !in contract.keys }
                .map { CanonicalText.of(it?.let { key -> JsonPrimitive(key) }) }
            errors.add(
                "$name: Gradle variants differ from publication contract: " +
                    "missing=${Py.listRepr(missing.sortedWith(CanonicalText::compare))} " +
                    "extra=${Py.listRepr(extra.sortedWith(CanonicalText::compare))}",
            )
        }

        val referenced = mutableSetOf<Path>()
        val fileHashes = mutableMapOf<Path, Map<String, String>>()

        for ((variantName, specification) in contract) {
            val item = actual[variantName] ?: continue
            val available = specification.availableAt
            val expectedFields = if (available != null) {
                setOf("name", "attributes", "available-at")
            } else {
                buildSet {
                    add("name")
                    add("attributes")
                    add("files")
                    if (specification.dependencies.isNotEmpty()) add("dependencies")
                }
            }
            if (item.keys != expectedFields) {
                errors.add("$name: $variantName metadata fields differ from publication contract")
            }
            if (asStringMap(item["attributes"]) != Qualification.variantAttributes(specification.target, specification.kind)) {
                errors.add("$name: $variantName selection attributes differ from publication contract")
            }
            if (available != null) {
                if (!matchesAvailableAt(item["available-at"], available) ||
                    "files" in item ||
                    "dependencies" in item
                ) {
                    errors.add("$name: $variantName target mapping differs")
                }
                continue
            }
            if (item["available-at"] != null && item["available-at"] !is kotlinx.serialization.json.JsonNull) {
                errors.add("$name: $variantName unexpectedly redirects to another publication")
            }

            val dependencies = item["dependencies"] ?: JsonArray(emptyList())
            if (dependencies !is JsonArray || dependencies.any { it !is JsonObject }) {
                errors.add("$name: $variantName dependencies are invalid")
            } else {
                val observed = mutableSetOf<Triple<String?, String?, String?>>()
                for (dependency in dependencies) {
                    val dep = dependency as JsonObject
                    val version = dep["version"] as? JsonObject
                    observed.add(Triple(Py.str(dep["group"]), Py.str(dep["module"]), Py.str(version?.get("requires"))))
                }
                val canonical = specification.dependencies.map { dependency ->
                    Triple(dependency.group, dependency.module, dependency.version)
                }
                val everyDependencyIsCanonical = dependencies.all { dependency ->
                    isCanonicalDependency(dependency as JsonObject, specification.dependencies)
                }
                if (observed.size != dependencies.size ||
                    observed != canonical.toSet() ||
                    !everyDependencyIsCanonical
                ) {
                    errors.add("$name: $variantName dependency graph differs from publication contract")
                }
            }

            val files = item["files"]
            if (files !is JsonArray || files.size != 1 || files[0] !is JsonObject) {
                errors.add("$name: $variantName must reference one published file")
                continue
            }
            val file = files[0] as JsonObject
            val url = specification.url ?: continue
            if (Py.str(file["url"]) != url || Py.str(file["name"]) != specification.fileName) {
                errors.add("$name: $variantName file reference differs from publication contract")
            }
            if (file.keys != FILE_FIELDS) {
                errors.add("$name: $variantName file descriptor fields differ from publication contract")
            }
            val path = base.resolve(url)
            referenced.add(path)
            if (!Files.isRegularFile(path)) {
                errors.add("$name: $variantName referenced file missing: $url")
            } else {
                val hashes = fileHashes.getOrPut(path) { computeHashes(path) }
                if (!Py.equalsInt(file["size"], Files.size(path)) ||
                    hashes.any { (algorithm, value) -> Py.str(file[algorithm]) != value }
                ) {
                    errors.add("$name: $variantName referenced file size or checksum differs from staged bytes")
                }
            }
        }
        return MetadataAuditResult(errors, referenced)
    }

    private fun matchesAvailableAt(value: JsonElement?, available: VariantAvailableAt): Boolean {
        val pointer = value as? JsonObject ?: return false
        return pointer.keys == setOf("group", "module", "version", "url") &&
            Py.str(pointer["group"]) == available.group &&
            Py.str(pointer["module"]) == available.module &&
            Py.str(pointer["version"]) == available.version &&
            Py.str(pointer["url"]) == available.url
    }

    private fun isCanonicalDependency(
        dependency: JsonObject,
        canonical: Set<VariantDependency>,
    ): Boolean {
        if (dependency.keys != setOf("group", "module", "version")) return false
        val version = dependency["version"] as? JsonObject ?: return false
        if (version.keys != setOf("requires")) return false
        val row = VariantDependency(
            group = Py.str(dependency["group"]) ?: return false,
            module = Py.str(dependency["module"]) ?: return false,
            version = Py.str(version["requires"]) ?: return false,
        )
        return row in canonical
    }

    private fun asStringMap(value: JsonElement?): Map<String, String>? {
        val source = value as? JsonObject ?: return null
        val result = LinkedHashMap<String, String>()
        for ((key, item) in source) {
            result[key] = Py.str(item) ?: return null
        }
        return result
    }

    private fun computeHashes(path: Path): Map<String, String> {
        val digests = linkedMapOf(
            "sha512" to MessageDigest.getInstance("SHA-512"),
            "sha256" to MessageDigest.getInstance("SHA-256"),
            "sha1" to MessageDigest.getInstance("SHA-1"),
            "md5" to MessageDigest.getInstance("MD5"),
        )
        Files.newInputStream(path).use { stream ->
            val block = ByteArray(1024 * 1024)
            while (true) {
                val read = stream.read(block)
                if (read < 0) break
                for (digest in digests.values) digest.update(block, 0, read)
            }
        }
        return digests.mapValues { (_, digest) -> digest.digest().joinToString("") { "%02x".format(it) } }
    }
}
