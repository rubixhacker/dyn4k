plugins {
    kotlin("jvm") version "2.4.20"
}

val stagingRepository = providers.gradleProperty("qualificationRepository")

repositories {
    maven { url = uri(stagingRepository.get()) }
    mavenCentral()
}

dependencies {
    testImplementation("io.github.rubixhacker:dyn4k:0.1.0-alpha.1")
    testImplementation(kotlin("test-junit5"))
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test { useJUnitPlatform() }
