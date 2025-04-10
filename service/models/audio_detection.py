# -*- coding:utf-8 -*-
import asyncio
import torch
import torchaudio
import time
import io
import numpy as np
import soundfile as sf
from silero_vad import load_silero_vad, get_speech_timestamps
from collections import deque
from enum import Enum

from utils.logger import logger


class DetectionState(Enum):
    BEFORE_SPEECH = 0
    DURING_SPEECH = 1
    AFTER_SPEECH = 2


class AudioDetectionModule:
    def __init__(self,
                 model,
                 audio_queue: asyncio.Queue,
                 detected_audio_queue: asyncio.Queue,
                 send_text_queue: asyncio.Queue,
                 reset_callback,
                 orig_sample_rate=16000,
                 target_sample_rate=16000,
                 buffer_duration=1.0,
                 silence_duration=1.5,
                 history_max_count=5
                 ):
        """
        初始化音频检测模块
        """
        self.model = model
        self.source_audio_queue = audio_queue
        self.detected_audio_queue = detected_audio_queue
        self.send_text_queue = send_text_queue
        self.reset_callback = reset_callback
        self.orig_sample_rate = orig_sample_rate
        self.target_sample_rate = target_sample_rate
        self.buffer_size = int(target_sample_rate * buffer_duration)
        self.buffer = torch.tensor([], dtype=torch.float32)
        self.silence_duration = silence_duration
        self.state = DetectionState.BEFORE_SPEECH
        self.collected_audio = torch.tensor([], dtype=torch.float32)
        self.last_speech_time = None

        # 历史缓冲区,存储多个前置缓冲区
        self.history_buffers = deque(maxlen=history_max_count)
        logger.info(f"初始化历史缓冲区,最多存储{history_max_count}个前置缓冲区")

        # 初始化重采样器

        if self.orig_sample_rate != self.target_sample_rate:
            self.resampler = torchaudio.transforms.Resample(
                orig_freq=self.orig_sample_rate,
                new_freq=self.target_sample_rate
            )
            logger.info(f"初始化重采样器,原始采样率:{self.orig_sample_rate},目标采样率:{self.target_sample_rate}")

        logger.info(f"音频检测模块初始化完成,当前状态:{self.state.name}")

    async def log(self, message: str):
        """
        异步记录日志
        Args:
            message (str):

        Returns:

        """
        logger.info(message)

    async def _handle_after_speech(self):
        """
        处理进入 afterSpeech 状态后的操作
        """
        try:
            await asyncio.sleep(self.silence_duration)
            self.buffer = torch.tensor([], dtype=torch.float32)
            await self.log("[_handle_after_speech] buffer was reset")
            cleared = 0
            while not self.source_audio_queue.empty():
                try:
                    self.source_audio_queue.get_nowait()
                    self.source_audio_queue.task_done()
                    cleared += 1
                except:
                    break
            await self.log(f"[_handle_after_speech] cleared {cleared} items from source_audio_queue")

            # reset state to before speech
            self.state = DetectionState.BEFORE_SPEECH

            # reset history buffer
            self.history_buffer.clear()
            await self.log(f"[_handle_after_speech] history buffer was reset")
        except Exception as e:
            logger.error(f"[_handle_after_speech] Error: {e}")

    async def run(self):
        """
        音频检测模块主程序
        """
        await self.log(f"audio_detection_module:音频检测模块开始运行")

        while True:
            try:
                audio_data = self.source_audio_queue.get()
            except asyncio.TimeoutError:
                continue

            # 处理 16 位 PCM 格式的音频数据 - 转换为 torch.Tensor 归一化
            if isinstance(audio_data, bytes):
                audio_array = np.frombuffer(audio_data, dtype=np.int16).copy()
                # [-32768, 32767]：int16 的取值范围。
                audio_tensor = torch.tensor(audio_array,
                                            dtype=torch.float32) / 32768.0  ## numpy 数组转换为 PyTorch 张量，并将其标准化为浮点数范围 [−1.0,1.0][−1.0,1.0]
            elif isinstance(audio_data, torch.Tensor):
                if audio_data.dtype != torch.int16:
                    audio_tensor = audio_data.float() / 32768.0
                elif audio_data.dtype == torch.float32:
                    audio_tensor = audio_data
                else:
                    await self.log(f"audio_detection_module:音频检测模块接收到不支持的数据类型：{type(audio_data)}")
                    self.source_audio_queue.task_done()
                    continue
            else:
                await self.log(f"audio_detection_module:音频检测模块接收到不支持的数据类型：{type(audio_data)}")
                self.source_audio_queue.task_done()
                continue

            if self.resampler is not None:
                await self.log("audio_detection_module:音频检测模块进行重采样")
                try:
                    audio_tensor = self.resampler(audio_tensor)
                    await self.log("audio_detection_module:音频检测模块重采样完成")
                except Exception as e:
                    await self.log(f"audio_detection_module:音频检测模块重采样失败：{e}")
                    self.source_audio_queue.task_done()
                    continue

            # 追加到缓冲区
            self.buffer = torch.cat((self.buffer, audio_tensor))

            if len(self.buffer) >= self.buffer_size:
                await self.log(f"audio_detection_module:音频检测模块缓冲区已满，进行音频检测")
                try:
                    speech_timestamps = get_speech_timestamps(
                        self.buffer,
                        self.model,
                        sampling_rate=self.target_sample_rate,
                        threshold=0.95,  # 调整阈值,控制敏感度
                    )
                    await self.log(f"audio_detection_module:音频检测模块检测到语音，当前状态：{self.state.name}")
                except Exception as e:
                    await self.log(f"audio_detection_module:音频检测模块检测到语音失败：{e}")
                    self.source_audio_queue.task_done()
                    continue

                current_time = time.time()
                if speech_timestamps:
                    if self.state == DetectionState.BEFORE_SPEECH:
                        self.state = DetectionState.DURING_SPEECH
                        try:
                            await self.reset_callback()

                            # todo 打断音频输出
                        except Exception as e:
                            await self.log(f"audio_detection_module:音频检测模块重置回调函数失败：{e}")

                        # 包含所有历史缓冲区
                        if len(self.history_buffers) > 0:
                            historical_audio = torch.cat(list(self.history_buffers))
                            self.collected_audio = torch.cat((historical_audio, self.buffer.clone()))
                            logger.debug("包含所有历史缓冲区到 collected_audio。")
                        else:
                            self.collected_audio = self.buffer.clone()
                            logger.debug("无历史缓冲区，仅包含当前缓冲区到 collected_audio。")

                        self.last_speech_time = current_time
                    elif self.state == DetectionState.DURING_SPEECH:
                        self.collected_audio = torch.cat((self.collected_audio, self.buffer.clone()))
                        self.last_speech_time = current_time
                else:
                    if self.state == DetectionState.DURING_SPEECH:
                        # Transition to AFTER_SPEECH
                        self.state = DetectionState.AFTER_SPEECH
                        self.collected_audio = torch.cat((self.collected_audio, self.buffer.clone()))
                        self.last_speech_time = current_time

                        audio_bytes_io = io.BytesIO()
                        # 转换为正确的形状（需要是 (num_samples, num_channels)）
                        audio_np = self.collected_audio.cpu().numpy()
                        if audio_np.ndim == 1:
                            audio_np = np.expand_dims(audio_np, axis=1)
                        sf.write(audio_bytes_io, audio_np, self.target_sample_rate, format='WAV')
                        audio_bytes = audio_bytes_io.getvalue()

                        await self.detected_audio_queue.put(audio_bytes)
                        await self.log("检测到完整语音片段，已放入 detected_audio_queue。")

                        # 异步保存音频文件
                        save_dir = "XXX/speaker_wav"
                        # await self.save_audio_async(audio_bytes, save_dir)

                        # 直接在 run 方法中处理 AFTER_SPEECH，阻塞 run 函数
                        await self._handle_after_speech()
