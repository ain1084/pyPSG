from __future__ import annotations
from collections import deque
from enum import Enum, auto
from abc import ABCMeta, abstractmethod
import pypsg


class Sequencer:
    class FormatError(Exception):
        pass

    class DataReader(metaclass=ABCMeta):
        @abstractmethod
        def get_byte(self, offset: int) -> int:
            pass

        @abstractmethod
        def get_short(self, offset: int) -> int:
            pass

        @property
        @abstractmethod
        def length(self) -> int:
            pass

    class _Header:
        def __init__(self, data_reader: Sequencer.DataReader):
            offset = 0
            title = []
            while True:
                ch = data_reader.get_byte(offset)
                if ch == 0:
                    break
                title.append(ch)
                offset += 1
            try:
                self._title = bytes(title).decode("utf8").replace("\n", " ")
            except Exception:
                raise Sequencer.FormatError
            data_offset = offset
            self._patch_table_offset = data_reader.get_short(offset + 2) + data_offset
            if self._patch_table_offset >= data_reader.length:
                raise Sequencer.FormatError
            self._channel_offsets = [
                self._adjust_part_offset(
                    data_offset,
                    data_reader.get_short(offset + 4 + index * 2),
                    data_reader.length,
                )
                for index in range(3)
            ]

        @property
        def envelope_table_offset(self) -> int:
            return self._patch_table_offset

        @property
        def channel_offsets(self) -> list[int]:
            return self._channel_offsets

        @property
        def title(self) -> str:
            return self._title

        @staticmethod
        def _adjust_part_offset(data_offset: int, part_offset: int, length: int) -> int:
            if part_offset == 0:
                return None
            adjusted = data_offset + part_offset
            if adjusted >= length:
                raise Sequencer.FormatError
            return adjusted

    class _Context:
        _tune_table = [
            3816,
            3602,
            3400,
            3209,
            3029,
            2859,
            2698,
            2547,
            2404,
            2269,
            2142,
            2022,
        ]

        def __init__(
            self,
            sample_generator: pypsg.SampleGenerator,
            data_reader: Sequencer.DataReader,
            patch_table_offset: int,
        ):
            self._sample_generator = sample_generator
            self._data_reader = data_reader
            self._patch_table_offset = patch_table_offset

        def get_byte(self, offset: int) -> int:
            return self._data_reader.get_byte(offset)

        def get_signed_short(self, offset: int) -> int:
            temp = self._data_reader.get_short(offset)
            return temp if temp < 32768 else temp - 65536

        def find_patch(
            self, target_patch_number: int
        ) -> tuple[int, int, int, int, int, int]:
            offset = self._patch_table_offset
            while True:
                patch_number = self.get_byte(offset)
                if patch_number == 0xFF:
                    return None
                elif target_patch_number == patch_number:
                    al = self.get_byte(offset + 1)
                    ar = self.get_byte(offset + 2)
                    dr = self.get_byte(offset + 3)
                    sl = self.get_byte(offset + 4)
                    sr = self.get_byte(offset + 5)
                    rr = self.get_byte(offset + 6)
                    return (al, ar, dr, sl, sr, rr)
                else:
                    offset += 7

        def get_tune_and_octave(self, note: int) -> tuple[int, int]:
            return (self._tune_table[note % 12], note // 12)

        def get_channel(self, channel_number: int) -> pypsg.SampleGenerator.ToneChannel:
            return self._sample_generator[channel_number]

        def set_noise_frequency(self, frequency: int):
            self._sample_generator.set_noise_frequency(frequency)

    class Part:
        class _LFO:
            def __init__(self, is_enable=False, delay=0, speed=0, depth=0, value=0):
                self._is_enable = is_enable
                self._delay = delay
                self._speed = speed
                self._depth = depth
                self._value = value
                self.reset()

            def set_enable(self, is_enable: bool):
                self._is_enable = is_enable
                self.reset()

            def reset(self):
                self._wait_count = self._delay
                self._depth_count = self._depth >> 1
                self._value_current = self._value
                self._current = 0

            def update(self) -> bool:
                if not self._is_enable:
                    return False
                self._wait_count -= 1
                if self._wait_count != 0:
                    return False
                self._wait_count = self._speed
                self._current += self._value_current
                self._depth_count -= 1
                if self._depth_count == 0:
                    self._depth_count = self._depth
                    self._value_current = -self._value_current
                return True

            @property
            def current(self) -> int:
                return self._current

        class _EnvelopeGenerator:
            class Phase(Enum):
                Attack = auto()
                Decay = auto()
                Sustain = auto()
                Release = auto()

            def __init__(self):
                self._current = 0
                self._al = 255
                self._ar = 255
                self._dr = 0
                self._sl = 0
                self._sr = 0
                self._rr = 255
                self._phase = self.Phase.Attack

            def set_parameter(self, parameter: tuple[int, int, int, int, int, int]):
                (self._al, self._ar, self._dr, self._sl, self._sr, self._rr) = parameter

            def attack(self):
                self._current = self._al
                self._phase = (
                    self.Phase.Attack if self._current != 255 else self.Phase.Decay
                )

            def release(self):
                self._phase = self.Phase.Release

            def update(self):
                current = self._current
                phase = self._phase
                if phase == self.Phase.Attack:
                    current += self._ar
                    if current > 255:
                        current = 255
                        phase = self.Phase.Decay
                elif phase == self.Phase.Decay:
                    current -= self._dr
                    if current < self._sl:
                        current = self._sl
                        phase = self.Phase.Sustain
                else:
                    if phase == self.Phase.Sustain:
                        current -= self._sr
                    else:
                        current -= self._rr
                    if current < 0:
                        current = 0
                self._current = current
                self._phase = phase

            @property
            def current(self) -> int:
                return self._current

        class _RepeatStack:
            class Item:
                def __init__(self, loop_count: int, start_offset: int):
                    self._count = loop_count
                    self._start_offset = start_offset
                    self._end_offset = None

                @property
                def start(self) -> int:
                    return self._start_offset

                @property
                def end(self) -> int | None:
                    return self._end_offset

                @end.setter
                def end(self, end: int):
                    self._end_offset = end

                @property
                def count(self) -> int:
                    return self._count

                def countDown(self) -> int:
                    self._count -= 1
                    return self._count

            def __init__(self):
                self.__deque = deque([self.Item])

            def start(self, loopCount, offset):
                self.__deque.appendleft(self.Item(loopCount, offset))

            def break_if_last(self, offset) -> int:
                data = self.__deque[0]
                if data.count == 1:
                    self.__deque.popleft()
                    offset = data.end
                return offset

            def end(self, offset) -> tuple[int, bool]:
                data = self.__deque[0]
                is_infinite_loop = data.count == 0
                if is_infinite_loop or data.countDown() != 0:
                    data.end = offset
                    offset = data.start
                else:
                    self.__deque.popleft()
                return (offset, is_infinite_loop)

        def __init__(
            self, context: Sequencer._Context, channel_number: int, offset: int
        ):
            self._context = context
            self._channel = context.get_channel(channel_number)
            self._next_offset = offset
            self._length_count = 1
            self._is_tie = False
            self._octave = 0
            self._volume = 0
            self._tune = 0
            self._detune = 0
            self._envelope = self._EnvelopeGenerator()
            self._repeat = self._RepeatStack()
            self._lfo = self._LFO()
            self._channel.set_tone_on(True)
            self._channel.set_noise_on(False)
            self._infinite_loop_count = 0

        def _next_byte(self) -> int:
            data = self._context.get_byte(self._next_offset)
            self._next_offset += 1
            return data

        def _get_byte(self) -> int:
            return self._context.get_byte(self._next_offset)

        def _next_signed_short(self) -> int:
            data = self._context.get_signed_short(self._next_offset)
            self._next_offset += 2
            return data

        def _update_tune(self):
            if self._lfo.update():
                self._apply_tune()

        def _apply_tune(self):
            self._channel.set_tune(min(max((self._tune + self._lfo.current + self._detune) >> self._octave, 0), 4095))

        def _update_volume(self):
            self._envelope.update()
            self._apply_volume()

        def _apply_volume(self):
            self._channel.set_volume((self._envelope.current * self._volume) >> 8)

        def tick(self):
            self._update_tune()
            self._length_count -= 1
            if self._length_count != 0:
                self._update_volume()
                return True
            else:
                if not self._is_tie:
                    self._envelope.release()
                self._update_volume()

            while True:
                data = self._next_byte()
                if data < 0x80:
                    self._length_count = data + 1
                    return True
                elif data < 0xE0:
                    (self._tune, self._octave) = self._context.get_tune_and_octave(
                        data - 0x80
                    )
                    if not self._is_tie:
                        self._envelope.attack()
                        self._lfo.reset()
                    self._length_count = self._next_byte()
                    if self._length_count == 0:
                        self._length_count = 256
                    if self._get_byte() == 0xE8:
                        self._is_tie = True
                        self._next_offset += 1
                    else:
                        self._is_tie = False
                    self._apply_tune()
                    self._apply_volume()
                    return True
                elif data == 0xE0:
                    envelope_parameter = self._context.find_patch(
                        target_patch_number=self._next_byte()
                    )
                    if envelope_parameter is not None:
                        self._envelope.set_parameter(envelope_parameter)
                elif data == 0xE1:
                    self._volume = self._next_byte()
                elif data == 0xE2:
                    count = self._next_byte()
                    self._repeat.start(count, self._next_offset)
                elif data == 0xE3:
                    self._next_offset = self._repeat.break_if_last(self._next_offset)
                elif data == 0xE4:
                    (self._next_offset, is_infinite_loop) = self._repeat.end(
                        self._next_offset
                    )
                    self._infinite_loop_count += 1 if is_infinite_loop else 0
                elif data == 0xE5:
                    self._context.set_noise_frequency(self._next_byte())
                elif data == 0xE6:
                    self._volume += 0 if self._volume == 15 else 1
                elif data == 0xE7:
                    self._volume -= 0 if self._volume == 0 else 1
                elif data == 0xE9:
                    self._detune = self._next_signed_short()
                elif data == 0xEA:
                    delay = self._next_byte()
                    speed = self._next_byte()
                    depth = self._next_byte()
                    value = self._next_signed_short()
                    self._lfo = self._LFO(
                        True, delay if delay != 0 else 256, speed, depth, value
                    )
                elif data == 0xEB:
                    self._lfo.set_enable(self._next_byte() != 0)
                elif data == 0xEC:
                    data = self._next_byte()
                    self._channel.set_tone_on((data & 0x1) != 0)
                    self._channel.set_noise_on((data & 0x2) != 0)
                elif data == 0xFF:
                    self._channel.set_volume(0)
                    return False

        @property
        def infinite_loop_count(self) -> int:
            return self._infinite_loop_count

    def __init__(self, sample_generator: pypsg.SampleGenerator, data_reader: DataReader):
        header = self._Header(data_reader)
        self._title = header.title
        context = self._Context(
            sample_generator, data_reader, header.envelope_table_offset
        )
        self._parts = [
            self.Part(context, channel_number, offset)
            for (channel_number, offset) in enumerate(header.channel_offsets)
            if offset is not None
        ]

    def tick(self):
        for (index, part) in enumerate(self._parts):
            if part is not None and not part.tick():
                self._parts[index] = None

    @property
    def loop_count(self) -> int:
        if None not in self._parts:
            return min(part.infinite_loop_count for part in self._parts if part is not None)
        else:
            return 0

    @property
    def title(self) -> str:
        return self._title

    @property
    def is_playing(self) -> bool:
        return None not in self._parts


class SequenceSampleBlockGenerator:
    DEFAULT_INTERVAL_RATIO_HZ = 59.94

    class _ElapseTime:
        def __init__(self, sampling_frequency_hz: int):
            self._sampling_frequency_hz = sampling_frequency_hz
            self._seconds = 0
            self._remain_samples = 0

        def update(self, size: int):
            (seconds, self._remain_samples) = divmod(
                self._remain_samples + size,
                self._sampling_frequency_hz,
            )
            self._seconds += seconds

        @property
        def time(self) -> float:
            return self._seconds + self._remain_samples / self._sampling_frequency_hz

    def __init__(
        self,
        sequencer: Sequencer,
        sample_generator: pypsg.SampleGenerator,
        interval_ratio_hz: float = None,
    ):
        interval_ratio_hz = (
            SequenceSampleBlockGenerator.DEFAULT_INTERVAL_RATIO_HZ
            if interval_ratio_hz is None
            else interval_ratio_hz
        )
        self._sample_generator = sample_generator
        self._sequencer = sequencer
        self._interval_ratio_100x_hz = int(interval_ratio_hz * 100)
        self._sample_count_error = 0
        self._sample_remain = 0

        self._elapseTime = self._ElapseTime(self._sample_generator.sampling_frequency_hz)

    @property
    def elapse_time(self) -> float:
        return self._elapseTime.time

    def next(self, block_size: int) -> list[float] | None:
        if block_size < 0:
            raise ValueError("block_size < 0")
        if not self._sequencer.is_playing:
            return None

        buffer = [0.0] * block_size
        block_remain = block_size
        sample_generator = self._sample_generator
        index = 0
        if self._sample_remain != 0:
            count = min(self._sample_remain, block_remain)
            buffer[:count] = [sample_generator.next_sample() for _ in range(count)]
            self._sample_remain -= count
            index = count
            block_remain -= count

        while block_remain != 0:
            self._sequencer.tick()
            (sample_count, self._sample_count_error) = divmod(
                self._sample_generator.sampling_frequency_hz * 100 + self._sample_count_error,
                self._interval_ratio_100x_hz,
            )
            count = min(block_remain, sample_count)
            buffer[index: index + count] = [
                sample_generator.next_sample() for _ in range(count)
            ]
            index += count
            block_remain -= count
            self._sample_remain = sample_count - count

        self._elapseTime.update(block_size)
        return buffer
