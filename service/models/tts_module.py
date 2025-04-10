# -*- coding:utf-8 -*-
import asyncio
from utils.logger import logger
from .TTS.lx_tts import LingXiTTS


class TTSModule:

    def __init__(self, tts_queue: asyncio.Queue, send_audio_queue: asyncio.Queue):
        self.tts_queue = tts_queue
        self.send_audio_queue = send_audio_queue
        self._sample_rate = 16000
        self._channels = 1
        self._sample_width = 2
        self._cache_duration = 5
        self.tts_engine = LingXiTTS()
        self.tasks = set()
        self.reset_lock = asyncio.Lock()
        self.cache = bytearray()

    async def log(self, message: str):
        logger.info(message)

    async def run(self, is_stream: bool = False):
        try:
            while True:
                text = await self.tts_queue.get()

                try:
                    if is_stream:
                        pass
                    else:
                        await self.process_text(text)
                except Exception as e:
                    await self.log(f"[tts module] handle text error:{e}")

        except Exception as e:
            await self.log(f"[tts module] main process error:{e}")

    async def process_text(self, text: str):
        try:
            async for chunk in self.tts_engine.stream(text):
                self.cache.extend(chunk)
        except asyncio.CancelledError:
            await self.log("[tts module][process text] task canceled")
            raise
        finally:
            if self.cache:
                await self.send_audio_queue.put(bytes(self.cache))
                self.cache.clear()

    async def process_audio_stream(self, text: str):
        try:
            async for data in self.tts_engine.stream(text):
                await self.send_audio_queue.put(data)
        except asyncio.CancelledError:
            await self.log("[tts module][process_audio_stream] was canceled")
            raise
        except Exception as e:
            await self.log(f"[tts module][process_audio_stream]has error{e}")

    async def reset(self):
        async with self.reset_lock:
            await self.log("[tts module][reset] starting reset tts module...")
            tasks = list(self.tasks)
            for task in tasks:
                task.cancel()

            # 等待手游任务取消完成
            await  asyncio.gather(
                *tasks,
                return_exceptions=True
            )

            self.tasks.clear()

            # 清空全局缓存
            self.cache.clear()
            # 重置 tts
            self.tts_engine = LingXiTTS()
        await self.log("[tts module][reset] reset finish...")
