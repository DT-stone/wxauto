# -*- coding:utf-8 -*-
import asyncio

from silero_vad import load_silero_vad

from service.models.text_processing import TextProcessingModule
from service.models.audio_detection import AudioDetectionModule
from service.models.audio_processing import AudioProcessingModule
from service.models.data_transfmission import DataTransmissionModule
from service.models.tts_module import TTSModule
from service.models.DEVICE.vb_devices import VBAudioDevice
from utils.logger import logger


class Pipeline:
    def __init__(self) -> object:
        # 工作队列
        self.source_audio_queue = asyncio.Queue()
        self.detected_audio_queue = asyncio.Queue()
        self.text_queue = asyncio.Queue()
        self.send_text_queue = asyncio.Queue()
        self.tts_queue = asyncio.Queue()
        self.send_audio_queue = asyncio.Queue()
        self.history_text_queue = asyncio.Queue()

        # 延迟加载 silero_vad
        self.model = None

        # 初始化工作模块
        self.llm = None
        self.audio_detection = None
        self.audio_processing = None
        self.text_processing = None
        self.tts_module = None
        self.data_transmission = None
        self.audio_device = None

        self.tasks = []

    async def initialize_pipeline(self):
        self.model = load_silero_vad()
        self.audio_device = VBAudioDevice(
            source_audio_queue=self.source_audio_queue,
            send_audio_queue=self.send_audio_queue
        )
        # 数据传输模块
        self.data_transmission = DataTransmissionModule(
            send_audio_queue=self.send_audio_queue,
            send_text_queue=self.send_text_queue,
            history_text_queue=self.history_text_queue
        )

        # 音频收集
        self.audio_detection = AudioDetectionModule(
            model=self.model,
            audio_queue=self.source_audio_queue,
            detected_audio_queue=self.detected_audio_queue,
            send_text_queue=self.send_text_queue,
            reset_callback=self.reset_pipeline,
        )

        self.audio_processing = AudioProcessingModule(
            llm=self.llm,
            audio_queue=self.detected_audio_queue,
            text_queue=self.text_queue,
            history_text_queue=self.history_text_queue,
            send_text_queue=self.send_text_queue

        )

        self.text_processing = TextProcessingModule(
            text_queue=self.text_queue,
            tts_queue=self.tts_queue,
            send_text_queue=self.send_text_queue
        )

        self.tts_module = TTSModule(
            tts_queue=self.tts_queue,
            send_audio_queue=self.send_audio_queue
        )

        # 启动任务
        self.tasks = [
            asyncio.create_task(self.audio_device.read_frame()),
            asyncio.create_task(self.audio_detection.run()),
            asyncio.create_task(self.audio_processing.run()),
            asyncio.create_task(self.text_processing.run()),
            asyncio.create_task(self.tts_module.run()),
            asyncio.create_task(self.data_transmission.run()),
            asyncio.create_task(self.audio_device.write_back()),
        ]

    async def reset_pipeline(self):
        logger.info("Resetting pipeline...")
        await self.clear_queues()
        # 释放资源
        if self.text_processing:
            self.text_processing.reset()
        if self.audio_detection:
            self.audio_detection.reset()
        if self.tts_module:
            self.tts_module.reset()
        if self.data_transmission:
            self.data_transmission.reset()
        if self.audio_processing:
            self.audio_processing.reset()
        logger.info("Pipeline reset complete.")

    async def clear_queues(self):
        queues = [
            self.source_audio_queue,
            self.detected_audio_queue,
            self.text_queue,
            self.send_text_queue,
            self.tts_queue,
            self.send_audio_queue
        ]

        for queue in queues:
            while not queue.empty():
                try:
                    queue.get_nowait()
                    queue.task_done()
                except:
                    break

    async def clear_history_queue(self):
        queues = [
            self.history_text_queue
        ]

        for queue in queues:
            while not queue.empty():
                try:
                    queue.get_nowait()
                    queue.task_done()
                except:
                    break

    async def shutdown(self):
        await self.reset_pipeline()
        await self.clear_history_queue()
        for task in self.tasks:
            task.cancel()


async def main():
    pipeline = Pipeline()
    await pipeline.initialize_pipeline()


if __name__ == '__main__':
    asyncio.run(main())
