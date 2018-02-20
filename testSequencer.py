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

samplingFrequencyMul100 = SamplingFrequency * 100

data = FileSource(sys.argv[1])
psg = SampleGenerator(PSGMasterClockHz, SamplingFrequency)
sequencer = Sequencer(psg, data)
print(sequencer.title)

pya = pyaudio.PyAudio()
stream = pya.open(format=pya.get_format_from_width(2), channels=1, rate=SamplingFrequency, output=True)
sampleCountError = 0
try:
    while sequencer.isPlaying:
        sequencer.tick()
        (sampleCount, sampleCountError) = divmod(samplingFrequencyMul100 + sampleCountError, IntervalRatioMul100)
        data = [int(psg.nextSample() * 32767) for i in range(sampleCount)]
        stream.write(struct.pack('h' * len(data), *data))
except KeyboardInterrupt:
    pass
