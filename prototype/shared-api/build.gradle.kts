plugins { kotlin("multiplatform") version "2.4.10" }
repositories { mavenCentral() }
kotlin {
    jvm { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) } }
    js { nodejs(); binaries.executable() }
}
val jvmMain = kotlin.targets.getByName("jvm").compilations.getByName("main")
tasks.register<JavaExec>("journey") {
    dependsOn("jvmMainClasses")
    classpath(jvmMain.output.allOutputs, jvmMain.runtimeDependencyFiles)
    mainClass.set("probe.MainKt")
}
tasks.register<JavaExec>("play") {
    dependsOn("jvmMainClasses")
    classpath(jvmMain.output.allOutputs, jvmMain.runtimeDependencyFiles)
    mainClass.set("probe.PlayKt")
    standardInput = System.`in`
}
tasks.register("runtimeClasspath") {
    dependsOn("jvmJar")
    doLast { layout.buildDirectory.file("runtime-classpath.txt").get().asFile.writeText(
        files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles).asPath
    ) }
}
val baseline = configurations.create("baseline")
dependencies { baseline("org.dyn4j:dyn4j:6.0.0") }
tasks.register<Copy>("baselineJar") { from(baseline); into(layout.buildDirectory.dir("baseline")) }
val compileBaseline = tasks.register<JavaCompile>("compileBaseline") {
    dependsOn("baselineJar")
    source("fixtures/Consumer.java")
    classpath = baseline
    destinationDirectory.set(layout.buildDirectory.dir("fixtures/baseline"))
    options.release.set(17)
}
val compileCandidate = tasks.register<JavaCompile>("compileCandidate") {
    dependsOn("jvmJar")
    source("fixtures/Consumer.java")
    classpath = files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles)
    destinationDirectory.set(layout.buildDirectory.dir("fixtures/candidate"))
    options.release.set(17)
}
for ((label, compilation, runtime) in listOf(
    Triple("Baseline", compileBaseline, baseline),
    Triple("Candidate", compileCandidate, files(tasks.named("jvmJar"), jvmMain.runtimeDependencyFiles))
)) {
    tasks.register<JavaExec>("run$label") {
        dependsOn(compilation)
        classpath(compilation.flatMap { it.destinationDirectory }, runtime)
        mainClass.set("Consumer")
    }
}
val mixed = kotlin.targets.getByName("jvm").compilations.create("mixed") {
    associateWith(jvmMain)
    defaultSourceSet.kotlin.srcDir("fixtures")
    compileDependencyFiles += files(compileCandidate.flatMap { it.destinationDirectory })
    compileTaskProvider.configure { dependsOn(compileCandidate) }
}
tasks.register<JavaExec>("mixedJourney") {
    dependsOn(mixed.compileTaskProvider)
    classpath(mixed.output.allOutputs, mixed.runtimeDependencyFiles, compileCandidate.flatMap { it.destinationDirectory })
    mainClass.set("MixedKt")
}
tasks.withType<JavaCompile>().configureEach { options.release.set(17) }
