plugins {
    id("org.jetbrains.kotlin.multiplatform")
    id("de.infix.testBalloon")
}

kotlin {
    jvm()

    sourceSets {
        commonMain.dependencies {
            api("com.squareup.okio:okio:3.18.2")
            implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.12.0")
        }

        commonTest.dependencies {
            implementation("de.infix.testBalloon:testBalloon-framework-core:1.2.0")
            implementation(kotlin("test"))
        }
    }
}
