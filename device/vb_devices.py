# -*- coding:utf-8 -*-
import asyncio
import pyaudio

from device.base_device import BaseDevice
import time
import wave


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
    RECORD_SECONDS = 10

    def __init__(self):
        self.audio_queue: asyncio.Queue = None
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
        self.allow_to_read = False

    def toggle_device(self):
        self.allow_to_read = not self.allow_to_read
        return self.allow_to_read

    async def read_frame(self):
        # frame = self.input_stream.read(self.CHUNK)
        frame = await asyncio.to_thread(self.input_stream.read, self.CHUNK)
        if frame:
            yield frame

    async def collect_frames(self):
        while True:
            try:
                if self.allow_to_read:
                    frame = await self.read_frame()
                    await self.audio_queue.put(frame)
                else:
                    await asyncio.sleep(0.1)
            except Exception as e:
                await self.log(f"[vb_audio_device][collect_frames] Error: {e}")

    async def set_queue(self, queue: asyncio.Queue):
        self.audio_queue = queue

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

    async def recording(self):
        # p = pyaudio.PyAudio()

        # input_device_index = _get_device_index(self.VB_OUTPUT_DEVICE_NAME, self.RATE, self.CHANNEL)
        # if input_device_index is None:
        #     print("未找到输入设备")
        #     return
        #
        # # 打开音频流
        # stream = p.open(format=self.FORMATTER,
        #                 channels=self.CHANNEL,
        #                 rate=self.RATE,
        #                 input=True,
        #                 input_device_index=input_device_index,
        #                 frames_per_buffer=self.CHUNK)

        wf = wave.open('test_recording.wav', 'wb')
        wf.setnchannels(self.CHANNEL)
        wf.setsampwidth(self.p.get_sample_size(self.FORMATTER))
        wf.setframerate(self.RATE)

        # 开始时间
        start_time = time.time()

        try:
            self.allow_to_read = True
            while True:
                if time.time() - start_time >= self.RECORD_SECONDS:
                    print("录音时间已到，停止录音")
                    break

                try:
                    elapsed_time = time.time() - start_time
                    print(f"\r录制中... {int(elapsed_time)}/{self.RECORD_SECONDS}秒", end="")
                    async for frame in self.read_frame():
                        wf.writeframes(frame)
                    # data = self.input_stream.read(self.CHUNK)
                    # wf.writeframes(data)
                except IOError as e:
                    print(f"音频流读取失败: {e}")
                    break

        except Exception as e:
            print(f"录音出现错误: {e}")
        finally:
            # 停止流并关闭
            print("停止录音...")
            # stream.stop_stream()
            # stream.close()
            # p.terminate()

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
    asyncio.run(vb.recording())
    print('关闭 vb 设备')
    vb.close()
    pass
