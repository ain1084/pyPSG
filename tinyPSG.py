class SampleGenerator:
    class MixingLookupTable:
        def __init__(self):
            # The following table generation was based on fmgen_008.lzh (Copyright (C) cisc 1997, 1999)
            # URL: http://retropc.net/cisc/sound/
            mul = 1 / pow(2, 1 / 4) ** 2
            self.__data = [1.0 / 3.0 * pow(mul, i) if i != 16 else 0 for i in range(16, 0, -1)]

        def __getitem__(self, index):
            return self.__data[index]

    class ToneChannel:
        class ToneGenerator:
            def __init__(self, masterFrequency, samplingFrequency):
                self.__masterFrequency = int(masterFrequency)
                self.__samplingFrequencyMul8 = int(samplingFrequency) << 3
                self.__error = self.__masterFrequency
                self.__tuneMin = int(self.__masterFrequency / self.__samplingFrequencyMul8) + 1
                self.__source = self.__tuneMin * self.__samplingFrequencyMul8
                self.__nextSource = self.__source
                self.__output = False

            def setTune(self, tune):
                if tune > 4095:
                    tune = 4095
                elif tune < self.__tuneMin:
                    tune = self.__tuneMin
                self.__nextSource = int(tune) * self.__samplingFrequencyMul8

            def update(self):
                self.__error -= self.__masterFrequency
                if self.__error < 0:
                    self.__error += self.__source
                    self.__output = ~self.__output & 0x1
                    self.__source = self.__nextSource
                return self.__output

        def __init__(self, masterFrequency, samplingFrequency):
            self.__volume = 0
            self.__isToneOn = True
            self.__isNoiseOn = False
            self.__toneGenerator = self.ToneGenerator(int(masterFrequency), int(samplingFrequency))

        def setMode(self, isToneOn, isNoiseOn):
            self.__isToneOn = bool(isToneOn)
            self.__isNoiseOn = bool(isNoiseOn)

        def setVolume(self, volume):
            self.__volume = int(volume)

        def setTune(self, tune):
            self.__toneGenerator.setTune(int(tune))

        def mixWithNoise(self, isNoise):
            return self.__volume if (self.__toneGenerator.update() & self.__isToneOn) or (isNoise & self.__isNoiseOn) else 0

    class NoiseGenerator:
        def __init__(self, masterFrequency, samplingFrequency):
            self.__masterFrequency = int(masterFrequency)
            self.__samplingFrequencyMul16 = int(samplingFrequency) << 4
            self.__error = self.__masterFrequency
            self.__tuneMin = int(self.__masterFrequency / self.__samplingFrequencyMul16) + 1
            self.__source = self.__tuneMin * self.__samplingFrequencyMul16
            self.__nextSource = self.__source
            self.__shift = 1
            self.__output = False

        def setTune(self, tune):
            if tune > 31:
                tune = 31
            elif tune < self.__tuneMin:
                tune = self.__tuneMin
            self.__nextSource = int(tune) * self.__samplingFrequencyMul16

        def update(self):
            self.__error -= self.__masterFrequency
            if self.__error < 0:
                self.__error += self.__source
                self.__shift = ((self.__shift >> 1) | ((self.__shift ^ (self.__shift >> 3)) << 15)) & 0xFFFF
                self.__output = self.__shift & 0x1
                self.__source = self.__nextSource
            return self.__output

    def __init__(self, masterFrequency, samplingFrequency):
        self.__noiseGenerator = self.NoiseGenerator(masterFrequency, samplingFrequency)
        self.__channels = [self.ToneChannel(masterFrequency, samplingFrequency) for ch in range(3)]
        self.__mixingLookupTable = self.MixingLookupTable()

    def __getitem__(self, channelNumber):
        return self.__channels[int(channelNumber)]

    def setNoiseFrequency(self, noiseFrequency):
        self.__noiseGenerator.setTune(noiseFrequency)

    def nextSample(self):
        isNoise = self.__noiseGenerator.update()
        return sum([self.__mixingLookupTable[channel.mixWithNoise(isNoise)] for channel in self.__channels])
