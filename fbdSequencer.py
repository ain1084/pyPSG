from collections import deque
from enum import Enum, auto
from abc import ABCMeta, abstractmethod

class Sequencer:
    class Source(metaclass=ABCMeta):
        @abstractmethod
        def readByte(self, offset):
            pass

        @abstractmethod
        def readWord(self, offset):
            pass

    class Header:
        def __init__(self, sequenceData):
            offset = 0
            title = []
            while True:
                ch = sequenceData.readByte(offset)
                if ch == 0:
                    break
                offset += 1
                title.append(ch)
            self._title = bytes(title).decode("utf8").replace("\n", " ")
            dataOffset = offset
            self.__envelopTable = sequenceData.readWord(offset + 2) + dataOffset
            self.__channels = [
                self.__getPartOffset(dataOffset, sequenceData.readWord(offset + 4 + index * 2))
                for index in range(3)]
            
        @property
        def envelopeTable(self):
            return self.__envelopTable

        @property
        def channels(self):
            return self.__channels

        @property
        def title(self):
            return self._title
            
        @staticmethod
        def __getPartOffset(dataOffset, partOffset):
            return dataOffset + partOffset if partOffset != 0 else None

    class Context:
        _tuneTable = [3816, 3602, 3400, 3209, 3029, 2859, 2698, 2547, 2404, 2269, 2142, 2022]

        def __init__(self, psg, sequenceData, envelopeTableOffset):
            self.__psg = psg
            self.__sequenceData = sequenceData
            self.__envelopeTableOffset = envelopeTableOffset

        def readByte(self, offset):
            return self.__sequenceData.readByte(offset)

        def readWord(self, offset):
            return self.__sequenceData.readWord(offset)

        def findEnvelope(self, targetToneNumber):
            offset = self.__envelopeTableOffset
            data = self.__sequenceData
            while True:
                toneNumber = data.readByte(offset)
                if toneNumber == 0xff:
                    return None
                elif targetToneNumber == toneNumber:
                    al = data.readByte(offset + 1)
                    ar = data.readByte(offset + 2)
                    dr = data.readByte(offset + 3)
                    sl = data.readByte(offset + 4)
                    sr = data.readByte(offset + 5)
                    rr = data.readByte(offset + 6)
                    return (al, ar, dr, sl, sr, rr)
                else:
                    offset += 7

        def getTuneAndOctave(self, note):
            return (Sequencer.Context._tuneTable[note % 12], note / 12)

        def getChannel(self, channelNumber):
            return self.__psg[channelNumber]

        def setNoiseFrequency(self, frequency):
            self.__psg.setNoiseFrequency(frequency)

    class Part:
        class LFO:
            def __init__(self, isEnable=False, delay=0, speed=0, depth=0, value=0):
                self.__isEnable = isEnable
                self.__delay = delay
                self.__speed = speed
                self.__depth = depth
                self.__value = value
                self.reset()

            def setEnable(self, isEnable):
                self.__isEnable = isEnable
                self.reset()

            def reset(self):
                self.__waitCount = self.__delay
                self.__depthCount = self.__depth >> 1
                self.__valueCurrent = self.__value
                self.__current = 0

            def update(self):
                if not self.__isEnable:
                    return False
                self.__waitCount -= 1
                if self.__waitCount != 0:
                    return False
                self.__waitCount = self.__speed
                self.__current += self.__valueCurrent
                self.__depthCount -= 1
                if self.__depthCount == 0:
                    self.__depthCount = self.__depth
                    self.__valueCurrent = -self.__valueCurrent
                return True

            @property
            def current(self):
                return self.__current

        class EnvelopeGenerator:
            class Phase(Enum):
                Attack = auto()
                Decay = auto()
                Sustain = auto()
                Release = auto()

            def __init__(self):
                self.__current = 0
                self.__al = 255
                self.__ar = 255
                self.__dr = 0
                self.__sl = 0
                self.__sr = 0
                self.__rr = 255
                self.__phase = self.Phase.Attack

            def setData(self, parameter):
                (self.__al, self.__ar, self.__dr, self.__sl, self.__sr, self.__rr) = parameter

            def attack(self):
                self.__current = self.__al
                self.__phase = self.Phase.Attack if self.__current != 255 else self.Phase.Decay

            def release(self):
                self.__phase = self.Phase.Release

            def update(self):
                current = self.__current
                phase = self.__phase
                if phase == self.Phase.Attack:
                    current += self.__ar
                    if current > 255:
                        current = 255
                        phase = self.Phase.Decay
                elif phase == self.Phase.Decay:
                    current -= self.__dr
                    if current < self.__sl:
                        current = self.__sl
                        phase = self.Phase.Sustain
                else:
                    if phase == self.Phase.Sustain:
                        current -= self.__sr
                    else:
                        current -= self.__rr
                    if current < 0:
                        current = 0
                self.__current = current
                self.__phase = phase

            @property
            def current(self):
                return self.__current

        class RepeatStack:
            class Data:
                def __init__(self, loopCount, startOffset):
                    self.__count = loopCount
                    self.__start = startOffset
                    self.__end = None

                @property
                def start(self):
                    return self.__start

                @property
                def end(self):
                    return self.__end

                @end.setter
                def end(self, end):
                    self.__end = end

                @property
                def count(self):
                    return self.__count

                def countDown(self):
                    self.__count -= 1
                    return self.__count

            def __init__(self):
                self.__deque = deque([])

            def start(self, loopCount, offset):
                self.__deque.appendleft(self.Data(loopCount, offset))

            def breakIfLast(self, offset):
                data = self.__deque[0]
                if data.count == 1:
                    self.__deque.popleft()
                    offset = data.end
                return offset

            def end(self, offset):
                data = self.__deque[0]
                isInfiniteLoop = data.count == 0
                if isInfiniteLoop or data.countDown() != 0:
                    data.end = offset
                    offset = data.start
                else:
                    self.__deque.popleft()
                return (offset, isInfiniteLoop)

        def __init__(self, context, channelNumber, offset):
            self.__context = context
            self.__channel = context.getChannel(channelNumber)
            self.__nextOffset = offset
            self.__lengthCount = 1
            self.__isTie = False
            self.__octave = 0
            self.__volume = 0
            self.__tune = 0
            self.__detune = 0
            self.__envelope = self.EnvelopeGenerator()
            self.__repeat = self.RepeatStack()
            self.__lfo = self.LFO(False)
            self.__channel.setMode(True, False)
            self.__infiniteLoopCount = 0
            
        def __nextByte(self):
            data = self.__context.readByte(self.__nextOffset)
            self.__nextOffset += 1
            return data
            
        def __getByte(self):
            return self.__context.readByte(self.__nextOffset)

        def __nextWord(self):
            data = self.__context.readWord(self.__nextOffset)
            self.__nextOffset += 2
            return data

        def __updateTune(self):
            if self.__lfo.update():
                self.__applyTune()

        def __applyTune(self):
            self.__channel.setTune((self.__tune + self.__lfo.current + self.__detune) >> int(self.__octave))

        def __updateVolume(self):
            self.__envelope.update()
            self.__applyVolume()

        def __applyVolume(self):
            self.__channel.setVolume((self.__envelope.current * self.__volume) >> 8)

        def tick(self):
            self.__updateTune()
            self.__lengthCount -= 1
            if self.__lengthCount != 0:
                self.__updateVolume()
                return True
            else:
                if not self.__isTie:
                    self.__envelope.release()
                self.__updateVolume()

            while True:
                data = self.__nextByte()
                if data < 0x80:
                    self.__lengthCount = data + 1
                    return True
                elif data < 0xe0:
                    (self.__tune, self.__octave) = self.__context.getTuneAndOctave(data - 0x80)
                    if not self.__isTie:
                        self.__envelope.attack()
                        self.__lfo.reset()
                    self.__lengthCount = self.__nextByte()
                    if self.__lengthCount == 0:
                        self.__lengthCount = 256
                    if self.__getByte() == 0xe8:
                        self.__isTie = True
                        self.__nextOffset += 1
                    else:
                        self.__isTie = False
                    self.__applyTune()
                    self.__applyVolume()
                    return True
                elif data == 0xe0:
                    envelopeData = self.__context.findEnvelope(targetToneNumber=self.__nextByte())
                    if envelopeData is not None:
                        self.__envelope.setData(envelopeData)
                elif data == 0xe1:
                    self.__volume = self.__nextByte()
                elif data == 0xe2:
                    count = self.__nextByte()
                    self.__repeat.start(count, self.__nextOffset)
                elif data == 0xe3:
                    self.__nextOffset = self.__repeat.breakIfLast(self.__nextOffset)
                elif data == 0xe4:
                    (self.__nextOffset, isInfiniteLoop) = self.__repeat.end(self.__nextOffset)
                    self.__infiniteLoopCount += 1 if isInfiniteLoop else 0
                elif data == 0xe5:
                    self.__context.setNoiseFrequency(frequency=self.__nextByte())
                elif data == 0xe6:
                    self.__volume += 0 if self.__volume == 15 else 1
                elif data == 0xe7:
                    self.__volume -= 0 if self.__volume == 0 else 1
                elif data == 0xe9:
                    self.__detune = self.__nextWord()
                elif data == 0xea:
                    delay = self.__nextByte()
                    speed = self.__nextByte()
                    depth = self.__nextByte()
                    value = self.__nextWord()
                    self.__lfo = self.LFO(True, delay if delay != 0 else 256, speed, depth, value)
                elif data == 0xeb:
                    self.__lfo.setEnable(True if self.__nextByte() != 0 else False)
                elif data == 0xec:
                    data = self.__nextByte()
                    self.__channel.setMode(isToneOn=data & 0x1, isNoiseOn=(data & 0x2) >> 1)
                elif data == 0xff:
                    self.__channel.setVolume(0)
                    return False

        @property
        def infiniteLoopCount(self):
            return self.__infiniteLoopCount
                    
    def __init__(self, psg, sequenceData):
        header = self.Header(sequenceData)
        self.__title = header.title;
        context = self.Context(psg, sequenceData, header.envelopeTable)
        self.__parts = [self.Part(context, channelNumber, offset) for (channelNumber, offset) in enumerate(header.channels) if offset != None]

    def tick(self):
        for (index, part) in enumerate(self.__parts):
            if part != None and not part.tick():
                self.__parts[index] = None

    @property
    def loopCount(self):
        return min(part.infiniteLoopCount for part in self.__parts if part != None)
                
    @property
    def title(self):
        return self.__title

    @property
    def isPlaying(self):
        return None not in self.__parts
