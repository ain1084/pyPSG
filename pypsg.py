class SampleGenerator:
    DEFAULT_SAMPLING_FREQUENCY_HZ = 48000
    DEFAULT_MASTER_FREQUENCY_HZ = 1789772

    class _MixingLookupTable:
        def __init__(self):
            # The following table generation was based on fmgen_008.lzh (Copyright (C) cisc 1997, 1999)
            # URL: http://retropc.net/cisc/sound/
            mul = 1 / pow(2, 1 / 4) ** 2
            self._data = [
                1.0 / 3.0 * pow(mul, i) if i != 16 else 0 for i in range(16, 0, -1)
            ]

        def __getitem__(self, index: int) -> float:
            return self._data[index]

    class ToneChannel:
        class _ToneGenerator:
            def __init__(self, master_frequency_hz: int, sampling_frequency_hz: int):
                self._master_frequency_hz = master_frequency_hz
                self._sampling_frequency_8x_hz = sampling_frequency_hz * 8
                self._error = self._master_frequency_hz
                self._tune_min = self._master_frequency_hz // self._sampling_frequency_8x_hz + 1
                self._source = self._tune_min * self._sampling_frequency_8x_hz
                self._next_source = self._source
                self._output = False

            def set_tune(self, tune: int):
                if tune < 0 or tune > 4095:
                    raise ValueError('tune >= 0 and tune < 4096')
                if tune < self._tune_min:
                    tune = self._tune_min
                self._next_source = tune * self._sampling_frequency_8x_hz

            def update(self) -> bool:
                self._error -= self._master_frequency_hz
                if self._error < 0:
                    self._error += self._source
                    self._output = not self._output
                    self._source = self._next_source
                return self._output

        def __init__(self, master_frequency_hz: int, sampling_frequency_hz: int):
            self._volume = 0
            self._is_tone_on = True
            self._is_noise_on = False
            self._tone_generator = self._ToneGenerator(master_frequency_hz, sampling_frequency_hz)

        @property
        def is_tone_on(self):
            return self._is_tone_on

        def set_tone_on(self, is_on: bool):
            self._is_tone_on = is_on

        def set_noise_on(self, is_on: bool):
            self._is_noise_on = is_on

        def set_volume(self, value: int):
            if value < 0 or value > 15:
                raise ValueError('volume >= 0 and volume < 16')
            self._volume = value

        def set_tune(self, tune: int):
            self._tone_generator.set_tune(tune)

        def mix_with_noise(self, isNoise: bool) -> int:
            return (
                self._volume
                if (self._tone_generator.update() & self._is_tone_on) or (isNoise & self._is_noise_on) else 0
            )

    class _NoiseGenerator:
        def __init__(self, master_frequency_hz: int, sampling_frequency_hz: int):
            self._master_frequency_hz = master_frequency_hz
            self._sampling_frequency_16x_hz = sampling_frequency_hz * 16
            self._error = self._master_frequency_hz
            self._tune_min = (
                self._master_frequency_hz // self._sampling_frequency_16x_hz
            )
            self._source = (self._tune_min + 1) * self._sampling_frequency_16x_hz
            self._next_source = self._source
            self._shift = 1

        def set_frequency(self, frequency: int):
            if frequency < 0 or frequency > 31:
                raise ValueError('frequency >= 0 and frequency < 32')
            if frequency < self._tune_min:
                frequency = self._tune_min
            self._next_source = (frequency + 1) * self._sampling_frequency_16x_hz

        def update(self) -> bool:
            self._error -= self._master_frequency_hz
            if self._error < 0:
                self._error += self._source
                self._shift = (
                    (self._shift >> 1) | ((self._shift ^ (self._shift >> 3)) << 15)
                ) & 0xFFFF
                self._source = self._next_source
            return self._shift & 1

    def __init__(self, master_frequency_hz: int = None, sampling_frequency_hz: int = None):
        master_frequency_hz = self.DEFAULT_MASTER_FREQUENCY_HZ if master_frequency_hz is None else master_frequency_hz
        sampling_frequency_hz = self.DEFAULT_SAMPLING_FREQUENCY_HZ if sampling_frequency_hz is None else sampling_frequency_hz
        self._sampling_frequency_hz = self.DEFAULT_SAMPLING_FREQUENCY_HZ if sampling_frequency_hz is None else sampling_frequency_hz
        self._noise_generator = self._NoiseGenerator(master_frequency_hz, sampling_frequency_hz)
        self._channels = [
            self.ToneChannel(master_frequency_hz, sampling_frequency_hz) for ch in range(3)
        ]
        self._mixing_lookup_table = self._MixingLookupTable()

    def __getitem__(self, channel_number: int) -> ToneChannel:
        return self._channels[channel_number]

    def set_noise_frequency(self, frequency: int):
        self._noise_generator.set_frequency(frequency)

    @property
    def sampling_frequency_hz(self) -> int:
        return self._sampling_frequency_hz

    def next_sample(self) -> float:
        is_noise = self._noise_generator.update()
        return sum(
            [
                self._mixing_lookup_table[channel.mix_with_noise(is_noise)]
                for channel in self._channels
            ]
        )
