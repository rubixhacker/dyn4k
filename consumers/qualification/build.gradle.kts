plugins {
    kotlin("jvm") version "2.4.20"
    application
}

val stagingRepository = providers.gradleProperty("qualificationRepository")
    .orElse("../../build/staging-repository")

repositories {
    maven { url = uri(stagingRepository.get()) }
    mavenCentral()
}

dependencies {
    implementation("io.github.rubixhacker:dyn4k:0.1.0-alpha.1")
    if (providers.gradleProperty("withUpstream").orNull == "true") {
        implementation("org.dyn4j:dyn4j:6.0.0")
    }
}

application { mainClass = "qualification.ConsumerKt" }

val verifySingleProvider by tasks.registering {
    doLast {
        val providers = configurations.runtimeClasspath.get().incoming.resolutionResult.allComponents
            .mapNotNull { it.moduleVersion }
        val core = providers.any {
            it.group == "io.github.rubixhacker" && it.name.startsWith("dyn4k-core")
        }
        val upstream = providers.any { it.group == "org.dyn4j" && it.name == "dyn4j" }
        check(core) { "staged dyn4k-core provider did not resolve" }
        check(!upstream) {
            "duplicate org.dyn4j provider: exclude org.dyn4j:dyn4j from the consumer dependency graph"
        }
    }
}

tasks.named("run") { dependsOn(verifySingleProvider) }
