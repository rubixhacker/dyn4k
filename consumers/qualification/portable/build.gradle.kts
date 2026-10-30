@file:OptIn(org.jetbrains.kotlin.gradle.ExperimentalWasmDsl::class)

import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import java.security.MessageDigest

plugins {
    kotlin("multiplatform") version "2.4.20"
    id("com.android.kotlin.multiplatform.library") version "9.3.1"
    id("de.infix.testBalloon") version "1.2.0"
}

repositories {
    maven { url = uri(providers.gradleProperty("qualificationRepository").get()) }
    google()
    mavenCentral()
}

kotlin {
    jvmToolchain(21)
    jvm { compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) } }
    android {
        namespace = "io.github.rubixhacker.qualification"
        compileSdk = 36
        minSdk = 21
        withHostTest {}
    }
    js {
        nodejs()
        browser {
            if (providers.gradleProperty("qualificationSafari").orNull == "true") {
                testTask { useKarma { useSafari() } }
            }
        }
    }
    wasmJs { nodejs(); browser() }
    wasmWasi { nodejs() }
    linuxX64()
    linuxArm64()
    mingwX64()
    macosArm64()
    iosArm64()
    iosSimulatorArm64()
    iosX64()
    tvosArm64()
    tvosSimulatorArm64()
    watchosArm64()
    watchosDeviceArm64()
    watchosSimulatorArm64()
    androidNativeArm32()
    androidNativeArm64()
    androidNativeX86()
    androidNativeX64()

    sourceSets {
        commonMain.dependencies {
            api("io.github.rubixhacker:dyn4k:0.1.0-alpha.1")
        }
        commonTest.dependencies {
            implementation(kotlin("test"))
            implementation("de.infix.testBalloon:testBalloon-framework-core:1.2.0")
        }
        providers.gradleProperty("qualificationSuiteCheckout").orNull?.let { checkout ->
            val source = providers.gradleProperty("qualificationSuiteSource").get()
            require(source.startsWith("org/") && source.endsWith(".kt") && ".." !in source)
            commonTest {
                kotlin.setSrcDirs(listOf(file("$checkout/dyn4k-core/src/commonTest/kotlin")))
                kotlin.include(source)
            }
        }
    }
}

if (providers.gradleProperty("qualificationProduction").orNull == "true") {
    tasks.named<org.jetbrains.kotlin.gradle.targets.js.testing.KotlinJsTest>("jsBrowserTest") {
        dependsOn("jsTestTestProductionExecutableCompileSync")
        inputFileProperty.set(layout.buildDirectory.file(
            "compileSync/js/test/testProductionExecutable/kotlin/${rootProject.name}-test.js"
        ))
        doFirst { logger.lifecycle("qualification test input: ${inputFileProperty.get().asFile}") }
    }
}

if (providers.gradleProperty("qualificationSuiteCheckout").isPresent) {
    tasks.register("qualificationSuiteGraph") {
        doLast {
            val configuration = configurations.getByName("jvmTestRuntimeClasspath")
            val components = configuration.incoming.resolutionResult.allComponents
                .map { it.id.displayName }.sorted()
            val artifacts = configuration.resolvedConfiguration.resolvedArtifacts.map { artifact ->
                val bytes = artifact.file.readBytes()
                mapOf(
                    "component" to artifact.moduleVersion.id.toString(),
                    "file" to artifact.file.absolutePath,
                    "name" to artifact.file.name,
                    "size" to bytes.size,
                    "sha256" to MessageDigest.getInstance("SHA-256")
                        .digest(bytes).joinToString("") { "%02x".format(it) },
                )
            }.sortedWith(compareBy({ it["component"].toString() }, { it["name"].toString() }))
            println("DYN4K_FULL_SUITE_GRAPH=" + groovy.json.JsonOutput.toJson(mapOf(
                "configuration" to configuration.name,
                "gradle_user_home" to gradle.gradleUserHomeDir.absolutePath,
                "components" to components,
                "artifacts" to artifacts,
            )))
        }
    }
    tasks.named("jvmTest") { dependsOn("qualificationSuiteGraph") }
}
