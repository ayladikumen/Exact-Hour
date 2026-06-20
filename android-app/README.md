# Exact Hour — Android Remote

A minimalist Android app that controls the **Exact Hour** clock over your local
Wi-Fi network. No cloud, no account — the phone talks straight to the clock's IP.

<p align="center"><i>READY · 25:00 · big amber readout · one tap to start</i></p>

---

## What it does

* Live time readout that mirrors the LED matrix (`MM:SS` or `H:MM:SS`, and `BITTI`
  when finished), polled a couple of times a second.
* One big context-aware button: **START → PAUSE → RESUME** (and **NEW** after a
  session finishes) — the same behaviour as the clock's physical button.
* **Presets** (5 / 15 / 25 / 45 min) and **± steppers** to set the duration.
  These are disabled while the timer is running, exactly like the hardware.
* **RESET** back to the default time.
* Connection status pill — tap it any time to change the clock's IP / port.

The design is intentionally bare: near-black canvas, a single amber accent that
echoes the LED, monospace digits. It matches the device's "see the time, nothing
else" philosophy.

---

## How it connects

The clock (`main.py` on the Raspberry Pi) runs a tiny HTTP server
(`remote_control.py`). On startup it prints:

```
Exact Hour remote control is live at http://192.168.1.50:8080
Type that address into the Exact Hour Android app.
```

Enter that IP and port (default **8080**) in the app's setup dialog. The phone
and the clock must be on the **same Wi-Fi network**.

### The API (for reference)

| Method | Path           | Body                       | Effect                         |
|--------|----------------|----------------------------|--------------------------------|
| GET    | `/api/status`  | —                          | current state snapshot (JSON)  |
| POST   | `/api/toggle`  | —                          | start / pause / resume / new   |
| POST   | `/api/reset`   | —                          | reset to the default time      |
| POST   | `/api/adjust`  | `{"delta": 5}`             | ± minutes (idle/paused only)   |
| POST   | `/api/set`     | `{"minutes":25,"seconds":0}` | set absolute (idle/paused only) |

Status JSON:

```json
{ "state": "IDLE", "minutes": 5, "seconds": 0, "remaining_seconds": 300,
  "display": "05:00", "max_minutes": 270, "name": "Exact Hour" }
```

---

## Building

This is a standard **Android Studio** project (Kotlin + Jetpack Compose).

1. Open the `android-app/` folder in **Android Studio** (Koala / 2024.1+).
2. Let it sync — Android Studio downloads the right Gradle and SDK automatically.
3. Run on a device or emulator (**Build ▸ Build APK** for an installable `.apk`).

**Stack:** Kotlin 2.0.21 · AGP 8.5.2 · Gradle 8.9 · Compose BOM 2024.09 ·
minSdk 26 (Android 8) · targetSdk 34.

> **Command-line note:** the binary `gradle/wrapper/gradle-wrapper.jar` is *not*
> committed (it can't be shipped as text). Android Studio doesn't need it. If you
> want to build from the terminal with `./gradlew`, generate the wrapper once with
> a system Gradle ≥ 8.9:
>
> ```bash
> gradle wrapper --gradle-version 8.9
> ./gradlew assembleDebug
> ```

---

## Notes

* The app uses **cleartext HTTP** (`usesCleartextTraffic="true"`) because the clock
  serves plain HTTP on the LAN — there's no TLS on the device. This is fine for a
  local-only tool; don't point it at the public internet.
* Networking is dependency-light on purpose: `HttpURLConnection` + the bundled
  `org.json`, no Retrofit/OkHttp.
