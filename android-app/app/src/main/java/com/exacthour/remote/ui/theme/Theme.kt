package com.exacthour.remote.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Minimalist "instrument" palette: near-black canvas, warm amber accent that
// echoes the LED matrix, one green/amber/red for the timer states.
val EhBackground = Color(0xFF0B0B0D)
val EhSurface = Color(0xFF16161A)
val EhSurfaceVariant = Color(0xFF24242B)
val EhAccent = Color(0xFFFFB020)
val EhOnAccent = Color(0xFF1A1206)
val EhOnDark = Color(0xFFEDEDED)
val EhMuted = Color(0xFF8A8A93)
val EhOutline = Color(0xFF3A3A42)

val EhRunning = Color(0xFF4ADE80)
val EhPaused = Color(0xFFFFB020)
val EhFinished = Color(0xFFFF6B3D)

private val EhColors = darkColorScheme(
    primary = EhAccent,
    onPrimary = EhOnAccent,
    secondary = EhAccent,
    onSecondary = EhOnAccent,
    background = EhBackground,
    onBackground = EhOnDark,
    surface = EhSurface,
    onSurface = EhOnDark,
    surfaceVariant = EhSurfaceVariant,
    onSurfaceVariant = EhMuted,
    outline = EhOutline,
    error = EhFinished,
)

@Composable
fun ExactHourTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = EhColors,
        typography = Typography(),
        content = content,
    )
}
