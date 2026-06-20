package com.exacthour.remote.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.exacthour.remote.ui.theme.EhFinished
import com.exacthour.remote.ui.theme.EhMuted
import com.exacthour.remote.ui.theme.EhPaused
import com.exacthour.remote.ui.theme.EhRunning

@Composable
fun ExactHourApp(vm: ExactHourViewModel = viewModel()) {
    val ui by vm.ui.collectAsState()
    var showSettings by remember { mutableStateOf(false) }

    // On first launch (no clock saved yet) nudge the user to enter the address.
    LaunchedEffect(Unit) {
        if (!ui.configured) showSettings = true
    }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = { TopBar(ui = ui, onSettings = { showSettings = true }) },
    ) { inner ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(inner)
                .padding(horizontal = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.weight(1f))
            ClockFace(ui)
            Spacer(Modifier.weight(1f))
            Controls(
                ui = ui,
                onToggle = vm::toggle,
                onReset = vm::reset,
                onAdjust = vm::adjust,
                onPreset = vm::setMinutes,
            )
            Spacer(Modifier.height(16.dp))
        }
    }

    if (showSettings) {
        SettingsDialog(
            initialHost = ui.host,
            initialPort = ui.port,
            onDismiss = { showSettings = false },
            onSave = { host, port ->
                vm.connect(host, port)
                showSettings = false
            },
        )
    }
}

// -----------------------------------------------------------------------------
//  Top bar: wordmark + a tappable pill showing the connection (opens settings)
// -----------------------------------------------------------------------------
@Composable
private fun TopBar(ui: UiState, onSettings: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 20.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = "EXACT HOUR",
            color = MaterialTheme.colorScheme.onBackground,
            fontSize = 15.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = 3.sp,
        )
        Spacer(Modifier.weight(1f))
        ConnectionPill(ui = ui, onClick = onSettings)
    }
}

@Composable
private fun ConnectionPill(ui: UiState, onClick: () -> Unit) {
    val (dotColor, label) = when {
        !ui.configured -> EhMuted to "Set up clock"
        ui.connected -> EhRunning to ui.host
        else -> EhFinished to "offline"
    }
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(percent = 50),
        color = MaterialTheme.colorScheme.surface,
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 9.dp),
        ) {
            Box(Modifier.size(8.dp).clip(CircleShape).background(dotColor))
            Spacer(Modifier.width(8.dp))
            Text(
                text = label,
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 13.sp,
                maxLines = 1,
            )
        }
    }
}

// -----------------------------------------------------------------------------
//  Centre: state label + the big clock readout + status hint
// -----------------------------------------------------------------------------
@Composable
private fun ClockFace(ui: UiState) {
    val s = ui.status
    val display = if (ui.connected) s.display else "--:--"
    // "H:MM:SS" is 7 chars; shrink so it never overflows a narrow phone.
    val timeSize = if (display.length > 5) 58.sp else 86.sp

    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = stateLabel(s.state),
            color = stateColor(s.state),
            fontSize = 14.sp,
            fontWeight = FontWeight.SemiBold,
            letterSpacing = 5.sp,
        )
        Spacer(Modifier.height(14.dp))
        Text(
            text = display,
            color = MaterialTheme.colorScheme.onBackground,
            fontSize = timeSize,
            fontWeight = FontWeight.Bold,
            fontFamily = FontFamily.Monospace,
            maxLines = 1,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(12.dp))
        val hint = when {
            !ui.configured -> "Tap the address above to connect to your clock."
            !ui.connected -> "Can't reach the clock — check the IP and that it's powered on."
            else -> null
        }
        if (hint != null) {
            Text(
                text = hint,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 13.sp,
                textAlign = TextAlign.Center,
            )
        }
    }
}

// -----------------------------------------------------------------------------
//  Bottom: presets, +/- steppers, the big action button, and reset
// -----------------------------------------------------------------------------
@Composable
private fun Controls(
    ui: UiState,
    onToggle: () -> Unit,
    onReset: () -> Unit,
    onAdjust: (Int) -> Unit,
    onPreset: (Int) -> Unit,
) {
    val canEdit = ui.connected && ui.status.isEditable

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        listOf(5, 15, 25, 45).forEach { m ->
            PillButton(
                text = "${m}m",
                enabled = canEdit,
                modifier = Modifier.weight(1f),
                onClick = { onPreset(m) },
            )
        }
    }

    Spacer(Modifier.height(12.dp))

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        listOf(-5, -1, 1, 5).forEach { d ->
            PillButton(
                text = if (d > 0) "+$d" else "$d",
                enabled = canEdit,
                modifier = Modifier.weight(1f),
                onClick = { onAdjust(d) },
            )
        }
    }

    Spacer(Modifier.height(24.dp))

    val primaryLabel = when {
        ui.status.isRunning -> "PAUSE"
        ui.status.isPaused -> "RESUME"
        ui.status.isFinished -> "NEW"
        else -> "START"
    }
    Button(
        onClick = onToggle,
        enabled = ui.connected,
        shape = RoundedCornerShape(18.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = MaterialTheme.colorScheme.primary,
            contentColor = MaterialTheme.colorScheme.onPrimary,
        ),
        modifier = Modifier
            .fillMaxWidth()
            .height(64.dp),
    ) {
        Text(primaryLabel, fontSize = 18.sp, fontWeight = FontWeight.Bold, letterSpacing = 3.sp)
    }

    Spacer(Modifier.height(6.dp))

    TextButton(
        onClick = onReset,
        enabled = ui.connected && !ui.status.isIdle,
    ) {
        Text(
            "RESET",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 13.sp,
            letterSpacing = 2.sp,
        )
    }
}

@Composable
private fun PillButton(
    text: String,
    enabled: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    Surface(
        onClick = onClick,
        enabled = enabled,
        shape = RoundedCornerShape(percent = 50),
        color = MaterialTheme.colorScheme.surface,
        modifier = modifier.height(46.dp),
    ) {
        Box(
            contentAlignment = Alignment.Center,
            modifier = Modifier.fillMaxSize(),
        ) {
            Text(
                text = text,
                fontSize = 15.sp,
                fontWeight = FontWeight.Medium,
                color = if (enabled) MaterialTheme.colorScheme.onSurface
                        else MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

// -----------------------------------------------------------------------------
//  Settings dialog: enter the clock's IP and port
// -----------------------------------------------------------------------------
@Composable
private fun SettingsDialog(
    initialHost: String,
    initialPort: Int,
    onDismiss: () -> Unit,
    onSave: (String, Int) -> Unit,
) {
    var host by remember { mutableStateOf(initialHost) }
    var portText by remember { mutableStateOf(initialPort.toString()) }

    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = MaterialTheme.colorScheme.surface,
        title = { Text("Clock connection") },
        text = {
            Column {
                Text(
                    "Enter the local IP the clock prints on startup (it's on your Wi-Fi network).",
                    fontSize = 13.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(16.dp))
                OutlinedTextField(
                    value = host,
                    onValueChange = { host = it },
                    label = { Text("IP address") },
                    placeholder = { Text("192.168.1.50") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = portText,
                    onValueChange = { portText = it.filter(Char::isDigit).take(5) },
                    label = { Text("Port") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onSave(host.trim(), portText.toIntOrNull() ?: 8080) },
                enabled = host.isNotBlank(),
            ) { Text("Connect") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        },
    )
}

// -----------------------------------------------------------------------------
//  Small helpers
// -----------------------------------------------------------------------------
private fun stateLabel(state: String): String = when (state) {
    "RUNNING" -> "FOCUS"
    "PAUSED" -> "PAUSED"
    "FINISHED" -> "FINISHED"
    else -> "READY"
}

private fun stateColor(state: String): Color = when (state) {
    "RUNNING" -> EhRunning
    "PAUSED" -> EhPaused
    "FINISHED" -> EhFinished
    else -> EhMuted
}
