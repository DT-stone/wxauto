import asyncio
import aiohttp
from utils.logger import logger
from pathlib import Path
import aiofiles
# from models.TTS.fish_speech_tts import FishSpeechTTS
from service.models.TTS.lx_tts import LingXiTTS
from datetime import datetime


class TTSModule:
    def __init__(self, tts_queue: asyncio.Queue, send_audio_queue: asyncio.Queue):
        self.tts_queue = tts_queue
        self.send_audio_queue = send_audio_queue
        self._sample_rate = 16000
        self._sample_width = 2
        self._channels = 1
        self._cache_duration_seconds = 1
        self.tts_engine = LingXiTTS()
        self.tasks = set()
        self.reset_lock = asyncio.Lock()
        self.cache = bytearray()  # 添加全局缓存属性

    async def periodic_logger(self):
        """每隔60秒记录一次日志，表明 run 函数仍在运行。"""
        try:
            while True:
                logger.info("tts_module run 函数正在正常运行。")
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("periodic_logger 任务被取消")
            pass

    async def run(self, streaming: bool = False):
        """主 TTS 处理循环，支持流式和非流式选项。"""
        logger.info("tts_module 开始运行")
        # 启动定期日志记录协程
        logger_task = asyncio.create_task(self.periodic_logger())
        self.tasks.add(logger_task)
        logger_task.add_done_callback(self.tasks.discard)
        try:
            while True:
                text = await self.tts_queue.get()
                t0 = datetime.now()
                logger.info(f"[tts_module] step 0 接收到文本：{t0}")
                print(f'tts_module handle text:{text}')

                try:
                    t1 = datetime.now()
                    logger.info(f'[tts_module] step 1 开始处理文本：{t1},cost:{t1 - t0}')
                    if streaming:
                        await self.process_audio(text)
                        # await self.process_audio_stream(text, file_name)
                        # await self.load_audio_in_chunks_to_queue("test.wav")
                    else:
                        await self.process_audio(text)
                        # await self.load_audio_in_chunks_to_queue("test.wav")
                    t2 = datetime.now()
                    logger.info(f'[tts_module] step 2 处理文本完成：{t2},cost:{t2 - t1}')
                    logger.info(f'成功合成一条音频：{text}')
                except Exception as e:
                    logger.error(f'处理文本 "{text}" 时发生错误: {e}')

                self.tts_queue.task_done()
        except asyncio.CancelledError:
            logger.info("run 任务被取消")
            raise
        except Exception as e:
            logger.error(f'运行过程中发生错误: {e}')
        finally:
            # 确保 logger_task 被取消
            logger_task.cancel()
            await logger_task

    async def read_audio_file_in_chunks(self, file_path: str, chunk_size: int = 1024):
        """
        异步读取音频文件，并将其切片成指定大小的块。

        :param file_path: 音频文件路径
        :param chunk_size: 每个切片的大小（字节）
        :return: 返回一个生成器，按块读取音频文件
        """
        async with aiofiles.open(file_path, 'rb') as f:
            while True:
                chunk = await f.read(chunk_size)  # 读取音频文件的指定大小块
                if not chunk:
                    break  # 文件读取完毕
                yield chunk  # 返回读取的切片

    async def load_audio_in_chunks_to_queue(self, file_path: str, chunk_size: int = 1024):
        """
        从音频文件读取数据，切片并放入队列。

        :param file_path: 音频文件路径
        :param queue: 要放入的队列（ send_audio_queue）
        :param chunk_size: 每个切片的大小
        """
        async for chunk in self.read_audio_file_in_chunks(file_path, chunk_size):
            # 如果最后一块数据不足 chunk_size，补充为零填充
            if len(chunk) < chunk_size:
                chunk = chunk.ljust(chunk_size, b'\0')  # 用零填充
            await self.send_audio_queue.put(chunk)  # 将切片放入队列

    async def process_audio_stream(self, text: str, file_path: Path):
        """Streams audio data directly to the send_audio_queue without using a cache."""
        try:
            async for data in self.tts_engine.stream(text):
                await self.send_audio_queue.put(data)
                logger.info('成功流式put音频')
        except asyncio.CancelledError:
            logger.info("process_audio_stream 被取消")
            raise
        except Exception as e:
            logger.error(f'流式处理音频时发生错误: {e}')

    async def process_audio(self, text: str):
        """积累并在流完成后处理音频数据。"""
        try:
            async for data in self.tts_engine.stream(text):
                self.cache.extend(data)

        except asyncio.CancelledError:
            logger.info("process_audio 被取消")
            raise
        finally:
            if self.cache:
                await self.send_audio_queue.put(bytes(self.cache))
                self.cache.clear()  # 确保最终缓存被清空

    async def reset(self):
        """
        快速重置模块，通过取消所有相关任务并重置 TTS 引擎。
        """
        async with self.reset_lock:
            logger.info("开始重置 TTSModule")

            # 取消所有任务（除了 run 方法自身）
            tasks = list(self.tasks)
            for task in tasks:
                task.cancel()

            # 等待所有任务取消完成
            await asyncio.gather(*tasks, return_exceptions=True)
            self.tasks.clear()

            # 清空全局缓存
            self.cache.clear()
            logger.info("全局缓存已清空")

            # 重新初始化 TTS 引擎（如果需要）
            # self.tts_engine = FishSpeechTTS()

            logger.info("TTSModule 重置完成")
