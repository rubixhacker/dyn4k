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
    lint { checkReleaseBuilds = false }
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
        val artifacts = configurations.getByName("${buildType}RuntimeClasspath")
            .resolvedConfiguration.resolvedArtifacts
        for (artifact in artifacts) {
            val id = artifact.moduleVersion.id
            if (id.group == "io.github.rubixhacker") {
                println("DYN4K_PROVIDER ${id.name} ${artifact.file.canonicalPath}")
            }
        }
    }
}
