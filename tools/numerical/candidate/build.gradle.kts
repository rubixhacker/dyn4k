subprojects {
    apply(plugin = "application")

    repositories {
        maven { url = uri(rootProject.file("../../../build/staging-repository")) }
        mavenCentral()
    }

    dependencies {
        add("implementation", "io.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1")
    }

    extensions.configure<org.gradle.api.plugins.JavaPluginExtension> {
        sourceSets.named("main") {
            java.setSrcDirs(listOf(projectDir))
        }
    }

    tasks.named<JavaExec>("run") {
        mainClass.set(when (project.name) {
            "default" -> "SleepWakeCases"
            "configured" -> "SleepWakeQuality"
            "physical" -> "WeldPulleyPhysicalCapture"
            else -> "CandidateCases"
        })
        dependsOn("verifyCandidateProvider")
    }

    tasks.register("verifyCandidateProvider") {
        doLast {
            val artifacts = configurations.getByName("runtimeClasspath").resolvedConfiguration.resolvedArtifacts
            check(artifacts.any { it.moduleVersion.id.group == "io.github.rubixhacker" && it.name == "dyn4k-core-jvm" })
            check(artifacts.none { it.moduleVersion.id.group == "org.dyn4j" && it.name == "dyn4j" })
        }
    }
}
