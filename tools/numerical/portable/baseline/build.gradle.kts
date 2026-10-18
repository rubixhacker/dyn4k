plugins {
    kotlin("jvm") version "2.4.20"
}

repositories {
    mavenCentral()
}

val baselineJar = providers.gradleProperty("baselineJar").map(::file)

dependencies {
    implementation(files(baselineJar))
    testImplementation(kotlin("test-junit"))
}

kotlin {
    jvmToolchain(21)
}

sourceSets {
    main {
        kotlin.srcDir("../src/commonMain/kotlin")
        kotlin.srcDir("src/main/kotlin")
    }
    test {
        kotlin.srcDir("../src/commonTest/kotlin")
        kotlin.include("portable/PortableMatrixTest.kt")
    }
}
