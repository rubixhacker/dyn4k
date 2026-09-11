plugins { application }
repositories {
    maven { url = uri("../build/repo") }
    mavenCentral()
}
dependencies { implementation("local.dyn4k.probe:toolchain-probe-jvm:0.0.1") }
java { toolchain.languageVersion.set(JavaLanguageVersion.of(21)) }
tasks.withType<JavaCompile>().configureEach { options.release.set(8) }
application { mainClass.set("Consumer") }
sourceSets.main { java.srcDir(".") }

configurations.configureEach {
    if (isCanBeResolved) attributes.attribute(org.gradle.api.attributes.java.TargetJvmVersion.TARGET_JVM_VERSION_ATTRIBUTE, 8)
}
