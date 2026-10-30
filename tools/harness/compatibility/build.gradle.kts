plugins {
    id("org.jetbrains.kotlin.multiplatform")
    id("de.infix.testBalloon")
}

kotlin {
    jvm()

    sourceSets {
        commonMain.dependencies {
            api(project(":core"))
        }

        commonTest.dependencies {
            implementation("de.infix.testBalloon:testBalloon-framework-core:1.2.0")
            implementation(kotlin("test"))
        }
    }
}
