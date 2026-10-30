plugins {
    id("org.jetbrains.kotlin.multiplatform")
    id("de.infix.testBalloon")
}

kotlin {
    jvm()

    sourceSets {
        commonMain.dependencies {
            api(project(":core"))
            // The migration tools read and write JSON streams and receipts with `json.loads` and
            // `json.dumps`, so the JSON model is part of the contract this module ports.
            implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.12.0")
        }

        jvmMain.dependencies {
            implementation(project(":host"))
        }

        jvmTest.dependencies {
            implementation("de.infix.testBalloon:testBalloon-framework-core:1.2.0")
            implementation(kotlin("test"))
        }
    }
}
