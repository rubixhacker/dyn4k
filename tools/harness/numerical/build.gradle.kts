plugins {
    id("org.jetbrains.kotlin.multiplatform")
    id("de.infix.testBalloon")
}

kotlin {
    jvm()

    sourceSets {
        commonMain.dependencies {
            api(project(":core"))
            // The traces the numerical contract validates are JSON Lines documents. `:core`
            // declares this library as `implementation`, which does not reach consumers.
            implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.12.0")
        }

        commonTest.dependencies {
            implementation("de.infix.testBalloon:testBalloon-framework-core:1.2.0")
            implementation(kotlin("test"))
        }

        jvmMain.dependencies {
            implementation(project(":host"))
        }
    }
}
