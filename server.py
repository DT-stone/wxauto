# -*- coding:utf-8 -*-
import asyncio

from torch.onnx.symbolic_opset11 import chunk

# from service.pipeline import Pipeline
from device.vb_devices import VBAudioDevice
import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from service.models.audio_detection import AudioDetectionModule
from service.models.audio_processing import AudioProcessingModule
from service.models.text_processing import TextProcessingModule
from service.models.tts_module import TTSModule
from service.models.data_transmission import DataTransmissionModule
from silero_vad import load_silero_vad
from fastapi.middleware.cors import CORSMiddleware
from service.models.LLM.azure_llm import AzureLLM


class Pipeline:
    def __init__(self):
        # 定义各个队列
        self.raw_audio_queue = asyncio.Queue()  # 原始数据队列
        self.detected_audio_queue = asyncio.Queue()  # 音频数据检测队列
        self.text_queue = asyncio.Queue()  # 文本队列
        self.send_text_queue = asyncio.Queue()  # 待发送文本队列
        self.tts_queue = asyncio.Queue()  # tts 队列
        self.send_audio_queue = asyncio.Queue()  # 待发送音频队列
        self.history_text_queue = asyncio.Queue()  # 历史文本队列
        self.history_audio_queue = asyncio.Queue()  # 历史音频队列

        self.model = None  # 延迟加载 silero_vad

        # 初始化模块引用为 None
        self.llm = AzureLLM()
        self.audio_detection = None
        self.audio_processing = None
        self.text_processing = None
        self.tts_module = None
        self.data_transmission = None

        self.tasks = []
        self.websocket = None

    async def initialize_pipeline(self, websocket: WebSocket):
        self.websocket = websocket
        self.data_transmission = DataTransmissionModule(
            send_audio_queue=self.send_audio_queue,
            send_text_queue=self.send_text_queue,
            history_audio_queue=self.history_audio_queue,
            history_text_queue=self.history_text_queue,
        )
        await self.data_transmission.set_websocket(websocket)

        # 初始化各个模块并发送状态更新
        message = BaseResp.gen_resp(MsgType.SYSTEM, "Modules initializing.")
        await self.send_status(message)
        # await self.send_status("Initializing silero_vad model...")
        self.model = load_silero_vad()

        self.audio_detection = AudioDetectionModule(
            model=self.model,
            audio_queue=self.raw_audio_queue,
            detected_audio_queue=self.detected_audio_queue,
            send_text_queue=self.send_text_queue,
            history_audio_queue=self.history_audio_queue,
            reset_callback=self.reset_pipeline,
        )

        self.audio_processing = AudioProcessingModule(
            llm=self.llm,
            audio_queue=self.detected_audio_queue,
            text_queue=self.text_queue,
            history_audio_queue=self.history_audio_queue,
            history_text_queue=self.history_text_queue,
            send_text_queue=self.send_text_queue,
        )

        self.text_processing = TextProcessingModule(
            text_queue=self.text_queue,
            tts_queue=self.tts_queue,
            send_text_queue=self.send_text_queue,
        )

        self.tts_module = TTSModule(
            tts_queue=self.tts_queue,
            send_audio_queue=self.send_audio_queue,
        )

        # 启动任务
        self.tasks = [
            asyncio.create_task(self.audio_detection.run()),
            asyncio.create_task(self.audio_processing.run()),
            asyncio.create_task(self.text_processing.run()),
            asyncio.create_task(self.tts_module.run()),
            asyncio.create_task(self.data_transmission.run())
        ]
        message = BaseResp.gen_resp(MsgType.SYSTEM, "All modules initialized and tasks started.")
        await self.send_status(message)

    async def send_status(self, message: str):
        if self.websocket:
            await self.websocket.send_text(message)

    async def reset_pipeline(self):
        print("Resetting pipeline...")
        # 清空除上下文队列之外的所有队列
        await self.clear_queues()
        # 释放资源（api请求）
        if self.text_processing:
            self.text_processing.reset()
        if self.audio_processing:
            await self.audio_processing.reset()
        if self.tts_module:
            await self.tts_module.reset()
        if self.data_transmission:
            await self.data_transmission.set_websocket(self.websocket)

    async def clear_queues(self):
        queues = [
            self.raw_audio_queue,
            self.detected_audio_queue,
            self.text_queue,
            self.tts_queue,
            self.send_audio_queue
        ]
        for q in queues:
            while not q.empty():
                try:
                    q.get_nowait()
                    q.task_done()
                except asyncio.QueueEmpty:
                    break

    async def clear_history_queues(self):
        queues = [
            self.history_text_queue,
            self.history_audio_queue
        ]
        for q in queues:
            while not q.empty():
                try:
                    q.get_nowait()
                    q.task_done()
                except asyncio.QueueEmpty:
                    break

    async def shutdown(self):
        await self.reset_pipeline()
        await self.clear_history_queues()
        for task in self.tasks:
            task.cancel()


async def main():
    pipeline = Pipeline()
    await pipeline.initialize_pipeline()
    vb_device = VBAudioDevice()

    # wx = WeChat()
    # pickup = True
    while True:
        data = await vb_device.read_frame()
        await pipeline.raw_audio_queue.put(data)
    #     pickup = wx.receive_call(pickup=pickup)
    #     if pickup:
    #         import time
    #         time.sleep(3)


async def load_wav(pipeline):
    wav_file = 'demo.wav'
    chunk = 1024
    import wave
    wf = wave.open(wav_file, 'rb')
    data = wf.readframes(chunk)

    while data:
        await pipeline.raw_audio_queue.put(data)


if __name__ == '__main__':
    asyncio.run(main())
