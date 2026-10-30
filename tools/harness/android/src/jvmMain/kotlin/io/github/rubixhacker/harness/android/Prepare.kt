package io.github.rubixhacker.harness.android

import java.nio.file.Files
import java.nio.file.Path
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject

/**
 * `tools/android-runtime/prepare.py`: the prepared candidate manifest.
 *
 * Everything the installed routes compare is pinned here — build identity, staged publications,
 * baseline JAR, portable suite JAR, generated consumer sources, the full app inputs, and the raw JVM XML
 * evidence — so a later installed run cannot silently consume different bytes.
 */
object Prepare {
    /** The SHA-256 of the pinned dyn4j 6.0.0 baseline JAR. */
    const val BASELINE_SHA256 =
        "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"

    /** `prepare.prepare`. */
    fun prepare(root: Path, rootBuildLog: Path): JsonObject {
        val jdk = BuildIdentity.currentJava(JvmBuildHost)
        val rootBuild = BuildIdentityFiles.buildLogIdentity(rootBuildLog)
        val app = root.resolve("consumers/android-runtime/app")
        val generated = app.resolve("build/generated")
        val javaOut = generated.resolve("consumer-java")
        Files.createDirectories(javaOut)
        val sourceHashes = linkedMapOf<String, JsonElement>()
        val generatedHashes = linkedMapOf<String, JsonElement>()
        for (name in PrepareContract.CONSUMERS) {
            val source = root.resolve("dyn4k-core/src/jvmConsumer/java/$name.java")
            if (!Files.isRegularFile(source)) {
                throw IllegalArgumentException("consumer source missing: $source")
            }
            val destination = javaOut.resolve("$name.java")
            Files.createDirectories(destination.parent)
            destination.toFile().writeBytes(
                PrepareContract.androidConsumerSource(
                    Path.of("$name.java").fileName.toString().removeSuffix(".java"),
                    source.toFile().readBytes(),
                ),
            )
            val relativeSource = posix(root.relativize(source))
            val digest = sha256(source)
            sourceHashes[relativeSource] = JsonPrimitive(digest)
            generatedHashes[posix(root.relativize(destination))] = buildJsonObject {
                put("source", JsonPrimitive(relativeSource))
                put("sha256", JsonPrimitive(sha256(destination)))
            }
        }

        val suite = AndroidFiles.loadSuite(root)
        val xmlEvidence = AndroidFiles.verifyJvmXml(root, suite.cases, AndroidFiles.commitTimeNs(root))
        val classes = AndroidFiles.portableClasses(root, suite.cases)
        val fullInputs = AndroidFiles.writeFullInputs(root, suite.cases)
        val fullJavaOut = root.resolve("consumers/android-runtime/full/build/generated/consumer-java")
        Files.createDirectories(fullJavaOut)
        val fullCopies = linkedMapOf<String, JsonElement>()
        for (name in PrepareContract.CONSUMERS) {
            val source = root.resolve("dyn4k-core/src/jvmConsumer/java/$name.java")
            val destination = fullJavaOut.resolve("$name.java")
            Files.createDirectories(destination.parent)
            destination.toFile().writeBytes(
                PrepareContract.androidConsumerSource(
                    Path.of("$name.java").fileName.toString().removeSuffix(".java"),
                    source.toFile().readBytes(),
                ),
            )
            fullCopies[posix(root.relativize(destination))] = buildJsonObject {
                put("source", JsonPrimitive(posix(root.relativize(source))))
                put("sha256", JsonPrimitive(sha256(destination)))
            }
        }
        val jar = generated.resolve("portable-suite.jar")
        val jvmOnly = suite.cases.filter { it.scope == "jvm-only" }.map { it.classname }.toSet()
        AndroidFiles.buildPortableJar(root, jar, jvmOnly)

        val staged = linkedMapOf<String, JsonElement>()
        for (artifact in listOf("dyn4k-core-android", "dyn4k-android")) {
            val path = root.resolve(
                "build/staging-repository/io/github/rubixhacker/$artifact/" +
                    "${PrepareContract.VERSION}/$artifact-${PrepareContract.VERSION}.aar",
            )
            if (!Files.isRegularFile(path)) {
                throw IllegalArgumentException("staged Android AAR missing: $path")
            }
            staged[artifact] = buildJsonObject {
                put("path", JsonPrimitive(posix(path)))
                put("sha256", JsonPrimitive(sha256(path)))
            }
        }
        val stagedRoots = linkedMapOf<String, JsonElement>()
        for (artifact in listOf("dyn4k-core", "dyn4k")) {
            for (extension in listOf("module", "pom")) {
                val path = root.resolve(
                    "build/staging-repository/io/github/rubixhacker/$artifact/" +
                        "${PrepareContract.VERSION}/$artifact-${PrepareContract.VERSION}.$extension",
                )
                if (!Files.isRegularFile(path)) {
                    throw IllegalArgumentException("staged publication root missing: $path")
                }
                stagedRoots["$artifact.$extension"] = buildJsonObject {
                    put("path", JsonPrimitive(posix(path)))
                    put("sha256", JsonPrimitive(sha256(path)))
                }
            }
        }
        val fullJavaJar = AndroidFiles.compileFullConsumers(root, fullCopies.mapValues { it.value.jsonObject }, staged.mapValues { it.value.jsonObject })
        var baseline = root.resolve("tools/baseline/dyn4j-6.0.0.jar")
        if (!Files.isRegularFile(baseline)) {
            val cache = Path.of(System.getProperty("user.home"))
                .resolve(".gradle/caches/modules-2/files-2.1/org.dyn4j/dyn4j/6.0.0")
            val matches = if (Files.isDirectory(cache)) {
                Files.walk(cache).use { stream ->
                    stream.filter {
                        Files.isRegularFile(it) && it.fileName.toString() == "dyn4j-6.0.0.jar"
                    }.toList()
                }
            } else {
                emptyList()
            }
            if (matches.size != 1) {
                throw IllegalArgumentException("pinned baseline JAR unavailable")
            }
            baseline = matches[0]
        }
        if (sha256(baseline) != BASELINE_SHA256) {
            throw IllegalArgumentException("baseline JAR checksum mismatch")
        }
        val commit = LaneHost.command(listOf("git", "rev-parse", "HEAD"), null, true, root).trim()
        val result = buildJsonObject {
            put("candidate_commit", JsonPrimitive(commit))
            put("build_jdk", jdk.toJson())
            put("root_build", rootBuild.toJson())
            put("staged", JsonObject(staged))
            put("staged_roots", JsonObject(stagedRoots))
            put("baseline_jar", buildJsonObject {
                put("path", JsonPrimitive(posix(baseline)))
                put("sha256", JsonPrimitive(sha256(baseline)))
            })
            put("portable_classes", kotlinx.serialization.json.JsonArray(classes.map { JsonPrimitive(it) }))
            put("suite_manifest", suite.binding)
            put("jvm_xml", xmlEvidence.toJson())
            put("portable_jar", buildJsonObject {
                put("path", JsonPrimitive(posix(jar)))
                put("sha256", JsonPrimitive(sha256(jar)))
            })
            put("consumer_sources", JsonObject(sourceHashes))
            put("generated_consumer_sources", JsonObject(generatedHashes))
            put("full_generated_consumer_sources", JsonObject(fullCopies))
            put("full_java_jar", fullJavaJar)
            put("full_inputs", JsonObject(fullInputs))
        }
        AndroidFiles.verifyConsumerSources(root, result)
        AndroidFiles.verifyFullConsumerSources(root, result)
        AndroidFiles.verifyFullInputs(root, suite.cases, result.objectOrNull("full_inputs"))
        return result
    }

    /** `prepare.main --verify-consumers`: every prepared input still describes this checkout. */
    fun verifyConsumers(root: Path, manifestPath: Path) {
        val bytes = manifestPath.toFile().readBytes()
        val prepared = FullHost.parseJson(bytes)
        val commit = LaneHost.command(listOf("git", "rev-parse", "HEAD"), null, true, root).trim()
        if (prepared.textOrNull("candidate_commit") != commit) {
            throw IllegalArgumentException("candidate commit differs from prepared consumer sources")
        }
        if (prepared["build_jdk"] != BuildIdentity.currentJava(JvmBuildHost).toJson()) {
            throw IllegalArgumentException("prepared JDK identity differs")
        }
        BuildIdentityFiles.verifyBuildLogIdentity(
            prepared.getValue("root_build").objectOrNull()
                ?: throw IllegalArgumentException("prepared JDK identity differs"),
        )
        AndroidFiles.verifyConsumerSources(root, prepared)
        AndroidFiles.verifyFullConsumerSources(root, prepared)
        val suite = AndroidFiles.loadSuite(root)
        AndroidFiles.verifyFullInputs(root, suite.cases, prepared.objectOrNull("full_inputs"))
        AndroidFiles.verifyXmlPins(root, prepared)
    }
}

/** `BuildJdk` as a JSON object, in the field order Python records. */
internal fun BuildJdk.toJson(): JsonObject = buildJsonObject {
    put("java_home", JsonPrimitive(javaHome))
    put("java_version", JsonPrimitive(javaVersion))
    put("gradle_version", JsonPrimitive(gradleVersion))
}
