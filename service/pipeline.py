# -*- coding:utf-8 -*-
import asyncio

from silero_vad import load_silero_vad

from device.base_device import BaseDevice
from service.models.text_processing import TextProcessingModule
from service.models.audio_detection import AudioDetectionModule
from service.models.audio_processing import AudioProcessingModule
from service.models.data_transmission import DataTransmissionModule
from service.models.tts_module import TTSModule
from service.models.LLM.azure_llm import AzureLLM
from utils.logger import logger
from wxauto import WeChat


class Pipeline:
    def __init__(self, device):
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
        self.wx: WeChat = None
        self.llm = AzureLLM()
        self.audio_detection = None
        self.audio_processing = None
        self.text_processing = None
        self.tts_module = None
        self.data_transmission = None
        self.device: BaseDevice = device

        self.tasks = []

    async def initialize_pipeline(self):
        self.wx = WeChat()
        self.data_transmission = DataTransmissionModule(
            wx=self.wx,
            device=self.device,
            send_audio_queue=self.send_audio_queue,
            send_text_queue=self.send_text_queue,
            history_audio_queue=self.history_audio_queue,
            history_text_queue=self.history_text_queue,
        )

        # 初始化各个模块并发送状态更新
        # await self.send_status("Initializing silero_vad model...")
        self.model = load_silero_vad()

        self.audio_detection = AudioDetectionModule(
            model=self.model,
            audio_queue=self.raw_audio_queue,
            detected_audio_queue=self.detected_audio_queue,
            send_text_queue=self.send_text_queue,
            history_audio_queue=self.history_audio_queue,
            reset_callback=self.reset_pipeline,
            orig_sample_rate=48000,
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
            # asyncio.create_task(self.device.read_frame()),
            # asyncio.create_task(self.wx.receive_call()),
            asyncio.create_task(self.audio_processing.run()),
            asyncio.create_task(self.text_processing.run()),
            asyncio.create_task(self.tts_module.run()),
            asyncio.create_task(self.data_transmission.run()),
        ]

        logger.info("All modules initialized and tasks started.")

    async def set_watched(self, who):
        await asyncio.to_thread(self.wx.AddListenChat, who)

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


if __name__ == '__main__':
    asyncio.run(main())
