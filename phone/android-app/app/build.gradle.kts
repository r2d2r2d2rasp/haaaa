plugins {
    id("com.android.application")
}

android {
    namespace = "it.bussense.phone"
    compileSdk = 35

    defaultConfig {
        applicationId = "it.bussense.phone"
        minSdk = 26          // Android 8: va bene anche per telefoni vecchi
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }
    buildTypes {
        release { isMinifyEnabled = false }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    val camerax = "1.4.1"
    implementation("androidx.camera:camera-core:$camerax")
    implementation("androidx.camera:camera-camera2:$camerax")
    implementation("androidx.camera:camera-lifecycle:$camerax")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-ktx:1.9.3")
    implementation("androidx.lifecycle:lifecycle-service:2.8.7")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
}
