plugins {
    kotlin("jvm") version "2.4.20" apply false
    id("com.android.application") version "9.3.1" apply false
    id("de.infix.testBalloon") version "1.2.0" apply false
}

layout.buildDirectory.set(file(providers.gradleProperty("qualificationOutput").get()).resolve("root"))

subprojects {
    layout.buildDirectory.set(file(providers.gradleProperty("qualificationOutput").get()).resolve(name))
}
