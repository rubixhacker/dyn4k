@file:OptIn(org.jetbrains.kotlin.gradle.ExperimentalWasmDsl::class)

import org.jetbrains.kotlin.gradle.tasks.KotlinCompilationTask
import java.security.MessageDigest

plugins { kotlin("multiplatform"); id("de.infix.testBalloon") }

val checkout = file(providers.gradleProperty("qualificationCheckout").get())
val staging = file(providers.gradleProperty("qualificationRepository").get())
val target = providers.gradleProperty("qualificationLaneId").get().substringBefore(':')
val variant = if (target == "wasmJs") "wasm-js" else "wasm-wasi"
val version = "0.1.0-alpha.1"

repositories {
    maven { url = uri(staging); content { includeGroup("io.github.rubixhacker") } }
    mavenCentral { content { excludeGroup("io.github.rubixhacker") } }
}

kotlin {
    wasmJs { nodejs(); binaries.executable() }
    wasmWasi { nodejs(); wasmtime(); binaries.executable() }
    sourceSets {
        val commonTest by getting {
            dependencies {
                implementation(kotlin("test"))
                implementation("de.infix.testBalloon:testBalloon-framework-core:1.2.0")
                implementation("io.github.rubixhacker:dyn4k-core:$version")
                implementation("io.github.rubixhacker:dyn4k:$version")
            }
            kotlin.setSrcDirs(listOf(file("$checkout/dyn4k/src/commonTest/kotlin")))
        }
    }
}

fun friend(): File {
    val artifact = configurations.getByName("${target}TestCompileClasspath")
        .resolvedConfiguration.resolvedArtifacts.single {
            it.moduleVersion.id.name == "dyn4k-$variant"
        }.file
    val staged = file("$staging/io/github/rubixhacker/dyn4k-$variant/$version/dyn4k-$variant-$version.klib")
    fun hash(file: File) = MessageDigest.getInstance("SHA-256").digest(file.readBytes()).toList()
    check(hash(artifact) == hash(staged))
    return artifact
}

for (platform in listOf("WasmJs", "WasmWasi")) {
    tasks.named<KotlinCompilationTask<*>>("compileTestKotlin$platform") {
        dependsOn(":qualificationInputs")
        if (platform == target.replaceFirstChar { it.uppercase() }) {
            compilerOptions.freeCompilerArgs.addAll(providers.provider {
                listOf("-Xfriend-modules=${friend().absolutePath}")
            })
        }
    }
    for (mode in listOf("Development", "Production")) {
        tasks.named<KotlinCompilationTask<*>>("compileTest${mode}ExecutableKotlin$platform") {
            if (platform == target.replaceFirstChar { it.uppercase() }) {
                compilerOptions.freeCompilerArgs.addAll(providers.provider {
                    listOf("-Xfriend-modules=${friend().absolutePath}")
                })
            }
        }
    }
}
