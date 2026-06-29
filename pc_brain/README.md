# Exact Hour - PC Brain

The "brain" runs on your **main PC** (the Ollama host). It receives recognized
speech text from the Pi, decides what you meant, and performs the action.

```
[Pi] mic -> Vosk STT -> text  --HTTP POST /command-->  [PC] brain_server
                                                          |
                              router (rules first, Ollama fallback)
                                                          |
                                              ActionBackend (per domain)
                                   home  -> mock | google_assistant
                                   timer -> mock | exact_hour (the Pi clock API)
```

Speech-to-text is on the Pi; **the AI is here**. It is intentionally lean (a
keyword router + a small local model), not a general chatbot.

## Run it

1. **Install Ollama** (https://ollama.com) and pull a small model:
   ```
   ollama pull llama3.2:3b      # or llama3.2:1b on a 4 GB RAM PC
   ```
   Ollama is only consulted when the keyword rules are unsure; clear commands
   ("turn on the light", "set 20 minutes") never touch it.
2. **Configure:** copy `config.example.json` to `config.json` and edit
   (`pi_clock_url`, `ollama_model`, which `backends` to use). `config.json` is
   gitignored. Anything you omit falls back to the defaults in `config.py`.
3. **Start the brain** (from the repo root or this folder):
   ```
   py pc_brain/brain_server.py
   ```
4. **Try it without a Pi or mic** - POST text by hand:
   ```
   curl -X POST http://localhost:8090/command -H "Content-Type: application/json" -d "{\"text\":\"turn on the light\"}"
   ```

## Backends (the swappable executor)

Set per-domain in `config.json` under `"backends"`:

| name               | domain | what it does                                            |
|--------------------|--------|---------------------------------------------------------|
| `mock`             | any    | prints what it *would* do (default - needs nothing)     |
| `exact_hour`       | timer  | calls the Pi clock's HTTP API (`remote_control.py`)     |
| `google_assistant` | home   | speaks the command to Google Assistant via a relay      |

> **Google Assistant note:** the relay it uses (`assistant-relay`) is archived
> and rides the deprecated Assistant SDK (Assistant retires ~March 2026). It
> works "for now"; when it stops, write one new backend file (e.g. Home
> Assistant or direct bulb APIs) and nothing else changes. See
> `actions/google_assistant.py`.

## Tests (PC-only, no Ollama/Pi/mic)

```
py dev/test_voice_router.py      # rules + routing + dispatch
py dev/test_voice_listener.py    # the Pi -> brain HTTP contract
```
