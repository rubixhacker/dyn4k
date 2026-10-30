import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import org.jetbrains.kotlin.gradle.tasks.KotlinCompile

plugins { kotlin("jvm") }

val checkout = file(providers.gradleProperty("sourceCheckout").get())
val providerClasses = file(providers.gradleProperty("coreClasses").get())
val commonSources = fileTree(checkout.resolve("dyn4k-core/src/commonTest/kotlin")) {
    include("**/*.kt")
}.files.sortedBy { it.absolutePath }

kotlin {
    jvmToolchain(21)
    compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) }
}

sourceSets.main {
    kotlin.srcDir(checkout.resolve("dyn4k-core/src/commonTest/kotlin"))
    kotlin.srcDir(checkout.resolve("dyn4k-core/src/androidHostTest/kotlin"))
}

dependencies {
    compileOnly(files(providerClasses))
    implementation("org.jetbrains.kotlin:kotlin-stdlib:2.4.20")
    implementation(kotlin("test"))
    implementation("de.infix.testBalloon:testBalloon-framework-core:1.2.0")
    implementation("junit:junit:4.13.2")
}

tasks.withType<KotlinCompile>().configureEach {
    compilerOptions.freeCompilerArgs.addAll(
        "-Xmulti-platform",
        "-Xcommon-sources=${commonSources.joinToString(",") { it.absolutePath }}",
        "-Xfriend-paths=${providerClasses.absolutePath}")
}

tasks.withType<JavaCompile>().configureEach { options.release.set(8) }
