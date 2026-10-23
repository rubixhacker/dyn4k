@file:OptIn(org.jetbrains.kotlin.gradle.ExperimentalWasmDsl::class)

import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import org.jetbrains.kotlin.gradle.targets.js.testing.KotlinJsTest
import org.gradle.api.tasks.testing.Test
import org.gradle.jvm.toolchain.JavaLanguageVersion
import java.io.File

plugins {
    kotlin("multiplatform") version "2.4.20"
    id("com.android.kotlin.multiplatform.library") version "9.3.1"
}

repositories {
    maven { url = uri(providers.gradleProperty("portableRepository").get()) }
    google()
    mavenCentral()
}

kotlin {
    jvmToolchain(21)
    jvm { compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) } }
    android {
        namespace = "io.github.rubixhacker.numerical.portable"
        compileSdk = 36
        minSdk = 21
        withHostTest {}
        withDeviceTest {}
    }
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
    js {
        nodejs()
        browser {
            testTask {
                useKarma {
                    if (System.getenv("DYN4K_BROWSER") == "firefox") useFirefoxHeadless()
                    else useChromeHeadless()
                }
            }
        }
    }
    wasmJs {
        nodejs()
        browser {
            testTask {
                useKarma {
                    if (System.getenv("DYN4K_BROWSER") == "firefox") useFirefoxHeadless()
                    else useChromeHeadless()
                }
            }
        }
    }
    wasmWasi { nodejs(); wasmtime() }

    sourceSets {
        commonMain.dependencies {
            api("io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1")
        }
        commonTest.dependencies { implementation(kotlin("test")) }
    }
}

tasks.withType<KotlinJsTest>().configureEach {
    if (name.endsWith("NodeTest")) useMocha { timeout = "90m" }
}

if (providers.gradleProperty("portableOptimized").orNull == "true") {
    tasks.named<KotlinJsTest>("jsBrowserTest") {
        dependsOn("jsTestTestProductionExecutableCompileSync")
        inputFileProperty.set(layout.buildDirectory.file(
            "compileSync/js/test/testProductionExecutable/kotlin/${rootProject.name}-test.js"
        ))
        doFirst { logger.lifecycle("portable numerical test input: ${inputFileProperty.get().asFile}") }
    }
    tasks.named<KotlinJsTest>("wasmJsBrowserTest") {
        dependsOn("compileTestProductionExecutableKotlinWasmJsOptimize")
        inputFileProperty.set(layout.buildDirectory.file(
            "compileSync/wasmJs/test/testProductionExecutable/optimized/${rootProject.name}-test.mjs"
        ))
        doFirst { logger.lifecycle("portable numerical test input: ${inputFileProperty.get().asFile}") }
    }
}

providers.gradleProperty("portableWorkerClassLoadLog").orNull?.let { logPattern ->
    require(logPattern.startsWith("/") && logPattern.endsWith("-%p.log") &&
        !logPattern.contains(':'))
    tasks.named<Test>("jvmTest") {
        jvmArgs("-Xlog:class+load=info:file=$logPattern:pid,level,tags:filecount=0")
    }
}

providers.gradleProperty("portableClassWitnessAgent").orNull?.let { agent ->
    val witness = providers.gradleProperty("portableClassWitnessOutput").get()
    val witnessFile = witness.removePrefix("boolean:")
    require(File(agent).isAbsolute && File(witnessFile).isAbsolute &&
        !agent.contains('=') && !witness.contains('='))
    tasks.named<Test>("jvmTest") {
        jvmArgs("-javaagent:$agent=$witness", "-XX:+DisableAttachMechanism", "-Xshare:off")
    }
}

providers.gradleProperty("portableBooleanJdiPort").orNull?.let { rawPort ->
    val port = rawPort.toIntOrNull()
    require(rawPort.matches(Regex("[1-9][0-9]{0,4}")) && port != null && port in 1..65535)
    require(providers.gradleProperty("portableBooleanJdiMethod").orNull ==
        "captureRevoluteLimitsFalse")
    tasks.named<Test>("jvmTest") {
        jvmArgs("-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,"
            + "address=127.0.0.1:$port")
    }
}

if (providers.gradleProperty("portableJvm8").orNull == "true") {
    tasks.named<Test>("jvmTest") {
        javaLauncher.set(javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(8))
        })
    }
}

providers.gradleProperty("portableNumericProbeMirror").orNull?.let { mirror ->
    require(File(mirror).isAbsolute)
    tasks.named<Test>("jvmTest") {
        systemProperty("portable.numericProbeMirror", mirror)
        maxParallelForks = 1
    }
}

providers.gradleProperty("portableBooleanMirror").orNull?.let { mirror ->
    require(File(mirror).isAbsolute)
    tasks.named<Test>("jvmTest") {
        systemProperty("portable.booleanMirror", mirror)
        maxParallelForks = 1
    }
}
