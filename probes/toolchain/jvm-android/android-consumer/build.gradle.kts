plugins { id("com.android.application") version "9.3.1" }
repositories { maven { url = uri("../android/build/repo") }; google(); mavenCentral() }
android {
    namespace = "probe.consumer"
    compileSdk = 36
    defaultConfig { applicationId = "probe.consumer"; minSdk = 21; targetSdk = 36; versionCode = 1; versionName = "1" }
    buildTypes {
        getByName("release") {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_1_8; targetCompatibility = JavaVersion.VERSION_1_8 }
}
dependencies { implementation("local.dyn4k.probe:toolchain-probe-android:0.0.1") }
