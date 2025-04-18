# -*- coding:utf-8 -*-
import asyncio
from abc import ABC, abstractmethod
from utils.logger import logger


class BaseDevice(ABC):
    @abstractmethod
    async def read_frame(self):
        pass

    @abstractmethod
    async def write_back(self, data):
        pass

    async def log(self, message: str):
        logger.info(message)
