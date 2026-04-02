import sounddevice as sd
import numpy as np
import time

print('sd.default.device:', sd.default.device)
print('sd.default.samplerate:', sd.default.samplerate)

try:
    dev = sd.default.device
    if dev is not None:
        try:
            info = sd.query_devices(dev)
            print('default device info:', info)
        except Exception as e:
            print('Could not query default device:', e)
except Exception as e:
    print('Error querying default device:', e)

print('\nAll devices summary:')
try:
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        print(i, d.get('name'), 'out_ch=', d.get('max_output_channels'))
except Exception as e:
    print('Could not list devices:', e)

# Play a 1s test tone at 440Hz on default device
fs = 44100
t = np.linspace(0, 1, int(fs), False)
tone = (0.2 * np.sin(2 * np.pi * 440 * t)).astype('float32')
try:
    print('\nAttempting to play a 1s 440Hz tone on default device...')
    sd.play(tone, fs)
    sd.wait()
    print('Played tone (no error).')
except Exception as e:
    print('Playback failed:', e)
