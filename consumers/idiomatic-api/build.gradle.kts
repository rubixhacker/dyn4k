plugins {
    kotlin("jvm") version "2.4.20"
    id("de.infix.testBalloon") version "1.2.0"
}

val stagingRepository = providers.gradleProperty("qualificationRepository")

repositories {
    maven { url = uri(stagingRepository.get()) }
    mavenCentral()
}

dependencies {
    testImplementation("io.github.rubixhacker:dyn4k:0.1.0-alpha.1")
    testImplementation(kotlin("test"))
    testImplementation("de.infix.testBalloon:testBalloon-framework-core:1.2.0")
}
