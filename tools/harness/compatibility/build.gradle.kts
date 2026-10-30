plugins {
    id("org.jetbrains.kotlin.multiplatform")
    id("de.infix.testBalloon")
}

kotlin {
    jvm()

    sourceSets {
        commonMain.dependencies {
            api(project(":core"))
            // `world_ci.validate_runs` reads recorded process logs with `json.loads`, so the JSON
            // reader is part of the contract this module ports. `:core` declares the same library
            // as an `implementation` dependency, which does not reach consumers of `:core`.
            implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.12.0")
            // `BaselineOracle` reads `javap` output with the `:baseline` port of
            // `verify.surface` / `member_inventory` instead of keeping a second copy.
            implementation(project(":baseline"))
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
