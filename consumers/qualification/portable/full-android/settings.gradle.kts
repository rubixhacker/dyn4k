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
        maven { url = uri(providers.gradleProperty("qualificationRepository").get()) }
        google()
        mavenCentral()
    }
}

rootProject.name = "dyn4k-full-android-staged-consumer"
include(":core-tests", ":facade-tests", ":app")
