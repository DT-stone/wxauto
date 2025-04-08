# -*- coding:utf-8 -*-
import asyncio
import pyaudio
from abc import ABC, abstractmethod


def _show_devices() -> (int, str, int, int):
    devices = []
    p = pyaudio.PyAudio()
    for i in range(0, p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        devices.append((dev["index"], dev["name"], dev["maxInputChannels"], dev.get("defaultSampleRate")))

    # print(devices)
    return devices


def _get_device_index(device_name, rate, channel=None) -> int:
    devices = _show_devices()
    target_device = [device for device in devices if
                     device_name in device[1] and device[3] == rate and (channel is None or device[2] == channel)]
    if target_device:
        return target_device[0][0]
    else:
        raise Exception(f"cannot find device: {device_name}, rate: {rate}, channel: {channel}")


class BaseDevice(ABC):
    @abstractmethod
    async def read_frame(self, output_queue: asyncio.Queue):
        pass

    @abstractmethod
    async def write_back(self, input_queue: asyncio.Queue):
        pass


class VBAudioDevice(BaseDevice):
    """"""
    FORMATTER = pyaudio.paInt16
    CHUNK = 1024
    CHANNEL = 2
    RATE = 48000
    VB_INPUT_DEVICE_NAME = "CABLE Input (VB-Audio Virtual Cable)"
    VB_OUTPUT_DEVICE_NAME = "CABLE Output (VB-Audio Virtual Cable)"

    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.intput_stream = self.p.open(
            format=self.FORMATTER,
            channels=self.CHANNEL,
            rate=self.RATE,
            input=True,
            frames_per_buffer=self.CHUNK,
            # VB 的输出设备作为音频的输入源
            input_device_index=_get_device_index(self.VB_OUTPUT_DEVICE_NAME, self.RATE, self.CHANNEL)
        )

        self.output_stream = self.p.open(
            format=self.FORMATTER,
            channels=self.CHANNEL,
            rate=self.RATE,
            input=True,
            frames_per_buffer=self.CHUNK,
            input_device_index=_get_device_index(self.VB_INPUT_DEVICE_NAME, self.RATE)  # 音频数据输出到 VB 的输入设备
        )

    async def read_frame(self, output_queue: asyncio.Queue):
        while True:
            data = self.intput_stream.read(self.CHUNK)
            await output_queue.put(data)

    async def write_back(self, input_queue: asyncio.Queue):
        while True:
            data = b''
            data = await input_queue.get()
            self.output_stream.write(data)

    def close(self):
        self.output_stream.stop_stream()
        self.output_stream.close()
        self.intput_stream.stop_stream()
        self.intput_stream.close()
        self.p.terminate()
