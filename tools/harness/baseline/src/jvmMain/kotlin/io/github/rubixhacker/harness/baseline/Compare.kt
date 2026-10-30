package io.github.rubixhacker.harness.baseline

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.IOException
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption

/** `verify._compare_jars_snapshot`'s report, in the order the command prints it. */
data class CompareReport(
    val baselineTypes: Int,
    val candidateTypes: Int,
    val comparedBaselineDeclarations: Int,
    val comparedApiTypes: List<String>,
    val missingTypes: List<String>,
    val signatureMismatches: List<String>,
    val compatibleDifferences: List<String>,
    val baselineSha256: String,
    val candidateSha256: String,
    val dependencySha256: Map<String, String>,
    val addedMemberRisks: List<MemberRisk>,
    val inventoryErrors: List<String>,
    val fixtureResults: List<FixtureResult>,
    val fixtureFailures: List<String>,
    val fixtureErrors: List<String>,
) {
    /** The failure set the command exits non-zero on. */
    fun hasProblems(): Boolean =
        missingTypes.isNotEmpty() || signatureMismatches.isNotEmpty() ||
            addedMemberRisks.isNotEmpty() || inventoryErrors.isNotEmpty() ||
            fixtureFailures.isNotEmpty() || fixtureErrors.isNotEmpty()

    fun toJson(): JsonObject = buildJsonObject {
        put("baseline_types", baselineTypes)
        put("candidate_types", candidateTypes)
        put("compared_baseline_declarations", comparedBaselineDeclarations)
        put("compared_api_types", stringArray(comparedApiTypes))
        put("missing_types", stringArray(missingTypes))
        put("signature_mismatches", stringArray(signatureMismatches))
        put("compatible_differences", stringArray(compatibleDifferences))
        put("baseline_sha256", baselineSha256)
        put("candidate_sha256", candidateSha256)
        put("dependency_sha256", JsonObject(dependencySha256.mapValues { JsonPrimitive(it.value) }))
        put("added_member_risks", buildJsonArray { addedMemberRisks.forEach { add(it.toJson()) } })
        put("inventory_errors", stringArray(inventoryErrors))
        put("fixture_results", fixtureResults.toJsonArray())
        put("fixture_failures", stringArray(fixtureFailures))
        put("fixture_errors", stringArray(fixtureErrors))
    }
}

internal fun stringArray(values: Collection<String>): JsonArray =
    buildJsonArray { values.forEach { add(JsonPrimitive(it)) } }

/**
 * `verify.compare_jars`: snapshot the pinned baseline and the candidate, compare every selected
 * baseline type's source surface, gate the candidate's added members, compile the Java 8 fixtures,
 * and prove no snapshot changed while that ran.
 */
fun compareJars(
    baseline: Path,
    candidate: Path,
    only: Set<String>? = null,
    visibility: String = "-protected",
    fixtures: List<Path> = emptyList(),
    requireFixture: Boolean = false,
    dependencies: List<Path> = emptyList(),
    policy: BaselinePolicy = BaselinePolicy(),
    seams: BaselineSeams = RealSeams,
): CompareReport = withTemporaryDirectory("dyn4k-candidate-") { directory ->
    val baselineSnapshot = directory.resolve("baseline.jar")
    copyFile(baseline, baselineSnapshot)
    val baselineHash = digest(baselineSnapshot)
    if (baselineHash != policy.binarySha256) {
        throw IllegalArgumentException(
            "baseline SHA-256 mismatch: expected ${policy.binarySha256}, got $baselineHash",
        )
    }
    val snapshot = directory.resolve("candidate.jar")
    copyFile(candidate, snapshot)
    val dependencySnapshots = mutableListOf<Triple<Path, Path, String>>()
    val dependencyHashes = linkedMapOf<String, String>()
    val dependencyErrors = mutableListOf<String>()
    for ((index, path) in dependencies.withIndex()) {
        if (path.toString() in dependencyHashes) {
            dependencyErrors.add("duplicate dependency JAR: $path")
            continue
        }
        try {
            if (!isFile(path)) throw IllegalArgumentException("missing or empty dependency JAR")
            val dependencySnapshot = directory.resolve("dependency-$index.jar")
            copyFile(path, dependencySnapshot)
            if (Files.size(dependencySnapshot) == 0L) {
                throw IllegalArgumentException("missing or empty dependency JAR")
            }
            val dependencyHash = digest(dependencySnapshot)
            dependencySnapshots.add(Triple(path, dependencySnapshot, dependencyHash))
            dependencyHashes[path.toString()] = dependencyHash
        } catch (error: IOException) {
            dependencyErrors.add("missing or empty dependency JAR: $path")
        } catch (error: IllegalArgumentException) {
            dependencyErrors.add("missing or empty dependency JAR: $path")
        }
    }
    compareSnapshots(
        baselineSnapshot,
        baselineHash,
        snapshot,
        only,
        visibility,
        fixtures,
        requireFixture,
        dependencySnapshots,
        dependencyHashes,
        dependencyErrors,
        policy,
        seams,
    )
}

private fun compareSnapshots(
    baseline: Path,
    baselineHash: String,
    candidate: Path,
    only: Set<String>?,
    visibility: String,
    fixtures: List<Path>,
    requireFixture: Boolean,
    dependencySnapshots: List<Triple<Path, Path, String>>,
    dependencyHashes: Map<String, String>,
    dependencyErrors: List<String>,
    policy: BaselinePolicy,
    seams: BaselineSeams,
): CompareReport {
    val candidateHash = digest(candidate)
    val candidateClasspath = (
        listOf(candidate.toString()) + dependencySnapshots.map { it.second.toString() }
        ).joinToString(java.io.File.pathSeparator)
    val baselineInventory = seams.jarInventory(baseline, only, "-p", true)
    val candidateInventory = seams.jarInventory(
        candidate,
        if (only == null) baselineInventory.classes.toSet() else only,
        "-p",
        true,
    )
    val baselineTypes = baselineInventory.classes
    val baselineSignatures = baselineInventory.signatures
    val candidateTypes = candidateInventory.classes
    val candidateSignatures = candidateInventory.signatures
    if (baselineTypes.isEmpty() || candidateTypes.isEmpty()) {
        throw IllegalArgumentException("empty baseline or candidate class-file inventory")
    }
    val selected = if (only == null) baselineTypes.toSet() else only
    val unknown = sortedByCodePoint(selected - baselineTypes.toSet())
    if (unknown.isNotEmpty()) {
        throw IllegalArgumentException("types absent from baseline: ${unknown.joinToString(", ")}")
    }
    val missing = mutableListOf<String>()
    val mismatches = mutableListOf<String>()
    val compatible = mutableListOf<String>()
    val compared = mutableListOf<String>()
    var declarations = 0
    val typeCache = mutableMapOf<String, TypeContract?>()

    fun candidateInterfaces(typeName: String, seen: MutableSet<String>): Set<String> {
        val raw = typeName.split("<", limit = 2)[0]
        if (!seen.add(typeName)) return emptySet()
        var signature = candidateSignatures[raw]
        if (signature == null) {
            signature = try {
                seams.requireRun(
                    listOf("javap", "-classpath", candidateClasspath, visibility, "-s", "-v", raw),
                ).stdoutText()
            } catch (error: CommandFailure) {
                return emptySet()
            }
        }
        if (raw !in typeCache) {
            val parsed = surface(signature, visibility == "-package")
            typeCache[raw] = parsed?.let { typeContract(it.header) }
        }
        val contract = typeCache[raw] ?: return emptySet()
        val parameters = classTypeParameters(contract.declaration)
        val arguments = if (typeName.length > raw.length + 1 && typeName.startsWith("$raw<")) {
            typeName.substring(raw.length + 1, typeName.length - 1)
        } else {
            ""
        }
        val values = if (arguments.isNotEmpty()) splitTopLevel(arguments, ",") else emptyList()
        val mapping = parameters.zip(values)
            .associate { (parameter, value) -> pySplitWhitespace(parameter)[0] to value }
        val parents = contract.interfaces.map { substituteEveryTypeParameter(it, mapping) }.toSet()
        val interfaces = parents.toMutableSet()
        for (item in parents) interfaces.addAll(candidateInterfaces(item, seen))
        contract.superclass?.let {
            interfaces.addAll(candidateInterfaces(substituteEveryTypeParameter(it, mapping), seen))
        }
        return interfaces
    }

    for (name in sortedByCodePoint(selected)) {
        val expected = surface(baselineSignatures.getValue(name), visibility == "-package")
        if (expected == null) continue
        compared.add(name)
        declarations += expected.members.values.sumOf { it.size }
        if (name !in candidateSignatures) {
            missing.add(name)
            continue
        }
        val actual = surface(candidateSignatures.getValue(name), visibility == "-package")
        if (actual == null) {
            mismatches.add(
                "$name: type access lost: ${expected.header} -> " +
                    (typeHeader(candidateSignatures.getValue(name)) ?: "<no type declaration>"),
            )
            continue
        }
        val expectedType = typeContract(expected.header)
        val actualType = typeContract(actual.header)
        val typeParameters = classTypeParameters(expectedType.declaration)
            .map { pySplitWhitespace(it)[0] }
            .toSet()
        val interfaces = actualType.interfaces.toMutableSet()
        if (!expectedType.interfaces.all { it in interfaces }) {
            interfaces.addAll(candidateInterfaces(name, mutableSetOf()))
        }
        val expectedSuperclass = expectedType.superclass
            ?: if (" class " in " ${expectedType.declaration} ") "java.lang.Object" else null
        val actualSuperclass = actualType.superclass
            ?: if (" class " in " ${actualType.declaration} ") "java.lang.Object" else null
        val contractChanged = !sourceCompatibleDeclaration(expectedType.declaration, actualType.declaration) ||
            expectedSuperclass != actualSuperclass ||
            !expectedType.interfaces.all { it in interfaces }
        if (contractChanged) {
            mismatches.add("$name: type contract changed: ${expected.header} -> ${actual.header}")
        } else if (expected.header != actual.header) {
            compatible.add("$name: compatible type difference: ${expected.header} -> ${actual.header}")
        }
        for ((key, members) in expected.members) {
            for (member in members) {
                val candidateMembers = actual.members[key]
                if (candidateMembers == null) {
                    mismatches.add("$name: missing $member")
                    continue
                }
                if (member in candidateMembers) continue
                val equivalent = candidateMembers.firstOrNull { item ->
                    sourceCompatibleDeclaration(
                        member,
                        item,
                        "descriptor: (" in member,
                        " final class " in " ${expectedType.declaration} " && "descriptor: (" in member,
                    ) || (
                        key.name == name &&
                            constructorListWidening(member, item, typeParameters)
                        )
                }
                if (equivalent == null) {
                    mismatches.add("$name: changed $member -> ${pythonListRepr(candidateMembers)}")
                } else {
                    compatible.add("$name: compatible member difference: $member -> $equivalent")
                }
            }
        }
    }
    val addition = seams.addedMemberGate(
        selected,
        baselineSignatures,
        candidateSignatures,
        baseline.toString(),
        candidateClasspath,
        digest(candidate),
    )
    val inventoryErrors = addition.errors.toMutableList()
    inventoryErrors.addAll(dependencyErrors)
    val audit = fixtureAudit(seams, baseline, fixtures, requireFixture, candidateClasspath, policy)
    if (digest(baseline) != baselineHash) {
        throw IllegalArgumentException("baseline SHA-256 changed during comparison")
    }
    if (digest(candidate) != candidateHash) {
        throw IllegalArgumentException("candidate snapshot SHA-256 changed during comparison")
    }
    for ((path, snapshot, expectedHash) in dependencySnapshots) {
        if (digest(snapshot) != expectedHash) {
            throw IllegalArgumentException(
                "dependency snapshot SHA-256 changed during comparison: $path",
            )
        }
    }
    return CompareReport(
        baselineTypes = baselineTypes.size,
        candidateTypes = candidateTypes.size,
        comparedBaselineDeclarations = declarations,
        comparedApiTypes = compared,
        missingTypes = missing,
        signatureMismatches = mismatches,
        compatibleDifferences = compatible,
        baselineSha256 = baselineHash,
        candidateSha256 = candidateHash,
        dependencySha256 = dependencyHashes,
        addedMemberRisks = addition.risks,
        inventoryErrors = inventoryErrors,
        fixtureResults = audit.results,
        fixtureFailures = audit.failures,
        fixtureErrors = audit.errors,
    )
}
