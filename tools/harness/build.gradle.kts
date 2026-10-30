plugins {
    kotlin("multiplatform") version "2.4.20" apply false
    id("de.infix.testBalloon") version "1.2.0" apply false
}

/** Runs the JVM tests of every harness module. */
tasks.register("checkAll") {
    group = "verification"
    description = "Runs :jvmTest in every harness module."
    dependsOn(subprojects.map { "${it.path}:jvmTest" })
}
