@file:OptIn(org.jetbrains.kotlin.gradle.ExperimentalWasmDsl::class)

import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    kotlin("multiplatform") version "2.4.20"
    id("com.android.kotlin.multiplatform.library") version "9.3.1"
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
        namespace = "io.github.rubixhacker.geometryextension"
        compileSdk = 36
        minSdk = 21
        withHostTest {}
    }
    linuxX64()
    js { nodejs() }
    wasmJs { nodejs() }
    wasmWasi { nodejs() }

    sourceSets {
        commonMain.dependencies { api("io.github.rubixhacker:dyn4k:0.1.0-alpha.1") }
        commonTest.dependencies { implementation(kotlin("test")) }
    }
}
