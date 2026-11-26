import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import java.nio.file.Files
import java.nio.file.attribute.PosixFilePermission
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

fun privateFile(file: File) {
    val allowed = setOf(PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE)
    require(Files.getPosixFilePermissions(file.toPath()).all(allowed::contains)) {
        "Signing inputs must be owner-only"
    }
}

fun environment(name: String) = providers.environmentVariable(name).orNull.orEmpty()

val signing = environment("JARVIS_ANDROID_SIGNING_CONFIG").takeIf(String::isNotBlank)?.let { path ->
    val config = file(path)
    privateFile(config)
    Properties().apply { config.inputStream().use(::load) }
}
val releaseCode = providers.gradleProperty("jarvis.versionCode").orNull?.toInt()
val releaseName = providers.gradleProperty("jarvis.versionName").orNull
val oauthClient = environment("JARVIS_OAUTH_CLIENT_ID")
val firebase = mapOf(
    "google_app_id" to environment("JARVIS_FIREBASE_APPLICATION_ID"),
    "google_api_key" to environment("JARVIS_FIREBASE_API_KEY"),
    "project_id" to environment("JARVIS_FIREBASE_PROJECT_ID"),
    "gcm_defaultSenderId" to environment("JARVIS_FIREBASE_SENDER_ID"),
)

gradle.taskGraph.whenReady {
    if (allTasks.any { it.project == project && it.name.contains("Release") }) {
        require(signing != null && releaseCode != null && releaseCode in 1..2_100_000_000 && !releaseName.isNullOrBlank()) {
            "Release builds require JARVIS_ANDROID_SIGNING_CONFIG, jarvis.versionName and a positive jarvis.versionCode"
        }
        require(oauthClient.isNotBlank() && firebase.values.none(String::isBlank)) {
            "Release builds require the public Cloudflare OAuth client and Firebase Android project settings"
        }
    }
}

android {
    namespace = "dev.niels.jarvis"
    compileSdk { version = release(36) { minorApiLevel = 1 } }

    defaultConfig {
        applicationId = "dev.niels.jarvis"
        minSdk = 33
        targetSdk = 36
        versionCode = releaseCode ?: 1
        versionName = releaseName ?: "0.1.0"
        manifestPlaceholders["jarvisHost"] = "jarvis.nielseriknandal.com"
        require(oauthClient.matches(Regex("[A-Za-z0-9._~-]*"))) { "Invalid OAuth client id" }
        buildConfigField("String", "JARVIS_ORIGIN", "\"https://${manifestPlaceholders.getValue("jarvisHost")}\"")
        buildConfigField("String", "JARVIS_OAUTH_CLIENT_ID", "\"$oauthClient\"")
        firebase.filterValues(String::isNotBlank).forEach { (key, value) ->
            resValue("string", key, value)
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
        resValues = true
    }

    signing?.let { config ->
        val key = file(config.getProperty("storeFile"))
        val passwordFile = file(config.getProperty("passwordFile"))
        privateFile(key)
        privateFile(passwordFile)
        val password = passwordFile.readLines().single()
        signingConfigs.create("privateRelease") {
            storeFile = key
            storePassword = password
            keyAlias = config.getProperty("keyAlias")
            keyPassword = password
            storeType = "PKCS12"
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.findByName("privateRelease")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin {
    compilerOptions.jvmTarget.set(JvmTarget.JVM_17)
}

dependencies {
    implementation("org.commonmark:commonmark:0.33.0")
    implementation("org.commonmark:commonmark-ext-gfm-tables:0.33.0")
    implementation(platform("androidx.compose:compose-bom:2026.06.00"))
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.browser:browser:1.9.0")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.core:core:1.17.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.10.0")
    implementation("androidx.pdf:pdf-document-service:1.0.0-beta01")
    implementation("com.google.firebase:firebase-messaging:26.0.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("net.openid:appauth:0.11.1")
}
