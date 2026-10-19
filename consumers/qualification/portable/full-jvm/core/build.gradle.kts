import org.jetbrains.kotlin.gradle.tasks.KotlinJvmCompile

plugins {
    kotlin("jvm")
}

val checkout = file(providers.gradleProperty("qualificationCheckout").get())
val staging = file(providers.gradleProperty("qualificationRepository").get())
val coreJar = file("$staging/io/github/rubixhacker/dyn4k-core-jvm/0.1.0-alpha.1/dyn4k-core-jvm-0.1.0-alpha.1.jar")

repositories {
    maven { url = uri(staging) }
    mavenCentral()
}

dependencies {
    testImplementation("io.github.rubixhacker:dyn4k:0.1.0-alpha.1")
    testImplementation("io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1")
    testImplementation(kotlin("test"))
}

sourceSets.test {
    kotlin.srcDir(file("$checkout/dyn4k-core/src/commonTest/kotlin"))
    kotlin.srcDir(file("$checkout/dyn4k-core/src/jvmTest/kotlin"))
}

tasks.named<KotlinJvmCompile>("compileTestKotlin") {
    dependsOn(":qualificationValidateInputs")
    compilerOptions.freeCompilerArgs.add("-Xfriend-paths=${coreJar.absolutePath}")
    compilerOptions.freeCompilerArgs.add("-Xmulti-platform")
    compilerOptions.freeCompilerArgs.add("-Xcommon-sources=${checkout.absolutePath}/dyn4k-core/src/commonTest/kotlin/org/dyn4j/world/CollisionWorldLiveViewErrorsTest.kt")
}

tasks.test {
    useJUnit()
    val selected = file(providers.gradleProperty("qualificationCoreCases").get()).readLines()
    filter {
        selected.forEach { line ->
            val parts = line.split('\t')
            require(parts.size == 3)
            includeTestsMatching("${parts[1]}.${parts[2]}")
        }
    }
}
