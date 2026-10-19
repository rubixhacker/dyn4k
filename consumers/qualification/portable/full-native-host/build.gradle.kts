import groovy.json.JsonOutput
import java.security.MessageDigest

plugins {
    kotlin("multiplatform") version "2.4.20" apply false
}

val checkout = file(providers.gradleProperty("qualificationCheckout").get())
val staging = file(providers.gradleProperty("qualificationRepository").get())
val archive = file(providers.gradleProperty("qualificationArchiveRoot").get())
val workRoot = file(providers.gradleProperty("qualificationWorkRoot").get())
val lane = providers.gradleProperty("qualificationLaneId").get()
val target = lane.substringBefore(':')
val variant = target.lowercase()
val version = "0.1.0-alpha.1"
val expected = mapOf(
    "dyn4k-core" to providers.gradleProperty("qualificationCoreSha256").get(),
    "dyn4k" to providers.gradleProperty("qualificationFacadeSha256").get(),
)

subprojects {
    layout.buildDirectory.set(file("$workRoot/${project.name}"))
}

fun hash(path: File): String = MessageDigest.getInstance("SHA-256")
    .digest(path.readBytes()).joinToString("") { "%02x".format(it) }

fun staged(module: String) = file(
    "$staging/io/github/rubixhacker/$module-$variant/$version/$module-$variant-$version.klib")

tasks.register("qualificationValidateInputs") {
    doLast {
        val lines = file(providers.gradleProperty("qualificationSourceInventory").get()).readLines()
        val sources = lines.associate { line ->
            val parts = line.split('\t')
            check(parts.size == 2)
            parts[0] to parts[1]
        }
        val roots = listOf("dyn4k-core/src/commonTest/kotlin", "dyn4k/src/commonTest/kotlin",
            "dyn4k-core/src/nativeTest/kotlin")
        val live = roots.flatMap { root ->
            file("$checkout/$root").walkTopDown().filter { it.isFile && it.extension == "kt" }
                .map { it.relativeTo(checkout).invariantSeparatorsPath }.toList()
        }.toSet()
        check(lines.isNotEmpty() && lines.size == sources.size && sources.keys == live)
        sources.forEach { (path, digest) -> check(hash(file("$checkout/$path")) == digest) }
        expected.forEach { (module, digest) -> check(hash(staged(module)) == digest) }
        println("QUALIFICATION_SOURCE_COUNT=${sources.size}")
    }
}

tasks.register("qualificationGraphs") {
    dependsOn("qualificationValidateInputs")
    doLast {
        val name = "${target}TestCompileKlibraries"
        val entries = listOf("core", "facade").map { short ->
            val resolved = project(":$short").configurations.getByName(name)
            mapOf("project" to short, "configuration" to name,
                "components" to resolved.incoming.resolutionResult.allComponents
                    .map { it.id.displayName }.sorted(),
                "artifacts" to resolved.resolvedConfiguration.resolvedArtifacts.map { artifact ->
                    mapOf("component" to artifact.moduleVersion.id.toString(),
                        "file" to artifact.file.absolutePath, "name" to artifact.file.name,
                        "size" to artifact.file.length(), "sha256" to hash(artifact.file))
                }.sortedBy { it["component"].toString() })
        }
        val graph = file("$archive/provider-graph.json")
        graph.parentFile.mkdirs()
        graph.writeText(JsonOutput.toJson(mapOf("compile" to entries,
            "runtime" to entries, "gradle_user_home" to gradle.gradleUserHomeDir.absolutePath)))
        println("QUALIFICATION_PROVIDER_GRAPH_SHA256=${hash(graph)}")
        expected.forEach { (module, _) ->
            val resolved = project(if (module == "dyn4k-core") ":core" else ":facade")
                .configurations.getByName(name).resolvedConfiguration.resolvedArtifacts
                .single { it.moduleVersion.id.name == "$module-$variant" }.file
            check(hash(resolved) == expected[module])
            val copy = file("$archive/resolved/$module-$variant-$version.klib")
            copy.parentFile.mkdirs()
            resolved.copyTo(copy, overwrite = true)
            println("QUALIFICATION_RESOLVED_${module.uppercase().replace('-', '_')}_SHA256=${hash(copy)}")
        }
    }
}

tasks.register("qualificationEvidence") {
    dependsOn("qualificationGraphs", ":core:${target}Test", ":facade:${target}Test")
    doLast {
        println("QUALIFICATION_LANE=$lane")
        val command = listOf(providers.gradleProperty("qualificationPython").get(),
            "$checkout/tools/qualification/full_native_host_consumer.py",
            "capture", "--repository", checkout.absolutePath,
            "--archive", archive.absolutePath, "--work-root", workRoot.absolutePath,
            "--lane", lane,
            "--core-cases", providers.gradleProperty("qualificationCoreCases").get(),
            "--facade-cases", providers.gradleProperty("qualificationFacadeCases").get())
        val process = ProcessBuilder(command).directory(rootDir).redirectErrorStream(true).start()
        val output = process.inputStream.bufferedReader().readText()
        if (output.isNotBlank()) logger.lifecycle(output.trimEnd())
        check(process.waitFor() == 0) { "native original result capture failed" }
    }
}
