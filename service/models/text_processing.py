# -*- coding:utf-8 -*-
import asyncio
import re
from utils.logger import logger


class TextProcessingModule:

    def __init__(self,
                 text_queue: asyncio.Queue,
                 tts_queue: asyncio.Queue,
                 send_text_queue: asyncio.Queue,
                 ban_list=None
                 ):
        self.text_queue = text_queue
        self.tts_queue = tts_queue
        self.send_text_queue = send_text_queue
        self.initial_termination_chars = ['.', '!', '?', '，', '。', '！', '~', '？', '；', ';', ',']
        self.subsequent_termination_chars = ['.', '!', '?', '。', '！', '~', '？', '；', ';']
        self.use_initial_chars = True
        self.current_text = []
        self.ban_list = ban_list or ["<strong>", "</strong>", "[laughter]", "[breath]", "「中性」", "「快乐」", "「悲伤」",
                                     "「惊讶」", "「恐惧」", "「厌恶」", "「愤怒」"]

        # 预编译ban_list的正则模式以提高性能
        if self.ban_list:
            # 转义每个禁止项以处理任何特殊的正则字符
            escaped_terms = [re.escape(term) for term in self.ban_list]
            # 使用单词边界确保只匹配完整的单词（可选）
            # 如果不需要单词边界，可以移除 r'\b' 和 r'\b'
            pattern = r'(' + '|'.join(escaped_terms) + r')'
            self.ban_pattern = re.compile(pattern, re.IGNORECASE)  # 添加不区分大小写的标志
        else:
            self.ban_pattern = None

    async def wash(self, text):
        # 移除 HTML 标签或其他格式符号
        text = re.sub(r'<.*?>', '', text)  # 移除 HTML 标签

        # 替换格式化符号（如加粗、斜体）
        text = re.sub(r'\*\*|__|~~|`', '', text)  # 去掉加粗、斜体等符号

        # 保留 ['.', '!', '?', '，', '。', '！', '~', '？', '；', ';', ',']
        text = re.sub(r'[^\w\s.!?，。！~？；,]', '', text)  # 去除其他不需要的符号

        text = re.sub(r'\*\s*', '，', text)

        # 替换长破折号为逗号或停顿
        text = re.sub(r'—', ',', text)

        # 删除不必要的空格和换行
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    async def log(self, message: str):
        logger.info(message)

    async def run(self):
        await self.log("开始处理文本")

        try:
            while True:
                # text = await self.text_queue.get()
                text = await asyncio.wait_for(self.text_queue.get(), timeout=1.5)

                await self.log(f"received text before wash: {text}")
                text = self.wash(text)
                await self.log(f"handle text after wash: {text}")

                self.current_text.append(text)

                while True:
                    merged_text = ' '.join(self.current_text)

                    # 应用禁止词汇替换
                    if self.ban_pattern:
                        merged_text = self.ban_pattern.sub('', merged_text)
                    # 根据当前状态选择终止符
                    termination_chars = self.initial_termination_chars if self.use_initial_chars else self.subsequent_termination_chars

                    # 找到任一终止符最早出现位置
                    termination_pos = self.find_first_termination_char(merged_text, termination_chars)

                    if termination_pos != -1:
                        # 切分文本(包含终止符)
                        split_point = termination_pos + 1
                        before_termination = merged_text[:split_point]
                        after_termination = merged_text[split_point:]

                        # 保留剩余文本
                        self.current_text = [after_termination]

                        # 处理 before termination
                        await self.tts_queue.put(before_termination)

                        # 切换终止符
                        if self.use_initial_chars:
                            self.use_initial_chars = False
                    else:
                        # 未找到终止符.等待更多文本
                        break
        except asyncio.TimeoutError:
            await self.log("[text_processing] 获取文本队列超时,等待处理剩余数据")
            # 超时表示队列空闲
            if self.current_text:
                # 合并处理剩余文本
                merged_text = ' '.join(self.current_text)

            # 应用禁止词汇替换
            if self.ban_pattern:
                merged_text = self.ban_pattern.sub('', merged_text)
            # 处理剩余文本
            await self.tts_queue.put(merged_text)

            self.current_text = []
            # 重置终止符 处理下一批次
            if self.use_initial_chars:
                self.use_initial_chars = True
        except asyncio.CancelledError:
            await self.log("[text_processing] run is cancelled")

    def find_first_termination_char(self, text: str, termination_chars: list):
        """
         查找文本中最早出现的终止符
        Args:
            text (str): 待处理文本
            termination_chars ( list): 终止符列表

        Returns:    第一个命中终止符的位置,否则返回-1

        """
        indices = [text.find(char) for char in termination_chars if char in text]
        return min(indices) if indices else -1

    def reset(self):
        self.current_text = []


