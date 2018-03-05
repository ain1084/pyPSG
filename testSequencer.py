import wave
import struct
import sys
import pyaudio
from fbdSequencer import Sequencer
from tinyPSG import SampleGenerator

# 48KHz
SamplingFrequency = 48000

# 1.789772MHz
PSGMasterClockHz = 1789772

# 59.94Hz
IntervalRatioMul100 = 5994


class FileSource(Sequencer.Source):
    __wordUnpack = struct.Struct('<h')

    def __init__(self, filename):
        with open(filename, 'rb') as f:
            self.__data = f.read()

    def readByte(self, offset):
        return self.__data[offset]

    def readWord(self, offset):
        return self.__wordUnpack.unpack(self.__data[offset:offset + 2])[0]

def sampleCountToTime(sampleCount):
    (sec, sampleMod)  = divmod(sampleCount, SamplingFrequency)
    min = int(sec / 60)
    hour = int(min / 60)
    millisec = int(sampleMod / SamplingFrequency * 1000)
    return (hour, min, sec, millisec)
        
samplingFrequencyMul100 = SamplingFrequency * 100

data = FileSource(sys.argv[1])
psg = SampleGenerator(PSGMasterClockHz, SamplingFrequency)
sequencer = Sequencer(psg, data)
print(sequencer.title)

pya = pyaudio.PyAudio()
stream = pya.open(format=pyaudio.paFloat32, channels=1, rate=SamplingFrequency, output=True)
sampleCountError = 0
totalSampleCount = 0
try:
    while sequencer.isPlaying:
        (hour, min, sec, millisec) = sampleCountToTime(totalSampleCount)
        print('%02d:%02d:%02d.%02d Loop:%d' % (hour, min, sec, int(millisec / 10), sequencer.loopCount), end='\r')
        sequencer.tick()
        (sampleCount, sampleCountError) = divmod(samplingFrequencyMul100 + sampleCountError, IntervalRatioMul100)
        stream.write(struct.pack(str(sampleCount) + 'f', *[psg.nextSample() for _ in range(sampleCount)]))
        totalSampleCount += sampleCount
        
        
except KeyboardInterrupt:
    pass
