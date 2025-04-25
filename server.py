# -*- coding:utf-8 -*-
import json

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from device.vb_devices import VBAudioDevice
from service.pipeline import Pipeline
from wxauto import WeChat
from utils.logger import logger
from beans.wx_req import WxContact

app = FastAPI()

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 根据实际情况调整
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
vb_device = VBAudioDevice()
wx = WeChat()
pipeline = Pipeline()


# 管理台-添加监控对象
@app.post("/add_monitor_object")
async def add_monitor_object(contact: WxContact):
    try:
        # await pipeline.initialize_pipeline(
        #     websocket=None,
        #     device=vb_device,
        #     wx=wx,
        # )
        who = contact.who
        await wx.AddListenChat(who, voice_call=True)
    except Exception as e:
        logger.error('add listenee error: %s' % e)


async def start():
    pass


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # 初始化 pipeline
    await pipeline.initialize_pipeline(
        websocket=websocket,
        device=vb_device,
        wx=wx,
    )

    try:
        while True:
            # data = await websocket.receive_bytes()  # 接收客户端发送的数据
            data = await websocket.receive()
            if 'text' in data:
                body = json.loads(data['text'])
                content = body['content']
                await pipeline.llm.post_text(content, pipeline.text_queue, pipeline.history_text_queue)
                # resp = BaseResp.gen_resp(MsgType.SYSTEM, '$clear$')
                await pipeline.send_text_queue.put("resp")
                # await pipeline.text_queue.put(result)
                print(f"Received text message: {content}")
            elif 'bytes' in data:
                # print(f"Received binary message: {data['binary']}")
                await pipeline.raw_audio_queue.put(data['bytes'])
    except WebSocketDisconnect:
        print("WebSocket disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await pipeline.shutdown()


if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8888, reload=True)
