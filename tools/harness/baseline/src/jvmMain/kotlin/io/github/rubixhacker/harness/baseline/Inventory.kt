package io.github.rubixhacker.harness.baseline

import io.github.rubixhacker.harness.contract.Sha256
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.nio.charset.StandardCharsets
import java.nio.file.Path

/**
 * `verify.inventory`: the baseline type inventory the comparison and the documentation cite.
 *
 * Every tracked source, its digest, the annotation count and each `javap` surface are recorded from
 * the committed bytes, and the binary is read from a snapshot so a concurrent replacement cannot
 * change what the inventory describes.
 */
fun inventory(
    seams: BaselineSeams,
    source: Path,
    binary: Path,
    output: Path,
    policy: BaselinePolicy = BaselinePolicy(),
    processEnvironment: Map<String, String> = System.getenv(),
): JsonObject {
    val checked = checkedJavaSources(seams, source, policy.commit, null, processEnvironment)
    if (checked.production.size != 268 || checked.tests.size != 199) {
        throw BaselineExit(
            "unaccounted source files: production=${checked.production.size} " +
                "tests=${checked.tests.size}",
        )
    }
    val sourceHashes = linkedMapOf<String, String>()
    var annotationCount = 0
    for (path in checked.production + checked.tests) {
        val pinnedBytes = checked.pinned.getValue(path)
        sourceHashes[path] = Sha256.of(pinnedBytes)
        if (path in checked.tests) {
            annotationCount += String(pinnedBytes, StandardCharsets.UTF_8).split("@Test").size - 1
        }
    }
    var binaryHash = ""
    var classes: List<String> = emptyList()
    var signatures: Map<String, String> = emptyMap()
    withTemporaryDirectory("dyn4k-inventory-") { directory ->
        val snapshot = directory.resolve("baseline.jar")
        copyFile(binary, snapshot)
        binaryHash = digest(snapshot)
        if (binaryHash != policy.binarySha256) {
            throw IllegalArgumentException(
                "baseline SHA-256 mismatch: expected ${policy.binarySha256}, got $binaryHash",
            )
        }
        val inventory = seams.jarInventory(snapshot, null, "-protected", true)
        if (digest(snapshot) != binaryHash) {
            throw IllegalArgumentException("baseline snapshot SHA-256 changed during inventory")
        }
        classes = inventory.classes
        signatures = inventory.signatures
    }
    checkedJavaSources(seams, source, policy.commit, checked.pinned, processEnvironment)
    val apiTypes = sortedByCodePoint(signatures.keys.filter { surface(signatures.getValue(it)) != null })
    val data = buildJsonObject {
        put(
            "baseline",
            buildJsonObject {
                put("coordinate", policy.coordinate)
                put("commit", policy.commit)
                put("binary_sha256", binaryHash)
            },
        )
        put("production_java_files", stringArray(checked.production))
        put("test_java_files", stringArray(checked.tests))
        put("source_input_sha256", JsonObject(sourceHashes.mapValues { JsonPrimitive(it.value) }))
        put("test_annotations", annotationCount)
        put("types", stringArray(classes))
        put("api_types", stringArray(apiTypes))
        put(
            "public_protected_jvm_signatures",
            JsonObject(signatures.mapValues { JsonPrimitive(it.value) }),
        )
    }
    output.parent?.let { makeDirectories(it) }
    writeText(output, PythonJson.renderIndented(data, sortKeys = true) + "\n")
    return data
}
