# Exact Hour - action backends.
#
# Each backend implements ActionBackend.execute(intent) and is responsible for
# ACTUALLY DOING the thing an Intent describes. They are interchangeable so the
# "executor" can be swapped without touching the Pi STT or the router/brain:
#
#   mock             - prints what it WOULD do (default; needs nothing)
#   exact_hour       - drives the Pi countdown clock via its HTTP API
#   google_assistant - speaks the command to Google Assistant (smart home)
#
# make_backend(name, config) builds one by name (see config.py).
