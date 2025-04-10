# -*- coding:utf-8 -*-
import asyncio
from utils.logger import logger


class DataTransmissionModule:
    def __init__(self,
                 send_audio_queue: asyncio.Queue,
                 send_text_queue: asyncio.Queue,
                 history_text_queue: asyncio.Queue,
                 ):
        self.send_audio_queue = send_audio_queue
        self.send_text_queue = send_text_queue
        self.history_text_queue = history_text_queue

        # 传输结果

        self.audio_task: asyncio.Task = None
        self.text_task: asyncio.Task = None

    async def log(self, message: str):
        logger.info(message)

    async def run(self):
        self.audio_task = asyncio.create_task(self._send_audio())
        self.text_task = asyncio.create_task(self._send_text())

        await asyncio.gather(
            self.audio_task,
            self.text_task,
            return_exceptions=True
        )

    async def _send_audio(self):
        await self.log("开始传输音频")

        audio_cache = []
        try:
            while True:
                audio_chunk = await self.send_audio_queue.get()

                if audio_chunk is not None:
                    # audio_cache.append(audio_chunk)

                    # todo 传输音频
                    pass
                # else:
                #     if audio_cache:
                #         merged_audio=b''.join(audio_cache)

                self.send_audio_queue.task_done()
        except asyncio.CancelledError:
            await self.log("run is cancelled")
        except Exception as e:
            await self.log(f"Error: {e}")

    async def _send_text(self):
        await self.log("开始传输文本")

        try:
            while True:
                text = await self.send_text_queue.get()
                # todo 传输文本
                self.send_text_queue.task_done()
        except asyncio.CancelledError:
            await self.log("run is cancelled")
        except Exception as e:
            await self.log(f"Error: {e}")
