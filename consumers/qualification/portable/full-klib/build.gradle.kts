import groovy.json.JsonOutput
import org.jetbrains.kotlin.gradle.tasks.KotlinCompilationTask
import java.security.MessageDigest

plugins {
    id("de.infix.testBalloon") version "1.2.0" apply false
    kotlin("multiplatform") version "2.4.20" apply false
}

val checkout = file(providers.gradleProperty("qualificationCheckout").get())
val staging = file(providers.gradleProperty("qualificationRepository").get())
val archive = file(providers.gradleProperty("qualificationArchiveRoot").get())
val lane = providers.gradleProperty("qualificationLaneId").get()
val target = lane.substringBefore(':')
val variant = when (target) {
    "linuxX64" -> "linuxx64"
    "js" -> "js"
    else -> error("Unsupported local KLIB target: $target")
}
val configuration = lane.substringAfterLast(':')
val version = "0.1.0-alpha.1"
val workRoot = file(providers.gradleProperty("qualificationWorkRoot").get())
val native = target == "linuxX64"
val mode = if (configuration == "production") "Production" else "Development"
val linkMode = if (configuration == "optimized-opt") "Release" else "Debug"
val runtimeTasks = if (native) listOf(":core:linuxX64Test", ":facade:linuxX64Test")
    else listOf(":core:compileTest${mode}ExecutableKotlinJs",
        ":facade:compileTest${mode}ExecutableKotlinJs")

subprojects {
    layout.buildDirectory.set(file("$workRoot/${project.name}"))
}

fun hash(file: File): String = MessageDigest.getInstance("SHA-256")
    .digest(file.readBytes()).joinToString("") { "%02x".format(it) }

fun staged(module: String): File = file(
    "$staging/io/github/rubixhacker/$module-$variant/$version/$module-$variant-$version.klib")

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
        val inventory = file(providers.gradleProperty("qualificationSourceInventory").get())
        val sources = inventory.readLines().filter { it.isNotBlank() }.associate { line ->
            val parts = line.split('\t')
            check(parts.size == 2)
            parts[0] to parts[1]
        }
        check(sources.isNotEmpty() && sources.size == inventory.readLines().size)
        val common = listOf("dyn4k-core", "dyn4k").flatMap { module ->
            file("$checkout/$module/src/commonTest/kotlin").walkTopDown()
                .filter { it.isFile && it.extension == "kt" }
                .map { it.relativeTo(checkout).invariantSeparatorsPath }.toList()
        }
        val platform = if (target == "linuxX64") "nativeTest" else "jsTest"
        val platformSources = file("$checkout/dyn4k-core/src/$platform/kotlin")
            .walkTopDown().filter { it.isFile && it.extension == "kt" }
            .map { it.relativeTo(checkout).invariantSeparatorsPath }.toList()
        val live = (common + platformSources).toSet()
        check(sources.keys == live)
        sources.forEach { (path, digest) -> check(hash(file("$checkout/$path")) == digest) }
        for (module in listOf("dyn4k-core", "dyn4k")) {
            val expected = providers.gradleProperty(
                if (module == "dyn4k-core") "qualificationCoreSha256" else "qualificationFacadeSha256"
            ).get()
            check(hash(staged(module)) == expected)
        }
        println("QUALIFICATION_INPUT_SOURCE_COUNT=${sources.size}")
    }
}

tasks.register("qualificationGraphs") {
    dependsOn("qualificationValidateInputs")
    doLast {
        val compile = if (target == "linuxX64") "linuxX64TestCompileKlibraries"
            else "jsTestCompileClasspath"
        val runtime = if (target == "linuxX64") "linuxX64TestCompileKlibraries"
            else "jsTestRuntimeClasspath"
        val graphs = mapOf("compile" to listOf("core", "facade").map { graph(it, compile) },
            "runtime" to listOf("core", "facade").map { graph(it, runtime) },
            "gradle_user_home" to gradle.gradleUserHomeDir.absolutePath)
        val path = file("$archive/provider-graph.json")
        path.parentFile.mkdirs()
        path.writeText(JsonOutput.toJson(graphs))
        println("QUALIFICATION_LANE=$lane")
        println("QUALIFICATION_PROVIDER_GRAPH_SHA256=${hash(path)}")
        for (module in listOf("dyn4k-core", "dyn4k")) {
            val copy = file("$archive/resolved/$module-$variant-$version.klib")
            copy.parentFile.mkdirs()
            staged(module).copyTo(copy, overwrite = true)
            println("QUALIFICATION_RESOLVED_${module.uppercase().replace('-', '_')}_SHA256=${hash(copy)}")
        }
    }
}

tasks.register("qualificationCompilerEvidence") {
    dependsOn(runtimeTasks)
    doLast {
        val evidence = listOf("core", "facade").map { module ->
            val owner = project(":$module")
            val compileName = if (native) "compileTestKotlinLinuxX64" else "compileTestKotlinJs"
            val compile = owner.tasks.getByName(compileName) as KotlinCompilationTask<*>
            val executableName = if (native) "link${linkMode}TestLinuxX64"
                else "compileTest${mode}ExecutableKotlinJs"
            val executable = owner.tasks.getByName(executableName)
            mapOf("module" to module, "compile_task" to compile.path,
                "compile_args" to compile.compilerOptions.freeCompilerArgs.get(),
                "executable_task" to executable.path,
                "executable_args" to (if (native) emptyList<String>() else
                    (executable as KotlinCompilationTask<*>).compilerOptions.freeCompilerArgs.get()))
        }
        val path = file("$archive/compiler-evidence.json")
        path.parentFile.mkdirs()
        path.writeText(JsonOutput.toJson(evidence))
        println("QUALIFICATION_COMPILER_EVIDENCE_SHA256=${hash(path)}")
    }
}

tasks.register("qualificationEvidence") {
    dependsOn("qualificationGraphs", "qualificationCompilerEvidence")
    doLast {
        val command = listOf("python3", "$checkout/tools/qualification/full_klib_consumer.py",
            "capture", "--repository", checkout.absolutePath, "--project", rootDir.absolutePath,
            "--archive", archive.absolutePath, "--work-root", workRoot.absolutePath,
            "--lane", lane, "--node", providers.gradleProperty("qualificationNode").get(),
            "--source-inventory", providers.gradleProperty("qualificationSourceInventory").get(),
            "--core-cases", providers.gradleProperty("qualificationCoreCases").get(),
            "--facade-cases", providers.gradleProperty("qualificationFacadeCases").get(),
            "--lane-script", providers.gradleProperty("qualificationLaneScript").get())
        val process = ProcessBuilder(command).directory(rootDir).redirectErrorStream(true).start()
        val output = process.inputStream.bufferedReader().readText()
        if (output.isNotBlank()) logger.lifecycle(output.trimEnd())
        val result = process.waitFor()
        check(result == 0) { "KLIB raw result capture failed: $result" }
    }
}
