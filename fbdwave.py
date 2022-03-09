from __future__ import annotations
import struct
import sys
import wave

import fbd
import pypsg

PSG_MASTER_CLOCK_HZ = 1789772
SAMPLING_FREQUENCY_HZ = 48000
INTERVAL_RATIO_HZ = 59.94
BLOCK_SIZE = 512


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


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('usage: fbdwave.py <fbd filename> <wav filename>')
        sys.exit(0)

    data_reader = FileDataReader(sys.argv[1])
    with wave.open(sys.argv[2], "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLING_FREQUENCY_HZ)
        sample_generator = pypsg.SampleGenerator(PSG_MASTER_CLOCK_HZ, SAMPLING_FREQUENCY_HZ)
        sequencer = fbd.Sequencer(sample_generator, data_reader)
        generator = fbd.SequenceSampleBlockGenerator(
            sequencer, sample_generator, INTERVAL_RATIO_HZ
        )
        print(sequencer.title)
        while True:
            block = generator.next(BLOCK_SIZE)
            if not block or sequencer.loop_count != 0:
                break
            wf.writeframes(
                struct.pack("h" * len(block), *[int(value * 32767) for value in block])
            )
            print(".", end="", flush=True)
    print('')
