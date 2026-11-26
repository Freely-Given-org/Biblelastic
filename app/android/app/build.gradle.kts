import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "org.freelygiven.biblelastic"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "org.freelygiven.biblelastic"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    // Release builds are signed with Freely-Given.org's key, as android/key.properties says (storeFile, storePassword, keyAlias, keyPassword).
    // That file isn't in git (nor is the key): without it, or without its passwords, a release build is signed with the debug key, which is only for testing.
    val keyProperties = Properties().apply {
        val file = rootProject.file("key.properties")
        if (file.exists()) file.inputStream().use { load(it) }
    }
    val releaseKey = !keyProperties.getProperty("storePassword").isNullOrBlank() && !keyProperties.getProperty("keyPassword").isNullOrBlank()
    signingConfigs {
        if (releaseKey) create("release") {
            storeFile = file(keyProperties.getProperty("storeFile"))
            storePassword = keyProperties.getProperty("storePassword")
            keyAlias = keyProperties.getProperty("keyAlias")
            keyPassword = keyProperties.getProperty("keyPassword")
        }
    }

    buildTypes {
        release {
            if (!releaseKey) logger.warn("Biblelastic: android/key.properties has no passwords, so this release build is signed with the debug key (for testing only)")
            signingConfig = signingConfigs.getByName(if (releaseKey) "release" else "debug")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
