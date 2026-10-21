plugins {
    kotlin("jvm") version "2.4.20"
}

repositories {
    mavenCentral()
}

val profile = providers.gradleProperty("pulleyProfile").get()
require(profile == "baseline" || profile == "candidate")
val providerJar = providers.gradleProperty("providerJar").map(::file)

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
        kotlin.srcDir("../src/jvmTest/kotlin")
        kotlin.include("portable/PulleyPreparationJdiV1Test.kt")
    }
}

tasks.register("writePulleyClasspath") {
    dependsOn(tasks.named("testClasses"))
    doLast {
        val output = providers.gradleProperty("pulleyClasspathFile").map(::file).get()
        require(output.parentFile.isDirectory)
        require(!output.exists())
        output.writeText(sourceSets.test.get().runtimeClasspath.asPath)
    }
}
