import org.jetbrains.kotlin.gradle.tasks.KotlinCompilationTask
import groovy.json.JsonOutput

plugins { kotlin("multiplatform") }

val checkout = file(providers.gradleProperty("qualificationCheckout").get())
val staging = file(providers.gradleProperty("qualificationRepository").get())
val target = providers.gradleProperty("qualificationLaneId").get().substringBefore(':')
val variant = target.lowercase()
val version = "0.1.0-alpha.1"
repositories { maven { url = uri(staging) }; mavenCentral() }

kotlin {
    when (target) {
        "linuxArm64" -> linuxArm64()
        "mingwX64" -> mingwX64()
        "macosArm64" -> macosArm64()
        "iosSimulatorArm64" -> iosSimulatorArm64()
        "iosX64" -> iosX64()
        "tvosSimulatorArm64" -> tvosSimulatorArm64()
        "watchosSimulatorArm64" -> watchosSimulatorArm64()
        else -> error("Unsupported native host target: $target")
    }
    sourceSets {
        val commonTest by getting {
            dependencies {
                implementation(kotlin("test"))
                implementation("io.github.rubixhacker:dyn4k-core:$version")
                implementation("io.github.rubixhacker:dyn4k:$version")
            }
            kotlin.setSrcDirs(listOf(file("$checkout/dyn4k/src/commonTest/kotlin")))
        }
    }
}

tasks.named<KotlinCompilationTask<*>>("compileTestKotlin${target.replaceFirstChar { it.uppercase() }}") {
    dependsOn(":qualificationValidateInputs")
    compilerOptions.freeCompilerArgs.addAll(providers.provider {
        val resolved = configurations.getByName("${target}TestCompileKlibraries")
            .resolvedConfiguration.resolvedArtifacts.single {
                it.moduleVersion.id.name == "dyn4k-$variant"
            }.file
        val mode = providers.gradleProperty("qualificationMode").get()
        listOf(if (mode == "debug-g") "-g" else "-opt", "-friend-modules", resolved.absolutePath)
    })
    doFirst {
        println("QUALIFICATION_COMPILER_FLAGS_FACADE=${JsonOutput.toJson(compilerOptions.freeCompilerArgs.get())}")
    }
}
