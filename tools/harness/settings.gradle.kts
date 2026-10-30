pluginManagement {
    repositories {
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = "dyn4k-harness"

include(":core", ":compatibility", ":performance", ":numerical", ":qualification")
