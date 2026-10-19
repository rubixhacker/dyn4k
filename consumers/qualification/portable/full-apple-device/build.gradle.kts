import groovy.json.JsonOutput
import java.security.MessageDigest

plugins { kotlin("multiplatform") version "2.4.20" apply false }

val checkout = file(providers.gradleProperty("qualificationCheckout").get())
val staging = file(providers.gradleProperty("qualificationRepository").get())
val evidence = file(providers.gradleProperty("qualificationEvidence").get())
val target = providers.gradleProperty("qualificationTarget").get()
val variant = target.lowercase()
val workRoot = file(providers.gradleProperty("qualificationWorkRoot").get())
val version = "0.1.0-alpha.1"

check(target in setOf("iosArm64", "tvosArm64", "watchosArm64", "watchosDeviceArm64"))
subprojects { layout.buildDirectory.set(file("$workRoot/${project.name}")) }

fun hash(file: File) = MessageDigest.getInstance("SHA-256")
    .digest(file.readBytes()).joinToString("") { "%02x".format(it) }

tasks.register("qualificationValidateInputs") {
    doLast {
        val inventory = file(providers.gradleProperty("qualificationSourceInventory").get())
        val rows = inventory.readLines().map { it.split('\t') }
        check(rows.isNotEmpty() && rows.all { it.size == 2 })
        val expected = rows.associate { it[0] to it[1] }
        check(expected.size == rows.size)
        val roots = listOf("dyn4k-core/src/commonTest/kotlin",
            "dyn4k-core/src/nativeTest/kotlin", "dyn4k/src/commonTest/kotlin")
        val actual = roots.flatMap { root ->
            file("$checkout/$root").walkTopDown().filter { it.isFile && it.extension == "kt" }
                .map { it.relativeTo(checkout).invariantSeparatorsPath }.toList()
        }.toSet()
        check(actual == expected.keys)
        expected.forEach { (path, digest) -> check(hash(file("$checkout/$path")) == digest) }
        for (module in listOf("dyn4k-core", "dyn4k")) {
            val staged = file("$staging/io/github/rubixhacker/$module-$variant/$version/$module-$variant-$version.klib")
            val property = if (module == "dyn4k-core") "qualificationCoreSha256" else "qualificationFacadeSha256"
            check(hash(staged) == providers.gradleProperty(property).get())
        }
        println("QUALIFICATION_INPUT_SOURCE_COUNT=${expected.size}")
    }
}

tasks.register("qualificationGraphs") {
    dependsOn("qualificationValidateInputs")
    doLast {
        val configuration = "${target}TestCompileKlibraries"
        val graphs = listOf("core", "facade").map { name ->
            val resolved = project(":$name").configurations.getByName(configuration)
            mapOf("project" to name, "configuration" to configuration,
                "components" to resolved.incoming.resolutionResult.allComponents
                    .map { it.id.displayName }.sorted(),
                "artifacts" to resolved.resolvedConfiguration.resolvedArtifacts.map { artifact ->
                    mapOf("component" to artifact.moduleVersion.id.toString(),
                        "file" to artifact.file.absolutePath, "name" to artifact.file.name,
                        "sha256" to hash(artifact.file))
                }.sortedBy { it["component"] })
        }
        evidence.mkdirs()
        val graph = file("$evidence/provider-graph.json")
        graph.writeText(JsonOutput.toJson(mapOf("compile" to graphs,
            "gradle_user_home" to gradle.gradleUserHomeDir.absolutePath)))
        println("QUALIFICATION_PROVIDER_GRAPH_SHA256=${hash(graph)}")
        println("QUALIFICATION_LANE=${providers.gradleProperty("qualificationLaneId").get()}")
    }
}
