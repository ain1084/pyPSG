from __future__ import annotations
import struct
import sys
import queue
import wave
import threading
import sounddevice as sd
import asyncio
import janus

import fbd
import pypsg

PSG_MASTER_CLOCK_HZ = 1789772
SAMPLING_FREQUENCY_HZ = 48000
INTERVAL_RATIO_HZ = 59.94
BUFFER_BLOCK_SIZE = 512
BUFFER_COUNT = 16


class FileDataReader(fbd.Sequencer.DataReader):
    def __init__(self, filename: str):
        with open(filename, "rb") as f:
            self._data = f.read()

    def get_byte(self, offset: int) -> int:
        return self._data[offset]

    def get_short(self, offset: int) -> int:
        return self._data[offset] | self._data[offset + 1] << 8

    @property
    def length(self) -> int:
        return len(self._data)


class Player:

    class LoopTime:
        def __init__(self):
            self._lock = threading.Lock()
            self._buffered_time = 0.0
            self._buffered_loop_count = 0
            self._output_time = 0.0
            self._output_loop_count = 0
            self._output_start_time = None

        def update_buffered(self, loop_count: int, elapse_time: float) -> None:
            with self._lock:
                if loop_count != self._buffered_loop_count:
                    self._buffered_loop_count = loop_count
                    self._buffered_time = elapse_time

        def update_output(self, outputTime: float) -> None:
            if not self._output_start_time:
                self._output_start_time = outputTime
            self._output_time = outputTime - self._output_start_time
            with self._lock:
                if self._output_time >= self._buffered_time:
                    self._output_loop_count = self._buffered_loop_count

        @property
        def output(self) -> tuple[float, int]:
            with self._lock:
                return (self._output_time, self._output_loop_count)

    def __init__(self, data_reader: fbd.Sequencer.DataReader, event_loop: asyncio.AbstractEventLoop):
        self._sample_queue = janus.Queue(BUFFER_COUNT)
        self._finished_callback = asyncio.Event()
        self._end_samples = threading.Event()
        self._event_loop = event_loop
        sample_generator = pypsg.SampleGenerator(PSG_MASTER_CLOCK_HZ, SAMPLING_FREQUENCY_HZ)
        self._sequencer = fbd.Sequencer(sample_generator, data_reader)
        self._sample_block_generator = fbd.SequenceSampleBlockGenerator(
            self._sequencer, sample_generator, INTERVAL_RATIO_HZ
        )
        self._loop_time = self.LoopTime()

        print(self._sequencer.title)
        for _ in range(self._sample_queue.maxsize):
            data = self._sample_block_generator.next(BUFFER_BLOCK_SIZE)
            if not data:
                self._end_samples.set()
                break
            self._sample_queue.async_q.put_nowait(data)

    async def within_stream(self):
        with sd.RawOutputStream(
            samplerate=SAMPLING_FREQUENCY_HZ,
            blocksize=BUFFER_BLOCK_SIZE,
            channels=1,
            dtype="float32",
            callback=lambda outdata, _, time, status: self._callback(
                outdata, time, status
            ),
            finished_callback=lambda: (self._event_loop.call_soon_threadsafe(self._finished_callback.set), None)[1]
        ):
            await self._finished_callback.wait()

    async def fill_samples(self):
        while True:
            data = self._sample_block_generator.next(BUFFER_BLOCK_SIZE)
            if not data:
                self._end_samples.set()
                break
            else:
                await self._sample_queue.async_q.put(data)
            self._loop_time.update_buffered(self._sequencer.loop_count, self._sample_block_generator.elapse_time)
            (time, loop_count) = self._loop_time.output
            Player._print_time_counter(time, loop_count)

    def _callback(self, outdata, time, status):
        self._loop_time.update_output(time.outputBufferDacTime)
        if status.output_underflow:
            print("Output underflow")
            raise sd.CallbackAbort
        try:
            data = self._sample_queue.sync_q.get_nowait()
        except queue.Empty as e:
            if self._end_samples.is_set:
                raise sd.CallbackStop
            else:
                print("Buffer is empty")
                raise sd.CallbackAbort from e
        outdata[:] = struct.pack("f" * len(data), *data)

    @staticmethod
    def _print_time_counter(time: float, loop_count: int):
        print(
            "%02d:%02d:%02d.%02d Loop:%d"
            % (
                time // 3600,
                (time % 3600) // 60,
                int(time % 60),
                int(time * 100) % 100,
                loop_count,
            ),
            end="\r", flush=True
        )

async def main() -> None:
    data_reader = FileDataReader(sys.argv[1])
    # test_write(data_reader)
    player = Player(data_reader, asyncio.get_running_loop())
    await asyncio.gather(player.within_stream(), player.fill_samples())

try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
finally:
    print('')
