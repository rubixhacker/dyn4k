import org.jetbrains.kotlin.gradle.tasks.KotlinCompilationTask
import org.jetbrains.kotlin.gradle.plugin.mpp.NativeBuildType
import java.security.MessageDigest

plugins { kotlin("multiplatform") }

val checkout = file(providers.gradleProperty("qualificationCheckout").get())
val staging = file(providers.gradleProperty("qualificationRepository").get())
val target = providers.gradleProperty("qualificationTarget").get()
val variant = target.lowercase()
val version = "0.1.0-alpha.1"

repositories { maven { url = uri(staging) }; mavenCentral() }

kotlin {
    when (target) {
        "iosArm64" -> iosArm64 { binaries { test(setOf(NativeBuildType.RELEASE)) } }
        "tvosArm64" -> tvosArm64 { binaries { test(setOf(NativeBuildType.RELEASE)) } }
        "watchosArm64" -> watchosArm64 { binaries { test(setOf(NativeBuildType.RELEASE)) } }
        "watchosDeviceArm64" -> watchosDeviceArm64 {
            binaries { test(setOf(NativeBuildType.RELEASE)) }
        }
        else -> error("Unsupported physical Apple target: $target")
    }
    sourceSets {
        commonTest {
            dependencies {
                implementation(kotlin("test"))
                implementation("io.github.rubixhacker:dyn4k-core:$version")
                implementation("io.github.rubixhacker:dyn4k:$version")
            }
            kotlin.setSrcDirs(listOf(file("$checkout/dyn4k/src/commonTest/kotlin")))
        }
        nativeTest { kotlin.setSrcDirs(listOf(file("$rootDir/facade/src/nativeTest/kotlin"))) }
    }
}

fun hash(file: File) = MessageDigest.getInstance("SHA-256")
    .digest(file.readBytes()).joinToString("") { "%02x".format(it) }

tasks.named<KotlinCompilationTask<*>>("compileTestKotlin${target.replaceFirstChar { it.uppercase() }}") {
    dependsOn(":qualificationValidateInputs")
    compilerOptions.freeCompilerArgs.addAll(providers.provider {
        val artifact = configurations.getByName("${target}TestCompileKlibraries")
            .resolvedConfiguration.resolvedArtifacts.single {
                it.moduleVersion.id.name == "dyn4k-$variant"
            }.file
        val expected = file("$staging/io/github/rubixhacker/dyn4k-$variant/$version/dyn4k-$variant-$version.klib")
        check(hash(artifact) == hash(expected))
        listOf("-Xfriend-modules=${artifact.absolutePath}")
    })
}
