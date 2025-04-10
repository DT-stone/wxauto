# -*- coding:utf-8 -*-
import asyncio

from utils.logger import logger
from .ASR.lx_asr import LxAsr


class AudioProcessingModule:
    def __init__(
            self,
            audio_queue: asyncio.Queue,
            text_queue: asyncio.Queue,
            history_text_queue: asyncio.Queue,
            send_text_queue: asyncio.Queue,
            llm):
        self.audio_queue = audio_queue
        self.text_queue = text_queue
        self.history_text_queue = history_text_queue
        self.send_text_queue = send_text_queue
        self.asr_result_queue = asyncio.Queue()
        self.asr = LxAsr(self.asr_result_queue)

        self.llm = llm
        self.tasks = set()
        self.reset_lock = asyncio.Lock()

    async def log(self, message: str):
        logger.info(message)

    async def post_audio(self, combined_audio: bytes, lang: str = "auto") -> str:
        return await self.asr.post_audio(combined_audio, lang)

    async def post_text(self, text: str):
        await self.llm.post_text(text, self.text_queue, self.history_text_queue)

    async def process_audio(self, combined_audio: bytes, lang: str = "auto"):
        """
         处理音频
        Args:
            combined_audio ():
            lang ():

        Returns:

        """
        try:
            await self.post_audio(combined_audio, lang)
            transcribed_text = await asyncio.wait_for(self.asr_result_queue.get(), timeout=3)
            await self.log(f"transcribed_text: {transcribed_text}")
            if transcribed_text:
                await self.post_text(transcribed_text)
        except asyncio.CancelledError:
            await self.log("process_audio is cancelled")
            raise
        except Exception as e:
            await self.log(f"Error: {e}")

    async def run(self):
        """
        音频处理模块主程序
        音频识别,llm 处理
        Returns:

        """
        try:
            while True:
                combined_audio = await self.audio_queue.get()
                # 为每个音频处理创建一个独立的任务
                task = asyncio.create_task(self.process_audio(combined_audio, lang="auto"))
                self.tasks.add(task)

                # 任务完成后移除
                task.add_done_callback(self.tasks.discard)

                self.audio_queue.task_done()

        except asyncio.CancelledError:
            await self.log("run is cancelled")
            raise
        except Exception as e:
            await self.log(f"Error: {e}")

    async def reset(self):
        """
        快速重置模块，通过取消所有相关任务并重置 ASR 和 LLM。
        """
        async with self.reset_lock:
            await self.log("开始重置 AudioProcessingModule")

            # 取消所有任务
            tasks = list(self.tasks)
            for task in tasks:
                task.cancel()

            # 等待所有任务取消完成
            await asyncio.gather(*tasks, return_exceptions=True)
            self.tasks.clear()

            await self.log("AudioProcessingModule 重置完成")
