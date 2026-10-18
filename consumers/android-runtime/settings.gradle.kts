pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        maven { url = uri(providers.gradleProperty("stagingRepository").get()) }
        google()
        mavenCentral()
    }
}

rootProject.name = "dyn4k-android-runtime"
include(":app")
include(":optimized")
include(":full")
