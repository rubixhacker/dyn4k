import java.io.File

plugins {
    kotlin("jvm") version "2.4.20"
}

repositories {
    mavenCentral()
}

val profile = providers.gradleProperty("pulleyProfile").get()
require(profile == "baseline" || profile == "candidate")
val providerJar = providers.gradleProperty("providerJar").map(::file)
layout.buildDirectory.set(layout.dir(providers.gradleProperty("pulleyBuildDirectory").map(::file)))

dependencies {
    implementation(files(providerJar))
    testImplementation(kotlin("test-junit"))
}

kotlin {
    jvmToolchain(21)
}

sourceSets {
    main {
        kotlin.srcDir("../src/commonMain/kotlin")
        if (profile == "baseline") kotlin.srcDir("../baseline/src/main/kotlin")
    }
    test {
        kotlin.srcDir("src/test/kotlin")
        kotlin.include("portable/PulleyPreparationJdiV1Test.kt")
    }
}

val pulleyFixtureJar = tasks.register<Jar>("pulleyFixtureJar") {
    dependsOn(tasks.named("testClasses"))
    archiveFileName.set("pulley-fixture.jar")
    destinationDirectory.set(layout.buildDirectory.dir("pulley-jdi"))
    from(sourceSets.main.get().output)
    from(sourceSets.test.get().output)
}

tasks.register("writePulleyClasspath") {
    dependsOn(pulleyFixtureJar)
    doLast {
        val output = providers.gradleProperty("pulleyClasspathFile").map(::file).get()
        require(output.parentFile.isDirectory)
        require(!output.exists())
        val fixture = pulleyFixtureJar.get().archiveFile.get().asFile.canonicalFile
        val provider = providerJar.get().canonicalFile
        val dependencies = sourceSets.test.get().runtimeClasspath.files
            .map { it.canonicalFile }
            .filter { it.isFile && it.extension == "jar" && it != provider && it != fixture }
        output.writeText((listOf(fixture, provider) + dependencies).joinToString(
            File.pathSeparator) { it.absolutePath } + "\n")
    }
}
