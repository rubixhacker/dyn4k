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
val version = "0.1.0-alpha.1"

layout.buildDirectory.set(file("$workRoot/root"))
subprojects {
    layout.buildDirectory.set(file("$workRoot/${project.name}"))
}

fun hash(file: File): String = MessageDigest.getInstance("SHA-256")
    .digest(file.readBytes()).joinToString("") { "%02x".format(it) }

fun staged(module: String): File = file(
    "$staging/io/github/rubixhacker/$module-js/$version/$module-js-$version.klib")

fun graph(projectName: String, name: String): Map<String, Any> {
    val resolved = project(":$projectName").configurations.getByName(name)
    val components = resolved.incoming.resolutionResult.allComponents
        .map { it.id.displayName }.sorted()
    val artifacts = resolved.resolvedConfiguration.resolvedArtifacts.map { artifact ->
        mapOf("component" to artifact.moduleVersion.id.toString(),
            "file" to artifact.file.absolutePath, "name" to artifact.file.name,
            "size" to artifact.file.length(), "sha256" to hash(artifact.file))
    }.sortedWith(compareBy({ it["component"].toString() }, { it["name"].toString() }))
    return mapOf("project" to projectName, "configuration" to name,
        "components" to components, "artifacts" to artifacts)
}

tasks.register("qualificationValidateInputs") {
    doLast {
        check(lane.matches(Regex("js:Chromium:(minimum|current):(development|production)")))
        val inventory = file(providers.gradleProperty("qualificationSourceInventory").get())
        val sources = inventory.readLines().filter { it.isNotBlank() }.associate { line ->
            val parts = line.split('\t')
            check(parts.size == 2)
            parts[0] to parts[1]
        }
        check(sources.isNotEmpty() && sources.size == inventory.readLines().size)
        val roots = listOf("dyn4k-core/src/commonTest/kotlin", "dyn4k/src/commonTest/kotlin",
            "dyn4k-core/src/jsTest/kotlin")
        val live = roots.flatMap { root ->
            file("$checkout/$root").walkTopDown().filter { it.isFile && it.extension == "kt" }
                .map { it.relativeTo(checkout).invariantSeparatorsPath }.toList()
        }.toSet()
        check(sources.keys == live)
        sources.forEach { (path, digest) -> check(hash(file("$checkout/$path")) == digest) }
        for (module in listOf("dyn4k-core", "dyn4k")) {
            val key = if (module == "dyn4k-core") "qualificationCoreSha256" else "qualificationFacadeSha256"
            check(hash(staged(module)) == providers.gradleProperty(key).get())
        }
        println("QUALIFICATION_INPUT_SOURCE_COUNT=${sources.size}")
    }
}

tasks.register("qualificationGraphs") {
    dependsOn("qualificationValidateInputs")
    doLast {
        val graphs = mapOf(
            "compile" to listOf("core", "facade").map { graph(it, "jsTestCompileClasspath") },
            "runtime" to listOf("core", "facade").map { graph(it, "jsTestRuntimeClasspath") },
            "gradle_user_home" to gradle.gradleUserHomeDir.absolutePath)
        val path = file("$archive/provider-graph.json")
        path.parentFile.mkdirs()
        path.writeText(JsonOutput.toJson(graphs))
        println("QUALIFICATION_LANE=$lane")
        println("QUALIFICATION_PROVIDER_GRAPH_SHA256=${hash(path)}")
        for (module in listOf("dyn4k-core", "dyn4k")) {
            val copy = file("$archive/resolved/$module-js-$version.klib")
            copy.parentFile.mkdirs()
            staged(module).copyTo(copy, overwrite = true)
            println("QUALIFICATION_RESOLVED_${module.uppercase().replace('-', '_')}_SHA256=${hash(copy)}")
        }
    }
}
