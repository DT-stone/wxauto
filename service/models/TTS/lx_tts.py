# -*- coding:utf-8 -*-
import asyncio
import time
import pygame
import aiohttp
import logging
import pyaudio
from pydub import AudioSegment
from io import BytesIO
from pathlib import Path
from datetime import datetime

from .base_tts import BaseTTS

current_dir = Path(__file__).resolve().parent
log_dir = current_dir.parents[2]
log_file_path = log_dir / 'log.txt'
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class LingXiTTS(BaseTTS):
    def __init__(self):
        self.url = "http://8.142.222.140/tts"
        self.session = aiohttp.ClientSession()
        self.chunk_size = 1024

    async def stream(self, text: str):
        start_time = time.perf_counter()
        param = {
            "text": text,
            "ttsModel": "shuting"
        }
        t1 = datetime.now()
        logging.info(f'[LingXiTTS] step 1 stream text time:: {t1}')
        async with self.session.get(self.url, params=param) as response:
            # 获取Content-Type
            content_type = response.headers.get('Content-Type')

            result = await response.content.read()

            for i in range(0, len(result), self.chunk_size):
                chunk = result[i:i + self.chunk_size]
                yield chunk

            # 处理流式音频
            # async for chunk in response.content.iter_chunked(1024):  # 每次处理1024字节
            #     if chunk:
            #         # processed_chunk = await self.convert_rate(chunk, 16000)
            #         yield chunk
        t2 = datetime.now()
        logging.info(f'[LingXiTTS] step 2 stream text done time:: {t2},cost time: {t2 - t1}')
        end_time = time.perf_counter()
        print(f"recv b-data cost time: {end_time - start_time}")

    async def communicate(self, text: str):
        return await self.send_msg_http_post(self.url, text, type='get')

    async def close(self):
        pass

    async def send_msg_http_post(self, url, text, type: str):
        start_time = time.perf_counter()
        param = {
            "text": text,
            "ttsModel": "shuting"
        }
        result = b''

        if type == 'post':
            async with self.session.post(url, json=param) as response:
                result = await response.read()  # 读取整个响应内容
        elif type == 'get':
            async with self.session.get(url, params=param) as response:
                # 获取Content-Type
                content_type = response.headers.get('Content-Type')
                print(f"Content-Type: {content_type}")
                data = await response.content.read()
                result = await self.convert_rate(data, 16000)

            end_time = time.perf_counter()
            print(f"recv b-data cost time: {end_time - start_time}")

            return result

    async def convert_rate(self, chunk, target_sample_rate=16000):
        # 将每个音频块转为 AudioSegment 对象
        audio_segment = AudioSegment.from_wav(BytesIO(chunk))
        source_sample_rate = audio_segment.frame_rate

        channels = audio_segment.channels
        sample_width = audio_segment.sample_width
        duration_seconds = audio_segment.duration_seconds

        print(
            f'audio attr: \n    -channels={channels}, \n    -sample_width={sample_width},\n    -frame_rate={source_sample_rate}, \n    -duration_seconds={duration_seconds}')

        if source_sample_rate == target_sample_rate:
            return chunk

        # 将采样率转换为目标采样率
        audio_segment = audio_segment.set_frame_rate(target_sample_rate)

        # 将转换后的音频保存到 BytesIO（即内存缓存）
        output_wav = BytesIO()
        audio_segment.export(output_wav, format="wav")

        # 处理后的音频数据
        output_wav.seek(0)
        return output_wav.read()


async def test_http():
    speaker = LingXiTTS()
    url = 'http://8.142.222.140/tts'
    text = '超级飞侠我爱你'

    async with aiohttp.ClientSession() as session:
        # b_data = asyncio.create_task(speaker.send_msg_http_post(session=session, url=url, text=text, type='get'))
        b_data = await speaker.send_msg_http_post(url=url, text=text, type='get')

        audio_data = BytesIO(b_data)

        # 初始化 pygame mixer
        pygame.mixer.init()

        # 加载音频并播放
        pygame.mixer.music.load(audio_data)
        pygame.mixer.music.play()

        # 等待音频播放完成
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)


async def main():
    speaker = LingXiTTS()
    data = b''
    data = await speaker.communicate("遛狗拉")

    say_time = time.perf_counter()
    audio_player = pyaudio.PyAudio()
    stream = audio_player.open(format=pyaudio.paInt16,
                               channels=1,
                               rate=16000,
                               output=True)

    stream.write(data)
    end_time = time.perf_counter()
    print(f"say cost time: {end_time - say_time}")
    # audio_data = io.BytesIO(data)
    #
    # # 初始化 pygame mixer
    # pygame.mixer.init()
    #
    # # 加载音频并播放
    # pygame.mixer.music.load(audio_data)
    # pygame.mixer.music.play()
    #
    # # 等待音频播放完成
    # while pygame.mixer.music.get_busy():
    #     pygame.time.Clock().tick(10)


if __name__ == '__main__':
    print('tts starting')
    start_time = time.perf_counter()
    asyncio.run(main())
    end_time = time.perf_counter()
    print(f"total cost time: {end_time - start_time}")
    print('tts end')
