plugins {
    kotlin("multiplatform") version "2.4.20" apply false
    id("com.android.kotlin.multiplatform.library") version "9.3.1" apply false
    id("org.jetbrains.dokka") version "2.2.0" apply false
    id("de.infix.testBalloon") version "1.2.0" apply false
}

allprojects {
    group = "io.github.rubixhacker"
    version = "0.1.0-alpha.1"
}
