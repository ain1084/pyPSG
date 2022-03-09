import struct
import sounddevice as sd
import pypsg

# 48KHz
SamplingFrequency = 48000

# 1.789772MHz
PSGMasterClockHz = 1789772

PLAY_LENGTH = SamplingFrequency // 2

sample_generator = pypsg.SampleGenerator(PSGMasterClockHz, SamplingFrequency)
stream = sd.RawOutputStream(blocksize=PLAY_LENGTH, samplerate=SamplingFrequency, dtype="float32", channels=1)


def play():
    stream.start()
    stream.write(struct.pack(str(PLAY_LENGTH) + "f", *[sample_generator.next_sample() for _ in range(PLAY_LENGTH)]))
    stream.stop()


# create PSG sample generator

#        o3c  o3d  o3e  o3f  o3g  o3a  o3b  o4c
tunes = [855, 762, 679, 641, 571, 509, 453, 428]

noises = [0, 2, 4, 6, 8, 10, 12, 14]

channel = sample_generator

print('play o4c - o5c')
channel[0].set_tone_on(True)
channel[0].set_noise_on(False)
channel[0].set_volume(12)
for i in tunes:
    channel[0].set_tune(i // 2)
    play()

print('play noise')
channel[0].set_tone_on(False)
channel[0].set_noise_on(True)
for i in noises:
    sample_generator.set_noise_frequency(i)
    play()

print('play noise & tone')
channel[0].set_tone_on(True)
channel[0].set_noise_on(True)
sample_generator.set_noise_frequency(0)
for i in tunes:
    channel[0].set_tune(i // 2)
    play()

print('play o4c - o5c (dual/detune)')
channel[0].set_tone_on(True)
channel[0].set_noise_on(False)
channel[0].set_volume(12)
channel[1].set_tone_on(True)
channel[1].set_noise_on(False)
channel[1].set_volume(12)
for i in tunes:
    channel[0].set_tune(i // 2)
    channel[1].set_tune(i // 2 - 1)
    play()

print('play o4c - o5c (triple/detune)')
channel[0].set_tone_on(True)
channel[0].set_noise_on(False)
channel[0].set_volume(12)
channel[1].set_tone_on(True)
channel[1].set_noise_on(False)
channel[1].set_volume(12)
channel[2].set_tone_on(True)
channel[2].set_noise_on(False)
channel[2].set_volume(12)
for i in tunes:
    channel[0].set_tune(i // 2)
    channel[1].set_tune(i // 2 - 2)
    channel[2].set_tune(i // 2 + 2)
    play()
