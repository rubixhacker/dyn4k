plugins {
    id("com.android.application")
}

android {
    namespace = "io.github.rubixhacker.dyn4k.optimized"
    compileSdk = 36

    defaultConfig {
        applicationId = "io.github.rubixhacker.dyn4k.optimized"
        minSdk = 21
        targetSdk = 36
        testInstrumentationRunner = "io.github.rubixhacker.dyn4k.optimized.OptimizedJourneyTest"
    }

    buildTypes {
        getByName("debug") { isMinifyEnabled = false }
        getByName("release") {
            isMinifyEnabled = true
            signingConfig = signingConfigs.getByName("debug")
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    testBuildType = providers.gradleProperty("runtimeTestBuildType").getOrElse("debug")
    testOptions { animationsDisabled = true }
}

dependencies {
    implementation("io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1")
    implementation("io.github.rubixhacker:dyn4k-core-android:0.1.0-alpha.1")
}

val repositoryRoot = rootProject.projectDir.resolve("../..").canonicalFile
val preparedManifest = providers.gradleProperty("preparedManifest")
val verifyConsumerSources = tasks.register<Exec>("verifyConsumerSources") {
    workingDir(repositoryRoot)
    commandLine(
        "python3",
        repositoryRoot.resolve("tools/android-runtime/prepare.py"),
        "--verify-consumers",
        preparedManifest.get(),
    )
}

tasks.configureEach {
    if (name.startsWith("compile") && (name.contains("JavaWithJavac") || name.contains("AndroidTest"))) {
        dependsOn(verifyConsumerSources)
    }
}
