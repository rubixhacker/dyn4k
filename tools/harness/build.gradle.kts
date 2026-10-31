plugins {
    kotlin("multiplatform") version "2.4.20" apply false
    id("de.infix.testBalloon") version "1.2.0" apply false
    id("com.diffplug.spotless") version "8.10.4" apply false
    id("io.gitlab.arturbosch.detekt") version "1.23.8" apply false
}

/** Static analysis and formatting for every harness module. New findings fail the build. */
subprojects {
    apply(plugin = "com.diffplug.spotless")
    apply(plugin = "io.gitlab.arturbosch.detekt")

    configure<com.diffplug.gradle.spotless.SpotlessExtension> {
        kotlin {
            ktlint("1.5.0")
            trimTrailingWhitespace()
            endWithNewline()
        }
        kotlinGradle {
            ktlint("1.5.0")
            trimTrailingWhitespace()
            endWithNewline()
        }
    }

    configure<io.gitlab.arturbosch.detekt.extensions.DetektExtension> {
        config.setFrom(rootProject.files("config/detekt/detekt.yml"))
        // Analysis tasks read this file. The per-compilation baseline tasks
        // write `baseline-main.xml` / `baseline-test.xml`; union them here
        // after regenerating (see the status doc), because the analysis tasks
        // do not read the per-compilation files.
        baseline = file("config/detekt/baseline.xml")
        buildUponDefaultConfig = true
        allRules = false
    }

    // Detekt 1.23 bundles an older Kotlin compiler than the build JDK, so it
    // cannot parse the runner's JVM target. The project targets 21 throughout.
    // The aggregate `detekt` task is empty on KMP modules, so `check` runs the
    // per-target tasks instead. One shared baseline per module records existing
    // debt; new findings fail the build.
    val detektAnalysis = tasks.withType<io.gitlab.arturbosch.detekt.Detekt>().matching {
        it.name != "detekt" && !it.name.startsWith("detektBaseline") &&
            it.name != "detektGenerateConfig"
    }
    tasks.named("detekt") { dependsOn(detektAnalysis) }
    tasks.withType<io.gitlab.arturbosch.detekt.Detekt>().configureEach {
        jvmTarget = "21"
    }
    if (file("src/commonTest").isDirectory) {
        tasks.register<io.gitlab.arturbosch.detekt.Detekt>("detektCommonTest") {
            description = "Runs detekt on commonTest sources (no type resolution)."
            config.setFrom(rootProject.files("config/detekt/detekt.yml"))
            jvmTarget = "21"
        }
        // The detekt plugin resets task sources during its own configuration;
        // set ours after it so the file tree survives.
        afterEvaluate {
            tasks.named<io.gitlab.arturbosch.detekt.Detekt>("detektCommonTest") {
                setSource(files(fileTree("src/commonTest") { include("**/*.kt") }))
            }
        }
    }
}

/** Runs the JVM tests of every harness module. */
tasks.register("checkAll") {
    group = "verification"
    description = "Runs :jvmTest in every harness module."
    dependsOn(subprojects.map { "${it.path}:jvmTest" })
}

/**
 * Runs every static gate of every harness module: detekt and spotlessCheck.
 *
 * Detekt 1.23 bundles a Kotlin compiler that cannot parse a 25+ runtime version,
 * so run this on JDK 21 (`JAVA_HOME=<jdk21>`); revisit on a detekt upgrade.
 */
tasks.register("staticAll") {
    group = "verification"
    description = "Runs detekt and spotlessCheck in every harness module."
    dependsOn(subprojects.map { "${it.path}:detekt" })
    dependsOn(subprojects.map { "${it.path}:spotlessCheck" })
}
