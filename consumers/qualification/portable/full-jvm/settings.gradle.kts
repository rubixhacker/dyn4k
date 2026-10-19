pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = "dyn4k-full-staged-jvm-consumer"
include("core", "facade", "jvm:Java:current")
