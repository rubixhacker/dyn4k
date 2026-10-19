import org.jetbrains.kotlin.gradle.tasks.KotlinJvmCompile

plugins {
    kotlin("jvm")
}

val checkout = file(providers.gradleProperty("qualificationCheckout").get())
val staging = file(providers.gradleProperty("qualificationRepository").get())
val facadeJar = file("$staging/io/github/rubixhacker/dyn4k-jvm/0.1.0-alpha.1/dyn4k-jvm-0.1.0-alpha.1.jar")

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
    kotlin.srcDir(file("$checkout/dyn4k/src/commonTest/kotlin"))
    kotlin.srcDir(file("$checkout/dyn4k/src/jvmTest/kotlin"))
    java.srcDir(file("$checkout/dyn4k/src/jvmTest/java"))
}

tasks.named<KotlinJvmCompile>("compileTestKotlin") {
    dependsOn(":qualificationValidateInputs")
    compilerOptions.freeCompilerArgs.add("-Xfriend-paths=${facadeJar.absolutePath}")
}

tasks.test {
    useJUnit()
    val selected = file(providers.gradleProperty("qualificationFacadeCases").get()).readLines()
    filter {
        selected.forEach { line ->
            val parts = line.split('\t')
            require(parts.size == 3)
            includeTestsMatching("${parts[1]}.${parts[2]}")
        }
    }
}
