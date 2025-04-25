# -*- coding:utf-8 -*-
import asyncio
from abc import ABC, abstractmethod
from typing import AsyncIterable

from utils.logger import logger


class BaseDevice(ABC):
    @abstractmethod
    async def collect_frames(self):
        pass

    @abstractmethod
    async def write_back(self, data):
        pass

    @abstractmethod
    async def set_queue(self, queue: asyncio.Queue):
        pass

    @abstractmethod
    async def toggle_device(self):
        pass

    async def log(self, message: str):
        logger.info(message)
