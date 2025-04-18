# -*- coding:utf-8 -*-
import asyncio
import pyaudio

from device.base_device import BaseDevice


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
        print(f"target_device:{target_device}")
        return target_device[0][0]
    else:
        raise Exception(f"cannot find device: {device_name}, rate: {rate}, channel: {channel}")


class VBAudioDevice(BaseDevice):
    """
    VB-Audio Cable Device
    """
    FORMATTER = pyaudio.paInt16
    CHUNK = 1024
    CHANNEL = 2
    RATE = 48000
    VB_INPUT_DEVICE_NAME = "CABLE Input (VB-Audio Virtual Cable)"
    VB_OUTPUT_DEVICE_NAME = "CABLE Output (VB-Audio Virtual Cable)"

    def __init__(self,
                 # source_audio_queue: asyncio.Queue,
                 # send_audio_queue: asyncio.Queue,
                 ):
        # self.source_audio_queue = source_audio_queue
        # self.send_audio_queue = send_audio_queue
        self.p = pyaudio.PyAudio()
        self.input_stream = self.p.open(
            format=self.FORMATTER,
            channels=self.CHANNEL,
            rate=self.RATE,
            input=True,
            frames_per_buffer=self.CHUNK,
            # VB 的输出设备作为音频的输入源
            # input_device_index=_get_device_index(self.VB_INPUT_DEVICE_NAME, self.RATE)
            input_device_index=_get_device_index(self.VB_OUTPUT_DEVICE_NAME, self.RATE, self.CHANNEL)
        )

        self.output_stream = self.p.open(
            format=self.FORMATTER,
            channels=self.CHANNEL,
            rate=self.RATE,
            output=True,
            frames_per_buffer=self.CHUNK,
            output_device_index=_get_device_index(self.VB_INPUT_DEVICE_NAME, self.RATE)  # 音频数据输出到 VB 的输入设备
        )

    async def read_frame(self):
        while True:
            try:
                data = await asyncio.to_thread(self.input_stream.read, self.CHUNK)
                print(f"read data len: {len(data)}")
                return data
            except asyncio.CancelledError:
                await self.log("[vb_audio_device][read_frame] task was cancelled")
            except Exception as e:
                await self.log(f"[vb_audio_device][read_frame] Error: {e}")

    async def play(self):
        import wave
        round = 0
        chunk = 1024
        p = pyaudio.PyAudio()
        # Open an output stream to play audio
        output_stream = p.open(
            format=self.FORMATTER,
            channels=self.CHANNEL,
            rate=self.RATE,
            output=True,
            output_device_index=_get_device_index(self.VB_INPUT_DEVICE_NAME, self.RATE),
            frames_per_buffer=chunk
        )
        while round < 5:
            round += 1
            wf = wave.open('Q55.wav', 'rb')
            data = wf.readframes(chunk)
            while data:
                output_stream.write(data)
                data = wf.readframes(chunk)
            print(f'Finished playing!-{round}')
            await asyncio.sleep(1)

        output_stream.stop_stream()
        output_stream.close()
        wf.close()
        p.terminate()

    async def write_back(self, data):
        while True:
            try:
                print(f'write back data len: {len(data)}')
                await self.output_stream.write(data)
                # data = await self.send_audio_queue.get()
                # self.output_stream.write(data)
                pass
            except asyncio.CancelledError:
                await self.log("[vb_audio_device][write_back] task was cancelled")
            except Exception as e:
                await self.log(f"[vb_audio_device][write_back] Error: {e}")

    async def reset(self):
        pass

    def close(self):
        self.output_stream.stop_stream()
        self.output_stream.close()
        self.input_stream.stop_stream()
        self.input_stream.close()
        self.p.terminate()


if __name__ == '__main__':
    vb = VBAudioDevice()
    print('初始化 vb 设备')
    asyncio.run(vb.play())
    print('关闭 vb 设备')
    vb.close()
    pass
