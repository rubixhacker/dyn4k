plugins {
    id("com.android.application")
    id("de.infix.testBalloon")
}

android {
    namespace = "io.github.rubixhacker.dyn4k.runtime"
    compileSdk = 36

    defaultConfig {
        applicationId = "io.github.rubixhacker.dyn4k.runtime"
        minSdk = 21
        targetSdk = 36
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    flavorDimensions += "provider"
    productFlavors {
        create("baseline") { dimension = "provider"; applicationIdSuffix = ".baseline" }
        create("candidate") { dimension = "provider"; applicationIdSuffix = ".candidate" }
    }

    buildTypes {
        getByName("debug") { isMinifyEnabled = false }
        getByName("release") {
            isMinifyEnabled = true
            signingConfig = signingConfigs.getByName("debug")
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            testProguardFiles("test-proguard-rules.pro")
        }
    }
    testBuildType = providers.gradleProperty("runtimeTestBuildType").getOrElse("debug")
    testOptions { animationsDisabled = true }
    sourceSets.getByName("androidTestBaseline").java.srcDir(layout.buildDirectory.dir("generated/consumer-java").get().asFile)
}

dependencies {
    "baselineImplementation"("org.dyn4j:dyn4j:6.0.0")
    "candidateImplementation"("io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1")
    "candidateImplementation"("io.github.rubixhacker:dyn4k-core-android:0.1.0-alpha.1")

    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test:runner:1.7.0")
    androidTestImplementation("androidx.test.ext:junit:1.3.0")
    androidTestImplementation("junit:junit:4.13.2")
    androidTestImplementation("com.google.errorprone:error_prone_annotations:2.50.0")
    androidTestImplementation("org.jetbrains.kotlin:kotlin-stdlib:2.4.20")
    "androidTestCandidateImplementation"(files(providers.gradleProperty("portableSuiteJar").get()))
    "androidTestCandidateImplementation"(files(rootProject.layout.projectDirectory.file("full/build/generated/full-consumers.jar")))
    "androidTestCandidateImplementation"(kotlin("test"))
    "androidTestCandidateImplementation"("de.infix.testBalloon:testBalloon-framework-core:1.2.0")
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
    if (name.startsWith("compile") && name.contains("AndroidTest")) {
        dependsOn(verifyConsumerSources)
    }
}
