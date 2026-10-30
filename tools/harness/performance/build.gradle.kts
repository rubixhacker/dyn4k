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

val jvmMain = kotlin.jvm().compilations.getByName("main")

// Argument and working-directory plumbing shared by the ported command line entry points.
// The working directory is the repository root, because the tools read
// `docs/research/performance-manifest-v1.json` and `tools/performance/*.java` relative to it.
fun JavaExec.entryPoint(main: String, description: String) {
    group = "verification"
    this.description = description
    dependsOn(tasks.named("jvmJar"))
    classpath = files(jvmMain.output.allOutputs, jvmMain.runtimeDependencyFiles)
    mainClass.set(main)
    workingDir = rootDir.parentFile.parentFile
}

tasks.register<JavaExec>("warmupProbe") {
    entryPoint(
        "io.github.rubixhacker.harness.performance.WarmupProbeCli",
        "Runs one workload with a long warm-up and reports the 30-second window medians; " +
            "pass --output DIR --family F --variant V --size small|medium --hz 30|60|120 " +
            "[--warmup-seconds N] [--jar JAR] [--java JAVA] [--javac JAVAC].",
    )
}

tasks.register<JavaExec>("calibrate") {
    entryPoint(
        "io.github.rubixhacker.harness.performance.CalibrateCli",
        "Runs six unchanged-baseline trials, pairs them, and reports the noise bound; " +
            "pass --output DIR --family F --variant V --size small|medium --hz 30|60|120 " +
            "[--warmup-seconds N] [--measurement-seconds N] [--jar JAR].",
    )
}

tasks.register<JavaExec>("ccdRouteTrace") {
    entryPoint(
        "io.github.rubixhacker.harness.performance.CcdRouteTraceCli",
        "Traces the CCD fixture identity and the three staged routes; " +
            "pass --output DIR --java JAVA --javac JAVAC --jar PINNED_DYN4J_JAR.",
    )
}
