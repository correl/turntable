from itertools import chain
import struct
from typing import List
import unittest

from turntable.models import PCM
from turntable.turntable import PCMRecognizer


class TestPCMRecognizer(unittest.TestCase):
    def channel_data_to_pcm(self, channels: List[List[int]]) -> PCM:
        def interleave(xs: List[List[int]]) -> List[int]:
            return list(chain(*zip(*xs)))

        interleaved = interleave(channels)
        raw = struct.pack("{}h".format(len(interleaved)), *interleaved)
        return PCM(framerate=48000, channels=len(channels), data=raw)

    def test_convert_monaural_audio(self):
        channels = [[1] * 10]
        pcm = self.channel_data_to_pcm(channels)
        converted = PCMRecognizer.pcm_to_channel_data(pcm)
        self.assertEqual(channels, converted)

    def test_convert_stereo_audio(self):
        channels = [[1] * 10, [2] * 10]
        pcm = self.channel_data_to_pcm(channels)
        converted = PCMRecognizer.pcm_to_channel_data(pcm)
        self.assertEqual(channels, converted)

    def test_convert_10_channel_audio(self):
        channels = [[i] * 10 for i in range(10)]
        pcm = self.channel_data_to_pcm(channels)
        converted = PCMRecognizer.pcm_to_channel_data(pcm)
        self.assertEqual(channels, converted)
