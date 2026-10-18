import org.gradle.api.artifacts.component.ModuleComponentIdentifier
import org.gradle.api.artifacts.result.ResolvedDependencyResult

plugins {
    id("com.android.application")
}

android {
    namespace = "io.github.rubixhacker.dyn4k.full"
    compileSdk = 36

    defaultConfig {
        applicationId = "io.github.rubixhacker.dyn4k.full"
        minSdk = 21
        targetSdk = 36
        testInstrumentationRunner = "io.github.rubixhacker.dyn4k.full.FullJourneyTest"
    }

    buildTypes {
        getByName("debug") { isMinifyEnabled = false }
        getByName("release") {
            isMinifyEnabled = true
            signingConfig = signingConfigs.getByName("debug")
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"),
                          layout.buildDirectory.file("generated/full-keep.pro").get().asFile)
        }
    }
    testBuildType = providers.gradleProperty("runtimeTestBuildType").getOrElse("debug")
    testOptions { animationsDisabled = true }
    sourceSets.getByName("main").assets.srcDir(layout.buildDirectory.dir("generated/assets").get().asFile)
}

dependencies {
    implementation("io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1")
    implementation("io.github.rubixhacker:dyn4k-core-android:0.1.0-alpha.1")
    implementation("org.jetbrains.kotlin:kotlin-stdlib:2.4.20")
    implementation("org.jetbrains.kotlin:kotlin-test-junit:2.4.20")
    implementation("junit:junit:4.13.2")
    implementation("com.google.errorprone:error_prone_annotations:2.50.0")
    implementation(files(providers.gradleProperty("portableSuiteJar").get()))
    implementation(files(layout.buildDirectory.file("generated/full-consumers.jar")))
}

val repositoryRoot = rootProject.projectDir.resolve("../..").canonicalFile
val verifyInputs = tasks.register<Exec>("verifyFullInputs") {
    workingDir(repositoryRoot)
    commandLine("python3", repositoryRoot.resolve("tools/android-runtime/prepare.py"),
                "--verify-consumers", providers.gradleProperty("preparedManifest").get())
}

tasks.configureEach {
    if (name.startsWith("compile") || name.startsWith("merge") && name.contains("Assets") ||
        name.startsWith("minify")) {
        dependsOn(verifyInputs)
    }
}

tasks.register("providerArtifacts") {
    doLast {
        println("DYN4K_BUILD_JDK javaHome=${System.getProperty("java.home")} " +
                "javaVersion=${JavaVersion.current().majorVersion} gradleVersion=${gradle.gradleVersion}")
        for (variant in listOf("debug", "release")) {
            val configuration = configurations.getByName("${variant}RuntimeClasspath")
            val resolution = configuration.incoming.resolutionResult
            fun coordinate(id: org.gradle.api.artifacts.component.ComponentIdentifier): String =
                when (id) {
                    is ModuleComponentIdentifier -> "${id.group}:${id.module}:${id.version}"
                    else -> "project:full"
                }
            val components = resolution.allComponents.map { coordinate(it.id) }.toSortedSet()
            val edges = resolution.allComponents.flatMap { component ->
                component.dependencies.map { dependency ->
                    val resolved = dependency as? ResolvedDependencyResult
                        ?: error("unresolved ${variant} runtime dependency: $dependency")
                    "${coordinate(component.id)} ${coordinate(resolved.selected.id)}"
                }
            }.toSortedSet()
            val artifacts = configuration.resolvedConfiguration.resolvedArtifacts
                .map { "${it.moduleVersion.id} ${it.file.canonicalPath}" }.toSortedSet()
            println("DYN4K_GRAPH_BEGIN $variant")
            components.forEach { println("DYN4K_GRAPH_COMPONENT $variant $it") }
            edges.forEach { println("DYN4K_GRAPH_EDGE $variant $it") }
            artifacts.forEach { println("DYN4K_GRAPH_ARTIFACT $variant $it") }
            println("DYN4K_GRAPH_END $variant ${components.size} ${edges.size} ${artifacts.size}")
        }
    }
}
