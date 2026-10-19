import org.jetbrains.kotlin.gradle.plugin.mpp.NativeBuildType
import org.jetbrains.kotlin.gradle.tasks.KotlinCompilationTask
import java.security.MessageDigest

plugins { kotlin("multiplatform") }

val checkout = file(providers.gradleProperty("qualificationCheckout").get())
val staging = file(providers.gradleProperty("qualificationRepository").get())
val target = providers.gradleProperty("qualificationTarget").get()
val variant = target.lowercase()
val version = "0.1.0-alpha.1"

repositories {
    exclusiveContent {
        forRepository { maven { url = uri(staging) } }
        filter { includeGroup("io.github.rubixhacker") }
    }
    mavenCentral()
}

kotlin {
    when (target) {
        "androidNativeArm32" -> androidNativeArm32 { binaries { test(setOf(NativeBuildType.RELEASE)) } }
        "androidNativeArm64" -> androidNativeArm64 { binaries { test(setOf(NativeBuildType.RELEASE)) } }
        "androidNativeX86" -> androidNativeX86 { binaries { test(setOf(NativeBuildType.RELEASE)) } }
        "androidNativeX64" -> androidNativeX64 { binaries { test(setOf(NativeBuildType.RELEASE)) } }
        else -> error("Unsupported Android Native target")
    }
    sourceSets {
        val commonTest by getting {
            dependencies {
                implementation(kotlin("test"))
                implementation("io.github.rubixhacker:dyn4k-core:$version")
                implementation("io.github.rubixhacker:dyn4k:$version")
            }
            kotlin.setSrcDirs(listOf(file("$checkout/dyn4k/src/commonTest/kotlin")))
        }
    }
}

fun hash(path: File) = MessageDigest.getInstance("SHA-256")
    .digest(path.readBytes()).joinToString("") { "%02x".format(it) }

tasks.named<KotlinCompilationTask<*>>("compileTestKotlin${target.replaceFirstChar { it.uppercase() }}") {
    compilerOptions.freeCompilerArgs.addAll(providers.provider {
        val artifacts = configurations.getByName("${target}TestCompileKlibraries")
            .resolvedConfiguration.resolvedArtifacts
        val friend = artifacts.single { it.moduleVersion.id.name == "dyn4k-$variant" }.file
        val staged = file("$staging/io/github/rubixhacker/dyn4k-$variant/$version/dyn4k-$variant-$version.klib")
        check(hash(friend) == hash(staged))
        listOf("-friend-modules", friend.absolutePath)
    })
}
