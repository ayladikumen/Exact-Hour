# Exact Hour - voice package (Pi side: microphone + Vosk speech-to-text).
#
# main.py does `import voice` and uses voice.VoiceListener. The import is guarded
# in main.py, so the clock still runs as a plain timer if this package or its
# optional deps (vosk, sounddevice) are absent. No AI runs here - recognized
# text is POSTed to the PC brain (pc_brain/), which does the understanding.

from .listener import VoiceListener, post_command

__all__ = ["VoiceListener", "post_command"]
