import org.jetbrains.kotlin.gradle.tasks.KotlinCompilationTask
import org.jetbrains.kotlin.gradle.targets.js.testing.KotlinJsTest
import java.security.MessageDigest

plugins { kotlin("multiplatform") }

val checkout = file(providers.gradleProperty("qualificationCheckout").get())
val staging = file(providers.gradleProperty("qualificationRepository").get())
val version = "0.1.0-alpha.1"

repositories {
    maven { url = uri(staging) }
    mavenCentral()
}

kotlin {
    js {
        browser { testTask { useKarma { useChromeHeadless() } } }
        binaries.executable()
    }
    sourceSets {
        val commonTest by getting {
            dependencies {
                implementation(kotlin("test"))
                implementation("io.github.rubixhacker:dyn4k-core:$version")
                implementation("io.github.rubixhacker:dyn4k:$version")
            }
            kotlin.setSrcDirs(listOf(file("$checkout/dyn4k-core/src/commonTest/kotlin")))
        }
        val jsTest by getting {
            kotlin.setSrcDirs(listOf(file("$checkout/dyn4k-core/src/jsTest/kotlin")))
        }
    }
}

fun friend(): File {
    val artifact = configurations.getByName("jsTestCompileClasspath").resolvedConfiguration
        .resolvedArtifacts.single { it.moduleVersion.id.name == "dyn4k-core-js" }.file
    val staged = file("$staging/io/github/rubixhacker/dyn4k-core-js/$version/dyn4k-core-js-$version.klib")
    fun hash(file: File) = MessageDigest.getInstance("SHA-256").digest(file.readBytes()).toList()
    check(hash(artifact) == hash(staged))
    return artifact
}

tasks.named<KotlinCompilationTask<*>>("compileTestKotlinJs") {
    dependsOn(":qualificationValidateInputs")
    compilerOptions.freeCompilerArgs.addAll(providers.provider {
        listOf("-Xfriend-modules=${friend().absolutePath}")
    })
}
for (mode in listOf("Development", "Production")) {
    tasks.named<KotlinCompilationTask<*>>("compileTest${mode}ExecutableKotlinJs") {
        compilerOptions.freeCompilerArgs.addAll(providers.provider {
            listOf("-Xfriend-modules=${friend().absolutePath}")
        })
    }
}

if (providers.gradleProperty("qualificationProduction").orNull == "true") {
    tasks.named<KotlinJsTest>("jsBrowserTest") {
        dependsOn("jsTestTestProductionExecutableCompileSync")
        inputFileProperty.set(layout.buildDirectory.file(
            "compileSync/js/test/testProductionExecutable/kotlin/${rootProject.name}-core-test.js"))
        doFirst { logger.lifecycle("qualification test input: ${inputFileProperty.get().asFile}") }
    }
}
