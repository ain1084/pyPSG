class SampleGenerator:
    class MixingLookupTable:
        def __init__(self):
            volres = [
                1.0 / 15950, 1.0 / 15350, 1.0 / 15090, 1.0 / 14760,
                1.0 / 14275, 1.0 / 13620, 1.0 / 12890, 1.0 / 11370,
                1.0 / 10600, 1.0 / 8590, 1.0 / 7190, 1.0 / 5985,
                1.0 / 4820, 1.0 / 3945, 1.0 / 3017, 1.0 / 2345
            ]
            mixRegister = 1000
            mixRegisterUp = 800000
            mixRegisterDown = 8000000

            temp = [
                (3.0 / mixRegisterUp + i + j + k) / (3.0 / mixRegisterUp + 3.0 / mixRegisterDown + 1.0 / mixRegister + i + j + k)
                for k in volres for j in volres for i in volres
            ]
            minValue = min(10.0, min(temp))
            maxValue = max(0.0, max(temp))
            self.__data = [(data - minValue) / (maxValue - minValue) for data in temp]

        def __getitem__(self, index):
            return self.__data[index]

    class ToneChannel:
        class ToneGenerator:
            def __init__(self, masterFrequency, samplingFrequency):
                self.__masterFrequency = int(masterFrequency)
                self.__samplingFrequencyMul8 = int(samplingFrequency) << 3
                self.__nextSource = 0
                self.__error = 0
                self.__tuneMin = self.__masterFrequency / self.__samplingFrequencyMul8 + 1
                self.__source = self.__tuneMin * self.__samplingFrequencyMul8
                self.__update = False
                self.__output = False

            def setTune(self, tune):
                if tune > 4095:
                    tune = 4095
                elif tune < self.__tuneMin:
                    tune = self.__tuneMin
                self.__nextSource = int(tune) * self.__samplingFrequencyMul8
                self.__update = True

            def update(self):
                self.__error -= self.__masterFrequency
                if self.__error < 0:
                    self.__error += self.__source
                    self.__output = ~self.__output & 0x1
                    if self.__update:
                        self.__update = False
                        self.__source = self.__nextSource
                return self.__output

        def __init__(self, channelNumber, masterFrequency, samplingFrequency):
            self.__volumeIndex = 0
            self.__volumeShift = int(channelNumber) * 4
            self.__isToneOn = True
            self.__isNoiseOn = False
            self.__toneGenerator = self.ToneGenerator(int(masterFrequency), int(samplingFrequency))

        def setMode(self, isToneOn, isNoiseOn):
            self.__isToneOn = bool(isToneOn)
            self.__isNoiseOn = bool(isNoiseOn)

        def setVolume(self, volume):
            self.__volumeIndex = int(volume) << self.__volumeShift

        def setTune(self, tune):
            self.__toneGenerator.setTune(int(tune))

        def mixWithNoise(self, isNoise):
            return self.__volumeIndex if (self.__toneGenerator.update() & self.__isToneOn) or (isNoise & self.__isNoiseOn) else 0

    class NoiseGenerator:
        def __init__(self, masterFrequency, samplingFrequency):
            self.__masterFrequencyDiv1024 = int(masterFrequency) >> 10
            self.__samplingFrequencyDiv64 = int(samplingFrequency) >> 6
            self.__nextSource = 0
            self.__error = 0
            self.__source = 0
            self.__target = 0
            self.__shift = 1
            self.__update = False
            self.__output = False

        def setTune(self, tune):
            self.__nextSource = int(tune) * self.__samplingFrequencyDiv64
            self.__update = True

        def update(self):
            if self.__error > 0:
                self.__error -= self.__target
            if self.__error <= 0:
                self.__error += self.__source
                self.__output = self.__shift & 0x1
                self.__shift >>= 1
                if self.__output:
                    self.__shift ^= 0x911a
            if self.__update:
                self.__update = False
                self.__source = self.__nextSource
                self.__target = self.__masterFrequencyDiv1024
            return self.__output

    def __init__(self, masterFrequency, samplingFrequency):
        self.__noiseGenerator = self.NoiseGenerator(masterFrequency, samplingFrequency)
        self.__channels = [self.ToneChannel(ch, masterFrequency, samplingFrequency) for ch in range(3)]
        self.__mixingLookupTable = self.MixingLookupTable()

    def __getitem__(self, channelNumber):
        return self.__channels[int(channelNumber)]

    def setNoiseFrequency(self, noiseFrequency):
        self.__noiseGenerator.setTune(noiseFrequency)

    def nextSample(self):
        isNoise = self.__noiseGenerator.update()
        index = 0
        for channel in self.__channels:
            index |= channel.mixWithNoise(isNoise)
        return self.__mixingLookupTable[index]
