import org.jetbrains.kotlin.gradle.dsl.JvmTarget
plugins {
    kotlin("multiplatform") version "2.4.20"
    `maven-publish`
}
group = "local.dyn4k.probe"
version = "0.0.1"
kotlin {
    jvmToolchain(21)
    jvm {
        compilerOptions {
            jvmTarget.set(JvmTarget.JVM_1_8)
            freeCompilerArgs.add("-Xjdk-release=8")
            if (providers.gradleProperty("probeNoOptimize").orNull == "true") freeCompilerArgs.add("-Xno-optimize")
        }
        attributes.attribute(org.gradle.api.attributes.java.TargetJvmVersion.TARGET_JVM_VERSION_ATTRIBUTE, 8)
    }
}
publishing { repositories { maven { url = uri(layout.buildDirectory.dir("repo")) } } }
