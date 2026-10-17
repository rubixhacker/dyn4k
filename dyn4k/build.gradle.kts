@file:OptIn(org.jetbrains.kotlin.gradle.ExperimentalWasmDsl::class)

import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    kotlin("multiplatform")
    id("com.android.kotlin.multiplatform.library")
    `maven-publish`
}

kotlin {
    jvmToolchain(21)
    jvm { compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) } }
    android {
        namespace = "io.github.rubixhacker.dyn4k"
        compileSdk = 36
        minSdk = 21
        withHostTest {}
        compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) }
    }
    js { nodejs() }
    wasmJs { nodejs() }
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
        commonMain.dependencies { api(project(":dyn4k-core")) }
        commonTest.dependencies { implementation(kotlin("test")) }
    }
}

publishing {
    publications.withType<MavenPublication>().configureEach {
        artifact(rootProject.file("LICENSE.md")) {
            classifier = "license"
            extension = "md"
        }
        pom {
            name = "dyn4k"
            description = "Kotlin conveniences for the dyn4k core"
            url = "https://github.com/rubixhacker/dyn4k"
            licenses {
                license {
                    name = "BSD 3-Clause License"
                    url = "https://opensource.org/licenses/BSD-3-Clause"
                }
            }
            scm { url = "https://github.com/rubixhacker/dyn4k" }
            developers { developer { id = "rubixhacker"; name = "Stewart Boling" } }
        }
    }
    repositories { maven { name = "staging"; url = uri(rootProject.layout.buildDirectory.dir("staging-repository")) } }
}

tasks.withType<Jar>().configureEach {
    from(rootProject.file("LICENSE.md")) { into("META-INF") }
}
