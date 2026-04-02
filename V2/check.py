import sounddevice as sd
import numpy as np
from pydub import AudioSegment

# Test 1: Play a sine wave
fs = 44100
duration = 3.0
t = np.linspace(0, duration, int(fs * duration), False)
audio = 0.5 * np.sin(2 * np.pi * 440 * t)  # 440Hz sine wave
print("Playing test tone...")
sd.play(audio, fs)
sd.wait()
print("Done.")

# Test 2: Play a real file
try:
    test_file = "C:/Users/T/Music/Salsa/_colleections/Salsa-2025-06/0 b Naiara - Me Las Quitas (Vídeo Oficial).m4a"  # Change to your file
    sound = AudioSegment.from_file(test_file)
    samples = np.array(sound.get_array_of_samples(), dtype=np.float32) / 32768.0
    print(f"Playing {test_file}...")
    sd.play(samples, sound.frame_rate)
    sd.wait()
except Exception as e:
    print(f"File test failed: {e}")
