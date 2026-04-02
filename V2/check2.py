import sounddevice as sd
import numpy as np
from pydub import AudioSegment

# Test 1: Play a 1-second tone at 44100Hz
fs = 44100
t = np.linspace(0, 1.0, fs, False)
audio = 0.3 * np.sin(2 * np.pi * 440 * t)
print("Playing 1s 440Hz tone at 44100Hz...")
sd.play(audio, fs)
sd.wait()

# Test 2: Play the same tone at 48000Hz (should sound slightly faster)
fs = 48000
t = np.linspace(0, 1.0, fs, False)
audio = 0.3 * np.sin(2 * np.pi * 440 * t)
print("Playing 1s 440Hz tone at 48000Hz (should be faster)...")
sd.play(audio, fs)
sd.wait()
