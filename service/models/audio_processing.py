import asyncio
from datetime import datetime
from service.models.ASR.lx_asr import LxAsr
from utils.logger import logger



class AudioProcessingModule:
    def __init__(self, audio_queue: asyncio.Queue, text_queue: asyncio.Queue, history_audio_queue: asyncio.Queue,
                 history_text_queue: asyncio.Queue, send_text_queue: asyncio.Queue, llm):
        self.audio_queue = audio_queue
        self.text_queue = text_queue
        self.history_text_queue = history_text_queue
        self.history_audio_queue = history_audio_queue
        self.send_text_queue = send_text_queue
        self.asr_result_queue = asyncio.Queue()

        
        self.asr = LxAsr(self.asr_result_queue)

        # from .models.LLM.azure_llm import AzureLLM
        self.llm = llm
        self.tasks = set()
        self.reset_lock = asyncio.Lock()

    async def post_audio(self, combined_audio: bytes, lang: str = "auto") -> str:
        await self.asr.post_audio(combined_audio, lang)

    async def post_text(self, text: str):
        await self.llm.post_text(text, self.text_queue, self.history_text_queue)

    async def process_audio(self, combined_audio: bytes, lang: str = "auto"):
        """
        处理音频，将其转换为文本，然后流式传输文本。
        """
        try:
            # step 1 识别音频的时间点
            logger.info(f'[audio processing] step 1 接收音频时间:{datetime.now()}')
            await self.post_audio(combined_audio, lang)
            transcribed_text = await asyncio.wait_for(self.asr_result_queue.get(), timeout=3)
            logger.info(
                f'[audio processing] step 2 接收 ASR result 时间 :{datetime.now()},\n- transcribed_text :{transcribed_text}')
            # transcribed_text = await self.asr_result_queue.get()
            if transcribed_text:
                # resp = BaseResp.gen_resp(MsgType.USER, transcribed_text, uuid.uuid4().hex)
                # await self.send_text_queue.put(resp)
                logger.info(f'[audio processing] step 3 发送文本到 llm 时间 :{datetime.now()}')
                await self.post_text(transcribed_text)
        except asyncio.CancelledError:
            logger.info("process_audio 任务被取消")
            raise
        except Exception as e:
            logger.error(f"处理音频时发生错误: {e}")

    async def periodic_logger(self):
        """每隔60秒记录一次日志，表明 run 函数仍在运行。"""
        try:
            while True:
                logger.info("audio_processing run 函数正在正常运行。")
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("periodic_logger 任务被取消")
            pass

    async def run(self):
        """
        持续处理来自队列的音频数据。
        """
        logger_task = asyncio.create_task(self.periodic_logger())
        self.tasks.add(logger_task)

        try:
            while True:
                combined_audio = await self.audio_queue.get()
                logger.info('AudioProcessingModule: 成功获取一块音频')

                # 为每个音频处理创建一个独立的任务
                task = asyncio.create_task(self.process_audio(combined_audio, lang="auto"))
                self.tasks.add(task)

                # 任务完成后移除
                task.add_done_callback(self.tasks.discard)

                self.audio_queue.task_done()
        except asyncio.CancelledError:
            logger.info("run 任务被取消")
            raise
        except Exception as e:
            logger.error(f"运行循环中的错误: {e}")
        finally:
            logger_task.cancel()
            await logger_task

    async def reset(self):
        """
        快速重置模块，通过取消所有相关任务并重置 ASR 和 LLM。
        """
        async with self.reset_lock:
            logger.info("开始重置 AudioProcessingModule")

            # 取消所有任务
            tasks = list(self.tasks)
            for task in tasks:
                task.cancel()

            # 等待所有任务取消完成
            await asyncio.gather(*tasks, return_exceptions=True)
            self.tasks.clear()

            logger.info("AudioProcessingModule 重置完成")


if __name__ == "__main__":
    processor = AudioProcessingModule(
        audio_queue=asyncio.Queue(),
        text_queue=asyncio.Queue(),
        history_text_queue=asyncio.Queue(),
        history_audio_queue=asyncio.Queue(),
        send_text_queue=asyncio.Queue()
    )
    print('done')
