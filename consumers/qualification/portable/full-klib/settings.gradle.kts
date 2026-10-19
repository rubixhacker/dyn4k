pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = "dyn4k-full-staged-klib-consumer"
include("core", "facade")
include("linuxX64:Linux x64:current")
include("js:Node.js:current")
