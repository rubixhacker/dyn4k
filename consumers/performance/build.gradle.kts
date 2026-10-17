plugins {
    kotlin("jvm") version "2.4.20"
}

val stagingRepository = providers.gradleProperty("performanceRepository")
    .orElse("../../build/staging-repository")

repositories {
    exclusiveContent {
        forRepository { maven { url = uri(stagingRepository.get()) } }
        filter { includeGroup("io.github.rubixhacker") }
    }
    mavenCentral()
}

val compatibility by sourceSets.creating {
    java.srcDir("../../tools/performance")
    java.srcDir("src/main/java")
    java.include("BaselinePilot.java", "performance/ProviderIdentity.java")
}

dependencies {
    implementation("io.github.rubixhacker:dyn4k:0.1.0-alpha.1")
    add(compatibility.implementationConfigurationName, "io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1")
}

kotlin.jvmToolchain(21)

tasks.named<JavaCompile>(compatibility.compileJavaTaskName) {
    options.release.set(21)
}

val writeCandidateClasspath by tasks.registering {
    dependsOn(tasks.named("classes"), tasks.named(compatibility.classesTaskName))
    doLast {
        val direct = configurations.runtimeClasspath.get().incoming.resolutionResult.allComponents
            .mapNotNull { it.moduleVersion }
        val shim = configurations[compatibility.runtimeClasspathConfigurationName]
            .incoming.resolutionResult.allComponents.mapNotNull { it.moduleVersion }
        check(direct.any { it.group == "io.github.rubixhacker" && it.name == "dyn4k" })
        check(direct.any { it.group == "io.github.rubixhacker" && it.name == "dyn4k-core" })
        check(shim.any { it.group == "io.github.rubixhacker" && it.name == "dyn4k-core" })
        check(shim.none { it.group == "io.github.rubixhacker" && it.name == "dyn4k" })
        check((direct + shim).none { it.group == "org.dyn4j" && it.name == "dyn4j" })
        val paths = listOf(
            "direct_kotlin\t${sourceSets.main.get().runtimeClasspath.asPath}",
            "compatibility\t${compatibility.runtimeClasspath.asPath}",
        )
        val output = layout.buildDirectory.file("candidate-paths.tsv").get().asFile
        output.parentFile.mkdirs()
        output.writeText(paths.joinToString("\n", postfix = "\n"))
    }
}
