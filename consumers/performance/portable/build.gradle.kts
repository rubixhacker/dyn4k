@file:OptIn(
    org.jetbrains.kotlin.gradle.ExperimentalWasmDsl::class,
)

import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    kotlin("multiplatform") version "2.4.20"
    id("com.android.kotlin.multiplatform.library") version "9.3.1"
}

repositories {
    maven { url = uri(providers.gradleProperty("performanceRepository").get()) }
    mavenCentral()
}

kotlin {
    jvmToolchain(21)
    jvm { compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) } }
    android {
        namespace = "io.github.rubixhacker.performance.portable"
        compileSdk = 36
        minSdk = 21
        withHostTest {}
    }
    js {
        nodejs()
        browser()
        binaries.executable()
    }
    wasmJs { nodejs(); browser(); binaries.executable() }
    wasmWasi { nodejs(); binaries.executable() }
    linuxX64 { binaries.executable { entryPoint = "performance.portable.main" } }
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
        commonMain.dependencies { implementation("io.github.rubixhacker:dyn4k:0.1.0-alpha.1") }
        commonTest.dependencies { implementation(kotlin("test")) }
    }
}
