import org.jetbrains.kotlin.gradle.tasks.KotlinJvmCompile
import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    kotlin("jvm")
    id("de.infix.testBalloon")
}

val checkout = file(providers.gradleProperty("qualificationCheckout").get())
val staging = file(providers.gradleProperty("qualificationRepository").get())
val facadeJar = file("$staging/io/github/rubixhacker/dyn4k-jvm/0.1.0-alpha.1/dyn4k-jvm-0.1.0-alpha.1.jar")
val configuration = providers.gradleProperty("qualificationBuildConfiguration").get()
val runtimeHome = file(providers.gradleProperty("qualificationRuntimeJavaHome").get())
val runtimeMajor = if (providers.gradleProperty("qualificationLaneId").get().contains(":minimum:")) 8 else 21

repositories {
    maven { url = uri(staging) }
    mavenCentral()
}

dependencies {
    testImplementation("io.github.rubixhacker:dyn4k:0.1.0-alpha.1")
    testImplementation("io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1")
    testImplementation(kotlin("test"))
    testImplementation("de.infix.testBalloon:testBalloon-framework-core:1.2.0")
}

sourceSets.test {
    kotlin.srcDir(file("$checkout/dyn4k/src/commonTest/kotlin"))
    kotlin.srcDir(file("$checkout/dyn4k/src/jvmTest/kotlin"))
    java.srcDir(file("$checkout/dyn4k/src/jvmTest/java"))
}

tasks.named<KotlinJvmCompile>("compileTestKotlin") {
    dependsOn(":qualificationValidateInputs")
    compilerOptions.jvmTarget.set(if (runtimeMajor == 8) JvmTarget.JVM_1_8 else JvmTarget.JVM_21)
    compilerOptions.freeCompilerArgs.add("-Xfriend-paths=${facadeJar.absolutePath}")
    if (configuration == "no-optimize") compilerOptions.freeCompilerArgs.add("-Xno-optimize")
}

tasks.named<JavaCompile>("compileTestJava") {
    options.release.set(runtimeMajor)
}

tasks.test {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(runtimeMajor))
    })
    doFirst {
        check(javaLauncher.get().metadata.installationPath.asFile.canonicalFile == runtimeHome.canonicalFile)
    }
    jvmArgs("-XshowSettings:properties")
    val selected = file(providers.gradleProperty("qualificationFacadeCases").get()).readLines()
    filter {
        selected.forEach { line ->
            val parts = line.split('\t')
            require(parts.size == 3)
            // TestBalloon separates a suite path element with U+2198.
            includeTestsMatching("${parts[1]}↘${parts[2]}")
        }
    }
}
