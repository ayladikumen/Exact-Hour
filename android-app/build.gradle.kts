// Top-level build file. Plugin versions are declared here (apply false) and the
// modules below opt in. Keeping versions in one place avoids mismatches.
plugins {
    id("com.android.application") version "8.5.2" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
    // Kotlin 2.0 moved the Compose compiler into this plugin; its version MUST
    // match the Kotlin version above.
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.21" apply false
}
