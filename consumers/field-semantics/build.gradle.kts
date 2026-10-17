plugins { kotlin("jvm") version "2.4.20"; application }
kotlin { compilerOptions.jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_1_8) }
repositories { mavenCentral() }
dependencies {
    if (project.hasProperty("libraryJar")) implementation(files(project.property("libraryJar")))
    else implementation("org.dyn4j:dyn4j:6.0.0")
}
application { mainClass.set("FieldTypesKt") }
tasks.named<JavaCompile>("compileJava") { options.release.set(8) }
