plugins {
    id("org.jetbrains.kotlin.multiplatform")
    id("de.infix.testBalloon")
}

kotlin {
    jvm()

    sourceSets {
        commonMain.dependencies {
            api(project(":core"))
        }

        commonTest.dependencies {
            implementation("de.infix.testBalloon:testBalloon-framework-core:1.2.0")
            implementation(kotlin("test"))
        }
    }
}

val jvmMain = kotlin.jvm().compilations.getByName("main")

tasks.register<JavaExec>("guardHostedRunners") {
    group = "verification"
    description = "Checks active workflows for forbidden hosted macOS runner labels."
    dependsOn(tasks.named("jvmJar"))
    classpath = files(jvmMain.output.allOutputs, jvmMain.runtimeDependencyFiles)
    mainClass.set("io.github.rubixhacker.harness.qualification.GuardHostedRunnersCliKt")
    args(rootDir.parentFile.parentFile.absolutePath)
}
