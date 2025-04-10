# -*- coding:utf-8 -*-
import asyncio

from wxauto import WeChat
from service.pipeline import Pipeline


async def main():
    pipeline = Pipeline()
    await pipeline.initialize_pipeline()
    wx = WeChat()
    pickup = True
    while True:
        pickup = wx.receive_call(pickup=pickup)
        if pickup:
            import time
            time.sleep(3)


if __name__ == '__main__':
    asyncio.run(main())
