# Exact Hour - PC "brain" package.
# Runs on the main PC (the Ollama host), NOT on the Pi. It receives recognized
# speech text from the Pi, decides what the user meant (rules first, Ollama as a
# fallback), and dispatches the action to a pluggable backend (mock / the Pi
# clock API / Google Assistant). See README.md in this folder.
