plugins {
    kotlin("jvm") version "2.4.20"
    application
}

repositories {
    maven { url = uri(projectDir.resolve("../../build/staging-repository")) }
    mavenCentral()
}

dependencies {
    implementation("io.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1")
}

sourceSets.main {
    kotlin.srcDir("../src/jvmConsumer/kotlin")
}

application {
    mainClass.set("PolygonAlgorithmStagedKotlinConsumerKt")
}
