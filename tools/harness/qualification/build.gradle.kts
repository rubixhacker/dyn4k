plugins {
    id("org.jetbrains.kotlin.multiplatform")
    id("de.infix.testBalloon")
}

kotlin {
    jvm()

    sourceSets {
        commonMain.dependencies {
            api(project(":core"))
            implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.12.0")
        }

        jvmMain.dependencies {
            implementation(project(":host"))
            implementation(project(":numerical"))
            // `full_hosted` writes and reads PAX transport archives with nanosecond timestamps.
            implementation("org.apache.commons:commons-compress:1.28.0")
        }

        commonTest.dependencies {
            implementation("de.infix.testBalloon:testBalloon-framework-core:1.2.0")
            implementation(kotlin("test"))
        }
    }
}

val jvmMain = kotlin.jvm().compilations.getByName("main")

/** Argument and working-directory plumbing shared by the ported command line entry points. */
fun JavaExec.entryPoint(main: String, description: String) {
    group = "verification"
    this.description = description
    dependsOn(tasks.named("jvmJar"))
    classpath = files(jvmMain.output.allOutputs, jvmMain.runtimeDependencyFiles)
    mainClass.set(main)
    workingDir = rootDir.parentFile.parentFile
}

tasks.register<JavaExec>("guardHostedRunners") {
    group = "verification"
    description = "Checks active workflows for forbidden hosted macOS runner labels."
    dependsOn(tasks.named("jvmJar"))
    classpath = files(jvmMain.output.allOutputs, jvmMain.runtimeDependencyFiles)
    mainClass.set("io.github.rubixhacker.harness.qualification.GuardHostedRunnersCliKt")
    args(rootDir.parentFile.parentFile.absolutePath)
}

tasks.register<JavaExec>("stagePublication") {
    entryPoint(
        "io.github.rubixhacker.harness.qualification.StageCli",
        "Runs the staging publication tasks and writes the receipt; pass --candidate-sha, --target, --output, --console.",
    )
}

tasks.register<JavaExec>("packagePublication") {
    entryPoint(
        "io.github.rubixhacker.harness.qualification.PublicationCli",
        "Packages an audited staging tree into a publication bundle, or verifies one; pass package|verify with its options.",
    )
}

tasks.register<JavaExec>("executePlan") {
    entryPoint(
        "io.github.rubixhacker.harness.qualification.ExecutionCli",
        "Runs a lane execution plan and records the evidence; pass --candidate-sha, --plan, --output.",
    )
}

tasks.register<JavaExec>("hostedProbe") {
    entryPoint(
        "io.github.rubixhacker.harness.qualification.HostedCli",
        "Probes one hosted target and writes its evidence; pass run --candidate-sha, --target, --output.",
    )
}

tasks.register<JavaExec>("qualify") {
    entryPoint(
        "io.github.rubixhacker.harness.qualification.QualificationCli",
        "Runs one qualification action; pass matrix, check-providers, probe, audit-staging, execute, or record with its options.",
    )
}

tasks.register<JavaExec>("collectQualification") {
    entryPoint(
        "io.github.rubixhacker.harness.qualification.CollectionCli",
        "Collects, verifies, or ingests the 112-lane producer artifacts; pass --repository, --candidate-sha, --artifacts-dir, and --output with --verify or --audit-input-dir.",
    )
}

tasks.register<JavaExec>("stageArtifact") {
    entryPoint(
        "io.github.rubixhacker.harness.qualification.ArtifactCli",
        "Packages or verifies bounded XML evidence bundles; pass hosted, ubuntu, or verify with its options.",
    )
}

tasks.register<JavaExec>("fullHosted") {
    entryPoint(
        "io.github.rubixhacker.harness.qualification.FullHostedCli",
        "Packages or verifies a hosted full-common-corpus archive; pass --package, --verify-tar, or --verify with its options.",
    )
}
