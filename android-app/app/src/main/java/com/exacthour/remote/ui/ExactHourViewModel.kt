package com.exacthour.remote.ui

import android.app.Application
import android.content.Context
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.exacthour.remote.data.ExactHourClient
import com.exacthour.remote.data.TimerStatus
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/** Everything the UI needs to render, in one immutable object. */
data class UiState(
    val host: String = "",
    val port: Int = 8080,
    val configured: Boolean = false,   // has the user entered a clock address yet?
    val connected: Boolean = false,    // did the last request succeed?
    val error: String? = null,
    val status: TimerStatus = TimerStatus.EMPTY,
)

class ExactHourViewModel(app: Application) : AndroidViewModel(app) {

    private val prefs = app.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private val _ui = MutableStateFlow(UiState())
    val ui: StateFlow<UiState> = _ui.asStateFlow()

    private var client: ExactHourClient? = null
    private var pollJob: Job? = null
    private var commandJob: Job? = null
    private var consecutiveFailures = 0       // for debouncing the "offline" flip

    init {
        val host = prefs.getString(KEY_HOST, "").orEmpty()
        val port = prefs.getInt(KEY_PORT, 8080)
        _ui.value = _ui.value.copy(host = host, port = port, configured = host.isNotBlank())
        if (host.isNotBlank()) connect(host, port)
    }

    /** Save the clock address, (re)build the client, and (re)start polling. */
    fun connect(host: String, port: Int) {
        val h = host.trim()
        prefs.edit().putString(KEY_HOST, h).putInt(KEY_PORT, port).apply()
        // Stop talking to the old address before swapping the client, so an
        // in-flight poll/command can't land against the new host:port.
        pollJob?.cancel()
        commandJob?.cancel()
        client = if (h.isNotBlank()) ExactHourClient("$h:$port") else null
        consecutiveFailures = 0
        _ui.value = _ui.value.copy(
            host = h,
            port = port,
            configured = h.isNotBlank(),
            connected = false,
            error = null,
        )
        startPolling()
    }

    private fun startPolling() {
        pollJob?.cancel()
        val c = client ?: return
        pollJob = viewModelScope.launch {
            while (isActive) {
                applyOutcome(c.status())
                delay(POLL_MS)
            }
        }
    }

    /** Fire a command, then immediately reflect the returned status. A newer tap
     *  supersedes an in-flight one so rapid taps can't apply results out of order. */
    private fun send(block: suspend (ExactHourClient) -> ExactHourClient.Outcome) {
        val c = client ?: return
        commandJob?.cancel()
        commandJob = viewModelScope.launch { applyOutcome(block(c)) }
    }

    private fun applyOutcome(outcome: ExactHourClient.Outcome) {
        _ui.value = when (outcome) {
            is ExactHourClient.Outcome.Ok -> {
                consecutiveFailures = 0
                _ui.value.copy(status = outcome.status, connected = true, error = null)
            }
            is ExactHourClient.Outcome.Error -> {
                // Don't flap to "offline" on a single dropped poll (Wi-Fi hiccups
                // are common); only show disconnected after two misses in a row.
                consecutiveFailures++
                if (consecutiveFailures >= 2)
                    _ui.value.copy(connected = false, error = outcome.message)
                else
                    _ui.value
            }
        }
    }

    fun toggle() = send { it.toggle() }
    fun reset() = send { it.reset() }
    fun adjust(deltaMinutes: Int) = send { it.adjust(deltaMinutes) }
    fun setMinutes(minutes: Int) = send { it.set(minutes, 0) }

    companion object {
        private const val PREFS = "exact_hour"
        private const val KEY_HOST = "host"
        private const val KEY_PORT = "port"
        private const val POLL_MS = 500L
    }
}
