plugins { base }

val stagingRepository = providers.gradleProperty("migrationRepository")
    .orElse("../../build/staging-repository")

repositories {
    maven { url = uri(stagingRepository.get()) }
    mavenCentral()
}

val baseline by configurations.creating
val candidate by configurations.creating
val instrumentation by configurations.creating

dependencies {
    baseline("org.dyn4j:dyn4j:6.0.0")
    candidate("io.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1")
    instrumentation("org.javassist:javassist:3.30.2-GA")
    listOf(baseline, candidate).forEach { configuration ->
        add(configuration.name, "org.jogamp.jogl:jogl-all:2.3.2")
        add(configuration.name, "org.jogamp.gluegen:gluegen-rt:2.3.2")
    }
}

tasks.register<Copy>("resolveBaseline") {
    from(baseline)
    into(layout.buildDirectory.dir("resolved/baseline"))
}

tasks.register<Copy>("resolveCandidate") {
    from(candidate)
    into(layout.buildDirectory.dir("resolved/candidate"))
}

tasks.register<Copy>("resolveInstrumentation") {
    from(instrumentation)
    into(layout.buildDirectory.dir("resolved/instrumentation"))
}
