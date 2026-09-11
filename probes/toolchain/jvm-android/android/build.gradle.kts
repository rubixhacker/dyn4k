import org.jetbrains.kotlin.gradle.dsl.JvmTarget
plugins {
    kotlin("multiplatform") version "2.4.20"
    id("com.android.kotlin.multiplatform.library") version "9.3.1"
    `maven-publish`
}
group = "local.dyn4k.probe"
version = "0.0.1"
kotlin {
    jvmToolchain(21)
    android {
        namespace = "local.dyn4k.probe"
        compileSdk = 36
        minSdk = providers.gradleProperty("probeMinSdk").orElse("21").get().toInt()
        compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) }
    }
    sourceSets { commonMain { kotlin.srcDir("../src/commonMain/kotlin") } }
}
publishing { repositories { maven { url = uri(layout.buildDirectory.dir("repo")) } } }
