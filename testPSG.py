import wave
import struct
import TinyPSG
import sys
import pyaudio

# 48KHz
SamplingFrequency = 48000

# 1.789772MHz
PSGMasterClockHz = 1789772


def play(stream, psg):
	data = [int(psg.nextSample() * 32767) for i in range(int(SamplingFrequency / 2))]
	stream.write(struct.pack('h' * len(data), *data))

# prepare audio device
pya = pyaudio.PyAudio()
stream = pya.open(format=pya.get_format_from_width(2), channels=1, rate=SamplingFrequency, output=True)

# create PSG sample generator
psg = TinyPSG.SampleGenerator(PSGMasterClockHz, SamplingFrequency)

#        o3c  o3d  o3e  o3f  o3g  o3a  o3b  o4c
tunes = [855, 762, 679, 641, 571, 509, 453, 428]

noises = [ 0, 2, 4, 6, 8, 10, 12, 14]

#play o4c - o5c
psg[0].setMode(isToneOn=True, isNoiseOn=False)
psg[0].setVolume(12)
for i in tunes:
	psg[0].setTune(int(i / 2))
	play(stream, psg)

#play noise
psg[0].setMode(isToneOn=False, isNoiseOn=True)
for i in noises:
	psg.setNoiseFrequency(i)
	play(stream, psg)
	
#play o4c - o5c (dual/detune)
psg[0].setMode(isToneOn=True, isNoiseOn=False)
psg[0].setVolume(12)
psg[1].setMode(isToneOn=True, isNoiseOn=False)
psg[1].setVolume(12)
for i in tunes:
	psg[0].setTune(int(i / 2))
	psg[1].setTune(int(i / 2)-1)
	play(stream, psg)

#play o4c - o5c (triple/detune)
psg[0].setMode(isToneOn=True, isNoiseOn=False)
psg[0].setVolume(12)
psg[1].setMode(isToneOn=True, isNoiseOn=False)
psg[1].setVolume(12)
psg[0].setMode(isToneOn=True, isNoiseOn=False)
psg[0].setVolume(12)
psg[2].setMode(isToneOn=True, isNoiseOn=False)
psg[2].setVolume(12)
for i in tunes:
	psg[0].setTune(int(i / 2))
	psg[1].setTune(int(i / 2)-1)
	psg[2].setTune(int(i / 2)+1)
	play(stream, psg)
