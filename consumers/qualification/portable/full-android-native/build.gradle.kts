import groovy.json.JsonOutput
import java.security.MessageDigest

plugins { kotlin("multiplatform") version "2.4.20" apply false
    id("de.infix.testBalloon") version "1.2.0" apply false }

val target = providers.gradleProperty("qualificationTarget").get()
check(target in setOf("androidNativeArm32", "androidNativeArm64", "androidNativeX86", "androidNativeX64"))
val variant = target.lowercase()
val staging = file(providers.gradleProperty("qualificationRepository").get())
val archive = file(providers.gradleProperty("qualificationArchiveRoot").get())
val work = file(providers.gradleProperty("qualificationWorkRoot").get())
val version = "0.1.0-alpha.1"

subprojects { layout.buildDirectory.set(file("$work/${project.name}")) }

fun hash(path: File): String = MessageDigest.getInstance("SHA-256")
    .digest(path.readBytes()).joinToString("") { "%02x".format(it) }

fun staged(module: String) = file(
    "$staging/io/github/rubixhacker/$module-$variant/$version/$module-$variant-$version.klib")

tasks.register("qualificationGraph") {
    doLast {
        val entries = listOf("core", "facade").map { name ->
            val configuration = project(":$name").configurations
                .getByName("${target}TestCompileKlibraries")
            mapOf("project" to name,
                "configuration" to configuration.name,
                "components" to configuration.incoming.resolutionResult.allComponents
                    .map { it.id.displayName }.sorted(),
                "artifacts" to configuration.resolvedConfiguration.resolvedArtifacts
                    .map { artifact ->
                        mapOf("component" to artifact.moduleVersion.id.toString(),
                            "name" to artifact.file.name,
                            "file" to artifact.file.absolutePath,
                            "size" to artifact.file.length(),
                            "sha256" to hash(artifact.file))
                    }.sortedBy { it["component"].toString() })
        }
        val graph = file("$archive/provider-graph.json")
        graph.parentFile.mkdirs()
        graph.writeText(JsonOutput.toJson(mapOf("compile" to entries)))
        println("QUALIFICATION_PROVIDER_GRAPH_SHA256=${hash(graph)}")
        for (module in listOf("dyn4k-core", "dyn4k")) {
            val source = staged(module)
            val destination = file("$archive/resolved/${source.name}")
            destination.parentFile.mkdirs()
            source.copyTo(destination, overwrite = true)
            println("QUALIFICATION_RESOLVED_${module.uppercase().replace('-', '_')}_SHA256=${hash(destination)}")
        }
    }
}
