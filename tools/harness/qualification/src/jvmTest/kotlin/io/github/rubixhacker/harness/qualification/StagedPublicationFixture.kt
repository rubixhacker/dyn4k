package io.github.rubixhacker.harness.qualification

import io.github.rubixhacker.harness.contract.Qualification
import io.github.rubixhacker.harness.contract.Sha256
import java.io.ByteArrayOutputStream
import java.nio.file.Files
import java.nio.file.Path
import java.security.MessageDigest
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/** The candidate every generated staging fixture belongs to. */
internal const val FIXTURE_CANDIDATE = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

/** One programmatically staged tree: the staging repository and its canonical stage evidence. */
internal class StagedTree(
    val root: Path,
    val staging: Path,
    val receipt: Path,
    val console: Path,
    val targets: List<String>,
)

/**
 * `test_publication.PublicationAuditTests.stage`: a staged publication for any target tuple.
 *
 * Every byte follows the reference builder: the POM identity and dependency list, the binary
 * (licensed JAR, or the KLIB layout for an Apple target), the sources and javadoc archives, the
 * `-license.md`, the Apple `-metadata.jar`, the Gradle module with its `Api`/`Runtime`/`Sources`/
 * `Metadata` variants (and, for a root module, the `available-at` map over every matrix target),
 * and a `SHA-256` sidecar beside each staged file. The `.qualification/` receipt and console are
 * included because `StagingAudit.verifyAuditAgainstStaging` only accepts canonical evidence.
 */
internal fun stagedPublication(
    root: Path,
    targets: List<String> = listOf("jvm", "js"),
    advanceClocks: Boolean = false,
    candidateSha: String = FIXTURE_CANDIDATE,
): StagedTree {
    val license = "Fixture license\n".toByteArray()
    plainWrite(root.resolve("LICENSE.md"), license)
    plainWrite(root.resolve(".gitattributes"), "*.kt -text\n*.java -text\n".toByteArray())
    val staging = root.resolve("build/staging-repository")
    val names = mutableListOf<String>()
    for (module in Qualification.modules) names.add(module)
    for (module in Qualification.modules) {
        for (target in targets) names.add(Qualification.targetPublicationName(module, target))
    }
    for (name in names) {
        val module = if (name.startsWith("dyn4k-core")) "dyn4k-core" else "dyn4k"
        val target: String? = if (name == module) {
            null
        } else {
            targets.first { Qualification.targetPublicationName(module, it) == name }
        }
        val base = staging.resolve(Qualification.GROUP.replace(".", "/"))
            .resolve(name)
            .resolve(Qualification.VERSION)
        val version = Qualification.VERSION
        val pom = pomText(module, name, target)
        fixtureWrite(base.resolve("$name-$version.pom"), pom.toByteArray())
        val apple = target != null && Qualification.isAppleTarget(target)
        val binaryRelative: String = if (target == null) {
            Qualification.publicationBinaryPath(module, null)
        } else {
            Qualification.publicationBinaryPath(module, target)
        }
        val binaryFile = staging.resolve(binaryRelative)
        if (apple) {
            fixtureWrite(
                binaryFile,
                zipBytes(
                    listOf(
                        "default/manifest" to "unique_name=fixture\n",
                        "default/linkdata/module" to "module",
                        "default/linkdata/package_api/0_api.knm" to "metadata",
                        "default/ir/bodies.knb" to "ir",
                    ),
                ),
            )
        } else {
            fixtureWrite(
                binaryFile,
                zipBytes(
                    listOf(
                        "META-INF/LICENSE.md" to "Fixture license\n",
                        "api/Type.class" to "class",
                    ),
                ),
            )
        }
        val sourcesFile = base.resolve("$name-$version-sources.jar")
        fixtureWrite(
            sourcesFile,
            zipBytes(
                listOf(
                    "META-INF/MANIFEST.MF" to "Manifest-Version: 1.0\r\n\r\n",
                    "commonMain/api/Type.kt" to "// Fixture notice\npackage api\nclass Type\n",
                ),
            ),
        )
        val javadocFile = base.resolve("$name-$version-javadoc.jar")
        fixtureWrite(
            javadocFile,
            zipBytes(
                listOf(
                    "META-INF/MANIFEST.MF" to "Manifest-Version: 1.0\r\n\r\n",
                    "META-INF/LICENSE.md" to "Fixture license\n",
                    "index.html" to "<html><body>Type API</body></html>",
                    "api/Type/index.html" to "<html><body>Type members</body></html>",
                ),
                advanceClocks = advanceClocks,
            ),
        )
        plainWrite(
            root.resolve(module).resolve("src/commonMain/kotlin/api/Type.kt"),
            "// Fixture notice\npackage api\nclass Type\n".toByteArray(),
        )
        plainWrite(
            root.resolve(module).resolve("build/dokka/html/index.html"),
            "<html><body>Type API</body></html>".toByteArray(),
        )
        plainWrite(
            root.resolve(module).resolve("build/dokka/html/api/Type/index.html"),
            "<html><body>Type members</body></html>".toByteArray(),
        )
        fixtureWrite(base.resolve("$name-$version-license.md"), license)
        if (apple) {
            fixtureWrite(
                base.resolve("$name-$version-metadata.jar"),
                zipBytes(listOf("META-INF/MANIFEST.MF" to "Manifest-Version: 1.0\r\n\r\n")),
            )
        }
        val variants = mutableListOf<JsonObject>()
        variants.add(
            variantOf(
                variantName(target, "Api"),
                Qualification.variantAttributes(target, "Api"),
                variantDependencies(module, target),
                listOf(referenced(binaryFile, module, target)),
            ),
        )
        if (target in setOf("jvm", "android", "js", "wasmJs", "wasmWasi")) {
            variants.add(
                variantOf(
                    variantName(target, "Runtime"),
                    Qualification.variantAttributes(target, "Runtime"),
                    variantDependencies(module, target),
                    listOf(referenced(binaryFile, module, target)),
                ),
            )
        }
        variants.add(
            variantOf(
                variantName(target, "Sources"),
                Qualification.variantAttributes(target, "Sources"),
                emptyList(),
                listOf(referenced(sourcesFile, module, target, sources = true)),
            ),
        )
        if (apple) {
            variants.add(
                variantOf(
                    variantName(target, "Metadata"),
                    Qualification.variantAttributes(target, "Metadata"),
                    variantDependencies(module, target),
                    listOf(
                        referenced(
                            base.resolve("$name-$version-metadata.jar"),
                            module,
                            target,
                            plain = true,
                        ),
                    ),
                ),
            )
        }
        if (target == null) {
            for (mapped in Qualification.matrixTargets().sortedWith(CanonicalText::compare)) {
                val mappedName = Qualification.targetPublicationName(module, mapped)
                val available = buildJsonObject {
                    put("group", JsonPrimitive(Qualification.GROUP))
                    put("module", JsonPrimitive(mappedName))
                    put("version", JsonPrimitive(version))
                    put(
                        "url",
                        JsonPrimitive(
                            "../../$mappedName/$version/$mappedName-$version.module",
                        ),
                    )
                }
                val kinds = mutableListOf("Api", "Sources")
                if (mapped in setOf("jvm", "android", "js", "wasmJs", "wasmWasi")) kinds.add("Runtime")
                if (Qualification.isAppleTarget(mapped)) kinds.add("Metadata")
                for (kind in kinds) {
                    variants.add(
                        buildJsonObject {
                            put("name", JsonPrimitive("$mapped${kind}Elements-published"))
                            put(
                                "attributes",
                                JsonObject(
                                    Qualification.variantAttributes(mapped, kind)
                                        .mapValues { JsonPrimitive(it.value) },
                                ),
                            )
                            put("available-at", available)
                        },
                    )
                }
            }
        }
        val component = buildJsonObject {
            put("group", JsonPrimitive(Qualification.GROUP))
            put("module", JsonPrimitive(module))
            put("version", JsonPrimitive(version))
            put(
                "attributes",
                buildJsonObject { put("org.gradle.status", JsonPrimitive("release")) },
            )
            if (target != null) {
                put(
                    "url",
                    JsonPrimitive("../../$module/$version/$module-$version.module"),
                )
            }
        }
        val metadata = buildJsonObject {
            put("formatVersion", JsonPrimitive("1.1"))
            put(
                "createdBy",
                buildJsonObject {
                    put("gradle", buildJsonObject { put("version", JsonPrimitive("9.5.0")) })
                },
            )
            put("component", component)
            put("variants", JsonArray(variants))
        }
        fixtureWrite(base.resolve("$name-$version.module"), metadata.toString().toByteArray())
    }
    val (receipt, console) = stageEvidence(root, staging, targets, candidateSha)
    return StagedTree(root, staging, receipt, console, targets)
}

/** The reference POM of one staged publication. */
private fun pomText(module: String, name: String, target: String?): String {
    val version = Qualification.VERSION
    val dependencies = StringBuilder("<dependencies>")
    if (module == "dyn4k") {
        dependencies.append(
            "<dependency><groupId>${Qualification.GROUP}</groupId>" +
                "<artifactId>${name.replaceFirst("dyn4k", "dyn4k-core")}</artifactId>" +
                "<version>$version</version>" +
                "<scope>${if (target == null) "runtime" else "compile"}</scope></dependency>",
        )
    }
    if (target == "js") {
        dependencies.append(
            "<dependency><groupId>org.jetbrains.kotlin</groupId>" +
                "<artifactId>kotlin-dom-api-compat</artifactId>" +
                "<version>2.4.20</version><scope>compile</scope></dependency>",
        )
    }
    val stdlib = when (target) {
        "js" -> "kotlin-stdlib-js"
        "wasmJs" -> "kotlin-stdlib-wasm-js"
        "wasmWasi" -> "kotlin-stdlib-wasm-wasi"
        else -> "kotlin-stdlib"
    }
    dependencies.append(
        "<dependency><groupId>org.jetbrains.kotlin</groupId><artifactId>$stdlib</artifactId>" +
            "<version>2.4.20</version><scope>${if (target == null) "runtime" else "compile"}</scope>" +
            "</dependency>",
    )
    dependencies.append("</dependencies>")
    val packaging = if (target == null || target == "jvm") {
        ""
    } else {
        "<packaging>${if (target == "android") "aar" else "klib"}</packaging>"
    }
    val title = if (module == "dyn4k-core") "dyn4k core" else "dyn4k"
    val description = if (module == "dyn4k-core") {
        "Kotlin Multiplatform dyn4j 6.0.0 compatible foundation"
    } else {
        "Kotlin conveniences for the dyn4k core"
    }
    return "<?xml version=\"1.0\"?>" +
        "<project xmlns=\"http://maven.apache.org/POM/4.0.0\">" +
        "<modelVersion>4.0.0</modelVersion>" +
        "<groupId>${Qualification.GROUP}</groupId><artifactId>$name</artifactId>" +
        "<version>$version</version>$packaging<name>$title</name>" +
        "<description>$description</description>" +
        "<url>https://github.com/rubixhacker/dyn4k</url>" +
        "<licenses><license><name>BSD 3-Clause License</name>" +
        "<url>https://opensource.org/licenses/BSD-3-Clause</url></license></licenses>" +
        "<developers><developer><id>rubixhacker</id>" +
        "<name>Stewart Boling</name></developer></developers>" +
        "<scm><url>https://github.com/rubixhacker/dyn4k</url></scm>" +
        dependencies + "</project>"
}

/** The Gradle variant name of one target and kind. */
private fun variantName(target: String?, kind: String): String =
    "${target ?: "metadata"}${kind}Elements" + (if (target == null) "" else "-published")

/** The dependencies a variant advertises. */
private fun variantDependencies(module: String, target: String?): List<JsonObject> {
    val result = mutableListOf<JsonObject>()
    result.add(dependencyRef("org.jetbrains.kotlin", "kotlin-stdlib", "2.4.20"))
    if (target == "js") result.add(dependencyRef("org.jetbrains.kotlin", "kotlin-dom-api-compat", "2.4.20"))
    if (module == "dyn4k") result.add(dependencyRef(Qualification.GROUP, "dyn4k-core", Qualification.VERSION))
    return result
}

/** One `dependencies` entry. */
private fun dependencyRef(group: String, module: String, version: String): JsonObject = buildJsonObject {
    put("group", JsonPrimitive(group))
    put("module", JsonPrimitive(module))
    put("version", buildJsonObject { put("requires", JsonPrimitive(version)) })
}

/** One variant record. */
private fun variantOf(
    name: String,
    attributes: Map<String, String>,
    dependencies: List<JsonObject>,
    files: List<JsonObject>,
): JsonObject = buildJsonObject {
    put("name", JsonPrimitive(name))
    put(
        "attributes",
        JsonObject(attributes.mapValues { JsonPrimitive(it.value) }),
    )
    if (dependencies.isNotEmpty()) put("dependencies", JsonArray(dependencies))
    if (files.isNotEmpty()) put("files", JsonArray(files))
}

/** The reference `referenced()` record of one staged file. */
private fun referenced(
    path: Path,
    module: String,
    target: String?,
    sources: Boolean = false,
    plain: Boolean = false,
): JsonObject {
    val bytes = Files.readAllBytes(path)
    val name = if (plain) {
        path.fileName.toString()
    } else when {
        sources && target == null -> "$module-kotlin-${Qualification.VERSION}-sources.jar"
        sources -> path.fileName.toString()
        target == null -> "$module-metadata-${Qualification.VERSION}.jar"
        target == "android" -> "$module.aar"
        target !in setOf("jvm", "js", "wasmJs", "wasmWasi") ->
            "$module-$target" + "Main-${Qualification.VERSION}.klib"
        else -> path.fileName.toString()
    }
    return buildJsonObject {
        put("name", JsonPrimitive(name))
        put("url", JsonPrimitive(path.fileName.toString()))
        put("size", JsonPrimitive(bytes.size))
        for (algorithm in listOf("sha512", "sha256", "sha1", "md5")) {
            put(algorithm, JsonPrimitive(hexDigest(algorithm, bytes)))
        }
    }
}

/** Writes one staged file and its `SHA-256` sidecar. */
internal fun fixtureWrite(path: Path, bytes: ByteArray) {
    plainWrite(path, bytes)
    plainWrite(
        path.resolveSibling(path.fileName.toString() + ".sha256"),
        (Sha256.of(bytes) + "\n").toByteArray(),
    )
}

/** Writes one fixture file with no sidecar. */
internal fun plainWrite(path: Path, bytes: ByteArray) {
    path.parent?.let { Files.createDirectories(it) }
    Files.write(path, bytes)
}

/** Builds a ZIP with the reference's member contents and clock behaviour. */
internal fun zipBytes(
    entries: List<Pair<String, String>>,
    advanceClocks: Boolean = false,
): ByteArray {
    val out = ByteArrayOutputStream()
    ZipOutputStream(out).use { archive ->
        for ((index, entry) in entries.withIndex()) {
            val member = ZipEntry(entry.first)
            // `zipfile.ZipInfo(member, (1980, 1, 1, 0, 0, 0))`, or an advancing clock that models
            // the reference's patched `zipfile.time.localtime`.
            member.time = if (advanceClocks) 1792300000000L + index * 2000L else 315532800000L
            archive.putNextEntry(member)
            archive.write(entry.second.toByteArray())
            archive.closeEntry()
        }
    }
    return out.toByteArray()
}

/** The canonical `.qualification/` stage receipt and console of one tree. */
private fun stageEvidence(
    root: Path,
    staging: Path,
    targets: List<String>,
    candidateSha: String,
): Pair<Path, Path> {
    val sorted = targets.sortedWith(CanonicalText::compare)
    val tasks = StageReceipt.publicationTasks(sorted)
    val directory = staging.resolve(".qualification/test")
    val console = directory.resolve("stage.log")
    plainWrite(
        console,
        (tasks.joinToString("") { "> Task $it\n" } + "BUILD SUCCESSFUL\n").toByteArray(),
    )
    val receipt = directory.resolve("receipt.json")
    val value = buildJsonObject {
        put("candidate_sha", JsonPrimitive(candidateSha))
        put("repository", JsonPrimitive(root.toString()))
        put("targets", JsonArray(sorted.map { JsonPrimitive(it) }))
        put("tasks", JsonArray(tasks.map { JsonPrimitive(it) }))
        put("command", JsonArray(StageReceipt.stageCommand(root, tasks).map { JsonPrimitive(it) }))
        put("status", JsonPrimitive("PASSED"))
        put("exit_code", JsonPrimitive(0))
        put("console_sha256", JsonPrimitive(Sha256.of(Files.readAllBytes(console))))
    }
    plainWrite(receipt, value.toString().toByteArray())
    return receipt to console
}

/** One hex digest of a staged file. */
private fun hexDigest(algorithm: String, bytes: ByteArray): String {
    val name = when (algorithm) {
        "sha512" -> "SHA-512"
        "sha256" -> "SHA-256"
        "sha1" -> "SHA-1"
        else -> "MD5"
    }
    return MessageDigest.getInstance(name).digest(bytes).joinToString("") { "%02x".format(it) }
}
