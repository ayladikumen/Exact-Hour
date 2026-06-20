package com.exacthour.remote.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL

/**
 * Tiny HTTP client for the Exact Hour clock.
 *
 * Uses java.net.HttpURLConnection (no extra networking library) and org.json
 * (bundled with Android) so the app has almost no dependencies. Every call runs
 * on Dispatchers.IO and returns an [Outcome] instead of throwing, so the UI can
 * show "offline" cleanly rather than crash.
 */
class ExactHourClient(baseUrl: String) {

    private val base: String = normalize(baseUrl)

    sealed interface Outcome {
        data class Ok(val status: TimerStatus) : Outcome
        data class Error(val message: String) : Outcome
    }

    suspend fun status(): Outcome = request("GET", "/api/status", null)
    suspend fun toggle(): Outcome = request("POST", "/api/toggle", null)
    suspend fun reset(): Outcome = request("POST", "/api/reset", null)

    suspend fun adjust(deltaMinutes: Int): Outcome =
        request("POST", "/api/adjust", JSONObject().put("delta", deltaMinutes))

    suspend fun set(minutes: Int, seconds: Int = 0): Outcome =
        request("POST", "/api/set", JSONObject().put("minutes", minutes).put("seconds", seconds))

    private suspend fun request(method: String, path: String, body: JSONObject?): Outcome =
        withContext(Dispatchers.IO) {
            var conn: HttpURLConnection? = null
            try {
                conn = (URL(base + path).openConnection() as HttpURLConnection).apply {
                    requestMethod = method
                    connectTimeout = TIMEOUT_MS
                    readTimeout = TIMEOUT_MS
                    if (body != null) {
                        doOutput = true
                        setRequestProperty("Content-Type", "application/json")
                        outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
                    }
                }
                val code = conn.responseCode
                val stream = if (code in 200..299) conn.inputStream else conn.errorStream
                val text = stream?.let { s ->
                    BufferedReader(InputStreamReader(s, Charsets.UTF_8)).use(BufferedReader::readText)
                }.orEmpty()

                if (code in 200..299) {
                    Outcome.Ok(parse(JSONObject(text)))
                } else {
                    Outcome.Error("HTTP $code")
                }
            } catch (e: Exception) {
                Outcome.Error(e.message ?: "Connection failed")
            } finally {
                conn?.disconnect()
            }
        }

    private fun parse(o: JSONObject) = TimerStatus(
        state = o.optString("state", "IDLE"),
        minutes = o.optInt("minutes", 0),
        seconds = o.optInt("seconds", 0),
        remainingSeconds = o.optInt("remaining_seconds", 0),
        display = o.optString("display", "--:--"),
        maxMinutes = o.optInt("max_minutes", 270),
        name = o.optString("name", "Exact Hour"),
    )

    companion object {
        private const val TIMEOUT_MS = 3000

        /** Accept "192.168.1.5", "192.168.1.5:8080", or a full URL; return a clean base. */
        fun normalize(input: String): String {
            var b = input.trim()
            if (b.isEmpty()) return b
            if (!b.startsWith("http://") && !b.startsWith("https://")) b = "http://$b"
            return b.trimEnd('/')
        }
    }
}
