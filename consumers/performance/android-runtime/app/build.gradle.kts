import org.gradle.api.artifacts.component.ModuleComponentIdentifier
import org.gradle.api.artifacts.result.ResolvedDependencyResult

plugins {
    id("com.android.application")
}

android {
    namespace = "io.github.rubixhacker.dyn4k.performance"
    compileSdk = 36

    defaultConfig {
        applicationId = "io.github.rubixhacker.dyn4k.performance"
        versionCode = 1
        versionName = "performance-android-v1"
        minSdk = 21
        targetSdk = 36
        testInstrumentationRunner = "io.github.rubixhacker.dyn4k.performance.PerformanceInstrumentation"
    }
    buildTypes {
        getByName("debug") { isMinifyEnabled = false }
        getByName("release") {
            isMinifyEnabled = true
            signingConfig = signingConfigs.getByName("debug")
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    testBuildType = providers.gradleProperty("performanceTestBuildType").getOrElse("debug")
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation("io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1")
    implementation("io.github.rubixhacker:dyn4k-core-android:0.1.0-alpha.1")
    androidTestImplementation("org.jetbrains.kotlin:kotlin-stdlib:2.4.20")
}

tasks.register("providerArtifacts") {
    doLast {
        val buildType = providers.gradleProperty("performanceTestBuildType").getOrElse("debug")
        fun coordinate(id: org.gradle.api.artifacts.component.ComponentIdentifier): String =
            when (id) {
                is ModuleComponentIdentifier -> "${id.group}:${id.module}:${id.version}"
                else -> "project:app"
            }
        for ((scope, configurationName) in listOf(
            "app" to "${buildType}RuntimeClasspath",
            "test" to "${buildType}AndroidTestRuntimeClasspath",
        )) {
            val configuration = configurations.getByName(configurationName)
            val resolution = configuration.incoming.resolutionResult
            for (component in resolution.allComponents) {
                val from = coordinate(component.id)
                println("DYN4K_GRAPH_COMPONENT $scope $from")
                for (dependency in component.dependencies) {
                    val selected = dependency as? ResolvedDependencyResult
                        ?: error("unresolved $configurationName dependency: $dependency")
                    println("DYN4K_GRAPH_EDGE $scope $from ${coordinate(selected.selected.id)}")
                }
            }
            for (artifact in configuration.resolvedConfiguration.resolvedArtifacts) {
                val id = artifact.moduleVersion.id
                println("DYN4K_GRAPH_ARTIFACT $scope ${id.group}:${id.name}:${id.version} ${artifact.file.canonicalPath}")
            }
        }
    }
}
