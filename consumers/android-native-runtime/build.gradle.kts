plugins {
    kotlin("multiplatform") version "2.4.20"
}

repositories {
    exclusiveContent {
        forRepository {
            maven { url = uri(providers.gradleProperty("stagingRepository").get()) }
        }
        filter { includeGroup("io.github.rubixhacker") }
    }
    mavenCentral()
}

kotlin {
    androidNativeX64 {
        binaries {
            executable { baseName = "journey" }
        }
    }
    sourceSets {
        commonMain.dependencies {
            implementation("io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1")
            implementation("io.github.rubixhacker:dyn4k:0.1.0-alpha.1")
        }
    }
}
