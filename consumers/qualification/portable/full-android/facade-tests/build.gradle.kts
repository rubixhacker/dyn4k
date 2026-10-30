import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import org.jetbrains.kotlin.gradle.tasks.KotlinCompile

plugins { kotlin("jvm") }

val checkout = file(providers.gradleProperty("sourceCheckout").get())
val coreClasses = file(providers.gradleProperty("coreClasses").get())
val facadeClasses = file(providers.gradleProperty("facadeClasses").get())

kotlin {
    jvmToolchain(21)
    compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) }
}

sourceSets.main {
    kotlin.srcDir(checkout.resolve("dyn4k/src/commonTest/kotlin"))
}

dependencies {
    compileOnly(files(coreClasses, facadeClasses))
    implementation("org.jetbrains.kotlin:kotlin-stdlib:2.4.20")
    implementation(kotlin("test"))
    implementation("de.infix.testBalloon:testBalloon-framework-core:1.2.0")
    implementation("junit:junit:4.13.2")
}

tasks.withType<KotlinCompile>().configureEach {
    compilerOptions.freeCompilerArgs.addAll(
        "-Xmulti-platform", "-Xfriend-paths=${coreClasses.absolutePath},${facadeClasses.absolutePath}")
}

tasks.withType<JavaCompile>().configureEach { options.release.set(8) }
