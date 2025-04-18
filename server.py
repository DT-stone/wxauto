# -*- coding:utf-8 -*-
import asyncio

from device.vb_devices import VBAudioDevice
import asyncio
from service.pipeline import Pipeline
from wxauto import WeChat


async def main():
    who = '三里清风三里路'
    # who = '杨威'
    vb_device = VBAudioDevice()
    pipeline = Pipeline(device=vb_device)
    await pipeline.initialize_pipeline()

    await pipeline.set_watched(who=who)

    # todo 添加页面管理交互
    # wx.AddListenChat(who=who)
    # wx.GetListenMessage()
    # while True:
    #     try:
    #         # data = await vb_device.read_frame()
    #         # print(f'put data len: {len(data)}')
    #         # await pipeline.raw_audio_queue.put(data)
    #
    #         # await wx.receive_call()
    #         # if pickup:
    #         #     import time
    #         #     time.sleep(3)
    #         pass
    #     except Exception as e:
    #         print(e)


async def load_wav():
    import pyaudio
    audio_player = pyaudio.PyAudio()
    stream = audio_player.open(format=pyaudio.paInt16,
                               channels=1,
                               rate=48000,
                               output=True)
    pipeline = Pipeline()
    await pipeline.initialize_pipeline()
    wav_file = 'Q55.wav'
    chunk = 1024
    import wave
    wf = wave.open(wav_file, 'rb')
    data = wf.readframes(chunk)

    while data:
        # stream.write(data)
        await pipeline.raw_audio_queue.put(data)
        data = wf.readframes(chunk)


if __name__ == '__main__':
    asyncio.run(main())
