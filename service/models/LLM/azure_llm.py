# -*- coding:utf-8 -*-
import json
import re

from .base_llm import BaseLLM
import asyncio
from openai import AzureOpenAI
from datetime import datetime

import logging
from pathlib import Path

current_dir = Path(__file__).resolve().parent
log_dir = current_dir.parents[2]
log_file_path = log_dir / 'log.txt'
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)



class AzureLLM(BaseLLM):
    def __init__(self):
        self.AZURE_OPENAI_URL = "https://lx-gpt-4o.openai.azure.com/openai/"
        self.AZURE_OPENAI_API_VERSION = "2024-02-15-preview"
        self.AZURE_OPENAI_DEPLOYMENT = "gpt-4o"
        self.AZURE_OPENAI_API_KEY = "9cb23f1238eb4fd0b33f5f11fb98985a"

        self.role_prompt = "你是一个非常棒的个人助手,请协助我解决问题!"

        self.client = AzureOpenAI(
            api_key=self.AZURE_OPENAI_API_KEY,
            api_version=self.AZURE_OPENAI_API_VERSION,
            base_url=self.AZURE_OPENAI_URL,
        )

    async def post_text(self, text: str, text_queue: asyncio.Queue = None, history_queue: asyncio.Queue = None,
                        max_history: int = 0):
        try:
            t0 = datetime.now()
            logging.info(f'[LLM module] step 0 send to llm msg time: {t0}')
            messages = [
                {"role": "system", "content": f"{self.role_prompt}"}
            ]

            # 维护历史消息
            temp_history = []
            while not history_queue.empty():
                msg = await history_queue.get()
                temp_history.append(msg)
            for msg in temp_history:
                await history_queue.put(msg)

            # 实际使用的历史对话轮数
            if max_history > 0 and len(temp_history) >= 2:
                actual_history = temp_history[-2 * max_history:]
                # 添加历史消息到消息列表
                for i, msg in enumerate(actual_history):
                    role = "user" if i % 2 == 0 else "assistant"
                    messages.append({"role": role, "content": msg})

            # 添加当前消息到消息列表
            messages.append({"role": "user", "content": text})

            print(f'send to llm msg: {json.dumps(messages)}')
            t1 = datetime.now()
            logging.info(f'[LLM module] step 1 prepare send to llm msg time: {t1}, cost: {t1 - t0}')
            result = await self.achat_with_azure_gpt4o(messages)
            t2 = datetime.now()
            logging.info(f'[LLM module] step 2 got llm response time: {t2}, cost: {t2 - t1}')
            print(f'got llm response: {result}')

            t3 = datetime.now()
            logging.info(f'[LLM module] step 3 put to text queue time: {t3}, cost: {t3 - t2}')
            await text_queue.put(result)
            t4 = datetime.now()
            logging.info(f'[LLM module] step 4 put to text queue done time: {t4}, cost: {t4 - t3}')
            await history_queue.put(result)

        except Exception as e:
            logging.info(f'处理文本 "{text}" 时发生错误: {e}')
            raise "llm 处理文本时发生错误"

    async def close(self):
        pass

    async def achat_with_azure_gpt4o(self, messages, **kwargs):
        print(f'{messages}')

        chat_completion = self.client.chat.completions.create(
            model=self.AZURE_OPENAI_DEPLOYMENT,
            messages=messages,
            temperature=kwargs.get("temperature", 0.9),
        )
        result = chat_completion.choices[0].message.content
        logging.info(
            f"当前任务： the gpt prompt is: {messages}\n{result}")
        return result




if __name__ == '__main__':
    agent = AzureLLM()

    import asyncio

    text_queue = asyncio.Queue()
    history_queue = asyncio.Queue()

    asyncio.run(agent.post_text(text="你好"))
