import org.gradle.api.artifacts.component.ModuleComponentIdentifier
import org.gradle.api.artifacts.result.ResolvedDependencyResult

plugins { id("com.android.application") }

val output = file(providers.gradleProperty("qualificationOutput").get())

android {
    namespace = "io.github.rubixhacker.dyn4k.qualification.fullandroid"
    compileSdk = 36
    defaultConfig {
        applicationId = "io.github.rubixhacker.dyn4k.qualification.fullandroid"
        minSdk = 21
        targetSdk = 36
        testInstrumentationRunner = "io.github.rubixhacker.dyn4k.qualification.fullandroid.FullJourneyTest"
    }
    buildTypes {
        getByName("debug") { isMinifyEnabled = false }
        getByName("release") {
            isMinifyEnabled = true
            signingConfig = signingConfigs.getByName("debug")
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"),
                          output.resolve("full-keep.pro"))
        }
    }
    testBuildType = providers.gradleProperty("runtimeTestBuildType").getOrElse("debug")
    testOptions { animationsDisabled = true }
    sourceSets.getByName("main").assets.srcDir(output.resolve("assets"))
}

dependencies {
    implementation("io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1")
    implementation("io.github.rubixhacker:dyn4k-core-android:0.1.0-alpha.1")
    implementation(project(":core-tests"))
    implementation(project(":facade-tests"))
    implementation("org.jetbrains.kotlin:kotlin-stdlib:2.4.20")
    implementation("org.jetbrains.kotlin:kotlin-test-junit:2.4.20")
    implementation("junit:junit:4.13.2")
}

tasks.register("providerArtifacts") {
    doLast {
        for (variant in listOf("debug", "release")) {
            val configuration = configurations.getByName("${variant}RuntimeClasspath")
            val resolution = configuration.incoming.resolutionResult
            fun coordinate(id: org.gradle.api.artifacts.component.ComponentIdentifier): String =
                when (id) {
                    is ModuleComponentIdentifier -> "${id.group}:${id.module}:${id.version}"
                    else -> "project:${id.displayName}"
                }
            val components = resolution.allComponents.map { coordinate(it.id) }.toSortedSet()
            val edges = resolution.allComponents.flatMap { component ->
                component.dependencies.map { dependency ->
                    val resolved = dependency as? ResolvedDependencyResult
                        ?: error("unresolved ${variant} dependency: $dependency")
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
