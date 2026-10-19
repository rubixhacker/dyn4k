import org.jetbrains.kotlin.gradle.tasks.KotlinCompilationTask
import java.security.MessageDigest

plugins { kotlin("multiplatform") }

val checkout = file(providers.gradleProperty("qualificationCheckout").get())
val staging = file(providers.gradleProperty("qualificationRepository").get())
val target = providers.gradleProperty("qualificationLaneId").get().substringBefore(':')
val variant = if (target == "linuxX64") "linuxx64" else "js"
val version = "0.1.0-alpha.1"

fun hash(file: File): String = MessageDigest.getInstance("SHA-256")
    .digest(file.readBytes()).joinToString("") { "%02x".format(it) }

repositories {
    maven { url = uri(staging) }
    mavenCentral()
}

kotlin {
    js { nodejs(); binaries.executable() }
    linuxX64()
    sourceSets {
        val commonTest by getting {
            dependencies {
                implementation(kotlin("test"))
                implementation("io.github.rubixhacker:dyn4k-core:$version")
                implementation("io.github.rubixhacker:dyn4k:$version")
            }
            kotlin.setSrcDirs(listOf(file("$checkout/dyn4k-core/src/commonTest/kotlin")))
            providers.gradleProperty("qualificationProbeSource").orNull?.let {
                kotlin.include("**/$it")
            }
        }
        val linuxX64Test by getting {
            kotlin.setSrcDirs(listOf(file("$checkout/dyn4k-core/src/nativeTest/kotlin")))
        }
        val jsTest by getting {
            kotlin.setSrcDirs(listOf(file("$checkout/dyn4k-core/src/jsTest/kotlin")))
        }
    }
}

fun friend(configuration: String): File {
    val artifact = configurations.getByName(configuration).resolvedConfiguration.resolvedArtifacts
        .single { it.moduleVersion.id.name == "dyn4k-core-$variant" }.file
    val staged = file("$staging/io/github/rubixhacker/dyn4k-core-$variant/$version/dyn4k-core-$variant-$version.klib")
    check(hash(artifact) == hash(staged))
    return artifact
}

tasks.named<KotlinCompilationTask<*>>("compileTestKotlinLinuxX64") {
    dependsOn(":qualificationValidateInputs")
    compilerOptions.freeCompilerArgs.addAll(providers.provider {
        listOf("-g", "-friend-modules", friend("linuxX64TestCompileKlibraries").absolutePath)
    })
}
tasks.named<KotlinCompilationTask<*>>("compileTestKotlinJs") {
    dependsOn(":qualificationValidateInputs")
    compilerOptions.freeCompilerArgs.addAll(providers.provider {
        listOf("-Xfriend-modules=${friend("jsTestCompileClasspath").absolutePath}")
    })
}
tasks.named<KotlinCompilationTask<*>>("compileTestDevelopmentExecutableKotlinJs") {
    compilerOptions.freeCompilerArgs.addAll(providers.provider {
        listOf("-Xfriend-modules=${friend("jsTestCompileClasspath").absolutePath}")
    })
}
