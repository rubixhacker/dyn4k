plugins {
    id("org.jetbrains.kotlin.multiplatform")
    id("de.infix.testBalloon")
}

// The performance tools measure against one pinned dyn4j binary. The host adapter tests need
// that exact jar on disk, so resolve it once and hand its path to the test JVM. It is not on
// any module's compile or runtime classpath.
val pinnedBaseline: Configuration by configurations.creating

dependencies {
    pinnedBaseline("org.dyn4j:dyn4j:6.0.0")
}

kotlin {
    jvm {
        testRuns["test"].executionTask.configure {
            doFirst {
                systemProperty("performance.baselineJar", pinnedBaseline.singleFile.absolutePath)
            }
        }
    }

    sourceSets {
        commonMain.dependencies {
            api(project(":core"))
            implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.12.0")
        }

        commonTest.dependencies {
            implementation("de.infix.testBalloon:testBalloon-framework-core:1.2.0")
            implementation(kotlin("test"))
        }
    }
}
