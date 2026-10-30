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

include(":core", ":host", ":compatibility", ":performance", ":numerical", ":qualification")
