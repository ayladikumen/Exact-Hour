package com.exacthour.remote.data

/**
 * An immutable snapshot of the clock, parsed from GET /api/status.
 * Field names mirror the JSON the Pi sends (see remote_control.py / main.py).
 */
data class TimerStatus(
    val state: String,            // IDLE | RUNNING | PAUSED | FINISHED
    val minutes: Int,
    val seconds: Int,
    val remainingSeconds: Int,
    val display: String,          // e.g. "05:00", "1:30:00", or "BITTI"
    val maxMinutes: Int,
    val name: String,
) {
    val isIdle get() = state == "IDLE"
    val isRunning get() = state == "RUNNING"
    val isPaused get() = state == "PAUSED"
    val isFinished get() = state == "FINISHED"

    /** Adjusting the time is only allowed when not actively counting. */
    val isEditable get() = isIdle || isPaused

    companion object {
        val EMPTY = TimerStatus(
            state = "IDLE",
            minutes = 0,
            seconds = 0,
            remainingSeconds = 0,
            display = "--:--",
            maxMinutes = 270,
            name = "Exact Hour",
        )
    }
}
