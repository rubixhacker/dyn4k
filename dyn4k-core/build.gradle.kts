@file:OptIn(org.jetbrains.kotlin.gradle.ExperimentalWasmDsl::class)

import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import java.security.MessageDigest
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.util.zip.ZipEntry
import java.util.zip.ZipFile
import java.util.zip.ZipOutputStream
import org.objectweb.asm.ClassReader
import org.objectweb.asm.ClassVisitor
import org.objectweb.asm.ClassWriter
import org.objectweb.asm.FieldVisitor
import org.objectweb.asm.MethodVisitor
import org.objectweb.asm.Opcodes
import org.objectweb.asm.Type

plugins {
    kotlin("multiplatform")
    id("com.android.kotlin.multiplatform.library")
    `maven-publish`
}

data class JvmApiSpec(
    val publicFields: Set<String> = emptySet(),
    val protectedFields: Set<String> = emptySet(),
    val staticMethods: Set<String> = emptySet(),
    val packageType: Boolean = false,
    val packageFields: Set<String> = emptySet(),
    val packageNodeMethods: Boolean = false,
    val packageMethods: Set<String> = emptySet(),
    val protectedMethods: Set<String> = emptySet(),
    val appendIterable: Boolean = false
)

val jvmApi = mapOf(
    "org/dyn4j/Copyable" to JvmApiSpec(),
    "org/dyn4j/Version" to JvmApiSpec(
        staticMethods = setOf("getVersion", "getVersionNumbers", "getMajorNumber", "getMinorNumber", "getRevisionNumber", "main")
    ),
    "org/dyn4j/AVLTree" to JvmApiSpec(
        packageFields = setOf("root", "size"),
        packageNodeMethods = true,
        packageMethods = setOf("get"),
        appendIterable = true
    ),
    "org/dyn4j/BinarySearchTree" to JvmApiSpec(),
    "org/dyn4j/BinarySearchTreeSearchCriteria" to JvmApiSpec(),
    "org/dyn4j/Reference" to JvmApiSpec(publicFields = setOf("value")),
    "org/dyn4j/BinarySearchTreeNode" to JvmApiSpec(
        packageType = true,
        packageFields = setOf("comparable", "parent", "left", "right"),
        packageMethods = setOf("isLeftChild")
    ),
    "org/dyn4j/BinarySearchTreeIterator" to JvmApiSpec(
        packageType = true,
        protectedMethods = setOf("pushLeftFrom", "pushLeft", "pushRight")
    ),
    "org/dyn4j/Epsilon" to JvmApiSpec(
        publicFields = setOf("E"), staticMethods = setOf("compute")
    ),
    "org/dyn4j/geometry/Vector2" to JvmApiSpec(
        publicFields = setOf("x", "y", "X_AXIS", "Y_AXIS", "INV_X_AXIS", "INV_Y_AXIS"),
        staticMethods = setOf("create", "tripleProduct")
    ),
    "org/dyn4j/geometry/Vector3" to JvmApiSpec(
        publicFields = setOf("x", "y", "z"), staticMethods = setOf("tripleProduct")
    ),
    "org/dyn4j/geometry/Rotation" to JvmApiSpec(
        protectedFields = setOf("cost", "sint"),
        staticMethods = setOf(
            "of", "ofDegrees", "rotation0", "rotation45", "rotation90", "rotation135",
            "rotation180", "rotation225", "rotation270", "rotation315",
            "getNormalizedAngle", "getShortestDistance", "isAngleBetween"
        )
    ),
    "org/dyn4j/geometry/Matrix22" to JvmApiSpec(
        publicFields = setOf("m00", "m01", "m10", "m11")
    ),
    "org/dyn4j/geometry/Matrix33" to JvmApiSpec(
        publicFields = setOf("m00", "m01", "m02", "m10", "m11", "m12", "m20", "m21", "m22")
    ),
    "org/dyn4j/geometry/Transform" to JvmApiSpec(
        protectedFields = setOf("cost", "sint", "x", "y")
    )
)

val patchJvmArchive: (File) -> Unit = { jar ->
        val temporary = jar.resolveSibling(jar.name + ".patched")
        ZipFile(jar).use { input ->
            val companionMethods = jvmApi.mapValues { (owner, spec) ->
                val entry = input.getEntry(owner + "\$Companion.class")
                if (entry == null) emptyList() else {
                    val methods = mutableListOf<Pair<String, String>>()
                    ClassReader(input.getInputStream(entry).use { it.readBytes() }).accept(
                        object : ClassVisitor(Opcodes.ASM9) {
                            override fun visitMethod(
                                access: Int, name: String, descriptor: String,
                                signature: String?, exceptions: Array<out String>?
                            ): MethodVisitor? {
                                if (name in spec.staticMethods && access and Opcodes.ACC_PUBLIC != 0) {
                                    methods += name to descriptor
                                }
                                return null
                            }
                        },
                        ClassReader.SKIP_CODE or ClassReader.SKIP_DEBUG or ClassReader.SKIP_FRAMES
                    )
                    methods
                }
            }
            ZipOutputStream(temporary.outputStream().buffered()).use { output ->
                for (entry in input.entries().asSequence()) {
                    val owner = entry.name.removeSuffix(".class")
                    val bytes = input.getInputStream(entry).use { it.readBytes() }
                    val spec = if (entry.name.endsWith(".class")) jvmApi[owner] else null
                    val content = if (spec == null) bytes else {
                        val writer = ClassWriter(ClassWriter.COMPUTE_MAXS)
                        val visitor = object : ClassVisitor(Opcodes.ASM9, writer) {
                            val present = mutableSetOf<Pair<String, String>>()
                            override fun visit(
                                version: Int, access: Int, name: String, signature: String?,
                                superName: String?, interfaces: Array<out String>?
                            ) {
                                val visibility = Opcodes.ACC_PUBLIC or Opcodes.ACC_PROTECTED or Opcodes.ACC_PRIVATE
                                val revisedAccess = if (spec.packageType) access and visibility.inv() else access
                                val extra = if (spec.appendIterable) arrayOf("java/lang/Iterable") else emptyArray()
                                val revisedInterfaces = (interfaces.orEmpty().toList() + extra).distinct().toTypedArray()
                                var revisedSignature = signature?.replace(
                                    "Ljava/lang/Comparable<-TE;>;", "Ljava/lang/Comparable<TE;>;"
                                )
                                if (spec.appendIterable && revisedSignature?.contains("Ljava/lang/Iterable<TE;>;") != true) {
                                    revisedSignature += "Ljava/lang/Iterable<TE;>;"
                                }
                                super.visit(version, revisedAccess, name, revisedSignature, superName, revisedInterfaces)
                            }
                            override fun visitField(
                                access: Int, name: String, descriptor: String,
                                signature: String?, value: Any?
                            ): FieldVisitor {
                                val visibility = Opcodes.ACC_PUBLIC or Opcodes.ACC_PROTECTED or Opcodes.ACC_PRIVATE
                                val revised = when (name) {
                                    in spec.publicFields -> (access and visibility.inv()) or Opcodes.ACC_PUBLIC
                                    in spec.protectedFields -> (access and visibility.inv()) or Opcodes.ACC_PROTECTED
                                    in spec.packageFields -> access and visibility.inv()
                                    else -> access
                                }
                                return super.visitField(revised, name, descriptor, signature, value)
                            }
                            override fun visitMethod(
                                access: Int, name: String, descriptor: String,
                                signature: String?, exceptions: Array<out String>?
                            ): MethodVisitor {
                                present += name to descriptor
                                val visibility = Opcodes.ACC_PUBLIC or Opcodes.ACC_PROTECTED or Opcodes.ACC_PRIVATE
                                val packageMethod = name in spec.packageMethods ||
                                    (spec.packageNodeMethods && descriptor.startsWith("(Lorg/dyn4j/BinarySearchTreeNode;"))
                                val revisedAccess = when {
                                    packageMethod -> access and visibility.inv() and Opcodes.ACC_FINAL.inv()
                                    name in spec.protectedMethods ->
                                        ((access and visibility.inv()) or Opcodes.ACC_PROTECTED) and Opcodes.ACC_FINAL.inv()
                                    owner == "org/dyn4j/BinarySearchTreeNode" && name == "getComparable" ->
                                        access and Opcodes.ACC_FINAL.inv()
                                    else -> access
                                }
                                val revisedSignature = signature?.replace(
                                    "Ljava/lang/Comparable<-TE;>;", "Ljava/lang/Comparable<TE;>;"
                                )
                                return super.visitMethod(revisedAccess, name, descriptor, revisedSignature, exceptions)
                            }
                            override fun visitEnd() {
                                for ((name, descriptor) in companionMethods[owner].orEmpty()) {
                                    if ((name to descriptor) in present) continue
                                    val method = super.visitMethod(
                                        Opcodes.ACC_PUBLIC or Opcodes.ACC_STATIC or
                                            (if (owner == "org/dyn4j/Version") Opcodes.ACC_FINAL else 0),
                                        name, descriptor, null, null
                                    )
                                    method.visitCode()
                                    method.visitFieldInsn(
                                        Opcodes.GETSTATIC, owner, "Companion", "L" + owner + "\$Companion;"
                                    )
                                    var index = 0
                                    for (argument in Type.getArgumentTypes(descriptor)) {
                                        method.visitVarInsn(argument.getOpcode(Opcodes.ILOAD), index)
                                        index += argument.size
                                    }
                                    method.visitMethodInsn(
                                        Opcodes.INVOKEVIRTUAL, owner + "\$Companion",
                                        name, descriptor, false
                                    )
                                    method.visitInsn(Type.getReturnType(descriptor).getOpcode(Opcodes.IRETURN))
                                    method.visitMaxs(0, 0)
                                    method.visitEnd()
                                }
                                super.visitEnd()
                            }
                        }
                        ClassReader(bytes).accept(visitor, 0)
                        writer.toByteArray()
                    }
                    val replacement = ZipEntry(entry.name)
                    replacement.time = entry.time
                    output.putNextEntry(replacement)
                    output.write(content)
                    output.closeEntry()
                }
            }
        }
        Files.move(temporary.toPath(), jar.toPath(), StandardCopyOption.REPLACE_EXISTING)
}

tasks.withType<Jar>().configureEach {
    if (name == "jvmJar") doLast { patchJvmArchive(archiveFile.get().asFile) }
}

tasks.matching {
    it.name == "bundleAndroidMainClassesToCompileJar" ||
        it.name == "bundleAndroidMainClassesToRuntimeJar" ||
        it.name == "syncAndroidMainLibJars"
}.configureEach {
    doLast {
        outputs.files.files.flatMap { output ->
            if (output.isDirectory) output.walkTopDown().filter { it.extension == "jar" }.toList()
            else listOf(output)
        }.filter { it.extension == "jar" && ZipFile(it).use { zip ->
            zip.getEntry("org/dyn4j/geometry/Vector2.class") != null
        } }.forEach(patchJvmArchive)
    }
}

kotlin {
    jvmToolchain(21)
    jvm {
        compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) }
    }
    android {
        namespace = "org.dyn4j"
        compileSdk = 36
        minSdk = 21
        withHostTest {}
        compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) }
    }
    js { nodejs() }
    wasmJs { nodejs() }
    wasmWasi { nodejs() }
    linuxX64()
    linuxArm64()
    mingwX64()
    macosArm64()
    iosArm64()
    iosSimulatorArm64()
    iosX64()
    tvosArm64()
    tvosSimulatorArm64()
    watchosArm64()
    watchosDeviceArm64()
    watchosSimulatorArm64()
    androidNativeArm32()
    androidNativeArm64()
    androidNativeX86()
    androidNativeX64()

    sourceSets {
        commonTest.dependencies { implementation(kotlin("test")) }
    }
}

publishing {
    publications.withType<MavenPublication>().configureEach {
        artifact(rootProject.file("LICENSE.md")) {
            classifier = "license"
            extension = "md"
        }
        pom {
            name = "dyn4k core"
            description = "Kotlin Multiplatform dyn4j 6.0.0 compatible foundation"
            url = "https://github.com/rubixhacker/dyn4k"
            licenses {
                license {
                    name = "BSD 3-Clause License"
                    url = "https://opensource.org/licenses/BSD-3-Clause"
                }
            }
            scm { url = "https://github.com/rubixhacker/dyn4k" }
            developers { developer { id = "rubixhacker"; name = "Stewart Boling" } }
        }
    }
    repositories { maven { name = "staging"; url = uri(rootProject.layout.buildDirectory.dir("staging-repository")) } }
}

tasks.withType<Jar>().configureEach {
    from(rootProject.file("LICENSE.md")) { into("META-INF") }
}

val baseline = configurations.create("baselineOracle")
dependencies { baseline("org.dyn4j:dyn4j:6.0.0") }
val baselineSources = configurations.create("baselineSources")
dependencies { baselineSources("org.dyn4j:dyn4j:6.0.0:sources") }
val upstreamTestRuntime = configurations.create("upstreamTestRuntime")
dependencies { upstreamTestRuntime("junit:junit:4.13.1") }

val verifyBaseline by tasks.registering {
    val files = baseline
    inputs.files(files)
    doLast {
        val jar = files.singleFile
        val digest = MessageDigest.getInstance("SHA-256").digest(jar.readBytes())
            .joinToString("") { "%02x".format(it) }
        check(digest == "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e") {
            "dyn4j 6.0.0 binary SHA-256 differs: $digest"
        }
        println("Baseline SHA-256 verified: $digest")
    }
}

tasks.register("verifyBaselineSources") {
    val files = baselineSources
    inputs.files(files)
    doLast {
        val jar = files.singleFile
        val digest = MessageDigest.getInstance("SHA-256").digest(jar.readBytes())
            .joinToString("") { "%02x".format(it) }
        check(digest == "83b47be47bdce27681139dab84937e0f586b70ab800dc494fbebed4b58893223") {
            "dyn4j 6.0.0 sources SHA-256 differs: $digest"
        }
        println("Baseline sources SHA-256 verified: $digest")
    }
}

val javaConsumerSource = file("src/jvmConsumer/java/FoundationConsumer.java")
val baselineConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(verifyBaseline)
    source(javaConsumerSource)
    classpath = baseline
    destinationDirectory.set(layout.buildDirectory.dir("consumer/baseline"))
    options.release.set(8)
}

val jvmMain = kotlin.targets.getByName("jvm").compilations.getByName("main")
tasks.register<Exec>("verifyJvmApi") {
    dependsOn(verifyBaseline, tasks.named("jvmJar"))
    doFirst {
        commandLine(
            "python3",
            rootProject.file("scripts/verify-foundation-jvm-api.py").absolutePath,
            baseline.singleFile.absolutePath,
            tasks.named<Jar>("jvmJar").get().archiveFile.get().asFile.absolutePath
        )
    }
}
tasks.register<Exec>("verifyTreeJvmApi") {
    dependsOn(verifyBaseline, tasks.named("jvmJar"))
    doFirst {
        commandLine(
            "python3",
            rootProject.file("scripts/verify-tree-jvm-api.py").absolutePath,
            baseline.singleFile.absolutePath,
            tasks.named<Jar>("jvmJar").get().archiveFile.get().asFile.absolutePath
        )
    }
}
val candidateConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(tasks.named("jvmJar"))
    source(javaConsumerSource)
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/candidate"))
    options.release.set(8)
}

tasks.register<JavaExec>("runBaselineConsumer") {
    dependsOn(baselineConsumer)
    classpath(baselineConsumer.flatMap { it.destinationDirectory }, baseline)
    mainClass.set("FoundationConsumer")
}

tasks.register<JavaExec>("runCandidateConsumer") {
    dependsOn(candidateConsumer)
    classpath(candidateConsumer.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    mainClass.set("FoundationConsumer")
}

val androidCompileJar = tasks.matching { it.name == "bundleAndroidMainClassesToCompileJar" }
val androidRuntimeJar = tasks.matching { it.name == "bundleAndroidMainClassesToRuntimeJar" }
val androidCandidateConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(androidCompileJar)
    source(javaConsumerSource)
    classpath = files(androidCompileJar, jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/android-candidate"))
    options.release.set(8)
}
tasks.register<JavaExec>("runAndroidCandidateConsumer") {
    dependsOn(androidCandidateConsumer, androidRuntimeJar)
    classpath(
        androidCandidateConsumer.flatMap { it.destinationDirectory },
        androidRuntimeJar,
        jvmMain.runtimeDependencyFiles
    )
    mainClass.set("FoundationConsumer")
}

val treeConsumerSources = files("src/jvmConsumer/java/TreeConsumer.java", "src/jvmConsumer/java/org/dyn4j/TreePackageConsumer.java")
val baselineTreeConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(verifyBaseline)
    source(treeConsumerSources)
    classpath = baseline
    destinationDirectory.set(layout.buildDirectory.dir("consumer/tree-baseline"))
    options.release.set(8)
}
val candidateTreeConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(tasks.named("jvmJar"))
    source(treeConsumerSources)
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/tree-candidate"))
    options.release.set(8)
}
tasks.register<JavaExec>("runBaselineTreeConsumer") {
    dependsOn(baselineTreeConsumer)
    classpath(baselineTreeConsumer.flatMap { it.destinationDirectory }, baseline)
    mainClass.set("TreeConsumer")
}
tasks.register<JavaExec>("runBaselineTreePackageConsumer") {
    dependsOn(baselineTreeConsumer)
    classpath(baselineTreeConsumer.flatMap { it.destinationDirectory }, baseline)
    mainClass.set("org.dyn4j.TreePackageConsumer")
}
tasks.register<JavaExec>("runCandidateTreePackageConsumer") {
    dependsOn(candidateTreeConsumer)
    classpath(candidateTreeConsumer.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    mainClass.set("org.dyn4j.TreePackageConsumer")
}
tasks.register<JavaExec>("runCandidateTreeConsumer") {
    dependsOn(candidateTreeConsumer)
    classpath(candidateTreeConsumer.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    mainClass.set("TreeConsumer")
}
val androidCandidateTreeConsumer by tasks.registering(JavaCompile::class) {
    dependsOn(androidCompileJar)
    source(treeConsumerSources)
    classpath = files(androidCompileJar, jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("consumer/tree-android-candidate"))
    options.release.set(8)
}
tasks.register<JavaExec>("runAndroidCandidateTreeConsumer") {
    dependsOn(androidCandidateTreeConsumer, androidRuntimeJar)
    classpath(androidCandidateTreeConsumer.flatMap { it.destinationDirectory }, androidRuntimeJar, jvmMain.runtimeDependencyFiles)
    mainClass.set("TreeConsumer")
}
tasks.register<JavaExec>("runAndroidCandidateTreePackageConsumer") {
    dependsOn(androidCandidateTreeConsumer, androidRuntimeJar)
    classpath(androidCandidateTreeConsumer.flatMap { it.destinationDirectory }, androidRuntimeJar, jvmMain.runtimeDependencyFiles)
    mainClass.set("org.dyn4j.TreePackageConsumer")
}

val upstreamCheckout = layout.buildDirectory.dir("upstream-dyn4j")
val foundationTestNames = listOf(
    "Vector2Test", "Vector3Test", "RotationTest", "Matrix22Test",
    "Matrix33Test", "TransformTest"
)
val fetchUpstreamTests by tasks.registering(Exec::class) {
    outputs.dir(upstreamCheckout)
    outputs.upToDateWhen { false }
    commandLine(
        rootProject.file("scripts/fetch-upstream-tests.sh").absolutePath,
        upstreamCheckout.get().asFile.absolutePath
    )
}
val compileUpstreamFoundationTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, tasks.named("jvmJar"))
    source(foundationTestNames.map {
        upstreamCheckout.map { dir -> dir.file("src/test/java/org/dyn4j/geometry/$it.java") }
    })
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-tests/classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runUpstreamFoundationTests") {
    dependsOn(compileUpstreamFoundationTests)
    classpath(
        compileUpstreamFoundationTests.flatMap { it.destinationDirectory },
        tasks.named("jvmJar"),
        jvmMain.runtimeDependencyFiles,
        upstreamTestRuntime
    )
    mainClass.set("org.junit.runner.JUnitCore")
    args(foundationTestNames.map { "org.dyn4j.geometry.$it" })
}

val treeTestNames = listOf("AVLTreeTest", "ReferenceTest", "VersionTest")
val compileUpstreamTreeTests by tasks.registering(JavaCompile::class) {
    dependsOn(fetchUpstreamTests, tasks.named("jvmJar"))
    source(treeTestNames.map { upstreamCheckout.map { dir -> dir.file("src/test/java/org/dyn4j/$it.java") } })
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    destinationDirectory.set(layout.buildDirectory.dir("upstream-tree-tests/classes"))
    options.release.set(8)
}
tasks.register<JavaExec>("runUpstreamTreeTests") {
    dependsOn(compileUpstreamTreeTests)
    classpath(compileUpstreamTreeTests.flatMap { it.destinationDirectory }, tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles, upstreamTestRuntime)
    mainClass.set("org.junit.runner.JUnitCore")
    args(treeTestNames.map { "org.dyn4j.$it" })
}
